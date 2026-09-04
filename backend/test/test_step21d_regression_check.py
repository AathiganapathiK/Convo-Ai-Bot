"""
Gate 3 Step 21d - F. Regression coverage against the live database.

These are integration-style checks (real DB, read-only SELECTs through
SemanticResolver) rather than unit tests, because they exist specifically to
prove the RC-02 exemption fix did not disturb behavior this session already
verified: the genuine-alternative filter, 21b's table-affinity dominance, and
21c's clarification gate/options. Skipped automatically if the configured
database is unreachable, matching this project's existing pattern for
DB-backed tests (see dev-environment-notes memory).
"""
import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _db_reachable():
    try:
        import core.config  # noqa - loads the active .env
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestStep21dLiveRegressionCheck(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        from semantic.dimension_value_resolver import DimensionValueResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.DimensionValueResolver = DimensionValueResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _resolve(self, question):
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        rr = self.DimensionValueResolver.last_resolution_result
        return res, rr

    def test_pending_amount_metric_words_not_wrongly_flagged(self):
        # E1-032/E1-033 shape. Confirms the metric-vocabulary exemption did
        # not introduce a NEW value-identity error - it should only ever
        # change the ambiguity STATUS, never which value/metric was picked.
        for q in ["Show pending amount for Chennai city", "Pending amount in Madurai city"]:
            res, rr = self._resolve(q)
            vm = res.get("value_matches") or []
            self.assertTrue(vm, f"expected at least one resolved value for: {q}")
            self.assertIn(vm[0]["value"], ("CHENNAI", "MADURAI"))

    def test_vt_cases_table_affinity_dominance_unchanged(self):
        # E1-097/E1-098/E1-063/E1-170. The RC-02 fix must only ever remove a
        # downgrade to PARTIAL_MATCH - it must never change WHICH candidate
        # is dominant, and must never turn WEAK_AMBIGUITY into SINGLE_MATCH
        # or STRONG_AMBIGUITY (that is 21b's dominance decision, untouched).
        cases = {
            "Show sales for VT division": "WEAK_AMBIGUITY",
            "Show sales for VT": "WEAK_AMBIGUITY",
            "Total sales for VT": "WEAK_AMBIGUITY",       # was PARTIAL_MATCH before this fix
            "Now show sales for VT division": "WEAK_AMBIGUITY",  # was PARTIAL_MATCH before this fix
        }
        for q, expected_status in cases.items():
            _, rr = self._resolve(q)
            self.assertEqual(rr.status.value, expected_status, msg=q)
            self.assertIsNotNone(rr.dominant_match, msg=q)
            self.assertEqual(rr.dominant_match.table_name, "QB_MDJMD_SALES_5YRS_SUMMARY", msg=q)
            self.assertEqual(rr.dominant_match.column_name, "Division", msg=q)

    def test_21c_gate_and_clarification_still_reached_for_genuine_ambiguity(self):
        # "children wear" / "women wear" must still resolve to PARTIAL_MATCH
        # with both genuine values retained (21c's target), unaffected by
        # the RC-02 change (neither question contains a newly-exempted word).
        from semantic.semantic_gate import SemanticGate
        for q in ["Total sales for children wear", "Total sales for women wear"]:
            res, rr = self._resolve(q)
            vm = res.get("value_matches") or []
            self.assertEqual(rr.status.value, "PARTIAL_MATCH", msg=q)
            self.assertEqual({v["value"] for v in vm}, {"ETHNIC WEAR", "N--NIGHT WEARS"}, msg=q)
            gate = SemanticGate.evaluate({"retrieval": res.get("retrieval"),
                                           "ambiguity_result": rr,
                                           "value_matches": vm})
            self.assertFalse(gate["allowed"], msg=q)

    def test_21c_single_genuine_value_still_allowed(self):
        # Chennai city / VT: a single genuine value must still pass the gate
        # (21c's other half) - the RC-02 fix changing the status label from
        # PARTIAL_MATCH to WEAK_AMBIGUITY for the VT cases must not, by
        # itself, cause the gate to start blocking a single-value result.
        from semantic.semantic_gate import SemanticGate
        for q in ["Show sales for Chennai city", "Show sales for VT"]:
            res, rr = self._resolve(q)
            vm = res.get("value_matches") or []
            self.assertEqual(len(vm), 1, msg=q)
            gate = SemanticGate.evaluate({"retrieval": res.get("retrieval"),
                                           "ambiguity_result": rr,
                                           "value_matches": vm})
            self.assertTrue(gate["allowed"], msg=q)


if __name__ == "__main__":
    unittest.main()
