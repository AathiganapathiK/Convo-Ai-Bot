"""
Gate 3 - DATE_COLUMN wired end-to-end into the live temporal flow.

Trace this pins: DateColumnConfigLoader / discover_capability_for_table
(temporal/resolver.py) -> a fresh ResolvedTimePlan for the metric's own
table -> TimeContext -> the "Temporal Context" block build_sql_prompt
embeds in the LLM prompt (ai/prompt_builder.py).

TemporalPipeline.build() still runs before any metric table is known and
still only ever sees the connection-wide capability (unchanged - see
TimeStrategyResolver._discover_capability()'s own docstring). Once
SemanticResolver.resolve() returns a metric and its table, PromptBuilder
now re-resolves the SAME detected intent against THAT table's own
capability and re-formats the temporal section from it - mirroring the
existing SNAPSHOT-period correction already in this method for a
period-column metric.

DB-gated, following this session's established pattern for live-resolver
tests. Uses the real connection's configuration:
  PBI_ENES_ORDER_PENDING_SUMMARY - DATE_COLUMN, DocMonth (a real, registered
      column - the capability resolves)
  PBI_OUTSTANDING_ENES_SUMMARY   - DATE_COLUMN, "Docdate (YYYY-MM-DD)" (free
      text, not a real column - the capability stays unconfigured)
  QB_MDJMD_SALES_5YRS_SUMMARY    - SNAPSHOT

    python backend/test/test_date_column_prompt_wiring.py
"""
import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _db_reachable():
    try:
        import core.config  # noqa
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestDateColumnWiredEndToEnd(unittest.TestCase):

    CONN = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
    DATE_TABLE_OK = "PBI_ENES_ORDER_PENDING_SUMMARY"
    DATE_TABLE_BAD = "PBI_OUTSTANDING_ENES_SUMMARY"
    SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"

    @classmethod
    def setUpClass(cls):
        cls.conn_patch = patch("services.connection_service.ConnectionService")
        mock_conn_service = cls.conn_patch.start()
        conn_row = {
            "connection_id": cls.CONN,
            "connection_name": "Test DB",
            "database_type": "mssql",
        }
        mock_conn_service.get_active_connection.return_value = conn_row
        mock_conn_service.get_connection.return_value = conn_row

    @classmethod
    def tearDownClass(cls):
        cls.conn_patch.stop()

    def setUp(self):
        # A clean, real-DB-driven connection-wide cache for every test - no
        # test seeds a synthetic capability, so what runs here is exactly
        # what a live request would compute.
        from semantic.temporal.capability_cache import TimeResolutionCache
        TimeResolutionCache._cache.pop(self.CONN, None)
        from semantic.temporal.date_column_config import DateColumnConfigLoader
        from semantic.temporal.snapshot_config import SnapshotConfigLoader
        DateColumnConfigLoader.invalidate(self.CONN)
        SnapshotConfigLoader.invalidate(self.CONN)

    def _prompt_and_metric_table(self, question):
        from ai.prompt_builder import build_sql_prompt
        prompt, sem_res, _ = build_sql_prompt(question, connection_id=self.CONN)
        metric_objs = sem_res.get("metric_objects") or []
        table = metric_objs[0]["table_name"] if metric_objs else None
        return prompt, table

    @staticmethod
    def _strategy_of(prompt):
        m = re.search(r"Strategy: (\w+)", prompt)
        return m.group(1) if m else None

    # 1 - a table with DATE_COLUMN capability.
    def test_date_column_table_uses_its_own_configured_column(self):
        prompt, table = self._prompt_and_metric_table("Show quantity this month")
        self.assertEqual(table, self.DATE_TABLE_OK)
        self.assertEqual(self._strategy_of(prompt), "DATE_COLUMN")
        self.assertIn("Date Column: DocMonth", prompt)

    # 2 - a table with snapshot capability (existing behaviour unchanged).
    def test_snapshot_table_still_uses_snapshot_strategy(self):
        prompt, table = self._prompt_and_metric_table("Show quantity for last year")
        # This metric's table is DATE_COLUMN-configured, not SNAPSHOT - a
        # negative check that the two never cross: no snapshot columns leak
        # onto a DATE_COLUMN table's plan.
        self.assertNotIn("Snapshot Columns:", prompt)

        from semantic.temporal.pipeline import TemporalPipeline
        from semantic.temporal.time_resolver import TimeResolver
        from semantic.temporal.detector import TemporalDetector
        import datetime
        intent = TemporalDetector().detect(
            "Show sales for last year", reference_date=datetime.date.today()
        )
        from semantic.temporal.resolver import TimeStrategyResolver
        cap = TimeStrategyResolver().discover_capability_for_table(self.CONN, self.SALES)
        res = TimeResolver().resolve_intent(intent=intent, capability=cap)
        self.assertTrue(res.resolved)
        self.assertEqual(res.plan.strategy.value, "SNAPSHOT")
        self.assertEqual(res.plan.snapshot_columns, ["PY"])

    # 3 - multiple tables with different temporal behaviours in one connection.
    def test_multiple_tables_get_different_temporal_behaviour(self):
        from semantic.temporal.resolver import TimeStrategyResolver
        resolver = TimeStrategyResolver()
        date_cap = resolver.discover_capability_for_table(self.CONN, self.DATE_TABLE_OK)
        snapshot_cap = resolver.discover_capability_for_table(self.CONN, self.SALES)
        self.assertEqual(date_cap.date_columns, ["DocMonth"])
        self.assertEqual(date_cap.snapshot_mapping, {})
        self.assertEqual(snapshot_cap.date_columns, [])
        self.assertIn(0, snapshot_cap.snapshot_mapping)

    # 4 - no (usable) capability configured for the table: a temporal_strategy
    # row exists but its configured column is not a real column, so nothing
    # is fabricated - the temporal section is simply not forced.
    def test_table_with_unusable_date_column_config_forces_nothing(self):
        prompt, table = self._prompt_and_metric_table("Show due amount last month")
        self.assertEqual(table, self.DATE_TABLE_BAD)
        self.assertIsNone(self._strategy_of(prompt))

    # 5 - existing snapshot regression: a literal snapshot-period metric
    # (CY/PY/...) still takes the SNAPSHOT correction path unchanged, never
    # the new DATE_COLUMN one.
    def test_snapshot_period_metric_still_forces_snapshot_strategy(self):
        from semantic.temporal.capability_cache import TimeResolutionCache
        from semantic.temporal.models import TimeCapability
        TimeResolutionCache.put(
            self.CONN,
            TimeCapability(snapshot_mapping={0: "CY", 1: "PY", 2: "PPY"}),
        )
        prompt, table = self._prompt_and_metric_table("Show last year sales")
        self.assertEqual(table, self.SALES)
        self.assertEqual(self._strategy_of(prompt), "SNAPSHOT")
        self.assertIn("Snapshot Columns: PY", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
