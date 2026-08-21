import unittest
from unittest.mock import patch, MagicMock
from semantic.matching.models import CachedDimensionValue, ResolutionStatus, MatchResult, MatchType
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.semantic_resolver import SemanticResolver
from semantic.semantic_gate import SemanticGate
from ai.prompt_builder import PromptBuilder
from core.exceptions import AmbiguityException, SemanticRetrievalException

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
    make_cached_value(1, "City", "Locations", "City", "Chennai"),
    make_cached_value(1, "City", "Locations", "City", "Coimbatore"),
    make_cached_value(2, "Brand", "Products", "Brand", "Ramraj"),
    make_cached_value(3, "Product", "Products", "Product", "cotton pants"),
    make_cached_value(3, "Product", "Products", "Product", "N--NIGHT WEARS"),
    make_cached_value(3, "Product", "Products", "Product", "blue shirt"),
    make_cached_value(3, "Product", "Products", "Product", "WHITE SHIRT"),
    make_cached_value(3, "Product", "Products", "Product", "FORMAL SOCKS")
]

mock_metrics = [
    ("Sales", "Sales", "SalesTable", "Sales", "SUM", "sales"),
    ("Qty", "Qty", "SalesTable", "Quantity", "SUM", "quantity")
]

mock_dimensions = [
    ("City", "City", "Locations", "City", "", ""),
    ("Brand", "Brand", "Products", "Brand", "", ""),
    ("Product", "Product", "Products", "Product", "", "")
]

class TestPhase1D6CPartialCoverageSafety(unittest.TestCase):

    def setUp(self):
        self.fetch_patcher = patch("semantic.semantic_resolver.SemanticResolver._fetch_active_metadata", return_value=(mock_metrics, mock_dimensions))
        self.load_patcher = patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=MOCK_INDEXED_VALUES)
        
        self.fetch_patcher.start()
        self.load_patcher.start()

    def tearDown(self):
        self.fetch_patcher.stop()
        self.load_patcher.stop()

    def test_children_wear_partial_match_blocked(self):
        """1. 'children wear' has unmatched token 'children', should downgrade to PARTIAL_MATCH and be blocked."""
        res = SemanticResolver.resolve("conn_123", "children wear")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.PARTIAL_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "PARTIAL_MATCH")

    def test_women_wear_partial_match_blocked(self):
        """2. 'women wear' has unmatched token 'women', should downgrade to PARTIAL_MATCH and be blocked."""
        res = SemanticResolver.resolve("conn_123", "women wear")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.PARTIAL_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "PARTIAL_MATCH")

    def test_chennai_hospital_partial_match_blocked(self):
        """3. 'Chennai hospital' has unmatched token 'hospital', should downgrade to PARTIAL_MATCH and be blocked."""
        res = SemanticResolver.resolve("conn_123", "Chennai hospital")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.PARTIAL_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "PARTIAL_MATCH")

    def test_cotton_shirt_partial_match_blocked(self):
        """4. 'cotton shirt' with only 'cotton pants' as candidate has unmatched 'shirt', should be PARTIAL_MATCH/blocked."""
        # Mocking to return only one product match
        one_product_idx = [
            make_cached_value(3, "Product", "Products", "Product", "cotton pants")
        ]
        with patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=one_product_idx):
            res = SemanticResolver.resolve("conn_123", "cotton shirt")
            ambig_res = res.get("ambiguity_result")
            
            self.assertIsNotNone(ambig_res)
            self.assertEqual(ambig_res.status, ResolutionStatus.PARTIAL_MATCH)
            
            gate_res = SemanticGate.evaluate(res)
            self.assertFalse(gate_res["allowed"])
            self.assertEqual(gate_res["status"], "PARTIAL_MATCH")

    def test_cotton_pant_full_coverage_allowed(self):
        """5. 'cotton pant' matches 'cotton pants' with 100% coverage (via singularization), should be SINGLE_MATCH/allowed."""
        res = SemanticResolver.resolve("conn_123", "cotton pant")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.SINGLE_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertTrue(gate_res["allowed"])

    def test_coimbatore_city_dimension_label_allowed(self):
        """6. 'Coimbatore city' -> 'Coimbatore' has unmatched token 'city', but it matches dimension name, so allowed."""
        res = SemanticResolver.resolve("conn_123", "Coimbatore city")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.SINGLE_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertTrue(gate_res["allowed"])

    def test_full_query_coverage_one_candidate_allowed(self):
        """7. Full query coverage ('Chennai') with one candidate -> SINGLE_MATCH / allowed."""
        res = SemanticResolver.resolve("conn_123", "Chennai")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.SINGLE_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertTrue(gate_res["allowed"])

    def test_zero_candidate_no_match_blocked(self):
        """8. Zero candidates -> NO_MATCH / blocked by gate as INSUFFICIENT."""
        res = SemanticResolver.resolve("conn_123", "Laptop")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.NO_MATCH)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "INSUFFICIENT")

    def test_multiple_candidates_ambiguity_unchanged(self):
        """9. Multiple candidates (e.g. 'shirt' matches 'blue shirt' and 'WHITE SHIRT') -> STRONG_AMBIGUITY."""
        res = SemanticResolver.resolve("conn_123", "shirt")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.STRONG_AMBIGUITY)
        
        gate_res = SemanticGate.evaluate(res)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "STRONG_AMBIGUITY")

    def test_partial_match_candidate_preservation(self):
        """10. Partial match must preserve the best candidate internally for clarification."""
        res = SemanticResolver.resolve("conn_123", "children wear")
        ambig_res = res.get("ambiguity_result")
        
        self.assertIsNotNone(ambig_res)
        self.assertEqual(ambig_res.status, ResolutionStatus.PARTIAL_MATCH)
        self.assertIsNotNone(ambig_res.dominant_match)
        self.assertEqual(ambig_res.dominant_match.value, "N--NIGHT WEARS")
        self.assertEqual(ambig_res.dominant_match.matched_query_tokens, ["wear"])


