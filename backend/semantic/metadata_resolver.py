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
        
        # 2. Load all relationships for finding related tables and keys
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

        # Helper to find related key
        def find_related_key(T: str, C: str, R_T: str):
            for rel in relationships:
                left_table, left_column, right_table, right_column = rel[0], rel[1], rel[2], rel[3]
                if left_table.lower() == T.lower() and left_column.lower() == C.lower() and right_table.lower() == R_T.lower():
                    return right_column
                if right_table.lower() == T.lower() and right_column.lower() == C.lower() and left_table.lower() == R_T.lower():
                    return left_column
            return None

        # Set of selected tables (lowercased for matching)
        sel_tables_lower = {t.lower() for t in selected_tables} if selected_tables else set()

        # Iterate over technical columns that belong to the selected tables
        for tech in technical_columns:
            t_name = tech["table_name"]
            c_name = tech["column_name"]
            disp_t = tech.get("display_table")
            disp_c = tech.get("display_column")
            
            if selected_tables is not None and t_name.lower() not in sel_tables_lower:
                continue
                
            stem, suffix = get_column_stem_and_suffix(c_name)
            is_explicit = is_key_explicitly_requested(question, c_name, stem)
            
            if disp_t and disp_c:
                dest_key = find_related_key(t_name, c_name, disp_t)
                qualified_key = f"{t_name}.{c_name}"
                qualified_desc = f"{disp_t}.{disp_c}"
                
                # Check if this is not a join key (same table mapping)
                is_join_key = (disp_t.lower() != t_name.lower() and dest_key is not None)
                
                if is_explicit:
                    if qualified_key not in requested_keys:
                        requested_keys.append(qualified_key)
                    if qualified_desc not in display_columns:
                        display_columns.append(qualified_desc)
                    if disp_t.lower() != t_name.lower() and disp_t not in required_tables:
                        required_tables.append(disp_t)
                        
                    if is_join_key:
                        metadata_rules.append(
                            f"Keep {t_name}.{c_name} because user explicitly requested it. "
                            f"Include both {t_name}.{c_name} and {disp_t}.{disp_c} in SELECT. "
                            f"Continue using {t_name}.{c_name} = {disp_t}.{dest_key} inside JOIN."
                        )
                    else:
                        metadata_rules.append(
                            f"Keep {t_name}.{c_name} because user explicitly requested it. "
                            f"Include both {t_name}.{c_name} and {disp_t}.{disp_c} in SELECT."
                        )
                else:
                    if qualified_key not in hidden_keys:
                        hidden_keys.append(qualified_key)
                    if qualified_desc not in display_columns:
                        display_columns.append(qualified_desc)
                    if disp_t.lower() != t_name.lower() and disp_t not in required_tables:
                        required_tables.append(disp_t)
                        
                    if is_join_key:
                        metadata_rules.append(
                            f"Use {disp_t}.{disp_c} instead of {t_name}.{c_name} for SELECT, GROUP BY, ORDER BY. "
                            f"Continue using {t_name}.{c_name} = {disp_t}.{dest_key} inside JOIN."
                        )
                    else:
                        metadata_rules.append(
                            f"Use {disp_t}.{disp_c} instead of {t_name}.{c_name} for SELECT, GROUP BY, ORDER BY"
                        )
            else:
                qualified_key = f"{t_name}.{c_name}"
                if is_explicit:
                    if qualified_key not in requested_keys:
                        requested_keys.append(qualified_key)
                    metadata_rules.append(f"Keep {t_name}.{c_name} because user explicitly requested it")
                else:
                    if qualified_key not in hidden_keys:
                        hidden_keys.append(qualified_key)
                    metadata_rules.append(f"Hide {t_name}.{c_name} from outputs")
                    
        return {
            "display_columns": display_columns,
            "hidden_keys": hidden_keys,
            "requested_keys": requested_keys,
            "required_tables": required_tables,
            "metadata_rules": metadata_rules
        }
