"""
Gate 3 Step 21e - live-DB regression/coverage check for the seven named
misspelled-city benchmark cases (E1-137 through E1-142, E1-153).

These confirm the fix's actual, scoped effect: AmbiguityChoice.matched_query_
tokens (read by RC-02 and the genuine-alternative filter) now carries the
correct token for the misspelled value. They do NOT assert these cases now
PASS the benchmark, because dominance itself is decided by
matching/confidence.py's score_candidates - which reads MatchResult fields
directly, bypasses _compute_query_coverage entirely, and was explicitly out
of scope for this fix. Asserting a PASS here would misrepresent what was
actually fixed.

Skipped automatically if the configured database is unreachable, matching
this project's existing pattern for DB-backed tests.
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
class TestStep21eMisspelledCityCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        from semantic.dimension_value_resolver import DimensionValueResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.DimensionValueResolver = DimensionValueResolver
        cls.conn_id = runner.resolve_logical_connection()

    # E1-153 ("Coimby") is deliberately excluded from CASES: "Coimby" is far
    # enough from "Coimbatore" that it never clears FuzzyMatcher's own
    # similarity cutoff, so no COIMBATORE candidate is generated at all for
    # that question - only the accidental ELECTRONIC CITY match reaches the
    # classifier. That is a different, upstream limitation (the fuzzy
    # cutoff/candidate generation), not the coverage-computation defect this
    # fix addresses, and is asserted separately below rather than folded in
    # here as if it were the same case.
    CASES = {
        "Show sales for coimbator city": "coimbator",     # E1-137
        "Show sales for chenai city": "chenai",            # E1-138
        "Show sales for maduray city": "maduray",           # E1-139
        "Show sales for erod city": "erod",                # E1-140
        "Show sales for salm city": "salm",                # E1-141
        "Show sales for tirunelvely city": "tirunelvely",   # E1-142
    }

    def test_coimby_never_generates_a_real_candidate_separate_issue(self):
        # E1-153. Documents the distinct finding rather than silently
        # excluding it: this is not the coverage bug 21e fixes.
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question="Show sales for Coimby city")
        rr = self.DimensionValueResolver.last_resolution_result
        real_city_candidates = [
            ch for ch in rr.candidates
            if ch.result and ch.result.column_name == "City" and ch.value.upper() != "ELECTRONIC CITY"
        ]
        self.assertEqual(
            real_city_candidates, [],
            msg="Coimby now generates a real city candidate - re-evaluate this test, "
                "the upstream fuzzy-cutoff limitation this documents may have changed"
        )

    def test_misspelled_city_candidate_now_carries_its_own_matched_token(self):
        for question, expected_token in self.CASES.items():
            res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
            rr = self.DimensionValueResolver.last_resolution_result
            city_candidates = [
                ch for ch in rr.candidates
                if ch.result and ch.result.column_name == "City"
                and ch.value.upper() != "ELECTRONIC CITY"
            ]
            self.assertTrue(city_candidates, msg=f"no misspelled-city candidate found for: {question}")
            for ch in city_candidates:
                self.assertIn(
                    expected_token, ch.matched_query_tokens,
                    msg=f"{question}: expected '{expected_token}' credited to {ch.value!r}, "
                        f"got {ch.matched_query_tokens!r}"
                )

    def test_accidental_electronic_city_gains_no_extra_coverage(self):
        for question in list(self.CASES) + ["Show sales for Coimby city"]:
            res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
            rr = self.DimensionValueResolver.last_resolution_result
            electronic_city = [ch for ch in rr.candidates if ch.value.upper() == "ELECTRONIC CITY"]
            for ch in electronic_city:
                self.assertEqual(
                    ch.matched_query_tokens, ["city"],
                    msg=f"{question}: ELECTRONIC CITY gained unexpected coverage "
                        f"{ch.matched_query_tokens!r}"
                )

    def test_accidental_electronic_city_no_longer_dominates(self):
        # Originally written for 21e as
        # test_dominance_and_status_unchanged_by_this_fix, asserting that 21e
        # did NOT change dominance - because 21e only corrected
        # AmbiguityChoice.matched_query_tokens, while dominance was decided by
        # confidence.py's own separate computation, out of scope at the time.
        #
        # Step 21f fixed that second computation (precise fuzzy token evidence
        # plus the specificity key), so the accidental ELECTRONIC CITY match
        # no longer outscores the real city. Updated to assert the corrected
        # behaviour rather than the boundary it documented.
        for question in self.CASES:
            res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
            rr = self.DimensionValueResolver.last_resolution_result
            if rr.dominant_match is not None:
                self.assertNotEqual(
                    rr.dominant_match.value.upper(), "ELECTRONIC CITY", msg=question
                )

        # "Coimby" is unchanged: it still generates no real city candidate at
        # all (upstream fuzzy-cutoff limitation), so ELECTRONIC CITY remains
        # the only candidate there.
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id, question="Show sales for Coimby city"
        )
        rr = self.DimensionValueResolver.last_resolution_result
        self.assertEqual(rr.status.value, "PARTIAL_MATCH")


if __name__ == "__main__":
    unittest.main()
