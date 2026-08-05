import unittest
import datetime
from unittest.mock import MagicMock, patch

from semantic.temporal.models import (
    TimeCapability,
    TimeSettings,
    TimeResolutionResult,
    ResolvedTimePlan,
    LastNYearsIntent,
    CurrentMonthIntent,
    FiscalYTDIntent,
    TimeContext
)
from semantic.temporal.enums import TimeStrategyType, CalendarType, Granularity
from semantic.temporal.time_resolver import TimeResolver
from semantic.temporal.context_builder import TimeContextBuilder
from semantic.temporal.temporal_prompt_formatter import TemporalPromptFormatter
from semantic.temporal.pipeline import TemporalPipeline
from semantic.execution_context import SemanticExecutionContext
from ai.prompt_builder import PromptBuilder


class TestPromptBuilderTemporalUnit(unittest.TestCase):
    """Unit tests with mocked temporal components (Step 9)."""

    def setUp(self):
        self.mock_pipeline = MagicMock(spec=TemporalPipeline)
        self.prompt_builder = PromptBuilder(
            temporal_pipeline=self.mock_pipeline
        )

        # Common mock for connection
        self.conn_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_service = self.conn_patcher.start()
        self.mock_conn_service.get_connection.return_value = {
            "connection_id": "test_conn",
            "connection_name": "Test DB",
            "database_type": "mssql"
        }

        # Common mock for semantic resolver and gate
        self.resolver_patcher = patch("ai.prompt_builder.SemanticResolver")
        self.mock_semantic_resolver = self.resolver_patcher.start()
        self.mock_semantic_resolver.resolve.return_value = {
            "metrics": "None",
            "dimensions": "None",
            "metric_objects": [],
            "dimension_objects": [],
            "value_matches": [],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0, "reason": None}
        }

        self.gate_patcher = patch("ai.prompt_builder.SemanticGate")
        self.mock_semantic_gate = self.gate_patcher.start()
        self.mock_semantic_gate.evaluate.return_value = {"allowed": True, "reason": None}

        # Other mock dependencies to skip DB and sub-services
        self.table_patcher = patch("ai.prompt_builder.RelevantTableResolver")
        self.table_patcher.start()

        self.expander_patcher = patch("ai.prompt_builder.RelationshipExpander")
        self.expander_patcher.start()

        self.rel_context_patcher = patch("ai.prompt_builder.RelationshipContextService")
        self.rel_context_patcher.start()

        self.metadata_patcher = patch("semantic.metadata_resolver.MetadataResolver")
        self.mock_metadata_resolver = self.metadata_patcher.start()
        self.mock_metadata_resolver.resolve.return_value = {"metadata_rules": [], "required_tables": []}

        self.schema_patcher = patch("ai.prompt_builder.RelevantSchemaService")
        self.mock_schema_service = self.schema_patcher.start()
        self.mock_schema_service.get_schema.return_value = "CREATE TABLE Sales (SalesID INT)"

        self.examples_patcher = patch("ai.prompt_builder.QueryExamplesService")
        self.examples_patcher.start()

        self.sem_ctx_patcher = patch("ai.prompt_builder.SemanticContextService")
        self.sem_ctx_patcher.start()

    def tearDown(self):
        self.conn_patcher.stop()
        self.resolver_patcher.stop()
        self.gate_patcher.stop()
        self.table_patcher.stop()
        self.expander_patcher.stop()
        self.rel_context_patcher.stop()
        self.metadata_patcher.stop()
        self.schema_patcher.stop()
        self.examples_patcher.stop()
        self.sem_ctx_patcher.stop()

    def test_snapshot_scenario(self):
        self.mock_pipeline.build.return_value = (
            "\n===========================================================\n"
            "TEMPORAL CONTEXT\n"
            "===========================================================\n\n"
            "Temporal Context:\n"
            "Intent: LastNYearsIntent\n"
            "Strategy: SNAPSHOT\n"
            "Snapshot Columns: CY, PY, PPY, PPPY, PPPPY\n"
            "Grouping: YEAR\n"
        )

        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Past 5 years sales",
            connection_id="test_conn"
        )

        self.assertIn("TEMPORAL CONTEXT", prompt)
        self.assertIn("Snapshot Columns: CY, PY, PPY, PPPY, PPPPY", prompt)
        self.assertIn("Strategy: SNAPSHOT", prompt)

    def test_date_column_scenario(self):
        self.mock_pipeline.build.return_value = (
            "\n===========================================================\n"
            "TEMPORAL CONTEXT\n"
            "===========================================================\n\n"
            "Temporal Context:\n"
            "Intent: CurrentMonthIntent\n"
            "Strategy: DATE_COLUMN\n"
            "Date Column: OrderDate\n"
            "Start Date: 2026-08-01\n"
            "End Date: 2026-08-05\n"
            "Grouping: DAY\n"
        )

        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Current Month Sales",
            connection_id="test_conn"
        )

        self.assertIn("TEMPORAL CONTEXT", prompt)
        self.assertIn("Start Date: 2026-08-01", prompt)
        self.assertIn("End Date: 2026-08-05", prompt)
        self.assertIn("Strategy: DATE_COLUMN", prompt)

    def test_fiscal_scenario(self):
        self.mock_pipeline.build.return_value = (
            "\n===========================================================\n"
            "TEMPORAL CONTEXT\n"
            "===========================================================\n\n"
            "Temporal Context:\n"
            "Intent: FiscalYTDIntent\n"
            "Strategy: DATE_COLUMN\n"
            "Calendar Type: FISCAL\n"
            "Financial Year Start Month: 4\n"
            "Timezone: Asia/Kolkata\n"
        )

        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="FYTD Revenue",
            connection_id="test_conn"
        )

        self.assertIn("Calendar Type: FISCAL", prompt)
        self.assertIn("Financial Year Start Month: 4", prompt)

    def test_partial_scenario(self):
        self.mock_pipeline.build.return_value = (
            "\n===========================================================\n"
            "TEMPORAL CONTEXT\n"
            "===========================================================\n\n"
            "Temporal Context:\n"
            "Intent: LastNYearsIntent\n"
            "Strategy: SNAPSHOT\n"
            "Warning: Requested period exceeds available data.\n"
            "- only 2 years available\n"
        )

        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Past 5 years sales with partial history",
            connection_id="test_conn"
        )

        self.assertIn("Warning: Requested period exceeds available data.", prompt)

    def test_no_temporal_intent_scenario(self):
        self.mock_pipeline.build.return_value = ""

        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="List all products",
            connection_id="test_conn"
        )

        self.assertNotIn("TEMPORAL CONTEXT", prompt)


