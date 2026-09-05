"""
Offline: conversational behaviour under candidate_scoped, plus the adversarial
cases the earlier matrix did not cover.

Two things are being asked here.

1. FOLLOW_UP / ENTITY_TOPIC_SHIFT (16 of the 87 benchmark failures) are the
   largest bucket this work has not touched, and `last_followup_context` is
   class-level state the new path populates on a different code path. If
   candidate_scoped breaks conversational carry-over, it must show up here.
   These tests characterise behaviour; they do not redesign it.

2. The adversarial shapes added after the shadow comparison found real
   defects - singular/plural, near-spelling typos, nested values, and the
   weak-evidence cases the scorer now deliberately refuses.

Everything is mock-backed. No database, no model, no network.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fixtures.mock_value_provider import MockDimensionValueProvider  # noqa: E402
from semantic.candidate_judge import (  # noqa: E402
    CandidateJudge,
    apply_judge,
    competitive_candidates,
    judge_enabled,
)
from semantic.candidate_scoring import (  # noqa: E402
    AMBIGUOUS,
    RESOLVED,
    UNRESOLVED,
    resolve_phrase,
)
from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402


class _Phrase:
    def __init__(self, phrase, dimension=None, qualifier_explicit=False):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit


class Base(unittest.TestCase):
    MODE = "candidate_scoped"

    def setUp(self):
        self._previous = os.environ.get("SEMANTIC_VALUE_MODE")
        if self.MODE is None:
            os.environ.pop("SEMANTIC_VALUE_MODE", None)
        else:
            os.environ["SEMANTIC_VALUE_MODE"] = self.MODE
        self.provider = MockDimensionValueProvider()
        self._real_loader = DimensionValueResolver._load_dimension_values
        DimensionValueResolver._load_dimension_values = lambda self, connection_id: []
        self.resolver = DimensionValueResolver()
        self._real_members_of = DimensionValueResolver._members_of
        DimensionValueResolver._members_of = staticmethod(lambda *a, **k: ())

    def tearDown(self):
        DimensionValueResolver._members_of = self._real_members_of
        DimensionValueResolver._load_dimension_values = self._real_loader
        os.environ.pop("SEMANTIC_VALUE_MODE", None)
        if self._previous is not None:
            os.environ["SEMANTIC_VALUE_MODE"] = self._previous

    def run_question(self, question, phrases, previous_context=None):
        return self.resolver.resolve_matches(
            "conn-1", question,
            previous_semantic_context=previous_context,
            value_phrases=phrases,
            value_provider=self.provider,
        )

    @staticmethod
    def values(result):
        return sorted({m.get("value") for m in (result or []) if isinstance(m, dict)})

    def scored(self, phrase, question, dimension=None, qualifier_explicit=False):
        search = dimension if qualifier_explicit else None
        return resolve_phrase(
            self.provider.get_candidates(search, phrase), phrase, question,
            qualifier_explicit=qualifier_explicit, phrase_dimension=dimension,
        )


# ---------------------------------------------------------------------------
# 6. Follow-up and topic shift
# ---------------------------------------------------------------------------
class TestFollowUpUnderCandidateScoped(Base):

    PREVIOUS = {
        "resolved_values": [
            {"value": "CHENNAI", "business_name": "City",
             "table_name": "SALES", "column_name": "City"}
        ],
        "dimensions": [{"business_name": "City"}],
    }

    def test_followup_with_its_own_value_resolves_that_value(self):
        """A follow-up naming a new value must use the new value, not the old."""
        result = self.run_question(
            "Now show quantity for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
            previous_context=self.PREVIOUS,
        )
        self.assertEqual(self.values(result), ["RAMRAJ"])

    def test_followup_context_is_published_by_the_resolve_entry_point(self):
        """
        `resolve()` is what publishes last_followup_context; resolve_matches()
        does not, in EITHER mode. Verified directly rather than assumed: the
        first version of this test asserted the class attribute after
        resolve_matches() and "failed" identically under legacy, which would
        have been reported as a candidate_scoped regression that does not
        exist.
        """
        DimensionValueResolver.last_followup_context = "SENTINEL"
        DimensionValueResolver.resolve(
            "conn-1", "Now show quantity for Ramraj brand",
            previous_semantic_context=self.PREVIOUS,
            value_phrases=[_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
            value_provider=self.provider,
        )
        self.assertNotEqual(DimensionValueResolver.last_followup_context, "SENTINEL")

    def test_candidate_scoped_populates_followup_context_at_least_as_well(self):
        """Not a weaker path: it must not leave context emptier than legacy."""
        def context_for(mode):
            previous = os.environ.get("SEMANTIC_VALUE_MODE")
            os.environ.pop("SEMANTIC_VALUE_MODE", None)
            if mode:
                os.environ["SEMANTIC_VALUE_MODE"] = mode
            try:
                resolver = DimensionValueResolver()
                resolver.resolve_matches(
                    "conn-1", "Now show quantity for Ramraj brand",
                    previous_semantic_context=self.PREVIOUS,
                    value_phrases=[_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
                    value_provider=self.provider,
                )
                return getattr(resolver, "followup_context", None)
            finally:
                os.environ.pop("SEMANTIC_VALUE_MODE", None)
                if previous is not None:
                    os.environ["SEMANTIC_VALUE_MODE"] = previous

        legacy = context_for(None)
        scoped = context_for("candidate_scoped")
        if legacy is not None:
            self.assertIsNotNone(scoped)
        self.assertIsNotNone(scoped)

    def test_topic_shift_does_not_inherit_the_previous_value(self):
        """ENTITY_TOPIC_SHIFT: a new entity must not be contaminated."""
        result = self.run_question(
            "What about Mumbai",
            [_Phrase("Mumbai")],
            previous_context=self.PREVIOUS,
        )
        self.assertEqual(self.values(result), ["MUMBAI"])
        self.assertNotIn("CHENNAI", self.values(result))

    def test_followup_without_a_value_phrase_uses_the_legacy_path(self):
        """
        "Break it down by month" carries no value. With no phrases the new path
        is not engaged at all, so conversational handling is untouched.
        """
        result = self.run_question(
            "Break it down by month", [], previous_context=self.PREVIOUS,
        )
        self.assertEqual(self.values(result), [])

    def test_previous_context_does_not_alter_scoring(self):
        """Scoring reads the phrase and the question - never the last turn."""
        without = self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        with_ctx = self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
            previous_context=self.PREVIOUS,
        )
        self.assertEqual(self.values(without), self.values(with_ctx))


# ---------------------------------------------------------------------------
# 2. Adversarial shapes found by the shadow comparison
# ---------------------------------------------------------------------------
class TestSingularPluralAndTypos(Base):

    def test_plural_phrase_reaches_singular_value(self):
        r = self.scored("shirts", "Show sales for shirts")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "SHIRT")

    def test_singular_phrase_reaches_plural_value(self):
        """The stem comparison must work in both directions."""
        provider = MockDimensionValueProvider({"Product": ["SHIRTS"]})
        r = resolve_phrase(
            provider.get_candidates(None, "shirt"), "shirt", "Show sales for shirt")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "SHIRTS")

    def test_doubled_letter_typo_resolves(self):
        """'Ramrajj' regressed against legacy until near-spelling was reweighted."""
        r = self.scored("Ramrajj", "Show sales for Ramrajj brand",
                        "Brand", qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "RAMRAJ")

    def test_truncation_typo_resolves(self):
        r = self.scored("Coimbator", "Show sales for Coimbator city",
                        "City", qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "COIMBATORE")

    def test_unrelated_short_word_does_not_resolve(self):
        """Near-spelling must not become a licence to match anything short."""
        r = self.scored("xyz", "Show sales for xyz")
        self.assertEqual(r.status, UNRESOLVED)


class TestWeakEvidenceIsRefused(Base):
    """
    The scorer deliberately refuses matches the legacy path accepts.

    One shared stem out of three candidate tokens is weak evidence. Legacy
    resolves "children wear" to "N--NIGHT WEARS" on exactly that; the shadow
    comparison counts our refusal as a regression against recorded
    expectations. It is recorded here as intended behaviour rather than
    silently tuned away, and it is the single clearest question for real-data
    review: is the expectation right, or is legacy over-matching?
    """

    def test_single_shared_token_is_not_enough(self):
        provider = MockDimensionValueProvider(
            {"Product Category": ["N--NIGHT WEARS", "ETHNIC WEAR"]})
        r = resolve_phrase(
            provider.get_candidates(None, "children wear"),
            "children wear", "Show sales for children wear")
        self.assertEqual(r.status, UNRESOLVED)
        best = max((s.score for s in r.scored), default=0.0)
        self.assertLess(best, 0.45)

    def test_two_of_two_shared_tokens_is_enough(self):
        provider = MockDimensionValueProvider(
            {"Product Category": ["NIGHT WEAR", "ETHNIC WEAR"]})
        r = resolve_phrase(
            provider.get_candidates(None, "night wear"),
            "night wear", "Show sales for night wear")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "NIGHT WEAR")


class TestNestedValues(Base):

    def test_nested_value_needs_question_support(self):
        provider = MockDimensionValueProvider(
            {"Brand": ["RAMRAJ", "RAMRAJ PANT", "RAMRAJ PANT CLASSIC"]})
        r = resolve_phrase(
            provider.get_candidates("Brand", "Ramraj pant"),
            "Ramraj pant", "Show sales for Ramraj pant brand",
            qualifier_explicit=True, phrase_dimension="Brand")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "RAMRAJ PANT")

    def test_deepest_nesting_wins_when_the_question_says_so(self):
        provider = MockDimensionValueProvider(
            {"Brand": ["RAMRAJ", "RAMRAJ PANT", "RAMRAJ PANT CLASSIC"]})
        r = resolve_phrase(
            provider.get_candidates("Brand", "Ramraj pant classic"),
            "Ramraj pant classic", "Show sales for Ramraj pant classic brand",
            qualifier_explicit=True, phrase_dimension="Brand")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "RAMRAJ PANT CLASSIC")


# ---------------------------------------------------------------------------
# 5. The judge seam - present, constrained, and switched off
# ---------------------------------------------------------------------------
class TestJudgeSeam(Base):

    class _AlwaysPicksFirst(CandidateJudge):
        def choose(self, resolution, question):
            return resolution.competitive[0].value

    class _Inventor(CandidateJudge):
        def choose(self, resolution, question):
            return "A VALUE NOBODY OFFERED"

    def test_no_judge_is_enabled(self):
        self.assertFalse(judge_enabled())

    def test_apply_judge_is_a_no_op_while_disabled(self):
        r = self.scored("Chennai", "Show sales for Chennai")
        self.assertEqual(r.status, AMBIGUOUS)
        self.assertIs(apply_judge(r, "Show sales for Chennai", self._AlwaysPicksFirst()), r)

    def test_a_judge_could_never_invent_a_value(self):
        """Enforced by the seam, not by the judge's good behaviour."""
        import semantic.candidate_judge as cj
        original = cj.judge_enabled
        cj.judge_enabled = lambda: True
        try:
            r = self.scored("Chennai", "Show sales for Chennai")
            out = cj.apply_judge(r, "Show sales for Chennai", self._Inventor())
            self.assertEqual(out.status, AMBIGUOUS)
            self.assertIsNone(out.winner)
        finally:
            cj.judge_enabled = original

    def test_a_judge_is_never_offered_a_resolved_phrase(self):
        import semantic.candidate_judge as cj
        original = cj.judge_enabled
        cj.judge_enabled = lambda: True
        try:
            r = self.scored("Mumbai", "Show sales for Mumbai")
            self.assertEqual(r.status, RESOLVED)
            self.assertIs(cj.apply_judge(r, "q", self._AlwaysPicksFirst()), r)
        finally:
            cj.judge_enabled = original

    def test_a_judge_cannot_rescue_an_unresolved_phrase(self):
        import semantic.candidate_judge as cj
        original = cj.judge_enabled
        cj.judge_enabled = lambda: True
        try:
            r = self.scored("Atlantis", "Show sales for Atlantis")
            self.assertEqual(r.status, UNRESOLVED)
            self.assertIs(cj.apply_judge(r, "q", self._AlwaysPicksFirst()), r)
        finally:
            cj.judge_enabled = original

    def test_competitive_candidates_reports_what_a_judge_would_see(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Chennai and Mumbai",
            [_Phrase("Chennai"), _Phrase("Mumbai")],
            provider=self.provider,
        )
        pending = competitive_candidates(resolutions)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].phrase, "Chennai")


class TestLegacyDefaultUnaffected(Base):
    """3. Production default must remain legacy throughout."""

    MODE = None

    def test_default_mode_is_legacy(self):
        self.assertFalse(DimensionValueResolver.candidate_scoped_enabled())

    def test_legacy_ignores_phrases_and_provider(self):
        result = self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        self.assertEqual(self.values(result), [])


if __name__ == "__main__":
    unittest.main()
