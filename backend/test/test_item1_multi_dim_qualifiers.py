import sys
import os
import unittest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath('backend'))
sys.path.insert(0, os.path.abspath('backend/test/semantic_benchmark'))

from database import engine
from semantic.semantic_resolver import SemanticResolver
from semantic.semantic_gate import SemanticGate
import run_retrieval_benchmark as runner


def _db_reachable():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "Database not reachable")
class TestItem1MultiDimQualifiers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn_id = runner.resolve_logical_connection()

    # 1. Exact qualifier: "Chennai city" -> City (not District)
    def test_01_exact_qualifier_city(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Show sales for Chennai city")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("City", dims)
        self.assertNotIn("District", dims)

    # 2. Fuzzy qualifier: "coimbator city" -> City = COIMBATORE
    def test_02_fuzzy_qualifier_city(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Show sales for coimbator city")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("City", dims)
        self.assertNotIn("District", dims)

    # 3. Explicit business-type qualifier: "VT business type" -> btype = VT
    def test_03_explicit_btype_qualifier(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="VT business type")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("btype", dims)
        self.assertNotIn("Division", dims)

    # 4. Explicit division qualifier: "VT division" -> Division = VT
    def test_04_explicit_division_qualifier(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="VT division")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("Division", dims)
        self.assertNotIn("btype", dims)

    # 5. Explicit brand qualifier: "Ramraj brand" -> Brand = RAMRAJ
    def test_05_explicit_brand_qualifier(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Ramraj brand")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("Brand", dims)
        self.assertNotIn("Prod Grp1", dims)

    # 6. Explicit product qualifier: "Ramraj Littlestars product group" -> Prod Grp1 = RAMRAJ LITTLESTARS
    def test_06_explicit_product_group_qualifier(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Ramraj Littlestars product group")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("Prod Grp1", dims)
        self.assertNotIn("Brand", dims)

    # 7. Multi-dimension: "Ramraj brand and Franchise mkt type" -> Brand and Mkt Type remain separate
    def test_07_multi_dimension_separation(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Ramraj brand and Franchise mkt type")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("Brand", dims)
        self.assertIn("Mkt Type", dims)

    # 8. Dimension/value disagreement test (synthetic)
    def test_08_dimension_value_disagreement(self):
        # User asks for "VT city". VT exists in Division & btype, NOT in City.
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="VT city")
        vms = res.get("value_matches", [])
        vt_city_vms = [vm for vm in vms if vm.get("value") == "VT" and vm.get("business_name") == "City"]
        self.assertEqual(len(vt_city_vms), 0)

    # 9. Genuine ambiguity: value in multiple dimensions without qualifier
    def test_09_genuine_ambiguity_no_qualifier(self):
        # "VT" without qualifier is valid in Division and btype -> ambiguity
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Show sales for VT")
        amb_obj = res.get("ambiguity_result")
        self.assertIsNotNone(amb_obj)
        self.assertIn(amb_obj.status.value, ("WEAK_AMBIGUITY", "STRONG_AMBIGUITY"))

    # 10. Cross-table safety: filter on Table A + metric on Table B + no relationship -> Blocked
    def test_10_cross_table_safety_gate(self):
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Show sales for Ramraj brand")
        gate_res = SemanticGate.evaluate(res)
        self.assertFalse(gate_res.get("allowed"))
        self.assertEqual(gate_res.get("status"), "UNSUPPORTED_CROSS_TABLE")

    # 11. Regression tests for Step 17a / 19b / 21f
    def test_11_plural_qualifier_regression(self):
        # "Chennai cities" -> City (Step 19b plural handling)
        res = SemanticResolver.resolve(connection_id=self.conn_id, question="Show sales for Chennai cities")
        vms = res.get("value_matches", [])
        dims = {vm.get("business_name") for vm in vms}
        self.assertIn("City", dims)
        self.assertNotIn("District", dims)

    # 12. No RAMRAJ-specific logic: generic synthetic dimension test
    def test_12_generic_synthetic_qualifier_mechanism(self):
        # Proves explicit qualifier mechanism works on any synthetic dimension/value
        from semantic.dimension_value_resolver import DimensionValueResolver

        resolver = DimensionValueResolver()

        # Mock dimension context
        dim_ctx = [
            {"business_name": "AlphaDim", "dimension_name": "AlphaDim", "column_name": "alpha_col", "synonyms": "alpha label"},
            {"business_name": "BetaDim", "dimension_name": "BetaDim", "column_name": "beta_col", "synonyms": "beta label"}
        ]

        # Call _find_matching_dimension
        match_alpha = resolver._find_matching_dimension("alpha label", dim_ctx)
        match_beta = resolver._find_matching_dimension("beta label", dim_ctx)

        self.assertEqual(match_alpha, "AlphaDim")
        self.assertEqual(match_beta, "BetaDim")

    # 13. Synthetic regression test: normalization does NOT overmatch unrelated dimensions
    def test_13_synthetic_no_overmatch(self):
        from semantic.dimension_value_resolver import DimensionValueResolver

        resolver = DimensionValueResolver()

        # Mock unrelated dimension context
        unrelated_dim_ctx = [
            {"business_name": "Customer Segment", "dimension_name": "CustomerSegment", "column_name": "Segment", "synonyms": "segment, channel"},
            {"business_name": "Department Name", "dimension_name": "DepartmentName", "column_name": "DeptName", "synonyms": "department, dept"}
        ]

        # Ensure "prod" or "group" does NOT overmatch "Customer Segment" or "Department Name"
        self.assertIsNone(resolver._find_matching_dimension("prod", unrelated_dim_ctx))
        self.assertIsNone(resolver._find_matching_dimension("group", unrelated_dim_ctx))
        self.assertIsNone(resolver._find_matching_dimension("product group", unrelated_dim_ctx))
        
        # Ensure correct synonyms match cleanly
        self.assertEqual(resolver._find_matching_dimension("dept", unrelated_dim_ctx), "Department Name")
        self.assertEqual(resolver._find_matching_dimension("channel", unrelated_dim_ctx), "Customer Segment")


if __name__ == "__main__":
    unittest.main(verbosity=2)
