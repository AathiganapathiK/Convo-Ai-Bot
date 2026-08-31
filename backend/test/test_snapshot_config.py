"""
Gate 2 Step 11a - the configured snapshot bindings.

The point of these tests is equivalence. Step 11a moved five column names out
of a hardcoded dictionary in the query planner and into the database, and the
whole claim was that nothing about the answers changes - only where the values
come from. That claim is worth holding onto, because the next person to touch
this will not remember it.
"""

import unittest

from semantic.temporal.snapshot_config import (
    DEFAULT_BINDINGS,
    DEFAULT_MEASURE_COLUMNS,
    SnapshotBinding,
    SnapshotConfig,
    SnapshotConfigLoader,
)


def _sales_config() -> SnapshotConfig:
    """The eleven bindings that tools/seed_semantic_config.py writes."""
    rows = [
        (0, "VALUE", "TO_DATE", "CY"),
        (1, "VALUE", "FULL", "PY"),
        (1, "VALUE", "TO_DATE", "PYTD"),
        (2, "VALUE", "FULL", "PPY"),
        (3, "VALUE", "FULL", "PPPY"),
        (4, "VALUE", "FULL", "PPPPY"),
        (0, "QUANTITY", "TO_DATE", "CYQ"),
        (1, "QUANTITY", "FULL", "PYQ"),
        (2, "QUANTITY", "FULL", "PPYQ"),
        (3, "QUANTITY", "FULL", "PPPYQ"),
        (4, "QUANTITY", "FULL", "PPPPYQ"),
    ]
    return SnapshotConfig(
        table_name="QB_MDJMD_SALES_5YRS_SUMMARY",
        bindings=[SnapshotBinding(*row) for row in rows],
        month_column="InvMonth",
        month_sort_column="InvMonth",
        fiscal_year_start_month=4,
        is_configured=True,
    )


class TestLegacyEquivalence(unittest.TestCase):
    """Without a connection, the behaviour must be what it was before Step 11a."""

    def setUp(self):
        self.config = SnapshotConfigLoader.for_connection(None)

    def test_no_connection_is_reported_as_unconfigured(self):
        # The planner surfaces this as an assumption, so it must not claim to
        # be configuration when it is a fallback.
        self.assertFalse(self.config.is_configured)

    def test_value_mapping_matches_the_old_dictionary(self):
        self.assertEqual(self.config.offset_to_column("VALUE"), DEFAULT_BINDINGS)

    def test_resolvable_columns_match_the_old_hardcoded_set(self):
        # This set decides which metrics get their period chosen for them.
        # If it drifts, queries silently change shape.
        self.assertEqual(self.config.resolvable_columns, DEFAULT_MEASURE_COLUMNS)

    def test_quantity_columns_keep_distinct_offsets(self):
        # Regression: parking them all on one offset collapsed five columns to
        # one, and four of them quietly stopped being treated as period columns.
        self.assertEqual(
            self.config.offset_to_column("QUANTITY"),
            {0: "CYQ", 1: "PYQ", 2: "PPYQ", 3: "PPPYQ", 4: "PPPPYQ"},
        )


