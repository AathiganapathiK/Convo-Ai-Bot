import sys
import os
import time
import json
from unittest.mock import MagicMock, patch

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 1. Setup mock database engine BEFORE importing app or other service files
mock_conn = MagicMock()

# Setup row mappings for connection execute fetchone
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

# Now import application modules
import app
import unittest
from fastapi.responses import JSONResponse
from services.conversation_memory import (
    get_pending_clarification,
    set_pending_clarification,
    clear_pending_clarification,
    pending_clarification_store
)
from semantic.matching.models import (
    MatchResult, MatchType, ResolutionStatus, AmbiguityChoice, SemanticResolutionResult
)

class TestPhase1D2EClarificationOffline(unittest.TestCase):

    def setUp(self):
        app.engine = mock_engine
        # 2. Patch ConnectionService globally
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
        
        # Clear storage
        clear_pending_clarification("EMP001", "42")

    def tearDown(self):
        self.conn_svc_patcher.stop()
        clear_pending_clarification("EMP001", "42")

    @patch("app.classify_intent")
    @patch("semantic.semantic_resolver.SemanticResolver.resolve")
    @patch("app.generate_sql_query")
    def test_pant_triggers_strong_ambiguity_clarification(self, mock_gen_sql, mock_resolve, mock_classify):
        """Verify that 'pant' triggers STRONG_AMBIGUITY and returns CLARIFICATION_REQUIRED response."""
        mock_classify.return_value = "ANALYTICAL"
        
        # Construct two ambiguity candidates
        m1 = MatchResult(
            matched=True, value="LINEN PANT", normalized_value="linen pant", confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
            reason="test", dimension_id=201, business_name="Brand", table_name="Products", column_name="Brand"
        )
        m2 = MatchResult(
            matched=True, value="RAMRAJ PANT", normalized_value="ramraj pant", confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL, matched_question_tokens=["pant"], matched_value_tokens=["ramraj", "pant"],
            reason="test", dimension_id=201, business_name="Brand", table_name="Products", column_name="Brand"
        )
        
        c1 = AmbiguityChoice(result=m1, actual_query_coverage=1, matched_query_tokens=["pant"])
        c2 = AmbiguityChoice(result=m2, actual_query_coverage=1, matched_query_tokens=["pant"])
        
        ambig_res = SemanticResolutionResult(
            status=ResolutionStatus.STRONG_AMBIGUITY,
            candidates=[c1, c2]
        )
        
        # Mock semantic resolver response
        mock_resolve.return_value = {
            "metrics": [], "dimensions": [], "metric_objects": [], "dimension_objects": [],
            "value_matches": [
                {
                    "dimension_id": 201, "business_name": "Brand", "table_name": "Products", "column_name": "Brand",
                    "value": "LINEN PANT", "normalized_value": "linen pant", "confidence": 0.95,
                    "match_type": "SINGULAR_PLURAL", "matched_question_tokens": ["pant"], "matched_value_tokens": ["linen", "pant"]
                },
                {
                    "dimension_id": 201, "business_name": "Brand", "table_name": "Products", "column_name": "Brand",
                    "value": "RAMRAJ PANT", "normalized_value": "ramraj pant", "confidence": 0.95,
                    "match_type": "SINGULAR_PLURAL", "matched_question_tokens": ["pant"], "matched_value_tokens": ["ramraj", "pant"]
                }
            ],
            "ambiguity_result": ambig_res,
            "retrieval": {
                "status": "STRONG_AMBIGUITY",
                "confidence": 0.95,
                "resolved_components": 1
            }
        }
        
        # When generate_sql_query runs, it will raise AmbiguityException which gets converted to dict.
        from core.exceptions import AmbiguityException
        ex = AmbiguityException(
            message="I found multiple values for Brand. Did you mean 'LINEN PANT' or 'RAMRAJ PANT'?",
            details={
                "original_question": "pant",
                "ambiguity_type": "SAME_DIMENSION",
                "options": [
                    {
                        "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                        "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
                    },
                    {
                        "option_id": 2, "value": "RAMRAJ PANT", "dimension": "Brand", "dimension_id": 201,
                        "table_name": "Products", "column_name": "Brand", "normalized_value": "ramraj pant"
                    }
                ]
            }
        )
        mock_gen_sql.return_value = ex.to_dict()
        
        response = app.ask_question(
            question="pant",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode('utf-8'))
        self.assertEqual(body.get("action"), "CLARIFICATION_REQUIRED")
        self.assertEqual(body.get("error", {}).get("code"), "AMBIGUITY_DETECTED")
        
        details = body.get("error", {}).get("details", {})
        self.assertEqual(details.get("original_question"), "pant")
        self.assertEqual(details.get("ambiguity_type"), "SAME_DIMENSION")
        
        # Confirm internal security information is NOT leaked to user
        options = details.get("options", [])
        self.assertEqual(len(options), 2)
        for opt in options:
            self.assertIn("option_id", opt)
            self.assertIn("value", opt)
            # These internal fields must NOT appear in public response
            self.assertNotIn("dimension", opt)
            self.assertNotIn("dimension_id", opt)
            self.assertNotIn("table_name", opt)
            self.assertNotIn("column_name", opt)
            self.assertNotIn("normalized_value", opt)
            self.assertNotIn("match_type", opt)
            self.assertNotIn("matched_question_tokens", opt)
            self.assertNotIn("matched_value_tokens", opt)
            
        # State must be successfully saved in the pending clarification store
        state = get_pending_clarification(self.user["employee_id"], "42")
        self.assertIsNotNone(state)
        self.assertEqual(state["original_question"], "pant")
        self.assertIn("1", state["options"])
        self.assertEqual(state["options"]["1"]["value"], "LINEN PANT")

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_option_selection_resolution(self, mock_gen_sql, mock_classify):
        """Verify selecting option '2' resumes query with selected candidate and clears pending state."""
        mock_classify.return_value = "ANALYTICAL"
        
        mock_options = {
            "1": {
                "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
            },
            "2": {
                "option_id": 2, "value": "RAMRAJ PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "ramraj pant"
            }
        }
        
        set_pending_clarification(
            self.user["employee_id"],
            "42",
            {
                "original_question": "show sales for pant",
                "ambiguity_type": "SAME_DIMENSION",
                "options": mock_options
            }
        )
        
        mock_gen_sql.return_value = {
            "success": True,
            "sql_query": "SELECT sum(sales) FROM sales WHERE brand = 'RAMRAJ PANT'",
            "usage": None,
            "semantic_result": {},
            "runtime_context": {}
        }
        
        # Resume with "2"
        response = app.ask_question(
            question="2",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        # Verify generate_sql_query was called with the clarified candidate
        mock_gen_sql.assert_called_with(
            "show sales for pant",
            [],
            company_id="COMPANY001",
            clarified_candidate=mock_options["2"]
        )
        
        # Pending state must be cleared
        self.assertIsNone(get_pending_clarification(self.user["employee_id"], "42"))

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_option_token_match_resolution(self, mock_gen_sql, mock_classify):
        """Verify selecting via unique value substring 'Ramraj' resolves successfully."""
        mock_classify.return_value = "ANALYTICAL"
        
        mock_options = {
            "1": {
                "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
            },
            "2": {
                "option_id": 2, "value": "RAMRAJ PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "ramraj pant"
            }
        }
        
        set_pending_clarification(
            self.user["employee_id"],
            "42",
            {
                "original_question": "show sales for pant",
                "ambiguity_type": "SAME_DIMENSION",
                "options": mock_options
            }
        )
        
        mock_gen_sql.return_value = {
            "success": True,
            "sql_query": "SELECT sum(sales) FROM sales WHERE brand = 'RAMRAJ PANT'",
            "usage": None,
            "semantic_result": {},
            "runtime_context": {}
        }
        
        # Resume with "Ramraj"
        response = app.ask_question(
            question="Ramraj",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        mock_gen_sql.assert_called_with(
            "show sales for pant",
            [],
            company_id="COMPANY001",
            clarified_candidate=mock_options["2"]
        )
        self.assertIsNone(get_pending_clarification(self.user["employee_id"], "42"))

    @patch("app.classify_intent")
    def test_ambiguous_selection_does_not_guess(self, mock_classify):
        """Verify that selecting ambiguous text like 'linen' returns clarification and does not execute SQL."""
        mock_classify.return_value = "ANALYTICAL"
        
        mock_options = {
            "1": {
                "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
            },
            "2": {
                "option_id": 2, "value": "LINEN SHIRT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen shirt"
            }
        }
        
        set_pending_clarification(
            self.user["employee_id"],
            "42",
            {
                "original_question": "show sales for pant",
                "ambiguity_type": "SAME_DIMENSION",
                "options": mock_options
            }
        )
        
        response = app.ask_question(
            question="linen",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode('utf-8'))
        self.assertEqual(body.get("action"), "CLARIFICATION_REQUIRED")
        self.assertIn("more than one option", body.get("error", {}).get("message").lower())
        
        # State must NOT be cleared
        self.assertIsNotNone(get_pending_clarification(self.user["employee_id"], "42"))

    @patch("app.classify_intent")
    @patch("semantic.semantic_resolver.SemanticResolver.resolve")
    def test_intent_shift_clears_clarification(self, mock_resolve, mock_classify):
        """Verify that typing an unrelated query (intent shift) clears clarification and processes the new question."""
        mock_classify.return_value = "ANALYTICAL"
        
        mock_options = {
            "1": {
                "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
            }
        }
        
        set_pending_clarification(
            self.user["employee_id"],
            "42",
            {
                "original_question": "show sales for pant",
                "ambiguity_type": "SAME_DIMENSION",
                "options": mock_options
            }
        )
        
        # Mock resolve to indicate that the new query "show sales for banians" contains semantic intent
        mock_resolve.return_value = {
            "metrics": ["Sales"], "dimensions": [], "metric_objects": [{"type": "metric"}],
            "dimension_objects": [], "value_matches": []
        }
        
        # Run new question
        response = app.ask_question(
            question="show sales for banians",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        # Pending state must be cleared because of intent shift
        self.assertIsNone(get_pending_clarification(self.user["employee_id"], "42"))

    @patch("app.classify_intent")
    def test_cls_block_on_resume(self, mock_classify):
        """Verify that selecting a candidate that references a forbidden column raises CLS block."""
        mock_classify.return_value = "ANALYTICAL"
        
        # Let's mock a restricted column name for CLS check
        with patch("security.cls_engine.get_forbidden_columns", return_value=["Salary"]):
            mock_options = {
                "1": {
                    "option_id": 1, "value": "RESTRICTED", "dimension": "Salary", "dimension_id": 999,
                    "table_name": "Employees", "column_name": "Salary", "normalized_value": "restricted"
                }
            }
            
            set_pending_clarification(
                self.user["employee_id"],
                "42",
                {
                    "original_question": "show salary for employees",
                    "ambiguity_type": "SAME_DIMENSION",
                    "options": mock_options
                }
            )
            
            response = app.ask_question(
                question="1",
                session_id=42,
                request=self.mock_request,
                user=self.user
            )
            
            self.assertIsInstance(response, JSONResponse)
            self.assertEqual(response.status_code, 403)
            body = json.loads(response.body.decode('utf-8'))
            self.assertEqual(body.get("error", {}).get("code"), "SECURITY_001")

    # -------------------------------------------------------
    # Phase 1D.6.D.2 — Selection Parsing + Public Payload
    # -------------------------------------------------------

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_exact_value_selection_resolves(self, mock_gen_sql, mock_classify):
        """Exact value 'MENS PYJAMA PANT' must resolve to exactly one option."""
        mock_classify.return_value = "ANALYTICAL"
        mock_options = {
            "1": {"option_id": 1, "value": "LS ZARI COTTON", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls zari cotton"},
            "2": {"option_id": 2, "value": "LS COTTON BREEZE", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls cotton breeze"},
            "3": {"option_id": 3, "value": "MENS PYJAMA PANT", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "mens pyjama pant"}
        }
        set_pending_clarification("EMP001", "42", {
            "original_question": "Show cotton pant sales",
            "ambiguity_type": "SAME_DIMENSION",
            "options": mock_options
        })
        mock_gen_sql.return_value = {
            "success": True, "sql_query": "SELECT 1", "usage": None, "semantic_result": {}, "runtime_context": {}
        }
        app.ask_question(question="MENS PYJAMA PANT", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=mock_options["3"]
        )
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_single_quoted_exact_value_resolves(self, mock_gen_sql, mock_classify):
        """'MENS PYJAMA PANT' (with surrounding single quotes) must resolve correctly."""
        mock_classify.return_value = "ANALYTICAL"
        mock_options = {
            "1": {"option_id": 1, "value": "LS ZARI COTTON", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls zari cotton"},
            "2": {"option_id": 2, "value": "MENS PYJAMA PANT", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "mens pyjama pant"}
        }
        set_pending_clarification("EMP001", "42", {
            "original_question": "Show cotton pant sales",
            "ambiguity_type": "SAME_DIMENSION",
            "options": mock_options
        })
        mock_gen_sql.return_value = {
            "success": True, "sql_query": "SELECT 1", "usage": None, "semantic_result": {}, "runtime_context": {}
        }
        app.ask_question(question="'MENS PYJAMA PANT'", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=mock_options["2"]
        )
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_double_quoted_exact_value_resolves(self, mock_gen_sql, mock_classify):
        """MENS PYJAMA PANT with surrounding double quotes must resolve correctly."""
        mock_classify.return_value = "ANALYTICAL"
        mock_options = {
            "1": {"option_id": 1, "value": "LS ZARI COTTON", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls zari cotton"},
            "2": {"option_id": 2, "value": "MENS PYJAMA PANT", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "mens pyjama pant"}
        }
        set_pending_clarification("EMP001", "42", {
            "original_question": "Show cotton pant sales",
            "ambiguity_type": "SAME_DIMENSION",
            "options": mock_options
        })
        mock_gen_sql.return_value = {
            "success": True, "sql_query": "SELECT 1", "usage": None, "semantic_result": {}, "runtime_context": {}
        }
        # Double quotes around the value
        app.ask_question(question='"MENS PYJAMA PANT"', session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=mock_options["2"]
        )
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_embedded_value_with_dimension_label_resolves(self, mock_gen_sql, mock_classify):
        """'I meant Prod Grp2 MENS PYJAMA PANT' must resolve via Tier 3 substring match."""
        mock_classify.return_value = "ANALYTICAL"
        mock_options = {
            "1": {"option_id": 1, "value": "LS ZARI COTTON", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls zari cotton"},
            "2": {"option_id": 2, "value": "LS COTTON BREEZE", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "ls cotton breeze"},
            "3": {"option_id": 3, "value": "MENS PYJAMA PANT", "dimension": "Prod Grp2", "dimension_id": "D1",
                  "table_name": "Products", "column_name": "ProdGrp2", "normalized_value": "mens pyjama pant"}
        }
        set_pending_clarification("EMP001", "42", {
            "original_question": "Show cotton pant sales",
            "ambiguity_type": "SAME_DIMENSION",
            "options": mock_options
        })
        mock_gen_sql.return_value = {
            "success": True, "sql_query": "SELECT 1", "usage": None, "semantic_result": {}, "runtime_context": {}
        }
        app.ask_question(
            question="I meant Prod Grp2 'MENS PYJAMA PANT'",
            session_id=42, request=self.mock_request, user=self.user
        )
        mock_gen_sql.assert_called_with(
            "Show cotton pant sales", [], company_id="COMPANY001", clarified_candidate=mock_options["3"]
        )
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.classify_intent")
    @patch("app.generate_sql_query")
    def test_server_side_state_retains_internal_metadata(self, mock_gen_sql, mock_classify):
        """Verify the server-side pending state retains all internal metadata for secure resumption."""
        mock_classify.return_value = "ANALYTICAL"
        from core.exceptions import AmbiguityException
        ex = AmbiguityException(
            message="Multiple matches",
            details={
                "original_question": "pant",
                "ambiguity_type": "SAME_DIMENSION",
                "options": [
                    {
                        "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                        "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
                    }
                ]
            }
        )
        mock_gen_sql.return_value = ex.to_dict()
        response = app.ask_question(question="pant", session_id=42, request=self.mock_request, user=self.user)

        # Public response must NOT contain internal metadata
        body = json.loads(response.body.decode('utf-8'))
        public_opts = body.get("error", {}).get("details", {}).get("options", [])
        for opt in public_opts:
            self.assertNotIn("dimension", opt)
            self.assertNotIn("dimension_id", opt)
            self.assertNotIn("table_name", opt)
            self.assertNotIn("column_name", opt)

        # Server-side state MUST still contain internal metadata
        state = get_pending_clarification("EMP001", "42")
        self.assertIsNotNone(state)
        internal_opt = state["options"]["1"]
        self.assertIn("table_name", internal_opt)
        self.assertIn("column_name", internal_opt)
        self.assertIn("dimension", internal_opt)
        self.assertIn("dimension_id", internal_opt)
        self.assertEqual(internal_opt["table_name"], "Products")
        self.assertEqual(internal_opt["column_name"], "Brand")

if __name__ == "__main__":
    unittest.main()

