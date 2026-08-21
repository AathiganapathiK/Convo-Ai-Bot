import unittest
from unittest.mock import patch, MagicMock

from semantic.semantic_resolver import SemanticResolver
from semantic.temporal.pipeline import TemporalPipeline
from ai.prompt_builder import PromptBuilder, build_sql_prompt
from semantic.matching.stopwords import STOPWORDS


class TestMetricTemporalDecoupling(unittest.TestCase):
    """
    Focused unit tests for Gate 1A — Decoupling Business Metric from Time
    and preventing temporal token value-matching collisions.
    """

    def setUp(self):
        self.conn_id = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
        self.conn_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_service = self.conn_patcher.start()
        self.mock_conn_service.get_active_connection.return_value = {
            "connection_id": self.conn_id,
            "connection_name": "Test DB",
            "database_type": "mssql"
        }
        self.mock_conn_service.get_connection.return_value = {
            "connection_id": self.conn_id,
            "connection_name": "Test DB",
            "database_type": "mssql"
        }
        from semantic.temporal.capability_cache import TimeResolutionCache
        from semantic.temporal.models import TimeCapability
        TimeResolutionCache.put(
            self.conn_id,
            TimeCapability(
                date_columns=["createddate", "DocDate"],
                snapshot_mapping={0: "CY", 1: "PY", 2: "PPY"},
                snapshot_year_columns=["CY", "PY", "PPY"],
                default_date_column="createddate"
            )
        )

    def tearDown(self):
        self.conn_patcher.stop()

    def test_stopwords_contain_temporal_and_conjunctions(self):
        """
        Verify STOPWORDS contain 'current', 'previous', 'and', 'this', 'last', 'year'.
        """
        self.assertIn("current", STOPWORDS)
        self.assertIn("previous", STOPWORDS)
        self.assertIn("and", STOPWORDS)
        self.assertIn("this", STOPWORDS)
        self.assertIn("last", STOPWORDS)
        self.assertIn("year", STOPWORDS)

    def test1_show_sales_unspecified_temporal(self):
        """
        1. Show sales
        Expected: Resolves metric object, but temporal intent is None / UNSPECIFIED.
        """
        res = SemanticResolver.resolve(self.conn_id, "Show sales")
        self.assertIn("metric_objects", res)
        self.assertTrue(len(res["metric_objects"]) > 0)
        
        intent = TemporalPipeline().detector.detect("Show sales")
        self.assertIsNone(intent)

    def test2_show_sales_this_year(self):
        """
        2. Show sales this year
        Expected: Binds metric to CY on snapshot table and detects CURRENT_YEAR.
        """
        prompt, sem_res, _ = build_sql_prompt("Show sales this year", connection_id=self.conn_id)
        metric_cols = [m["column_name"] for m in sem_res.get("metric_objects", [])]
        self.assertIn("CY", metric_cols)
        self.assertNotIn("SQL Rule:", prompt)  # Redundant date predicate suppressed for snapshot

    def test3_show_sales_last_year(self):
        """
        3. Show sales last year
        Expected: Binds metric to PY (not CY) on snapshot table for PREVIOUS_YEAR intent.
        """
        prompt, sem_res, _ = build_sql_prompt("Show sales last year", connection_id=self.conn_id)
        metric_cols = [m["column_name"] for m in sem_res.get("metric_objects", [])]
        self.assertIn("PY", metric_cols)
        self.assertNotIn("CY", metric_cols)
        self.assertNotIn("SQL Rule:", prompt)  # Redundant date predicate suppressed for snapshot

    def test4_show_current_year_sales_no_false_dimension_match(self):
        """
        4. Show current year sales
        Expected: Token 'current' does not trigger false value match to 'Current Due (1-7)'.
        """
        res = SemanticResolver.resolve(self.conn_id, "Show current year sales")
        val_matches = res.get("value_matches", [])
        matched_values = [v["value"] for v in val_matches]
        self.assertNotIn("Current Due (1-7)", matched_values)

    def test5_show_previous_year_sales_no_contradictory_cy(self):
        """
        5. Show previous year sales
        Expected: Resolves PY metric and suppresses redundant date filter.
        """
        prompt, sem_res, _ = build_sql_prompt("Show previous year sales", connection_id=self.conn_id)
        metric_cols = [m["column_name"] for m in sem_res.get("metric_objects", [])]
        self.assertIn("PY", metric_cols)
        self.assertNotIn("CY", metric_cols)
        self.assertNotIn("SQL Rule:", prompt)

    def test6_compare_current_year_and_previous_year_sales(self):
        """
        6. Compare current year and previous year sales
        Expected: Intent is YEAR_COMPARISON, includes BOTH CY and PY metric objects,
        and 'and' does not match state code 'AN'.
        """
        res = SemanticResolver.resolve(self.conn_id, "Compare current year and previous year sales")
        metric_cols = [m["column_name"] for m in res.get("metric_objects", [])]
        self.assertIn("CY", metric_cols)
        self.assertIn("PY", metric_cols)

        val_matches = res.get("value_matches", [])
        matched_values = [v["value"] for v in val_matches]
        self.assertNotIn("AN", matched_values)

    def test7_explicit_cy(self):
        """
        7. Explicit CY
        Expected: Resolves CY metric.
        """
        res = SemanticResolver.resolve(self.conn_id, "Show CY sales")
        metric_cols = [m["column_name"] for m in res.get("metric_objects", [])]
        self.assertIn("CY", metric_cols)

    def test8_explicit_py(self):
        """
        8. Explicit PY
        Expected: Resolves PY metric.
        """
        res = SemanticResolver.resolve(self.conn_id, "Show PY sales")
        metric_cols = [m["column_name"] for m in res.get("metric_objects", [])]
        self.assertIn("PY", metric_cols)

    def test9_snapshot_table_temporal_binding(self):
        """
        9. Snapshot table temporal binding: PREVIOUS_YEAR -> PY without redundant date predicate.
        """
        prompt, sem_res, _ = build_sql_prompt("Show last year sales", connection_id=self.conn_id)
        self.assertIn("PY", [m["column_name"] for m in sem_res.get("metric_objects", [])])
        self.assertIn("Strategy: SNAPSHOT", prompt)

    def test10_date_column_temporal_binding(self):
        """
        10. Date-column temporal binding: PREVIOUS_YEAR on pending orders uses DATE_COLUMN strategy.
        """
        prompt, sem_res, _ = build_sql_prompt("Show last year pending orders", connection_id=self.conn_id)
        # Pending orders table uses Amt column (date-column table)
        metric_cols = [m["column_name"] for m in sem_res.get("metric_objects", [])]
        if "Amt" in metric_cols or "Qty" in metric_cols:
            self.assertIn("Strategy: DATE_COLUMN", prompt)
            self.assertIn("SQL Rule:", prompt)

    def test11_generic_metric_no_temporal_context(self):
        """
        11. Generic metric with no temporal context does not force a temporal filter.
        """
        res = SemanticResolver.resolve(self.conn_id, "Show sales")
        intent = TemporalPipeline().detector.detect("Show sales")
        self.assertIsNone(intent)
