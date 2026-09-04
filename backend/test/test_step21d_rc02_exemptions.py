"""
Gate 3 Step 21d - RC-02 unmatched-token exemption fix.

AmbiguityClassifier.classify() (semantic/matching/models.py) downgrades
SINGLE_MATCH/WEAK_AMBIGUITY to PARTIAL_MATCH whenever the dominant candidate
leaves a question token unexplained, unless that token is a stopword or
belongs to the dominant candidate's own dimension metadata. Two gaps in that
exemption were found by the Step 21d investigation and are fixed here:

  1. A word belonging to the already-RESOLVED METRIC (current_metrics /
     all_metrics) was never exempted, only words belonging to the dimension.
  2. Three concrete generic filler words - "total", "now", "instead" - are
     not in the global STOPWORDS set (which is shared by other consumers and
     deliberately left untouched) and so were treated as dangerous.

Every test calls AmbiguityClassifier.classify() directly with constructed
MatchResult objects - no live database, no dependency on 21b scoring,
DOMINANCE_MARGIN, table_affinity, or MatchRanker, none of which changed.
"""
import unittest

from semantic.matching.models import (
    AmbiguityClassifier,
    MatchResult,
    MatchType,
    ResolutionStatus,
)


def _match(value, business_name, table_name, column_name, matched_q_tokens,
           dimension_id=1, confidence=1.0, match_type=MatchType.EXACT):
    return MatchResult(
        matched=True,
        value=value,
        normalized_value=value.lower(),
        confidence=confidence,
        match_type=match_type,
        matched_question_tokens=matched_q_tokens,
        matched_value_tokens=[value.lower()],
        reason="test",
        dimension_id=dimension_id,
        business_name=business_name,
        table_name=table_name,
        column_name=column_name,
    )


class TestRC02MetricVocabularyExemption(unittest.TestCase):
    """A. A token belonging to the already-resolved metric must not, by
    itself, trigger the PARTIAL_MATCH downgrade."""

    def test_metric_business_name_word_is_exempted(self):
        # "Show pending amount for Chennai" - "pending" belongs to the
        # resolved metric ("Pending Amount"), not to the City dimension.
        q_tokens = ["show", "pending", "amount", "for", "chennai"]
        match = _match("CHENNAI", "City", "SALES", "City", ["chennai"])

        current_metrics = [{"business_name": "Pending Amount", "metric_name": "PAMT"}]
        all_metrics = [("PAMT", "Pending Amount", "SALES", "PendingAmt", "SUM", "pending, pending amount")]

        res = AmbiguityClassifier.classify(
            [match], q_tokens, current_metrics=current_metrics, all_metrics=all_metrics
        )
        self.assertEqual(res.status, ResolutionStatus.SINGLE_MATCH)

    def test_metric_synonym_word_is_exempted(self):
        # The word appears only in the metric's synonyms column, not its
        # business_name - the exemption must read synonyms too.
        q_tokens = ["show", "revenue", "for", "chennai"]
        match = _match("CHENNAI", "City", "SALES", "City", ["chennai"])

        current_metrics = [{"business_name": "C Y", "metric_name": "CY"}]
        all_metrics = [("CY", "C Y", "SALES", "CY", "SUM", "revenue, turnover")]

        res = AmbiguityClassifier.classify(
            [match], q_tokens, current_metrics=current_metrics, all_metrics=all_metrics
        )
        self.assertEqual(res.status, ResolutionStatus.SINGLE_MATCH)

    def test_without_metric_data_word_still_dangerous(self):
        # Sanity check: with no current_metrics/all_metrics passed at all,
        # the same unmatched word is NOT exempted - proves the exemption is
        # additive, not a blanket relaxation.
        q_tokens = ["show", "pending", "amount", "for", "chennai"]
        match = _match("CHENNAI", "City", "SALES", "City", ["chennai"])

        res = AmbiguityClassifier.classify([match], q_tokens)
        self.assertEqual(res.status, ResolutionStatus.PARTIAL_MATCH)


class TestRC02FillerWords(unittest.TestCase):
    """B, C, D - the three verified filler words, each on a representative
    shape drawn from an actual failing benchmark case."""

    def test_total_does_not_trigger_downgrade(self):
        # E1-098 shape: "Total sales for VT"
        q_tokens = ["total", "sales", "for", "vt"]
        match = _match("VT", "Division", "SALES", "Division", ["vt"])
        res = AmbiguityClassifier.classify([match], q_tokens)
        self.assertEqual(res.status, ResolutionStatus.SINGLE_MATCH)

    def test_now_does_not_trigger_downgrade(self):
        # E1-170 shape: "Now show sales for VT division"
        q_tokens = ["now", "show", "sales", "for", "vt", "division"]
        match = _match("VT", "Division", "SALES", "Division", ["vt"])
        res = AmbiguityClassifier.classify([match], q_tokens)
        self.assertEqual(res.status, ResolutionStatus.SINGLE_MATCH)

    def test_instead_does_not_trigger_downgrade(self):
        # E1-174 shape: "Show sales for Chennai city instead"
        q_tokens = ["show", "sales", "for", "chennai", "city", "instead"]
        match = _match("CHENNAI", "City", "SALES", "City", ["chennai"])
        res = AmbiguityClassifier.classify([match], q_tokens)
        self.assertEqual(res.status, ResolutionStatus.SINGLE_MATCH)


class TestRC02NegativeSafety(unittest.TestCase):
    """E. A genuinely meaningful unmatched token must still downgrade.

    Uses a second, unrelated dimension's business name as the unmatched
    token ("children") - not a contrived string - so it cannot accidentally
    match the dominant candidate's own dimension/metric vocabulary or any
    other resolver rule; it is exactly the kind of token RC-02 exists to
    catch (a second business term the dominant candidate does not explain).
    """

    def test_second_business_term_still_downgrades(self):
        # "Show sales for children in Chennai" - "children" names a second,
        # unresolved business concept the City-only dominant match cannot
        # explain, and is not one of the three verified filler words.
        q_tokens = ["show", "sales", "for", "children", "in", "chennai"]
        match = _match("CHENNAI", "City", "SALES", "City", ["chennai"])

        current_metrics = [{"business_name": "C Y", "metric_name": "CY"}]
        all_metrics = [("CY", "C Y", "SALES", "CY", "SUM", "revenue")]

        res = AmbiguityClassifier.classify(
            [match], q_tokens, current_metrics=current_metrics, all_metrics=all_metrics
        )
        self.assertEqual(res.status, ResolutionStatus.PARTIAL_MATCH)


if __name__ == "__main__":
    unittest.main()
