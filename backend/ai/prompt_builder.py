from pprint import pprint
from typing import Optional, Dict, Any, List
from core.exceptions import SemanticRetrievalException
from database import engine
from sqlalchemy import text

from services.schema_context_service import SchemaContextService
from services.connection_service import ConnectionService

from semantic.semantic_resolver import  SemanticResolver
from semantic.semantic_context_service import SemanticContextService
from semantic.discovery_service import SemanticDiscoveryService
from semantic.query_examples_service import QueryExamplesService
from semantic.relationship_context_service import RelationshipContextService
from semantic.relevant_table_resolver import RelevantTableResolver
from semantic.relevant_schema_service import RelevantSchemaService
from semantic.relationship_expander import RelationshipExpander
from semantic.runtime_context_builder import RuntimeContextBuilder
from semantic.semantic_gate import SemanticGate
from core.logger import debug_print as print

from semantic.temporal import TimeResolver, TimeContextBuilder, TemporalPromptFormatter, TimeSettings, TemporalPipeline
from semantic.execution_context import SemanticExecutionContext

def get_dynamic_business_context(connection_id: str, company_id: str) -> str:
    query = """
    SELECT st.table_name, sc.column_name
    FROM schema_tables st
    INNER JOIN schema_columns sc ON st.table_id = sc.table_id
    WHERE st.connection_id = :connection_id
      AND st.company_id = :company_id
      AND LOWER(st.table_name) NOT IN (
          'companies',
          'users',
          'roles',
          'permissions',
          'role_permissions',
          'user_roles',
          'chat_sessions',
          'chat_messages',    
          'schema_tables',
          'schema_columns',
          'schema_relationships',
          'schema_drift_events',
          'database_connections',
          'audit_logs',
          'user_queries',
          'user_usage',
          'user_data_access',
          'role_column_access',
          'semantic_metrics',
          'semantic_dimensions',
          'api_keys',
          'base_config',
          'drifttest',
          'llm_fallbacks',
          'llm_models',
          'llm_providers',
          'provider_health'
      )
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query), {"connection_id": connection_id, "company_id": company_id}).fetchall()
    except Exception:
        return ""

    context_lines = []
    seen_mappings = set()

    heuristics = [
        ("revenue / sales amount", ["salesamount", "sales_amount", "revenue", "linetotal", "line_total", "amount", "price"]),
        ("product cost", ["productcost", "product_cost", "cost", "expense"]),
        ("units sold / quantity", ["quantity", "qty", "units"]),
        ("unit price / selling price", ["unitprice", "unit_price"]),
        ("sales date / date", ["orderdate", "order_date", "date", "timestamp", "created_at"]),
        ("customer / reseller / buyer", ["customer", "reseller", "buyer", "client", "customer_id", "reseller_id"]),
        ("employee / salesperson / staff", ["employee", "salesperson", "sales_rep", "salesrep", "staff"]),
        ("region / territory / location", ["region", "territory", "location", "country", "state", "city"]),
        ("sales target / goal", ["target", "goal", "quota"])
    ]

    for row in rows:
        table_name = row[0]
        column_name = row[1]
        
        # Exclude technical and audit columns
        if SemanticDiscoveryService.is_technical_column(column_name):
            continue
            
        col_lower = column_name.lower()
        tbl_lower = table_name.lower()

        for concept, substrings in heuristics:
            for sub in substrings:
                if sub in col_lower:
                    mapping = f"{table_name}.{column_name} = {concept}"
                    if mapping not in seen_mappings:
                        context_lines.append(f"- {mapping}")
                        seen_mappings.add(mapping)
                    break
        
        # Also check table name match for generic mapping
        if "product" in tbl_lower and "name" in col_lower:
            mapping = f"{table_name}.{column_name} = product name"
            if mapping not in seen_mappings:
                context_lines.append(f"- {mapping}")
                seen_mappings.add(mapping)
        elif "customer" in tbl_lower and "name" in col_lower:
            mapping = f"{table_name}.{column_name} = customer name"
            if mapping not in seen_mappings:
                context_lines.append(f"- {mapping}")
                seen_mappings.add(mapping)

    if not context_lines:
        return ""

    return "Business Context:\n" + "\n".join(context_lines)


class PromptBuilder:
    def __init__(
        self,
        temporal_pipeline: Optional[TemporalPipeline] = None,
        time_resolver: Optional[TimeResolver] = None,
        context_builder: Optional[TimeContextBuilder] = None,
        temporal_formatter: Optional[TemporalPromptFormatter] = None
    ):
        if temporal_pipeline:
            self.temporal_pipeline = temporal_pipeline
        else:
            self.temporal_pipeline = TemporalPipeline(
                time_resolver=time_resolver,
                context_builder=context_builder,
                temporal_formatter=temporal_formatter
            )

    def build_sql_prompt(
        self,
        question: str,
        history = None,
        company_id = None,
        connection_id: Optional[str] = None,
        settings: Optional[TimeSettings] = None,
        context: Optional[SemanticExecutionContext] = None
    ) -> tuple[str, dict, str]:
        history_text = ""

        if history:
            history_text = "\nConversation History:\n"

            for item in history[-2:]:
                history_text += (
                    f"\nUser: {item['question']}"
                    f"\nPrevious SQL: {item['sql_query']}"
                )

        if context is None:
            context = SemanticExecutionContext(
                connection_id=connection_id,
                company_id=company_id,
                settings=settings
            )

        active_connection = context.connection
        if not active_connection:
            raise ValueError("No active database connection found.")

        # Print all the Aggregation metrics, Dimensions, and Joins for the current active database connection
        try:
            from semantic.semantic_service import SemanticService
            from semantic.relationship_service import SemanticRelationshipService

            conn_id = active_connection["connection_id"]
            all_metrics = SemanticService.get_metrics(conn_id)
            all_dims = SemanticService.get_dimensions(conn_id)
            all_joins = SemanticRelationshipService.build_relationships(conn_id)

            print("\n========== ALL DB SEMANTIC METRICS, DIMENSIONS, AND JOINS (CURRENT DB) ==========")
            print(f"Connection Name: {active_connection.get('connection_name')}")
            print("Aggregation Metrics:")
            if all_metrics:
                for metric in all_metrics:
                    print(f"- {metric.get('metric_name')} ({metric.get('business_name')}): {metric.get('aggregation_type')}({metric.get('table_name')}.{metric.get('column_name')})")
            else:
                print("- (None)")

            print("Dimensions:")
            if all_dims:
                for dim in all_dims:
                    print(f"- {dim.get('dimension_name')} ({dim.get('business_name')}): {dim.get('table_name')}.{dim.get('column_name')}")
            else:
                print("- (None)")

            print("Joins:")
            if all_joins:
                for join in all_joins:
                    print(f"- {join[0]}.{join[1]} -> {join[2]}.{join[3]}")
            else:
                print("- (None)")
            print("=================================================================================\n")
        except Exception as e:
            print(f"Error printing DB semantic metadata: {e}")

        # Resolve temporal context
        temporal_section = self.temporal_pipeline.build(
            question=question,
            connection_id=context.connection_id,
            settings=context.settings
        )

        import time
        semantic_start_time = time.time()
        semantic_result = (
            SemanticResolver.resolve(
                active_connection["connection_id"],
                question
            )
        )
        semantic_time = round(time.time() - semantic_start_time, 2)
        if isinstance(semantic_result, dict):
            ret_dict = semantic_result.setdefault("retrieval", {})
            if isinstance(ret_dict, dict):
                ret_dict["time"] = semantic_time

        ret_confidence = 0.0
        ret_status = "Unknown"
        ret_reason = "None"
        if isinstance(semantic_result, dict):
            ret_data = semantic_result.get("retrieval")
            if isinstance(ret_data, dict):
                conf = ret_data.get("confidence")
                if isinstance(conf, (int, float)):
                    ret_confidence = float(conf)
                stat = ret_data.get("status")
                if isinstance(stat, str):
                    ret_status = stat
                reas = ret_data.get("reason")
                if isinstance(reas, str):
                    ret_reason = reas
        
        metric_objs = semantic_result.get("metric_objects", []) if isinstance(semantic_result, dict) else []
        dimension_objs = semantic_result.get("dimension_objects", []) if isinstance(semantic_result, dict) else []
        value_matches = semantic_result.get("value_matches", []) if isinstance(semantic_result, dict) else []
        
        resolved_tables_set = set()
        for obj in metric_objs:
            if isinstance(obj, dict):
                tname = obj.get("table_name")
                if isinstance(tname, str):
                    resolved_tables_set.add(tname)
        for obj in dimension_objs:
            if isinstance(obj, dict):
                tname = obj.get("table_name")
                if isinstance(tname, str):
                    resolved_tables_set.add(tname)
        for val in value_matches:
            if isinstance(val, dict):
                tname = val.get("table_name")
                if isinstance(tname, str):
                    resolved_tables_set.add(tname)
                
        resolved_tables = sorted(list(resolved_tables_set))
        
        filters_list: list[str] = []
        for v in value_matches:
            if isinstance(v, dict):
                col = v.get("column_name")
                op = v.get("operator", "=")
                val = v.get("value")
                if isinstance(col, str) and isinstance(val, (str, int, float)):
                    op_str = str(op) if op is not None else "="
                    filters_list.append(f"{col} {op_str} {str(val)}")
        resolved_filters_str = ', '.join(filters_list) or 'None'
        
        values_list: list[str] = []
        for v in value_matches:
            if isinstance(v, dict):
                val = v.get("value")
                if val is not None:
                    values_list.append(str(val))
        resolved_values_str = ', '.join(values_list) or 'None'

        metrics_list: list[str] = []
        for m in metric_objs:
            if isinstance(m, dict):
                bname = m.get("business_name")
                if isinstance(bname, str):
                    metrics_list.append(bname)
        resolved_metrics_str = ', '.join(metrics_list) or 'None'

        dims_list: list[str] = []
        for d in dimension_objs:
            if isinstance(d, dict):
                bname = d.get("business_name")
                if isinstance(bname, str):
                    dims_list.append(bname)
        resolved_dims_str = ', '.join(dims_list) or 'None'

        resolved_tables_str = ', '.join(resolved_tables) or 'None'

        print("\n========== SEMANTIC RESOLUTION ==========")
        print(f"Question: {question}")
        print(f"Resolved Metrics: {resolved_metrics_str}")
        print(f"Resolved Dimensions: {resolved_dims_str}")
        print(f"Resolved Filters: {resolved_filters_str}")
        print(f"Resolved Values: {resolved_values_str}")
        print(f"Resolved Tables: {resolved_tables_str}")
        print(f"Semantic Confidence: {ret_confidence}")
        print(f"Retrieval Status: {ret_status}")
        print(f"Reason: {ret_reason}")
        print("=========================================")

        # --------------------------------------------------
        # Semantic Retrieval Gate
        # --------------------------------------------------

        gate_result = SemanticGate.evaluate(semantic_result)

        print("\n========== RETRIEVAL GATE ==========")

        retrieval = semantic_result.get("retrieval")

        if isinstance(retrieval, dict):
            print(f"Retrieval Status: {retrieval.get('status', 'Unknown')}")
            print(f"Confidence: {retrieval.get('confidence', 0.0)}")
        else:
            print("Retrieval Status: Unknown")
            print("Confidence: 0.0")

        print(f"Decision: {'ALLOW SQL' if gate_result['allowed'] else 'BLOCK SQL'}")
        print(f"Reason: {gate_result.get('reason', 'None')}")
        print("====================================")
        
        # --------------------------------------------------
        # Stop pipeline if semantic retrieval failed
        # --------------------------------------------------

        if not gate_result["allowed"]:

            print("\n========== SEMANTIC GATE BLOCKED ==========")
            print(gate_result["reason"])

            raise SemanticRetrievalException(
                details={
                    "question": question,
                    "retrieval": semantic_result["retrieval"]
                }
            )

        # Resolve initial relevant tables from matched semantic objects and keyword fallback
        relevant_tables = RelevantTableResolver.resolve(
            semantic_result
        )
        print("\n========== RELEVANT TABLES ==========")
        pprint(relevant_tables)

        # Expand relationship bridge tables
        expanded_tables = RelationshipExpander.expand(
            active_connection["connection_id"],
            relevant_tables
        )

        table_names: list[str] = []
        if isinstance(expanded_tables, list):
            for t in expanded_tables:
                if isinstance(t, dict):
                    tname = t.get("table_name")
                    if isinstance(tname, str):
                        table_names.append(tname)

        relationship_context = (
            RelationshipContextService.build_context(
                active_connection["connection_id"],
                table_names
            )
        )

        print("\n========== EXPANDED TABLES ==========")
        pprint(expanded_tables)

        from semantic.metadata_resolver import MetadataResolver
        
        metadata_result = MetadataResolver.resolve(
            question=question,
            connection_id=active_connection["connection_id"],
            semantic_result=semantic_result,
            expanded_tables=expanded_tables
        )

        print("\n========== METADATA RESULT ==========")
        pprint(metadata_result)

        runtime_context = RuntimeContextBuilder.build(
            metadata_result
        )

        if relationship_context:
            runtime_context += (
                "\n\n"
                "=== RELATIONSHIP CONTEXT ===\n\n"
                f"{relationship_context}"
            )

        # Add required tables from metadata resolver if any extra display tables were needed
        extra_req = metadata_result.get("required_tables", []) if isinstance(metadata_result, dict) else []
        if isinstance(extra_req, list):
            for req in extra_req:
                if isinstance(req, str) and req not in table_names:
                    table_names.append(req)
        table_names = sorted(table_names)

        schema_text = RelevantSchemaService.get_schema(
            active_connection["connection_id"],
            table_names
        )

        # Format Metadata Rules
        metadata_rules_text = ""
        rules = metadata_result.get("metadata_rules", []) if isinstance(metadata_result, dict) else []
        if isinstance(rules, list) and rules:
            metadata_rules_text = (
                "\n"
                "--------------------------------\n"
                "Metadata Rules\n\n"
                "Technical key columns are relationship columns.\n"
                "Use them ONLY for JOIN conditions.\n"
                "Never return them in SELECT unless explicitly requested.\n\n"
            )
            formatted_rules: list[str] = []
            for rule in rules:
                if not isinstance(rule, str):
                    continue
                if rule.startswith("Use ") and " instead of " in rule:
                    parts = rule.split(" instead of ")
                    bus_col = parts[0][4:]
                    remainder = parts[1]
                    
                    if " for SELECT, GROUP BY, ORDER BY. Continue using " in remainder:
                        parts2 = remainder.split(" for SELECT, GROUP BY, ORDER BY. Continue using ")
                        tech_col = parts2[0]
                        join_cond = parts2[1].replace(" inside JOIN.", "")
                        
                        formatted_rules.append(
                            f"Use\n{bus_col}\ninstead of\n{tech_col}\nfor\nSELECT\nGROUP BY\nORDER BY\n\n"
                            f"Continue using\n{join_cond}\ninside JOIN."
                        )
                    else:
                        tech_col = remainder.replace(" for SELECT, GROUP BY, ORDER BY", "")
                        formatted_rules.append(
                            f"Use\n{bus_col}\ninstead of\n{tech_col}\nfor\nSELECT\nGROUP BY\nORDER BY"
                        )
                elif rule.startswith("Keep ") and " because user explicitly requested it. Include both " in rule:
                    parts = rule.split(" because user explicitly requested it. Include both ")
                    tech_col = parts[0][5:]
                    remainder = parts[1]
                    
                    parts2 = remainder.split(" and ")
                    remainder2 = parts2[1]
                    
                    if " in SELECT. Continue using " in remainder2:
                        parts3 = remainder2.split(" in SELECT. Continue using ")
                        bus_col = parts3[0]
                        join_cond = parts3[1].replace(" inside JOIN.", "")
                        
                        formatted_rules.append(
                            f"Keep {tech_col} because user explicitly requested it.\n"
                            f"Include both\n{tech_col}\n+\n{bus_col}\nin SELECT.\n\n"
                            f"Continue using\n{join_cond}\ninside JOIN."
                        )
                    else:
                        bus_col = remainder2.replace(" in SELECT.", "")
                        formatted_rules.append(
                            f"Keep {tech_col} because user explicitly requested it.\n"
                            f"Include both\n{tech_col}\n+\n{bus_col}\nin SELECT."
                        )
                else:
                    formatted_rules.append(rule)
            
            metadata_rules_text += "\n\n".join(formatted_rules) + "\n\n"
            metadata_rules_text += (
                "LLM SQL Rules:\n"
                "Rule 1: JOINs always use technical keys.\n"
                "        Example: ON Sales.ProductKey = Products.ProductKey\n"
                "Rule 2: SELECT always uses descriptive columns.\n"
                "        Example: Products.Product\n"
                "Rule 3: GROUP BY uses descriptive columns.\n"
                "        Example: GROUP BY Products.Product\n"
                "Rule 4: ORDER BY uses aliases or descriptive columns.\n"
                "Rule 5: If user explicitly requests Key, ID, Code, Identifier, Number, Reference,\n"
                "        then include BOTH technical key and descriptive column.\n"
                "--------------------------------\n"
            )

        ret_metrics: list[str] = []
        if isinstance(semantic_result, dict):
            m_objects = semantic_result.get("metric_objects", [])
            if isinstance(m_objects, list):
                for m in m_objects:
                    if isinstance(m, dict):
                        mname = m.get("metric_name")
                        if isinstance(mname, str):
                            ret_metrics.append(mname)

        ret_dims: list[str] = []
        if isinstance(semantic_result, dict):
            d_objects = semantic_result.get("dimension_objects", [])
            if isinstance(d_objects, list):
                for d in d_objects:
                    if isinstance(d, dict):
                        dname = d.get("dimension_name")
                        if isinstance(dname, str):
                            ret_dims.append(dname)

        # === Pipeline Logging: STAGE RETRIEVAL DEBUG LOGS ===
        print("\n========== STAGE RETRIEVAL DEBUG LOGS ==========")
        print(f"Question                : {question}")
        print(f"Retrieved Tables        : {table_names}")
        print(f"Retrieved Metrics       : {ret_metrics}")
        print(f"Retrieved Dimensions    : {ret_dims}")
        print(f"Retrieved Metadata Rules: {rules}")
        print(f"Retrieved Relationships :\n{relationship_context.strip() if relationship_context else '(None)'}")
        print("================================================\n")

        examples = (
            QueryExamplesService
            .retrieve(
                active_connection["connection_id"],
                relevant_tables=table_names
            )
        )

        examples_text = ""

        if examples:
            examples_text = "\n"
            for example in examples:
                examples_text += (
                    f"\nQuestion: "
                    f"{example['question']}"
                    f"\nSQL: "
                    f"{example['sql_query']}\n"
                )

        metric_objects_list = semantic_result.get("metric_objects", []) if isinstance(semantic_result, dict) else []
        dimension_objects_list = semantic_result.get("dimension_objects", []) if isinstance(semantic_result, dict) else []
        semantic_context = SemanticContextService.build_context(
            metric_objects_list,
            dimension_objects_list,
            dialect=active_connection.get("database_type")
        )

        print("\n========== SEMANTIC CONTEXT ==========")
        print("Metrics:")
        metric_objs_ctx = semantic_result.get("metric_objects") if isinstance(semantic_result, dict) else None
        if isinstance(metric_objs_ctx, list) and metric_objs_ctx:
            for m in metric_objs_ctx:
                if isinstance(m, dict):
                    bname = m.get("business_name")
                    tname = m.get("table_name")
                    cname = m.get("column_name")
                    agg = m.get("aggregation_type")
                    if bname is not None and tname is not None and cname is not None and agg is not None:
                        print(f"- {bname} ({tname}.{cname} as {agg})")
        else:
            print("- None")
        
        print("\nDimensions:")
        dimension_objs_ctx = semantic_result.get("dimension_objects") if isinstance(semantic_result, dict) else None
        if isinstance(dimension_objs_ctx, list) and dimension_objs_ctx:
            for d in dimension_objs_ctx:
                if isinstance(d, dict):
                    bname = d.get("business_name")
                    tname = d.get("table_name")
                    cname = d.get("column_name")
                    if bname is not None and tname is not None and cname is not None:
                        print(f"- {bname} ({tname}.{cname})")
        else:
            print("- None")
            
        print("\nRelationships:")
        if relationship_context:
            print(relationship_context.strip())
        else:
            print("- None")
            
        print("\nValues:")
        val_matches_ctx = semantic_result.get("value_matches") if isinstance(semantic_result, dict) else None
        if isinstance(val_matches_ctx, list) and val_matches_ctx:
            for v in val_matches_ctx:
                if isinstance(v, dict):
                    val = v.get("value")
                    tname = v.get("table_name")
                    cname = v.get("column_name")
                    if val is not None and tname is not None and cname is not None:
                        print(f"- {val} ({tname}.{cname})")
        else:
            print("- None")
            
        print("\nSQL Expressions:")
        has_expr = False
        dimension_objs_expr = semantic_result.get("dimension_objects") if isinstance(semantic_result, dict) else None
        if isinstance(dimension_objs_expr, list) and dimension_objs_expr:
            for d in dimension_objs_expr:
                if isinstance(d, dict):
                    category = d.get("semantic_category")
                    dialect = active_connection.get("database_type")
                    col_name = d.get("column_name")
                    bname = d.get("business_name")
                    if isinstance(category, str) and category.startswith("TIME_") and isinstance(dialect, str) and isinstance(col_name, str) and bname is not None:
                        from semantic.sql.temporal_mapper import TemporalMapper
                        expr = TemporalMapper.get_sql_expression(dialect, category, col_name)
                        print(f"- {bname}: {expr}")
                        has_expr = True
        if not has_expr:
            print("- None")
        print("======================================")

        # === GENERAL/ALL-SCHEMA PROMPT GENERATION (FOR COMPARISON LOGGING) ===
        try:
            all_tables_query = "SELECT st.table_name FROM schema_tables st WHERE st.connection_id = :connection_id"
            with engine.connect() as conn:
                all_tables_rows = conn.execute(text(all_tables_query), {"connection_id": active_connection["connection_id"]}).fetchall()
            all_tables = [r[0] for r in all_tables_rows]
            all_schema_text = RelevantSchemaService.get_schema(active_connection["connection_id"], all_tables)
        except Exception as e:
            all_schema_text = f"Error loading all schema: {e}"

        prompt = f"""
