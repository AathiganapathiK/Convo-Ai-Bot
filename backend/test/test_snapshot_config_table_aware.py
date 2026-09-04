"""
Gate 3 Step 7a - SnapshotConfigLoader.for_table().

`for_connection()` answers "what is the snapshot table on this connection?" and
its loader settles that with SELECT TOP 1 ... ORDER BY table_name. With more
than one SNAPSHOT table configured, one wins alphabetically and the rest are
invisible - so a metric on any other snapshot table is measured against the
wrong table's period columns. Configuration is per table; this is the per-table
read.

These tests stub the database access rather than requiring a live connection,
so they run anywhere. Run with PYTHONPATH=backend:

    python backend/test/test_snapshot_config_table_aware.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.temporal.snapshot_config import (  # noqa: E402
    DEFAULT_BINDINGS,
    SnapshotConfig,
    SnapshotConfigLoader,
)

CONN = "conn-1"
SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
SECOND_SNAPSHOT = "AB_SECOND_SNAPSHOT_SUMMARY"   # sorts BEFORE Sales - the TOP 1 trap
DATE_TABLE = "PBI_OUTSTANDING_ENES_SUMMARY"

# What the stubbed database holds: two SNAPSHOT tables and one DATE_COLUMN.
TABLE_CONFIG = {
    SALES: ("SNAPSHOT", "InvMonth", "InvMonth", 4),
    SECOND_SNAPSHOT: ("SNAPSHOT", "PeriodMonth", "PeriodMonth", 1),
    DATE_TABLE: ("DATE_COLUMN", "Docdate", None, 4),
}
MAPPINGS = {
    SALES: [(0, "VALUE", "TO_DATE", "CY"), (1, "VALUE", "FULL", "PY")],
    SECOND_SNAPSHOT: [(0, "VALUE", "TO_DATE", "THIS_PERIOD"),
                      (1, "VALUE", "FULL", "LAST_PERIOD")],
}


def fake_load(cls, connection_id, table_name=None):
    """Stands in for _load(), reproducing its contract without a database."""
    if table_name:
        row = TABLE_CONFIG.get(table_name)
        if not row or row[0] != "SNAPSHOT":
            return SnapshotConfig()
        resolved_table = table_name
    else:
        snapshots = sorted(t for t, r in TABLE_CONFIG.items() if r[0] == "SNAPSHOT")
        if not snapshots:
            return SnapshotConfig()
        resolved_table = snapshots[0]          # the TOP 1 ... ORDER BY behaviour
        row = TABLE_CONFIG[resolved_table]

    from semantic.temporal.snapshot_config import SnapshotBinding
    bindings = [
        SnapshotBinding(period_offset=o, measure_kind=k,
                        period_scope=s, column_name=c)
        for o, k, s, c in MAPPINGS.get(resolved_table, [])
    ]
    return SnapshotConfig(
        table_name=resolved_table,
        bindings=bindings,
        month_column=row[1],
        month_sort_column=row[2],
        fiscal_year_start_month=row[3] or 4,
        is_configured=bool(bindings),
    )


class TableAwareBase(unittest.TestCase):
    def setUp(self):
        SnapshotConfigLoader.invalidate(None)
        self._real_load = SnapshotConfigLoader._load
        SnapshotConfigLoader._load = classmethod(fake_load)

    def tearDown(self):
        SnapshotConfigLoader._load = self._real_load
        SnapshotConfigLoader.invalidate(None)


class TestPerTableResolution(TableAwareBase):

    def test_each_snapshot_table_returns_its_own_bindings(self):
        """The defect TOP 1 caused: only one snapshot table was ever visible."""
        sales = SnapshotConfigLoader.for_table(CONN, SALES)
        second = SnapshotConfigLoader.for_table(CONN, SECOND_SNAPSHOT)

        self.assertEqual(sales.table_name, SALES)
        self.assertEqual(sales.column_for_offset(0), "CY")
        self.assertEqual(second.table_name, SECOND_SNAPSHOT)
        self.assertEqual(second.column_for_offset(0), "THIS_PERIOD")
        self.assertNotEqual(sales.column_for_offset(0), second.column_for_offset(0))

    def test_the_alphabetically_later_table_is_no_longer_shadowed(self):
        # SECOND_SNAPSHOT sorts first, so under TOP 1 it is what for_connection
        # returns and Sales was unreachable per-table.
        self.assertEqual(
            SnapshotConfigLoader.for_connection(CONN).table_name, SECOND_SNAPSHOT)
        self.assertEqual(
            SnapshotConfigLoader.for_table(CONN, SALES).table_name, SALES)


class TestUnconfiguredTablesAreNotGivenLegacyBindings(TableAwareBase):

    def test_date_column_table_is_unconfigured(self):
        config = SnapshotConfigLoader.for_table(CONN, DATE_TABLE)
        self.assertFalse(config.is_configured)
        self.assertIsNone(config.table_name)
        self.assertEqual(config.bindings, [])
        self.assertIsNone(config.column_for_offset(0))

    def test_date_column_table_does_not_get_the_legacy_sales_columns(self):
        config = SnapshotConfigLoader.for_table(CONN, DATE_TABLE)
        self.assertNotIn("CY", config.measure_columns)
        self.assertNotEqual(config.offset_to_column("VALUE"), DEFAULT_BINDINGS)

    def test_unknown_table_is_unconfigured_and_does_not_raise(self):
        config = SnapshotConfigLoader.for_table(CONN, "NO_SUCH_TABLE")
        self.assertFalse(config.is_configured)
        self.assertIsNone(config.table_name)

    def test_missing_arguments_are_unconfigured(self):
        self.assertFalse(SnapshotConfigLoader.for_table(None, SALES).is_configured)
        self.assertFalse(SnapshotConfigLoader.for_table(CONN, None).is_configured)
        self.assertFalse(SnapshotConfigLoader.for_table(None, None).is_configured)

    def test_a_load_failure_is_unconfigured_rather_than_legacy(self):
        def boom(cls, connection_id, table_name=None):
            raise RuntimeError("database unavailable")

        SnapshotConfigLoader._load = classmethod(boom)
        config = SnapshotConfigLoader.for_table(CONN, SALES)
        self.assertFalse(config.is_configured)
        self.assertEqual(config.bindings, [])


class TestForConnectionUnchanged(TableAwareBase):

    def test_for_connection_still_answers_the_connection_wide_question(self):
        config = SnapshotConfigLoader.for_connection(CONN)
        self.assertTrue(config.is_configured)
        self.assertEqual(config.table_name, SECOND_SNAPSHOT)

    def test_for_connection_still_falls_back_to_legacy_without_a_connection(self):
        config = SnapshotConfigLoader.for_connection(None)
        self.assertEqual(config.offset_to_column("VALUE"), DEFAULT_BINDINGS)
        self.assertFalse(config.is_configured)

    def test_for_connection_falls_back_to_legacy_when_nothing_is_configured(self):
        def empty(cls, connection_id, table_name=None):
            return SnapshotConfig()

        SnapshotConfigLoader._load = classmethod(empty)
        config = SnapshotConfigLoader.for_connection(CONN)
        self.assertEqual(config.offset_to_column("VALUE"), DEFAULT_BINDINGS)


class TestCacheIsolation(TableAwareBase):

    def test_two_tables_do_not_share_a_cache_entry(self):
        a = SnapshotConfigLoader.for_table(CONN, SALES)
        b = SnapshotConfigLoader.for_table(CONN, SECOND_SNAPSHOT)
        self.assertEqual(a.table_name, SALES)
        self.assertEqual(b.table_name, SECOND_SNAPSHOT)
        # served from cache the second time, still distinct
        self.assertEqual(SnapshotConfigLoader.for_table(CONN, SALES).table_name, SALES)

    def test_table_and_connection_entries_do_not_collide(self):
        per_table = SnapshotConfigLoader.for_table(CONN, SALES)
        connection_wide = SnapshotConfigLoader.for_connection(CONN)
        self.assertEqual(per_table.table_name, SALES)
        self.assertEqual(connection_wide.table_name, SECOND_SNAPSHOT)

    def test_invalidate_clears_every_table_entry_for_the_connection(self):
        SnapshotConfigLoader.for_table(CONN, SALES)
        SnapshotConfigLoader.for_table(CONN, SECOND_SNAPSHOT)
        SnapshotConfigLoader.for_connection(CONN)
        self.assertTrue(SnapshotConfigLoader._cache)

        SnapshotConfigLoader.invalidate(CONN)
        self.assertFalse(
            [k for k in SnapshotConfigLoader._cache if k[0] == CONN],
            "invalidate(connection_id) must clear per-table entries too - an "
            "admin save can change which tables are SNAPSHOT at all",
        )

    def test_invalidate_leaves_other_connections_alone(self):
        SnapshotConfigLoader.for_table(CONN, SALES)
        SnapshotConfigLoader.for_table("conn-2", SALES)
        SnapshotConfigLoader.invalidate(CONN)
        self.assertTrue([k for k in SnapshotConfigLoader._cache if k[0] == "conn-2"])


class TestScopeGuards(TableAwareBase):
    """7a must not quietly become 7b or 7c."""

    def test_month_fields_are_carried_but_not_interpreted(self):
        config = SnapshotConfigLoader.for_table(CONN, SALES)
        self.assertEqual(config.month_column, "InvMonth")
        self.assertEqual(config.month_sort_column, "InvMonth")
        self.assertEqual(config.fiscal_year_start_month, 4)

    def test_a_second_table_may_carry_a_different_fiscal_start(self):
        # Proves the field travels per table. Nothing consumes it until 7b.
        self.assertEqual(
            SnapshotConfigLoader.for_table(CONN, SECOND_SNAPSHOT).fiscal_year_start_month, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
