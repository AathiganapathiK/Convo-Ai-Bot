from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from database import engine
from services.database_connection_factory import DatabaseConnectionFactory
from security.rbac_service import require_permission

from admin.connection_schema import (
    CreateConnectionRequest
)

from services.connection_service import (
    ConnectionService
)

from admin.connection_schema import (
    TestConnectionRequest
)

from services.connection_test_service import (
    ConnectionTestService
)

from services.schema_sync_service import (
    SchemaSyncService
)

from services.relationship_discovery_service import (
    RelationshipDiscoveryService
)

from services.drift_detection_service import (
    DriftDetectionService
)

router = APIRouter(
    tags=["Data Sources"]
)

@router.get("/connections")
def get_connections(
    user=Depends(require_permission("admin:connections:manage"))
):

    return (
        ConnectionService.get_connections(
            user["company_id"]
        )
    )

@router.post("/connections")
def create_connection(
    request: CreateConnectionRequest,
    user=Depends(require_permission("admin:connections:manage"))
):

    ConnectionService.create_connection(
        user["company_id"],
        request
    )

    connection = ConnectionService.get_active_connection(
        user["company_id"]
    )

    if connection:

        SchemaSyncService.sync_schema(
            connection
        )

        RelationshipDiscoveryService.discover_relationships(
            company_id=user["company_id"],
            connection_id=connection["connection_id"]
        )

    return {
        "message":
        "Connection created and synchronized"
    }


@router.put(
    "/connections/{connection_id}/disable"
)
def disable_connection(
    connection_id: str,
    user=Depends(require_permission("admin:connections:manage"))
):

    ConnectionService.disable_connection(
        connection_id,
        user["company_id"]
    )

    return {
        "message":
        "Connection disabled"
    }

@router.put(
    "/connections/{connection_id}/enable"
)
def enable_connection(
    connection_id: str,
    user=Depends(require_permission("admin:connections:manage"))
):

    ConnectionService.enable_connection(
        connection_id,
        user["company_id"]
    )

    connection = ConnectionService.get_active_connection(
        user["company_id"]
    )

    SchemaSyncService.sync_schema(
        connection
    )

    relationship_result = (
        RelationshipDiscoveryService
        .discover_relationships(
            company_id=user["company_id"],
            connection_id=connection["connection_id"]
        )
    )

    DriftDetectionService.detect_drift(
        company_id=user["company_id"],
        connection_id=connection["connection_id"]
    )

    return {
    "message":
    "Connection enabled",

    "relationships_found":
        relationship_result[
            "relationships_found"
        ]

    }


@router.post(
    "/connections/test"
)
def test_connection(
    request: TestConnectionRequest,
    user=Depends(require_permission("admin:connections:manage"))
):

    return (
        ConnectionTestService
        .test_payload(
            request.dict()
        )
    )

@router.post(
    "/connections/{connection_id}/sync"
)
def sync_connection_schema(
    connection_id: str,
    user=Depends(require_permission("admin:connections:manage"))
):
    connection = ConnectionService.get_active_connection(user["company_id"])
    if not connection:
        return {
            "success": False,
            "message":
                "No active database connection found"
        }

    return (
        SchemaSyncService
        .sync_schema(
            connection
        )
    )

@router.post(
    "/connections/{connection_id}/discover-relationships"
)
def discover_relationships(
    connection_id: str,
    current_user=Depends(require_permission("admin:connections:manage"))
):
    connection = ConnectionService.get_active_connection(current_user["company_id"])
    if not connection:
        return {
            "success": False,
            "message":
                "No active database connection found"
        }

    return RelationshipDiscoveryService.discover_relationships(
        company_id=current_user["company_id"],
        connection_id=connection["connection_id"]
    )   


@router.post(
    "/connections/{connection_id}/detect-drift"
)
def detect_drift(
    connection_id: str,
    current_user=Depends(require_permission("admin:connections:manage"))
):
    connection = ConnectionService.get_active_connection(current_user["company_id"])
    if not connection:
        return {
            "success": False,
            "message":
                "No active database connection found"
        }

    return DriftDetectionService.detect_drift(
        company_id=current_user["company_id"],
        connection_id=connection["connection_id"]
    )

@router.get("/schema/active")
def get_active_schema(
    user=Depends(require_permission("chat:history:read"))
):
    """
    Returns active connection information and the list of synchronized tables.
    """
    company_id = user["company_id"]
    active_conn = ConnectionService.get_active_connection(company_id)
    if not active_conn:
        return {
            "active_connection": None,
            "tables": []
        }
    
    # Query tables
    query = """
    SELECT table_id, schema_name, table_name, table_type, last_synced_at
    FROM schema_tables
    WHERE connection_id = :connection_id
      AND company_id = :company_id
    ORDER BY schema_name, table_name
    """
    with engine.connect() as conn:
        result = conn.execute(
            text(query),
            {
                "connection_id": active_conn["connection_id"],
                "company_id": company_id
            }
        ).fetchall()
        
    tables = [dict(row._mapping) for row in result]
    return {
        "active_connection": {
            "connection_id": active_conn["connection_id"],
            "connection_name": active_conn["connection_name"],
            "database_name": active_conn["database_name"]
        },
        "tables": tables
    }


