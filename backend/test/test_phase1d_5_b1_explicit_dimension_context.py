import unittest
from unittest.mock import patch
from semantic.matching.models import MatchResult, MatchType, CachedDimensionValue, QuestionContext
from semantic.dimension_value_resolver import DimensionValueResolver


class TestExplicitDimensionContext(unittest.TestCase):
    def setUp(self):
        # Build mock CachedDimensionValue items to avoid connecting to the database
        self.mock_indexed_values = [
            CachedDimensionValue(
                semantic_dimension_id=1,
                business_name="Brand",
                table_name="Products",
                column_name="Brand",
                value="Ramraj Pant",
                normalized_value="ramraj pant",
                runtime_stored_norm="ramraj pant",
                runtime_stored_tokens=["ramraj", "pant"],
                runtime_stored_singulars=["ramraj", "pant"],
                runtime_raw_norm="ramraj pant",
                runtime_raw_tokens=["ramraj", "pant"],
                runtime_raw_singulars=["ramraj", "pant"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=1,
                business_name="Brand",
                table_name="Products",
                column_name="Brand",
                value="Linen Pant",
                normalized_value="linen pant",
                runtime_stored_norm="linen pant",
                runtime_stored_tokens=["linen", "pant"],
                runtime_stored_singulars=["linen", "pant"],
                runtime_raw_norm="linen pant",
                runtime_raw_tokens=["linen", "pant"],
                runtime_raw_singulars=["linen", "pant"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=1,
                business_name="Brand",
                table_name="Products",
                column_name="Brand",
                value="Ramraj",
                normalized_value="ramraj",
                runtime_stored_norm="ramraj",
                runtime_stored_tokens=["ramraj"],
                runtime_stored_singulars=["ramraj"],
                runtime_raw_norm="ramraj",
                runtime_raw_tokens=["ramraj"],
                runtime_raw_singulars=["ramraj"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=2,
                business_name="Product Group",
                table_name="Products",
                column_name="ProductGroup",
                value="Cotton Pants",
                normalized_value="cotton pants",
                runtime_stored_norm="cotton pants",
                runtime_stored_tokens=["cotton", "pants"],
                runtime_stored_singulars=["cotton", "pant"],
                runtime_raw_norm="cotton pants",
                runtime_raw_tokens=["cotton", "pants"],
                runtime_raw_singulars=["cotton", "pant"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=3,
                business_name="City",
                table_name="Customers",
                column_name="City",
                value="Coimbatore",
                normalized_value="coimbatore",
                runtime_stored_norm="coimbatore",
                runtime_stored_tokens=["coimbatore"],
                runtime_stored_singulars=["coimbatore"],
                runtime_raw_norm="coimbatore",
                runtime_raw_tokens=["coimbatore"],
                runtime_raw_singulars=["coimbatore"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=4,
                business_name="State",
                table_name="Customers",
                column_name="State",
                value="Tamil Nadu",
                normalized_value="tamil nadu",
                runtime_stored_norm="tamil nadu",
                runtime_stored_tokens=["tamil", "nadu"],
                runtime_stored_singulars=["tamil", "nadu"],
                runtime_raw_norm="tamil nadu",
                runtime_raw_tokens=["tamil", "nadu"],
                runtime_raw_singulars=["tamil", "nadu"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=5,
                business_name="State",
                table_name="Customers",
                column_name="State",
                value="Coimbatore",
                normalized_value="coimbatore",
                runtime_stored_norm="coimbatore",
                runtime_stored_tokens=["coimbatore"],
                runtime_stored_singulars=["coimbatore"],
                runtime_raw_norm="coimbatore",
                runtime_raw_tokens=["coimbatore"],
                runtime_raw_singulars=["coimbatore"]
            )
        ]

        # Dimension Context mimicking database schemas
        self.dimension_context = [
            {"dimension_name": "Brand", "business_name": "Brand", "table_name": "Products", "column_name": "Brand"},
            {"dimension_name": "ProductGroup", "business_name": "Product Group", "table_name": "Products", "column_name": "ProductGroup"},
            {"dimension_name": "City", "business_name": "City", "table_name": "Customers", "column_name": "City"},
            {"dimension_name": "State", "business_name": "State", "table_name": "Customers", "column_name": "State"}
        ]

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_1_brand_ramraj_pant(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "brand ramraj pant", dimension_context=self.dimension_context)
        # Should resolve uniquely to Brand / Ramraj Pant since "brand" is adjacent and filters out other dimensions
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Ramraj Pant")
        self.assertEqual(results[0]["business_name"], "Brand")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_2_ramraj_pant_brand(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "ramraj pant brand", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Ramraj Pant")
        self.assertEqual(results[0]["business_name"], "Brand")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_3_city_coimbatore(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "city coimbatore", dimension_context=self.dimension_context)
        # Without context, Coimbatore is ambiguous between City and State. With "city" prefix, it must be City.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Coimbatore")
        self.assertEqual(results[0]["business_name"], "City")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_4_coimbatore_city(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "coimbatore city", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Coimbatore")
        self.assertEqual(results[0]["business_name"], "City")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_5_state_tamil_nadu(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "state tamil nadu", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Tamil Nadu")
        self.assertEqual(results[0]["business_name"], "State")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_6_tamil_nadu_state(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "tamil nadu state", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Tamil Nadu")
        self.assertEqual(results[0]["business_name"], "State")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_7_brand_ramraj(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        results = resolver.resolve_matches("dummy-conn", "brand ramraj", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Ramraj")
        self.assertEqual(results[0]["business_name"], "Brand")

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_8_city_xyz(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        # Even if a matching candidate might exist under a different dimension, city xyz must not fall back to it
        results = resolver.resolve_matches("dummy-conn", "city xyz", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 0)

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_9_show_brand_sales_for_coimbatore(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        # "brand" is distant (separated by sales/for). Coimbatore must NOT be treated as Brand.
        # Since Coimbatore is ambiguous between City and State, it must return BOTH candidates.
        results = resolver.resolve_matches("dummy-conn", "show brand sales for coimbatore", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 2)
        business_names = {r["business_name"] for r in results}
        self.assertEqual(business_names, {"City", "State"})

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_10_show_sales_for_pant(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        # Normal query without explicit dimension label -> returns multiple candidates (ambiguity)
        results = resolver.resolve_matches("dummy-conn", "show sales for pant", dimension_context=self.dimension_context)
        self.assertGreater(len(results), 1)

    @patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values")
    def test_11_explicit_dimension_multiple_candidates(self, mock_load):
        mock_load.return_value = self.mock_indexed_values
        resolver = DimensionValueResolver()
        # brand pant -> returns both "Ramraj Pant" and "Linen Pant" because they are both Brand
        results = resolver.resolve_matches("dummy-conn", "brand pant", dimension_context=self.dimension_context)
        self.assertEqual(len(results), 2)
        business_names = {r["business_name"] for r in results}
        self.assertEqual(business_names, {"Brand"})

    def test_12_client_cannot_supply_dimension_id(self):
        # Verify app.py asks endpoint does not have parameters for client-provided dimension_context or dimension_id
        import inspect
        from app import ask_question
        sig = inspect.signature(ask_question)
        self.assertNotIn("dimension_id", sig.parameters)
        self.assertNotIn("dimension_context", sig.parameters)


if __name__ == "__main__":
    unittest.main()