class TestConfiguredBindings(unittest.TestCase):
    """The real eleven-binding configuration."""

    def setUp(self):
        self.config = _sales_config()

    def test_flat_mapping_is_unchanged_by_the_extra_bindings(self):
        # PYTD, CYQ and the rest are configured, but the flat mapping the old
        # consumers read must still look exactly like the old dictionary.
        self.assertEqual(self.config.offset_to_column("VALUE"), DEFAULT_BINDINGS)

    def test_full_wins_over_to_date_by_default(self):
        # "Last year's sales" means the whole year.
        self.assertEqual(self.config.column_for_offset(1), "PY")

    def test_to_date_is_reachable_when_asked_for(self):
        # What Step 11b will request. If this breaks, 11b cannot be built.
        self.assertEqual(
            self.config.column_for_offset(1, "VALUE", "TO_DATE"), "PYTD"
        )

    def test_current_period_resolves_even_though_it_is_to_date_only(self):
        # Offset 0 has no FULL row - the year is still running - so the
        # fallback to TO_DATE has to work or "this year" resolves to nothing.
        self.assertEqual(self.config.column_for_offset(0), "CY")

    def test_quantity_is_addressed_separately_from_value(self):
        self.assertEqual(self.config.column_for_offset(0, "QUANTITY"), "CYQ")
        self.assertEqual(self.config.column_for_offset(1, "QUANTITY"), "PYQ")

    def test_missing_combination_returns_none_rather_than_guessing(self):
        # There is no to-date column for two years ago, and inventing one would
        # mean comparing a partial period against a full one.
        self.assertIsNone(self.config.column_for_offset(2, "VALUE", "TO_DATE"))
        self.assertIsNone(self.config.column_for_offset(9))

    def test_pytd_is_configured_but_not_resolvable_yet(self):
        # The distinction Step 11a turns on: PYTD is real configuration, but
        # nothing can ask for it until 11b, so the planner must not treat a
        # metric on PYTD as one whose period it should choose.
        self.assertIn("PYTD", self.config.measure_columns)
        self.assertNotIn("PYTD", self.config.resolvable_columns)


class TestComparisonScope(unittest.TestCase):
    """
    Gate 2 Step 11b - the rule that stops one question having two answers.

    On the live data: CY = 9,861,268,495 over five months, PY = 26,418,264,939
    over twelve, PYTD = 8,615,674,009 over the matching five. CY against PY
    reads -62.7%. CY against PYTD reads +14.5%. Same data, opposite stories.
    """

    def setUp(self):
        self.config = _sales_config()

    def test_current_versus_last_year_uses_the_to_date_column(self):
        columns, warnings = self.config.comparison_columns([0, 1])

        self.assertEqual(columns, ["CY", "PYTD"])
        self.assertEqual(warnings, [])

    def test_comparison_between_two_complete_years_uses_full_columns(self):
        # Neither period is still running, so full years are like for like and
        # forcing to-date here would be the opposite mistake.
        columns, warnings = self.config.comparison_columns([2, 3])

        self.assertEqual(columns, ["PPY", "PPPY"])
        self.assertEqual(warnings, [])

    def test_missing_to_date_column_falls_back_but_says_so(self):
        # There is no to-date column for two years ago. The comparison is still
        # answered, but the caveat must travel with it.
        columns, warnings = self.config.comparison_columns([0, 2])

        self.assertEqual(columns, ["CY", "PPY"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("overstated", warnings[0])

    def test_quantity_comparison_is_resolved_independently(self):
        columns, _ = self.config.comparison_columns([0, 1], "QUANTITY")

        self.assertEqual(columns, ["CYQ", "PYQ"])

    def test_unresolvable_period_yields_no_columns(self):
        # A caller must be able to tell "cannot answer" from "partial answer".
        columns, _ = self.config.comparison_columns([0, 9])

        self.assertEqual(columns, [])

    def test_standalone_last_year_is_untouched_by_the_comparison_rule(self):
        # Regression guard. "What were last year's sales?" means the whole
        # year; only a comparison against the running year narrows it.
        self.assertEqual(self.config.column_for_offset(1), "PY")


class TestCapabilityWiring(unittest.TestCase):

    def test_discover_capability_carries_both_shapes(self):
        from semantic.temporal.resolver import TimeStrategyResolver

        capability = TimeStrategyResolver()._discover_capability(None)

        # The old flat contract, still spoken for existing consumers.
        self.assertEqual(capability.snapshot_mapping, DEFAULT_BINDINGS)
        # The new scope-aware detail, carried alongside.
        self.assertTrue(capability.snapshot_bindings)
        # Left empty on purpose - see _discover_capability's docstring.
        self.assertEqual(capability.date_columns, [])


if __name__ == "__main__":
    unittest.main()
