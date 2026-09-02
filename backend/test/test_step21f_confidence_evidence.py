"""
Gate 3 Step 21f - two corrections inside confidence.score_candidates().

1. Fuzzy query evidence. `evidence_tokens = matched_v_tokens or matched_q`
   discarded the fuzzy matcher's own approved question token whenever the
   candidate had value tokens (i.e. essentially always). For every non-fuzzy
   tier the value's tokens ARE the question's tokens, so measuring coverage
   against the value works; a fuzzy match is exactly the case where they
   differ by spelling ("coimbator" vs "coimbatore"), so the intersection was
   guaranteed empty and a correct match scored 0.00 query_coverage while an
   accidental one scored 0.50. Now unioned additively, FUZZY only.

2. Specificity key granularity. `value_claims` was keyed on the bare
   normalized value, so two candidates on DIFFERENT columns that merely
   shared a string were counted as competing duplicates. City=COIMBATORE and
   District=COIMBATORE are two genuinely true facts about this data, and VT
   is a real Division value on three separate tables; each was scoring 0.50
   or 0.33 specificity for the others' existence. Key is now
   (table_name, column_name, normalized_value).

Nothing is deduplicated or removed. Pareto dominance, DOMINANCE_MARGIN,
PARETO_EPSILON, table_affinity, tier and the weights are untouched.
"""
import unittest

from semantic.matching.confidence import score_candidates
from semantic.matching.models import AmbiguityChoice, MatchResult, MatchType


def _choice(value, matched_question_tokens, matched_value_tokens, match_type,
            table_name="SALES", column_name="City", confidence=0.9,
            dimension_id=1, business_name="City", precise=None):
    result = MatchResult(
        matched=True,
        value=value,
        normalized_value=value.lower(),
        confidence=confidence,
        match_type=match_type,
        matched_question_tokens=matched_question_tokens,
        matched_value_tokens=matched_value_tokens,
        reason="test",
        dimension_id=dimension_id,
        business_name=business_name,
        table_name=table_name,
        column_name=column_name,
        matched_question_tokens_precise=precise,
    )
    return AmbiguityChoice(result=result, matched_query_tokens=matched_question_tokens)


class TestFuzzyQueryEvidence(unittest.TestCase):

    def test_fuzzy_matched_token_receives_query_coverage(self):
        # "coimbator city": the fuzzy matcher approved "coimbator" against
        # the stored value "COIMBATORE". Coverage must credit it.
        choices = [
            _choice("COIMBATORE", ["coimbator"], ["coimbatore"], MatchType.FUZZY,
                    confidence=0.947, precise=["coimbator"]),
            _choice("ELECTRONIC CITY", ["city"], ["electronic", "city"], MatchType.FUZZY,
                    confidence=0.900, precise=["city"]),
        ]
        scores = score_candidates(choices, entity_tokens=["coimbator", "city"])
        self.assertGreater(scores[0].query_coverage, 0.0)
        self.assertAlmostEqual(scores[0].query_coverage, 0.5)

    def test_fuzzy_without_approved_token_gets_no_extra_credit(self):
        # The matcher recorded no precise evidence -> nothing to union in, so
        # the candidate must not gain coverage it never earned.
        choices = [
            _choice("COIMBATORE", [], ["coimbatore"], MatchType.FUZZY,
                    confidence=0.947, precise=None),
        ]
        scores = score_candidates(choices, entity_tokens=["coimbator", "city"])
        self.assertEqual(scores[0].query_coverage, 0.0)

    def test_fuzzy_span_is_never_used_as_evidence(self):
        # THE regression invariant. Both candidates report the whole
        # "cotton pant" span in matched_question_tokens; only the precise
        # field distinguishes them. LINEN PANT must not be credited for
        # "cotton".
        cotton = _choice("COTTON PANT", ["cotton", "pant"], ["cotton", "pant"],
                         MatchType.FUZZY, confidence=0.90, column_name="Product",
                         precise=["cotton"])
        linen = _choice("LINEN PANT", ["cotton", "pant"], ["linen", "pant"],
                        MatchType.FUZZY, confidence=0.95, column_name="Product",
                        precise=["pant"])
        scores = score_candidates([cotton, linen], entity_tokens=["cotton", "pant"])
        self.assertAlmostEqual(scores[0].query_coverage, 1.0)   # COTTON PANT
        self.assertAlmostEqual(scores[1].query_coverage, 0.5)   # LINEN PANT
        self.assertGreater(scores[0].scalar, scores[1].scalar)

    def test_exact_behavior_unchanged(self):
        choices = [
            _choice("CHENNAI", ["chennai"], ["chennai"], MatchType.EXACT, confidence=1.0),
        ]
        scores = score_candidates(choices, entity_tokens=["chennai", "city"])
        self.assertAlmostEqual(scores[0].query_coverage, 0.5)
        self.assertAlmostEqual(scores[0].value_coverage, 1.0)

    def test_normalized_behavior_unchanged(self):
        choices = [
            _choice("Cotton Pant", ["cotton", "pant"], ["cotton", "pant"],
                    MatchType.NORMALIZED, confidence=0.98, column_name="Product"),
        ]
        scores = score_candidates(choices, entity_tokens=["cotton", "pant"])
        self.assertAlmostEqual(scores[0].query_coverage, 1.0)

    def test_singular_plural_behavior_unchanged(self):
        choices = [
            _choice("BANIANS", ["banians"], ["banians"], MatchType.SINGULAR_PLURAL,
                    confidence=0.95, column_name="ProdGrp1"),
        ]
        scores = score_candidates(choices, entity_tokens=["banians"])
        self.assertAlmostEqual(scores[0].query_coverage, 1.0)

    def test_non_fuzzy_still_prefers_value_tokens_over_question_tokens(self):
        # The original `or` semantics for non-FUZZY: a matcher reporting the
        # whole question span must NOT get credit for tokens its value does
        # not account for. "LINEN PANT" claims the span "cotton pant" but
        # only explains "pant".
        choices = [
            _choice("LINEN PANT", ["cotton", "pant"], ["linen", "pant"],
                    MatchType.NORMALIZED, column_name="Product"),
        ]
        scores = score_candidates(choices, entity_tokens=["cotton", "pant"])
        self.assertAlmostEqual(scores[0].query_coverage, 0.5)