You are an expert Microsoft SQL Server SQL generator for an Enterprise Conversational Analytics Platform.

Your objective is to generate ONE correct Microsoft SQL Server SELECT query.

===========================================================
USER QUESTION
===========================================================

{question}

===========================================================
CONVERSATION HISTORY
===========================================================

{history_text}

{temporal_section}

===========================================================
SEMANTIC RUNTIME
===========================================================

{runtime_context}

===========================================================
SEMANTIC CONTEXT
===========================================================

{semantic_context}

===========================================================
RELEVANT METRICS
===========================================================

{semantic_result["metrics"]}

===========================================================
RELEVANT DIMENSIONS
===========================================================

{semantic_result["dimensions"]}

===========================================================
MATCHED DIMENSION VALUES
===========================================================

{semantic_result.get("value_matches", [])}

===========================================================
PREVIOUS SUCCESSFUL QUERIES
===========================================================

{examples_text}

===========================================================
METADATA RULES
===========================================================

{metadata_rules_text}

===========================================================
DATABASE SCHEMA
===========================================================

{schema_text}

===========================================================
SQL GENERATION RULES
===========================================================

1. Database Schema is the only physical source of truth.
2. Never invent tables.
3. Never invent columns.
4. Generate Microsoft SQL Server SQL only.
5. Generate exactly ONE executable SELECT statement.
6. Never generate INSERT.
7. Never generate UPDATE.
8. Never generate DELETE.
9. Never generate DROP.
10. Never generate ALTER.
11. Never generate CREATE.

