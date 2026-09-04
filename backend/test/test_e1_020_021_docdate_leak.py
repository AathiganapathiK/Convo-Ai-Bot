"""
Gate 3 - E1-020 / E1-021 Docdate leakage.

Root cause: _get_match_info's Priority 7 (generic stemmed token overlap)
matched "Docdate Day" against "days" in "Show due days" purely because
"day"/"days" share a stem with the dimension's OWN business name - not
because the question asked for a date dimension. The Due metric's own
configured synonym ("Due number of days") already explains "days" for this
question, so the weak stem-overlap candidate was pure noise: a dimension
attached merely because a date-like word occurred, with zero genuine
evidence of its own.

The fix (SemanticResolver._drop_metric_subsumed_dimension_candidates) drops
a "Stem Overlap"-matched dimension candidate only when the stems it actually
overlaps the question on are entirely covered by an already-selected
metric's own configured vocabulary. A literal, explicit Docdate/date request
(Priority 1-6 - a real phrase match, not a bare stem) is never touched.

DB-gated, following this session's established pattern for live-resolver
tests.

    python backend/test/test_e1_020_021_docdate_leak.py
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
class TestDocdateLeakage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _dims(self, question):
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        return [d.get("business_name") for d in (res.get("dimension_objects") or [])]

    def test_e1_020_show_due_days_no_docdate_leak(self):
        self.assertNotIn("Docdate Day", self._dims("Show due days"))
        self.assertNotIn("Doc Date Day", self._dims("Show due days"))

    def test_e1_021_average_due_days_no_docdate_leak(self):
        self.assertNotIn("Docdate Day", self._dims("Average due days"))
        self.assertNotIn("Doc Date Day", self._dims("Average due days"))

    def test_legitimate_bare_date_dimension_request_preserved(self):
        # No metric here claims "day" - the stem-overlap candidate is the
        # only evidence, and there is nothing for it to be subsumed by.
        self.assertIn("Docdate Day", self._dims("Show sales by day"))

    def test_legitimate_explicit_docdate_request_preserved(self):
        # A literal phrase match (Priority 1-6, not "Stem Overlap") is never
        # touched by the subsumption filter.
        self.assertIn("Docdate Month", self._dims("Show sales by docdate month"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
