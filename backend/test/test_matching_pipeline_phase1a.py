import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest

from semantic.matching.models import (
    MatchingContext,
    QuestionContext,
    MatchResult,
    MatchType,
)

from semantic.matching.pipeline import MatchingPipeline


class FakeMatcher:
    """
    Controlled matcher used only to test MatchingPipeline orchestration.

    This deliberately does not use the real matchers because this test
    verifies the pipeline itself, not the matching algorithms.
    """

    def __init__(self, match_type, results):
        self.match_type = match_type
        self.results = results
        self.call_count = 0

    def match(self, context):
        self.call_count += 1
        return self.results


def make_match(match_type, value):
    return MatchResult(
        matched=True,
        value=value,
        normalized_value=value.lower(),
        confidence=0.95,
        match_type=match_type,
        matched_question_tokens=[value.lower()],
        matched_value_tokens=[value.lower()],
        reason=f"test-{match_type.value.lower()}",
        dimension_id=1,
        business_name=value,
        table_name="TestTable",
        column_name="TestColumn",
    )


def make_context():
    question_context = QuestionContext(
        raw_question="show sales in tamil nadu",
        normalized_question="show sales in tamil nadu",
        q_tokens=[
            "show",
            "sales",
            "in",
            "tamil",
            "nadu",
        ],
        q_singulars=[
            "show",
            "sale",
            "in",
            "tamil",
            "nadu",
        ],
    )

    return MatchingContext(
        question_context=question_context,
        connection_id="test-connection",
        indexed_values=[],
        settings={},
    )


class TestMatchingPipelinePhase1A(unittest.TestCase):

    def test_all_matchers_execute_even_when_exact_matches(self):
        """
        Regression test for the Phase 1A short-circuit bug.

        Every matcher must execute even when an earlier matcher
        already returns candidates.
        """

        exact = FakeMatcher(
            MatchType.EXACT,
            [
                make_match(
                    MatchType.EXACT,
                    "Tamil Nadu",
                )
            ],
        )

        normalized = FakeMatcher(
            MatchType.NORMALIZED,
            [
                make_match(
                    MatchType.NORMALIZED,
                    "Tamil Nadu",
                )
            ],
        )

        plural = FakeMatcher(
            MatchType.SINGULAR_PLURAL,
            [
                make_match(
                    MatchType.SINGULAR_PLURAL,
                    "Tamil Nadu",
                )
            ],
        )

        fuzzy = FakeMatcher(
            MatchType.FUZZY,
            [
                make_match(
                    MatchType.FUZZY,
                    "Tamil Nadu",
                )
            ],
        )

        pipeline = MatchingPipeline(
            [
                exact,
                normalized,
                plural,
                fuzzy,
            ]
        )

        matches, stats = pipeline.execute(
            make_context()
        )

        # Every matcher must execute exactly once.
        self.assertEqual(exact.call_count, 1)
        self.assertEqual(normalized.call_count, 1)
        self.assertEqual(plural.call_count, 1)
        self.assertEqual(fuzzy.call_count, 1)

        # Every matcher must be marked as attempted.
        self.assertTrue(stats.exact_attempted)
        self.assertTrue(stats.normalized_attempted)
        self.assertTrue(stats.plural_attempted)
        self.assertTrue(stats.fuzzy_attempted)

        # All matcher candidates must be preserved.
        self.assertEqual(len(matches), 4)

        # The pipeline does not select a winner.
        self.assertIsNone(stats.winning_match)

        # Per-matcher candidate counts.
        self.assertEqual(stats.exact_match_count, 1)
        self.assertEqual(stats.normalized_match_count, 1)
        self.assertEqual(stats.plural_match_count, 1)
        self.assertEqual(stats.fuzzy_match_count, 1)

        # Total candidate count.
        self.assertEqual(stats.total_match_count, 4)

    def test_matchers_with_no_results_still_execute(self):
        """
        Matchers returning no candidates must not prevent later
        matchers from executing.
        """

        exact = FakeMatcher(
            MatchType.EXACT,
            [],
        )

        normalized = FakeMatcher(
            MatchType.NORMALIZED,
            [
                make_match(
                    MatchType.NORMALIZED,
                    "Tamil Nadu",
                )
            ],
        )

        plural = FakeMatcher(
            MatchType.SINGULAR_PLURAL,
            [],
        )

        fuzzy = FakeMatcher(
            MatchType.FUZZY,
            [
                make_match(
                    MatchType.FUZZY,
                    "Tamil Nadu",
                )
            ],
        )

        pipeline = MatchingPipeline(
            [
                exact,
                normalized,
                plural,
                fuzzy,
            ]
        )

        matches, stats = pipeline.execute(
            make_context()
        )

        self.assertEqual(exact.call_count, 1)
        self.assertEqual(normalized.call_count, 1)
        self.assertEqual(plural.call_count, 1)
        self.assertEqual(fuzzy.call_count, 1)

        self.assertEqual(len(matches), 2)

        self.assertEqual(stats.exact_match_count, 0)
        self.assertEqual(stats.normalized_match_count, 1)
        self.assertEqual(stats.plural_match_count, 0)
        self.assertEqual(stats.fuzzy_match_count, 1)
        self.assertEqual(stats.total_match_count, 2)

    def test_empty_matcher_list_returns_empty_results(self):
        """
        Edge case:
        a pipeline with no matchers must return safely.
        """

        pipeline = MatchingPipeline([])

        matches, stats = pipeline.execute(
            make_context()
        )

        self.assertEqual(matches, [])

        self.assertFalse(
            stats.exact_attempted
        )

        self.assertFalse(
            stats.normalized_attempted
        )

        self.assertFalse(
            stats.plural_attempted
        )

        self.assertFalse(
            stats.fuzzy_attempted
        )

        self.assertEqual(
            stats.total_match_count,
            0,
        )

        self.assertIsNone(
            stats.winning_match
        )

    def test_matcher_returning_none_is_safe(self):
        """
        Edge case:
        a matcher returning None should be treated
        as producing no candidates.
        """

        exact = FakeMatcher(
            MatchType.EXACT,
            None,
        )

        normalized = FakeMatcher(
            MatchType.NORMALIZED,
            [
                make_match(
                    MatchType.NORMALIZED,
                    "Tamil Nadu",
                )
            ],
        )

        pipeline = MatchingPipeline(
            [
                exact,
                normalized,
            ]
        )

        matches, stats = pipeline.execute(
            make_context()
        )

        self.assertEqual(
            exact.call_count,
            1,
        )

        self.assertEqual(
            normalized.call_count,
            1,
        )

        self.assertEqual(
            len(matches),
            1,
        )

        self.assertEqual(
            stats.total_match_count,
            1,
        )

    def test_multiple_candidates_from_one_matcher_are_preserved(self):
        """
        Phase 1A does not deduplicate candidates.

        Candidate consolidation belongs to a later phase.
        """

        exact_matches = [
            make_match(
                MatchType.EXACT,
                "Tamil Nadu",
            ),
            make_match(
                MatchType.EXACT,
                "Tamil",
            ),
        ]

        exact = FakeMatcher(
            MatchType.EXACT,
            exact_matches,
        )

        pipeline = MatchingPipeline(
            [exact]
        )

        matches, stats = pipeline.execute(
            make_context()
        )

        self.assertEqual(
            len(matches),
            2,
        )

        self.assertEqual(
            stats.exact_match_count,
            2,
        )

        self.assertEqual(
            stats.total_match_count,
            2,
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )