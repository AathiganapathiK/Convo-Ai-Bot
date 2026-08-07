import unittest
from unittest.mock import patch, MagicMock
import datetime

from ai.ai_service import generate_sql_query
from semantic.temporal.pipeline import TemporalPipeline
from semantic.temporal.models import TimeResolutionResult, ResolvedTimePlan, BaseTimeIntent
from semantic.temporal.enums import TimeStrategyType, Granularity


class TestTemporalVerificationLogger(unittest.TestCase):
    def setUp(self):
        TemporalPipeline.clear_last_result()

    def tearDown(self):
        TemporalPipeline.clear_last_result()

    @patch("ai.ai_service.build_sql_prompt")
    @patch("ai.ai_service.LLMExecutionService.execute")
    @patch("ai.ai_service.print")
    def test_logger_temporal_detected_no(self, mock_print, mock_execute, mock_build_prompt):
        # Arrange
        mock_build_prompt.return_value = ("mock_prompt", {}, "mock_context")
        
        mock_choice = MagicMock()
        mock_choice.message.content = "SELECT * FROM orders"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_response.model = "gpt-4"
        mock_execute.return_value = mock_response

        # Act
        generate_sql_query("Show me all users")

        # Assert
        # Check that "Temporal Detected : NO" was printed
        printed_messages = [call[0][0] for call in mock_print.call_args_list if call[0]]
        self.assertTrue(any("Temporal Detected : NO" in msg for msg in printed_messages))

    @patch("ai.ai_service.build_sql_prompt")
    @patch("ai.ai_service.LLMExecutionService.execute")
    @patch("ai.ai_service.print")
    @patch("semantic.execution_context.SemanticExecutionContext")
    def test_logger_temporal_detected_yes(self, mock_exec_context, mock_print, mock_execute, mock_build_prompt):
        # Arrange
        mock_build_prompt.return_value = ("mock_prompt", {}, "mock_context")
        
        mock_choice = MagicMock()
        mock_choice.message.content = "SELECT * FROM orders WHERE OrderDate >= '2026-01-01'"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_response.model = "gpt-4"
        mock_execute.return_value = mock_response

        # Mock SemanticExecutionContext
        mock_ctx_instance = MagicMock()
        mock_ctx_instance.connection = {"database_type": "mssql"}
        mock_exec_context.return_value = mock_ctx_instance

        # Populate TemporalPipeline thread-local with production objects
        class MockIntent(BaseTimeIntent):
            pass

        mock_intent = MockIntent()
        mock_intent.reference_date = datetime.date(2026, 8, 7)
        
        mock_plan = ResolvedTimePlan(
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="OrderDate",
            grouping=Granularity.MONTH,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            reference_date=datetime.date(2026, 8, 7)
        )
        
        mock_resolution = TimeResolutionResult(
            resolved=True,
            intent=mock_intent,
            plan=mock_plan
        )

        TemporalPipeline._thread_local.last_intent = mock_intent
        TemporalPipeline._thread_local.last_resolution = mock_resolution

        # Act
        generate_sql_query("Sales in 2026")

        # Assert
        printed_messages = [call[0][0] for call in mock_print.call_args_list if call[0]]
        
        # Verify the logger prints the production resolution details directly
        self.assertTrue(any("Temporal Intent: MockIntent" in msg for msg in printed_messages))
        self.assertTrue(any("Strategy: DATE_COLUMN" in msg for msg in printed_messages))
        self.assertTrue(any("Granularity: MONTH" in msg for msg in printed_messages))
        self.assertTrue(any("Reference Date: 2026-08-07" in msg for msg in printed_messages))
        self.assertTrue(any("Resolved Start Date: 2026-01-01" in msg for msg in printed_messages))
        self.assertTrue(any("Resolved End Date: 2026-12-31" in msg for msg in printed_messages))
        self.assertTrue(any("Expected SQL Fragment:" in msg for msg in printed_messages))
