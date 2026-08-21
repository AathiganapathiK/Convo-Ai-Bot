import unittest
from unittest.mock import MagicMock, patch
from semantic.semantic_resolver import SemanticResolver
from semantic.semantic_context_service import SemanticContextService
from ai.prompt_builder import PromptBuilder

class TestSemanticAggregation(unittest.TestCase):
    """Focused regression tests for metric aggregation logic (Phase 1E.2)."""

    def setUp(self):
        # Set up ConnectionService mock so PromptBuilder doesn't throw ValueErrors
        self.conn_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_service = self.conn_patcher.start()
        self.mock_conn_service.get_active_connection.return_value = {
            "connection_id": "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
            "connection_name": "Test DB",
            "database_type": "mssql"
        }
        self.mock_conn_service.get_connection.return_value = {
            "connection_id": "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
            "connection_name": "Test DB",
            "database_type": "mssql"
        }

    def tearDown(self):
        self.conn_patcher.stop()

    def test_cy_resolves_with_sum_aggregation(self):
        # TEST 1: Metric cy resolves with aggregation_type = SUM
        # Check that SemanticResolver retrieves SUM for cy metric
        result = SemanticResolver.resolve(
            connection_id="F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
            question="Show cotton sales"
        )
        
        self.assertIn("metric_objects", result)
        cy_metric = next((m for m in result["metric_objects"] if m["metric_name"] == "cy"), None)
        self.assertIsNotNone(cy_metric)
        self.assertEqual(cy_metric["aggregation_type"], "SUM")

    def test_semantic_context_renders_sum(self):
        # TEST 2: Semantic context renders: Aggregation: SUM
        metric_objects = [
            {
                "business_name": "C Y",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "CY",
                "aggregation_type": "SUM"
            }
        ]
        
        context_str = SemanticContextService.build_context(
            metric_objects=metric_objects,
            dimension_objects=[]
        )
        
        self.assertIn("Aggregation: SUM", context_str)
        self.assertNotIn("Aggregation: None", context_str)

    def test_bare_sales_does_not_expose_none_aggregation(self):
        # TEST 3: A bare business question such as "Show sales" does not expose Aggregation: None
        # Verify using build_sql_prompt directly
        builder = PromptBuilder()
        prompt, semantic_result, _ = builder.build_sql_prompt(
            question="Show sales",
            connection_id="F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
        )
        
        # Verify prompt does not contain 'Aggregation: None' or 'Aggregation: null'
        self.assertNotIn("Aggregation: None", prompt)
        self.assertNotIn("Aggregation: null", prompt)
        self.assertIn("Aggregation: SUM", prompt)

    @patch("services.llm_execution_service.LLMExecutionService.execute")
    @patch("database.engine.connect")
    def test_filtered_question_preserves_filter_and_sum(self, mock_connect, mock_execute):
        # TEST 4: A filtered question: "Show cotton sales" after selecting a resolved product
        # still preserves ProdGrp2 filter and SUM(CY)
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        # Mock database connection values/queries
        mock_conn.execute.return_value.fetchall.return_value = []
        
        # Mock LLM return value with SQL containing SUM(CY) and ProdGrp2 filter
        mock_execute.return_value.choices = [
            MagicMock(message=MagicMock(content="SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'LS ZARI COTTON'"))
        ]
        
        # We simulate the clarified candidate resumption flow in ai_service
        import ai.ai_service
        res = ai.ai_service.generate_sql_query(
            question="Show cotton sales",
            company_id="FD4925A0-9034-4343-A368-8D20A919DF92",
            clarified_candidate={
                "column_name": "ProdGrp2",
                "value": "LS ZARI COTTON",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "dimension_id": "DCBA558A-C4F4-409C-AF0C-A8B3E95B0DAF",
                "business_name": "Prod Grp2"
            }
        )
        sql_query = res["sql_query"]
        
        # Verify SUM(CY) and ProdGrp2 exist in the query
        self.assertIn("SUM(CY)", sql_query)
        self.assertIn("ProdGrp2 = 'LS ZARI COTTON'", sql_query)

    def test_existing_defined_aggregation_remains_unchanged(self):
        # TEST 5: Existing metrics whose aggregation_type is already defined remain unchanged
        # e.g., qty has SUM and remains SUM
        result = SemanticResolver.resolve(
            connection_id="F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
            question="Show qty"
        )
        
        self.assertIn("metric_objects", result)
        qty_metric = next((m for m in result["metric_objects"] if m["metric_name"] == "qty"), None)
        self.assertIsNotNone(qty_metric)
        self.assertEqual(qty_metric["aggregation_type"], "SUM")

    def test_unverified_null_aggregation_remains_unchanged(self):
        # TEST 6: Unverified numeric metrics with NULL aggregation remain unchanged
        # e.g., pendamt has NULL aggregation in database
        result = SemanticResolver.resolve(
            connection_id="F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
            question="Show pendamt"
        )
        
        self.assertIn("metric_objects", result)
        pend_metric = next((m for m in result["metric_objects"] if m["metric_name"] == "pendamt"), None)
        self.assertIsNotNone(pend_metric)
        self.assertIsNone(pend_metric["aggregation_type"])

if __name__ == "__main__":
    unittest.main()
