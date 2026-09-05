"""
Gate 4 Step 3 - phrase-scoped dimension value resolution.

These tests exercise the match-production change directly, with a stubbed value
index, so they need no database, no model and no network. The stub IS the point
of test I: every value these tests can possibly resolve was placed in the index
by this file, so a resolved value provably came from the configured value
source and not from anything the extractor said.

What is deliberately NOT tested here: ranking, containment, competition and
ambiguity classification. Step 3 does not touch them - it changes only WHAT the
matchers are asked to explain - and the existing G3 suites remain their tests.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402
from semantic.matching import (  # noqa: E402
    CachedDimensionValue,
    SingularPluralMatcher,
)


def _value(dim_id, business_name, value, table="SALES", column="COL"):
    """One indexed value, with the runtime tokens the matchers expect."""
    norm = DimensionValueResolver._normalize_text(value)
    tokens = norm.split()
    singulars = [SingularPluralMatcher._to_singular(t) for t in tokens]
    return CachedDimensionValue(
        semantic_dimension_id=dim_id,
        business_name=business_name,
        table_name=table,
        column_name=column,
        value=value,
        normalized_value=norm,
        runtime_stored_norm=norm,
        runtime_stored_tokens=tokens,
        runtime_stored_singulars=singulars,
        runtime_raw_norm=norm,
        runtime_raw_tokens=tokens,
        runtime_raw_singulars=singulars,
    )


# The only values that exist as far as these tests are concerned.
INDEX = [
    _value(1, "City", "CHENNAI"),
    _value(2, "District", "CHENNAI"),
    _value(1, "City", "COIMBATORE"),
    _value(1, "City", "ELECTRONIC CITY"),
    _value(3, "Brand", "RAMRAJ"),
    _value(3, "Brand", "RAMRAJ PANT"),
    _value(4, "Product Category", "SHIRTS"),
    _value(5, "State", "VT"),
    _value(6, "Region", "VT"),
]


class _Phrase:
    """Structural stand-in for ValuePhrase - the resolver reads it by shape."""

    def __init__(self, phrase, dimension=None, qualifier_explicit=False):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit


class PhraseScopedBase(unittest.TestCase):
    def setUp(self):
        self.resolver = DimensionValueResolver()

    def run_phrases(self, phrases):
        matches, stats = self.resolver._phrase_scoped_matches(phrases, "conn-1", INDEX)
        return matches, stats

    @staticmethod
    def values(matches):
        return sorted({m.value for m in matches})

    @staticmethod
    def dimensions(matches):
        return sorted({m.business_name for m in matches})


class TestExplicitQualifier(PhraseScopedBase):
    """A. and B. - the user named the dimension."""

    def test_chennai_city_resolves_against_city_only(self):
        matches, _ = self.run_phrases(
            [_Phrase("Chennai", "City", qualifier_explicit=True)]
        )
        self.assertIn("CHENNAI", self.values(matches))
        self.assertEqual(self.dimensions(matches), ["City"])
        self.assertNotIn("District", self.dimensions(matches))

    def test_ramraj_brand_resolves_against_brand(self):
        matches, _ = self.run_phrases(
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)]
        )
        self.assertIn("RAMRAJ", self.values(matches))
        self.assertEqual(self.dimensions(matches), ["Brand"])

    def test_unverified_qualifier_does_not_narrow(self):
        """
        Step 5: the model may propose a dimension, but only the deterministic
        qualifier_explicit computed in Step 2 unlocks narrowing.
        """
        matches, _ = self.run_phrases(
            [_Phrase("Chennai", "City", qualifier_explicit=False)]
        )
        self.assertEqual(self.dimensions(matches), ["City", "District"])

    def test_dimension_with_no_indexed_values_falls_back(self):
        matches, _ = self.run_phrases(
            [_Phrase("Chennai", "Warehouse", qualifier_explicit=True)]
        )
        self.assertIn("CHENNAI", self.values(matches))


class TestKnownWideningLimitation(PhraseScopedBase):
    """
    KNOWN LIMITATION, asserted so it cannot be forgotten.

    Phrase-scoping narrows WHICH words may be values, but it also removes the
    surrounding question words that used to keep fuzzy matching honest. The
    whole question "Show sales for Ramraj brand" never made RAMRAJ PANT a
    candidate, because "pant" is not in the question. The phrase "Ramraj" on
    its own matches every value that starts with it, so RAMRAJ PANT scores
    above the fuzzy cutoff and becomes a candidate too.

    Verified live: legacy resolves "Show sales for Ramraj brand" to 1 value,
    phrase-scoped to 13. This is why SEMANTIC_VALUE_MODE defaults to off, and
    it must be solved before the flag is turned on anywhere.
    """

    def test_prefix_siblings_widen_the_candidate_set(self):
        matches, _ = self.run_phrases(
            [_Phrase("Ramraj", "Brand", qualifier_explicit=True)]
        )
        values = self.values(matches)
        self.assertIn("RAMRAJ", values)
        # Documents today's behaviour, not the behaviour we want.
        self.assertIn("RAMRAJ PANT", values)


class TestBareValueAmbiguity(PhraseScopedBase):
    """D. and K. - genuine ambiguity must survive."""

    def test_bare_chennai_keeps_both_dimensions(self):
        matches, _ = self.run_phrases([_Phrase("Chennai")])
        self.assertEqual(self.dimensions(matches), ["City", "District"])

    def test_bare_vt_keeps_both_dimensions(self):
        matches, _ = self.run_phrases([_Phrase("VT")])
        self.assertEqual(self.dimensions(matches), ["Region", "State"])

    def test_coimbator_misspelling_still_matches_fuzzily(self):
        matches, _ = self.run_phrases([_Phrase("Coimbator")])
        self.assertIn("COIMBATORE", self.values(matches))


class TestIndependentPhrases(PhraseScopedBase):
    """C. and G. - one phrase must not contaminate another."""

    def test_two_phrases_resolve_independently(self):
        matches, _ = self.run_phrases([
            _Phrase("Chennai", "City", qualifier_explicit=True),
            _Phrase("Ramraj", "Brand", qualifier_explicit=True),
        ])
        self.assertEqual(self.dimensions(matches), ["Brand", "City"])
        self.assertIn("CHENNAI", self.values(matches))
        self.assertIn("RAMRAJ", self.values(matches))

    def test_no_candidate_spans_the_two_phrases(self):
        """
        The false-merge guard. Every candidate's matched question tokens must
        come from ONE phrase; a candidate crediting tokens of both is what
        bridged City and Brand into a single false ambiguity before.
        """
        matches, _ = self.run_phrases([
            _Phrase("Chennai", "City", qualifier_explicit=True),
            _Phrase("Ramraj", "Brand", qualifier_explicit=True),
        ])
        for m in matches:
            tokens = set(m.matched_question_tokens or [])
            self.assertFalse(
                {"chennai"} <= tokens and {"ramraj"} <= tokens,
                "candidate %r spans both phrases" % (m.value,),
            )

    def test_unrelated_phrases_each_resolve(self):
        matches, _ = self.run_phrases([_Phrase("Coimbatore"), _Phrase("Shirts")])
        self.assertIn("COIMBATORE", self.values(matches))
        self.assertIn("SHIRTS", self.values(matches))


class TestUnresolvedAndProvenance(PhraseScopedBase):
    """H. and I."""

    def test_value_absent_from_index_stays_unresolved(self):
        matches, stats = self.run_phrases([_Phrase("Mumbai")])
        self.assertEqual(matches, [])
        self.assertIsNotNone(stats)   # the phrase ran; it simply matched nothing

    def test_every_resolved_value_comes_from_the_index(self):
        indexed = {v.value for v in INDEX}
        matches, _ = self.run_phrases([
            _Phrase("Chennai"), _Phrase("Ramraj"), _Phrase("Coimbator"),
        ])
        self.assertTrue(matches)
        for m in matches:
            self.assertIn(m.value, indexed)

    def test_llm_supplied_spelling_never_becomes_the_value(self):
        matches, _ = self.run_phrases([_Phrase("coimbator")])
        self.assertNotIn("coimbator", self.values(matches))
        self.assertIn("COIMBATORE", self.values(matches))


class TestMalformedAndEmpty(PhraseScopedBase):
    """F., J. and requirement 8."""

    def test_no_phrases_produces_no_stats(self):
        """stats None is the signal resolve_matches uses to keep the old path."""
        matches, stats = self.run_phrases([])
        self.assertEqual(matches, [])
        self.assertIsNone(stats)

    def test_all_malformed_phrases_produce_no_stats(self):
        matches, stats = self.run_phrases([
            _Phrase(""), _Phrase("   "), _Phrase(None), _Phrase("the"),
        ])
        self.assertEqual(matches, [])
        self.assertIsNone(stats)

    def test_dict_form_is_accepted(self):
        matches, _ = self.run_phrases([
            {"phrase": "Chennai", "dimension": "City", "qualifier_explicit": True}
        ])
        self.assertEqual(self.dimensions(matches), ["City"])

    def test_malformed_phrase_does_not_stop_the_others(self):
        matches, stats = self.run_phrases([_Phrase(""), _Phrase("Chennai")])
        self.assertIsNotNone(stats)
        self.assertIn("CHENNAI", self.values(matches))


class TestRolloutFlag(unittest.TestCase):
    """The path is off unless deliberately enabled."""

    def setUp(self):
        self.previous = os.environ.pop("SEMANTIC_VALUE_MODE", None)

    def tearDown(self):
        os.environ.pop("SEMANTIC_VALUE_MODE", None)
        if self.previous is not None:
            os.environ["SEMANTIC_VALUE_MODE"] = self.previous

    def test_default_is_off(self):
        self.assertFalse(DimensionValueResolver.phrase_scoped_enabled())

    def test_enforce_turns_it_on(self):
        os.environ["SEMANTIC_VALUE_MODE"] = "enforce"
        self.assertTrue(DimensionValueResolver.phrase_scoped_enabled())

    def test_unknown_value_is_off(self):
        os.environ["SEMANTIC_VALUE_MODE"] = "shadow"
        self.assertFalse(DimensionValueResolver.phrase_scoped_enabled())

    def test_resolve_phrases_entry_point_exists(self):
        self.assertTrue(callable(DimensionValueResolver.resolve_phrases))


if __name__ == "__main__":
    unittest.main()
