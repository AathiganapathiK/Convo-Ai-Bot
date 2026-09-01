"""
Gate 3 P0 - the runtime honours Gate 2 configuration.

Two things are being protected here, and they pull in opposite directions.

The first is that an administrator's exclusion must actually take effect. On the
live database five active dimensions were marked excluded - State1, State2,
State3, KeyLine and createddate - and all five were still being offered to every
question, along with 302 indexed values. "Show sales in TN" produced eleven
candidate dimensions, three of them explicitly switched off.

The second is that the chat feature must not break on a database where migration
004 was never applied. There is no migration runner in this project, so that is
a real deployment state rather than a hypothetical one, and a bare
"AND is_excluded = 0" would raise on every single question rather than degrade.
The tests below pin both behaviours, because a future change that satisfies one
by sacrificing the other would be a regression even though it looks correct.
"""

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from semantic import runtime_config_filter


def _engine_with(dimension_columns: str, metric_columns: str):
    """An in-memory database whose semantic tables have the given columns."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE semantic_dimensions ({dimension_columns})"))
        conn.execute(text(f"CREATE TABLE semantic_metrics ({metric_columns})"))
    return engine


MIGRATED_DIMENSIONS = (
    "dimension_id TEXT, connection_id TEXT, business_name TEXT, "
    "is_active INTEGER, is_excluded INTEGER, is_confirmed INTEGER, "
    "dimension_role TEXT"
)
MIGRATED_METRICS = (
    "metric_id TEXT, connection_id TEXT, business_name TEXT, "
    "is_active INTEGER, is_excluded INTEGER, is_confirmed INTEGER"
)

# What the tables looked like before migration 004.
LEGACY_DIMENSIONS = "dimension_id TEXT, connection_id TEXT, business_name TEXT, is_active INTEGER"
LEGACY_METRICS = "metric_id TEXT, connection_id TEXT, business_name TEXT, is_active INTEGER"


class TestMigratedDatabase(unittest.TestCase):
    """Migration 004 applied: the switches must be honoured."""

    def setUp(self):
        self.engine = _engine_with(MIGRATED_DIMENSIONS, MIGRATED_METRICS)
        self.patcher = patch("semantic.runtime_config_filter.engine", self.engine)
        self.patcher.start()
        runtime_config_filter.reset_cache()

    def tearDown(self):
        self.patcher.stop()
        runtime_config_filter.reset_cache()

    def test_metric_exclusion_is_applied(self):
        self.assertEqual(runtime_config_filter.metric_filter(), "AND is_excluded = 0")

    def test_dimension_exclusion_is_applied(self):
        self.assertIn("is_excluded = 0", runtime_config_filter.dimension_filter())

    def test_internal_role_is_hidden(self):
        # The role's own definition is "exists but is not offered to business
        # users", so leaving it visible would contradict the configuration.
        clause = runtime_config_filter.dimension_filter()
        self.assertIn("INTERNAL", clause)

    def test_null_role_is_kept(self):
        # An unclassified dimension is not an internal one. Most of the live
        # registry has no role set, so dropping NULL would empty the layer.
        self.assertIn("dimension_role IS NULL", runtime_config_filter.dimension_filter())

    def test_alias_is_applied_to_every_column(self):
        clause = runtime_config_filter.dimension_filter("sd")
        self.assertIn("sd.is_excluded", clause)
        self.assertIn("sd.dimension_role", clause)
        self.assertNotIn(" is_excluded", clause.replace("sd.is_excluded", ""))

    def test_role_column_is_selected(self):
        self.assertEqual(
            runtime_config_filter.dimension_role_column(),
            "dimension_role AS dimension_role",
        )

    def test_confirmation_is_not_filtered(self):
        # Deliberate. Fifteen of twenty metrics and thirty-nine of seventy-six
        # dimensions are confirmed; filtering on it would switch off the rest of
        # the semantic layer. Confirmation belongs in confidence scoring.
        self.assertNotIn("is_confirmed", runtime_config_filter.metric_filter())
        self.assertNotIn("is_confirmed", runtime_config_filter.dimension_filter())

    def test_generated_predicates_are_valid_sql(self):
        # A malformed fragment would only surface as a runtime error on a live
        # question, so it is executed here rather than merely string-matched.
        with self.engine.connect() as conn:
            conn.execute(text(
                "SELECT business_name FROM semantic_metrics "
                "WHERE is_active = 1 " + runtime_config_filter.metric_filter()
            ))
            conn.execute(text(
                "SELECT business_name FROM semantic_dimensions sd "
                "WHERE sd.is_active = 1 " + runtime_config_filter.dimension_filter("sd")
            ))

    def test_excluded_rows_are_actually_removed(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO semantic_dimensions VALUES "
                "('1','c','State',1,0,0,NULL),"          # kept
                "('2','c','State1',1,1,0,'GROUPING'),"   # excluded
                "('3','c','Loader',1,0,0,'INTERNAL')"    # internal
            ))

        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT business_name FROM semantic_dimensions sd "
                "WHERE sd.is_active = 1 "
                + runtime_config_filter.dimension_filter("sd")
            )).fetchall()

        self.assertEqual([r[0] for r in rows], ["State"])


class TestUnmigratedDatabase(unittest.TestCase):
    """
    Migration 004 never applied: the query path must still work.

    This is the safety property. Failing here means every question raises.
    """

    def setUp(self):
        self.engine = _engine_with(LEGACY_DIMENSIONS, LEGACY_METRICS)
        self.patcher = patch("semantic.runtime_config_filter.engine", self.engine)
        self.patcher.start()
        runtime_config_filter.reset_cache()

    def tearDown(self):
        self.patcher.stop()
        runtime_config_filter.reset_cache()

    def test_predicates_are_empty_rather_than_invalid(self):
        self.assertEqual(runtime_config_filter.metric_filter(), "")
        self.assertEqual(runtime_config_filter.dimension_filter(), "")
        self.assertEqual(runtime_config_filter.dimension_filter("sd"), "")

    def test_role_column_degrades_to_null_keeping_row_shape(self):
        # Callers index the role positionally, so the column must still be
        # present in the SELECT list or every row read would shift.
        self.assertEqual(
            runtime_config_filter.dimension_role_column(),
            "NULL AS dimension_role",
        )

    def test_queries_still_execute(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO semantic_dimensions VALUES ('1','c','State',1)"
            ))

        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT business_name, "
                + runtime_config_filter.dimension_role_column()
                + " FROM semantic_dimensions sd WHERE sd.is_active = 1 "
                + runtime_config_filter.dimension_filter("sd")
            )).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "State")
        self.assertIsNone(rows[0][1])


class TestProbeFailure(unittest.TestCase):
    """An unreachable database must not take the query path down with it."""

    def tearDown(self):
        runtime_config_filter.reset_cache()

    def test_inspection_failure_degrades_quietly(self):
        runtime_config_filter.reset_cache()
        with patch("semantic.runtime_config_filter.inspect", side_effect=RuntimeError("boom")):
            self.assertEqual(runtime_config_filter.metric_filter(), "")
            self.assertEqual(runtime_config_filter.dimension_filter(), "")


if __name__ == "__main__":
    unittest.main()
