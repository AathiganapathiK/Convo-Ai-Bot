import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from database import engine

def discover_inventory():
    connection_id = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"

    with engine.connect() as conn:
        # 1. Database connection info
        conn_info = conn.execute(
            text("SELECT connection_id, connection_name, database_name FROM database_connections WHERE connection_id = :connection_id"),
            {"connection_id": connection_id}
        ).fetchone()

        conn_data = {
            "connection_id": conn_info[0] if conn_info else connection_id,
            "connection_name": conn_info[1] if conn_info else "Chatbot",
            "db_type": "sqlserver",
            "database_name": conn_info[2] if conn_info else "PBI"
        }

        # 2. Semantic Metrics
        metrics_rows = conn.execute(
            text("""
                SELECT metric_id, metric_name, business_name, description, table_name, column_name, aggregation_type, source
                FROM semantic_metrics
                WHERE connection_id = :connection_id
                ORDER BY business_name
            """),
            {"connection_id": connection_id}
        ).fetchall()

        metrics_list = []
        for r in metrics_rows:
            metrics_list.append({
                "metric_id": str(r[0]),
                "metric_name": r[1],
                "business_name": r[2],
                "description": r[3],
                "table_name": r[4],
                "column_name": r[5],
                "aggregation_type": r[6],
                "source": r[7]
            })

        # 3. Semantic Dimensions
        dimensions_rows = conn.execute(
            text("""
                SELECT dimension_id, dimension_name, business_name, description, table_name, column_name, semantic_category, synonyms, source
                FROM semantic_dimensions
                WHERE connection_id = :connection_id
                ORDER BY business_name
            """),
            {"connection_id": connection_id}
        ).fetchall()

        dimensions_list = []
        synonyms_map = {}
        for r in dimensions_rows:
            dim_id = str(r[0])
            syn_str = r[7] or ""
            syn_list = [s.strip() for s in syn_str.split(",") if s.strip()] if syn_str else []
            
            dim_obj = {
                "dimension_id": dim_id,
                "dimension_name": r[1],
                "business_name": r[2],
                "description": r[3],
                "table_name": r[4],
                "column_name": r[5],
                "semantic_category": r[6],
                "synonyms": syn_list,
                "source": r[8]
            }
            dimensions_list.append(dim_obj)
            if syn_list:
                synonyms_map[r[2]] = syn_list

        # 4. Dimension Value Index summary
        val_summary = conn.execute(
            text("""
                SELECT COUNT(*), COUNT(DISTINCT value)
                FROM dimension_value_index dvi
                JOIN semantic_dimensions sd ON dvi.semantic_dimension_id = sd.dimension_id
                WHERE sd.connection_id = :connection_id
            """),
            {"connection_id": connection_id}
        ).fetchone()

        total_values = val_summary[0] if val_summary else 0
        unique_values = val_summary[1] if val_summary else 0

        # Duplicate values across dimensions (Python aggregation to avoid SQL dialect issues)
        all_dvi_rows = conn.execute(
            text("""
                SELECT dvi.value, sd.business_name
                FROM dimension_value_index dvi
                JOIN semantic_dimensions sd ON dvi.semantic_dimension_id = sd.dimension_id
                WHERE sd.connection_id = :connection_id
            """),
            {"connection_id": connection_id}
        ).fetchall()

        value_to_dims = {}
        for val, bus_name in all_dvi_rows:
            if not val or not bus_name:
                continue
            v_norm = val.strip().upper()
            if v_norm not in value_to_dims:
                value_to_dims[v_norm] = set()
            value_to_dims[v_norm].add(bus_name)

        duplicates_list = []
        for val_norm, dim_set in value_to_dims.items():
            if len(dim_set) > 1:
                duplicates_list.append({
                    "value": val_norm,
                    "dimension_count": len(dim_set),
                    "dimensions": sorted(list(dim_set))
                })

        duplicates_list.sort(key=lambda x: (-x["dimension_count"], x["value"]))

        # 5. Schema Tables & Columns
        tables_rows = conn.execute(
            text("""
                SELECT st.table_name, COUNT(sc.column_id) as col_count
                FROM schema_tables st
                LEFT JOIN schema_columns sc ON st.table_id = sc.table_id
                WHERE st.connection_id = :connection_id
                GROUP BY st.table_name
                ORDER BY st.table_name
            """),
            {"connection_id": connection_id}
        ).fetchall()

        tables_list = [{"table_name": r[0], "column_count": r[1]} for r in tables_rows]

    inventory_data = {
        "datasource": conn_data,
        "summary": {
            "total_metrics": len(metrics_list),
            "total_dimensions": len(dimensions_list),
            "total_indexed_values": total_values,
            "unique_indexed_values": unique_values,
            "duplicate_value_count": len(duplicates_list),
            "table_count": len(tables_list)
        },
        "metrics": metrics_list,
        "dimensions": dimensions_list,
        "duplicate_values": duplicates_list,
        "synonyms_map": synonyms_map,
        "tables": tables_list
    }

    print(json.dumps(inventory_data, indent=2))
    
    with open("backend/test/discovery_output.json", "w") as f:
        json.dump(inventory_data, f, indent=2)

if __name__ == "__main__":
    discover_inventory()
