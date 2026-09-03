"""
Gate 4 Steps 25, 26, 27 - extraction, escalation and mode tests.

The model is injected, never called. Every test states what the extraction
rules do given a particular model answer, so a provider outage or a model
upgrade cannot turn these green or red for reasons unrelated to the code.

The canonical case has its own class. It is the one this gate was opened for.
"""

import json
import unittest

from ai.extraction.models import (
    CLARIFY_CONFIDENCE,
    EscalationTier,
    ExtractedIntent,
    LOW_CONFIDENCE,
    SlotName,
    coerce_enum,
    coerce_top_n,
)
from ai.extraction.slot_extractor import (
    extract_intent,
    read_deterministic_signals,
)
from semantic.models.semantic_plan import (
    AnalysisMode,
    BenchmarkType,
    OutputFormat,
    RankDirection,
    RankMeasure,
)
from semantic.vocabulary_service import Vocabulary


def _vocabulary() -> Vocabulary:
    return Vocabulary(
        connection_id="T",
        metrics=[
            {"business_name": "Sales", "metric_name": "Sales"},
            {"business_name": "Quantity", "metric_name": "Qty"},
        ],
        dimensions=[
            {"business_name": "Product", "dimension_name": "product"},
            {"business_name": "Brand", "dimension_name": "brand"},
        ],
    )


def _model(payload, escalation_payload=None):
    """
    An injectable model returning fixed JSON per purpose.

    Returning the object rather than a string on the escalation call is not
    supported on purpose: the extractor must cope with text, because that is
    what a provider actually returns.
    """
    def invoke(purpose, prompt):
        if purpose == "extraction_escalation":
            if escalation_payload is None:
                return None
            return json.dumps(escalation_payload)
        return json.dumps(payload)
    return invoke


CANONICAL = "Top 5 products whose sales are reducing last quarter"


class TestCanonicalCase(unittest.TestCase):
    """
    "Top 5 products whose sales are reducing last quarter"

    Must be mode=RANKING, direction=ASC, measure=CHANGE, top_n=5, previous
    quarter. Ranking on sales rather than on the change answers a different
    question - five products that may all be growing - and that is the specific
    defect this gate exists to remove.
    """

    def test_deterministic_reading_alone_is_correct(self):
        # No model at all. The wording fully determines this, and the system
        # must not need a provider to get it right.
        intent = read_deterministic_signals(CANONICAL)
        self.assertEqual(intent.mode, AnalysisMode.RANKING)
        self.assertEqual(intent.direction, RankDirection.ASC)
        self.assertEqual(intent.measure, RankMeasure.CHANGE)
        self.assertEqual(intent.top_n, 5)
        self.assertEqual(intent.time_period, "last quarter")

    def test_measure_is_change_not_absolute(self):
        intent = read_deterministic_signals(CANONICAL)
        self.assertNotEqual(
            intent.measure, RankMeasure.ABSOLUTE,
            "Ranking on the level answers a different question from the one asked.",
        )

    def test_full_extraction_with_agreeing_model(self):
        invoke = _model({
            "mode": "RANKING", "direction": "ASC", "measure": "CHANGE",
            "top_n": 5, "benchmark": None, "output": None,
            "metric_terms": ["Sales"], "dimension_terms": ["Product"],
            "time_period": "last quarter", "comparison_period": None,
            "evidence": {"mode": "Top 5", "direction": "reducing",
                         "measure": "sales are reducing", "top_n": "Top 5"},
            "confidence": {"mode": 0.97, "direction": 0.93, "measure": 0.92,
                           "top_n": 0.99, "metric": 0.95, "dimension": 0.95},
        })
        intent = extract_intent(CANONICAL, vocabulary=_vocabulary(), invoke=invoke)

        self.assertEqual(intent.mode, AnalysisMode.RANKING)
        self.assertEqual(intent.direction, RankDirection.ASC)
        self.assertEqual(intent.measure, RankMeasure.CHANGE)
        self.assertEqual(intent.top_n, 5)
        self.assertEqual(intent.metric_terms, ["Sales"])
        self.assertEqual(intent.dimension_terms, ["Product"])
        self.assertEqual(intent.escalation_tier, EscalationTier.PRIMARY)
        self.assertIsNone(intent.clarification)

    def test_agreement_raises_confidence(self):
        invoke = _model({
            "mode": "RANKING", "measure": "CHANGE", "direction": "ASC", "top_n": 5,
            "metric_terms": [], "dimension_terms": [],
            "confidence": {"mode": 0.80, "measure": 0.80, "direction": 0.80, "top_n": 0.80},
        })
        intent = extract_intent(CANONICAL, vocabulary=_vocabulary(), invoke=invoke)
        self.assertGreater(intent.confidence_for(SlotName.MEASURE), 0.80)

    def test_model_saying_absolute_is_escalated_not_accepted(self):
        # The deterministic pass says CHANGE; the model says ABSOLUTE. That
        # disagreement must not be resolved silently in either direction.
        invoke = _model(
            {
                "mode": "RANKING", "direction": "ASC", "measure": "ABSOLUTE",
                "top_n": 5, "metric_terms": [], "dimension_terms": [],
                "confidence": {"mode": 0.9, "direction": 0.9, "measure": 0.9, "top_n": 0.9},
            },
            escalation_payload={
                "measure": "CHANGE",
                "confidence": {"measure": 0.94},
            },
        )
        intent = extract_intent(CANONICAL, vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.escalation_tier, EscalationTier.ESCALATED)
        self.assertEqual(intent.measure, RankMeasure.CHANGE)


