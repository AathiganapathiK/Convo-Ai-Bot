import unittest
from unittest.mock import MagicMock, patch
from semantic.query_examples_service import QueryExamplesService

class TestQueryExamplesService(unittest.TestCase):
    """Focused regression tests for QueryExamplesService retrieve generic compatibility filtering logic."""

    @patch("database.engine.connect")
    def test_retrieve_conflicting_example_excluded(self, mock_connect):
        # Current: City = Chennai
        # Example: same/similar question but no City predicate -> excluded
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales in Chennai", "SELECT CY FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE YEAR(createddate) = 2026")
        ]
        
        value_matches = [
            {
                "column_name": "City",
                "value": "Chennai"
            }
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=value_matches
        )
        
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_retrieve_structurally_compatible_example_excluded_on_different_value(self, mock_connect):
        # Current: City = Chennai
        # Example: City = Coimbatore -> EXCLUDED under Gate 1B because it introduces unrequested value Coimbatore
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales in Coimbatore", "SELECT CY FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE City = 'Coimbatore'")
        ]
        
        value_matches = [
            {
                "column_name": "City",
                "value": "Chennai"
            }
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=value_matches
        )
        
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_retrieve_multiple_required_filters_excluded_on_different_value(self, mock_connect):
        # Current: City = Chennai, Brand = Ramraj
        # Example: City = Coimbatore AND Brand = Linen -> EXCLUDED because of unrequested values
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            # Example 1: Missing Brand
            ("Show Chennai outstanding", "SELECT PAMT FROM PBI_OUTSTANDING_ENES_SUMMARY WHERE City = 'Chennai'"),
            # Example 2: Has both City and Brand but different values
            ("Show Coimbatore outstanding", "SELECT PAMT FROM PBI_OUTSTANDING_ENES_SUMMARY WHERE City = 'Coimbatore' AND Brand = 'Linen'")
        ]
        
        value_matches = [
            {
                "column_name": "City",
                "value": "Chennai"
            },
            {
                "column_name": "Brand",
                "value": "Ramraj"
            }
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["PBI_OUTSTANDING_ENES_SUMMARY"],
            value_matches=value_matches
        )
        
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_retrieve_no_required_filters(self, mock_connect):
        # Current query has no resolved value filters -> existing example retrieval behavior unchanged
        # Note: Example with no value filters should be retained, example with filter will be excluded by Gate 1B.
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales in this year", "SELECT CY FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE YEAR(createddate) = 2026"),
            ("Show brand outstanding", "SELECT PAMT FROM PBI_OUTSTANDING_ENES_SUMMARY")
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"]
        )
        
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_retrieve_exact_real_regression(self, mock_connect):
        # Current: Show cotton sales in this year
        # Required: ProdGrp2 = 'WHITE SHIRT 100% COTTON'
        # Historical example without ProdGrp2 -> excluded
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show cotton sales in this year", "SELECT YEAR(createddate) AS Year, SUM(CY) AS TotalCottonSales FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE YEAR(createddate) = YEAR(GETDATE()) GROUP BY YEAR(createddate) ORDER BY YEAR(createddate) DESC;")
        ]
        
        value_matches = [
            {
                "column_name": "ProdGrp2",
                "value": "WHITE SHIRT 100% COTTON"
            }
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=value_matches
        )
        
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_metric_conflict_excluded(self, mock_connect):
        # TEST 1: Current metric = CY, Historical SQL = SUM(PY) -> EXCLUDED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales trend", "SELECT ProdGrp2, SUM(PY) AS TotalSales FROM QB_MDJMD_SALES_5YRS_SUMMARY GROUP BY ProdGrp2")
        ]
        
        metric_objects = [{"column_name": "CY", "metric_name": "cy"}]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            metric_objects=metric_objects
        )
        
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_metric_compatible_retained(self, mock_connect):
        # TEST 2: Current metric = CY, Historical SQL = SUM(CY) -> RETAINED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales in this year", "SELECT ProdGrp2, SUM(CY) AS TotalSales FROM QB_MDJMD_SALES_5YRS_SUMMARY GROUP BY ProdGrp2")
        ]
        
        metric_objects = [{"column_name": "CY", "metric_name": "cy"}]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            metric_objects=metric_objects
        )
        
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_metric_reverse_conflict_excluded(self, mock_connect):
        # TEST 3: Current metric = PY, Historical SQL = SUM(CY) -> EXCLUDED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show current sales", "SELECT ProdGrp2, SUM(CY) AS TotalSales FROM QB_MDJMD_SALES_5YRS_SUMMARY GROUP BY ProdGrp2")
        ]
        
        metric_objects = [{"column_name": "PY", "metric_name": "py"}]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            metric_objects=metric_objects
        )
        
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_metric_multi_compatible_retained(self, mock_connect):
        # TEST 4: Current metrics = CY + PY, Historical SQL = SUM(CY), SUM(PY) -> RETAINED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Compare years", "SELECT SUM(CY) AS CurrentSales, SUM(PY) AS PreviousSales FROM QB_MDJMD_SALES_5YRS_SUMMARY")
        ]
        
        metric_objects = [
            {"column_name": "CY", "metric_name": "cy"},
            {"column_name": "PY", "metric_name": "py"}
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            metric_objects=metric_objects
        )
        
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_metric_missing_retained(self, mock_connect):
        # TEST 5: Current metric = CY, Historical SQL = ProdGrp2 filter but no metric-column signal
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            # The example has no CY or PY or other period metric references, just plain table
            ("List items", "SELECT ProdGrp2 FROM QB_MDJMD_SALES_5YRS_SUMMARY")
        ]
        
        metric_objects = [{"column_name": "CY", "metric_name": "cy"}]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            metric_objects=metric_objects
        )
        
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_metric_no_metrics_retained(self, mock_connect):
        # TEST 6: Query has no resolved metric -> unchanged
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("List items", "SELECT ProdGrp2, PY FROM QB_MDJMD_SALES_5YRS_SUMMARY")
        ]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"]
        )
        
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_real_cotton_regression(self, mock_connect):
        # TEST 7: Question: "Show cotton sales", Metric: CY, Historical: "show sales trend" with SUM(PY) -> EXCLUDED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_conn.execute.return_value.fetchall.return_value = [
            ("show sales trend", "SELECT TOP 100 ProdGrp2, SUM(PY) AS TotalSales FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'CCB TRENDY' GROUP BY ProdGrp2")
        ]
        
        metric_objects = [{"column_name": "CY", "metric_name": "cy"}]
        value_matches = [{"column_name": "ProdGrp2", "value": "LS ZARI COTTON"}]
        
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=value_matches,
            metric_objects=metric_objects
        )
        
        self.assertEqual(len(results), 0)

    # =========================================================================
    # GATE 1B - NEW TESTS REQUIRED
    # =========================================================================

    @patch("database.engine.connect")
    def test_1_current_no_values_example_has_filter_excluded(self, mock_connect):
        # TEST 1: Current value_matches = [], Example: WHERE ProdGrp2 = 'MENS PYJAMA PANT' -> EXCLUDED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show pyjama sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'MENS PYJAMA PANT'")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[]
        )
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_2_current_has_value_example_has_same_value_retained(self, mock_connect):
        # TEST 2: Current: ProdGrp2 = 'WHITE SHIRT 100% COTTON', Example: same value -> RETAINED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show cotton sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'WHITE SHIRT 100% COTTON'")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[{"column_name": "ProdGrp2", "value": "WHITE SHIRT 100% COTTON"}]
        )
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_3_current_has_value_example_has_different_value_excluded(self, mock_connect):
        # TEST 3: Current: ProdGrp2 = 'WHITE SHIRT 100% COTTON', Example: ProdGrp2 = 'DHOTI : 3.80MT KL COTTON KARA' -> EXCLUDED
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show dhoti sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'DHOTI : 3.80MT KL COTTON KARA'")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[{"column_name": "ProdGrp2", "value": "WHITE SHIRT 100% COTTON"}]
        )
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_4_current_has_value_example_has_same_value_retained_rule(self, mock_connect):
        # TEST 4: Current: City = Chennai, Example: City = Chennai -> RETAINED for this specific extra-value-filter rule.
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show Chennai sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE City = 'Chennai'")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[{"column_name": "City", "value": "Chennai"}]
        )
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_5_current_has_value_example_has_extra_value_filter_excluded(self, mock_connect):
        # TEST 5: Current: City = Chennai, Example: City = Chennai AND Brand = Unibro -> EXCLUDED because of extra Brand filter
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show Chennai Unibro sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE City = 'Chennai' AND Brand = 'Unibro'")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[{"column_name": "City", "value": "Chennai"}]
        )
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_6_current_no_value_example_no_value_retained(self, mock_connect):
        # TEST 6: Current: No value filters, Example: No value filters -> RETAINED.
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[]
        )
        self.assertEqual(len(results), 1)

    @patch("database.engine.connect")
    def test_7_real_regression_unrequested_value_filter_excluded(self, mock_connect):
        # TEST 7: Current: Show sales, value_matches = [], Example: Show sales, SQL has ProdGrp2 = 'MENS PYJAMA PANT' -> EXCLUDED.
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show sales", "SELECT TOP 100 CardName, SUM(CY) AS PantSales FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'MENS PYJAMA PANT' GROUP BY CardName ORDER BY PantSales DESC;")
        ]
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[]
        )
        self.assertEqual(len(results), 0)

    @patch("database.engine.connect")
    def test_8_new_chat_regression(self, mock_connect):
        # TEST 8: Chat A stores a filtered example (ProdGrp2 = 'MENS PYJAMA PANT'). Chat B starts with history = [], no filters -> Chat A example not returned.
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        # Stored Chat A query
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Show cotton sales", "SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'MENS PYJAMA PANT'")
        ]
        
        # Chat B query: Show sales (no value matches)
        results = QueryExamplesService.retrieve(
            connection_id="test_conn",
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"],
            value_matches=[]
        )
        self.assertEqual(len(results), 0)

if __name__ == "__main__":
    unittest.main()

