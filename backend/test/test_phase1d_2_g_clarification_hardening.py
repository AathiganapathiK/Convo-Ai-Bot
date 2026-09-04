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
def create_mock_session_row(session_id=42, employee_id="EMP001", company_id="COMPANY001"):
    row = MagicMock()
    row.id = session_id
    row._mapping = {
        "id": session_id,
        "employee_id": employee_id,
        "company_id": company_id
    }
    return row

mock_engine = MagicMock()
mock_engine.connect.return_value.__enter__.return_value = mock_conn
mock_engine.begin.return_value.__enter__.return_value = mock_conn

import database
database.engine = mock_engine

# Now import application modules
import app
from ai.intent_classifier import Destination, RoutingDecision
import unittest
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from services.conversation_memory import (
    get_pending_clarification,
    set_pending_clarification,
    clear_pending_clarification,
    pending_clarification_store
)
from semantic.matching.models import (
    MatchResult, MatchType, ResolutionStatus, AmbiguityChoice, SemanticResolutionResult
)

class TestPhase1D2GClarificationHardening(unittest.TestCase):

    def setUp(self):
        app.engine = mock_engine
        # Reset default session mock return value to prevent test leakage
        mock_conn.execute.return_value.fetchone.return_value = create_mock_session_row(42, "EMP001", "COMPANY001")

        # Patch ConnectionService globally
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
        clear_pending_clarification("EMP002", "42")
        clear_pending_clarification("EMP001", "43")

    def tearDown(self):
        self.conn_svc_patcher.stop()
        clear_pending_clarification("EMP001", "42")
        clear_pending_clarification("EMP002", "42")
        clear_pending_clarification("EMP001", "43")

    # ----------------------------------------------------
    # 1. Response Contract & Metadata Leakage
    # ----------------------------------------------------
    @patch("app.route_question")
    @patch("semantic.semantic_resolver.SemanticResolver.resolve")
    @patch("app.generate_sql_query")
    def test_response_contract_and_metadata_leakage(self, mock_gen_sql, mock_resolve, mock_classify):
        """Verify that STRONG_AMBIGUITY response contract contains correct details and does not leak internal schema metadata."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        # Construct candidates
        m1 = MatchResult(
            matched=True, value="LINEN PANT", normalized_value="linen pant", confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
            reason="test", dimension_id=201, business_name="Brand", table_name="Products", column_name="Brand"
        )
        c1 = AmbiguityChoice(result=m1, actual_query_coverage=1, matched_query_tokens=["pant"])
        
        ambig_res = SemanticResolutionResult(
            status=ResolutionStatus.STRONG_AMBIGUITY,
            candidates=[c1]
        )
        
        mock_resolve.return_value = {
            "metrics": [], "dimensions": [], "metric_objects": [], "dimension_objects": [],
            "value_matches": [
                {
                    "dimension_id": 201, "business_name": "Brand", "table_name": "Products", "column_name": "Brand",
                    "value": "LINEN PANT", "normalized_value": "linen pant", "confidence": 0.95,
                    "match_type": "SINGULAR_PLURAL", "matched_question_tokens": ["pant"], "matched_value_tokens": ["linen", "pant"]
                }
            ],
            "ambiguity_result": ambig_res,
            "retrieval": {
                "status": "STRONG_AMBIGUITY",
                "confidence": 0.95,
                "resolved_components": 1
            }
        }
        
        from core.exceptions import AmbiguityException
        ex = AmbiguityException(
            message="Multiple brands found",
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
        
        response = app.ask_question(
            question="pant",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode('utf-8'))
        
        self.assertEqual(body.get("action"), "CLARIFICATION_REQUIRED")
        details = body.get("error", {}).get("details", {})
        self.assertEqual(details.get("original_question"), "pant")
        
        options = details.get("options", [])
        self.assertEqual(len(options), 1)
        opt = options[0]
        # Required public attributes
        self.assertEqual(opt["option_id"], 1)
        self.assertEqual(opt["value"], "LINEN PANT")
        
        # ALL internal metadata must NOT leak in public response
        self.assertNotIn("dimension", opt)
        self.assertNotIn("dimension_id", opt)
        self.assertNotIn("table_name", opt)
        self.assertNotIn("column_name", opt)
        self.assertNotIn("normalized_value", opt)
        self.assertNotIn("match_type", opt)
        self.assertNotIn("matched_question_tokens", opt)
        self.assertNotIn("matched_value_tokens", opt)

    # ----------------------------------------------------
    # 2. Option ID Integrity & Spoof Prevention
    # ----------------------------------------------------
    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_option_id_integrity_and_spoof_prevention(self, mock_gen_sql, mock_classify):
        """Verify client cannot spoof candidate metadata by providing arbitrary values."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        # Store state on server
        mock_options = {
            "1": {
                "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
            }
        }
        set_pending_clarification(
            self.user["employee_id"], "42",
            {"original_question": "show sales for pant", "ambiguity_type": "SAME_DIMENSION", "options": mock_options}
        )
        
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 1", "usage": None, "semantic_result": {}, "runtime_context": {}}
        
        # When user selects option "1", verify the backend pulls the server candidate, not any client inputs
        app.ask_question(
            question="1",
            session_id=42,
            request=self.mock_request,
            user=self.user
        )
        
        # Check that generate_sql_query was called with server-side candidate
        mock_gen_sql.assert_called_with(
            "show sales for pant", [], company_id="COMPANY001", clarified_candidate=mock_options["1"]
        )

    # ----------------------------------------------------
    # 3. Session & User Isolation
    # ----------------------------------------------------
    @patch("app.route_question")
    def test_session_and_user_isolation(self, mock_classify):
        """Verify User B or Session B cannot resolve User A's pending clarification state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        mock_options = {
            "1": {
                "option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"
            }
        }
        
        # Set state for User A (EMP001) in Session 42
        set_pending_clarification(
            "EMP001", "42",
            {"original_question": "pant", "ambiguity_type": "SAME_DIMENSION", "options": mock_options}
        )
        
        # User B (EMP002) in Session 42 attempts to resume with "1"
        user_b = {"employee_id": "EMP002", "company_id": "COMPANY001", "role": "ANALYST"}
        
        # Mock database fetch for session validation for User B
        mock_conn.execute.return_value.fetchone.return_value = create_mock_session_row(42, "EMP002", "COMPANY001")
        
        response = app.ask_question(
            question="1",
            session_id=42,
            request=self.mock_request,
            user=user_b
        )
        
        # Should NOT use EMP001's clarification and instead process "1" as a brand new question, returning a JSONResponse (blocking)
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 400)
        
        # Session B (43) attempts to resume User A's state in Session 42
        mock_conn.execute.return_value.fetchone.return_value = create_mock_session_row(43, "EMP001", "COMPANY001")
        
        response_sess_b = app.ask_question(
            question="1",
            session_id=43,
            request=self.mock_request,
            user=self.user
        )
        
        # Since Session 43 does not have pending clarification (only 42 does), it processes as new query, returning a JSONResponse
        self.assertIsInstance(response_sess_b, JSONResponse)
        self.assertEqual(response_sess_b.status_code, 400)

    # ----------------------------------------------------
    # 4. State Lifecycle transitions
    # ----------------------------------------------------
    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_state_lifecycle_valid_cleared(self, mock_gen_sql, mock_classify):
        """Verify: valid selection -> clears state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_options = {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                  "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"}
        }
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": mock_options})
        mock_gen_sql.return_value = {"success": True, "sql_query": "SELECT 1", "usage": None, "semantic_result": {}, "runtime_context": {}}
        
        app.ask_question(question="1", session_id=42, request=self.mock_request, user=self.user)
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    @patch("app.route_question")
    def test_state_lifecycle_invalid_preserved(self, mock_classify):
        """Verify: invalid selection -> preserves state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_options = {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                  "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"}
        }
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": mock_options})
        
        app.ask_question(question="999", session_id=42, request=self.mock_request, user=self.user)
        self.assertIsNotNone(get_pending_clarification("EMP001", "42"))

    @patch("app.route_question")
    def test_state_lifecycle_ambiguous_preserved(self, mock_classify):
        """Verify: ambiguous selection -> preserves state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_options = {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                  "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"},
            "2": {"option_id": 2, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                  "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"}
        }
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": mock_options})
        
        app.ask_question(question="linen pant", session_id=42, request=self.mock_request, user=self.user)
        self.assertIsNotNone(get_pending_clarification("EMP001", "42"))

    @patch("app.route_question")
    @patch("semantic.semantic_resolver.SemanticResolver.resolve")
    def test_state_lifecycle_intent_shift_cleared(self, mock_resolve, mock_classify):
        """Verify: intent shift -> clears state."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        mock_options = {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                  "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"}
        }
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": mock_options})
        
        # Mock resolve to indicate new question has semantic content
        mock_resolve.return_value = {
            "metrics": ["Sales"], "dimensions": [], "metric_objects": [{"type": "metric"}],
            "dimension_objects": [], "value_matches": []
        }
        
        app.ask_question(question="show sales", session_id=42, request=self.mock_request, user=self.user)
        self.assertIsNone(get_pending_clarification("EMP001", "42"))

    def test_state_lifecycle_ttl_expiry(self):
        """Verify: TTL expiry -> state becomes unusable."""
        mock_options = {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201,
                  "table_name": "Products", "column_name": "Brand", "normalized_value": "linen pant"}
        }
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": mock_options})
        
        # Override timestamp to 301 seconds ago
        pending_clarification_store[("EMP001", "42")]["timestamp"] = time.time() - 301
        
        state = get_pending_clarification("EMP001", "42")
        self.assertIsNone(state)

    # ----------------------------------------------------
    # 5. SQL Generation Boundary Proofs
    # ----------------------------------------------------
    @patch("app.route_question")
    @patch("semantic.semantic_resolver.SemanticResolver.resolve")
    @patch("app.generate_sql_query")
    def test_sql_generation_blocking_and_continuation(self, mock_gen_sql, mock_resolve, mock_classify):
        """Verify exact SQL generation boundaries:
        - STRONG_AMBIGUITY does NOT trigger SQL generation connect/execution.
        - Valid selection triggers generate_sql_query once.
        - Invalid/Ambiguous choice does NOT call generate_sql_query.
        """
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        # 1. STRONG_AMBIGUITY (via Mock resolver showing ambiguity)
        m1 = MatchResult(
            matched=True, value="LINEN PANT", normalized_value="linen pant", confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
            reason="test", dimension_id=201, business_name="Brand", table_name="Products", column_name="Brand"
        )
        c1 = AmbiguityChoice(result=m1, actual_query_coverage=1, matched_query_tokens=["pant"])
        mock_resolve.return_value = {
            "metrics": [], "dimensions": [], "metric_objects": [], "dimension_objects": [],
            "value_matches": [
                {"dimension_id": 201, "business_name": "Brand", "table_name": "Products", "column_name": "Brand", "value": "LINEN PANT"}
            ],
            "ambiguity_result": SemanticResolutionResult(status=ResolutionStatus.STRONG_AMBIGUITY, candidates=[c1, c1])
        }
        
        from core.exceptions import AmbiguityException
        mock_gen_sql.return_value = AmbiguityException("Ambiguous query", details={"original_question": "pant", "options": []}).to_dict()
        
        app.ask_question(question="pant", session_id=42, request=self.mock_request, user=self.user)
        
        # 2. Invalid Selection
        mock_options = {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201}
        }
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": mock_options})
        mock_gen_sql.reset_mock()
        mock_resolve.return_value = {
            "metrics": [], "dimensions": [], "metric_objects": [], "dimension_objects": [], "value_matches": []
        }
        
        app.ask_question(question="999", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_not_called()
        
        # 3. Ambiguous Selection
        set_pending_clarification("EMP001", "42", {"original_question": "pant", "options": {
            "1": {"option_id": 1, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201},
            "2": {"option_id": 2, "value": "LINEN PANT", "dimension": "Brand", "dimension_id": 201}
        }})
        mock_gen_sql.reset_mock()
        mock_resolve.return_value = {
            "metrics": [], "dimensions": [], "metric_objects": [], "dimension_objects": [], "value_matches": []
        }
        
        app.ask_question(question="linen pant", session_id=42, request=self.mock_request, user=self.user)
        mock_gen_sql.assert_not_called()

    # ----------------------------------------------------
    # 6. Company Isolation & Security Revalidation
    # ----------------------------------------------------
    def test_company_isolation(self):
        """Verify that a user from a different company is blocked from accessing the chat session."""
        # Setup session row for session 42 belonging to COMPANY001
        mock_conn.execute.return_value.fetchone.return_value = create_mock_session_row(42, "EMP001", "COMPANY001")
        
        # User from COMPANY002 tries to access Session 42
        user_c = {
            "employee_id": "EMP003",
            "company_id": "COMPANY002",
            "role": "ANALYST"
        }
        
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            app.ask_question(
                question="1",
                session_id=42,
                request=self.mock_request,
                user=user_c
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("chat session belongs to another company", ctx.exception.detail)

    @patch("app.route_question")
    def test_security_revalidation_cls(self, mock_classify):
        """Verify that selecting a candidate that references a forbidden column raises CLS block."""
        mock_classify.return_value = RoutingDecision(destination=Destination.ANALYTICAL, reason="test", method="keyword")
        
        # Mock a restricted column name for CLS check
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

if __name__ == "__main__":
    unittest.main()
