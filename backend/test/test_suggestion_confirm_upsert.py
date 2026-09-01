"""
Gate 3 P1 - confirming a suggestion for a column discovery never registered.

The suggester profiles every physical column. Discovery registers only some of
them: Gate 2 Step 12 correctly taught it to skip a constant column and an
identifier. Those two scopes are not the same set, and every proposal that fell
in the gap was impossible to confirm - the handler raised

    Column 'PBI_OUTSTANDING_ENES_SUMMARY.CreatedDate' is not registered as a
    metric or a dimension, so there is no row to confirm.

which left seven items stuck in the review queue permanently. The proposals
themselves already said what to do - target.action is UPSERT and
current.exists is false - so only the insert half was missing.

The two live cases these tests are modelled on:

    CreatedDate   1 distinct value over 95,613 rows   -> constant, skipped
    transid       95,053 distinct over 95,613 rows    -> identifier, skipped
"""

import datetime
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, event, text

test_engine = create_engine("sqlite:///:memory:")


@event.listens_for(test_engine, "connect")
def _register_sqlite_functions(dbapi_connection, connection_record):
    # ColumnConfigService._patch stamps updated_at with GETDATE().
    dbapi_connection.create_function(
        "GETDATE", 0, lambda: datetime.datetime.now().isoformat()
    )


from semantic.config_service import SuggestionService  # noqa: E402

CONNECTION_ID = str(uuid.uuid4())
USER = {"employee_id": "EMP001"}
TABLE = "PBI_OUTSTANDING_ENES_SUMMARY"


def _suggestion(column_name, config_table="semantic_dimensions"):
    return {
        "table_name": TABLE,
        "column_name": column_name,
        "target": {"config_table": config_table, "action": "UPSERT"},
    }


