"""
Deterministic qualifier handling for value phrases.

The defect this covers was found on real data, not in a fixture. The extractor
is inconsistent about the user's dimension word: "Show sales for Chennai city"
came back with phrase "Chennai city", while "Show sales for Ramraj brand" came
back with phrase "Ramraj". And "Show sales for Ramraj brands" set
qualifier_explicit False purely because the plural did not match the configured
singular - which removed the dimension narrowing and produced a 13-way brand
tie on real values.

So the qualifier is decided here, deterministically, from the question and the
configured dimension names, in whatever number the user typed. The model's own
qualifier_explicit flag is never read.

No database, no model, no network.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from ai.extraction.slot_extractor import _validate_value_phrases  # noqa: E402

# Configured names only - nothing company-specific is hardcoded in the code
# under test, which reads whatever vocabulary it is handed.
DIMENSIONS = ["City", "District", "Brand", "Category", "Product Category", "State"]


def validate(raw, question, metric_terms=None):
    notes = []
    kept = _validate_value_phrases(
        raw, question, metric_terms or [], DIMENSIONS, notes)
    return kept, notes


def one(phrase, question, dimension=None, metric_terms=None):
    kept, notes = validate(
        [{"phrase": phrase, "dimension": dimension, "confidence": 0.9}],
        question, metric_terms)
    return (kept[0] if kept else None), notes


class TestQualifierInsideThePhrase(unittest.TestCase):
    """The real-data defect: the model swallowed the qualifier."""

    def test_chennai_city(self):
        p, _ = one("Chennai city", "Show sales for Chennai city", "City")
        self.assertEqual(p.phrase, "chennai")
        self.assertEqual(p.dimension, "City")
        self.assertTrue(p.qualifier_explicit)

    def test_chennai_cities_plural(self):
        p, _ = one("Chennai cities", "Show sales for Chennai cities", "City")
        self.assertEqual(p.phrase, "chennai")
        self.assertEqual(p.dimension, "City")
        self.assertTrue(p.qualifier_explicit)

    def test_chennai_district(self):
        p, _ = one("Chennai district", "Show sales for Chennai district", "District")
        self.assertEqual(p.phrase, "chennai")
        self.assertEqual(p.dimension, "District")
        self.assertTrue(p.qualifier_explicit)

    def test_multi_word_dimension_is_preferred(self):
        """'Product Category' must win over 'Category', which is its tail."""
        p, _ = one("Ethnic product category",
                   "Show sales for Ethnic product category")
        self.assertEqual(p.phrase, "ethnic")
        self.assertEqual(p.dimension, "Product Category")
        self.assertTrue(p.qualifier_explicit)

    def test_a_note_records_the_change(self):
        _, notes = one("Chennai city", "Show sales for Chennai city", "City")
        self.assertTrue(any("carried the qualifier" in n for n in notes))

    def test_phrase_that_is_only_a_dimension_is_not_stripped(self):
        """Stripping everything would leave no value at all."""
        p, _ = one("city", "Show sales by city")
        self.assertIsNotNone(p)
        self.assertEqual(p.phrase, "city")
        self.assertIsNone(p.dimension)


class TestQualifierOutsideThePhrase(unittest.TestCase):
    """The model split them; the flag must still be set, in any number."""

    def test_ramraj_brand(self):
        p, _ = one("Ramraj", "Show sales for Ramraj brand", "Brand")
        self.assertEqual(p.phrase, "Ramraj")
        self.assertEqual(p.dimension, "Brand")
        self.assertTrue(p.qualifier_explicit)

    def test_ramraj_brands_plural(self):
        """The exact real-data regression: plural defeated the check."""
        p, _ = one("Ramraj", "Show sales for Ramraj brands", "Brand")
        self.assertEqual(p.dimension, "Brand")
        self.assertTrue(p.qualifier_explicit)

    def test_cities_plural_outside(self):
        p, _ = one("Chennai", "Compare sales across cities like Chennai", "City")
        self.assertTrue(p.qualifier_explicit)


class TestBareValuesStayBare(unittest.TestCase):

    def test_bare_chennai(self):
        p, _ = one("Chennai", "Show sales for Chennai", "City")
        self.assertEqual(p.phrase, "Chennai")
        self.assertIsNone(p.dimension)
        self.assertFalse(p.qualifier_explicit)

    def test_bare_ramraj(self):
        p, _ = one("Ramraj", "Show sales for Ramraj")
        self.assertEqual(p.phrase, "Ramraj")
        self.assertIsNone(p.dimension)
        self.assertFalse(p.qualifier_explicit)

    def test_model_flag_is_never_trusted(self):
        """A model claiming the qualifier cannot create one."""
        kept, _ = validate(
            [{"phrase": "Chennai", "dimension": "City",
              "qualifier_explicit": True, "confidence": 0.99}],
            "Show sales for Chennai")
        self.assertFalse(kept[0].qualifier_explicit)
        self.assertIsNone(kept[0].dimension)


class TestMultipleAndMalformed(unittest.TestCase):

    def test_two_qualified_phrases_stay_independent(self):
        kept, _ = validate(
            [{"phrase": "Chennai city", "dimension": "City"},
             {"phrase": "Ramraj brand", "dimension": "Brand"}],
            "Show sales for Chennai city and Ramraj brand")
        self.assertEqual(
            [(p.phrase, p.dimension, p.qualifier_explicit) for p in kept],
            [("chennai", "City", True), ("ramraj", "Brand", True)])

    def test_mixed_qualified_and_bare(self):
        kept, _ = validate(
            [{"phrase": "Chennai city", "dimension": "City"},
             {"phrase": "Ramraj"}],
            "Show sales for Chennai city and Ramraj")
        self.assertEqual(
            [(p.phrase, p.dimension, p.qualifier_explicit) for p in kept],
            [("chennai", "City", True), ("Ramraj", None, False)])

    def test_unconfigured_dimension_is_still_refused(self):
        p, notes = one("Chennai", "Show sales for Chennai warehouse", "Warehouse")
        self.assertEqual(p.phrase, "Chennai")
        self.assertIsNone(p.dimension)
        self.assertTrue(any("Warehouse" in n for n in notes))

    def test_missing_dimension_field(self):
        p, _ = one("Chennai city", "Show sales for Chennai city", None)
        self.assertEqual(p.phrase, "chennai")
        self.assertEqual(p.dimension, "City")
        self.assertTrue(p.qualifier_explicit)

    def test_no_dimension_names_configured(self):
        notes = []
        kept = _validate_value_phrases(
            [{"phrase": "Chennai city"}], "Show sales for Chennai city",
            [], [], notes)
        self.assertEqual(kept[0].phrase, "Chennai city")
        self.assertIsNone(kept[0].dimension)

    def test_metric_overlap_still_refused_after_stripping(self):
        """Stripping must not smuggle a metric word through as a value."""
        kept, notes = validate(
            [{"phrase": "pending city", "dimension": "City"}],
            "Show pending city", metric_terms=["Pending"])
        self.assertEqual(kept, [])
        self.assertTrue(any("names a metric" in n for n in notes))

    def test_duplicates_collapse_after_stripping(self):
        kept, _ = validate(
            [{"phrase": "Chennai city", "dimension": "City"},
             {"phrase": "Chennai", "dimension": "City"}],
            "Show sales for Chennai city")
        self.assertEqual(len(kept), 1)

    def test_no_value_question_yields_nothing(self):
        kept, _ = validate([], "Which product categories are seeing reducing sales?")
        self.assertEqual(kept, [])

    def test_phrase_absent_from_question_still_dropped(self):
        p, notes = one("Bangalore city", "Show sales for Chennai city", "City")
        self.assertIsNone(p)
        self.assertTrue(any("not present in the question" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
