"""
Gate 3 - collapse an all-unreachable STRONG_AMBIGUITY tie.

Root cause: "Show sales for Chennai" ties City against District (both on
PBI_OUTSTANDING_ENES_SUMMARY, neither reachable from Sales via any verified
schema relationship). AmbiguityClassifier.classify() correctly cannot break
that tie on its own evidence (table_affinity is 0 for both candidates), but
asking the user to disambiguate between two answers that are BOTH dead ends
is not a real clarification.

DimensionValueResolver.resolve_matches()'s STRONG_AMBIGUITY fallthrough now
checks, strictly AFTER classify() has already decided the tie, whether every
tied candidate is unreachable from the resolved metric's table (the same
RelationshipExpander graph SemanticGate itself checks). Only then does the
candidate list collapse to empty. This runs after classification, not
during it, so it cannot influence which candidates competed - "Show sales
for VT" (Division vs btype) is untouched because that tie is resolved
INSIDE classify() via table_affinity, long before this code runs, and never
reaches this branch as a mixed group.

DB-gated, following this session's established pattern for live-resolver
tests.

    python -m unittest backend.test.test_strong_ambiguity_all_unreachable
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _db_reachable():
    try:
        import core.config  # noqa
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestAllUnreachableStrongAmbiguityCollapse(unittest.TestCase):

    SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
    OUTSTANDING = "PBI_OUTSTANDING_ENES_SUMMARY"
    ORDER_PENDING = "PBI_ENES_ORDER_PENDING_SUMMARY"

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        from semantic.semantic_gate import SemanticGate
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.SemanticGate = SemanticGate
        cls.conn_id = runner.resolve_logical_connection()

    def _resolve(self, question):
        return self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)

    # 1 - the traced case: a genuine tie where EVERY candidate is
    # unreachable from Sales collapses to an empty candidate list.
    def test_bare_chennai_collapses_all_unreachable_tie(self):
        res = self._resolve("Show sales for Chennai")
        amb = res.get("ambiguity_result")
        self.assertEqual(amb.status.value, "STRONG_AMBIGUITY")
        self.assertEqual(res.get("value_matches"), [])
        # The metric itself still resolves - only the dead-end tie is gone.
        self.assertTrue(
            any(m.get("table_name") == self.SALES
                for m in (res.get("metric_objects") or []))
        )

    # 2 - "VT" (Division vs btype) is a MIXED tie - Division is reachable
    # (it IS the metric's own table) - must never collapse.
    def test_vt_mixed_reachability_is_not_collapsed(self):
        res = self._resolve("Show sales for VT")
        values = [(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])]
        self.assertIn(("Division", self.SALES, "VT"), values)
        self.assertEqual(res.get("retrieval", {}).get("status"), "COMPLETE")
        gate = self.SemanticGate.evaluate(res)
        self.assertTrue(gate["allowed"])

    # 3 - explicit qualifier ("Chennai city") already narrows to WEAK_AMBIGUITY
    # before this code ever runs - untouched, still correctly cross-table
    # blocked by the unchanged SemanticGate check.
    def test_chennai_city_explicit_qualifier_unaffected(self):
        res = self._resolve("Show sales for Chennai city")
        values = [(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])]
        self.assertIn(("City", self.OUTSTANDING, "CHENNAI"), values)
        gate = self.SemanticGate.evaluate(res)
        self.assertEqual(gate["status"], "UNSUPPORTED_CROSS_TABLE")
        self.assertFalse(gate["allowed"])

    # 4 - "Ramraj brand" is SINGLE_MATCH, never reaches the STRONG_AMBIGUITY
    # branch at all - untouched, still correctly cross-table blocked.
    def test_ramraj_brand_unaffected(self):
        res = self._resolve("Show sales for Ramraj brand")
        values = [(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])]
        self.assertIn(("Brand", self.ORDER_PENDING, "RAMRAJ"), values)
        gate = self.SemanticGate.evaluate(res)
        self.assertEqual(gate["status"], "UNSUPPORTED_CROSS_TABLE")
        self.assertFalse(gate["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