class TestPhase1D6CUserResponse(unittest.TestCase):
    """Step 8: User Response Test at the API/response layer."""

    @patch("services.connection_service.ConnectionService.get_connection")
    @patch("semantic.semantic_service.SemanticService.get_metrics", return_value=[])
    @patch("semantic.semantic_service.SemanticService.get_dimensions", return_value=mock_dimensions)
    @patch("semantic.relationship_service.SemanticRelationshipService.build_relationships", return_value=[])
    @patch("semantic.relevant_table_resolver.RelevantTableResolver.resolve", return_value=[])
    @patch("semantic.relevant_schema_service.RelevantSchemaService.get_schema", return_value="")
    @patch("semantic.query_examples_service.QueryExamplesService.retrieve", return_value=[])
    @patch("semantic.metadata_resolver.MetadataResolver.resolve", return_value={"required_tables": [], "metadata_rules": []})
    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=MOCK_INDEXED_VALUES)
    def test_partial_match_api_response_clarification(self, mock_load, mock_meta, mock_examples, mock_schema, mock_table, mock_rel, mock_dims, mock_mets, mock_conn):
        mock_conn.return_value = {
            "connection_id": "7cdfaca8-5097-4f9c-a521-0bdcd8e912d4",
            "connection_name": "Test Connection",
            "database_type": "mssql"
        }
        
        prompt_builder = PromptBuilder()
        
        # Scenario A: Partial Coverage with a credible candidate -> raise AmbiguityException
        try:
            prompt_builder.build_sql_prompt(
                question="children wear",
                connection_id="7cdfaca8-5097-4f9c-a521-0bdcd8e912d4"
            )
            self.fail("Expected AmbiguityException was not raised")
        except AmbiguityException as ex:
            # 1. Candidate value is presented
            self.assertIn("N--NIGHT WEARS", ex.message)
            # 2. Original query intent is referenced
            self.assertIn("children wear", ex.message)
            # 3. Internal database metadata (like table_name, column_name) is NOT exposed in the message
            self.assertNotIn("Products", ex.message)
            self.assertNotIn("Product", ex.message)
            
            # Check details
            details = ex.details
            self.assertEqual(details["original_question"], "children wear")
            self.assertEqual(details["ambiguity_type"], "PARTIAL_MATCH")
            
            options = details["options"]
            self.assertEqual(len(options), 1)
            opt = options[0]
            self.assertEqual(opt["value"], "N--NIGHT WEARS")
            self.assertEqual(opt["dimension"], "Product")
            # Verify internal metadata (table_name, column_name, etc.) is present in internal exception options for resumption
            self.assertIn("table_name", opt)
            self.assertIn("column_name", opt)
            self.assertIn("dimension_id", opt)
            self.assertIn("match_type", opt)
            self.assertIn("matched_question_tokens", opt)

        # Scenario B: Partial Coverage with NO credible candidate -> raise SemanticRetrievalException
        try:
            prompt_builder.build_sql_prompt(
                question="Laptop",
                connection_id="7cdfaca8-5097-4f9c-a521-0bdcd8e912d4"
            )
            self.fail("Expected SemanticRetrievalException was not raised")
        except SemanticRetrievalException as ex:
            self.assertIn("Laptop", ex.message)
            self.assertIn("couldn't find any data matching", ex.message)
            self.assertNotIn("Products", ex.message)


if __name__ == "__main__":
    unittest.main()