===========================================================
SEMANTIC SQL RULES
===========================================================

1. Use the Semantic Runtime as the primary reasoning source.
2. Use the Database Schema only for validation.
3. Use only the Resolved Tables unless another table is absolutely required.
4. Use only the Relationships provided in the Semantic Runtime.
5. Never invent joins.
6. Prefer descriptive business columns over technical columns.
7. Technical keys must only be used in JOIN conditions unless the user explicitly requests them.
8. Respect all Metadata Rules.
9. Follow the style demonstrated by Previous Successful Queries whenever possible.
10. If a dimension has a specified SQL Expression under SEMANTIC CONTEXT, you MUST use that SQL Expression in the SELECT, GROUP BY, WHERE, and ORDER BY clauses instead of the raw physical column name.

===========================================================
SQL SERVER RULES
===========================================================

- Never use ROW_NUMBER() inside GROUP BY.
- Never add integers directly to DATE values.
- Use DATEADD() for all date arithmetic.
- Window functions are allowed only in SELECT or ORDER BY.
- Always qualify ambiguous columns with table names.
- Use aliases only when they improve readability.

===========================================================
FOLLOW-UP RULES
===========================================================

If conversation history exists:

- Preserve previous analytical intent.
- Understand references such as:
    • show only
    • those
    • them
    • previous result
    • what about
    • instead
    • top
    • filter
    • sort

