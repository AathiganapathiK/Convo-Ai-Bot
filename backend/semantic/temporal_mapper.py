class TemporalMapper:
    @staticmethod
    def get_sql_expression(dialect: str, semantic_category: str, column_name: str) -> str:
        """
        Converts a semantic temporal dimension category into a dialect-specific SQL expression.
        """
        dialect = (dialect or "mssql").lower()
        if dialect in ("tsql", "sqlserver", "mssql", "microsoft"):
            dialect = "mssql"
        elif dialect in ("postgres", "postgresql", "pg"):
            dialect = "postgresql"
        elif dialect in ("mysql", "mariadb"):
            dialect = "mysql"
        
        category = (semantic_category or "").upper()
        
        mappings = {
            "mssql": {
                "TIME_YEAR": f"YEAR({column_name})",
                "TIME_QUARTER": f"DATEPART(quarter, {column_name})",
                "TIME_MONTH": f"MONTH({column_name})",
                "TIME_WEEK": f"DATEPART(week, {column_name})",
                "TIME_DAY": f"DAY({column_name})",
                "TIME_DATE": f"CAST({column_name} AS DATE)",
            },
            "postgresql": {
                "TIME_YEAR": f"EXTRACT(YEAR FROM {column_name})",
                "TIME_QUARTER": f"EXTRACT(QUARTER FROM {column_name})",
                "TIME_MONTH": f"EXTRACT(MONTH FROM {column_name})",
                "TIME_WEEK": f"EXTRACT(WEEK FROM {column_name})",
                "TIME_DAY": f"EXTRACT(DAY FROM {column_name})",
                "TIME_DATE": f"CAST({column_name} AS DATE)",
            },
            "mysql": {
                "TIME_YEAR": f"YEAR({column_name})",
                "TIME_QUARTER": f"QUARTER({column_name})",
                "TIME_MONTH": f"MONTH({column_name})",
                "TIME_WEEK": f"WEEK({column_name})",
                "TIME_DAY": f"DAY({column_name})",
                "TIME_DATE": f"DATE({column_name})",
            }
        }
        
        dialect_map = mappings.get(dialect, mappings["mssql"])
        return dialect_map.get(category, column_name)
