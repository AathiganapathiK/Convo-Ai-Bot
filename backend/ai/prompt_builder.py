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

    tables = RelevantTableResolver.resolve(
        active_connection["connection_id"],
        question
    )

    tables = RelationshipExpander.expand(
        active_connection["connection_id"],
        tables
    )

    schema_text = RelevantSchemaService.get_schema(
        active_connection["connection_id"],
        tables
    )

    semantic_result = (
        SemanticResolver.resolve(
            active_connection["connection_id"],
            question
        )
    )

    relationship_context = (
        RelationshipContextService.build_context(
            active_connection["connection_id"],
            tables
        )
    )

    # === Pipeline Logging: SEMANTIC ===
    print("\n========== SEMANTIC ==========")
    print("Metrics:")
    if semantic_result["metrics"]:
        for metric in semantic_result["metrics"]:
            print(f"- {metric}")
    else:
        print("- (None)")
    print("Dimensions:")
    if semantic_result["dimensions"]:
        for dim in semantic_result["dimensions"]:
            print(f"- {dim}")
    else:
        print("- (None)")

    # === Pipeline Logging: TABLES ===
    print("\n========== TABLES ==========")
    print("Relevant Tables:")
    if tables:
        for table in tables:
            print(f"- {table}")
    else:
        print("- (None)")

    # === Pipeline Logging: RELATIONSHIPS ===
    print("\n========== RELATIONSHIPS ==========")
    if relationship_context:
        rel_lines = [line for line in relationship_context.strip().split("\n") if line.startswith("- ")]
        for line in rel_lines:
            print(line)

    examples = (
        QueryExamplesService
        .retrieve(
            active_connection["connection_id"]
        )
    )

    examples_text = ""

    if examples:

        examples_text = (
            "\nPrevious Successful Queries:\n"
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
You are an expert Microsoft SQL Server SQL generator.

Database Schema:
{schema_text}

Semantic Context:
{semantic_context}

Relationships:
{relationship_context}

Relevant Metrics:
{semantic_result["metrics"]}

Relevant Dimensions:
{semantic_result["dimensions"]}

Previous Successful Queries
{examples_text}

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
