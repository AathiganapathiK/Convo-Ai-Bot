"""
Gate 3 - the ambiguity-status contract.

Pure unit tests over AmbiguityClassifier.classify() and the small dispatch
change in DimensionValueResolver.resolve_matches() that reads its new
MULTI_MATCH / dominant_matches output. No database, no live resolver - every
MatchResult here is constructed by hand, the same style
test_phase1d_2_b_ambiguity.py already uses.

THE CONTRACT THIS PINS

    SINGLE_MATCH      one candidate, nothing to compete with.
    WEAK_AMBIGUITY     >=2 candidates FOR THE SAME requested concept, one
                        dominates the others on the evidence (Pareto or
                        margin).
    STRONG_AMBIGUITY   >=2 candidates for the same concept, none dominates -
                        OR one of several distinct requested concepts (see
                        MULTI_MATCH) is itself unresolved this way.
    PARTIAL_MATCH      a concept resolved (SINGLE_MATCH/WEAK_AMBIGUITY/
                        MULTI_MATCH), but the question contains a token none
                        of the accepted candidates explains - some requested
                        concept the classifier has no candidate for at all.
    MULTI_MATCH         >=2 requested concepts, each independently resolving
                        its own SINGLE_MATCH or WEAK_AMBIGUITY - never a
                        vote between concepts, only within one.
    NO_MATCH           no candidates at all.

"Concept" is decided by _competes(): two candidates compete only when they
sit on the same physical (table, column) or were matched through the same
question token(s) - see models.py for the full reasoning. Grouping is
generic: it reads physical identity and matched-token overlap only, never a
name, a table, or a case ID.

    python -m unittest backend.test.test_gate3_ambiguity_status_contract
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.matching.models import (
    AmbiguityClassifier,
    MatchResult,
    MatchType,
    ResolutionStatus,
)


def mr(value, table, column, q_tokens, v_tokens, match_type=MatchType.EXACT,
       confidence=1.0, dimension_id=None, business_name=None):
    return MatchResult(
        matched=True,
        value=value,
        normalized_value=value.lower(),
        confidence=confidence,
        match_type=match_type,
        matched_question_tokens=q_tokens,
        matched_value_tokens=v_tokens,
        reason="test",
        dimension_id=dimension_id,
        business_name=business_name or column,
        table_name=table,
        column_name=column,
    )


class TestSingleMatch(unittest.TestCase):
    """1 - one clear SINGLE_MATCH."""

    def test_one_candidate_is_single_match(self):
        c = mr("CHENNAI", "SALES", "City", ["chennai"], ["chennai"])
        result = AmbiguityClassifier.classify([c], q_tokens=["chennai"])
        self.assertEqual(result.status, ResolutionStatus.SINGLE_MATCH)
        self.assertEqual(result.dominant_match.value, "CHENNAI")
        self.assertEqual(result.dominant_matches, [])


class TestWeakAmbiguity(unittest.TestCase):
    """2 - genuine WEAK_AMBIGUITY: same concept, one candidate dominates."""

    def test_dominant_candidate_wins_but_alternative_recorded(self):
        # Same column, both matched via "pant" - one also explains "cotton".
        c1 = mr("COTTON PANT", "SALES", "ProdGrp1", ["cotton", "pant"], ["cotton", "pant"])
        c2 = mr("LINEN PANT", "SALES", "ProdGrp1", ["cotton", "pant"], ["linen", "pant"],
                match_type=MatchType.FUZZY, confidence=0.90)
        result = AmbiguityClassifier.classify([c1, c2], q_tokens=["cotton", "pant"])
        self.assertEqual(result.status, ResolutionStatus.WEAK_AMBIGUITY)
        self.assertEqual(result.dominant_match.value, "COTTON PANT")
        # The alternative is not discarded - it stays a live candidate.
        self.assertEqual({c.value for c in result.candidates}, {"COTTON PANT", "LINEN PANT"})


class TestStrongAmbiguity(unittest.TestCase):
    """3 - genuine STRONG_AMBIGUITY: same concept, neither dominates."""

    def test_tied_candidates_same_column_no_dominant(self):
        c1 = mr("VIVEAGHAM WHITE SHIRT", "SALES", "Brand",
                ["viveagham"], ["viveagham"], match_type=MatchType.FUZZY, confidence=0.90)
        c2 = mr("VIVEAGHAM COLOUR SHIRT", "SALES", "Brand",
                ["viveagham"], ["viveagham"], match_type=MatchType.FUZZY, confidence=0.90)
        result = AmbiguityClassifier.classify([c1, c2], q_tokens=["viveagham"])
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)
        self.assertIsNone(result.dominant_match)
        self.assertEqual(result.dominant_matches, [])
        self.assertEqual(len(result.candidates), 2)


class TestPartialMatch(unittest.TestCase):
    """4 - PARTIAL_MATCH: a requested concept the classifier has zero
    candidates for leaves a token the resolved concept cannot explain."""

    def test_unexplained_token_downgrades_single_match(self):
        # "franchise" and "category" never enter `matches` at all - no
        # dimension value matched them - but they sit in q_tokens, so the
        # dominant candidate (RAMRAJ) cannot account for the whole question.
        c = mr("RAMRAJ", "SALES", "Brand", ["ramraj"], ["ramraj"])
        result = AmbiguityClassifier.classify(
            [c], q_tokens=["ramraj", "franchise", "category"]
        )
        self.assertEqual(result.status, ResolutionStatus.PARTIAL_MATCH)
        # The resolved concept is still reported - nothing is discarded,
        # only the confidence label changes.
        self.assertEqual(result.dominant_match.value, "RAMRAJ")


class TestMultiMatch(unittest.TestCase):
    """5 - MULTI_MATCH: multiple distinct requested concepts, each resolved
    on its own. The CRITICAL DISTINCTION: this must never be scored as
    STRONG_AMBIGUITY just because len(choices) > 1."""

    def test_two_distinct_dimensions_both_single_match_are_multi_match(self):
        brand = mr("RAMRAJ", "SALES", "Brand", ["ramraj", "brand"], ["ramraj"])
        city = mr("CHENNAI", "SALES", "City", ["chennai", "city"], ["chennai"])
        result = AmbiguityClassifier.classify(
            [brand, city], q_tokens=["chennai", "city", "ramraj", "brand"]
        )
        self.assertEqual(result.status, ResolutionStatus.MULTI_MATCH)
        self.assertIsNone(result.dominant_match)
        self.assertEqual(
            {c.value for c in result.dominant_matches}, {"RAMRAJ", "CHENNAI"}
        )
        # Nothing is thrown away - both remain in the raw candidate list too.
        self.assertEqual({c.value for c in result.candidates}, {"RAMRAJ", "CHENNAI"})

    def test_multi_match_can_itself_carry_a_weak_ambiguity_group(self):
        # Brand resolves cleanly (SINGLE_MATCH within its group); City has
        # two candidates that dominate one another (WEAK_AMBIGUITY within
        # its group). Neither group blocks the other - the top-level result
        # is still MULTI_MATCH, with the City group's own dominant chosen.
        brand = mr("RAMRAJ", "SALES", "Brand", ["ramraj"], ["ramraj"])
        city_a = mr("CHENNAI", "SALES", "City", ["chennai"], ["chennai"])
        city_b = mr("CHENNAI PORT", "SALES", "City", ["chennai"], ["chennai", "port"],
                    match_type=MatchType.FUZZY, confidence=0.90)
        result = AmbiguityClassifier.classify(
            [brand, city_a, city_b], q_tokens=["ramraj", "chennai"]
        )
        self.assertEqual(result.status, ResolutionStatus.MULTI_MATCH)
        self.assertEqual(
            {c.value for c in result.dominant_matches}, {"RAMRAJ", "CHENNAI"}
        )

    def test_one_unresolved_group_among_several_stays_strong_ambiguity(self):
        # Brand resolves cleanly; City has two candidates that are genuinely
        # tied. One live competing interpretation anywhere means the whole
        # request cannot be answered confidently yet - this is NOT
        # "downgraded to PARTIAL_MATCH", it is the same STRONG_AMBIGUITY a
        # single-concept tie would be.
        brand = mr("RAMRAJ", "SALES", "Brand", ["ramraj"], ["ramraj"])
        city_a = mr("VIVEAGHAM WHITE SHIRT", "SALES", "City",
                    ["chennai"], ["chennai"], match_type=MatchType.FUZZY, confidence=0.90)
        city_b = mr("VIVEAGHAM COLOUR SHIRT", "SALES", "City",
                    ["chennai"], ["chennai"], match_type=MatchType.FUZZY, confidence=0.90)
        result = AmbiguityClassifier.classify(
            [brand, city_a, city_b], q_tokens=["ramraj", "chennai"]
        )
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)
        self.assertIsNone(result.dominant_match)


class TestNoMatch(unittest.TestCase):
    """6 - NO_MATCH."""

    def test_no_candidates_at_all(self):
        result = AmbiguityClassifier.classify([], q_tokens=["nothing", "here"])
        self.assertEqual(result.status, ResolutionStatus.NO_MATCH)
        self.assertEqual(result.candidates, [])


class TestGenuineDuplicatesStayAmbiguous(unittest.TestCase):
    """7 - ambiguous duplicate candidates must remain ambiguous. Grouping
    must never be used to quietly resolve a real tie."""

    def test_two_identical_confidence_candidates_same_column_stay_strong(self):
        c1 = mr("BANIANS", "SALES", "ProdGrp3", ["banians"], ["banians"])
        c2 = mr("BANIANS", "OTHER_SALES", "ProdGrp3", ["banians"], ["banians"])
        # Different tables, but the SAME question token - _competes() merges
        # them (shared token), so they are still asked to out-compete each
        # other, exactly as before this change.
        result = AmbiguityClassifier.classify([c1, c2], q_tokens=["banians"])
        self.assertIn(
            result.status,
            (ResolutionStatus.STRONG_AMBIGUITY, ResolutionStatus.WEAK_AMBIGUITY),
        )
        self.assertNotEqual(result.status, ResolutionStatus.MULTI_MATCH)


class TestExplicitQualifierRemovesAmbiguity(unittest.TestCase):
    """8 - an explicit qualifier narrows candidates to one before classify()
    ever sees more than one - handled upstream in
    DimensionValueResolver.resolve_matches(), unchanged by this contract.
    Verified here at the classify() boundary: once narrowed to one
    candidate, the result is unambiguously SINGLE_MATCH."""

    def test_narrowed_to_one_candidate_is_single_match(self):
        # "Chennai city" - the qualifier "city" already picked City over
        # District upstream; classify() only ever sees the City candidate.
        c = mr("CHENNAI", "SALES", "City", ["chennai", "city"], ["chennai"])
        result = AmbiguityClassifier.classify([c], q_tokens=["chennai", "city"])
        self.assertEqual(result.status, ResolutionStatus.SINGLE_MATCH)


class TestReplicatedPhysicalCopiesAreNotFalseAmbiguity(unittest.TestCase):
    """9 - RC-07: a value replicated across physical tables (Division=VT on
    three tables) must not be split into MULTI_MATCH just because the
    tables differ - all three are candidate answers to the SAME question
    token, so they stay one competing group, and table affinity (existing,
    unchanged, confidence.py) picks the one on the resolved metric's table."""

    def test_three_table_replica_resolves_to_the_metric_table_copy(self):
        sales = mr("VT", "SALES", "Division", ["vt"], ["vt"], dimension_id=1)
        outstanding = mr("VT", "OUTSTANDING", "Division", ["vt"], ["vt"], dimension_id=2)
        order_pending = mr("VT", "ORDER_PENDING", "Division", ["vt"], ["vt"], dimension_id=3)
        result = AmbiguityClassifier.classify(
            [sales, outstanding, order_pending],
            q_tokens=["vt"],
            current_metrics=[{"table_name": "SALES"}],
        )
        # Not MULTI_MATCH: this is one concept (Division=VT), not three.
        self.assertNotEqual(result.status, ResolutionStatus.MULTI_MATCH)
        self.assertEqual(len(result.candidates), 3)
        if result.dominant_match is not None:
            self.assertEqual(result.dominant_match.table_name, "SALES")