class TestConfirmCreatesMissingRow(unittest.TestCase):

    def setUp(self):
        with test_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS semantic_dimensions"))
            conn.execute(text("DROP TABLE IF EXISTS semantic_metrics"))
            conn.execute(text("""
                CREATE TABLE semantic_dimensions (
                    dimension_id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    dimension_name TEXT NOT NULL,
                    business_name TEXT NOT NULL,
                    description TEXT,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'AUTO',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT, updated_by TEXT, updated_at TEXT,
                    synonyms TEXT, semantic_category TEXT,
                    dimension_role TEXT,
                    is_excluded INTEGER NOT NULL DEFAULT 0,
                    is_confirmed INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.execute(text("""
                CREATE TABLE semantic_metrics (
                    metric_id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    business_name TEXT NOT NULL,
                    description TEXT,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    aggregation_type TEXT,
                    source TEXT NOT NULL DEFAULT 'AUTO',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT, updated_by TEXT, updated_at TEXT,
                    synonyms TEXT,
                    is_excluded INTEGER NOT NULL DEFAULT 0,
                    is_confirmed INTEGER NOT NULL DEFAULT 0
                )
            """))

        self.patchers = [
            patch("semantic.config_service.engine", test_engine),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    def _dimension(self, column_name):
        with test_engine.connect() as conn:
            return conn.execute(text(
                "SELECT dimension_name, business_name, dimension_role, "
                "is_excluded, is_confirmed, source, synonyms, column_name "
                "FROM semantic_dimensions WHERE column_name = :c"
            ), {"c": column_name}).fetchone()

    # -- the reported failure ------------------------------------------------

    def test_constant_column_can_now_be_confirmed(self):
        # CreatedDate: one distinct value over 95,613 rows. Discovery skips it,
        # so before this fix confirming raised a 404.
        result = SuggestionService._confirm_column(
            connection_id=CONNECTION_ID,
            suggestion=_suggestion("CreatedDate"),
            proposal={
                "classification": "EXCLUDED",
                "business_name": "Load Timestamp",
                "description": "Date when data was loaded",
                "synonyms": ["Created Date", "Load Date", "Extraction Time"],
                "dimension_role": "INTERNAL",
            },
            user=USER,
        )

        self.assertTrue(result["persisted"])

        row = self._dimension("CreatedDate")
        self.assertIsNotNone(row, "the row should have been created")
        self.assertEqual(row.business_name, "Load Timestamp")
        self.assertEqual(row.dimension_role, "INTERNAL")
        self.assertEqual(row.is_confirmed, 1)
        # EXCLUDED classification must switch the column off, which is the
        # whole point of confirming this particular proposal.
        self.assertEqual(row.is_excluded, 1)

    def test_identifier_column_can_now_be_confirmed(self):
        # transid: 99.4% unique. Discovery rejects it as a measure and never
        # registers it as a dimension either.
        SuggestionService._confirm_column(
            connection_id=CONNECTION_ID,
            suggestion=_suggestion("transid"),
            proposal={
                "classification": "EXCLUDED",
                "business_name": "Transaction ID",
                "synonyms": ["trans id", "transaction number"],
                "dimension_role": "IDENTIFIER",
            },
            user=USER,
        )

        row = self._dimension("transid")
        self.assertIsNotNone(row)
        self.assertEqual(row.dimension_role, "IDENTIFIER")
        self.assertEqual(row.is_excluded, 1)

    # -- shape of what gets created -----------------------------------------

    def test_technical_name_follows_discovery_convention(self):
        # column_name.lower() with spaces underscored, so a row created here is
        # indistinguishable from one discovery would have made.
        SuggestionService._confirm_column(
            CONNECTION_ID, _suggestion("CreatedDate"),
            {"classification": "EXCLUDED", "business_name": "Load Timestamp",
             "dimension_role": "INTERNAL"}, USER,
        )
        self.assertEqual(self._dimension("CreatedDate").dimension_name, "createddate")

    def test_source_stays_auto(self):
        # The column came from the schema. The administrator confirmed an
        # interpretation of it; they did not invent it by hand.
        SuggestionService._confirm_column(
            CONNECTION_ID, _suggestion("CreatedDate"),
            {"classification": "EXCLUDED", "business_name": "Load Timestamp"}, USER,
        )
        self.assertEqual(self._dimension("CreatedDate").source, "AUTO")

    def test_metric_target_creates_a_metric_row(self):
        SuggestionService._confirm_column(
            connection_id=CONNECTION_ID,
            suggestion=_suggestion("pendamt", config_table="semantic_metrics"),
            proposal={
                "classification": "MEASURE",
                "business_name": "Pending Amount",
                "aggregation_type": "SUM",
            },
            user=USER,
        )

        with test_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT metric_name, business_name, aggregation_type, "
                "is_confirmed, is_excluded FROM semantic_metrics "
                "WHERE column_name = 'pendamt'"
            )).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row.metric_name, "pendamt")
        self.assertEqual(row.aggregation_type, "SUM")
        self.assertEqual(row.is_confirmed, 1)
        self.assertEqual(row.is_excluded, 0)

    def test_only_one_row_is_created(self):
        SuggestionService._confirm_column(
            CONNECTION_ID, _suggestion("CreatedDate"),
            {"classification": "EXCLUDED", "business_name": "Load Timestamp"}, USER,
        )
        with test_engine.connect() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) FROM semantic_dimensions WHERE column_name='CreatedDate'"
            )).scalar()
        self.assertEqual(n, 1)


class TestExistingRowsAreStillUpdatedNotDuplicated(unittest.TestCase):
    """The pre-existing update path must be untouched by the new insert path."""

    def setUp(self):
        with test_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS semantic_dimensions"))
            conn.execute(text("""
                CREATE TABLE semantic_dimensions (
                    dimension_id TEXT PRIMARY KEY, connection_id TEXT NOT NULL,
                    dimension_name TEXT NOT NULL, business_name TEXT NOT NULL,
                    description TEXT, table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'AUTO',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT, updated_by TEXT, updated_at TEXT,
                    synonyms TEXT, semantic_category TEXT, dimension_role TEXT,
                    is_excluded INTEGER NOT NULL DEFAULT 0,
                    is_confirmed INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.execute(text(
                "INSERT INTO semantic_dimensions "
                "(dimension_id, connection_id, dimension_name, business_name, "
                " table_name, column_name, source, synonyms) "
                "VALUES ('existing-1', :c, 'category', 'Old Name', :t, "
                "'Category', 'AUTO', 'old syn')"
            ), {"c": CONNECTION_ID, "t": TABLE})

        self.patcher = patch("semantic.config_service.engine", test_engine)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_existing_row_is_updated_in_place(self):
        SuggestionService._confirm_column(
            connection_id=CONNECTION_ID,
            suggestion=_suggestion("Category"),
            proposal={
                "classification": "DIMENSION",
                "business_name": "Category",
                "dimension_role": "GROUPING",
            },
            user=USER,
        )

        with test_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT dimension_id, business_name, dimension_role, is_confirmed "
                "FROM semantic_dimensions WHERE column_name = 'Category'"
            )).fetchall()

        self.assertEqual(len(rows), 1, "must not create a duplicate row")
        self.assertEqual(rows[0].dimension_id, "existing-1", "must reuse the row")
        self.assertEqual(rows[0].business_name, "Category")
        self.assertEqual(rows[0].dimension_role, "GROUPING")
        self.assertEqual(rows[0].is_confirmed, 1)


if __name__ == "__main__":
    unittest.main()
