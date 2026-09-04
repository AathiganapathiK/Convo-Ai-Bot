"""
Gate 3 Step 21a - an explicit value that does not resolve blocks execution.

ResolutionStatus.NO_MATCH was produced by the matching pipeline and read by
nothing, so a question naming a value that does not exist still came back
executable:

    "Show sales for xyzabc"  ->  metrics=['C Y'], values=[], PARTIAL

which answers "all sales" - a question the user did not ask.

The frozen rule: an explicit value reference that does not resolve sets
retrieval_status = INSUFFICIENT, and the existing SemanticGate refuses to
generate SQL for that status.

Two properties matter as much as the fix itself, and both are pinned here:

  * resolved metrics and dimensions are KEPT, so a clarification can say what
    was understood as well as what was not found;
  * the trigger does not widen. An unknown word that names nothing ("orders",
    "compare") must not block a perfectly answerable question.

Requires the live connection; skipped when unavailable.
"""

import unittest

try:
    import core.config  # noqa: F401
    from semantic.semantic_resolver import SemanticResolver
    from semantic.semantic_gate import SemanticGate
    from services.connection_service import ConnectionService

    _conn = ConnectionService.get_active_connection_global()
    CONNECTION_ID = _conn["connection_id"] if _conn else None
except Exception:
    CONNECTION_ID = None


@unittest.skipIf(not CONNECTION_ID, "no active connection")
class TestExplicitValueNoMatch(unittest.TestCase):

    def resolve(self, question):
        result = SemanticResolver.resolve(CONNECTION_ID, question)
        retrieval = result.get("retrieval") or {}
        return {
            "metrics": [m.get("business_name") for m in result.get("metric_objects", [])],
            "dimensions": [d.get("business_name") for d in result.get("dimension_objects", [])],
            "values": [v.get("value") for v in (result.get("value_matches") or [])],
            "status": retrieval.get("status"),
            "reason": retrieval.get("reason") or "",
            "unresolved_terms": retrieval.get("unresolved_terms"),
            "gate": SemanticGate.evaluate(result),
        }

    # -- unknown explicit value -> INSUFFICIENT --------------------------

    def test_unknown_value_after_preposition_is_insufficient(self):
        r = self.resolve("Show sales for xyzabc")

        self.assertEqual(r["status"], "INSUFFICIENT")
        self.assertIn("xyzabc", r["unresolved_terms"])
        self.assertEqual(r["values"], [], "no value may be substituted")

    def test_unknown_value_on_another_table(self):
        r = self.resolve("Show quantity for qwert")

        self.assertEqual(r["status"], "INSUFFICIENT")
        self.assertIn("qwert", r["unresolved_terms"])

    # -- the existing gate blocks it -------------------------------------

    def test_semantic_gate_blocks_insufficient(self):
        # No second blocking mechanism was added; this is the gate that
        # already existed refusing the status the resolver now reports.
        r = self.resolve("Show sales for xyzabc")

        self.assertFalse(r["gate"]["allowed"])
        self.assertEqual(r["gate"]["status"], "INSUFFICIENT")

    # -- what was understood survives, for the clarification -------------

    def test_resolved_metric_is_retained_for_clarification(self):
        r = self.resolve("Show sales for xyzabc")

        self.assertEqual(r["metrics"], ["C Y"],
                         "the metric must survive so the clarification can say "
                         "what was understood")

    def test_reason_names_the_unresolved_term(self):
        r = self.resolve("Show sales for xyzabc")

        self.assertIn("xyzabc", r["reason"])
        self.assertIn("does not match any known value", r["reason"])

    # -- known values are untouched --------------------------------------

    def test_known_value_resolves_normally(self):
        r = self.resolve("Show sales for Chennai city")

        self.assertEqual(r["status"], "COMPLETE")
        self.assertIn("CHENNAI", r["values"])
        self.assertTrue(r["gate"]["allowed"])
        self.assertEqual(r["unresolved_terms"], [])

    def test_known_value_on_product_dimension(self):
        r = self.resolve("Show sales for BANIANS")

        self.assertIn("BANIANS", r["values"])
        self.assertNotEqual(r["status"], "INSUFFICIENT")

    # -- no explicit value -> no false blocking --------------------------

    def test_question_with_no_value_is_not_blocked(self):
        # "Show quantity" names nothing to look up. That is an optional slot,
        # not a failed lookup.
        r = self.resolve("Show quantity")

        self.assertEqual(r["status"], "PARTIAL")
        self.assertTrue(r["gate"]["allowed"])
        self.assertEqual(r["unresolved_terms"], [])

    def test_unknown_word_that_names_nothing_does_not_block(self):
        # "orders" is outside the configured vocabulary but is not an entity
        # reference. Blocking here would refuse an answerable question.
        r = self.resolve("Show last year pending orders")

        self.assertNotEqual(r["status"], "INSUFFICIENT")
        self.assertTrue(r["gate"]["allowed"])

    def test_verb_outside_vocabulary_does_not_block(self):
        r = self.resolve("compare current year and previous year sales")

        self.assertNotEqual(r["status"], "INSUFFICIENT")
        self.assertTrue(r["gate"]["allowed"])

    def test_temporal_question_is_not_blocked(self):
        r = self.resolve("Show sales this year")

        self.assertNotEqual(r["status"], "INSUFFICIENT")
        self.assertTrue(r["gate"]["allowed"])


if __name__ == "__main__":
    unittest.main()