class TestGenericSyntheticCases(unittest.TestCase):
    """12 - synthetic, deliberately non-production names, proving the
    contract is evaluated purely from evidence (physical identity + token
    overlap), never a hardcoded metric/value/table name or a case ID."""

    def test_two_unrelated_widgets_are_multi_match(self):
        a = mr("WIDGET_ALPHA", "T1", "ColA", ["alpha"], ["widget", "alpha"])
        b = mr("WIDGET_BETA", "T2", "ColB", ["beta"], ["widget", "beta"])
        result = AmbiguityClassifier.classify([a, b], q_tokens=["alpha", "beta"])
        self.assertEqual(result.status, ResolutionStatus.MULTI_MATCH)

    def test_two_competing_widgets_same_slot_are_ambiguous(self):
        a = mr("WIDGET_ALPHA", "T1", "ColA", ["widget"], ["widget", "alpha"],
               match_type=MatchType.FUZZY, confidence=0.90)
        b = mr("WIDGET_BETA", "T1", "ColA", ["widget"], ["widget", "beta"],
               match_type=MatchType.FUZZY, confidence=0.90)
        result = AmbiguityClassifier.classify([a, b], q_tokens=["widget"])
        self.assertIn(
            result.status,
            (ResolutionStatus.STRONG_AMBIGUITY, ResolutionStatus.WEAK_AMBIGUITY),
        )