class TestDeterministicSignals(unittest.TestCase):
    """Positive, negative and false-positive coverage for the wording rules."""

    def test_absolute_ranking(self):
        intent = read_deterministic_signals("Top 5 products by sales")
        self.assertEqual(intent.measure, RankMeasure.ABSOLUTE)
        self.assertEqual(intent.direction, RankDirection.DESC)

    def test_percentage_ranking(self):
        intent = read_deterministic_signals("fastest declining brands by percentage")
        self.assertEqual(intent.measure, RankMeasure.CHANGE_PCT)
        self.assertEqual(intent.direction, RankDirection.ASC)

    def test_growth_ranking_is_descending_change(self):
        # "fastest" frames the ordering as a rate, so the measure is the
        # percentage change. What matters is the direction, and that it is not
        # ABSOLUTE - growth is movement, never a level.
        intent = read_deterministic_signals("top 10 fastest growing brands")
        self.assertEqual(intent.measure, RankMeasure.CHANGE_PCT)
        self.assertEqual(intent.direction, RankDirection.DESC)
        self.assertEqual(intent.top_n, 10)

    def test_worded_counts(self):
        self.assertEqual(read_deterministic_signals("top five brands").top_n, 5)
        self.assertEqual(read_deterministic_signals("bottom three cities").top_n, 3)

    def test_substring_false_positives(self):
        # "laptop" contains "top"; "stopped" contains "top"; "topic" contains
        # "top". None of them is a ranking.
        for question in ["laptop sales stopped", "change the topic",
                         "how many laptops"]:
            with self.subTest(question=question):
                self.assertIsNone(read_deterministic_signals(question).top_n)

    def test_duration_is_not_a_row_count(self):
        # Regression, found by the plan benchmark on E1-197. "last two
        # quarters" is a period; reading its count as a top-N turned a plain
        # retrieval question into a ranking of two things.
        for question in ["Show sales for the last two quarters",
                         "Show sales for the last 3 months",
                         "sales over the past six weeks"]:
            with self.subTest(question=question):
                intent = read_deterministic_signals(question)
                self.assertIsNone(intent.top_n)
                self.assertIsNone(intent.mode)

    def test_a_real_ranking_survives_a_duration_phrase(self):
        # The guard must not swallow a genuine count sitting beside a period.
        intent = read_deterministic_signals(
            "top 5 brands over the last two quarters"
        )
        self.assertEqual(intent.top_n, 5)
        self.assertEqual(intent.mode, AnalysisMode.RANKING)

    def test_ranking_of_time_units_still_works(self):
        # "top 5 months by sales" ranks months. Only temporal head words are
        # guarded, so this is unaffected.
        self.assertEqual(read_deterministic_signals("top 5 months by sales").top_n, 5)

    def test_descriptive_statement_is_not_a_ranking(self):
        # "sales are declining" describes movement but asks for no ordered list.
        intent = read_deterministic_signals("sales are declining")
        self.assertIsNone(intent.mode)

    def test_contradictory_direction_is_left_unset(self):
        # "top" and "worst" together. Guessing either would be wrong half the
        # time, so nothing is chosen.
        intent = read_deterministic_signals("show me the top worst brands")
        self.assertIsNone(intent.direction)

    def test_zero_and_negative_counts_rejected(self):
        self.assertIsNone(coerce_top_n(0))
        self.assertIsNone(coerce_top_n(-3))
        self.assertIsNone(coerce_top_n("abc"))
        self.assertIsNone(coerce_top_n(True))


