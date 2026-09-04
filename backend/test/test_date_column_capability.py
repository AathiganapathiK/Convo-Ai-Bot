"""
Gate 3 - table-aware DATE_COLUMN capability.

TimeStrategyResolver._discover_capability() (connection-scoped) deliberately
never populates date_columns. discover_capability_for_table() is the
table-aware counterpart these tests pin: given a specific table, it reads
that table's own DATE_COLUMN configuration (DateColumnConfigLoader) and its
own SNAPSHOT bindings (SnapshotConfigLoader.for_table()) - never another
table's, unlike the connection-wide _discover_capability().

Stubs the database access rather than requiring a live connection, so this
runs anywhere. Run with PYTHONPATH=backend:

    python backend/test/test_date_column_capability.py
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.temporal.date_column_config import DateColumnConfig, DateColumnConfigLoader  # noqa: E402
from semantic.temporal.resolver import TimeStrategyResolver  # noqa: E402
from semantic.temporal.snapshot_config import SnapshotConfig  # noqa: E402

CONN = "conn-date-1"
SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"          # SNAPSHOT-configured
DATE_TABLE_OK = "PBI_ENES_ORDER_PENDING_SUMMARY"     # DATE_COLUMN, real column
DATE_TABLE_BAD = "PBI_OUTSTANDING_ENES_SUMMARY"      # DATE_COLUMN, free-text garbage
UNCONFIGURED_TABLE = "SOME_OTHER_TABLE"

# What the stubbed database holds.
TABLE_CONFIG = {
    DATE_TABLE_OK: ("DATE_COLUMN", "DocMonth"),
    DATE_TABLE_BAD: ("DATE_COLUMN", "Docdate (YYYY-MM-DD)"),  # display text, not a column
}
REGISTERED_COLUMNS = {
    (DATE_TABLE_OK, "docmonth"): {"column_name": "DocMonth"},
}


def fake_date_load(cls, connection_id, table_name):
    row = TABLE_CONFIG.get(table_name)
    if not row or row[0] != "DATE_COLUMN":
        return DateColumnConfig()
    configured_column = row[1]

    registered = REGISTERED_COLUMNS.get((table_name, configured_column.lower()))
    if not registered:
        return DateColumnConfig()

    return DateColumnConfig(
        table_name=table_name, date_column=registered["column_name"], is_configured=True
    )


def fake_snapshot_for_table(cls, connection_id, table_name):
    # Only the SNAPSHOT table in this stub carries bindings - a genuinely
    # table-scoped stub, matching discover_capability_for_table() reading
    # SnapshotConfigLoader.for_table() rather than the connection-wide
    # for_connection().
    if table_name != SALES:
        return SnapshotConfig()
    from semantic.temporal.snapshot_config import SnapshotBinding
    return SnapshotConfig(
        table_name=SALES,
        bindings=[SnapshotBinding(0, "VALUE", "TO_DATE", "CY"),
                  SnapshotBinding(1, "VALUE", "FULL", "PY")],
        is_configured=True,
    )


class TestDateColumnConfigLoader(unittest.TestCase):
    """1 - a table with DATE_COLUMN capability; validation of garbage config."""

    def setUp(self):
        DateColumnConfigLoader.invalidate()

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    def test_configured_real_column_resolves(self):
        config = DateColumnConfigLoader.for_table(CONN, DATE_TABLE_OK)
        self.assertTrue(config.is_configured)
        self.assertEqual(config.date_column, "DocMonth")

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    def test_free_text_config_is_rejected(self):
        # "Docdate (YYYY-MM-DD)" is not a registered column - Gate 3 Step 7b's
        # exact footgun, reused here for DATE_COLUMN's month_column reuse.
        config = DateColumnConfigLoader.for_table(CONN, DATE_TABLE_BAD)
        self.assertFalse(config.is_configured)
        self.assertIsNone(config.date_column)

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    def test_unconfigured_table_is_unconfigured(self):
        config = DateColumnConfigLoader.for_table(CONN, UNCONFIGURED_TABLE)
        self.assertFalse(config.is_configured)

    def test_no_connection_or_table_never_raises(self):
        self.assertFalse(DateColumnConfigLoader.for_table(None, DATE_TABLE_OK).is_configured)
        self.assertFalse(DateColumnConfigLoader.for_table(CONN, None).is_configured)

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    def test_cache_isolated_between_tables(self):
        ok = DateColumnConfigLoader.for_table(CONN, DATE_TABLE_OK)
        bad = DateColumnConfigLoader.for_table(CONN, DATE_TABLE_BAD)
        self.assertNotEqual(ok.is_configured, bad.is_configured)

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    def test_invalidate_clears_cache(self):
        DateColumnConfigLoader.for_table(CONN, DATE_TABLE_OK)
        DateColumnConfigLoader.invalidate(CONN)
        self.assertEqual(DateColumnConfigLoader._cache, {})


class TestTableAwareCapability(unittest.TestCase):
    """
    2 - table with snapshot capability, 3 - multiple tables with different
    temporal behaviours, 4 - no capability configured, 5 - existing snapshot
    regression: SNAPSHOT bindings are unaffected by this addition.
    """

    def setUp(self):
        DateColumnConfigLoader.invalidate()
        self.resolver = TimeStrategyResolver()

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    @patch("semantic.temporal.snapshot_config.SnapshotConfigLoader.for_table",
           classmethod(fake_snapshot_for_table))
    def test_date_column_table_gets_its_own_column(self):
        cap = self.resolver.discover_capability_for_table(CONN, DATE_TABLE_OK)
        self.assertEqual(cap.date_columns, ["DocMonth"])
        self.assertEqual(cap.default_date_column, "DocMonth")

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    @patch("semantic.temporal.snapshot_config.SnapshotConfigLoader.for_table",
           classmethod(fake_snapshot_for_table))
    def test_snapshot_table_keeps_snapshot_mapping_and_no_date_columns(self):
        # 5 - existing snapshot-table behaviour is unchanged by this addition.
        cap = self.resolver.discover_capability_for_table(CONN, SALES)
        self.assertEqual(cap.date_columns, [])
        self.assertEqual(cap.snapshot_mapping, {0: "CY", 1: "PY"})

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    @patch("semantic.temporal.snapshot_config.SnapshotConfigLoader.for_table",
           classmethod(fake_snapshot_for_table))
    def test_multiple_tables_get_independent_capabilities(self):
        # 3 - two tables in the same connection resolve independently; one
        # table's DATE_COLUMN never leaks onto another's capability.
        date_cap = self.resolver.discover_capability_for_table(CONN, DATE_TABLE_OK)
        snapshot_cap = self.resolver.discover_capability_for_table(CONN, SALES)
        self.assertTrue(date_cap.date_columns)
        self.assertFalse(snapshot_cap.date_columns)

    @patch.object(DateColumnConfigLoader, "_load", classmethod(fake_date_load))
    @patch("semantic.temporal.snapshot_config.SnapshotConfigLoader.for_table",
           classmethod(fake_snapshot_for_table))
    def test_unconfigured_table_gets_empty_capability(self):
        # 4 - neither DATE_COLUMN nor SNAPSHOT configuration for this table:
        # a fully empty, genuinely table-scoped capability.
        cap = self.resolver.discover_capability_for_table(CONN, UNCONFIGURED_TABLE)
        self.assertEqual(cap.date_columns, [])
        self.assertEqual(cap.snapshot_mapping, {})

    def test_no_connection_or_table_returns_empty_capability(self):
        self.assertEqual(
            self.resolver.discover_capability_for_table(None, DATE_TABLE_OK).date_columns, []
        )
        self.assertEqual(
            self.resolver.discover_capability_for_table(CONN, None).date_columns, []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
