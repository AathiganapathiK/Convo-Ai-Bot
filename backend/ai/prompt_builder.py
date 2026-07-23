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


def build_sql_prompt(question: str, history = None, company_id = None):

    history_text = ""

    if history:
        history_text = "\nConversation History:\n"

        for item in history[-2:]:
            history_text += (
                f"\nUser: {item['question']}"
                f"\nPrevious SQL: {item['sql_query']}"
            )

    if company_id:
        active_connection = ConnectionService.get_active_connection(company_id)
    else:
        active_connection = ConnectionService.get_active_connection_global()

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

    semantic_result = (
        SemanticResolver.resolve(
            active_connection["connection_id"],
            question
        )
    )
    print("\n========== SEMANTIC RESULT ==========")
    from pprint import pprint
    pprint(semantic_result)

    # Resolve initial relevant tables from matched semantic objects and keyword fallback
    relevant_tables = RelevantTableResolver.resolve(
        active_connection["connection_id"],
        question
    )
    print("\n========== RELEVANT TABLES ==========")
    pprint(relevant_tables)

    # Expand relationship bridge tables
    expanded_tables = RelationshipExpander.expand(
        active_connection["connection_id"],
        relevant_tables
    )

    
    table_names = [
        t["table_name"]
        for t in expanded_tables
    ]

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
    extra_req = metadata_result.get("required_tables", [])
    if extra_req:
        table_names = sorted(
            set(table_names + extra_req)
        )

    schema_text = RelevantSchemaService.get_schema(
        active_connection["connection_id"],
        table_names
    )


    # Format Metadata Rules
    metadata_rules_text = ""
    rules = metadata_result.get("metadata_rules", [])
    if rules:
        metadata_rules_text = (
            "\n"
            "--------------------------------\n"
            "Metadata Rules\n\n"
            "Technical key columns are relationship columns.\n"
            "Use them ONLY for JOIN conditions.\n"
            "Never return them in SELECT unless explicitly requested.\n\n"
        )
        formatted_rules = []
        for rule in rules:
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

    # === Pipeline Logging: STAGE RETRIEVAL DEBUG LOGS ===
    print("\n========== STAGE RETRIEVAL DEBUG LOGS ==========")
    print(f"Question                : {question}")
    print(f"Retrieved Tables        : {table_names}")
    print(f"Retrieved Metrics       : {semantic_result.get('metrics', [])}")
    print(f"Retrieved Dimensions    : {semantic_result.get('dimensions', [])}")
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

        examples_text = (
            "\n"
        )

        for example in examples:

            examples_text += (
                f"\nQuestion: "
                f"{example['question']}"
                f"\nSQL: "
                f"{example['sql_query']}\n"
            )

    semantic_context = SemanticContextService.build_context(
        semantic_result["metric_objects"],
        semantic_result["dimension_objects"]
    )

    # === GENERAL/ALL-SCHEMA PROMPT GENERATION (FOR COMPARISON LOGGING) ===
    try:
        all_tables_query = "SELECT st.table_name FROM schema_tables st WHERE st.connection_id = :connection_id"
        with engine.connect() as conn:
            all_tables_rows = conn.execute(text(all_tables_query), {"connection_id": active_connection["connection_id"]}).fetchall()
        all_tables = [r[0] for r in all_tables_rows]
        all_schema_text = RelevantSchemaService.get_schema(active_connection["connection_id"], all_tables)
    except Exception as e:
        all_schema_text = f"Error loading all schema: {e}"

    prompt_general = f"""
You are an expert Microsoft SQL Server SQL generator.

Database Schema:
{all_schema_text}

Relationships:
{relationship_context}

Rules:
- Schema above is the only source of truth.
- Use only tables and columns in schema.
- Never invent tables or columns.
- Generate Microsoft SQL Server SQL only.
- SELECT queries only.
- Use JOINs only when required.
- Return exactly one executable SQL statement.

SQL Server Rules:
- Never use ROW_NUMBER() inside GROUP BY.
- Never add integers directly to DATE values.
- Use DATEADD() for all date arithmetic.
- Window functions are allowed only in SELECT or ORDER BY.

OUTPUT RULES:
- Return SQL only.
- Never include : <think> or </think>
- No explanation.
- No markdown.
- No code fences.
- First character must be S in SELECT.

Conversation History:
{history_text}

Current Question:
{question}

Follow-up Rules:
- If history exists, preserve previous analytical intent
- For phrases like:
  show only, filter, sort, top, those, them,
  previous result, what about, instead
  modify previous SQL rather than creating a new analysis
"""

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

{semantic_result.get("values", [])}

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

    # === COMPARISON LOGGING IN TERMINAL ===
    print("\n" + "="*80)
    print(" [COMPARISON] PROMPT A: GENERAL (ALL SCHEMA, NO TABLE PRUNING, NO SEMANTIC CONTEXT)")
    print("="*80)
    print(prompt_general)
    print("="*80)

    print("\n" + "="*80)
    print(" [COMPARISON] PROMPT B: SEMANTIC (RELEVANT SCHEMA ONLY + SEMANTIC LAYER CONTEXT)")
    print("="*80)
    print(prompt)
    print("="*80)

    print("\n========== FINAL PROMPT STATS ==========")
    print(f"Expanded Schema Size : {len(schema_text)} chars")
    print(f"Final Prompt Size    : {len(prompt)} chars")
    print(f"Estimated Token Count: ~{len(prompt) // 4} tokens")
    print("========================================\n")

    return prompt


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