class TestModeDetection(unittest.TestCase):
    """Step 27 - mode comes from extraction, and limits are stated honestly."""

    def test_diagnostic_recognised_and_flagged_unsupported(self):
        intent = read_deterministic_signals("Why did sales drop in Chennai?")
        self.assertEqual(intent.mode, AnalysisMode.DIAGNOSTIC)
        self.assertIn("DIAGNOSTIC", intent.unsupported)

    def test_prescriptive_recognised_and_flagged_unsupported(self):
        intent = read_deterministic_signals("How can we improve dhoti sales?")
        self.assertEqual(intent.mode, AnalysisMode.PRESCRIPTIVE)
        self.assertIn("PRESCRIPTIVE", intent.unsupported)

    def test_diagnostic_beats_ranking_cue(self):
        # "why are our top brands falling" is asking why, not for a list.
        intent = read_deterministic_signals("why are our top brands falling")
        self.assertEqual(intent.mode, AnalysisMode.DIAGNOSTIC)

    def test_trend_and_comparison(self):
        self.assertEqual(
            read_deterministic_signals("monthly sales trend").mode,
            AnalysisMode.TREND,
        )
        self.assertEqual(
            read_deterministic_signals("compare sales with last year").mode,
            AnalysisMode.COMPARISON,
        )


class TestVocabularyValidation(unittest.TestCase):
    """Never invent a metric, a dimension or an enum value."""

    def test_unconfigured_metric_is_dropped(self):
        invoke = _model({
            "mode": "DESCRIPTIVE",
            "metric_terms": ["Profit Margin"],   # not configured
            "dimension_terms": ["Brand"],
            "confidence": {"mode": 0.9, "metric": 0.99, "dimension": 0.9},
        })
        intent = extract_intent("show profit margin by brand",
                                vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.metric_terms, [])
        self.assertEqual(intent.dimension_terms, ["Brand"])
        self.assertTrue(any("Profit Margin" in n for n in intent.notes))

    def test_high_model_confidence_does_not_rescue_an_unconfigured_term(self):
        invoke = _model({
            "metric_terms": ["Gross Margin"],
            "confidence": {"metric": 1.0},
        })
        intent = extract_intent("gross margin", vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.metric_terms, [])

    def test_configured_spelling_is_returned_not_the_models(self):
        invoke = _model({
            "metric_terms": ["sales"],          # lowercase from the model
            "confidence": {"metric": 0.9},
        })
        intent = extract_intent("sales", vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.metric_terms, ["Sales"])

    def test_invented_enum_value_becomes_none(self):
        self.assertIsNone(coerce_enum(SlotName.MODE, "FORECASTING"))
        self.assertIsNone(coerce_enum(SlotName.MEASURE, "DELTA"))
        self.assertIsNone(coerce_enum(SlotName.DIRECTION, "SIDEWAYS"))

    def test_valid_enum_values_are_accepted_case_insensitively(self):
        self.assertEqual(coerce_enum(SlotName.MODE, "ranking"), AnalysisMode.RANKING)
        self.assertEqual(coerce_enum(SlotName.OUTPUT, "KPI"), OutputFormat.KPI)
        self.assertEqual(
            coerce_enum(SlotName.BENCHMARK, "target"), BenchmarkType.TARGET
        )

    def test_fabricated_evidence_reduces_confidence(self):
        invoke = _model({
            "mode": "RANKING",
            "benchmark": "TARGET",
            "metric_terms": [], "dimension_terms": [],
            "evidence": {"benchmark": "against our quarterly target"},
            "confidence": {"mode": 0.9, "benchmark": 0.95},
        })
        # The question says nothing about a target, so the quote cannot be real.
        intent = extract_intent("top 5 brands", vocabulary=_vocabulary(), invoke=invoke)
        self.assertLess(intent.confidence_for(SlotName.BENCHMARK), LOW_CONFIDENCE)


