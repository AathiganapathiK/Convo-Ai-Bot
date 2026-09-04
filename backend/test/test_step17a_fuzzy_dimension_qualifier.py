"""
Gate 3 Step 17a - explicit dimension qualifier for FUZZY value matches.

The qualifier filter in DimensionValueResolver.resolve_matches (the
"Apply explicit dimension context filtering" block) already worked for
exactly-spelled values: "Chennai city" locates CHENNAI in the question, sees
the adjacent word "city", and drops District=CHENNAI.

It could never work for a fuzzy match, because it located the value by the
value's OWN spelling - and a fuzzy match is precisely the case where the
question's spelling differs. "coimbator city" found no span for
"coimbatore", so no adjacent word was examined and District=COIMBATORE
survived alongside City=COIMBATORE.

17a supplies the span from MatchResult.matched_question_tokens_precise (added
in 21f) - the token the fuzzy matcher actually approved for that candidate,
which does appear in the question. matched_question_tokens is deliberately
NOT used: it is the whole n-gram span the matcher searched with.

Live DB, read-only. Skipped if the database is unreachable, matching this
project's existing pattern for DB-backed tests.
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
class TestStep17aFuzzyDimensionQualifier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        from semantic.dimension_value_resolver import DimensionValueResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.DimensionValueResolver = DimensionValueResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _candidates(self, question):
        self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        rr = self.DimensionValueResolver.last_resolution_result
        return rr, list(rr.candidates)

    def _columns(self, candidates):
        return {c.column_name for c in candidates if c.result}

    def test_exact_qualifier_unchanged(self):
        # 1. The pre-existing behaviour that already worked must not change.
        _, candidates = self._candidates("Show sales for Chennai city")
        columns = self._columns(candidates)
        self.assertIn("City", columns)
        self.assertNotIn("District", columns)

    def test_fuzzy_qualifier_filters_district(self):
        # 2. The case 17a fixes.
        _, candidates = self._candidates("Show sales for coimbator city")
        columns = self._columns(candidates)
        self.assertIn("City", columns)
        self.assertNotIn("District", columns,
                         "District=COIMBATORE should be removed by the 'city' qualifier")

    def test_all_six_misspelled_cities_drop_district(self):
        # 3. Every case in the cluster, not just the one traced.
        cases = {
            "Show sales for coimbator city": "COIMBATORE",
            "Show sales for chenai city": "CHENNAI",
            "Show sales for maduray city": "MADURAI",
            "Show sales for erod city": "ERODE",
            "Show sales for salm city": "SALEM",
            "Show sales for tirunelvely city": "TIRUNELVELI",
        }
        for question, expected_value in cases.items():
            _, candidates = self._candidates(question)
            columns = self._columns(candidates)
            self.assertNotIn("District", columns, msg=question)
            self.assertIn(expected_value, {c.value for c in candidates}, msg=question)

    def test_fuzzy_without_qualifier_unchanged(self):
        # 4. No dimension word next to the value -> the filter must not fire,
        # so candidates from other dimensions are still allowed through.
        _, candidates = self._candidates("Show sales for coimbator")
        self.assertTrue(candidates, "expected at least one candidate")
        # Nothing is asserted to be removed here: with no qualifier word the
        # block leaves every candidate in place, which is the pre-existing
        # contract for unqualified questions.

    def test_vt_division_rc07_behavior_unchanged(self):
        # 6. Step 17 removes the wrong DIMENSION (btype) but must leave the
        # cross-TABLE Division spread alone - that is RC-07, untouched here.
        rr, candidates = self._candidates("Show sales for VT division")
        columns = self._columns(candidates)
        self.assertEqual(columns, {"Division"})
        tables = {c.table_name for c in candidates}
        self.assertGreater(len(tables), 1,
                           "cross-table Division ambiguity is RC-07 and must remain")


class TestStep17aUsesPreciseTokenOnly(unittest.TestCase):
    """
    5. The span must come from matched_question_tokens_precise, never from
    the whole matched_question_tokens span. Pure unit test, no DB.
    """

    def test_precise_token_locates_span_and_whole_span_does_not(self):
        from semantic.dimension_value_resolver import DimensionValueResolver

        q_words = "show sales for coimbator city".split()

        # The value's own spelling cannot be found - this is the gap.
        self.assertEqual(
            DimensionValueResolver._find_match_span_indices(q_words, "coimbatore"), []
        )
        # The precise approved token can be, and points at the right word.
        indices = DimensionValueResolver._find_match_span_indices(q_words, "coimbator")
        self.assertEqual(indices, [3])
        self.assertEqual(q_words[max(indices) + 1], "city")

    def test_whole_span_would_point_at_the_wrong_words(self):
        # Demonstrates why matched_question_tokens is not used: for a
        # multi-token fuzzy phrase it spans words the candidate does not
        # explain, so the "adjacent word" would be computed from the wrong
        # boundary.
        from semantic.dimension_value_resolver import DimensionValueResolver

        q_words = "show sales for coimbator city".split()
        span_indices = DimensionValueResolver._find_match_span_indices(
            q_words, "coimbator city"
        )
        self.assertEqual(span_indices, [3, 4])
        # max index is the last word, so there is no adjacent word after it -
        # the qualifier "city" would be consumed as part of the value span
        # instead of being read as the qualifier.
        self.assertEqual(max(span_indices), len(q_words) - 1)


if __name__ == "__main__":
    unittest.main()
