import re
from sqlalchemy import text
from database import engine
from services.connection_service import ConnectionService


# Common English stopwords to filter out from questions
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when", "at", "by", 
    "for", "with", "about", "against", "between", "into", "through", "during", "before", 
    "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", 
    "over", "under", "again", "further", "then", "once", "here", "there", "when", 
    "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", 
    "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", 
    "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now",
    "show", "get", "find", "list", "select", "display", "query", "run", "what", "is", 
    "are", "was", "were", "be", "been", "being", "have", "has", "had", "having", 
    "do", "does", "did", "doing", "of", "top", "bottom", "highest", "lowest", "most", "least"
}

# Synonym mapping to align natural language with DB naming conventions
SYNONYMS = {
    "revenue": ["sales", "sales_amount", "amount", "price", "revenue", "line_total", "total"],
    "cost": ["product_cost", "cost", "price", "margin", "profit"],
    "profit": ["margin", "profit", "sales_amount", "product_cost"],
    "salesperson": ["salesperson", "employee", "staff", "sales_rep", "salesperson_id"],
    "rep": ["salesperson", "sales_rep"],
    "reseller": ["reseller", "partner", "merchant", "reseller_name"],
    "customer": ["customer", "client", "buyer"],
    "product": ["products", "product", "item", "goods", "sku", "product_name"],
    "items": ["products", "product", "item"],
    "region": ["region", "territory", "country", "state", "city", "location"],
    "target": ["targets", "target", "goal", "quota"],
    "drift": ["drift", "drifttest"]
}

# Internal metadata tables that should never be included in schema context
INTERNAL_TABLES = {
    "api_keys", "llm_providers", "llm_models", "provider_health", 
    "base_config", "user_roles", "companies", "llm_fallbacks", 
    "audit_logs", "user_queries", "users"
}

