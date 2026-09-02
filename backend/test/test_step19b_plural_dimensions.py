"""
Gate 3 Step 19b - RC-04 plural dimension handling.

Two bugs, both required:

A. semantic_resolver._get_match_info, Priority 7 (Stem Overlap) reported
   [(0, len(q_norm))] - the WHOLE question - as its matched span. A plural
   dimension name only ever reaches that path ("cities" matches no literal,
   whole-word or synonym rule), so the candidate arrived at _remove_overlaps
   claiming the entire question, collided with the metric's "sales" span and
   was discarded. Every plural-qualified question therefore resolved
   dimensions=[] while its singular form resolved correctly.

B. dimension_value_resolver._find_matching_dimension compared raw strings,
   so the qualifier word "cities" did not identify the City dimension even
   once A made it available - leaving District in contention.

The stems themselves were always correct: _stem_word already maps
cities->city, and SingularPluralMatcher._to_singular already maps every form
in these tests. Neither fix adds a new pluralisation algorithm.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.semantic_resolver import _get_match_info


def _db_reachable():
    try:
        import core.config  # noqa
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


class TestStemOverlapSpan(unittest.TestCase):
    """A. The span contract, in isolation - no database."""

    SYNONYMS = "Town, Municipality, Location"

    def test_plural_reports_its_own_token_span_not_the_question(self):
        question = "Show sales for Chennai cities"
        score, length, spans, matched_by, name = _get_match_info(
            "city", "City", self.SYNONYMS, question
        )
        self.assertEqual(matched_by, "Stem Overlap")
        self.assertEqual(spans, [(23, 29)])
        self.assertEqual(question.lower()[23:29], "cities")

    def test_plural_span_does_not_claim_whole_question(self):
        question = "Show sales for Chennai cities"
        _, _, spans, _, _ = _get_match_info("city", "City", self.SYNONYMS, question)
        self.assertNotIn((0, len(question)), spans)
        for start, end in spans:
            self.assertGreater(start, 0)

    def test_singular_behaviour_unchanged(self):
        # Priority 3 still wins for the singular; nothing about that path moved.
        score, length, spans, matched_by, _ = _get_match_info(
            "city", "City", self.SYNONYMS, "Show sales for Chennai city"
        )
        self.assertEqual(matched_by, "Business Name")
        self.assertEqual(spans, [(23, 27)])
        self.assertEqual(score, 30000)

    def test_score_and_length_unchanged_for_stem_overlap(self):
        # Only the span changed - the tier/score contract is untouched.
        score, length, _, matched_by, _ = _get_match_info(
            "city", "City", self.SYNONYMS, "Show sales for Chennai cities"
        )
        self.assertEqual(matched_by, "Stem Overlap")
        self.assertEqual(score, 8000)
        self.assertEqual(length, 2)


class TestPluralQualifierLookup(unittest.TestCase):
    """B. The qualifier lookup, in isolation - no database."""

    CONTEXT = [
        {"dimension_name": "city", "business_name": "City",
         "table_name": "T", "column_name": "City"},
        {"dimension_name": "district", "business_name": "District",
         "table_name": "T", "column_name": "District"},
        {"dimension_name": "division", "business_name": "Division",
         "table_name": "T", "column_name": "Division"},
    ]

    def _lookup(self, word):
        from semantic.dimension_value_resolver import DimensionValueResolver
        return DimensionValueResolver._find_matching_dimension(word, self.CONTEXT)

    def test_singular_forms_unchanged(self):
        self.assertEqual(self._lookup("city"), "City")
        self.assertEqual(self._lookup("district"), "District")
        self.assertEqual(self._lookup("division"), "Division")

    def test_plural_forms_now_resolve(self):
        self.assertEqual(self._lookup("cities"), "City")
        self.assertEqual(self._lookup("districts"), "District")
        self.assertEqual(self._lookup("divisions"), "Division")

    def test_unrelated_word_still_returns_nothing(self):
        self.assertIsNone(self._lookup("sprocket"))


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestPluralDimensionsLive(unittest.TestCase):
    """C-L. The ten RC-04 cases end to end, against the real connection."""

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        from semantic.dimension_value_resolver import DimensionValueResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.DimensionValueResolver = DimensionValueResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _resolve(self, question):
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        rr = self.DimensionValueResolver.last_resolution_result
        dims = [d.get("business_name") for d in (res.get("dimension_objects") or [])]
        values = res.get("value_matches") or []
        return dims, rr, values

    def test_e1_126_vt_divisions(self):
        # C. Dimension and ambiguity must be right; the value count stays
        # wrong because that is the RC-07 cross-table issue, not RC-04.
        dims, rr, _ = self._resolve("Show sales for VT divisions")
        self.assertIn("Division", dims)
        self.assertEqual(rr.status.value, "WEAK_AMBIGUITY")

    def test_city_plural_cases(self):
        # D, E, F, J, K, L
        cases = {
            "Show sales for Chennai cities": "CHENNAI",
            "Show sales for Coimbatore cities": "COIMBATORE",
            "Show sales for Madurai cities": "MADURAI",
            "Show quantity for Erode cities": "ERODE",
            "Show quantity for Salem cities": "SALEM",
            "Show quantity for Tirunelveli cities": "TIRUNELVELI",
        }
        for question, expected_value in cases.items():
            dims, rr, values = self._resolve(question)
            self.assertIn("City", dims, msg=question)
            self.assertEqual({v["value"] for v in values}, {expected_value}, msg=question)
            self.assertEqual({v["column_name"] for v in values}, {"City"}, msg=question)

    def test_district_plural_cases(self):
        # G, H, I - the plural qualifier must select District, not City.
        cases = {
            "Show sales for Chennai districts": "CHENNAI",
            "Show sales for Coimbatore districts": "COIMBATORE",
            "Show sales for Madurai districts": "MADURAI",
        }
        for question, expected_value in cases.items():
            dims, rr, values = self._resolve(question)
            self.assertIn("District", dims, msg=question)
            self.assertEqual({v["column_name"] for v in values}, {"District"}, msg=question)
            self.assertEqual({v["value"] for v in values}, {expected_value}, msg=question)


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestStep19bDoesNotDisturbEarlierFixes(unittest.TestCase):
    """Explicit guards for the behaviours 19b must not change."""

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        from semantic.dimension_value_resolver import DimensionValueResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.DimensionValueResolver = DimensionValueResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _resolve(self, question):
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        return res, self.DimensionValueResolver.last_resolution_result

    def test_singular_city_qualifier_unchanged(self):
        res, rr = self._resolve("Show sales for Chennai city")
        columns = {v["column_name"] for v in (res.get("value_matches") or [])}
        self.assertEqual(columns, {"City"})
        self.assertEqual(rr.status.value, "WEAK_AMBIGUITY")

    def test_17a_fuzzy_qualifier_unchanged(self):
        res, _ = self._resolve("Show sales for coimbator city")
        columns = {v["column_name"] for v in (res.get("value_matches") or [])}
        self.assertEqual(columns, {"City"}, "District must still be filtered out")

    def test_vt_division_rc07_unchanged(self):
        res, rr = self._resolve("Show sales for VT division")
        columns = {v["column_name"] for v in (res.get("value_matches") or [])}
        self.assertEqual(columns, {"Division"})
        self.assertEqual(rr.status.value, "WEAK_AMBIGUITY")


if __name__ == "__main__":
    unittest.main()