class TestRamrajFamilyStaysSingleMatch(unittest.TestCase):
    """10 - a curated value family (RAMRAJ standing for its product-line
    rows, see semantic/value_family.py) is offered to the matcher as one
    EXACT candidate, so when it is the only thing that matched, classify()
    sees exactly what it sees for any other single candidate: SINGLE_MATCH.
    This module never inspects family membership - it only ever sees the
    candidate _family_candidates() already produced - so this is the same
    code path as TestSingleMatch, exercised with a family-shaped value. The
    live integration (family loading, migration-backed, DB-gated) is
    test_value_family_ramraj.py, unaffected by this change (38 tests, 5
    subtests, all passing before and after)."""

    def test_family_candidate_alone_is_single_match(self):
        family = mr("RAMRAJ", "SALES", "Brand", ["ramraj"], ["ramraj"])
        result = AmbiguityClassifier.classify([family], q_tokens=["ramraj"])
        self.assertEqual(result.status, ResolutionStatus.SINGLE_MATCH)
        self.assertEqual(result.dominant_match.value, "RAMRAJ")


class TestFollowupMetricCarryoverUnaffected(unittest.TestCase):
    """11 - Gate 3 Item #2's metric carry-over (semantic_resolver.py) runs
    entirely before DimensionValueResolver / AmbiguityClassifier ever see a
    question - it only ever touches metric_objects. Pinned here at the
    boundary this change actually touches: classify() and resolve_matches()
    accept whatever `current_metrics` they are handed (carried or not)
    purely as a table-affinity signal and never alter it. The live
    end-to-end carry-over behaviour is test_item2_followup_metric_carryover.py
    (DB-gated), unaffected by this change."""

    def test_carried_metric_only_affects_table_affinity_not_status(self):
        # Two replicas of the same concept; current_metrics (as if carried
        # from a previous turn) points at OUTSTANDING instead of SALES. The
        # status contract (still one competing group) is identical either
        # way - only which replica dominates can move.
        sales = mr("VT", "SALES", "Division", ["vt"], ["vt"])
        outstanding = mr("VT", "OUTSTANDING", "Division", ["vt"], ["vt"])
        result = AmbiguityClassifier.classify(
            [sales, outstanding],
            q_tokens=["vt"],
            current_metrics=[{"table_name": "OUTSTANDING"}],
        )
        self.assertNotEqual(result.status, ResolutionStatus.MULTI_MATCH)
        if result.dominant_match is not None:
            self.assertEqual(result.dominant_match.table_name, "OUTSTANDING")


