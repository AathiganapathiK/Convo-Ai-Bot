"""
Gate 4 - the /ask integration gap fix.

Pins:
  1. /ask calls route_question(), not the legacy classify_intent(), for the
     initial (non-clarification-resume) routing decision.
  2. Destination.METADATA is answered directly via answer_metadata() - no
     resolver, no generate_sql_query().
  3. SMALL_TALK still behaves exactly as the old GENERAL branch did.
  4. The analytics (ANALYTICAL) path is untouched - it falls through to the
     existing generate_sql_query() flow.
  5. Gate 4's clarification / assumptions_made / unsupported / mode, when
     present on semantic_result["extracted_intent"], are surfaced on the
     successful /ask response.

Follows this test suite's established offline pattern (mock the DB engine
and ConnectionService before importing app, call app.ask_question()
directly). No live DB, no LLM calls - route_question/answer_metadata are
patched so this test is deterministic.

    python -m unittest backend.test.test_gate4_ask_wiring
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

mock_conn = MagicMock()
session_row = MagicMock()
session_row._mapping = {
    "id": 42,
    "employee_id": "EMP001",
    "company_id": "COMPANY001",
}
mock_conn.execute.return_value.fetchone.return_value = session_row

mock_engine = MagicMock()
mock_engine.connect.return_value.__enter__.return_value = mock_conn
mock_engine.begin.return_value.__enter__.return_value = mock_conn

import database
database.engine = mock_engine

import app  # noqa: E402
from ai.intent_classifier import Destination, RoutingDecision  # noqa: E402


class TestAskWiring(unittest.TestCase):

    def setUp(self):
        app.engine = mock_engine
        self.conn_svc_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_svc = self.conn_svc_patcher.start()
        self.mock_conn_svc.get_active_connection.return_value = {
            "connection_id": "CONN001",
            "connection_name": "TestDB",
            "database_type": "mssql",
        }
        self.user = {
            "employee_id": "EMP001",
            "company_id": "COMPANY001",
            "role": "ANALYST",
            "official_email": "test@example.com",
        }
        self.mock_request = MagicMock()
        self.mock_request.client.host = "127.0.0.1"

        from services.conversation_memory import clear_pending_clarification
        clear_pending_clarification("EMP001", "42")

    def tearDown(self):
        self.conn_svc_patcher.stop()
        from services.conversation_memory import clear_pending_clarification
        clear_pending_clarification("EMP001", "42")

    @patch("app.route_question")
    @patch("app.answer_metadata")
    @patch("app.generate_sql_query")
    def test_metadata_destination_calls_answer_metadata_not_resolver(
        self, mock_gen_sql, mock_answer_metadata, mock_route
    ):
        mock_route.return_value = RoutingDecision(
            destination=Destination.METADATA, reason="test", method="keyword"
        )
        mock_answer_metadata.return_value = "You can ask about Sales and City."

        response = app.ask_question(
            question="what can I ask?",
            session_id=42,
            request=self.mock_request,
            user=self.user,
        )

        mock_answer_metadata.assert_called_once()
        mock_gen_sql.assert_not_called()
        self.assertEqual(response["type"], "METADATA")
        self.assertEqual(response["message"], "You can ask about Sales and City.")

    @patch("app.route_question")
    @patch("app.generate_general_response")
    @patch("app.generate_sql_query")
    def test_small_talk_destination_behaves_like_legacy_general(
        self, mock_gen_sql, mock_general, mock_route
    ):
        mock_route.return_value = RoutingDecision(
            destination=Destination.SMALL_TALK, reason="test", method="keyword"
        )
        mock_general.return_value = "Hi there!"

        response = app.ask_question(
            question="hello",
            session_id=42,
            request=self.mock_request,
            user=self.user,
        )

        mock_gen_sql.assert_not_called()
        self.assertEqual(response, {"type": "GENERAL", "message": "Hi there!"})

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_analytical_destination_falls_through_to_sql_generation(
        self, mock_gen_sql, mock_route
    ):
        mock_route.return_value = RoutingDecision(
            destination=Destination.ANALYTICAL, reason="test", method="vocabulary"
        )
        mock_gen_sql.return_value = {
            "success": False,
            "error": {"message": "stopped after routing check"},
        }

        app.ask_question(
            question="show sales",
            session_id=42,
            request=self.mock_request,
            user=self.user,
        )

        mock_gen_sql.assert_called_once()

    @patch("app.route_question")
    @patch("app.generate_sql_query")
    def test_gate4_fields_surface_on_successful_response(self, mock_gen_sql, mock_route):
        mock_route.return_value = RoutingDecision(
            destination=Destination.ANALYTICAL, reason="test", method="vocabulary"
        )
        mock_gen_sql.return_value = {
            "success": True,
            "sql_query": "SELECT 1",
            "usage": None,
            "semantic_result": {
                "extracted_intent": {
                    "mode": "DIAGNOSTIC",
                    "clarification": {"slot": "time_period", "question": "Which period?",
                                       "options": ["this year", "last year"], "reason": "ambiguous"},
                    "assumptions_made": ["Assumed 'sales' means Sales.CY."],
                    "unsupported": ["root-cause analysis"],
                }
            },
            "runtime_context": None,
        }

        with patch("app.SecurityPipeline") as mock_pipeline_cls, \
             patch("app.get_history", return_value=[]), \
             patch("app.validate_sql_query", return_value=(True, "")), \
             patch("app.guard_sql") as mock_guard_sql, \
             patch("app.ConnectionManager") as mock_conn_mgr, \
             patch("app.ground_answer") as mock_ground_answer, \
             patch("app.generate_business_summary",
                   return_value={"summary": "", "usage": None, "sum_time": 0.0, "followups": []}), \
             patch("app.generate_chart_metadata", return_value=(None, None)), \
             patch("app.QueryExamplesService"), \
             patch("app.save_usage"), \
             patch("app.save_query_history"):

            mock_pipeline = MagicMock()
            mock_pipeline.validate_cls.return_value = (True, "")
            mock_pipeline.apply_rls.return_value = ("SELECT 1", {})
            mock_pipeline.apply_cls.return_value = ("SELECT 1", [])
            mock_pipeline_cls.return_value = mock_pipeline

            from ai.guard.enforcement import GuardDecision
            mock_guard_sql.return_value = GuardDecision(sql="SELECT 1", blocked=False)

            from ai.guard.grounding import GroundingDecision
            mock_ground_answer.return_value = GroundingDecision(answer="", blocked=False)

            source_engine = MagicMock()
            source_conn = MagicMock()
            source_conn.execute.return_value.fetchall.return_value = []
            source_conn.execute.return_value.keys.return_value = []
            source_engine.connect.return_value.__enter__.return_value = source_conn
            mock_conn_mgr.source.return_value = source_engine

            response = app.ask_question(
                question="show sales",
                session_id=42,
                request=self.mock_request,
                user=self.user,
            )

        self.assertEqual(response.get("mode"), "DIAGNOSTIC")
        self.assertEqual(
            response.get("assumptions_made"), ["Assumed 'sales' means Sales.CY."]
        )
        self.assertEqual(response.get("unsupported"), ["root-cause analysis"])
        self.assertEqual(response.get("clarification", {}).get("slot"), "time_period")


if __name__ == "__main__":
    unittest.main(verbosity=2)
