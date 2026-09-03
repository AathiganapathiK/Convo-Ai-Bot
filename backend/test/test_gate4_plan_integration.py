"""
Gate 4 - the shared-file integration, and the Gate 3 behaviour it must preserve.

semantic_plan_builder.py is edited by both gates. The agreed Gate 4 change is one
optional parameter and one guarded block. The tests here assert both halves of
that agreement:

  when `extracted` is None the builder behaves exactly as it did before, so
  Gate 3's work, the existing suite and the v1 benchmark are untouched;

  when `extracted` is supplied it overrides the heuristics, which is the whole
  point of step 27.
"""

import unittest

from ai import assumptions
from ai.extraction.models import ExtractedIntent
from ai.extraction.slot_extractor import read_deterministic_signals
from semantic.models.semantic_plan import (
    AnalysisMode,
    BenchmarkType,
    OutputFormat,
    RankDirection,
    RankMeasure,
)
from semantic.semantic_plan_builder import SemanticPlanBuilder


CANONICAL = "Top 5 products whose sales are reducing last quarter"


def _build(question, extracted=None):
    return SemanticPlanBuilder.build(
        question=question, semantic_result={}, extracted=extracted
    )


class TestGate3BehaviourPreserved(unittest.TestCase):
    """Without an extraction, nothing about the builder changed."""

    def test_default_parameter_means_existing_callers_are_unaffected(self):
        # Every current call site omits `extracted`. This is the call they make.
        plan = SemanticPlanBuilder.build(question="Show sales", semantic_result={})
        self.assertIsNotNone(plan)

    def test_heuristic_ranking_still_applies(self):
        plan = _build("top 5 products by sales")
        self.assertEqual(plan.mode, AnalysisMode.RANKING)
        self.assertEqual(plan.ranking.direction, RankDirection.DESC)

    def test_heuristic_lowest_still_reads_ascending(self):
        plan = _build("lowest selling brands")
        self.assertEqual(plan.ranking.direction, RankDirection.ASC)

    def test_descriptive_question_is_unchanged(self):
        plan = _build("Show sales for Chennai city")
        self.assertEqual(plan.mode, AnalysisMode.DESCRIPTIVE)
        self.assertIsNone(plan.ranking)

    def test_benchmark_stays_none_without_extraction(self):
        # Gate 1 left benchmark unset and documented that Gate 4 fills it.
        # Adding the field to the constructor must not start populating it.
        self.assertIsNone(_build("top 5 products by sales").benchmark)

    def test_canonical_case_shows_the_old_defect_without_extraction(self):
        # Documents precisely what Gate 4 fixes. The heuristic ranks on the
        # level, which answers a different question.
        plan = _build(CANONICAL)
        self.assertEqual(plan.ranking.direction, RankDirection.DESC)
        self.assertIsNone(plan.ranking.measure)
        self.assertIsNone(plan.ranking.top_n)


class TestExtractionOverrides(unittest.TestCase):
    """With an extraction, the plan reflects the sentence rather than a keyword."""

    def test_canonical_case_is_correct_with_extraction(self):
        intent = read_deterministic_signals(CANONICAL)
        plan = _build(CANONICAL, extracted=intent)

        self.assertEqual(plan.mode, AnalysisMode.RANKING)
        self.assertEqual(plan.ranking.direction, RankDirection.ASC)
        self.assertEqual(plan.ranking.measure, RankMeasure.CHANGE)
        self.assertEqual(plan.ranking.top_n, 5)

    def test_mode_is_taken_from_extraction(self):
        intent = ExtractedIntent(mode=AnalysisMode.TREND)
        plan = _build("show me the numbers", extracted=intent)
        self.assertEqual(plan.mode, AnalysisMode.TREND)

    def test_benchmark_is_populated_only_by_extraction(self):
        intent = ExtractedIntent(
            mode=AnalysisMode.COMPARISON, benchmark=BenchmarkType.TARGET
        )
        plan = _build("sales against target", extracted=intent)
        self.assertIsNotNone(plan.benchmark)
        self.assertEqual(plan.benchmark.benchmark_type, BenchmarkType.TARGET)

    def test_output_override_is_honoured(self):
        intent = ExtractedIntent(
            mode=AnalysisMode.DESCRIPTIVE, output=OutputFormat.CHART
        )
        plan = _build("show sales as a chart", extracted=intent)
        self.assertEqual(plan.output.output_format, OutputFormat.CHART)

    def test_partial_extraction_does_not_blank_heuristic_fields(self):
        # The extractor found a count but no direction. The direction the
        # heuristic already worked out must survive.
        intent = ExtractedIntent(mode=AnalysisMode.RANKING, top_n=3)
        plan = _build("lowest selling brands", extracted=intent)
        self.assertEqual(plan.ranking.top_n, 3)
        self.assertEqual(plan.ranking.direction, RankDirection.ASC)

    def test_empty_extraction_changes_nothing(self):
        plan_without = _build("top 5 products by sales")
        plan_with = _build("top 5 products by sales", extracted=ExtractedIntent())

        self.assertEqual(plan_without.mode, plan_with.mode)
        self.assertEqual(
            plan_without.ranking.direction, plan_with.ranking.direction
        )


class TestAssumptionsReachThePlan(unittest.TestCase):
    """Step 29 - what was assumed must be visible on the plan."""

    def test_assumptions_are_appended_to_the_plan(self):
        intent = read_deterministic_signals("top brands")
        outcome = assumptions.resolve(intent)
        intent.assumptions_made = assumptions.merge_into(
            intent.assumptions_made, outcome.assumptions
        )
        plan = _build("top brands", extracted=intent)

        self.assertTrue(intent.assumptions_made)
        for sentence in intent.assumptions_made:
            self.assertIn(sentence, plan.assumptions_made)

    def test_builder_own_assumptions_are_not_replaced(self):
        # The builder records the snapshot-configuration fallback before Gate 4
        # runs. Gate 4 appending must not delete it.
        baseline = _build("top brands")
        self.assertTrue(
            baseline.assumptions_made,
            "Expected the builder to record its snapshot-config fallback.",
        )
        pre_existing = baseline.assumptions_made[0]

        intent = read_deterministic_signals("top brands")
        outcome = assumptions.resolve(intent)
        intent.assumptions_made = assumptions.merge_into(
            intent.assumptions_made, outcome.assumptions
        )
        plan = _build("top brands", extracted=intent)

        self.assertIn(pre_existing, plan.assumptions_made)
        self.assertGreater(len(plan.assumptions_made), len(baseline.assumptions_made))

    def test_no_duplicate_disclosures(self):
        intent = read_deterministic_signals("top brands")
        intent.assumptions_made = ["Showing the top 10 - ask for more or fewer."]
        plan = _build("top brands", extracted=intent)
        self.assertEqual(
            len(plan.assumptions_made), len(set(plan.assumptions_made))
        )


if __name__ == "__main__":
    unittest.main()
