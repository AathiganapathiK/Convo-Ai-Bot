"""
Gate 4 Steps 28 and 29 - assume, record, surface.

The rule under test throughout: ask only when there is nothing safe to assume.
A test that allows a clarification where a default existed is testing the wrong
behaviour, so several of these assert the absence of a question.

The missing-period policy is exercised in all three settings regardless of
which one is currently in force, so that whichever way the business rules, the
behaviour is already covered.
"""

import unittest
from unittest.mock import patch

from ai import assumptions
from ai.assumptions import MissingPeriodPolicy
from ai.extraction.models import Clarification, ExtractedIntent
from semantic.models.semantic_plan import (
    AnalysisMode,
    OutputFormat,
    RankDirection,
    RankMeasure,
)


def _ranking(**kwargs) -> ExtractedIntent:
    intent = ExtractedIntent(mode=AnalysisMode.RANKING)
    for key, value in kwargs.items():
        setattr(intent, key, value)
    return intent


class TestStatedValuesWin(unittest.TestCase):
    """Case one: the user said it, so use it and assume nothing."""

    def test_stated_top_n_is_untouched(self):
        intent = _ranking(top_n=5, direction=RankDirection.ASC,
                          measure=RankMeasure.CHANGE, time_period="last quarter")
        outcome = assumptions.resolve(intent)
        self.assertEqual(intent.top_n, 5)
        self.assertEqual(outcome.assumptions, [])

    def test_stated_direction_is_untouched(self):
        intent = _ranking(top_n=5, direction=RankDirection.ASC,
                          time_period="last year")
        assumptions.resolve(intent)
        self.assertEqual(intent.direction, RankDirection.ASC)

    def test_nothing_is_asked_when_everything_is_stated(self):
        intent = _ranking(top_n=5, direction=RankDirection.DESC,
                          measure=RankMeasure.ABSOLUTE, time_period="2024")
        outcome = assumptions.resolve(intent)
        self.assertFalse(outcome.needs_user)


class TestSafeDefaults(unittest.TestCase):
    """Case two: absent with a convention. Use it, record it, never ask."""

    def test_missing_top_n_defaults_and_is_recorded(self):
        intent = _ranking(direction=RankDirection.DESC, time_period="2024")
        outcome = assumptions.resolve(intent)

        self.assertEqual(intent.top_n, assumptions.DEFAULT_TOP_N)
        self.assertTrue(
            any(str(assumptions.DEFAULT_TOP_N) in s for s in outcome.assumptions)
        )
        self.assertFalse(outcome.needs_user)

    def test_missing_direction_defaults_and_is_recorded(self):
        intent = _ranking(top_n=5, time_period="2024")
        outcome = assumptions.resolve(intent)

        self.assertEqual(intent.direction, RankDirection.DESC)
        self.assertTrue(any("highest first" in s.lower() for s in outcome.assumptions))

    def test_no_clarification_when_a_default_was_available(self):
        # The headline Done criterion for step 28.
        intent = _ranking(time_period="2024")
        outcome = assumptions.resolve(intent)
        self.assertIsNone(outcome.clarification)

    def test_ranking_defaults_do_not_apply_to_descriptive(self):
        # A row cap on a breakdown would silently truncate what the user asked
        # to see in full.
        intent = ExtractedIntent(mode=AnalysisMode.DESCRIPTIVE, time_period="2024")
        assumptions.resolve(intent)
        self.assertIsNone(intent.top_n)
        self.assertIsNone(intent.direction)

    def test_presentation_default_is_not_disclosed(self):
        # How a number is shown does not change the number, so disclosing it
        # would be noise on every answer.
        intent = ExtractedIntent(mode=AnalysisMode.TREND, time_period="2024")
        outcome = assumptions.resolve(intent)
        self.assertEqual(intent.output, OutputFormat.CHART)
        self.assertEqual(outcome.assumptions, [])

    def test_every_disclosure_says_how_to_change_it(self):
        intent = _ranking(time_period="2024")
        outcome = assumptions.resolve(intent)
        for sentence in outcome.assumptions:
            with self.subTest(sentence=sentence):
                self.assertRegex(sentence.lower(), r"ask|say|if you")


