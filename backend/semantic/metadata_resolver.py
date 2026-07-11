import re
from sqlalchemy import text
from database import engine
from services.column_display_service import ColumnDisplayService
from semantic.relationship_service import SemanticRelationshipService

class MetadataResolver:

    @staticmethod
    def resolve(
        question,
        connection_id,
        semantic_result,
        selected_tables
    ):
        # 1. Fetch column display config for the active connection where is_visible = 0
        configs = ColumnDisplayService.load_display_config(connection_id)
        technical_columns = [
            c for c in configs 
            if not c.get("is_visible")
        ]
        
        # 2. Load all tables and columns from the database connection
        all_tables_query = """
        SELECT
            st.table_name,
            sc.column_name
        FROM schema_columns sc
        JOIN schema_tables st ON sc.table_id = st.table_id
        WHERE st.connection_id = :connection_id
        """
        all_tables = {}
        with engine.connect() as conn:
            rows = conn.execute(text(all_tables_query), {"connection_id": connection_id}).fetchall()
            for r_table, r_col in rows:
                if r_table not in all_tables:
                    all_tables[r_table] = []
                all_tables[r_table].append(r_col)
                
        # 3. Load all relationships for finding related tables
        relationships = SemanticRelationshipService.build_relationships(connection_id)
        
        display_columns = []
        hidden_keys = []
        requested_keys = []
        required_tables = []
        metadata_rules = []
        
        # Helper to get stem and suffix
        def get_column_stem_and_suffix(col_name: str):
            col_lower = col_name.lower()
            suffixes = [
                "key", "id", "code", "no", "num", "seq", "pk", "fk", 
                "number", "identifier", "reference", "ref"
            ]
            suffixes.sort(key=len, reverse=True)
            for suffix in suffixes:
                if col_lower.endswith(suffix):
                    stem_part = col_name[:-len(suffix)]
                    stem_part = stem_part.rstrip("_")
                    return stem_part, suffix
            return col_name, None

        # Helper to check if key is explicitly requested
        def is_key_explicitly_requested(q: str, col_name: str, stem: str) -> bool:
            if not stem:
                return False
            q_clean = " ".join(q.lower().split())
            stem_clean = stem.lower()
            
            # Check exact column name or column name with underscore replaced
            col_clean = col_name.lower()
            col_clean_no_underscore = col_clean.replace("_", "")
            q_words = re.findall(r"\b\w+\b", q_clean)
            if col_clean in q_words or col_clean_no_underscore in q_words:
                return True
                
            # Check stem + key term patterns
            terms = ["key", "id", "code", "identifier", "number", "no", "reference"]
            plural_terms = [t + "s" for t in terms]
            all_terms = terms + plural_terms
            
            for term in all_terms:
                pattern = rf"\b{re.escape(stem_clean)}\s+{re.escape(term)}\b"
                if re.search(pattern, q_clean):
                    return True
            return False

        # Helper to search for descriptive column in a table T with stem S
        def search_table_for_desc_col(T: str, S: str, is_related: bool) -> str:
            cols = []
            normalized_T = T
            for t_name, t_cols in all_tables.items():
                if t_name.lower() == T.lower():
                    normalized_T = t_name
                    cols = t_cols
                    break
            if not cols:
                return None
                
            # Heuristic 1: Same stem
            for col in cols:
                if col.lower() == S.lower():
                    return f"{normalized_T}.{col}"
                    
            # Heuristic 2: Stem + Name
            for col in cols:
                if col.lower() in (S.lower() + "name", S.lower() + "_name"):
                    return f"{normalized_T}.{col}"
                    
            # Heuristics 2b and 3 are only allowed if is_related is True
            if is_related:
                # Heuristic 2b: Table Name as stem, or Table Name + Name
                t_stem = normalized_T.lower()
                if t_stem.endswith("s"):
                    t_stem = t_stem[:-1]
                for col in cols:
                    if col.lower() == normalized_T.lower() or col.lower() == t_stem:
                        return f"{normalized_T}.{col}"
                    if col.lower() in (normalized_T.lower() + "name", normalized_T.lower() + "_name", t_stem + "name", t_stem + "_name"):
                        return f"{normalized_T}.{col}"
                        
                # Heuristic 3: Generic (Name, Description, Title, Desc)
                for gen in ["name", "description", "title", "desc"]:
                    for col in cols:
                        if col.lower() == gen:
                            return f"{normalized_T}.{col}"
            return None

        # Helper to find related table
        def find_related_table(T: str, C: str):
            for rel in relationships:
                left_table, left_column, right_table, right_column = rel[0], rel[1], rel[2], rel[3]
                if left_table.lower() == T.lower() and left_column.lower() == C.lower():
                    return right_table
                if right_table.lower() == T.lower() and right_column.lower() == C.lower():
                    return left_table
            return None

        # Set of selected tables (lowercased for matching)
        sel_tables_lower = {t.lower() for t in selected_tables} if selected_tables else set()

        # Iterate over technical columns that belong to the selected tables
        for tech in technical_columns:
            t_name = tech["table_name"]
            c_name = tech["column_name"]
            
            if selected_tables and t_name.lower() not in sel_tables_lower:
                continue
                
            stem, suffix = get_column_stem_and_suffix(c_name)
            
            # Check if user explicitly requested this key
            is_explicit = is_key_explicitly_requested(question, c_name, stem)
            
            # Check if source table name matches the stem
            source_matches_stem = (t_name.lower() == stem.lower() or t_name.lower().rstrip("s") == stem.lower())
            
            # Find descriptive column
            desc_col = search_table_for_desc_col(t_name, stem, is_related=source_matches_stem)
            if not desc_col:
                # Try related table
                related_t = find_related_table(t_name, c_name)
                if related_t:
                    desc_col = search_table_for_desc_col(related_t, stem, is_related=True)
            
            if is_explicit:
                if c_name not in requested_keys:
                    requested_keys.append(c_name)
                metadata_rules.append(f"Keep {c_name} because user explicitly requested it")
                
                # Still add the descriptive column if found
                if desc_col:
                    if desc_col not in display_columns:
                        display_columns.append(desc_col)
                    dt_name = desc_col.split(".")[0]
                    # Find correct case for table name
                    for t_orig in all_tables:
                        if t_orig.lower() == dt_name.lower():
                            dt_name = t_orig
                            break
                    if dt_name.lower() != t_name.lower() and dt_name not in required_tables:
                        required_tables.append(dt_name)
            else:
                if c_name not in hidden_keys:
                    hidden_keys.append(c_name)
                
                if desc_col:
                    if desc_col not in display_columns:
                        display_columns.append(desc_col)
                    dt_name = desc_col.split(".")[0]
                    # Find correct case for table name
                    for t_orig in all_tables:
                        if t_orig.lower() == dt_name.lower():
                            dt_name = t_orig
                            break
                    if dt_name.lower() != t_name.lower() and dt_name not in required_tables:
                        required_tables.append(dt_name)
                    metadata_rules.append(f"Use {desc_col} instead of {t_name}.{c_name}")
                else:
                    metadata_rules.append(f"Hide {t_name}.{c_name} from outputs")
                    
        return {
            "display_columns": display_columns,
            "hidden_keys": hidden_keys,
            "requested_keys": requested_keys,
            "required_tables": required_tables,
            "metadata_rules": metadata_rules
        }
