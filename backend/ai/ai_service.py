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



def generate_sql_query(question: str, history = None, company_id = None):

    try:

        prompt = build_sql_prompt(
            question,
            history,
            company_id
        )

    except EnterpriseException as ex:

        return ex.to_dict()
    
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
    print("\n========== SQL ==========")
    print(sql_query)

    return {
        "sql_query": sql_query,
        "usage": response.usage
    }
# ______________________________________________________________________________________________________________________________________________

def generate_business_summary(question: str,sql_query: str,rows,company_id = None):

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

    print("\n========== SUMMARY ==========")
    print(f"Data Shape: {data_shape.value}")
    print("Summary Generated ✓")

    prompt = build_summary_prompt(
        question,
        sql_query,
        serialized_data,
        template
        )

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

    followups = FollowupGenerator.generate(
        question=question,
        serialized_data=serialized_data,
        company_id=company_id
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
            response.usage if response else None
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