class TestContradictionsAsk(unittest.TestCase):
    """Case three: only a genuine contradiction may interrupt."""

    def test_change_ranking_without_any_period_asks(self):
        # Ranking by movement needs two periods. With none named there is
        # nothing to difference against, and no default can invent one.
        intent = _ranking(top_n=5, direction=RankDirection.ASC,
                          measure=RankMeasure.CHANGE)
        outcome = assumptions.resolve(intent)

        self.assertTrue(outcome.needs_user)
        self.assertEqual(outcome.clarification.slot, "comparison")
        self.assertTrue(outcome.clarification.options)

    def test_change_ranking_with_a_period_does_not_ask(self):
        intent = _ranking(top_n=5, direction=RankDirection.ASC,
                          measure=RankMeasure.CHANGE, time_period="last quarter")
        outcome = assumptions.resolve(intent)
        self.assertFalse(outcome.needs_user)

    def test_extractor_clarification_is_preserved(self):
        intent = _ranking(top_n=5, time_period="2024")
        intent.clarification = Clarification(
            slot="measure", question="Level or change?",
            options=["Level", "Change"], reason="ambiguous",
        )
        outcome = assumptions.resolve(intent)
        self.assertTrue(outcome.needs_user)
        self.assertEqual(outcome.clarification.slot, "measure")

    def test_no_defaults_are_filled_while_a_question_is_outstanding(self):
        # A plan that looks complete beside a question admitting it is not
        # would be actively misleading.
        intent = _ranking(measure=RankMeasure.CHANGE)
        outcome = assumptions.resolve(intent)
        self.assertTrue(outcome.needs_user)
        self.assertIsNone(intent.top_n)
        self.assertEqual(outcome.assumptions, [])


class TestMissingPeriodPolicy(unittest.TestCase):
    """
    The open business decision, covered in all three settings.

    Whichever way the team rules, the behaviour is already tested and switching
    MISSING_PERIOD_POLICY is genuinely a one-line change.
    """

    def test_defer_assumes_nothing_and_asks_nothing(self):
        with patch.object(assumptions, "MISSING_PERIOD_POLICY",
                          MissingPeriodPolicy.DEFER):
            intent = ExtractedIntent(mode=AnalysisMode.DESCRIPTIVE)
            outcome = assumptions.resolve(intent)

            self.assertIsNone(intent.time_period)
            self.assertEqual(outcome.assumptions, [])
            self.assertFalse(outcome.needs_user)

    def test_assume_fills_and_discloses(self):
        with patch.object(assumptions, "MISSING_PERIOD_POLICY",
                          MissingPeriodPolicy.ASSUME):
            intent = ExtractedIntent(mode=AnalysisMode.DESCRIPTIVE)
            outcome = assumptions.resolve(intent)

            self.assertEqual(intent.time_period, assumptions.CONVENTIONAL_PERIOD)
            self.assertTrue(
                any(assumptions.CONVENTIONAL_PERIOD in s for s in outcome.assumptions)
            )
            self.assertFalse(outcome.needs_user)

    def test_ask_raises_a_narrow_question(self):
        with patch.object(assumptions, "MISSING_PERIOD_POLICY",
                          MissingPeriodPolicy.ASK):
            intent = ExtractedIntent(mode=AnalysisMode.DESCRIPTIVE)
            outcome = assumptions.resolve(intent)

            self.assertTrue(outcome.needs_user)
            self.assertEqual(outcome.clarification.slot, "time_period")
            self.assertTrue(outcome.clarification.options)

    def test_a_stated_period_is_never_overridden_under_any_policy(self):
        for policy in MissingPeriodPolicy:
            with self.subTest(policy=policy):
                with patch.object(assumptions, "MISSING_PERIOD_POLICY", policy):
                    intent = ExtractedIntent(
                        mode=AnalysisMode.DESCRIPTIVE, time_period="last month"
                    )
                    outcome = assumptions.resolve(intent)
                    self.assertEqual(intent.time_period, "last month")
                    self.assertFalse(outcome.needs_user)

    def test_shipping_default_is_defer(self):
        # Guards against the decision being made silently in a later edit.
        self.assertEqual(
            assumptions.MISSING_PERIOD_POLICY,
            MissingPeriodPolicy.DEFER,
            "The missing-period rule is an unsettled business decision. "
            "Changing this constant requires a recorded ruling.",
        )


