# ignoring loop detection
import unittest
import datetime
from unittest.mock import MagicMock, patch
from semantic.matching.models import CachedDimensionValue, MatchResult, MatchType
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.semantic_resolver import SemanticResolver
from ai.prompt_builder import PromptBuilder

# Setup mock functions and fixtures
def make_cached_value(dim_id, bus_name, tbl, col, val):
    val_norm = val.lower()
    val_tokens = val_norm.split()
    from semantic.matching.singular_plural_matcher import SingularPluralMatcher
    val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
    return CachedDimensionValue(
        semantic_dimension_id=dim_id,
        business_name=bus_name,
        table_name=tbl,
        column_name=col,
        value=val,
        normalized_value=val_norm,
        runtime_stored_norm=val_norm,
        runtime_stored_tokens=val_tokens,
        runtime_stored_singulars=val_singulars,
        runtime_raw_norm=val_norm,
        runtime_raw_tokens=val_tokens,
        runtime_raw_singulars=val_singulars
    )

MOCK_INDEXED_VALUES = [
    make_cached_value(1, "City", "Locations", "City", "Coimbatore"),
    make_cached_value(2, "District", "Locations", "District", "Coimbatore"),
    make_cached_value(3, "Brand", "Products", "Brand", "Ramraj"),
    make_cached_value(4, "Prod Grp", "Products", "ProdGrp", "Ramraj"),
    make_cached_value(5, "City", "Locations", "City", "Chennai"),
    make_cached_value(6, "Brand", "Products", "Brand", "cotton pants"),
]

mock_metrics = [
    ("Qty", "Qty", "SalesTable", "Quantity", "SUM", "quantity"),
    ("Amt", "Amt", "SalesTable", "Amount", "SUM", "amount"),
    ("Sales", "Sales", "SalesTable", "Sales", "SUM", "sales")
]

mock_dimensions = [
    ("City", "City", "Locations", "City", "", ""),
    ("District", "District", "Locations", "District", "", ""),
    ("Brand", "Brand", "Products", "Brand", "", ""),
    ("Prod Grp", "Prod Grp", "Products", "ProdGrp", "", "")
]