class TestPromptBuilderTemporalIntegration(unittest.TestCase):
    """End-to-End integration testing for the temporal prompt pipeline (Step 10)."""

    def setUp(self):
        self.prompt_builder = PromptBuilder()
        self.ref_date = datetime.date(2026, 8, 5)

        # Setup standard patches to skip actual DB schema tables & semantic database lookups
        self.conn_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_service = self.conn_patcher.start()
        self.mock_conn_service.get_connection.return_value = {
            "connection_id": "test_conn",
            "connection_name": "Test DB",
            "database_type": "mssql"
        }

        self.resolver_patcher = patch("ai.prompt_builder.SemanticResolver")
        self.mock_semantic_resolver = self.resolver_patcher.start()
        self.mock_semantic_resolver.resolve.return_value = {
            "metrics": "None",
            "dimensions": "None",
            "metric_objects": [],
            "dimension_objects": [],
            "value_matches": [],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0, "reason": None}
        }

        self.gate_patcher = patch("ai.prompt_builder.SemanticGate")
        self.mock_semantic_gate = self.gate_patcher.start()
        self.mock_semantic_gate.evaluate.return_value = {"allowed": True, "reason": None}

        self.table_patcher = patch("ai.prompt_builder.RelevantTableResolver")
        self.table_patcher.start()

        self.expander_patcher = patch("ai.prompt_builder.RelationshipExpander")
        self.expander_patcher.start()

        self.rel_context_patcher = patch("ai.prompt_builder.RelationshipContextService")
        self.rel_context_patcher.start()

        self.metadata_patcher = patch("semantic.metadata_resolver.MetadataResolver")
        self.mock_metadata_resolver = self.metadata_patcher.start()
        self.mock_metadata_resolver.resolve.return_value = {"metadata_rules": [], "required_tables": []}

        self.schema_patcher = patch("ai.prompt_builder.RelevantSchemaService")
        self.mock_schema_service = self.schema_patcher.start()
        self.mock_schema_service.get_schema.return_value = "CREATE TABLE Sales (SalesID INT)"

        self.examples_patcher = patch("ai.prompt_builder.QueryExamplesService")
        self.examples_patcher.start()

        self.sem_ctx_patcher = patch("ai.prompt_builder.SemanticContextService")
        self.sem_ctx_patcher.start()

        # Cache capability under "test_conn"
        from semantic.temporal.capability_cache import TimeResolutionCache
        self.capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY", 3: "PPPY", 4: "PPPPY"}
        )
        TimeResolutionCache.put("test_conn", self.capability)

    def tearDown(self):
        from semantic.temporal.capability_cache import TimeResolutionCache
        TimeResolutionCache.clear()
        
        self.conn_patcher.stop()
        self.resolver_patcher.stop()
        self.gate_patcher.stop()
        self.table_patcher.stop()
        self.expander_patcher.stop()
        self.rel_context_patcher.stop()
        self.metadata_patcher.stop()
        self.schema_patcher.stop()
        self.examples_patcher.stop()
        self.sem_ctx_patcher.stop()

    def test_full_pipeline_snapshot(self):
        # We pass a settings object to configure financial month and calendar type
        settings = TimeSettings(
            default_calendar=CalendarType.CALENDAR,
            financial_year_start_month=1
        )

        # Mock reference date inside TimeResolver.resolve by patching datetime/date calculations 
        # or passing custom settings.
        original_resolve = self.prompt_builder.temporal_pipeline.time_resolver.resolve
        
        def mock_resolve(*args, **kwargs):
            kwargs["reference_date"] = self.ref_date
            return original_resolve(*args, **kwargs)
            
        with patch.object(self.prompt_builder.temporal_pipeline.time_resolver, "resolve", side_effect=mock_resolve):
            prompt, _, _ = self.prompt_builder.build_sql_prompt(
                question="Show sales for the past 5 years",
                connection_id="test_conn",
                settings=settings
            )

        self.assertIn("TEMPORAL CONTEXT", prompt)
        self.assertIn("Intent: LastNYearsIntent", prompt)
        self.assertIn("Strategy: SNAPSHOT", prompt)
        self.assertIn("Snapshot Columns: CY, PY, PPY, PPPY, PPPPY", prompt)
        self.assertIn("Grouping: YEAR", prompt)
        self.assertIn("Calendar Type: CALENDAR", prompt)


if __name__ == "__main__":
    unittest.main()
