"""
Gate 3 Item #2 - follow-up metric carry-over.

Root cause: metric resolution in SemanticResolver.resolve() runs on the
current question's text only. A follow-up naming a new dimension/value but
no metric ("How about Ramraj brand?") resolved zero metrics even though a
metric was clearly implied by the previous turn - previous_semantic_context
was forwarded only to DimensionValueResolver for value/dimension
inheritance, never consulted for the metric.

The fix carries the previous turn's metric into metric_objects only when:
  - the current turn resolved no metric of its own (an explicit current-turn
    metric always wins - this block never runs otherwise)
  - previous_semantic_context names EXACTLY ONE previous metric
  - the current question has at least one non-stopword token

DB-gated, following this session's established pattern for live-resolver
tests (test_rc03a_metric_semantics.py, test_value_family_ramraj.py).

    python backend/test/test_item2_followup_metric_carryover.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _db_reachable():
    try:
        import core.config  # noqa
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestFollowupMetricCarryover(unittest.TestCase):

    CY = ("QB_MDJMD_SALES_5YRS_SUMMARY", "CY")
    QTY = ("PBI_ENES_ORDER_PENDING_SUMMARY", "Qty")

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _turn1_context(self, question):
        """The exact shape ai/prompt_builder.py stores for the next turn."""
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        return {
            "metrics": [
                {"metric_name": m.get("metric_name"), "business_name": m.get("business_name"),
                 "table_name": m.get("table_name"), "column_name": m.get("column_name")}
                for m in (res.get("metric_objects") or [])
            ],
            "dimensions": [
                {"business_name": d.get("business_name"), "dimension_name": d.get("dimension_name"),
                 "table_name": d.get("table_name"), "column_name": d.get("column_name")}
                for d in (res.get("dimension_objects") or [])
            ],
            "resolved_values": [
                {"business_name": v.get("business_name"), "value": v.get("value"),
                 "table_name": v.get("table_name"), "column_name": v.get("column_name")}
                for v in (res.get("value_matches") or [])
            ],
        }

    def _metric_identities(self, question, previous_semantic_context=None):
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id, question=question,
            previous_semantic_context=previous_semantic_context,
        )
        return [(m.get("table_name"), m.get("column_name"))
                for m in (res.get("metric_objects") or [])]

    # -- 1. metric carry-over ------------------------------------------------

    def test_1_sales_metric_carries_into_ramraj_brand_followup(self):
        prev = self._turn1_context("Show sales for Chennai")
        self.assertEqual(prev["metrics"], [{
            "metric_name": "cy", "business_name": "C Y",
            "table_name": self.CY[0], "column_name": self.CY[1],
        }])
        got = self._metric_identities("How about Ramraj brand?", prev)
        self.assertEqual(got, [self.CY])

    def test_1b_quantity_metric_carries_into_ramraj_brand_followup(self):
        prev = self._turn1_context("Show quantity for Chennai")
        got = self._metric_identities("How about Ramraj brand?", prev)
        self.assertEqual(got, [self.QTY])

    def test_1c_bare_value_followup_with_no_dimension_word_also_carries(self):
        # "Mumbai" alone matches no dimension NAME - only the guard on
        # question content, not a literal dimension match, lets this carry.
        prev = self._turn1_context("Show sales for Chennai")
        got = self._metric_identities("What about Mumbai?", prev)
        self.assertEqual(got, [self.CY])

    # -- 2. explicit metric override -----------------------------------------

    def test_2_explicit_current_turn_metric_overrides_previous(self):
        prev = self._turn1_context("Show sales for Chennai")
        got = self._metric_identities("What about quantity for Ramraj?", prev)
        self.assertEqual(got, [self.QTY])
        self.assertNotIn(self.CY, got)

    # -- 3. dimension/value replacement or addition --------------------------

    def test_3_carried_metric_combines_with_new_dimension_value(self):
        prev = self._turn1_context("Show sales for Chennai")
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id, question="How about Ramraj brand?",
            previous_semantic_context=prev,
        )
        metric_ids = [(m.get("table_name"), m.get("column_name"))
                     for m in (res.get("metric_objects") or [])]
        values = [(v.get("value") or "").upper() for v in (res.get("value_matches") or [])]
        self.assertEqual(metric_ids, [self.CY])
        self.assertIn("RAMRAJ", values)

    # -- 4. no prior context -> no guessing -----------------------------------

    def test_4a_no_previous_context_at_all_does_not_guess(self):
        got = self._metric_identities("How about Ramraj brand?", None)
        self.assertEqual(got, [])

    def test_4b_previous_turn_with_zero_metrics_does_not_guess(self):
        prev = {"metrics": [], "dimensions": [{"business_name": "City"}],
                "resolved_values": [{"business_name": "City", "value": "CHENNAI"}]}
        got = self._metric_identities("How about Ramraj brand?", prev)
        self.assertEqual(got, [])

    # -- 5. ambiguous prior context -> safe handling --------------------------

    def test_5_previous_turn_with_two_metrics_is_ambiguous_does_not_guess(self):
        prev = {
            "metrics": [
                {"metric_name": "cy", "business_name": "C Y",
                 "table_name": self.CY[0], "column_name": self.CY[1]},
                {"metric_name": "py", "business_name": "P Y",
                 "table_name": self.CY[0], "column_name": "PY"},
            ],
            "dimensions": [], "resolved_values": [],
        }
        got = self._metric_identities("How about Ramraj brand?", prev)
        self.assertEqual(got, [],
                         "an ambiguous (multi-metric) previous turn must not be guessed from")

    # -- 6. RAMRAJ follow-up regression ---------------------------------------

    def test_6_ramraj_family_still_expands_on_a_followup_turn(self):
        prev = self._turn1_context("Show sales for Chennai")
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id, question="How about Ramraj brand?",
            previous_semantic_context=prev,
        )
        vm = res.get("value_matches") or []
        values = [(v.get("value") or "").upper() for v in vm]
        self.assertIn("RAMRAJ", values, msg=vm)
        self.assertFalse(
            len(vm) == 1 and values[0] == "RAMRAJ LITTLESTARS",
            "must not collapse to one arbitrary product line on a follow-up turn",
        )

    def test_6b_cross_table_safety_gate_still_applies_on_followup(self):
        from semantic.semantic_gate import SemanticGate
        prev = self._turn1_context("Show sales for Chennai")
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id, question="How about Ramraj brand?",
            previous_semantic_context=prev,
        )
        gate = SemanticGate.evaluate(res)
        # Brand (order_pending) has no verified join to the Sales metric
        # table - the same cross-table protection already proven for a
        # first-turn RAMRAJ question must still fire on a follow-up turn.
        self.assertFalse(gate.get("allowed"))

    # -- 7. unrelated existing follow-up behaviour unchanged ------------------

    def test_7_first_turn_metric_resolution_is_unaffected(self):
        # No previous_semantic_context supplied - the carry-over block must
        # not run and ordinary first-turn resolution must be identical.
        got = self._metric_identities("Show sales for Chennai")
        self.assertEqual(got, [self.CY])

    def test_7b_a_followup_that_already_names_its_own_metric_is_unaffected(self):
        prev = self._turn1_context("Show sales for Chennai")
        got = self._metric_identities("Show quantity for Chennai", prev)
        self.assertEqual(got, [self.QTY])


if __name__ == "__main__":
    unittest.main(verbosity=2)