@router.get("/schema/tables/{table_id}")
def get_table_schema_details(
    table_id: str,
    user=Depends(require_permission("chat:history:read"))
):
    """
    Returns column details, relationships, and sample data for a selected table.
    """
    company_id = user["company_id"]
    active_conn = ConnectionService.get_active_connection(company_id)
    if not active_conn:
        raise HTTPException(status_code=400, detail="No active database connection configured.")

    # Get table info
    table_query = """
    SELECT schema_name, table_name, table_type, last_synced_at
    FROM schema_tables
    WHERE table_id = :table_id AND company_id = :company_id
    """
    with engine.connect() as conn:
        table_row = conn.execute(
            text(table_query),
            {"table_id": table_id, "company_id": company_id}
        ).fetchone()
        
    if not table_row:
        raise HTTPException(status_code=404, detail="Table not found.")
        
    schema_name = table_row._mapping["schema_name"]
    table_name = table_row._mapping["table_name"]
    
    # Query columns
    cols_query = """
    SELECT column_id, column_name, data_type, max_length, is_nullable, is_primary_key, is_foreign_key
    FROM schema_columns
    WHERE table_id = :table_id AND company_id = :company_id
    ORDER BY column_name
    """
    with engine.connect() as conn:
        cols_result = conn.execute(
            text(cols_query),
            {"table_id": table_id, "company_id": company_id}
        ).fetchall()
        
    columns = []
    for idx, row in enumerate(cols_result):
        is_pk = bool(row._mapping["is_primary_key"])
        is_fk = bool(row._mapping["is_foreign_key"])
        
        constraint = "NONE"
        if is_pk and is_fk:
            constraint = "PRIMARY KEY, FOREIGN KEY"
        elif is_pk:
            constraint = "PRIMARY KEY"
        elif is_fk:
            constraint = "FOREIGN KEY"
            
        columns.append({
            "key": row._mapping["column_id"] or str(idx),
            "name": row._mapping["column_name"],
            "type": row._mapping["data_type"],
            "constraint": constraint,
            "nullable": "YES" if row._mapping["is_nullable"] else "NO",
            "desc": f"Primary key column for {table_name}" if is_pk else (f"Foreign key referencing related table" if is_fk else f"Attribute of type {row._mapping['data_type']}")
        })
        
    # Query relationships
    rel_query = """
    SELECT
        sr.relationship_id,
        st_src.table_name AS source_table,
        sc_src.column_name AS source_column,
        st_tgt.table_name AS target_table,
        sc_tgt.column_name AS target_column
    FROM schema_relationships sr
    INNER JOIN schema_tables st_src ON sr.source_table_id = st_src.table_id
    INNER JOIN schema_columns sc_src ON sr.source_column_id = sc_src.column_id
    INNER JOIN schema_tables st_tgt ON sr.target_table_id = st_tgt.table_id
    INNER JOIN schema_columns sc_tgt ON sr.target_column_id = sc_tgt.column_id
    WHERE (sr.source_table_id = :table_id OR sr.target_table_id = :table_id)
      AND sr.company_id = :company_id
    """
    with engine.connect() as conn:
        rel_result = conn.execute(
            text(rel_query),
            {"table_id": table_id, "company_id": company_id}
        ).fetchall()
    relationships = [dict(row._mapping) for row in rel_result]
    
    # Query row count from source database
    row_count = 0
    db_type = active_conn.get("database_type", "").lower()
    table_esc = f"[{schema_name}].[{table_name}]" if db_type == "sqlserver" else f"{schema_name}.{table_name}"
    
    try:
        source_engine = DatabaseConnectionFactory.create_engine_for_connection(active_conn)
        with source_engine.connect() as source_conn:
            count_res = source_conn.execute(text(f"SELECT COUNT(*) AS total FROM {table_esc}")).fetchone()
            row_count = count_res._mapping["total"] if count_res else 0
    except Exception as e:
        print(f"Error getting row count: {e}")
        
    # Query sample data (top 5 rows)
    sample_data = []
    try:
        source_engine = DatabaseConnectionFactory.create_engine_for_connection(active_conn)
        limit_sql = f"SELECT TOP 5 * FROM {table_esc}" if db_type == "sqlserver" else f"SELECT * FROM {table_esc} LIMIT 5"
        with source_engine.connect() as source_conn:
            sample_res = source_conn.execute(text(limit_sql)).fetchall()
            sample_data = [dict(row._mapping) for row in sample_res]
    except Exception as e:
        print(f"Error getting sample data: {e}")
        
    return {
        "table_id": table_id,
        "name": table_name,
        "schema": schema_name,
        "description": f"Metadata catalog representation of table '{schema_name}.{table_name}'.",
        "rowCount": row_count,
        "lastDiscovered": table_row._mapping["last_synced_at"].strftime("%Y-%m-%d %H:%M") if table_row._mapping["last_synced_at"] else "N/A",
        "columns": columns,
        "relationships": relationships,
        "sampleData": sample_data
    }