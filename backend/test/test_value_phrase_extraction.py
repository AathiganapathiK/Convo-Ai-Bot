"""
Gate 4 Step 2 - value-phrase extraction.

Every test here injects `invoke`, so nothing reaches a model, a provider or the
database. The point of the step is that the MODEL PROPOSES and the CODE
DISPOSES, so almost all of these feed a deliberately bad model response and
assert on what survives.

The two phrasing-invariance tests are the ones worth keeping forever: they are
the regression guard for the TELLAR class of failure, where a verb in the
question became a database value.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.extraction.models import (  # noqa: E402
    LOW_CONFIDENCE,
    MAX_VALUE_PHRASES,
    SlotName,
    ValuePhrase,
)
from ai.extraction.slot_extractor import (  # noqa: E402
    _validate_value_phrases,
    extract_intent,
)


METRICS = ["Sales", "Pending Amount", "Quantity"]
DIMENSIONS = ["City", "Brand", "Product Category", "District"]


def _validate(raw, question, metric_terms=None):
    notes = []
    kept = _validate_value_phrases(
        raw, question, metric_terms or [], DIMENSIONS, notes
    )
    return kept, notes


class TestValuePhraseValidation(unittest.TestCase):
    """The deterministic gate, exercised directly."""

    def test_phrase_absent_from_question_is_dropped(self):
        kept, notes = _validate(
            [{"phrase": "Bangalore", "confidence": 0.99}],
            "Show sales for Chennai",
        )
        self.assertEqual(kept, [])
        self.assertTrue(any("not present in the question" in n for n in notes))

    def test_phrase_present_is_kept_verbatim(self):
        kept, _ = _validate(
            [{"phrase": "Chennai", "confidence": 0.9}],
            "Show sales for Chennai",
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].phrase, "Chennai")
        self.assertIsNone(kept[0].dimension)
        self.assertFalse(kept[0].qualifier_explicit)

    def test_unconfigured_dimension_drops_binding_but_keeps_phrase(self):
        kept, notes = _validate(
            [{"phrase": "Chennai", "dimension": "Postcode", "confidence": 0.8}],
            "Show sales for Chennai postcode",
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].phrase, "Chennai")
        self.assertIsNone(kept[0].dimension)
        self.assertTrue(any("Postcode" in n for n in notes))

    def test_qualifier_explicit_requires_the_word_in_the_question(self):
        """The model may claim a binding; only the question can confirm it."""
        kept, notes = _validate(
            [{"phrase": "Chennai", "dimension": "City", "confidence": 0.9}],
            "Show sales for Chennai",          # no "city" anywhere
        )
        self.assertEqual(len(kept), 1)
        self.assertFalse(kept[0].qualifier_explicit)
        self.assertTrue(any("does not name that dimension" in n for n in notes))

    def test_qualifier_explicit_when_user_said_it(self):
        kept, _ = _validate(
            [{"phrase": "Chennai", "dimension": "City", "confidence": 0.9}],
            "Show sales for Chennai city",
        )
        self.assertTrue(kept[0].qualifier_explicit)
        self.assertEqual(kept[0].dimension, "City")

    def test_metric_word_is_not_a_value(self):
        kept, notes = _validate(
            [{"phrase": "pending", "confidence": 0.9}],
            "Show pending for Chennai",
            metric_terms=["Pending Amount"],
        )
        self.assertEqual(kept, [])
        self.assertTrue(any("names a metric" in n for n in notes))

    def test_partial_metric_overlap_is_still_a_value(self):
        """
        Only a phrase made ENTIRELY of metric words is refused.

        The example deliberately avoids any configured dimension name. It used
        to read "Amount City", which now has its "City" qualifier stripped and
        so reduces to the bare metric word "amount" - correctly refused, but no
        longer a test of partial overlap.
        """
        kept, _ = _validate(
            [{"phrase": "Amount Zone", "confidence": 0.7}],
            "Show sales for Amount Zone",
            metric_terms=["Pending Amount"],
        )
        self.assertEqual(len(kept), 1)

    def test_duplicate_phrases_collapse(self):
        kept, _ = _validate(
            [{"phrase": "Chennai"}, {"phrase": "chennai"}, {"phrase": "CHENNAI"}],
            "Show sales for Chennai",
        )
        self.assertEqual(len(kept), 1)

    def test_cap_at_max_value_phrases(self):
        words = ["alpha", "bravo", "charlie", "delta", "echo",
                 "foxtrot", "golf", "hotel", "india", "juliett"]
        question = "Show sales for " + " ".join(words)
        kept, notes = _validate([{"phrase": w} for w in words], question)
        self.assertEqual(len(kept), MAX_VALUE_PHRASES)
        self.assertTrue(any("more than" in n for n in notes))

    def test_bare_string_entries_are_accepted(self):
        kept, _ = _validate(["Chennai"], "Show sales for Chennai")
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].confidence, 0.0)

    def test_malformed_shapes_yield_empty_list(self):
        for bad in (None, "Chennai", 7, {"phrase": "Chennai"}):
            kept, _ = _validate(bad, "Show sales for Chennai")
            self.assertEqual(kept, [], bad)

    def test_junk_entries_are_skipped_individually(self):
        kept, _ = _validate(
            [None, 5, {}, {"phrase": ""}, {"phrase": "Chennai"}],
            "Show sales for Chennai",
        )
        self.assertEqual(len(kept), 1)

    def test_confidence_is_clamped(self):
        kept, _ = _validate(
            [{"phrase": "Chennai", "confidence": 5.0}], "Show sales for Chennai"
        )
        self.assertEqual(kept[0].confidence, 1.0)


class TestValuePhraseThroughExtraction(unittest.TestCase):
    """End to end through extract_intent, with the model stubbed."""

    def _run(self, question, payload):
        return extract_intent(
            question=question,
            vocabulary=_FakeVocabulary(),
            invoke=lambda purpose, prompt: json.dumps(payload),
        )

    def test_two_explicit_qualifiers_stay_independent(self):
        intent = self._run(
            "Show sales for Chennai city and Ramraj brand",
            {
                "metric_terms": ["Sales"],
                "value_phrases": [
                    {"phrase": "Chennai", "dimension": "City", "confidence": 0.95},
                    {"phrase": "Ramraj", "dimension": "Brand", "confidence": 0.95},
                ],
                "confidence": {"metric": 0.9},
            },
        )
        self.assertEqual(len(intent.value_phrases), 2)
        self.assertEqual(
            [(p.phrase, p.dimension, p.qualifier_explicit) for p in intent.value_phrases],
            [("Chennai", "City", True), ("Ramraj", "Brand", True)],
        )

    def test_bare_value_is_unqualified(self):
        intent = self._run(
            "Show sales for Chennai",
            {
                "metric_terms": ["Sales"],
                "value_phrases": [{"phrase": "Chennai", "confidence": 0.9}],
                "confidence": {"metric": 0.9},
            },
        )
        self.assertEqual(len(intent.value_phrases), 1)
        self.assertIsNone(intent.value_phrases[0].dimension)
        self.assertFalse(intent.value_phrases[0].qualifier_explicit)

    def test_pending_is_a_metric_not_a_value(self):
        intent = self._run(
            "Show pending for Chennai",
            {
                "metric_terms": ["Pending Amount"],
                "value_phrases": [
                    {"phrase": "pending", "confidence": 0.8},
                    {"phrase": "Chennai", "confidence": 0.9},
                ],
                "confidence": {"metric": 0.9},
            },
        )
        self.assertEqual([p.phrase for p in intent.value_phrases], ["Chennai"])

    def test_missing_field_is_empty_not_an_error(self):
        intent = self._run(
            "Show sales for Chennai",
            {"metric_terms": ["Sales"], "confidence": {"metric": 0.9}},
        )
        self.assertEqual(intent.value_phrases, [])

    def test_low_confidence_phrase_is_reported_weak(self):
        intent = self._run(
            "Show sales for Chennai",
            {
                "value_phrases": [{"phrase": "Chennai", "confidence": 0.2}],
                "confidence": {},
            },
        )
        self.assertIn(SlotName.VALUE_PHRASE, intent.low_confidence_slots())

    def test_to_dict_carries_value_phrases(self):
        intent = self._run(
            "Show sales for Chennai",
            {"value_phrases": [{"phrase": "Chennai", "confidence": 0.9}]},
        )
        payload = intent.to_dict()
        self.assertIn("value_phrases", payload)
        self.assertEqual(payload["value_phrases"][0]["phrase"], "Chennai")

    def test_empty_intent_has_no_value_phrases(self):
        self.assertEqual(ValuePhrase("x").dimension, None)
        intent = self._run("Show sales", {"metric_terms": ["Sales"]})
        self.assertEqual(intent.value_phrases, [])


class TestPhrasingInvariance(unittest.TestCase):
    """
    The TELLAR guard.

    Two phrasings of one question must produce the same (empty) value phrases.
    A verb is not a value, however confidently a model asserts otherwise.
    """

    PAYLOAD = {
        "mode": "RANKING",
        "measure": "CHANGE",
        "direction": "ASC",
        "metric_terms": ["Sales"],
        "dimension_terms": ["Product Category"],
        "value_phrases": [],
        "confidence": {"mode": 0.9, "metric": 0.9, "dimension": 0.9},
    }

    def _phrases(self, question, payload=None):
        intent = extract_intent(
            question=question,
            vocabulary=_FakeVocabulary(),
            invoke=lambda purpose, prompt: json.dumps(payload or self.PAYLOAD),
        )
        return [p.phrase for p in intent.value_phrases]

    def test_both_phrasings_agree(self):
        a = self._phrases("Which product categories are seeing reducing sales?")
        b = self._phrases(
            "Tell me which are the product categories for which sales are reducing"
        )
        self.assertEqual(a, [])
        self.assertEqual(a, b)

    def test_a_verb_offered_as_a_value_is_refused(self):
        payload = dict(self.PAYLOAD)
        payload["value_phrases"] = [{"phrase": "Tell", "confidence": 0.95}]
        phrases = self._phrases(
            "Tell me which are the product categories for which sales are reducing",
            payload,
        )
        # "Tell" IS in the question, so evidence alone cannot refuse it. It is
        # kept as a proposal here and the database is what will find nothing -
        # which is exactly the point: no value is invented, and no fuzzy match
        # over the whole question can turn it into TELLAR.
        self.assertEqual(phrases, ["Tell"])


class _FakeVocabulary:
    def metric_names(self):
        return list(METRICS)

    def dimension_names(self):
        return list(DIMENSIONS)


if __name__ == "__main__":
    unittest.main()
