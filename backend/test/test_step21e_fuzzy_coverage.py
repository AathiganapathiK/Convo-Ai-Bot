"""
Gate 3 Step 21e - fuzzy-match token-evidence loss.

Root cause (verified by the 21e read-only investigation): AmbiguityClassifier
._compute_query_coverage (semantic/matching/models.py) recomputed which
question token a candidate explained from scratch, checking only exact/
singular-plural equality between the question tokens and the candidate's own
STORED-VALUE tokens. A misspelled fuzzy match can never satisfy that check -
"coimbator" is not "coimbatore" even after singularizing - so the coverage
computation silently discarded the token FuzzyMatcher._has_token_level_
evidence had already confirmed and recorded on MatchResult.matched_question_
tokens at match time.

The fix adds one additive step: for FUZZY candidates only, a token already
present in choice.result.matched_question_tokens AND genuinely part of the
question (present in the same q_map steps 1-3 already built) is also
credited. EXACT/NORMALIZED/SINGULAR_PLURAL candidates never take this branch.

Scope boundary this investigation surfaced and these tests confirm rather
than paper over: which candidate becomes DOMINANT is decided by
matching/confidence.py's score_candidates, which reads MatchResult fields
directly and was explicitly out of scope for this fix. So
AmbiguityChoice.matched_query_tokens (what RC-02 and the genuine-alternative
filter read) is now correct, but the ELECTRONIC CITY / <misspelled city>
benchmark cases do not flip to PASS from this fix alone - confidence.py's own
coverage computation is a separate, untouched copy of similar logic.
"""
import unittest

from semantic.matching.models import (
    AmbiguityClassifier,
    AmbiguityChoice,
    MatchResult,
    MatchType,
)


def _fuzzy_match(value, matched_question_tokens, matched_value_tokens,
                  business_name="City", table_name="SALES", column_name="City",
                  confidence=0.9):
    return MatchResult(
        matched=True,
        value=value,
        normalized_value=value.lower(),
        confidence=confidence,
        match_type=MatchType.FUZZY,
        matched_question_tokens=matched_question_tokens,
        matched_value_tokens=matched_value_tokens,
        reason="fuzzy",
        dimension_id=1,
        business_name=business_name,
        table_name=table_name,
        column_name=column_name,
    )


def _exact_match(value, matched_question_tokens, matched_value_tokens,
                  business_name="City", table_name="SALES", column_name="City"):
    return MatchResult(
        matched=True,
        value=value,
        normalized_value=value.lower(),
        confidence=1.0,
        match_type=MatchType.EXACT,
        matched_question_tokens=matched_question_tokens,
        matched_value_tokens=matched_value_tokens,
        reason="exact",
        dimension_id=1,
        business_name=business_name,
        table_name=table_name,
        column_name=column_name,
    )


class TestFuzzyCoverageUnit(unittest.TestCase):
    """Direct unit tests of _compute_query_coverage - no live DB, no
    dominance/scoring involved at all."""

    def test_coimbator_credits_the_fuzzy_matched_token(self):
        q_tokens = ["show", "sales", "for", "coimbator", "city"]
        result = _fuzzy_match("COIMBATORE", ["coimbator"], ["coimbatore"])
        choice = AmbiguityChoice(result=result)

        matched = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertIn("coimbator", matched)

    def test_electronic_city_does_not_gain_extra_coverage(self):
        # ELECTRONIC CITY's own matched_question_tokens is ['city'] - the
        # same token it already legitimately earns via the existing
        # value-token comparison (step 1-3), since "city" is literally a
        # word of the stored value "ELECTRONIC CITY" too. The fuzzy addition
        # must not inflate this beyond that single, pre-existing token.
        q_tokens = ["show", "sales", "for", "coimbator", "city"]
        result = _fuzzy_match("ELECTRONIC CITY", ["city"], ["electronic", "city"])
        choice = AmbiguityChoice(result=result)

        matched = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertEqual(matched, ["city"])

    def test_fuzzy_match_cannot_claim_a_token_it_did_not_record(self):
        # Safety requirement: a FUZZY candidate must not receive credit for
        # a question token merely because that token exists in the
        # question - only a token the fuzzy matcher itself recorded on
        # matched_question_tokens (i.e. actually approved via
        # _has_token_level_evidence) qualifies.
        q_tokens = ["show", "sales", "for", "coimbator", "city"]
        result = _fuzzy_match("COIMBATORE", [], ["coimbatore"])  # matcher recorded nothing
        choice = AmbiguityChoice(result=result)

        matched = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertNotIn("coimbator", matched)

    def test_exact_match_coverage_unchanged(self):
        q_tokens = ["show", "sales", "for", "chennai"]
        result = _exact_match("CHENNAI", ["chennai"], ["chennai"])
        choice = AmbiguityChoice(result=result)

        matched = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertEqual(matched, ["chennai"])

    def test_normalized_match_coverage_unchanged(self):
        result = MatchResult(
            matched=True, value="Cotton Pant", normalized_value="cotton pant",
            confidence=0.98, match_type=MatchType.NORMALIZED,
            matched_question_tokens=["cotton", "pant"],
            matched_value_tokens=["cotton", "pant"],
            reason="normalized", dimension_id=1, business_name="Product",
            table_name="SALES", column_name="Product",
        )
        choice = AmbiguityChoice(result=result)
        q_tokens = ["show", "cotton", "pant", "sales"]

        matched = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertEqual(set(matched), {"cotton", "pant"})

    def test_singular_plural_match_coverage_unchanged(self):
        result = MatchResult(
            matched=True, value="BANIANS", normalized_value="banians",
            confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=["banian"],
            matched_value_tokens=["banians"],
            reason="singular_plural", dimension_id=1, business_name="Product",
            table_name="SALES", column_name="Product",
        )
        choice = AmbiguityChoice(result=result)
        q_tokens = ["show", "sales", "for", "banian"]

        matched = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertIn("banian", matched)


class TestFuzzyCoverageDeterminism(unittest.TestCase):
    """21b determinism: the same inputs must produce the same coverage every
    time - this fix adds no randomness, no state, no external call."""

    def test_repeated_calls_are_identical(self):
        q_tokens = ["show", "sales", "for", "coimbator", "city"]
        result = _fuzzy_match("COIMBATORE", ["coimbator"], ["coimbatore"])
        choice = AmbiguityChoice(result=result)

        first = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)
        second = AmbiguityClassifier._compute_query_coverage(choice, q_tokens)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
