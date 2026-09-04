"""
Gate 3 - AmbiguityClassifier._compute_query_coverage()'s FUZZY branch reads
matched_question_tokens_precise, not the raw matched_question_tokens span.

Root cause: "Show sales for Chennai city and Ramraj brand" fuzzy-matched
RAMRAJ PANT against a wide n-gram window whose raw matched_question_tokens
was ['chennai', 'city', 'ramraj'] - only "ramraj" is genuine evidence for
RAMRAJ PANT, but the raw span credited it with "chennai"/"city" too. Since
_competes() reads AmbiguityChoice.matched_query_tokens (computed by this
method) to decide what competes, the over-wide credit bridged the
independently-qualified City concept (CHENNAI) and Brand concept (RAMRAJ)
into one false STRONG_AMBIGUITY tie instead of two MULTI_MATCH resolutions.

DB-gated, following this session's established pattern for live-resolver
tests.

    python -m unittest backend.test.test_fuzzy_precise_token_grouping
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
class TestFuzzyPreciseTokenGrouping(unittest.TestCase):

    SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
    OUTSTANDING = "PBI_OUTSTANDING_ENES_SUMMARY"
    ORDER_PENDING = "PBI_ENES_ORDER_PENDING_SUMMARY"

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _resolve(self, question):
        return self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)

    # 1 - the traced case: two independently-qualified concepts must combine
    # as MULTI_MATCH, not bridge into a false STRONG_AMBIGUITY tie.
    def test_chennai_city_and_ramraj_brand_is_multi_match(self):
        res = self._resolve("Show sales for Chennai city and Ramraj brand")
        amb = res.get("ambiguity_result")
        self.assertEqual(amb.status.value, "MULTI_MATCH")
        values = {(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])}
        self.assertEqual(
            values,
            {("City", self.OUTSTANDING, "CHENNAI"),
             ("Brand", self.ORDER_PENDING, "RAMRAJ")},
        )

    # 2 - solo "Chennai city" unaffected: still WEAK_AMBIGUITY, CHENNAI dominant.
    def test_chennai_city_solo_unaffected(self):
        res = self._resolve("Show sales for Chennai city")
        amb = res.get("ambiguity_result")
        self.assertEqual(amb.status.value, "WEAK_AMBIGUITY")
        values = [(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])]
        self.assertIn(("City", self.OUTSTANDING, "CHENNAI"), values)

    # 3 - solo "Ramraj brand" unaffected: still SINGLE_MATCH.
    def test_ramraj_brand_solo_unaffected(self):
        res = self._resolve("Show sales for Ramraj brand")
        amb = res.get("ambiguity_result")
        self.assertEqual(amb.status.value, "SINGLE_MATCH")
        values = [(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])]
        self.assertEqual(values, [("Brand", self.ORDER_PENDING, "RAMRAJ")])

    # 4 - "VT" (Division vs btype, resolved via table_affinity inside
    # classify()) unaffected - this fix never touches that mechanism.
    def test_vt_ambiguity_resolution_unaffected(self):
        res = self._resolve("Show sales for VT")
        amb = res.get("ambiguity_result")
        self.assertEqual(amb.status.value, "WEAK_AMBIGUITY")
        values = [(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])]
        self.assertIn(("Division", self.SALES, "VT"), values)

    # 5 - "coimbator city" (a genuine fuzzy same-column tie: COIMBATORE vs
    # ELECTRONIC CITY, both explicitly qualified) must remain a real
    # STRONG_AMBIGUITY - this fix must not accidentally suppress a
    # legitimate tie within one concept.
    def test_coimbator_city_genuine_tie_preserved(self):
        res = self._resolve("Show sales for coimbator city")
        amb = res.get("ambiguity_result")
        self.assertEqual(amb.status.value, "STRONG_AMBIGUITY")
        values = {(v.get("business_name"), v.get("table_name"), v.get("value"))
                  for v in (res.get("value_matches") or [])}
        self.assertEqual(
            values,
            {("City", self.OUTSTANDING, "ELECTRONIC CITY"),
             ("City", self.OUTSTANDING, "COIMBATORE")},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