class TestMergeIntoPreservesExisting(unittest.TestCase):
    """Step 29 - append, never replace. Other stages write here too."""

    def test_existing_entries_survive(self):
        existing = ["No snapshot configuration was found for this connection."]
        merged = assumptions.merge_into(existing, ["Showing the top 10."])
        self.assertEqual(len(merged), 2)
        self.assertIn(existing[0], merged)

    def test_order_is_preserved(self):
        merged = assumptions.merge_into(["first"], ["second", "third"])
        self.assertEqual(merged, ["first", "second", "third"])

    def test_duplicates_are_dropped(self):
        merged = assumptions.merge_into(["same"], ["same", "other"])
        self.assertEqual(merged, ["same", "other"])

    def test_a_new_list_is_returned(self):
        # SemanticPlan is frozen; its list must be rebuilt, not mutated.
        existing = ["a"]
        merged = assumptions.merge_into(existing, ["b"])
        self.assertIsNot(merged, existing)
        self.assertEqual(existing, ["a"])

    def test_empty_inputs_are_safe(self):
        self.assertEqual(assumptions.merge_into(None, None), [])
        self.assertEqual(assumptions.merge_into([], ["  "]), [])


class TestSurfacing(unittest.TestCase):
    """Step 29 - the user must see the assumptions and how to change them."""

    def test_single_assumption_is_rendered(self):
        rendered = assumptions.render_for_user(["Assuming the current year."])
        self.assertIn("Assuming the current year.", rendered)

    def test_several_assumptions_are_listed(self):
        rendered = assumptions.render_for_user(["First one.", "Second one."])
        self.assertIn("First one.", rendered)
        self.assertIn("Second one.", rendered)
        self.assertIn("-", rendered)

    def test_nothing_renders_when_nothing_was_assumed(self):
        self.assertEqual(assumptions.render_for_user([]), "")
        self.assertEqual(assumptions.render_for_user(None), "")

    def test_clarification_renders_its_options(self):
        clarification = Clarification(
            slot="measure", question="Level or change?",
            options=["Lowest values", "Biggest change"], reason="",
        )
        rendered = assumptions.render_clarification(clarification)
        self.assertIn("Lowest values", rendered)
        self.assertIn("Biggest change", rendered)

    def test_unsupported_modes_are_stated_honestly(self):
        intent = ExtractedIntent(mode=AnalysisMode.DIAGNOSTIC,
                                 unsupported=["DIAGNOSTIC"])
        said = assumptions.describe_unsupported(intent)
        self.assertIn("cannot", said.lower())
        self.assertIn("why", said.lower())

    def test_prescriptive_limit_is_stated(self):
        intent = ExtractedIntent(mode=AnalysisMode.PRESCRIPTIVE,
                                 unsupported=["PRESCRIPTIVE"])
        said = assumptions.describe_unsupported(intent)
        self.assertIn("recommend", said.lower())

    def test_nothing_is_said_when_everything_is_supported(self):
        intent = ExtractedIntent(mode=AnalysisMode.DESCRIPTIVE)
        self.assertEqual(assumptions.describe_unsupported(intent), "")


if __name__ == "__main__":
    unittest.main()
