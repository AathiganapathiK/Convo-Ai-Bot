from core.exceptions import EnterpriseException
from core.exceptions import SemanticRetrievalException
from ai.providers.provider_factory import (
    ProviderFactory
)


from services.model_routing_service import (
    ModelRoutingService
)

from ai.prompt_builder import (
    build_sql_prompt,
    build_summary_prompt
)

from services.llm_execution_service import (
    LLMExecutionService
)
from core.logger import debug_print as print

from ai.insights.data_shape_classifier import (
    DataShapeClassifier
)

from ai.insights.serializer import (
    SmartSerializer
)

from ai.insights.prompt_resolver import (
    PromptResolver
)

from ai.insights.followup_generator import (
    FollowupGenerator
)

print("FOLLOWUP GENERATOR LOADED")

# DEPRECATED: get_llm_provider() is deprecated.
# Runtime routing has migrated to LLMExecutionService.execute() which dynamically routes and retries 
# using the active llm_fallbacks list, avoiding single-point-of-failure defaults.
def get_llm_provider(
    purpose: str
):

    provider_config = (
        ModelRoutingService
        .get_model_for_purpose(
            purpose
        )
    )

    provider = (
        ProviderFactory
        .get_provider(
            provider_config[
                "provider_type"
            ]
        )
    )

    return (
        provider,
        provider_config[
            "model_name"
        ]
    )



def generate_sql_query(question: str, history = None, company_id = None, clarified_candidate = None, guard_feedback = None):

    try:

        prompt, semantic_result, runtime_context = build_sql_prompt(
            question,
            history,
            company_id,
            clarified_candidate=clarified_candidate
        )

    except EnterpriseException as ex:

        return ex.to_dict()

    # Gate 5 Step 32: on a plan-conformance retry, the deterministic guard's
    # findings are appended to the prompt the builder produced. Appending here
    # rather than inside the prompt builder keeps that 1,200-line shared file
    # untouched, since build_sql_prompt already returns the prompt as text.
    if guard_feedback:
        prompt = f"{prompt}\n\n{guard_feedback}"
    
    import time
    start_time = time.time()
    response = (    
        LLMExecutionService.execute(
            purpose=
                "sql_generation",

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            company_id=company_id
        )
    )
    gen_time = round(time.time() - start_time, 2)

    sql_query = ""
    if response and getattr(response, "choices", None):
        choice = response.choices[0]
        if choice and getattr(choice, "message", None):
            message = choice.message
            if message and getattr(message, "content", None) is not None:
                sql_query = message.content

    # Remove markdown formatting
    if sql_query:
        sql_query = sql_query.replace("```sql", "")
        sql_query = sql_query.replace("```", "")
        sql_query = sql_query.strip()

    # TEMP_PIPELINE_TRACE_REMOVE_LATER
    try:
        from semantic.diagnostic_trace import PipelineDiagnosticTracer
        PipelineDiagnosticTracer.record_sql("generated", sql_query)
    except Exception:
        pass

    model_name = getattr(response, "model", "Unknown") if response else "Unknown"

    print("\n========== SQL GENERATION ==========")
    print(f"Model: {model_name}")
    print(f"Temperature: 0.0")
    print(f"Attempt: 1")
    print(f"Generation Time: {gen_time}s")
    print("====================================")

    print("\n========== GENERATED SQL ==========")
    print(sql_query)
    print("===================================")

    # Structured temporal verification logging
    try:
        from semantic.temporal.pipeline import TemporalPipeline
        from semantic.execution_context import SemanticExecutionContext
        from semantic.sql.temporal_mapper import TemporalMapper
        from semantic.temporal.enums import TimeStrategyType, Granularity
        import datetime

        time_res = TemporalPipeline.get_last_resolution()
        intent = TemporalPipeline.get_last_intent()

        print("\n============================================================\nTEMPORAL VERIFICATION\n============================================================")
        print(f"Question: {question}")

        if not intent or not time_res or not time_res.resolved:
            print("Temporal Detected : NO")
            print("============================================================")
        else:
            intent_name = intent.__class__.__name__
            plan = time_res.plan

            strategy = plan.strategy.value if (plan and plan.strategy) else "None"
            granularity = plan.grouping.value if (plan and plan.grouping) else "None"
            ref_date = getattr(intent, "reference_date", None) or getattr(plan, "reference_date", None) or datetime.date.today()
            ref_date_str = ref_date.isoformat() if ref_date else "None"

            start_date_str = plan.start_date.isoformat() if (plan and plan.start_date) else "None"
            end_date_str = plan.end_date.isoformat() if (plan and plan.end_date) else "None"

            print(f"Temporal Intent: {intent_name}")
            print(f"Strategy: {strategy}")
            print(f"Granularity: {granularity}")
            print(f"Reference Date: {ref_date_str}")
            print(f"Resolved Start Date: {start_date_str}")
            print(f"Resolved End Date: {end_date_str}")

            expected_fragments = []
            if plan:
                context = SemanticExecutionContext(company_id=company_id)
                dialect = "mssql"
                if context.connection and context.connection.get("database_type"):
                    dialect = context.connection.get("database_type")

                if plan.strategy == TimeStrategyType.SNAPSHOT:
                    if plan.snapshot_columns:
                        expected_fragments.extend(plan.snapshot_columns)
                else:
                    date_col = plan.date_column or "OrderDate"
                    if "Quarter" in intent_name or "QTD" in intent_name:
                        expected_fragments.append(TemporalMapper.get_sql_expression(dialect, "TIME_QUARTER", date_col))
                    elif "Month" in intent_name or "MTD" in intent_name:
                        expected_fragments.append(TemporalMapper.get_sql_expression(dialect, "TIME_MONTH", date_col))
                        expected_fragments.append(TemporalMapper.get_sql_expression(dialect, "TIME_YEAR", date_col))
                    elif "Year" in intent_name or "YTD" in intent_name:
                        expected_fragments.append(TemporalMapper.get_sql_expression(dialect, "TIME_YEAR", date_col))
                    elif "Week" in intent_name:
                        expected_fragments.append(TemporalMapper.get_sql_expression(dialect, "TIME_WEEK", date_col))
                    elif "Day" in intent_name:
                        expected_fragments.append(TemporalMapper.get_sql_expression(dialect, "TIME_DAY", date_col))
                    else:
                        if plan.grouping and plan.grouping != Granularity.AUTO:
                            cat = f"TIME_{plan.grouping.name}"
                            expected_fragments.append(TemporalMapper.get_sql_expression(dialect, cat, date_col))
                        else:
                            expected_fragments.append(date_col)

            expected_frag_str = ", ".join(expected_fragments) if expected_fragments else "None"
            print(f"Expected SQL Fragment: {expected_frag_str}")
            print(f"Generated SQL: {sql_query}")

            validation_status = "FAIL"
            validation_reason = ""
            if not expected_fragments:
                validation_status = "PASS"
                validation_reason = "No specific expected temporal SQL fragments to validate."
            else:
                missing_fragments = []
                sql_cleaned = sql_query.upper().replace(" ", "")
                for frag in expected_fragments:
                    frag_cleaned = frag.upper().replace(" ", "")
                    if frag_cleaned not in sql_cleaned:
                        missing_fragments.append(frag)

                if missing_fragments:
                    validation_reason = f"Missing expected SQL fragments: {', '.join(missing_fragments)}"
                else:
                    validation_status = "PASS"
                    validation_reason = "All expected temporal SQL fragments present."

            print(f"Temporal SQL Validation: {validation_status}")
            print(f"Reason: {validation_reason}")
            print("============================================================")
    except Exception as exc:
        pass

    return {
        "sql_query": sql_query,
        "usage": response.usage if response else None,
        "semantic_result": semantic_result,
        "runtime_context": runtime_context,
        "gen_time": gen_time
    }