class SchemaContextService:
    @staticmethod
    def stem_word(word: str) -> str:
        """Simple stemmer to map plurals to singulars for database schema matching."""
        word = word.lower()
        if word.endswith("ies"):
            return word[:-3] + "y"
        if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
            return word[:-1]
        return word

    @staticmethod
    def tokenize_question(question: str) -> set[str]:
        """
        Tokenizes the question, removes stopwords, and expands with synonyms.
        """
        # Split by non-alphanumeric characters and lowercase
        words = re.findall(r'\b\w+\b', question.lower())
        tokens = {w for w in words if w not in STOPWORDS}
        
        # Stem all base tokens
        stemmed_tokens = {SchemaContextService.stem_word(t) for t in tokens}
        
        # Expand with synonyms (also stemmed)
        expanded_tokens = set(stemmed_tokens)
        for token in stemmed_tokens:
            if token in SYNONYMS:
                expanded_tokens.update({SchemaContextService.stem_word(syn) for syn in SYNONYMS[token]})
        return expanded_tokens

    @staticmethod
    def get_relevant_schema(company_id: str = None, question: str = "") -> str:
        """
        Retrieves only the relevant tables, columns, and relationships
        based on the user's question and active database connection metadata.
        """
        # Resolve active connection
        if company_id:
            active_conn = ConnectionService.get_active_connection(company_id)
        else:
            active_conn = ConnectionService.get_active_connection_global()
            
        if not active_conn:
            return "No active database connection configured."
            
        connection_id = active_conn["connection_id"]
        if not company_id:
            company_id = active_conn.get("company_id")
        tokens = SchemaContextService.tokenize_question(question)
        
        # 1. Fetch tables
        query_tables = """
        SELECT table_id, schema_name, table_name, table_type
        FROM schema_tables
        WHERE connection_id = :connection_id AND company_id = :company_id
        """
        with engine.connect() as conn:
            tables_res = conn.execute(
                text(query_tables),
                {"connection_id": connection_id, "company_id": company_id}
            ).fetchall()
            
        # Filter out internal tables and respect ALLOWED_TABLES
        business_tables = []
        for row in tables_res:
            t_schema = row._mapping["schema_name"]
            t_name = row._mapping["table_name"]
            full_name = f"{t_schema}.{t_name}"
            business_tables.append(row._mapping)
                
        if not business_tables:
            return "No schema tables found for the active connection. Run schema sync."
            
        # 2. Fetch columns
        query_columns = """
        SELECT column_id, table_id, column_name, data_type, is_primary_key, is_foreign_key, is_nullable
        FROM schema_columns
        WHERE company_id = :company_id AND table_id IN (
            SELECT table_id FROM schema_tables 
            WHERE connection_id = :connection_id AND company_id = :company_id
        )
        """
        with engine.connect() as conn:
            columns_res = conn.execute(
                text(query_columns),
                {"connection_id": connection_id, "company_id": company_id}
            ).fetchall()
            
        # Map columns by table_id
        columns_by_table = {}
        for row in columns_res:
            t_id = row._mapping["table_id"]
            if t_id not in columns_by_table:
                columns_by_table[t_id] = []
            columns_by_table[t_id].append(row._mapping)
            
        # 3. Fetch relationships
        query_rels = """
        SELECT relationship_id, source_table_id, source_column_id, target_table_id, target_column_id
        FROM schema_relationships
        WHERE company_id = :company_id
        """
        with engine.connect() as conn:
            rels_res = conn.execute(
                text(query_rels),
                {"company_id": company_id}
            ).fetchall()
            
        # 4. Identify directly matched tables
        directly_matched_ids = set()
        for tbl in business_tables:
            t_id = tbl["table_id"]
            t_name = tbl["table_name"].lower()
            
            # Split table name (e.g. SalespersonRegion -> salesperson, region)
            t_parts = re.findall(r'[a-zA-Z0-9]+', t_name)
            t_parts_stemmed = {SchemaContextService.stem_word(p) for p in t_parts}
            
            # Match table name parts with tokens
            name_match = any(part in tokens for part in t_parts_stemmed)
            
            # Match columns with tokens
            col_match = False
            tbl_cols = columns_by_table.get(t_id, [])
            for col in tbl_cols:
                col_name = col["column_name"].lower()
                col_parts = re.findall(r'[a-zA-Z0-9]+', col_name)
                col_parts_stemmed = {SchemaContextService.stem_word(p) for p in col_parts}
                if any(part in tokens for part in col_parts_stemmed):
                    col_match = True
                    break
                    
            if name_match or col_match:
                directly_matched_ids.add(t_id)
                
        # 5. Expand matched tables using 1-hop relationship neighbors
        selected_table_ids = set(directly_matched_ids)
        for r in rels_res:
            src_id = r._mapping["source_table_id"]
            tgt_id = r._mapping["target_table_id"]
            if src_id in directly_matched_ids:
                selected_table_ids.add(tgt_id)
            if tgt_id in directly_matched_ids:
                selected_table_ids.add(src_id)
                
        # Fallback: if no tables matched, include all business tables
        if not selected_table_ids:
            selected_table_ids = {t["table_id"] for t in business_tables}
            
        # 6. Build the formatted schema string
        schema_text = ""
        
        # Selected tables metadata map for quick lookup
        selected_tables_map = {t["table_id"]: t for t in business_tables if t["table_id"] in selected_table_ids}
        
        # Build Table & Column definitions
        for t_id, tbl in selected_tables_map.items():
            schema_text += f"\nTable: {tbl['schema_name']}.{tbl['table_name']}\nColumns:\n"
            
            is_direct = t_id in directly_matched_ids
            tbl_cols = columns_by_table.get(t_id, [])
            
            for col in tbl_cols:
                col_name = col["column_name"]
                col_type = col["data_type"]
                is_pk = col["is_primary_key"]
                is_fk = col["is_foreign_key"]
                
                # Column relevance heuristics
                is_pk_or_fk = is_pk or is_fk
                is_token_match = any(part in tokens for part in re.findall(r'[a-zA-Z0-9]+', col_name.lower()))
                is_common_desc = any(desc in col_name.lower() for desc in ["name", "title", "description", "code", "number", "type", "desc"])
                
                # Heuristic: include all columns for directly matched tables,
                # or only relevant keys/descriptions for neighbor tables.
                if is_direct or is_pk_or_fk or is_token_match or is_common_desc:
                    constraints = []
                    if is_pk:
                        constraints.append("PRIMARY KEY")
                    if is_fk:
                        constraints.append("FOREIGN KEY")
                    constraint_str = f" ({', '.join(constraints)})" if constraints else ""
                    schema_text += f"  - {col_name} ({col_type}){constraint_str}\n"
            schema_text += "\n"
            
        # 7. Add relevant relationships
        schema_text += "Relationships:\n"
        has_relationships = False
        
        # Resolve table names for relationships
        table_name_by_id = {t["table_id"]: f"{t['schema_name']}.{t['table_name']}" for t in business_tables}
        # Resolve column names
        column_name_by_id = {c._mapping["column_id"]: c._mapping["column_name"] for c in columns_res}
        
        for r in rels_res:
            src_id = r._mapping["source_table_id"]
            tgt_id = r._mapping["target_table_id"]
            
            # Show relationship only if both tables are selected
            if src_id in selected_table_ids and tgt_id in selected_table_ids:
                src_tbl = table_name_by_id.get(src_id)
                tgt_tbl = table_name_by_id.get(tgt_id)
                src_col = column_name_by_id.get(r._mapping["source_column_id"])
                tgt_col = column_name_by_id.get(r._mapping["target_column_id"])
                
                if src_tbl and tgt_tbl and src_col and tgt_col:
                    schema_text += f"  - {src_tbl}.{src_col} references {tgt_tbl}.{tgt_col}\n"
                    has_relationships = True
                    
        if not has_relationships:
            schema_text += "  - None\n"
            
        return schema_text
