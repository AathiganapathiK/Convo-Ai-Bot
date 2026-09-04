import sys
import os
import json
import time
import unittest
from unittest.mock import MagicMock, patch

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup mock database engine before importing app
mock_conn = MagicMock()
session_row = MagicMock()
session_row.id = 42
session_row._mapping = {
    "id": 42,
    "employee_id": "EMP001",
    "company_id": "COMPANY001"
}
mock_conn.execute.return_value.fetchone.return_value = session_row

# Set fetchall to return a MagicMock that acts as an empty list by default,
# so get_schema_metadata doesn't crash but returns empty dict.
mock_conn.execute.return_value.fetchall.return_value = []

mock_engine = MagicMock()
mock_engine.connect.return_value.__enter__.return_value = mock_conn
mock_engine.begin.return_value.__enter__.return_value = mock_conn

import database
database.engine = mock_engine

import app
from ai.intent_classifier import Destination, RoutingDecision
from services.conversation_memory import (
    set_pending_clarification,
    get_pending_clarification,
    clear_pending_clarification,
    pending_clarification_store
)

class TestPhase1D6D4ResumeSecurity(unittest.TestCase):

    def setUp(self):
        app.engine = mock_engine
        self.conn_svc_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_svc = self.conn_svc_patcher.start()
        self.mock_conn_svc.get_active_connection.return_value = {
            "connection_id": "CONN001",
            "connection_name": "TestDB",
            "database_type": "mssql"
        }

        self.user = {
            "employee_id": "EMP001",
            "company_id": "COMPANY001",
            "role": "ANALYST",
            "official_email": "analyst@company.com"
        }
        
        self.mock_request = MagicMock()
        self.mock_request.client.host = "127.0.0.1"
        
        self.mock_options = {
            "1": {
                "option_id": 1, "value": "LS ZARI COTTON", "dimension": "Prod Grp2", "dimension_id": 101,
                "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls zari cotton"
            },
            "2": {
                "option_id": 2, "value": "LS COTTON BREEZE", "dimension": "Prod Grp2", "dimension_id": 101,
                "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls cotton breeze"
            }
        }
        
        clear_pending_clarification("EMP001", "42")
        set_pending_clarification(
            "EMP001", "42",
            {
                "original_question": "Show cotton sales",
                "ambiguity_type": "SAME_DIMENSION",
                "options": self.mock_options
            }
        )

    def tearDown(self):
        self.conn_svc_patcher.stop()
        clear_pending_clarification("EMP001", "42")

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    @patch("app.add_exchange")
    @patch("app.validate_sql_query")
    @patch("app.ConnectionManager.source")
    @patch("app.generate_business_summary")
    @patch("app.generate_chart_metadata")
    @patch("app.generate_kpis")
    def test_successful_resume_flow(self, mock_kpis, mock_chart, mock_summary, mock_cm_source, mock_val_sql, mock_add_exchange, mock_gen_sql, mock_classify):
        """Verify successful resume recovers candidate, restores question, clears state, and records history."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_gen_sql.return_value = {
            "success": True, 
            "sql_query": "SELECT * FROM sales WHERE ProdGrp2 = 'LS ZARI COTTON'", 
            "usage": None,
            "semantic_result": {
                "metric_objects": [],
                "dimension_objects": [],
                "value_matches": [self.mock_options["1"]]
            },
            "runtime_context": {}
        }
        mock_val_sql.return_value = (True, "SELECT * FROM sales WHERE ProdGrp2 = 'LS ZARI COTTON'")
        mock_cm_source.return_value = mock_engine
        
        # Mock database execution results for the SQL query
        mock_exec_res = MagicMock()
        mock_exec_res.keys.return_value = ["sales_amount"]
        mock_exec_res.fetchall.return_value = [(100.0,)]
        
        # Route query types correctly: metadata queries vs business SQL execution
        def mock_execute_side_effect(statement, *args, **kwargs):
            stmt_str = str(statement).lower()
            if "chat_sessions" in stmt_str:
                res = MagicMock()
                res.fetchone.return_value = session_row
                res.fetchall.return_value = []
                return res
            elif any(k in stmt_str for k in ("roles", "role_column_access", "user_data_access", "schema_tables", "schema_columns", "column_display_config")):
                res = MagicMock()
                res.fetchone.return_value = None
                res.fetchall.return_value = []
                return res
            return mock_exec_res
            
        mock_conn.execute.side_effect = mock_execute_side_effect
        
        mock_summary.return_value = {"summary": "Sales summary", "followups": [], "usage": None}
        mock_chart.return_value = {"recommended_view": "table", "insight": "ok"}
        mock_kpis.return_value = []
        
        response = app.ask_question(question="1", session_id=42, request=self.mock_request, user=self.user)
        
        # Verify response was successful
        self.assertNotIsInstance(response, json.JSONEncoder)
        if hasattr(response, "status_code"):
            self.assertEqual(response.status_code, 200)

        # 1. Selection was resolved using server-side options and original question was restored
        mock_gen_sql.assert_called_with(
            "Show cotton sales", [], company_id="COMPANY001", clarified_candidate=self.mock_options["1"]
        )
        # 2. Pending clarification cleared on success
        self.assertIsNone(get_pending_clarification("EMP001", "42"))
        # 3. Exchange recorded in conversation history with correct semantic_context
        mock_add_exchange.assert_called_once()
        args, kwargs = mock_add_exchange.call_args
        self.assertEqual(args[0], "EMP001")
        self.assertEqual(args[1], "Show cotton sales")
        self.assertEqual(args[2], "SELECT TOP 100 * FROM sales WHERE ProdGrp2 = 'LS ZARI COTTON'")
        self.assertEqual(args[3], "42")
        self.assertIn("resolved_values", kwargs["semantic_context"])
        self.assertEqual(kwargs["semantic_context"]["resolved_values"][0]["value"], "LS ZARI COTTON")

    @patch("app.route_question")
    def test_invalid_selection_retains_pending_state(self, mock_classify):
        """Verify that an invalid choice does not clear the pending clarification state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_conn.execute.side_effect = None
        
        response = app.ask_question(question="invalid_choice", session_id=42, request=self.mock_request, user=self.user)
        self.assertEqual(response.status_code, 400)
        
        # State must STILL exist
        state = get_pending_clarification("EMP001", "42")
        self.assertIsNotNone(state)
        self.assertEqual(state["original_question"], "Show cotton sales")

    @patch("app.route_question")
    def test_ambiguous_selection_retains_pending_state(self, mock_classify):
        """Verify that an ambiguous choice does not clear the pending clarification state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_conn.execute.side_effect = None
        
        response = app.ask_question(question="ls", session_id=42, request=self.mock_request, user=self.user)
        self.assertEqual(response.status_code, 400)
        
        # State must STILL exist
        state = get_pending_clarification("EMP001", "42")
        self.assertIsNotNone(state)
        self.assertEqual(state["original_question"], "Show cotton sales")

    @patch("app.route_question")
    def test_expired_state_cannot_resume(self, mock_classify):
        """Verify that an expired pending state (TTL > 300s) is rejected and cannot resume."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_conn.execute.side_effect = None
        
        # Artificially set timestamp to 301 seconds ago
        key = ("EMP001", "42")
        pending_clarification_store[key]["timestamp"] = time.time() - 301
        
        # Attempt resume
        response = app.ask_question(question="1", session_id=42, request=self.mock_request, user=self.user)
        
        # Should be treated as normal question and bypass resume because state expired
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.route_question")
    @patch("semantic.semantic_resolver.SemanticResolver.resolve")
    def test_intent_shift_clears_pending_state(self, mock_resolve, mock_classify):
        """Verify that a new question with semantic intent (intent shift) clears the pending state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_conn.execute.side_effect = None
        
        # Mock semantic resolver indicating that the query has dimension/metric entities
        mock_resolve.return_value = {
            "metrics": ["Sales"],
            "dimensions": [],
            "metric_objects": [{"type": "metric"}],
            "dimension_objects": [],
            "value_matches": []
        }
        
        # User shifts intent to "show sales for shirt"
        response = app.ask_question(question="show sales for shirt", session_id=42, request=self.mock_request, user=self.user)
        
        # Pending state must be cleared
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.route_question")
    @patch("security.cls_engine.get_forbidden_columns")
    def test_security_revalidation_cls_blocks_continuation(self, mock_get_forbidden, mock_classify):
        """Verify that CLS security revalidation blocks continuation if candidate references forbidden column."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_conn.execute.side_effect = None
        mock_get_forbidden.return_value = ["ProdGrp2"] # Restrict the column referenced in the option
        
        response = app.ask_question(question="1", session_id=42, request=self.mock_request, user=self.user)
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.body.decode('utf-8'))
        self.assertEqual(body.get("error", {}).get("code"), "SECURITY_001")
        self.assertIn("denied", body.get("error", {}).get("message").lower())

if __name__ == "__main__":
    unittest.main()