# ______________________________________________________________________________________________________________________________________________

def generate_business_summary(
    question,
    sql_query,
    rows,
    semantic_result,
    runtime_context,
    history=None,
    company_id=None,
    connection_id=None,
    grounding_feedback=None
):

    data_shape = (
        DataShapeClassifier
        .classify(
            rows,
            question
        )
    )

    template = (
        PromptResolver
        .get_template(
            data_shape
        )
    )

    serialized_data = (
        SmartSerializer.serialize(
            rows,
            data_shape
        )
    )

    # Section 12: DATA SHAPE
    cols_count = len(rows[0].keys()) if rows else 0
    print("\n========== DATA SHAPE ==========")
    print(f"Detected Shape: {data_shape.name if hasattr(data_shape, 'name') else str(data_shape)}")
    print(f"Rows: {len(rows)}")
    print(f"Columns: {cols_count}")
    print("Chart Recommendation: True")
    print("================================")

    prompt = build_summary_prompt(
        question,
        sql_query,
        serialized_data,
        template
    )

    # Gate 6 Step 33: on a grounding retry, the deterministic validator's
    # findings are appended to the prompt. Appended here rather than inside the
    # prompt builder so that shared file stays untouched, matching how Step 32
    # feeds SQL guard findings back.
    if grounding_feedback:
        prompt = f"{prompt}\n\n{grounding_feedback}"

    import time
    start_sum = time.time()
    response = (
        LLMExecutionService.execute(
            purpose="insight",

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            company_id=company_id
        )
    )
    sum_time = round(time.time() - start_sum, 2)
    model_used = getattr(response, "model", "Unknown") if response else "Unknown"

    print("\n========== BUSINESS SUMMARY ==========")
    print("Summary Enabled: True")
    print(f"LLM Used: {model_used}")
    print(f"Summary Time: {sum_time}s")
    print("=====================================")

    followups = FollowupGenerator.generate(
        question=question,
        serialized_data=serialized_data,
        semantic_result=semantic_result,
        runtime_context=runtime_context,
        history=history,
        company_id=company_id,
        connection_id=connection_id
    )

    summary = ""
    if response and getattr(response, "choices", None):
        choice = response.choices[0]
        if choice and getattr(choice, "message", None):
            message = choice.message
            if message and getattr(message, "content", None) is not None:
                summary = message.content

    return {
        "summary":
            summary,

        "followups":
            followups,

        "usage":
            response.usage if response else None,
        "sum_time": sum_time
    }

# Use the Intl.NumberFormat API in JavaScript/TypeScript, which natively supports the Indian numbering system via the en-IN locale. This is the most robust and standard method.

# const formatter = new Intl.NumberFormat('en-IN', {
#   style: 'currency',
#   currency: 'INR',
#   minimumFractionDigits: 2,
#   maximumFractionDigits: 2,
# });

# console.log(formatter.format(150000));   // Output: ₹1,50,000.00
# console.log(formatter.format(12000000)); // Output: ₹1,20,00,000.00