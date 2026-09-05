"""
Step 4 - offline matrix for the provider contract, deterministic candidate
scoring, and the ambiguity decision.

Runs with no database, no model and no network. Every value any test here can
resolve was placed in test/fixtures/mock_value_provider.py by this repository,
which is what makes the provenance assertions meaningful: a resolved value came
from a provider or it did not appear at all.

These tests encode intended semantics, not observed output. Where the intended
behaviour is a judgement call - notably bare "Ramraj" - the reasoning is written
into the test so a future reader can disagree with the decision rather than
having to reverse-engineer it.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fixtures.mock_value_provider import (  # noqa: E402
    FIXTURE_VALUES,
    MockDimensionValueProvider,
)
from semantic.candidate_scoring import (  # noqa: E402
    AMBIGUOUS,
    RESOLVED,
    UNRESOLVED,
    resolve_phrase,
)
from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402
from semantic.value_provider import (  # noqa: E402
    PROVENANCE_MOCK,
    DimensionValueProvider,
    ValueCandidate,
)


class _Phrase:
    def __init__(self, phrase, dimension=None, qualifier_explicit=False, confidence=1.0):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit
        self.confidence = confidence


class Base(unittest.TestCase):
    def setUp(self):
        self.provider = MockDimensionValueProvider()

    def resolve(self, question, phrase, dimension=None, qualifier_explicit=False):
        search_dim = dimension if qualifier_explicit else None
        candidates = self.provider.get_candidates(search_dim, phrase)
        return resolve_phrase(
            candidates, phrase, question,
            qualifier_explicit=qualifier_explicit,
            phrase_dimension=dimension,
        )


# ---------------------------------------------------------------------------
# 1-3, 22: matching the phrase itself
# ---------------------------------------------------------------------------
class TestPhraseMatching(Base):

    def test_01_exact_value(self):
        r = self.resolve("Show sales for Mumbai", "Mumbai")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "MUMBAI")

    def test_02_case_differences(self):
        for spelling in ("mumbai", "MUMBAI", "MuMbAi"):
            r = self.resolve("Show sales for %s" % spelling, spelling)
            self.assertEqual(r.status, RESOLVED, spelling)
            self.assertEqual(r.winner.value, "MUMBAI")

    def test_02b_punctuation_and_whitespace(self):
        for spelling in ("  Mumbai  ", "Mumbai,", "(Mumbai)"):
            r = self.resolve("Show sales for %s" % spelling, spelling)
            self.assertEqual(r.status, RESOLVED, spelling)
            self.assertEqual(r.winner.value, "MUMBAI")

    def test_03_spelling_variation(self):
        """'Coimbator' is a real misspelling users type; it must still land."""
        r = self.resolve("Show sales for Coimbator city", "Coimbator",
                         "City", qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "COIMBATORE")

    def test_22_phrase_inside_a_longer_sentence(self):
        r = self.resolve(
            "Could you please show me the total sales figures for Mumbai last quarter",
            "Mumbai",
        )
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "MUMBAI")

    def test_16_fake_value_stays_unresolved(self):
        r = self.resolve("Show sales for Atlantis", "Atlantis")
        self.assertEqual(r.status, UNRESOLVED)
        self.assertIsNone(r.winner)


# ---------------------------------------------------------------------------
# 4, 5, 6, 17: dimension qualification
# ---------------------------------------------------------------------------
class TestDimensionQualification(Base):

    def test_04_explicit_dimension_narrows(self):
        r = self.resolve("Show sales for Chennai city", "Chennai",
                         "City", qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.dimension, "City")

    def test_05_06_bare_value_keeps_cross_dimension_ambiguity(self):
        r = self.resolve("Show sales for Chennai", "Chennai")
        self.assertEqual(r.status, AMBIGUOUS)
        self.assertEqual(sorted({s.dimension for s in r.competitive}),
                         ["City", "District"])

    def test_14_vt_ambiguous_across_brand_and_state(self):
        r = self.resolve("Show sales for VT", "VT")
        self.assertEqual(r.status, AMBIGUOUS)
        self.assertEqual(sorted({s.dimension for s in r.competitive}),
                         ["Brand", "State"])

    def test_14b_vt_with_qualifier_resolves(self):
        r = self.resolve("Show sales for VT brand", "VT", "Brand",
                         qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.dimension, "Brand")

    def test_17_fake_dimension_is_not_trusted(self):
        """
        An unconfigured dimension must narrow nothing, and must not narrow to
        nothing either - the user still named a real value.
        """
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Chennai warehouse",
            [_Phrase("Chennai", "Warehouse", qualifier_explicit=True)],
            provider=self.provider,
        )
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0].status, AMBIGUOUS)
        self.assertEqual(
            sorted({s.dimension for s in resolutions[0].competitive}),
            ["City", "District"],
        )


# ---------------------------------------------------------------------------
# 7, 8, 9, 23: the Ramraj family - the reason this module exists
# ---------------------------------------------------------------------------
class TestRamrajRegression(Base):

    def test_08_ramraj_brand_resolves_to_the_exact_value(self):
        """
        THE regression. Phrase-scoping alone returned 13 candidates live,
        because every RAMRAJ* value clears a fuzzy cutoff against "Ramraj".
        The exact normalized match must dominate, and the extensions must be
        penalised for extra words the question never contained.
        """
        r = self.resolve("Show sales for Ramraj brand", "Ramraj",
                         "Brand", qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "RAMRAJ")
        self.assertEqual(len(r.competitive), 1)

    def test_07_exact_candidate_outscores_every_fuzzy_extension(self):
        r = self.resolve("Show sales for Ramraj brand", "Ramraj",
                         "Brand", qualifier_explicit=True)
        by_value = {s.value: s.score for s in r.scored}
        for extension in ("RAMRAJ PANT", "RAMRAJ SHIRT", "RAMRAJ DHOTI"):
            self.assertLess(by_value[extension], by_value["RAMRAJ"], extension)

    def test_09_ramraj_pant_dominates_when_the_user_says_pant(self):
        r = self.resolve("Show sales for Ramraj pant brand", "Ramraj pant",
                         "Brand", qualifier_explicit=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "RAMRAJ PANT")

    def test_09b_question_context_rescues_a_supported_extension(self):
        """
        Signal 9. Even when the extracted phrase is only "Ramraj", the word
        "pant" in the QUESTION is evidence for RAMRAJ PANT, so the extension
        is not penalised. This is the two-signal design: the phrase says what
        was named, the question says what is supported.
        """
        r = self.resolve("Show sales for Ramraj pant", "Ramraj")
        supported = {s.value: s for s in r.scored}["RAMRAJ PANT"]
        self.assertIn("question_supports_extension", supported.signals)
        self.assertGreater(
            supported.score,
            {s.value: s for s in r.scored}["RAMRAJ SHIRT"].score,
        )

    def test_23_bare_ramraj_preserves_family_ambiguity(self):
        """
        Judgement call, stated explicitly.

        "Show sales for Ramraj" matches RAMRAJ exactly, so scoring alone would
        resolve it. But RAMRAJ PANT / SHIRT / DHOTI are all configured and all
        begin with it, and nothing in the question says whether the user meant
        the RAMRAJ line or the RAMRAJ family. The missing information is in the
        user's head, not in the evidence, so the honest outcome is a
        clarification. Naming the dimension ("Ramraj brand") settles it, which
        is why the test above resolves and this one does not.
        """
        r = self.resolve("Show sales for Ramraj", "Ramraj")
        self.assertEqual(r.status, AMBIGUOUS)
        self.assertIn("RAMRAJ", r.values)
        self.assertIn("RAMRAJ PANT", r.values)

    def test_23b_specificity_alone_never_wins(self):
        """A longer value must not beat a shorter exact match by being longer."""
        r = self.resolve("Show sales for Ramraj brand", "Ramraj",
                         "Brand", qualifier_explicit=True)
        self.assertEqual(r.winner.value, "RAMRAJ")

    def test_21_metric_word_offered_as_a_value(self):
        """
        "pending" is the Pending Amount metric AND a real Payment Status value.
        The scorer must not blocklist it - it resolves on evidence like any
        other value, and it is Step 2's job to keep a metric phrase out of the
        value slot in the first place.
        """
        r = self.resolve("Show pending amount for Chennai", "pending")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.winner.value, "PENDING")
        self.assertEqual(r.winner.dimension, "Payment Status")


# ---------------------------------------------------------------------------
# 15: multiple phrases resolve independently
# ---------------------------------------------------------------------------
class TestMultipleValues(Base):

    def test_15_two_independent_values(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Chennai city and Ramraj brand",
            [
                _Phrase("Chennai", "City", qualifier_explicit=True),
                _Phrase("Ramraj", "Brand", qualifier_explicit=True),
            ],
            provider=self.provider,
        )
        self.assertEqual(len(resolutions), 2)
        self.assertEqual(resolutions[0].status, RESOLVED)
        self.assertEqual(resolutions[0].winner.value, "CHENNAI")
        self.assertEqual(resolutions[0].winner.dimension, "City")
        self.assertEqual(resolutions[1].status, RESOLVED)
        self.assertEqual(resolutions[1].winner.value, "RAMRAJ")
        self.assertEqual(resolutions[1].winner.dimension, "Brand")

    def test_15b_no_candidate_crosses_between_phrases(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Chennai city and Ramraj brand",
            [
                _Phrase("Chennai", "City", qualifier_explicit=True),
                _Phrase("Ramraj", "Brand", qualifier_explicit=True),
            ],
            provider=self.provider,
        )
        first = {s.value for s in resolutions[0].scored}
        second = {s.value for s in resolutions[1].scored}
        self.assertEqual(first & second, set())

    def test_15c_one_unresolved_phrase_does_not_affect_the_other(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Atlantis and Mumbai",
            [_Phrase("Atlantis"), _Phrase("Mumbai")],
            provider=self.provider,
        )
        self.assertEqual(resolutions[0].status, UNRESOLVED)
        self.assertEqual(resolutions[1].status, RESOLVED)
        self.assertEqual(resolutions[1].winner.value, "MUMBAI")


# ---------------------------------------------------------------------------
# 18, 19, 20, 27: malformed input and compatibility
# ---------------------------------------------------------------------------
class TestMalformedAndCompatibility(Base):

    def test_18_empty_phrase(self):
        r = resolve_phrase([], "", "Show sales")
        self.assertEqual(r.status, UNRESOLVED)

    def test_19_malformed_value_phrases_are_skipped(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Mumbai",
            [_Phrase(""), _Phrase(None), _Phrase("   "), _Phrase("Mumbai")],
            provider=self.provider,
        )
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0].winner.value, "MUMBAI")

    def test_19b_dict_form_is_accepted(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Chennai city",
            [{"phrase": "Chennai", "dimension": "City", "qualifier_explicit": True}],
            provider=self.provider,
        )
        self.assertEqual(resolutions[0].winner.dimension, "City")

    def test_20_low_confidence_phrase_still_resolves_on_evidence(self):
        """
        Extraction confidence is about the READING of the question, not about
        whether the value exists. A hesitantly-extracted phrase that matches a
        real value exactly is still a match; suppressing it here would hide a
        correct answer behind a number that means something else.
        """
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Mumbai",
            [_Phrase("Mumbai", confidence=0.05)],
            provider=self.provider,
        )
        self.assertEqual(resolutions[0].status, RESOLVED)

    def test_27_no_value_phrases_returns_nothing(self):
        for empty in ([], None):
            self.assertEqual(
                DimensionValueResolver.resolve_value_phrases(
                    None, "Show sales", empty, provider=self.provider),
                [],
            )


# ---------------------------------------------------------------------------
# 24, 25, 26: provenance and provider isolation
# ---------------------------------------------------------------------------
class TestProviderContract(Base):

    def test_25_every_candidate_carries_provenance(self):
        for phrase in ("Chennai", "Ramraj", "VT", "Coimbator"):
            for c in self.provider.get_candidates(None, phrase):
                self.assertEqual(c.provenance, PROVENANCE_MOCK)

    def test_25b_provenance_is_required(self):
        with self.assertRaises(ValueError):
            ValueCandidate(value="X", normalized_value="x",
                           dimension="City", provenance="")

    def test_25c_resolved_values_come_from_the_fixture_only(self):
        known = {v for values in FIXTURE_VALUES.values() for v in values}
        for phrase in ("Chennai", "Ramraj", "Coimbator", "VT", "Mumbai"):
            r = self.resolve("Show sales for %s" % phrase, phrase)
            for s in r.scored:
                self.assertIn(s.value, known)

    def test_25d_the_phrase_spelling_never_becomes_the_value(self):
        r = self.resolve("Show sales for coimbator city", "coimbator",
                         "City", qualifier_explicit=True)
        self.assertEqual(r.winner.value, "COIMBATORE")
        self.assertNotEqual(r.winner.value, "coimbator")

    def test_24_duplicate_normalized_candidates_collapse(self):
        dupes = [
            ValueCandidate("CHENNAI", "chennai", "City", PROVENANCE_MOCK),
            ValueCandidate("Chennai", "chennai", "City", PROVENANCE_MOCK),
            ValueCandidate("chennai ", "chennai", "City", PROVENANCE_MOCK),
        ]
        r = resolve_phrase(dupes, "Chennai", "Show sales for Chennai")
        self.assertEqual(len(r.scored), 1)
        self.assertEqual(r.status, RESOLVED)

    def test_26_provider_is_isolated_and_swappable(self):
        """The resolver must depend on the contract, not on the fixture."""
        class OneValueProvider(DimensionValueProvider):
            def dimensions(self):
                return ["City"]

            def get_candidates(self, dimension, phrase, context=None):
                return [ValueCandidate("ATLANTIS", "atlantis", "City",
                                       "mock/test/provider-generated-from-fixture")]

        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Atlantis", [_Phrase("Atlantis")],
            provider=OneValueProvider(),
        )
        self.assertEqual(resolutions[0].status, RESOLVED)
        self.assertEqual(resolutions[0].winner.value, "ATLANTIS")

    def test_26b_production_module_carries_no_fixture_data(self):
        """
        The invariant is that production code holds no VALUES, not that it
        never mentions a city in a comment. Asserted structurally: the
        production provider is empty until someone hands it data, and the
        fixture data lives under test/.
        """
        from semantic.value_provider import StaticDimensionValueProvider
        import semantic.value_provider as vp
        import fixtures.mock_value_provider as fixture

        empty = StaticDimensionValueProvider()
        self.assertEqual(empty.values_by_dimension, {})
        self.assertEqual(empty.dimensions(), [])
        for phrase in ("Chennai", "Ramraj", "Coimbatore"):
            self.assertEqual(empty.get_candidates(None, phrase), [])

        self.assertNotIn("FIXTURE_VALUES", dir(vp))
        self.assertIn("test", fixture.__file__.replace("\\", "/").split("/"))


# ---------------------------------------------------------------------------
# 28, 29: mode discipline
# ---------------------------------------------------------------------------
class TestModes(unittest.TestCase):

    def setUp(self):
        self.previous = os.environ.pop("SEMANTIC_VALUE_MODE", None)

    def tearDown(self):
        os.environ.pop("SEMANTIC_VALUE_MODE", None)
        if self.previous is not None:
            os.environ["SEMANTIC_VALUE_MODE"] = self.previous

    def test_28_default_is_legacy(self):
        self.assertFalse(DimensionValueResolver.phrase_scoped_enabled())
        self.assertFalse(DimensionValueResolver.candidate_scoped_enabled())

    def test_28b_explicit_legacy_is_legacy(self):
        os.environ["SEMANTIC_VALUE_MODE"] = "legacy"
        self.assertFalse(DimensionValueResolver.phrase_scoped_enabled())
        self.assertFalse(DimensionValueResolver.candidate_scoped_enabled())

    def test_29_candidate_scoped_implies_phrase_scoped(self):
        os.environ["SEMANTIC_VALUE_MODE"] = "candidate_scoped"
        self.assertTrue(DimensionValueResolver.phrase_scoped_enabled())
        self.assertTrue(DimensionValueResolver.candidate_scoped_enabled())

    def test_29b_enforce_is_not_candidate_scoped(self):
        os.environ["SEMANTIC_VALUE_MODE"] = "enforce"
        self.assertTrue(DimensionValueResolver.phrase_scoped_enabled())
        self.assertFalse(DimensionValueResolver.candidate_scoped_enabled())

    def test_29c_unknown_mode_is_off(self):
        os.environ["SEMANTIC_VALUE_MODE"] = "shadow"
        self.assertFalse(DimensionValueResolver.phrase_scoped_enabled())
        self.assertFalse(DimensionValueResolver.candidate_scoped_enabled())

    def test_29d_scoring_is_deterministic(self):
        provider = MockDimensionValueProvider()
        runs = set()
        for _ in range(5):
            r = resolve_phrase(
                provider.get_candidates("Brand", "Ramraj"),
                "Ramraj", "Show sales for Ramraj brand",
                qualifier_explicit=True, phrase_dimension="Brand",
            )
            runs.add((r.status, tuple((s.value, s.score) for s in r.scored)))
        self.assertEqual(len(runs), 1)


if __name__ == "__main__":
    unittest.main()