class TestSpecificityKeyGranularity(unittest.TestCase):

    def test_city_and_district_do_not_suppress_each_other(self):
        # Two genuinely different dimensions that legitimately share a value.
        choices = [
            _choice("COIMBATORE", ["coimbator"], ["coimbatore"], MatchType.FUZZY,
                    column_name="City", business_name="City", dimension_id=1),
            _choice("COIMBATORE", ["coimbator"], ["coimbatore"], MatchType.FUZZY,
                    column_name="District", business_name="District", dimension_id=2),
        ]
        scores = score_candidates(choices, entity_tokens=["coimbator", "city"])
        self.assertEqual(scores[0].specificity, 1.0)
        self.assertEqual(scores[1].specificity, 1.0)

    def test_same_table_column_value_still_shares_one_claim(self):
        # The signal's original intent must survive: genuinely competing
        # claims on the SAME column still divide specificity.
        choices = [
            _choice("OTHERS", ["others"], ["others"], MatchType.EXACT,
                    table_name="SALES", column_name="Category", dimension_id=1),
            _choice("OTHERS", ["others"], ["others"], MatchType.EXACT,
                    table_name="SALES", column_name="Category", dimension_id=1),
        ]
        scores = score_candidates(choices, entity_tokens=["others"])
        self.assertAlmostEqual(scores[0].specificity, 0.5)
        self.assertAlmostEqual(scores[1].specificity, 0.5)

    def test_vt_across_different_tables_not_treated_as_duplicates(self):
        # Same column NAME, three different physical tables - each is the
        # only claimant of "VT" within its own table.
        choices = [
            _choice("VT", ["vt"], ["vt"], MatchType.EXACT, confidence=1.0,
                    table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="Division"),
            _choice("VT", ["vt"], ["vt"], MatchType.EXACT, confidence=1.0,
                    table_name="PBI_OUTSTANDING_ENES_SUMMARY", column_name="Division"),
            _choice("VT", ["vt"], ["vt"], MatchType.EXACT, confidence=1.0,
                    table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Division"),
        ]
        scores = score_candidates(choices, entity_tokens=["vt", "division"])
        for s in scores:
            self.assertEqual(s.specificity, 1.0)


if __name__ == "__main__":
    unittest.main()
