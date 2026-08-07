import unittest
from unittest.mock import MagicMock, patch
import datetime

from semantic.temporal.models import TimeCapability, TimeSettings, TimeResolutionResult, ResolvedTimePlan
from semantic.temporal.enums import TimeStrategyType, CalendarType, Granularity
from semantic.temporal.exceptions import StrategyResolutionError
from semantic.temporal.pipeline import TemporalPipeline
from semantic.execution_context import SemanticExecutionContext


class TestTemporalPipeline(unittest.TestCase):
    def test_pipeline_fast_bypass_no_intent(self):
        # Arrange
        mock_detector = MagicMock()
        mock_detector.detect.return_value = None
        
        mock_resolver = MagicMock()
        pipeline = TemporalPipeline(detector=mock_detector, time_resolver=mock_resolver)

        # Act
        result = pipeline.build("Show all users")

        # Assert
        self.assertEqual(result, "")
        mock_detector.detect.assert_called_once_with("Show all users", reference_date=None)
        mock_resolver.resolve.assert_not_called()

    def test_pipeline_normal_flow(self):
        # Arrange
        mock_intent = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_intent
        
        mock_plan = ResolvedTimePlan(
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY"]
        )
        mock_resolution = TimeResolutionResult(resolved=True, intent=mock_intent, plan=mock_plan)
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = mock_resolution
        
        pipeline = TemporalPipeline(detector=mock_detector, time_resolver=mock_resolver)

        # Act
        result = pipeline.build("Sales in the last 2 years", connection_id="test_conn")

        # Assert
        self.assertIn("TEMPORAL CONTEXT", result)
        self.assertIn("Strategy: SNAPSHOT", result)
        self.assertIn("Snapshot Columns: CY, PY", result)

    def test_pipeline_exception_handling_expected(self):
        # Arrange
        mock_intent = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_intent
        
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = StrategyResolutionError("Resolution failed")
        
        pipeline = TemporalPipeline(detector=mock_detector, time_resolver=mock_resolver)

        # Act
        result = pipeline.build("invalid time question")

        # Assert
        self.assertEqual(result, "")  # Caught StrategyResolutionError and degraded gracefully

    def test_pipeline_exception_handling_unexpected_propagates(self):
        # Arrange
        mock_intent = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_intent
        
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = KeyError("unexpected bug")
        
        pipeline = TemporalPipeline(detector=mock_detector, time_resolver=mock_resolver)

        # Act & Assert
        with self.assertRaises(KeyError):
            pipeline.build("buggy question")

    def test_formatter_styles(self):
        # Arrange
        mock_intent = MagicMock()
        mock_intent.__class__.__name__ = "CustomIntent"
        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_intent
        
        mock_plan = ResolvedTimePlan(
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="OrderDate",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            grouping=Granularity.MONTH
        )
        mock_resolution = TimeResolutionResult(resolved=True, intent=mock_intent, plan=mock_plan)
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = mock_resolution
        
        pipeline = TemporalPipeline(detector=mock_detector, time_resolver=mock_resolver)

        # Test llm style (default)
        res_llm = pipeline.build("q", style="llm")
        self.assertIn("TEMPORAL CONTEXT", res_llm)
        self.assertIn("Date Column: OrderDate", res_llm)

        # Test json style
        res_json = pipeline.build("q", style="json")
        self.assertIn('"strategy": "DATE_COLUMN"', res_json)
        self.assertIn('"date_column": "OrderDate"', res_json)

        # Test logs style
        res_logs = pipeline.build("q", style="logs")
        self.assertIn("strategy=DATE_COLUMN", res_logs)

        # Test debug style
        res_debug = pipeline.build("q", style="debug")
        self.assertIn("[DEBUG]", res_debug)
        self.assertIn("Strategy: DATE_COLUMN", res_debug)

    def test_pipeline_thread_local_storage(self):
        # Arrange
        mock_intent = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_intent
        
        mock_plan = ResolvedTimePlan(
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY"]
        )
        mock_resolution = TimeResolutionResult(resolved=True, intent=mock_intent, plan=mock_plan)
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = mock_resolution
        
        pipeline = TemporalPipeline(detector=mock_detector, time_resolver=mock_resolver)

        # Act
        pipeline.build("Sales in the last 2 years")

        # Assert
        self.assertEqual(TemporalPipeline.get_last_intent(), mock_intent)
        self.assertEqual(TemporalPipeline.get_last_resolution(), mock_resolution)

        # Clear
        TemporalPipeline.clear_last_result()
        self.assertIsNone(TemporalPipeline.get_last_intent())
        self.assertIsNone(TemporalPipeline.get_last_resolution())


class TestSemanticExecutionContext(unittest.TestCase):
    @patch("services.connection_service.ConnectionService")
    @patch("services.config_service.ConfigService")
    def test_context_initialization(self, mock_config, mock_conn):
        # Arrange
        mock_conn.get_connection.return_value = {
            "connection_id": "test-uuid",
            "connection_name": "Test Connection",
            "database_type": "mssql"
        }
        mock_config.get_company_config.return_value = {
            "company_id": "company-uuid",
            "company_name": "Ramraj Textiles",
            "timezone": "Asia/Kolkata",
            "financial_year_start_month": 4,
            "week_start_day": 1,
            "default_calendar": "fiscal",
            "locale": "en_IN"
        }

        # Act
        ctx = SemanticExecutionContext(connection_id="test-uuid", company_id="company-uuid")

        # Assert
        self.assertEqual(ctx.connection_id, "test-uuid")
        self.assertEqual(ctx.company_id, "company-uuid")
        self.assertEqual(ctx.settings.financial_year_start_month, 4)
        self.assertEqual(ctx.settings.week_start_day, 1)
        self.assertEqual(ctx.settings.default_calendar, CalendarType.FISCAL)
        self.assertEqual(ctx.settings.timezone, "Asia/Kolkata")
        self.assertEqual(ctx.settings.locale, "en_IN")
