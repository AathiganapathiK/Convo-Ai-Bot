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
        expanded_tables
    ):

        selected_tables = [
            table["table_name"]
            for table in expanded_tables
        ]
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

        table_metadata = MetadataResolver.load_column_metadata(
            connection_id,
            expanded_tables
        )

        # Load relationship metadata
        relationship_metadata = MetadataResolver.load_relationship_metadata(
            connection_id,
            expanded_tables
        )
                

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

            "tables": table_metadata,

            "relationships": relationship_metadata,

            "display_columns": display_columns,

            "hidden_keys": hidden_keys,

            "requested_keys": requested_keys,

            "required_tables": required_tables,

            "metadata_rules": metadata_rules

        }


    @staticmethod
    def load_table_metadata(
        connection_id,
        expanded_tables
    ):
        """
        Load metadata only for the tables selected by the semantic pipeline.
        """

        if not expanded_tables:
            return []

        table_names = [
            table["table_name"]
            for table in expanded_tables
        ]

        placeholders = ", ".join(
            f":table_{i}"
            for i in range(len(table_names))
        )

        query = f"""
        SELECT
            table_name,
            business_name,
            description
        FROM schema_tables
        WHERE
            connection_id = :connection_id
            AND table_name IN ({placeholders})
        """

        params = {
            "connection_id": connection_id
        }

        for i, table_name in enumerate(table_names):
            params[f"table_{i}"] = table_name

        with engine.connect() as conn:

            rows = conn.execute(
                text(query),
                params
            ).mappings().all()

        metadata_lookup = {
            row["table_name"]: dict(row)
            for row in rows
        }

        results = []

        for table in expanded_tables:

            metadata = metadata_lookup.get(
                table["table_name"],
                {}
            )

            results.append(
                {
                    "table_name": table["table_name"],
                    "business_name": metadata.get("business_name"),
                    "description": metadata.get("description"),
                    "score": table["score"],
                    "is_bridge": table["is_bridge"]
                }
            )

        return results


    @staticmethod
    def load_column_metadata(
        connection_id,
        expanded_tables
    ):
        """
        Load physical column metadata for the tables selected by
        the semantic pipeline.
        """

        if not expanded_tables:
            return []

        table_names = [
            table["table_name"]
            for table in expanded_tables
        ]

        placeholders = ", ".join(
            f":table_{i}"
            for i in range(len(table_names))
        )

        query = f"""
        SELECT
            st.table_name,

            sc.column_name,
            sc.data_type,
            sc.max_length,
            sc.numeric_precision,
            sc.numeric_scale,

            sc.is_nullable,
            sc.is_primary_key,
            sc.is_foreign_key,

            sc.column_description

        FROM schema_columns sc

        INNER JOIN schema_tables st
            ON st.table_id = sc.table_id

        WHERE
            st.connection_id = :connection_id
            AND st.table_name IN ({placeholders})

        ORDER BY
            st.table_name,
            sc.column_name
        """

        params = {
            "connection_id": connection_id
        }

        for i, table_name in enumerate(table_names):
            params[f"table_{i}"] = table_name

        with engine.connect() as conn:

            rows = conn.execute(
                text(query),
                params
            ).mappings().all()

        # -----------------------------------------
        # Group columns by table
        # -----------------------------------------
        columns_lookup = {}

        for row in rows:

            table_name = row["table_name"]

            if table_name not in columns_lookup:
                columns_lookup[table_name] = {
                    "columns": [],
                    "primary_keys": [],
                    "foreign_keys": []
                }

            column = {
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "max_length": row["max_length"],
                "numeric_precision": row["numeric_precision"],
                "numeric_scale": row["numeric_scale"],
                "is_nullable": row["is_nullable"],
                "is_primary_key": row["is_primary_key"],
                "is_foreign_key": row["is_foreign_key"],
                "description": row["column_description"]
            }

            columns_lookup[table_name]["columns"].append(column)

            if row["is_primary_key"]:
                columns_lookup[table_name]["primary_keys"].append(
                    row["column_name"]
                )

            if row["is_foreign_key"]:
                columns_lookup[table_name]["foreign_keys"].append(
                    {
                        "column_name": row["column_name"]
                    }
                )

        results = []

        for table in expanded_tables:

            metadata = columns_lookup.get(
                table["table_name"],
                {
                    "columns": [],
                    "primary_keys": [],
                    "foreign_keys": []
                }
            )

            results.append(
                {
                    "table_name": table["table_name"],
                    "score": table["score"],
                    "is_bridge": table.get("is_bridge", False),

                    "columns": metadata["columns"],
                    "primary_keys": metadata["primary_keys"],
                    "foreign_keys": metadata["foreign_keys"]
                }
            )

        return results



    @staticmethod
    def load_relationship_metadata(
        connection_id,
        expanded_tables
    ):
        """
        Load relationship metadata for the selected tables.
        """

        if not expanded_tables:
            return []

        table_names = [
            table["table_name"]
            for table in expanded_tables
        ]

        placeholders = ", ".join(
            f":table_{i}"
            for i in range(len(table_names))
        )

        query = f"""
        SELECT

            src_table.table_name AS source_table,
            src_col.column_name AS source_column,

            tgt_table.table_name AS target_table,
            tgt_col.column_name AS target_column,

            sr.relationship_type,
            sr.confidence_score,
            sr.is_confirmed

        FROM schema_relationships sr

        INNER JOIN schema_tables src_table
            ON src_table.table_id = sr.source_table_id

        INNER JOIN schema_columns src_col
            ON src_col.column_id = sr.source_column_id

        INNER JOIN schema_tables tgt_table
            ON tgt_table.table_id = sr.target_table_id

        INNER JOIN schema_columns tgt_col
            ON tgt_col.column_id = sr.target_column_id

        WHERE
            sr.connection_id = :connection_id

            AND src_table.table_name IN ({placeholders})

            AND tgt_table.table_name IN ({placeholders})

        ORDER BY
            src_table.table_name,
            tgt_table.table_name
        """

        params = {
            "connection_id": connection_id
        }

        for i, table_name in enumerate(table_names):
            params[f"table_{i}"] = table_name

        with engine.connect() as conn:

            rows = conn.execute(
                text(query),
                params
            ).mappings().all()

        relationships = []

        for row in rows:

            relationships.append({

                "source_table": row["source_table"],
                "source_column": row["source_column"],

                "target_table": row["target_table"],
                "target_column": row["target_column"],

                "relationship_type": row["relationship_type"],

                "confidence_score": row["confidence_score"],

                "is_confirmed": row["is_confirmed"]

            })

        return relationships