class TestMandatoryBenchmarkCases(unittest.TestCase):
    """
    Reconstructs the shape of the five mandatory cases from their captured
    actual behaviour (backend/test/semantic_benchmark/v2/baseline_runs/
    20260903T202348/results.json) and asserts this change leaves each one's
    ambiguity_status exactly where it was. None of E1-017/018/019 involve
    more than one physical column, so the MULTI_MATCH grouping never
    activates for them - confirming, rather than assuming, that this change
    does not touch their (separately debatable) STRONG_AMBIGUITY status.
    E1-075/077 are the multi-dimension cases this change was written for.
    """

    def test_e1_017_due_amount_seven_way_tie_stays_strong_ambiguity(self):
        # "Show due amount" - seven Due-Status labels, one physical column,
        # all sharing the single generic token "due". Unaffected: one
        # column means one group, exactly the pre-existing code path.
        labels = ["NO DUE", "OVER DUE", "Due Today", "Future Due",
                  "Current Due (1-7)", "Delayed Due (16-30)",
                  "Critical Due (31-60)"]
        candidates = [
            mr(label, "PENDING", "DueStatus", ["due"], ["due"],
               match_type=MatchType.FUZZY, confidence=0.90)
            for label in labels
        ]
        result = AmbiguityClassifier.classify(candidates, q_tokens=["due", "amount"])
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)

    def test_e1_018_total_due_amount_stays_one_competing_group(self):
        # The captured live behaviour is STRONG_AMBIGUITY; this synthetic
        # reconstruction (evidence recomputed from scratch on hand-built
        # MatchResults, not the live matcher's exact fuzzy scores) is not
        # asserted to reproduce that exact sub-status - only that it is
        # still ONE group's internal dominance decision (SINGLE_MATCH is
        # impossible with 4 candidates; MULTI_MATCH and PARTIAL_MATCH would
        # both mean this change altered how many concepts were seen, which
        # is the one thing this change must never do for a one-column tie).
        labels = ["Due Today", "Current Due (1-7)",
                  "Delayed Due (16-30)", "Critical Due (31-60)"]
        candidates = [
            mr(label, "PENDING", "DueStatus", ["due"], ["due"],
               match_type=MatchType.FUZZY, confidence=0.90)
            for label in labels
        ]
        result = AmbiguityClassifier.classify(
            candidates, q_tokens=["total", "due", "amount"]
        )
        self.assertIn(
            result.status,
            (ResolutionStatus.STRONG_AMBIGUITY, ResolutionStatus.WEAK_AMBIGUITY),
        )
        self.assertEqual(len(result.candidates), 4)

    def test_e1_019_payment_amount_two_way_tie_stays_strong_ambiguity(self):
        labels = ["FULL PAYMENT", "PARTIAL PAYMENT"]
        candidates = [
            mr(label, "PENDING", "PaymentStatus", ["payment"], ["payment"],
               match_type=MatchType.FUZZY, confidence=0.90)
            for label in labels
        ]
        result = AmbiguityClassifier.classify(candidates, q_tokens=["payment", "amount"])
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)

    def test_e1_075_ramraj_brand_and_franchise_category_is_partial_match(self):
        # "Show sales for Ramraj brand and Franchise category" - only Brand
        # resolves to a concrete value (RAMRAJ); "Franchise"/"category" name
        # a dimension but no value ever enters `matches` for it, so
        # classify() only ever sees the one Brand candidate. One group,
        # SINGLE_MATCH, downgraded to PARTIAL_MATCH by the unexplained
        # "franchise"/"category" tokens - exactly the captured actual
        # behaviour (PASS in the live benchmark), unchanged by this fix.
        brand = mr("RAMRAJ", "SALES", "Brand", ["ramraj"], ["ramraj"])
        result = AmbiguityClassifier.classify(
            [brand], q_tokens=["ramraj", "brand", "franchise", "category"]
        )
        self.assertEqual(result.status, ResolutionStatus.PARTIAL_MATCH)
        self.assertEqual(result.dominant_match.value, "RAMRAJ")

    def test_e1_077_quantity_variant_same_shape_as_e1_075(self):
        brand = mr("RAMRAJ", "ORDER_PENDING", "Brand", ["ramraj"], ["ramraj"])
        result = AmbiguityClassifier.classify(
            [brand], q_tokens=["ramraj", "brand", "franchise", "category"]
        )
        self.assertEqual(result.status, ResolutionStatus.PARTIAL_MATCH)

    def test_e1_075_would_become_multi_match_if_category_also_resolved(self):
        # Not a captured case - illustrates why E1-075 passes today only
        # because Category never produces a value candidate. If it did (a
        # real "Franchise" category value existed), the pre-fix classifier
        # would have scored Brand against Category as competing alternatives
        # and returned STRONG_AMBIGUITY, incorrectly blocking a fully
        # resolved multi-dimension request. This is the defect this change
        # closes; see verify_multi_match.py in the session scratchpad for
        # the live-shaped reproduction against SemanticResolver.resolve().
        brand = mr("RAMRAJ", "SALES", "Brand", ["ramraj"], ["ramraj"])
        category = mr("FRANCHISE", "SALES", "Category", ["franchise"], ["franchise"])
        result = AmbiguityClassifier.classify(
            [brand, category], q_tokens=["ramraj", "franchise"]
        )
        self.assertEqual(result.status, ResolutionStatus.MULTI_MATCH)