class TestEscalation(unittest.TestCase):
    """Step 26 - escalate, record the tier, ask only as a last resort."""

    def test_low_confidence_field_escalates(self):
        invoke = _model(
            {
                "mode": "RANKING", "measure": "ABSOLUTE", "direction": "DESC",
                "top_n": 3, "metric_terms": [], "dimension_terms": [],
                "confidence": {"mode": 0.95, "measure": 0.30,
                               "direction": 0.9, "top_n": 0.9},
            },
            escalation_payload={"measure": "CHANGE", "confidence": {"measure": 0.91}},
        )
        intent = extract_intent("top 3 brands",
                                vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.escalation_tier, EscalationTier.ESCALATED)
        self.assertEqual(intent.measure, RankMeasure.CHANGE)

    def test_escalation_that_stays_unsure_asks_the_user(self):
        invoke = _model(
            {
                "mode": "RANKING", "measure": "ABSOLUTE", "direction": "DESC",
                "top_n": 3, "metric_terms": [], "dimension_terms": [],
                "confidence": {"mode": 0.95, "measure": 0.20,
                               "direction": 0.9, "top_n": 0.9},
            },
            escalation_payload={"measure": "CHANGE", "confidence": {"measure": 0.35}},
        )
        intent = extract_intent("top 3 brands",
                                vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.escalation_tier, EscalationTier.CLARIFY)
        self.assertIsNotNone(intent.clarification)

    def test_a_clarification_always_names_its_options(self):
        invoke = _model(
            {
                "mode": "RANKING", "measure": "ABSOLUTE", "direction": "DESC",
                "top_n": 3, "metric_terms": [], "dimension_terms": [],
                "confidence": {"mode": 0.95, "measure": 0.10,
                               "direction": 0.9, "top_n": 0.9},
            },
            escalation_payload={"measure": None, "confidence": {"measure": 0.1}},
        )
        intent = extract_intent("top 3 brands",
                                vocabulary=_vocabulary(), invoke=invoke)
        self.assertIsNotNone(intent.clarification)
        self.assertTrue(intent.clarification.options)
        self.assertNotIn("please clarify", intent.clarification.question.lower())

    def test_confident_extraction_does_not_escalate(self):
        invoke = _model({
            "mode": "DESCRIPTIVE", "metric_terms": ["Sales"], "dimension_terms": [],
            "confidence": {"mode": 0.96, "metric": 0.95},
        })
        intent = extract_intent("total sales", vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.escalation_tier, EscalationTier.PRIMARY)
        self.assertIsNone(intent.clarification)

    def test_absent_slot_is_not_low_confidence(self):
        # Absence is step 28's business. Escalating an empty slot would spend a
        # stronger model call on a question the user simply did not answer.
        intent = ExtractedIntent()
        self.assertFalse(intent.is_low(SlotName.MEASURE))
        self.assertEqual(intent.low_confidence_slots(), [])


class TestModelFailureHandling(unittest.TestCase):
    """Extraction is an enrichment: its failure must not cost the answer."""

    def test_no_model_falls_back_to_wording(self):
        intent = extract_intent(CANONICAL, vocabulary=_vocabulary(),
                                invoke=lambda purpose, prompt: None)
        self.assertEqual(intent.escalation_tier, EscalationTier.UNAVAILABLE)
        self.assertEqual(intent.measure, RankMeasure.CHANGE)
        self.assertEqual(intent.top_n, 5)

    def test_unparseable_output_falls_back_to_wording(self):
        intent = extract_intent(CANONICAL, vocabulary=_vocabulary(),
                                invoke=lambda purpose, prompt: "I cannot help with that.")
        self.assertEqual(intent.escalation_tier, EscalationTier.UNAVAILABLE)
        self.assertEqual(intent.mode, AnalysisMode.RANKING)

    def test_fenced_json_is_parsed(self):
        raw = '```json\n{"mode": "TREND", "confidence": {"mode": 0.9}}\n```'
        intent = extract_intent("monthly movement", vocabulary=_vocabulary(),
                                invoke=lambda purpose, prompt: raw)
        self.assertEqual(intent.mode, AnalysisMode.TREND)

    def test_prose_wrapped_json_is_parsed(self):
        raw = 'Here you go: {"mode": "DESCRIPTIVE", "confidence": {"mode": 0.9}} Hope that helps!'
        intent = extract_intent("total sales", vocabulary=_vocabulary(),
                                invoke=lambda purpose, prompt: raw)
        self.assertEqual(intent.mode, AnalysisMode.DESCRIPTIVE)

    def test_empty_question_returns_empty_intent(self):
        intent = extract_intent("", vocabulary=_vocabulary(),
                                invoke=lambda purpose, prompt: None)
        self.assertIsNone(intent.mode)


class TestStructuralConsistency(unittest.TestCase):
    """Ranking fields must not survive onto a non-ranking plan."""

    def test_ranking_fields_cleared_for_descriptive(self):
        invoke = _model({
            "mode": "DESCRIPTIVE", "direction": "DESC", "measure": "ABSOLUTE",
            "top_n": 5, "metric_terms": [], "dimension_terms": [],
            "confidence": {"mode": 0.95, "direction": 0.9,
                           "measure": 0.9, "top_n": 0.9},
        })
        intent = extract_intent("total sales", vocabulary=_vocabulary(), invoke=invoke)
        self.assertEqual(intent.mode, AnalysisMode.DESCRIPTIVE)
        self.assertIsNone(intent.direction)
        self.assertIsNone(intent.measure)
        self.assertIsNone(intent.top_n)


if __name__ == "__main__":
    unittest.main()