class TestPhase1D5CIntegrationGaps(unittest.TestCase):

    def setUp(self):
        # Patch resolver's metadata fetch and load values
        self.fetch_patcher = patch("semantic.semantic_resolver.SemanticResolver._fetch_active_metadata", return_value=(mock_metrics, mock_dimensions))
        self.load_patcher = patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=MOCK_INDEXED_VALUES)
        
        self.fetch_patcher.start()
        self.load_patcher.start()

    def tearDown(self):
        self.fetch_patcher.stop()
        self.load_patcher.stop()

    # =========================================================================
    # GAP 1: REAL METRIC-SHIFT VALIDATION
    # =========================================================================
    def test_integration_metric_shift_different_metric(self):
        """Verify that introducing a different metric (Qty -> Amt) blocks B.2 dimension inheritance."""
        prev_context = {
            "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
            "dimensions": [{"dimension_name": "City", "business_name": "City"}],
            "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
        }
        # amt is a new metric, different from Qty -> metric shift triggers -> B.2 is skipped.
        res = SemanticResolver.resolve("conn_123", "amt Coimbatore", previous_semantic_context=prev_context)
        
        self.assertFalse(res["followup_context"]["applied"])
        self.assertEqual(res["followup_context"]["reason"], "CURRENT_METRICS_PRESENT")
        # Should keep both City and District matches (not filter to City)
        dims = {m["business_name"] for m in res["value_matches"]}
        self.assertEqual(dims, {"City", "District"})

    def test_integration_metric_shift_same_metric(self):
        """Verify that keeping the same metric (Qty -> Qty) allows B.2 dimension inheritance."""
        prev_context = {
            "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
            "dimensions": [{"dimension_name": "City", "business_name": "City"}],
            "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
        }
        res = SemanticResolver.resolve("conn_123", "qty Coimbatore", previous_semantic_context=prev_context)
        
        self.assertTrue(res["followup_context"]["applied"])
        self.assertEqual(res["followup_context"]["reason"], "PREVIOUS_DIMENSION_MATCH")
        dims = {m["business_name"] for m in res["value_matches"]}
        self.assertEqual(dims, {"City"})

    # =========================================================================
    # GAP 2: PARTIAL-SINGLE DOWNSTREAM VALIDATION
    # =========================================================================
    def test_integration_partial_single_coverage_preservation(self):
        """Verify that matched tokens are preserved and unmatched tokens are available for downstream intent."""
        # Query "cotton" matches "cotton pants" in the index partially.
        res = SemanticResolver.resolve("conn_123", "cotton")
        self.assertTrue(len(res["value_matches"]) > 0)
        
        match = res["value_matches"][0]
        self.assertEqual(match["value"], "cotton pants")
        # Matched query token should be "cotton"
        self.assertIn("cotton", match["matched_question_tokens"])
        
        # Calculate unmatched tokens from the query. If the query is "cotton blue shirt", 
        # and "cotton" is matched, then "blue" and "shirt" are unmatched.
        query = "cotton blue shirt"
        res_full = SemanticResolver.resolve("conn_123", query)
        self.assertTrue(len(res_full["value_matches"]) > 0)
        
        match_full = res_full["value_matches"][0]
        matched_tokens = set(match_full["matched_question_tokens"])
        query_tokens = set(query.lower().split())
        unmatched_tokens = query_tokens - matched_tokens
        
        self.assertIn("cotton", matched_tokens)
        self.assertIn("blue", unmatched_tokens)
        self.assertIn("shirt", unmatched_tokens)

    # =========================================================================
    # GAP 3: RESOLVED SEMANTIC CANDIDATE -> ACTUAL GENERATED SQL PREDICATE VALIDATION
    # =========================================================================
    @patch("services.connection_service.ConnectionService.get_connection")
    @patch("semantic.semantic_service.SemanticService.get_metrics", return_value=[])
    @patch("semantic.semantic_service.SemanticService.get_dimensions", return_value=[])
    @patch("semantic.relationship_service.SemanticRelationshipService.build_relationships", return_value=[])
    @patch("ai.prompt_builder.engine.connect")
    @patch("semantic.relevant_table_resolver.RelevantTableResolver.resolve", return_value=["Locations", "SalesTable"])
    @patch("semantic.relationship_expander.RelationshipExpander.expand", return_value=[{"table_name": "Locations"}, {"table_name": "SalesTable"}])
    @patch("semantic.relationship_context_service.RelationshipContextService.build_context", return_value="SalesTable JOIN Locations ON ...")
    @patch("semantic.relevant_schema_service.RelevantSchemaService.get_schema", return_value="CREATE TABLE Locations (City VARCHAR(100), District VARCHAR(100))")
    @patch("semantic.query_examples_service.QueryExamplesService.retrieve", return_value=[])
    @patch("semantic.metadata_resolver.MetadataResolver.resolve", return_value={"required_tables": [], "metadata_rules": []})
    def test_resolved_candidate_to_sql_prompt_serialization(self, mock_metadata, mock_examples, mock_schema, mock_rel, mock_exp, mock_table, mock_db_conn, mock_joins, mock_dims, mock_mets, mock_conn):
        """Verify that resolved dimension/value matches map correctly to prompt variables for SQL generation."""
        mock_conn.return_value = {
            "connection_id": "7cdfaca8-5097-4f9c-a521-0bdcd8e912d4",
            "connection_name": "Test Connection",
            "database_type": "mssql"
        }
        
        # We mock sqlalchemy connection object returned by connect() to avoid real query to database
        mock_conn_obj = MagicMock()
        mock_conn_obj.execute.return_value.fetchall.return_value = []
        mock_db_conn.return_value.__enter__.return_value = mock_conn_obj

        # We resolve "Chennai" -> City
        prompt_builder = PromptBuilder()
        prompt, sem_res, runtime = prompt_builder.build_sql_prompt(
            question="Chennai",
            connection_id="7cdfaca8-5097-4f9c-a521-0bdcd8e912d4"
        )
        
        # Verify the prompt text contains instructions and serialization of the city Chennai
        self.assertIn("Chennai", prompt)
        self.assertIn("MATCHED DIMENSION VALUES", prompt)
        
        # Verify that all properties of the resolved candidate match are present in the prompt string
        self.assertIn("'table_name': 'Locations'", prompt)
        self.assertIn("'column_name': 'City'", prompt)
        self.assertIn("'value': 'Chennai'", prompt)


if __name__ == "__main__":
    unittest.main()
