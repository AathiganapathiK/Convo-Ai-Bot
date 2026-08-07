import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import uuid
from sqlalchemy import create_engine, text

# Create the test engine first
test_engine = create_engine("sqlite:///:memory:")

from sqlalchemy import event
import datetime
@event.listens_for(test_engine, "connect")
def register_sqlite_functions(dbapi_connection, connection_record):
    dbapi_connection.create_function("GETDATE", 0, lambda: datetime.datetime.now().isoformat())

from semantic.discovery_service import SemanticDiscoveryService
from services.relationship_discovery_service import RelationshipDiscoveryService
from semantic.dimension_value_index_builder import DimensionValueIndexBuilder
from semantic.semantic_service import SemanticService

class TestSemanticMetadataPersistence(unittest.TestCase):
    def setUp(self):
        # Reset the database schema before each test
        with test_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS schema_tables"))
            conn.execute(text("DROP TABLE IF EXISTS schema_columns"))
            conn.execute(text("DROP TABLE IF EXISTS semantic_dimensions"))
            conn.execute(text("DROP TABLE IF EXISTS semantic_metrics"))
            conn.execute(text("DROP TABLE IF EXISTS schema_relationships"))
            conn.execute(text("DROP TABLE IF EXISTS dimension_value_index"))
            
            conn.execute(text("""
                CREATE TABLE schema_tables (
                    table_id VARCHAR(50) PRIMARY KEY,
                    connection_id VARCHAR(50),
                    schema_name VARCHAR(100),
                    table_name VARCHAR(100)
                )
            """))
            conn.execute(text("""
                CREATE TABLE schema_columns (
                    column_id VARCHAR(50) PRIMARY KEY,
                    table_id VARCHAR(50),
                    column_name VARCHAR(100),
                    data_type VARCHAR(50),
                    is_primary_key INTEGER DEFAULT 0,
                    is_foreign_key INTEGER DEFAULT 0
                )
            """))
            conn.execute(text("""
                CREATE TABLE semantic_dimensions (
                    dimension_id VARCHAR(50) PRIMARY KEY,
                    connection_id VARCHAR(50),
                    dimension_name VARCHAR(100),
                    business_name VARCHAR(100),
                    description VARCHAR(255),
                    table_name VARCHAR(100),
                    column_name VARCHAR(100),
                    semantic_category VARCHAR(50),
                    source VARCHAR(20),
                    synonyms VARCHAR(255),
                    is_active INTEGER DEFAULT 1,
                    created_by VARCHAR(50),
                    updated_by VARCHAR(50),
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE semantic_metrics (
                    metric_id VARCHAR(50) PRIMARY KEY,
                    connection_id VARCHAR(50),
                    metric_name VARCHAR(100),
                    business_name VARCHAR(100),
                    description VARCHAR(255),
                    table_name VARCHAR(100),
                    column_name VARCHAR(100),
                    aggregation_type VARCHAR(50),
                    source VARCHAR(20),
                    created_by VARCHAR(50),
                    updated_by VARCHAR(50),
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE schema_relationships (
                    relationship_id VARCHAR(50) PRIMARY KEY,
                    company_id VARCHAR(50),
                    connection_id VARCHAR(50),
                    source_table_id VARCHAR(50),
                    source_column_id VARCHAR(50),
                    target_table_id VARCHAR(50),
                    target_column_id VARCHAR(50),
                    relationship_type VARCHAR(50),
                    confidence_score REAL,
                    is_confirmed INTEGER DEFAULT 0,
                    discovered_by VARCHAR(50)
                )
            """))
            conn.execute(text("""
                CREATE TABLE dimension_value_index (
                    connection_id VARCHAR(50),
                    semantic_dimension_id VARCHAR(50),
                    value VARCHAR(255),
                    normalized_value VARCHAR(255)
                )
            """))

    @patch("semantic.discovery_service.engine", test_engine)
    @patch("semantic.dimension_value_index_builder.engine", test_engine)
    @patch("services.connection_service.ConnectionService.get_connection")
    @patch("services.database_connection_factory.DatabaseConnectionFactory.create_engine_for_connection")
    def test_semantic_dimensions_preserves_customizations(self, mock_create_engine, mock_get_connection):
        connection_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())

        mock_get_connection.return_value = {"connection_id": connection_id, "company_id": company_id}

        # Setup mock source engine for dimension value fetching
        mock_source_conn = MagicMock()
        
        # Mock responses for _validate_dimension_mapping and _fetch_distinct_values
        def execute_side_effect(sql_text, *args, **kwargs):
            sql_str = str(sql_text)
            mock_res = MagicMock()
            if "INFORMATION_SCHEMA.COLUMNS" in sql_str:
                mock_res.fetchone.return_value = ("Country",)
            elif "SELECT DISTINCT" in sql_str:
                mock_res.fetchall.return_value = [("USA",), ("Canada",)]
            else:
                mock_res.fetchall.return_value = []
                mock_res.fetchone.return_value = None
            return mock_res
            
        mock_source_conn.execute.side_effect = execute_side_effect
        mock_source_engine = MagicMock()
        mock_source_engine.dialect.name = "mssql"
        mock_source_engine.connect.return_value.__enter__.return_value = mock_source_conn
        mock_create_engine.return_value = mock_source_engine

        # Populate tables and columns
        with test_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO schema_tables (table_id, connection_id, schema_name, table_name)
                VALUES ('t1', :conn_id, 'dbo', 'Customers')
            """), {"conn_id": connection_id})
            
            conn.execute(text("""
                INSERT INTO schema_columns (column_id, table_id, column_name, data_type)
                VALUES ('c1', 't1', 'Country', 'varchar')
            """))

        # Run discovery the first time
        SemanticDiscoveryService.discover(connection_id)

        # Verify it was inserted as AUTO
        with test_engine.connect() as conn:
            dim = conn.execute(text("SELECT * FROM semantic_dimensions WHERE connection_id = :conn_id"), {"conn_id": connection_id}).fetchone()
            self.assertIsNotNone(dim)
            self.assertEqual(dim.source, "AUTO")
            self.assertIsNone(dim.synonyms)
            self.assertEqual(dim.semantic_category, "Geography")

        # Now, simulate a manual user customization (adding synonyms and changing semantic category)
        with test_engine.begin() as conn:
            conn.execute(text("""
                UPDATE semantic_dimensions
                SET synonyms = 'nation,region',
                    semantic_category = 'LOCATION_COUNTRY'
                WHERE connection_id = :conn_id
            """), {"conn_id": connection_id})

        # Run discovery a second time
        SemanticDiscoveryService.discover(connection_id)

        # Verify the manual changes were NOT overwritten
        with test_engine.connect() as conn:
            dim = conn.execute(text("SELECT * FROM semantic_dimensions WHERE connection_id = :conn_id"), {"conn_id": connection_id}).fetchone()
            self.assertIsNotNone(dim)
            self.assertEqual(dim.synonyms, "nation,region")
            self.assertEqual(dim.semantic_category, "LOCATION_COUNTRY")
            self.assertEqual(dim.source, "AUTO")

    @patch("services.relationship_discovery_service.engine", test_engine)
    @patch("services.connection_service.ConnectionService.get_connection")
    @patch("services.database_connection_factory.DatabaseConnectionFactory.create_engine_for_connection")
    def test_relationship_discovery_preserves_user_joins_and_prevents_dups(self, mock_create_engine, mock_get_connection):
        connection_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())

        mock_get_connection.return_value = {"connection_id": connection_id, "company_id": company_id}

        # Mock the source database responses
        mock_fk_row = MagicMock()
        mock_fk_row.foreign_key_name = "FK_Sales_Customers"
        mock_fk_row.source_schema = "dbo"
        mock_fk_row.source_table = "Sales"
        mock_fk_row.source_column = "CustomerKey"
        mock_fk_row.target_schema = "dbo"
        mock_fk_row.target_table = "Customers"
        mock_fk_row.target_column = "CustomerKey"

        mock_source_conn = MagicMock()
        
        def execute_side_effect(sql_text, *args, **kwargs):
            sql_str = str(sql_text)
            mock_res = MagicMock()
            if "sys.foreign_key_columns" in sql_str:
                mock_res.fetchall.return_value = [mock_fk_row]
            elif "CONSTRAINT_TYPE = 'PRIMARY KEY'" in sql_str:
                mock_pk_row = MagicMock()
                mock_pk_row.TABLE_SCHEMA = "dbo"
                mock_pk_row.TABLE_NAME = "Customers"
                mock_pk_row.COLUMN_NAME = "CustomerKey"
                mock_res.fetchall.return_value = [mock_pk_row]
            else:
                mock_res.fetchall.return_value = []
                mock_res.fetchone.return_value = None
            return mock_res

        mock_source_conn.execute.side_effect = execute_side_effect
        mock_source_engine = MagicMock()
        mock_source_engine.connect.return_value.__enter__.return_value = mock_source_conn
        mock_create_engine.return_value = mock_source_engine

        # Populate tables and columns
        with test_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO schema_tables (table_id, connection_id, schema_name, table_name)
                VALUES 
                    ('t_sales', :conn_id, 'dbo', 'Sales'),
                    ('t_customers', :conn_id, 'dbo', 'Customers')
            """), {"conn_id": connection_id})
            
            conn.execute(text("""
                INSERT INTO schema_columns (column_id, table_id, column_name, data_type)
                VALUES 
                    ('c_sales_cust', 't_sales', 'CustomerKey', 'int'),
                    ('c_cust_key', 't_customers', 'CustomerKey', 'int')
            """))

        # 1. Run discovery first time
        RelationshipDiscoveryService.discover_relationships(company_id, connection_id)

        # Verify it was inserted as SYSTEM relationship
        with test_engine.connect() as conn:
            rels = conn.execute(text("SELECT * FROM schema_relationships WHERE connection_id = :conn_id"), {"conn_id": connection_id}).fetchall()
            self.assertEqual(len(rels), 1)
            self.assertEqual(rels[0].discovered_by, "SYSTEM")

        # 2. Add a manual USER relationship with the same details
        with test_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO schema_relationships (
                    relationship_id, company_id, connection_id,
                    source_table_id, source_column_id, target_table_id, target_column_id,
                    relationship_type, confidence_score, is_confirmed, discovered_by
                ) VALUES (
                    'rel-manual-1', :comp_id, :conn_id,
                    't_sales', 'c_sales_cust', 't_customers', 'c_cust_key',
                    'MANUAL', 1.0, 1, 'USER'
                )
            """), {"comp_id": company_id, "conn_id": connection_id})

        # Run discovery a second time
        RelationshipDiscoveryService.discover_relationships(company_id, connection_id)

        # Verify:
        # - The USER relationship is still there (not deleted)
        # - The SYSTEM relationship was deleted/re-evaluated or not duplicated
        with test_engine.connect() as conn:
            rels = conn.execute(text("SELECT * FROM schema_relationships WHERE connection_id = :conn_id ORDER BY discovered_by"), {"conn_id": connection_id}).fetchall()
            # We expect exactly 1 row (the USER one) because the SYSTEM discovery check skips inserting
            # if the relationship already exists (which the USER one does!).
            self.assertEqual(len(rels), 1)
            self.assertEqual(rels[0].discovered_by, "USER")

    @patch("semantic.semantic_service.engine", test_engine)
    def test_dimension_name_uniqueness_scoped_by_table_and_column(self):
        connection_id = str(uuid.uuid4())
        user = {"employee_id": "test-emp"}

        # 1. Create a dimension on Orders table
        data1 = {
            "dimension_name": "status",
            "business_name": "Order Status",
            "synonyms": "state",
            "description": "status of order",
            "table_name": "Orders",
            "column_name": "order_status"
        }
        res1 = SemanticService.create_dimension(connection_id, data1, user)
        self.assertIn("dimension_id", res1)
        dim1_id = res1["dimension_id"]

        # 2. Create another dimension with same name but on Users table.
        # This should SUCCEED because it's on a different table/column.
        data2 = {
            "dimension_name": "status",
            "business_name": "User Status",
            "synonyms": "active_state",
            "description": "status of user",
            "table_name": "Users",
            "column_name": "user_status"
        }
        res2 = SemanticService.create_dimension(connection_id, data2, user)
        self.assertIn("dimension_id", res2)

        # 3. Trying to create a third dimension on the same Orders table and order_status column
        # with the same name 'status' should FAIL.
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            SemanticService.create_dimension(connection_id, data1, user)
        self.assertEqual(ctx.exception.status_code, 409)

        # 4. Updating the first dimension (Orders.order_status) without changing name
        # should succeed even though Users.user_status also has name 'status'.
        data1_updated = data1.copy()
        data1_updated["synonyms"] = "state,progress"
        res_update = SemanticService.update_dimension(dim1_id, data1_updated, user)
        self.assertEqual(res_update["message"], "Semantic dimension updated successfully.")
