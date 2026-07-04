import os
from sqlalchemy import text
from database import engine
from dotenv import load_dotenv

load_dotenv()

# Tables exposed to the AI SQL generator.
# Configurable via ALLOWED_TABLES env var (comma-separated: "dbo.Sales,dbo.Products")
# Defaults to AdventureWorks business tables.
_env_tables = os.getenv("ALLOWED_TABLES", "dbo.Sales,dbo.Products,dbo.Region,dbo.Reseller,dbo.Salesperson,dbo.Targets,dbo.Users,dbo.SalespersonRegion")
ALLOWED_TABLES = {t.strip() for t in _env_tables.split(",") if t.strip()}


def get_database_schema(company_id: str = None) -> str:
    """
    Discovers the schema from metadata tables for the company's active database connection,
    or falls back to the live database metadata if company_id is None.
    """
    if company_id:
        # Resolve the active connection for this company
        from services.connection_service import ConnectionService
        active_conn = ConnectionService.get_active_connection(company_id)
        if not active_conn:
            return "No active database connection configured."
            
        connection_id = active_conn["connection_id"]
        
        # Query schema_tables and schema_columns
        query = """
        SELECT
            st.schema_name,
            st.table_name,
            sc.column_name,
            sc.data_type
        FROM schema_tables st
        INNER JOIN schema_columns sc ON st.table_id = sc.table_id
        WHERE st.connection_id = :connection_id
          AND st.company_id = :company_id
        ORDER BY
            st.table_name,
            sc.column_name
        """
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text(query),
                    {
                        "connection_id": connection_id,
                        "company_id": company_id
                    }
                )
                rows = result.fetchall()
            
            tables = {}
            for row in rows:
                table_key = f"{row.schema_name}.{row.table_name}"
                if table_key not in ALLOWED_TABLES:
                    continue
                if table_key not in tables:
                    tables[table_key] = []
                tables[table_key].append(f"{row.column_name} ({row.data_type})")
                
            if not tables:
                return "No synchronized schema found in ALLOWED_TABLES for the active connection. Run schema sync."
                
            schema_text = ""
            for table, columns in tables.items():
                schema_text += f"\nTable: {table}\nColumns:\n"
                for column in columns:
                    schema_text += f"  - {column}\n"
                schema_text += "\n"
            return schema_text
        except Exception as e:
            return f"Error loading schema metadata: {str(e)}"

    from services.connection_service import ConnectionService
    active_conn = ConnectionService.get_active_connection_global()
    if not active_conn:
        return "No active database connection configured."
        
    connection_id = active_conn["connection_id"]
    
    query = """
    SELECT
        st.schema_name,
        st.table_name,
        sc.column_name,
        sc.data_type
    FROM schema_tables st
    INNER JOIN schema_columns sc ON st.table_id = sc.table_id
    WHERE st.connection_id = :connection_id
    ORDER BY
        st.table_name,
        sc.column_name
    """

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(query),
                {"connection_id": connection_id}
            )
            rows = result.fetchall()

        tables = {}
        for row in rows:
            table_key = f"{row.schema_name}.{row.table_name}"
            if table_key not in ALLOWED_TABLES:
                continue
            if table_key not in tables:
                tables[table_key] = []
            tables[table_key].append(f"{row.column_name} ({row.data_type})")

        if not tables:
            return "No synchronized schema found in ALLOWED_TABLES for the active connection. Run schema sync."

        schema_text = ""
        for table, columns in tables.items():
            schema_text += f"\nTable: {table}\nColumns:\n"
            for column in columns:
                schema_text += f"  - {column}\n"
            schema_text += "\n"

        return schema_text
    except Exception as e:
        return f"Error loading schema metadata: {str(e)}"


try:
    print(get_database_schema())
except Exception:
    pass

"""

To change tables exposed to AI:
1. Edit ALLOWED_TABLES in backend/.env

Example:
ALLOWED_TABLES=dbo.Sales,dbo.Products,dbo.Region

2. Reload server

Allowed tables will automatically update without code changes.

"""