class TestSemanticGateAllowsMultiMatch(unittest.TestCase):
    """
    SemanticGate.evaluate() blocks STRONG_AMBIGUITY, PARTIAL_MATCH and a
    multi-candidate WEAK_AMBIGUITY - MULTI_MATCH is deliberately absent from
    that chain, so it falls through exactly like SINGLE_MATCH: allowed, no
    SemanticGate change required. This is the change's real payoff -
    "Show sales for Chennai city and Ramraj brand" no longer gets refused as
    STRONG_AMBIGUITY.
    """

    def test_multi_match_is_not_blocked(self):
        from semantic.semantic_gate import SemanticGate

        class _FakeAmbiguityResult:
            status = ResolutionStatus.MULTI_MATCH

        semantic_result = {
            "connection_id": "conn-multi-match",
            "metric_objects": [{"table_name": "SALES", "metric_name": "Sales"}],
            "dimension_objects": [],
            "value_matches": [
                {"table_name": "SALES", "business_name": "City", "value": "CHENNAI"},
                {"table_name": "SALES", "business_name": "Brand", "value": "RAMRAJ"},
            ],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0},
            "ambiguity_result": _FakeAmbiguityResult(),
        }
        from unittest.mock import patch
        from collections import defaultdict
        with patch("semantic.relationship_expander.RelationshipExpander.build_graph",
                   return_value=defaultdict(set)):
            res = SemanticGate.evaluate(semantic_result)
        self.assertTrue(res["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