Modify the previous SQL whenever appropriate instead of generating an entirely unrelated query.

===========================================================
OUTPUT RULES
===========================================================

- Return SQL only.
- No explanation.
- No markdown.
- No code fences.
- Never output <think>.
- Never output </think>.
- First character must be SELECT.

"""

        # Estimate tokens: roughly 1 token = 4 characters or word count
        estimated_tokens = len(prompt) // 4
        
        print("\n========== PROMPT ==========")
        print(f"Prompt Length: {len(prompt)}")
        print(f"Prompt Tokens (estimated): {estimated_tokens}")
        print(f"Database Type: {active_connection.get('database_type')}")
        print(f"Schema Tables Used: {', '.join(table_names) if table_names else 'None'}")
        print(f"Semantic Objects: {len(semantic_result.get('metric_objects', [])) + len(semantic_result.get('dimension_objects', []))}")
        print(f"Conversation Messages: {len(history) if history else 0}")
        print("================================\n")

        return prompt, semantic_result, runtime_context


def build_sql_prompt(
    question: str,
    history = None,
    company_id = None,
    connection_id: Optional[str] = None,
    settings: Optional[TimeSettings] = None,
    context: Optional[SemanticExecutionContext] = None
) -> tuple[str, dict, str]:
    builder = PromptBuilder()
    return builder.build_sql_prompt(
        question=question,
        history=history,
        company_id=company_id,
        connection_id=connection_id,
        settings=settings,
        context=context
    )


def build_summary_prompt(
    question,
    sql_query,
    serialized_data,
    template
):

    prompt = f"""
    User Question:
    {question}

    SQL Query:
    {sql_query}

    Query Result:
    {serialized_data}

    {template}
    """

    return prompt
