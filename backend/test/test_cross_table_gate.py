import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from collections import defaultdict

sys.path.insert(0, os.path.abspath('backend'))
sys.path.insert(0, os.path.abspath('.'))

from semantic.semantic_gate import SemanticGate


class TestGenericCrossTableGate(unittest.TestCase):
    """
    Tests for generic cross-table reachability check in SemanticGate.
    Ensures unjoinable cross-table dimension/metric pairs block SQL generation,
    while connected tables and same-table queries remain allowed.
    """

    def test_1_cross_table_no_relationship_blocked(self):
        """Cross-table filter + metric + NO verified relationship -> blocked."""
        semantic_result = {
            "connection_id": "conn-test-1",
            "metric_objects": [{"table_name": "SalesTable", "metric_name": "Sales"}],
            "dimension_objects": [],
            "value_matches": [{"table_name": "PendingTable", "business_name": "Brand", "value": "RAMRAJ"}],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0}
        }
        with patch("semantic.relationship_expander.RelationshipExpander.build_graph", return_value=defaultdict(set)):
            res = SemanticGate.evaluate(semantic_result)
            self.assertFalse(res["allowed"])
            self.assertEqual(res["status"], "UNSUPPORTED_CROSS_TABLE")
            self.assertIn("SalesTable", res["reason"])
            self.assertIn("PendingTable", res["reason"])

    def test_2_cross_table_with_relationship_allowed(self):
        """Cross-table filter + verified relationship/path -> allowed."""
        semantic_result = {
            "connection_id": "conn-test-2",
            "metric_objects": [{"table_name": "SalesTable", "metric_name": "Sales"}],
            "dimension_objects": [],
            "value_matches": [{"table_name": "CustomerTable", "business_name": "Customer", "value": "Acme"}],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0}
        }
        graph = defaultdict(set, {
            "SalesTable": {"CustomerTable"},
            "CustomerTable": {"SalesTable"}
        })
        with patch("semantic.relationship_expander.RelationshipExpander.build_graph", return_value=graph):
            res = SemanticGate.evaluate(semantic_result)
            self.assertTrue(res["allowed"])
            self.assertEqual(res["status"], "COMPLETE")

    def test_3_same_table_filter_and_metric_allowed(self):
        """Same-table filter + metric -> unchanged and allowed."""
        semantic_result = {
            "connection_id": "conn-test-3",
            "metric_objects": [{"table_name": "SalesTable", "metric_name": "Sales"}],
            "dimension_objects": [{"table_name": "SalesTable", "business_name": "ProdGrp1"}],
            "value_matches": [{"table_name": "SalesTable", "business_name": "ProdGrp1", "value": "Shirt"}],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0}
        }
        with patch("semantic.relationship_expander.RelationshipExpander.build_graph", return_value=defaultdict(set)):
            res = SemanticGate.evaluate(semantic_result)
            self.assertTrue(res["allowed"])
            self.assertEqual(res["status"], "COMPLETE")

    def test_4_ramraj_brand_to_sales_specifically_blocked(self):
        """RAMRAJ Brand -> Sales specifically blocks because no verified path exists."""
        conn_id = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
        semantic_result = {
            "connection_id": conn_id,
            "metric_objects": [{"table_name": "QB_MDJMD_SALES_5YRS_SUMMARY", "metric_name": "sales"}],
            "dimension_objects": [],
            "value_matches": [{"table_name": "PBI_ENES_ORDER_PENDING_SUMMARY", "business_name": "Brand", "value": "RAMRAJ"}],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0}
        }
        with patch("semantic.relationship_expander.RelationshipExpander.build_graph", return_value=defaultdict(set)):
            res = SemanticGate.evaluate(semantic_result)
            self.assertFalse(res["allowed"])
            self.assertEqual(res["status"], "UNSUPPORTED_CROSS_TABLE")
            self.assertIn("PBI_ENES_ORDER_PENDING_SUMMARY", res["reason"])
            self.assertIn("QB_MDJMD_SALES_5YRS_SUMMARY", res["reason"])

    def test_5_no_regression_to_existing_gate_behavior(self):
        """No regression to existing SemanticGate status checks (INSUFFICIENT, WEAK_AMBIGUITY, STRONG_AMBIGUITY)."""
        insufficient_res = {
            "retrieval": {"status": "INSUFFICIENT", "confidence": 0.0}
        }
        res_insuf = SemanticGate.evaluate(insufficient_res)
        self.assertFalse(res_insuf["allowed"])
        self.assertEqual(res_insuf["status"], "INSUFFICIENT")

        ambig_mock = MagicMock()
        from semantic.matching.models import ResolutionStatus
        ambig_mock.status = ResolutionStatus.STRONG_AMBIGUITY
        strong_ambig_res = {
            "retrieval": {"status": "COMPLETE", "confidence": 0.5},
            "ambiguity_result": ambig_mock
        }
        res_ambig = SemanticGate.evaluate(strong_ambig_res)
        self.assertFalse(res_ambig["allowed"])
        self.assertEqual(res_ambig["status"], "STRONG_AMBIGUITY")


if __name__ == "__main__":
    unittest.main()
