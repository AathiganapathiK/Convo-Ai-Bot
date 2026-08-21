import sys
import os
import unittest

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.matching.models import (
    MatchType,
    MatchResult,
    ResolutionStatus,
    AmbiguityChoice,
    SemanticResolutionResult,
    AmbiguityClassifier
)
from semantic.dimension_value_resolver import DimensionValueResolver

class TestPhase1D2BAmbigutiy(unittest.TestCase):

    def test_no_match(self):
        """
        A. NO_MATCH: Empty list of candidates should classify to NO_MATCH.
        """
        result = AmbiguityClassifier.classify([])
        self.assertEqual(result.status, ResolutionStatus.NO_MATCH)
        self.assertEqual(len(result.candidates), 0)
        self.assertIsNone(result.dominant_match)

    def test_single_match(self):
        """
        B. SINGLE_MATCH: Exactly one MatchResult should resolve to SINGLE_MATCH.
        """
        match = MatchResult(
            matched=True,
            value="RAMRAJ PANT",
            normalized_value="ramraj pant",
            confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=["pant"],
            matched_value_tokens=["ramraj", "pant"],
            reason="Morphological singular/plural match",
            dimension_id=201,
            business_name="Brand",
            table_name="PBI_ENES_ORDER_PENDING_SUMMARY",
            column_name="Brand"
        )
        result = AmbiguityClassifier.classify([match])
        self.assertEqual(result.status, ResolutionStatus.SINGLE_MATCH)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.dominant_match.value, "RAMRAJ PANT")
        self.assertEqual(result.dominant_match.dimension_id, 201)

    def test_strong_same_type_ambiguity(self):
        """
        C. Strong same-type ambiguity:
        LINEN PANT 0.95 vs RAMRAJ PANT 0.95 (both SINGULAR_PLURAL)
        should classify to STRONG_AMBIGUITY.
        """
        match1 = MatchResult(
            matched=True,
            value="LINEN PANT",
            normalized_value="linen pant",
            confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=["pant"],
            matched_value_tokens=["linen", "pant"],
            reason="Morphological singular/plural match",
            dimension_id=201,
            business_name="Brand"
        )
        match2 = MatchResult(
            matched=True,
            value="RAMRAJ PANT",
            normalized_value="ramraj pant",
            confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=["pant"],
            matched_value_tokens=["ramraj", "pant"],
            reason="Morphological singular/plural match",
            dimension_id=201,
            business_name="Brand"
        )
        result = AmbiguityClassifier.classify([match1, match2])
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)
        self.assertIsNone(result.dominant_match)
        self.assertEqual(len(result.candidates), 2)

    def test_strong_fuzzy_ambiguity(self):
        """
        D. Strong fuzzy ambiguity:
        candidate A FUZZY 0.90 vs candidate B FUZZY 0.90
        should classify to STRONG_AMBIGUITY.
        """
        match1 = MatchResult(
            matched=True,
            value="Candidate A",
            normalized_value="candidate a",
            confidence=0.90,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["candidate"],
            matched_value_tokens=["candidate", "a"],
            reason="Fuzzy match",
            dimension_id=201,
            business_name="Brand"
        )
        match2 = MatchResult(
            matched=True,
            value="Candidate B",
            normalized_value="candidate b",
            confidence=0.90,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["candidate"],
            matched_value_tokens=["candidate", "b"],
            reason="Fuzzy match",
            dimension_id=201,
            business_name="Brand"
        )
        result = AmbiguityClassifier.classify([match1, match2])
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)
        self.assertIsNone(result.dominant_match)

    def test_fuzzy_minor_gap_ambiguity(self):
        """
        Verify that a small gap (e.g. FUZZY 0.90 vs FUZZY 0.86) with same span length
        does NOT declare dominance (remains STRONG_AMBIGUITY).
        """
        match1 = MatchResult(
            matched=True,
            value="Candidate A",
            normalized_value="candidate a",
            confidence=0.90,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["candidate"],
            matched_value_tokens=["candidate", "a"],
            reason="Fuzzy match"
        )
        match2 = MatchResult(
            matched=True,
            value="Candidate B",
            normalized_value="candidate b",
            confidence=0.86,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["candidate"],
            matched_value_tokens=["candidate", "b"],
            reason="Fuzzy match"
        )
        result = AmbiguityClassifier.classify([match1, match2])
        self.assertEqual(result.status, ResolutionStatus.STRONG_AMBIGUITY)
        self.assertIsNone(result.dominant_match)

    def test_fuzzy_larger_gap_dominance(self):
        """
        Verify that a larger gap (e.g. FUZZY 0.90 vs FUZZY 0.84)
        correctly registers as WEAK_AMBIGUITY with Rank 1 dominant.
        """
        match1 = MatchResult(
            matched=True,
            value="Candidate A",
            normalized_value="candidate a",
            confidence=0.90,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["candidate"],
            matched_value_tokens=["candidate", "a"],
            reason="Fuzzy match"
        )
        match2 = MatchResult(
            matched=True,
            value="Candidate B",
            normalized_value="candidate b",
            confidence=0.84,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["candidate"],
            matched_value_tokens=["candidate", "b"],
            reason="Fuzzy match"
        )
        result = AmbiguityClassifier.classify([match1, match2])
        self.assertEqual(result.status, ResolutionStatus.WEAK_AMBIGUITY)
        self.assertEqual(result.dominant_match.value, "Candidate A")

    def test_exact_dominant_match(self):
        """
        E. Exact dominant match:
        EXACT 1.00 vs FUZZY 0.85 should resolve to WEAK_AMBIGUITY
        with the EXACT match as dominant_match.
        """
        match1 = MatchResult(
            matched=True,
            value="RAMRAJ PANT",
            normalized_value="ramraj pant",
            confidence=1.00,
            match_type=MatchType.EXACT,
            matched_question_tokens=["ramraj", "pant"],
            matched_value_tokens=["ramraj", "pant"],
            reason="Exact match",
            dimension_id=201,
            business_name="Brand"
        )
        match2 = MatchResult(
            matched=True,
            value="LINEN PANT",
            normalized_value="linen pant",
            confidence=0.85,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["pant"],
            matched_value_tokens=["linen", "pant"],
            reason="Fuzzy match",
            dimension_id=201,
            business_name="Brand"
        )
        result = AmbiguityClassifier.classify([match1, match2])
        self.assertEqual(result.status, ResolutionStatus.WEAK_AMBIGUITY)
        self.assertEqual(result.dominant_match.value, "RAMRAJ PANT")

    def test_preserve_metadata(self):
        """
        F. Preserve metadata:
        Verify all MatchResult metadata fields reach AmbiguityChoice.
        """
        match = MatchResult(
            matched=True,
            value="RAMRAJ PANT",
            normalized_value="ramraj pant",
            confidence=0.95,
            match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=["pant"],
            matched_value_tokens=["ramraj", "pant"],
            reason="Morphological singular/plural match",
            dimension_id=201,
            business_name="Brand",
            table_name="PBI_ENES_ORDER_PENDING_SUMMARY",
            column_name="Brand"
        )
        choice = AmbiguityChoice(match)
        self.assertEqual(choice.value, "RAMRAJ PANT")
        self.assertEqual(choice.normalized_value, "ramraj pant")
        self.assertEqual(choice.confidence, 0.95)
        self.assertEqual(choice.match_type, MatchType.SINGULAR_PLURAL)
        self.assertEqual(choice.dimension_id, 201)
        self.assertEqual(choice.business_name, "Brand")
        self.assertEqual(choice.table_name, "PBI_ENES_ORDER_PENDING_SUMMARY")
        self.assertEqual(choice.column_name, "Brand")
        self.assertEqual(choice.matched_question_tokens, ["pant"])
        self.assertEqual(choice.matched_value_tokens, ["ramraj", "pant"])
        self.assertEqual(choice.reason, "Morphological singular/plural match")

    def test_duplicate_candidates_integration(self):
        """
        G. Duplicate candidates:
        Verify that already-consolidated duplicate candidates are not artificially
        duplicated by the classification layer.
        """
        resolver = DimensionValueResolver()
        resolver.pipeline.matches = [
            MatchResult(
                matched=True, value="LINEN PANT", normalized_value="linen pant",
                confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
                matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
                reason="Morphological match", dimension_id=201, business_name="Brand",
                table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand"
            ),
            MatchResult(
                matched=True, value="LINEN PANT", normalized_value="linen pant",
                confidence=0.85, match_type=MatchType.FUZZY,
                matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
                reason="Fuzzy match", dimension_id=201, business_name="Brand",
                table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand"
            )
        ]
        
        from unittest.mock import MagicMock
        resolver._load_dimension_values = MagicMock(return_value=[])
        resolver.pipeline.execute = MagicMock(return_value=(resolver.pipeline.matches, None))
        
        results = resolver.resolve_matches("dummy_conn", "pant")
        
        self.assertEqual(len(results), 1)
        
        res_result = resolver.last_resolution_result
        self.assertEqual(res_result.status, ResolutionStatus.SINGLE_MATCH)
        self.assertEqual(len(res_result.candidates), 1)
        self.assertEqual(res_result.candidates[0].value, "LINEN PANT")
        self.assertEqual(res_result.dominant_match.value, "LINEN PANT")

    def test_formal_shirt_coverage_calculation(self):
        """
        A, B, C: Test matched query-token coverage calculation specifically for 'formal shirt' query context.
        """
        q_tokens = ["formal", "shirt"]

        # Candidate matching only 'shirt'
        c_shirt = MatchResult(
            matched=True, value="VIVEAGHAM COLOUR SHIRT", normalized_value="viveagham colour shirt",
            confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=q_tokens, matched_value_tokens=["viveagham", "colour", "shirt"],
            reason="test"
        )
        choice_shirt = AmbiguityChoice(c_shirt)
        matched_shirt = AmbiguityClassifier._compute_query_coverage(choice_shirt, q_tokens)
        self.assertEqual(len(matched_shirt), 1)
        self.assertEqual(matched_shirt, ["shirt"])

        # Candidate matching only 'formal'
        c_formal = MatchResult(
            matched=True, value="FORMAL SOCKS DESIGN FULL", normalized_value="formal socks design full",
            confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=q_tokens, matched_value_tokens=["formal", "socks", "design", "full"],
            reason="test"
        )
        choice_formal = AmbiguityChoice(c_formal)
        matched_formal = AmbiguityClassifier._compute_query_coverage(choice_formal, q_tokens)
        self.assertEqual(len(matched_formal), 1)
        self.assertEqual(matched_formal, ["formal"])

        # Candidate matching full phrase (2 tokens)
        c_both = MatchResult(
            matched=True, value="FORMAL SHIRT", normalized_value="formal shirt",
            confidence=0.95, match_type=MatchType.EXACT,
            matched_question_tokens=q_tokens, matched_value_tokens=["formal", "shirt"],
            reason="test"
        )
        choice_both = AmbiguityChoice(c_both)
        matched_both = AmbiguityClassifier._compute_query_coverage(choice_both, q_tokens)
        self.assertEqual(len(matched_both), 2)
        self.assertTrue("formal" in matched_both and "shirt" in matched_both)

    def test_coverage_dominance_rule(self):
        """
        D: Test coverage dominance rule.
        Candidate 1: FUZZY, confidence = 0.90, coverage = 2 tokens.
        Candidate 2: FUZZY, confidence = 0.95, coverage = 1 token.
        Candidate 1 should dominate.
        """
        q_tokens = ["cotton", "pant"]

        # Candidate matching 2 tokens (coverage = 2)
        c1 = MatchResult(
            matched=True, value="COTTON PANT", normalized_value="cotton pant",
            confidence=0.90, match_type=MatchType.FUZZY,
            matched_question_tokens=q_tokens, matched_value_tokens=["cotton", "pant"],
            reason="test"
        )
        
        # Candidate matching 1 token (coverage = 1)
        c2 = MatchResult(
            matched=True, value="LINEN PANT", normalized_value="linen pant",
            confidence=0.95, match_type=MatchType.FUZZY,
            matched_question_tokens=q_tokens, matched_value_tokens=["linen", "pant"],
            reason="test"
        )

        res = AmbiguityClassifier.classify([c1, c2], q_tokens)
        self.assertEqual(res.status, ResolutionStatus.WEAK_AMBIGUITY)
        self.assertEqual(res.dominant_match.value, "COTTON PANT")

    def test_equal_coverage_equal_confidence_ambiguity(self):
        """
        E: Test equal coverage + equal confidence -> STRONG_AMBIGUITY.
        """
        q_tokens = ["cotton", "pant"]

        c1 = MatchResult(
            matched=True, value="RAMRAJ PANT", normalized_value="ramraj pant",
            confidence=0.95, match_type=MatchType.FUZZY,
            matched_question_tokens=q_tokens, matched_value_tokens=["ramraj", "pant"],
            reason="test"
        )
        c2 = MatchResult(
            matched=True, value="LINEN PANT", normalized_value="linen pant",
            confidence=0.95, match_type=MatchType.FUZZY,
            matched_question_tokens=q_tokens, matched_value_tokens=["linen", "pant"],
            reason="test"
        )

        res = AmbiguityClassifier.classify([c1, c2], q_tokens)
        self.assertEqual(res.status, ResolutionStatus.STRONG_AMBIGUITY)
        self.assertIsNone(res.dominant_match)

    def test_semantic_gate_blocks_strong_ambiguity(self):
        """
        Verify that SemanticGate.evaluate blocks SQL generation and returns
        allowed: False when STRONG_AMBIGUITY is present in ambiguity_result.
        """
        from semantic.semantic_gate import SemanticGate
        from semantic.matching.models import SemanticResolutionResult
        
        ambig_res = SemanticResolutionResult(
            status=ResolutionStatus.STRONG_AMBIGUITY,
            candidates=[]
        )
        semantic_result = {
            "retrieval": {
                "status": "PARTIAL",
                "confidence": 0.45,
                "resolved_components": 1
            },
            "ambiguity_result": ambig_res
        }
        
        gate_res = SemanticGate.evaluate(semantic_result)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "STRONG_AMBIGUITY")
        self.assertIn("Strong ambiguity detected", gate_res["reason"])

    def test_resolver_filters_to_dominant_match_and_cleans_tokens(self):
        """
        Verify that DimensionValueResolver.resolve_matches returns only the dominant match
        and overrides the matched_question_tokens with clean intersected tokens.
        """
        from semantic.dimension_value_resolver import DimensionValueResolver
        from semantic.matching.models import MatchResult, MatchType
        from unittest.mock import MagicMock
        
        resolver = DimensionValueResolver(MagicMock())
        
        # Mock pipeline execute to return two fuzzy matches (weak ambiguity)
        # Query is "cotton pant"
        c1 = MatchResult(
            matched=True, value="COTTON PANT", normalized_value="cotton pant",
            confidence=0.95, match_type=MatchType.FUZZY,
            # Polluted matched_question_tokens (e.g. from legacy singular/plural matcher)
            matched_question_tokens=["cotton", "pant", "noise"], matched_value_tokens=["cotton", "pant"],
            reason="test"
        )
        c2 = MatchResult(
            matched=True, value="LINEN PANT", normalized_value="linen pant",
            confidence=0.90, match_type=MatchType.FUZZY,
            matched_question_tokens=["cotton", "pant", "noise"], matched_value_tokens=["linen", "pant"],
            reason="test"
        )
        
        resolver.pipeline.matches = [c1, c2]
        resolver._load_dimension_values = MagicMock(return_value=[])
        resolver.pipeline.execute = MagicMock(return_value=(resolver.pipeline.matches, None))
        
        results = resolver.resolve_matches("dummy_conn", "cotton pant")
        
        # Since c1 ("COTTON PANT") has coverage of 2 tokens vs c2 ("LINEN PANT")'s 1 token,
        # and COTTON PANT has higher confidence, it dominates.
        # Therefore, dominant_match should be COTTON PANT, and ONLY COTTON PANT should be returned.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "COTTON PANT")
        # Ensure matched_question_tokens is cleaned to ['cotton', 'pant'] (noise token removed)
        self.assertCountEqual(results[0]["matched_question_tokens"], ["cotton", "pant"])

if __name__ == "__main__":
    unittest.main()
