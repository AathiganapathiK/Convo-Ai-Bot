import sys
import os
import json
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
    clear_pending_clarification
)

class TestPhase1D6D3SelectionMatching(unittest.TestCase):

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
            "role": "ANALYST"
        }
        
        self.mock_request = MagicMock()
        self.mock_request.client.host = "127.0.0.1"
        
        # Test options:
        # 1. LS ZARI COTTON
        # 2. LS COTTON BREEZE
        # 3. MENS PYJAMA PANT
        self.mock_options = {
            "1": {
                "option_id": 1, "value": "LS ZARI COTTON", "dimension": "Prod Grp2", "dimension_id": 101,
                "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls zari cotton"
            },
            "2": {
                "option_id": 2, "value": "LS COTTON BREEZE", "dimension": "Prod Grp2", "dimension_id": 101,
                "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls cotton breeze"
            },
            "3": {
                "option_id": 3, "value": "MENS PYJAMA PANT", "dimension": "Prod Grp2", "dimension_id": 101,
                "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "mens pyjama pant"
            }
        }
        
        clear_pending_clarification("EMP001", "42")
        set_pending_clarification(
            "EMP001", "42",
            {
                "original_question": "Show cotton pant sales",
                "ambiguity_type": "SAME_DIMENSION",
                "options": self.mock_options
            }
        )

    def tearDown(self):
        self.conn_svc_patcher.stop()
        clear_pending_clarification("EMP001", "42")

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_numeric_selection(self, mock_gen_sql, mock_classify):
        """Verify selection via option number '1'."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 1"}
        
        response = app.ask_question(question="1", session_id=42, request=self.mock_request, user=self.user)
        self.assertNotIsInstance(response, json.JSONEncoder) # check success/no error
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=self.mock_options["1"]
        )

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_option_n_selection(self, mock_gen_sql, mock_classify):
        """Verify selection via text 'option 2'."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 2"}
        
        response = app.ask_question(question="option 2", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=self.mock_options["2"]
        )

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_exact_value_selection(self, mock_gen_sql, mock_classify):
        """Verify selection via exact displayed value 'MENS PYJAMA PANT'."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 3"}
        
        response = app.ask_question(question="MENS PYJAMA PANT", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=self.mock_options["3"]
        )

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_case_insensitive_exact_value_selection(self, mock_gen_sql, mock_classify):
        """Verify selection via case-insensitive exact value 'mens pyjama pant'."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 3"}
        
        response = app.ask_question(question="mens pyjama pant", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=self.mock_options["3"]
        )

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_unique_prefix_selection(self, mock_gen_sql, mock_classify):
        """Verify selection via unique prefix 'mens pyjama'."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 3"}
        
        response = app.ask_question(question="mens pyjama", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=self.mock_options["3"]
        )

    @patch("app.route_question")
    def test_ambiguous_selection(self, mock_classify):
        """Verify that typing an ambiguous prefix like 'ls' returns a 400 clarification required."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        response = app.ask_question(question="ls", session_id=42, request=self.mock_request, user=self.user)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode('utf-8'))
        self.assertEqual(body.get("action"), "CLARIFICATION_REQUIRED")
        self.assertIn("more than one option", body.get("error", {}).get("message").lower())

    @patch("app.route_question")
    def test_invalid_selection(self, mock_classify):
        """Verify that typing an invalid value like 'pant' (which is a substring but NOT a prefix/exact) is rejected."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        response = app.ask_question(question="pant", session_id=42, request=self.mock_request, user=self.user)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode('utf-8'))
        self.assertEqual(body.get("action"), "CLARIFICATION_REQUIRED")
        self.assertIn("isn't one of the available options", body.get("error", {}).get("message").lower())

if __name__ == "__main__":
    unittest.main()
