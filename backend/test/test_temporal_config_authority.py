"""
Gate 3 Steps 7b and 7c - configuration that is finally authoritative.

7b - month_column, month_sort_column, fiscal_year_start_month
7c - is_confirmed

The two are tested in separate classes so a failure attributes to one step.
No database: the loader's _load is stubbed, and the dimension registry lookup
is stubbed, exactly as the Step 7a tests do.

    python backend/test/test_temporal_config_authority.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.semantic_plan_builder import SemanticPlanBuilder  # noqa: E402
from semantic.temporal.snapshot_config import (  # noqa: E402
    SnapshotBinding,
    SnapshotConfig,
    SnapshotConfigLoader,
)

CONN = "conn-1"
SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
OUTSTANDING = "PBI_OUTSTANDING_ENES_SUMMARY"

BINDINGS = [
    SnapshotBinding(period_offset=0, measure_kind="VALUE",
                    period_scope="TO_DATE", column_name="CY"),
    SnapshotBinding(period_offset=1, measure_kind="VALUE",
                    period_scope="FULL", column_name="PY"),
]

# The registered dimensions the stubbed registry knows about. Note that
# "Docdate (YYYY-MM-DD)" is deliberately absent: it is what one confirmed row
# on the live connection actually holds in month_column, and it is not a column.
REGISTERED = {
    (SALES.lower(), "invmonth"): {
        "dimension_name": "invmonth", "business_name": "Inv Month",
        "table_name": SALES, "column_name": "InvMonth",
        "semantic_category": "Time", "dimension_role": "TIME_LABEL",
    },
    (SALES.lower(), "docmonth"): {
        "dimension_name": "docmonth", "business_name": "Document Month",
        "table_name": SALES, "column_name": "DocMonth",
        "semantic_category": None, "dimension_role": "TIME_LABEL",
    },
}


def matched_docmonth():
    return {
        "dimension_name": "docmonth", "business_name": "Document Month",
        "table_name": SALES, "column_name": "DocMonth",
        "semantic_category": None, "dimension_role": "TIME_LABEL",
    }


class StubbedBase(unittest.TestCase):
    """Stubs the config loader and the dimension registry."""

    month_column = "InvMonth"
    month_sort_column = "InvMonth"
    fiscal_year_start_month = 4
    configured = True

    def setUp(self):
        SnapshotConfigLoader.invalidate(None)
        SemanticPlanBuilder._month_dimension_cache = {}
        self._real_for_table = SnapshotConfigLoader.for_table
        self._real_registered = SemanticPlanBuilder._registered_dimension

        test = self

        def fake_for_table(cls, connection_id, table_name):
            if table_name != SALES or not test.configured:
                return SnapshotConfig()
            return SnapshotConfig(
                table_name=SALES, bindings=list(BINDINGS),
                month_column=test.month_column,
                month_sort_column=test.month_sort_column,
                fiscal_year_start_month=test.fiscal_year_start_month,
                is_configured=True,
            )

        def fake_registered(cls, connection_id, table_name, column_name):
            if not (connection_id and table_name and column_name):
                return None
            return REGISTERED.get((table_name.lower(), column_name.lower()))

        SnapshotConfigLoader.for_table = classmethod(fake_for_table)
        SemanticPlanBuilder._registered_dimension = classmethod(fake_registered)

    def tearDown(self):
        SnapshotConfigLoader.for_table = self._real_for_table
        SemanticPlanBuilder._registered_dimension = self._real_registered
        SnapshotConfigLoader.invalidate(None)
        SemanticPlanBuilder._month_dimension_cache = {}

    def apply(self, dim=None):
        assumptions = []
        result, order_by = SemanticPlanBuilder._apply_configured_month(
            dim or matched_docmonth(), CONN, assumptions
        )
        return result, order_by, assumptions


# =====================================================================
# 7b
# =====================================================================

class Test7bMonthColumnIsAuthoritative(StubbedBase):

    def test_configured_month_column_replaces_the_matched_one(self):
        dim, _, _ = self.apply()
        self.assertEqual(dim["column_name"], "InvMonth")
        self.assertEqual(dim["business_name"], "Inv Month")

    def test_the_substitution_is_recorded_as_a_plan_assumption(self):
        _, _, assumptions = self.apply()
        self.assertEqual(len(assumptions), 1)
        self.assertIn("Document Month", assumptions[0])
        self.assertIn("Inv Month", assumptions[0])

    def test_a_dimension_already_on_the_configured_column_is_untouched(self):
        already = dict(REGISTERED[(SALES.lower(), "invmonth")])
        dim, _, assumptions = self.apply(already)
        self.assertEqual(dim["column_name"], "InvMonth")
        self.assertEqual(assumptions, [], "no decision was made, so none is claimed")

    def test_a_table_with_no_snapshot_configuration_is_untouched(self):
        dim, order_by, assumptions = self.apply(
            {"dimension_name": "docdate_month", "business_name": "Docdate Month",
             "table_name": OUTSTANDING, "column_name": "Docdate",
             "semantic_category": "TIME_MONTH", "dimension_role": None})
        self.assertEqual(dim["column_name"], "Docdate")
        self.assertIsNone(order_by)
        self.assertEqual(assumptions, [])


class Test7bConfiguredColumnMustBeReal(StubbedBase):
    """The live connection holds month_column = 'Docdate (YYYY-MM-DD)'."""

    def test_a_configured_column_that_is_not_a_dimension_is_ignored(self):
        self.month_column = "Docdate (YYYY-MM-DD)"
        self.month_sort_column = None
        dim, _, assumptions = self.apply()
        self.assertEqual(dim["column_name"], "DocMonth",
                         "must not plan onto a column that does not exist")
        self.assertEqual(assumptions, [])

    def test_confirmation_alone_does_not_make_a_bad_column_usable(self):
        # That row is is_confirmed = 1, so 7c is no protection here.
        self.month_column = "NoSuchColumn"
        dim, _, _ = self.apply()
        self.assertEqual(dim["column_name"], "DocMonth")


class Test7bMonthSortColumn(StubbedBase):

    def test_month_sort_column_is_carried_onto_the_dimension(self):
        _, order_by, _ = self.apply()
        self.assertEqual(order_by, "InvMonth")

    def test_no_sort_column_configured_carries_nothing(self):
        self.month_sort_column = None
        _, order_by, _ = self.apply()
        self.assertIsNone(order_by)

    def test_an_unregistered_sort_column_is_not_carried(self):
        self.month_sort_column = "NoSuchColumn"
        _, order_by, _ = self.apply()
        self.assertIsNone(order_by)

    def test_the_plan_model_accepts_and_defaults_the_field(self):
        from semantic.models.semantic_plan import SemanticDimension
        plain = SemanticDimension(dimension_name="d", business_name="D",
                                  table_name="T", column_name="C")
        self.assertIsNone(plain.order_by_column,
                          "existing construction sites must be unaffected")
        ordered = SemanticDimension(dimension_name="d", business_name="D",
                                    table_name="T", column_name="C",
                                    order_by_column="InvMonth")
        self.assertEqual(ordered.order_by_column, "InvMonth")


class Test7bFiscalYearStartMonth(StubbedBase):

    def test_a_january_year_with_no_sort_column_needs_no_override(self):
        self.fiscal_year_start_month = 1
        self.month_sort_column = None
        dim, order_by, assumptions = self.apply()
        self.assertEqual(dim["column_name"], "DocMonth",
                         "a calendar year sorts correctly on any month column")
        self.assertIsNone(order_by)
        self.assertEqual(assumptions, [])

    def test_a_january_year_with_a_sort_column_still_applies(self):
        self.fiscal_year_start_month = 1
        dim, order_by, _ = self.apply()
        self.assertEqual(dim["column_name"], "InvMonth")
        self.assertEqual(order_by, "InvMonth")

    def test_a_non_january_year_applies(self):
        self.fiscal_year_start_month = 4
        dim, _, _ = self.apply()
        self.assertEqual(dim["column_name"], "InvMonth")

    def test_a_configured_january_is_no_longer_coerced_to_april(self):
        config = SnapshotConfig(fiscal_year_start_month=1)
        self.assertEqual(config.fiscal_year_start_month, 1)


# =====================================================================
# 7c
# =====================================================================

class Test7cOnlyConfirmedConfigurationIsAuthoritative(unittest.TestCase):
    """
    Migration 004: "0 = system suggestion awaiting review... Nothing
    unconfirmed may be treated as authoritative." The queries did not honour it.
    """

    def _sql(self):
        import inspect
        from semantic.temporal import snapshot_config
        return inspect.getsource(snapshot_config.SnapshotConfigLoader._load.__func__)

    def test_the_table_specific_query_filters_on_is_confirmed(self):
        sql = self._sql()
        table_specific = sql.split("else:")[0]
        self.assertIn("AND is_confirmed = 1", table_specific)

    def test_the_connection_wide_query_filters_on_is_confirmed(self):
        sql = self._sql()
        connection_wide = sql.split("else:")[1]
        self.assertIn("AND is_confirmed = 1", connection_wide)

    def test_the_snapshot_mapping_query_filters_on_is_confirmed(self):
        sql = self._sql()
        mapping = sql.split("semantic_snapshot_mapping")[1]
        self.assertIn("AND is_confirmed = 1", mapping)

    def test_every_configuration_read_is_covered(self):
        self.assertEqual(self._sql().count("AND is_confirmed = 1"), 3)

    def test_an_unconfirmed_table_reads_as_unconfigured(self):
        """The safe direction: leave the metric alone, do not guess."""
        SnapshotConfigLoader.invalidate(None)
        real = SnapshotConfigLoader._load

        def only_confirmed(cls, connection_id, table_name=None):
            # Stands in for the WHERE is_confirmed = 1 predicate.
            return SnapshotConfig()

        SnapshotConfigLoader._load = classmethod(only_confirmed)
        try:
            config = SnapshotConfigLoader.for_table(CONN, SALES)
            self.assertFalse(config.is_configured)
            self.assertIsNone(config.column_for_offset(0))
        finally:
            SnapshotConfigLoader._load = real
            SnapshotConfigLoader.invalidate(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
