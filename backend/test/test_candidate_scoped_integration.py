"""
Step 4 integration - scorer results flowing through the EXISTING resolution
engine rather than beside it.

These tests call resolve_matches(), not the scorer, so what they exercise is
the real path: provider -> scorer -> MatchResult adapter -> consolidation,
containment, competition, the ambiguity classifier and the resolution result.
If the adapter loses information or the downstream engine reacts badly to
scorer-shaped matches, it shows up here and not in the unit tests.

Offline: the value index is stubbed empty so no database is touched. That is
test scaffolding only - in candidate_scoped mode the index is not the candidate
source anyway, the provider is.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fixtures.mock_value_provider import MockDimensionValueProvider  # noqa: E402
from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402
from semantic.matching import MatchType  # noqa: E402
from semantic.value_provider import PROVENANCE_MOCK  # noqa: E402


class _Phrase:
    def __init__(self, phrase, dimension=None, qualifier_explicit=False):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit


class IntegrationBase(unittest.TestCase):
    """Drives resolve_matches with the value index stubbed out."""

    MODE = "candidate_scoped"

    def setUp(self):
        self._previous = os.environ.get("SEMANTIC_VALUE_MODE")
        if self.MODE is None:
            os.environ.pop("SEMANTIC_VALUE_MODE", None)
        else:
            os.environ["SEMANTIC_VALUE_MODE"] = self.MODE

        self.provider = MockDimensionValueProvider()
        self.resolver = DimensionValueResolver()
        # No database in this session; the provider is the candidate source.
        self.resolver._load_dimension_values = lambda connection_id: []
        # _members_of asks the DB whether a value is a family head. Off the
        # office network it cannot answer; () is its own documented value
        # for 'not a family', which is true of every fixture value.
        self._real_members_of = DimensionValueResolver._members_of
        DimensionValueResolver._members_of = staticmethod(lambda *a, **k: ())

    def tearDown(self):
        DimensionValueResolver._members_of = self._real_members_of
        os.environ.pop("SEMANTIC_VALUE_MODE", None)
        if self._previous is not None:
            os.environ["SEMANTIC_VALUE_MODE"] = self._previous

    def run_question(self, question, phrases):
        return self.resolver.resolve_matches(
            "conn-1",
            question,
            value_phrases=phrases,
            value_provider=self.provider,
        )

    @staticmethod
    def values(result):
        return sorted({m.get("value") for m in (result or []) if isinstance(m, dict)})

    @staticmethod
    def dimensions(result):
        return sorted({
            m.get("business_name") for m in (result or [])
            if isinstance(m, dict) and m.get("business_name")
        })


class TestRamrajThroughTheEngine(IntegrationBase):

    def test_01_ramraj_brand_resolves_to_the_exact_value(self):
        result = self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        self.assertEqual(self.values(result), ["RAMRAJ"])

    def test_02_ramraj_pant_brand_resolves_to_the_specific_value(self):
        result = self.run_question(
            "Show sales for Ramraj pant brand",
            [_Phrase("Ramraj pant", "Brand", qualifier_explicit=True)],
        )
        self.assertEqual(self.values(result), ["RAMRAJ PANT"])

    def test_03_bare_ramraj_keeps_the_family_competing(self):
        """
        AMBIGUOUS must survive the adapter. The engine's containment pass could
        legitimately have dropped RAMRAJ as 'contained in' RAMRAJ PANT; if it
        did, the user would silently lose the option they most likely meant.
        """
        result = self.run_question("Show sales for Ramraj", [_Phrase("Ramraj")])
        values = self.values(result)
        self.assertIn("RAMRAJ", values)
        self.assertGreater(len(values), 1, values)


class TestDimensionsThroughTheEngine(IntegrationBase):

    def test_04_chennai_city_resolves_against_city(self):
        result = self.run_question(
            "Show sales for Chennai city",
            [_Phrase("Chennai", "City", qualifier_explicit=True)],
        )
        self.assertEqual(self.values(result), ["CHENNAI"])
        self.assertEqual(self.dimensions(result), ["City"])

    def test_05_bare_chennai_keeps_cross_dimension_ambiguity(self):
        result = self.run_question("Show sales for Chennai", [_Phrase("Chennai")])
        self.assertEqual(self.dimensions(result), ["City", "District"])

    def test_08_explicit_dimension_excludes_the_other_dimension(self):
        result = self.run_question(
            "Show sales for VT brand",
            [_Phrase("VT", "Brand", qualifier_explicit=True)],
        )
        self.assertEqual(self.dimensions(result), ["Brand"])

    def test_09_cross_dimension_ambiguity_survives(self):
        result = self.run_question("Show sales for VT", [_Phrase("VT")])
        self.assertEqual(self.dimensions(result), ["Brand", "State"])


class TestIndependenceAndUnresolved(IntegrationBase):

    def test_06_two_phrases_resolve_independently(self):
        result = self.run_question(
            "Show sales for Chennai city and Ramraj brand",
            [
                _Phrase("Chennai", "City", qualifier_explicit=True),
                _Phrase("Ramraj", "Brand", qualifier_explicit=True),
            ],
        )
        self.assertEqual(self.values(result), ["CHENNAI", "RAMRAJ"])
        self.assertEqual(self.dimensions(result), ["Brand", "City"])

    def test_06b_no_candidate_bridges_the_two_phrases(self):
        """The precise-token contract, preserved through the adapter."""
        self.run_question(
            "Show sales for Chennai city and Ramraj brand",
            [
                _Phrase("Chennai", "City", qualifier_explicit=True),
                _Phrase("Ramraj", "Brand", qualifier_explicit=True),
            ],
        )
        resolutions = DimensionValueResolver.last_phrase_resolutions
        self.assertEqual(len(resolutions), 2)
        first = {s.value for s in resolutions[0].scored}
        second = {s.value for s in resolutions[1].scored}
        self.assertEqual(first & second, set())

    def test_07_nonexistent_value_resolves_to_nothing(self):
        result = self.run_question("Show sales for Atlantis", [_Phrase("Atlantis")])
        self.assertEqual(self.values(result), [])

    def test_07b_unresolved_phrase_does_not_block_a_resolved_one(self):
        result = self.run_question(
            "Show sales for Atlantis and Mumbai",
            [_Phrase("Atlantis"), _Phrase("Mumbai")],
        )
        self.assertEqual(self.values(result), ["MUMBAI"])


class TestModesAndProvenance(IntegrationBase):

    def test_12_candidate_scoped_mode_uses_the_scorer(self):
        self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        resolutions = DimensionValueResolver.last_phrase_resolutions
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0].status, "RESOLVED")
        self.assertEqual(resolutions[0].winner.value, "RAMRAJ")

    def test_13_provenance_survives_the_conversion(self):
        self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        resolutions = DimensionValueResolver.last_phrase_resolutions
        for scored in resolutions[0].scored:
            self.assertEqual(scored.candidate.provenance, PROVENANCE_MOCK)

    def test_13b_provenance_is_carried_on_the_match_reason(self):
        from semantic.candidate_scoring import to_match_results
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
            provider=self.provider,
        )
        matches = to_match_results(resolutions[0])
        self.assertEqual(len(matches), 1)
        self.assertIn(PROVENANCE_MOCK, matches[0].reason)
        self.assertEqual(matches[0].match_type, MatchType.EXACT)
        self.assertEqual(matches[0].business_name, "Brand")

    def test_13c_adapter_emits_nothing_for_unresolved(self):
        from semantic.candidate_scoring import to_match_results
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Atlantis", [_Phrase("Atlantis")],
            provider=self.provider,
        )
        self.assertEqual(to_match_results(resolutions[0]), [])

    def test_14_no_value_phrases_falls_back_safely(self):
        """With no phrases the legacy path runs; the stub index yields nothing."""
        for empty in ([], None):
            result = self.resolver.resolve_matches(
                "conn-1", "Show sales", value_phrases=empty,
                value_provider=self.provider,
            )
            self.assertEqual(self.values(result), [])


class TestLegacyModeUnchanged(IntegrationBase):
    """11. Default mode must ignore phrases entirely."""

    MODE = None   # unset -> legacy

    def test_11_legacy_ignores_value_phrases(self):
        self.assertFalse(DimensionValueResolver.candidate_scoped_enabled())
        self.assertFalse(DimensionValueResolver.phrase_scoped_enabled())
        result = self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        # Legacy path against the stubbed-empty index: no provider values leak.
        self.assertEqual(self.values(result), [])


class TestEnforceModeIsStillBarePhraseScoping(IntegrationBase):
    """The two modes stay distinct: enforce must NOT use the provider."""

    MODE = "enforce"

    def test_enforce_does_not_use_the_candidate_provider(self):
        result = self.run_question(
            "Show sales for Ramraj brand",
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)],
        )
        self.assertEqual(self.values(result), [])


if __name__ == "__main__":
    unittest.main()
