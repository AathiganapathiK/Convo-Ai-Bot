import logging
from typing import Optional
from sqlglot import parse_one, exp
from database import engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

class DivisionRLSEngine:
    @staticmethod
    def get_division_tables(connection_id: str) -> dict[str, str]:
        """
        Retrieves a mapping of lowercase table names to their division column name
        (either 'division' or 'division_code') for the active datasource connection.
        """
        query = """
        SELECT LOWER(st.table_name) AS table_name, sc.column_name
        FROM schema_tables st
        INNER JOIN schema_columns sc ON st.table_id = sc.table_id
        WHERE st.connection_id = :connection_id
          AND LOWER(sc.column_name) IN ('division', 'division_code')
        """
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(query), {"connection_id": connection_id}).fetchall()
                return {row.table_name: row.column_name for row in rows}
        except Exception as e:
            logger.error(f"Error fetching division tables for connection {connection_id}: {e}")
            return {}

    @classmethod
    def apply_division_rls(cls, sql_query: str, division_code: Optional[str], connection_id: str) -> str:
        """
        Injects RLS division subqueries on base tables if the datasource
        contains a division column and the user is division-restricted.
        This preserves correct semantics for all outer joins, applies, unions, and CTEs.
        """
        if not division_code:
            logger.info("Division RLS: No division code provided, bypassing filter.")
            return sql_query

        # Capability Check / Datasource Scoping
        division_tables = cls.get_division_tables(connection_id)
        if not division_tables:
            logger.info(f"Division RLS: Datasource {connection_id} has no division tables, bypassing.")
            return sql_query

        try:
            ast = parse_one(sql_query, dialect="tsql")
            modified = False

            # 1. Traverse and replace exp.Table nodes (covering FROM, JOIN, CTEs, standard subqueries)
            for table in list(ast.find_all(exp.Table)):
                tbl_name = table.name.lower()
                if tbl_name in division_tables:
                    col_name = division_tables[tbl_name]
                    
                    # Copy the original table node and clear its alias
                    table_copy = table.copy()
                    table_copy.set("alias", None)
                    
                    # Build the RLS subquery
                    cond = exp.EQ(
                        this=exp.column(col_name, table=table.name),
                        expression=exp.Literal.string(division_code)
                    )
                    subquery = exp.select("*").from_(table_copy).where(cond)
                    
                    # Resolve alias: use original alias if exists, else fallback to table name (required for T-SQL subqueries)
                    original_alias = table.args.get("alias")
                    if original_alias:
                        alias_node = original_alias
                    else:
                        alias_node = exp.TableAlias(this=exp.to_identifier(table.name))
                    
                    new_node = exp.Subquery(this=subquery, alias=alias_node)
                    table.replace(new_node)
                    modified = True

            # 2. Traverse and replace exp.Lateral nodes representing direct table identifiers in CROSS/OUTER APPLY
            for lateral in list(ast.find_all(exp.Lateral)):
                if isinstance(lateral.this, exp.Identifier):
                    tbl_name = lateral.this.name.lower()
                    if tbl_name in division_tables:
                        col_name = division_tables[tbl_name]
                        
                        # Build the RLS subquery
                        subquery = exp.select("*").from_(
                            exp.Table(this=exp.to_identifier(tbl_name))
                        ).where(
                            exp.EQ(
                                this=exp.column(col_name, table=tbl_name),
                                expression=exp.Literal.string(division_code)
                            )
                        )
                        wrapped = exp.Paren(this=subquery)
                        lateral.set("this", wrapped)
                        modified = True

            if modified:
                modified_sql = ast.sql(dialect="tsql")
                logger.info(f"Division RLS applied to query: filter={division_code}")
                return modified_sql
            
            return sql_query
        except Exception as e:
            logger.error(f"Error parsing or modifying SQL AST for Division RLS: {e}")
            return sql_query
