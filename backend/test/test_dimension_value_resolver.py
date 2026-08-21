
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from unittest.mock import MagicMock, patch
from semantic.matching import MatchResult
from semantic.matching.singular_plural_matcher import SingularPluralMatcher
from semantic.matching.models import MatchType
from semantic.dimension_value_resolver import DimensionValueResolver, ResolvedDimensionValue


class TestDimensionValueResolver(unittest.TestCase):
    def setUp(self):
        DimensionValueResolver.clear_cache()

    @patch("semantic.dimension_value_resolver.engine")
    def test_exact_match_success(self, mock_engine):
        # Arrange
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        # Mock database rows for load_dimension_values
        mock_row = MagicMock()
        mock_row._mapping = {
            "semantic_dimension_id": 42,
            "business_name": "Category",
            "table_name": "Products",
            "column_name": "CategoryName",
            "value": "Banians",
            "normalized_value": "banians"
        }
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        # Act
        # Case 1: Exact match query
        results = DimensionValueResolver.resolve(
            connection_id="test-conn",
            question="Show Banians sales"
        )

        # Assert
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Banians")
        self.assertEqual(results[0]["business_name"], "Category")
        self.assertEqual(results[0]["column_name"], "CategoryName")
        self.assertEqual(results[0]["match_type"], MatchType.EXACT.value)

    def test_match_type_and_resolved_dataclass_exist(self):
        # Verify enum and dataclass can be instantiated/referenced
        self.assertEqual(MatchType.EXACT.value, "EXACT")
        res = ResolvedDimensionValue(
            original_value="Banian",
            resolved_value="Banians",
            confidence=0.9,
            match_type=MatchType.EXACT,
            column_name="CategoryName"
        )
        self.assertEqual(res.original_value, "Banian")

    @patch("semantic.dimension_value_resolver.engine")
    def test_normalized_matching_variations(self, mock_engine):
        # Arrange
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        mock_rows = [
            MagicMock(
                _mapping={
                    "semantic_dimension_id": 1,
                    "business_name": "Product Category",
                    "table_name": "Products",
                    "column_name": "CategoryName",
                    "value": "T-Shirt",
                    "normalized_value": "t-shirt",
                }
            ),
            MagicMock(
                _mapping={
                    "semantic_dimension_id": 2,
                    "business_name": "Product Category",
                    "table_name": "Products",
                    "column_name": "CategoryName",
                    "value": "Men's Wear",
                    "normalized_value": "men's wear",
                }
            ),
            MagicMock(
                _mapping={
                    "semantic_dimension_id": 3,
                    "business_name": "Brand",
                    "table_name": "Brands",
                    "column_name": "BrandName",
                    "value": "Ram-Raj",
                    "normalized_value": "ram-raj",
                }
            ),
            MagicMock(
                _mapping={
                    "semantic_dimension_id": 4,
                    "business_name": "Product Category",
                    "table_name": "Products",
                    "column_name": "CategoryName",
                    "value": "Cotton/Shirt",
                    "normalized_value": "outdated_value",
                }
            ),
        ]

        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        test_cases = [
            ("Show t shirt sales", "T-Shirt", MatchType.EXACT.value),
            ("mens wear", "Men's Wear", MatchType.EXACT.value),
            ("ram raj", "Ram-Raj", MatchType.EXACT.value),
            ("cotton shirt", "Cotton/Shirt", MatchType.NORMALIZED.value),
        ]

        for question, expected_value, expected_match in test_cases:
            results = DimensionValueResolver.resolve(
                connection_id="test-conn",
                question=question,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["value"], expected_value)
            self.assertEqual(results[0]["match_type"], expected_match)

    @patch("semantic.dimension_value_resolver.engine")
    def test_singular_plural_matching(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        # Setup mock database rows representing the target values
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Banians", "normalized_value": "banians"}),
            MagicMock(_mapping={"semantic_dimension_id": 2, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts", "normalized_value": "shirts"}),
            MagicMock(_mapping={"semantic_dimension_id": 3, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Pants", "normalized_value": "pants"}),
            MagicMock(_mapping={"semantic_dimension_id": 4, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Kids", "normalized_value": "kids"}),
            MagicMock(_mapping={"semantic_dimension_id": 5, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Men's Wear", "normalized_value": "men's wear"}),
            MagicMock(_mapping={"semantic_dimension_id": 6, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Women's Wear", "normalized_value": "women's wear"}),
            MagicMock(_mapping={"semantic_dimension_id": 7, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Formal Shirts", "normalized_value": "formal shirts"}),
            MagicMock(_mapping={"semantic_dimension_id": 8, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Cotton Pants", "normalized_value": "cotton pants"}),
            MagicMock(_mapping={"semantic_dimension_id": 9, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Children Wear", "normalized_value": "children wear"}),
            MagicMock(_mapping={"semantic_dimension_id": 10, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "People Choice", "normalized_value": "people choice"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Positive cases
        test_cases = [
            ("Banian", "Banians"),
            ("Shirt", "Shirts"),
            ("Pant", "Pants"),
            ("Kid", "Kids"),
            ("Men Wear", "Men's Wear"),
            ("Woman Wear", "Women's Wear"),
            ("Formal Shirt", "Formal Shirts"),
            ("Cotton Pant", "Cotton Pants"),
            ("Child Wear", "Children Wear"),
            ("Person Choice", "People Choice"),
        ]

        for question, expected_value in test_cases:
            results = DimensionValueResolver.resolve(
                connection_id="test-conn",
                question=question
            )
            matched_values = [r["value"] for r in results]
            self.assertIn(expected_value, matched_values, f"Failed positive match for: {question}")

        # Negative cases
        negative_cases = [
            ("Laptop", "Pants"),
            ("Women", "Men's Wear"),
            ("Kid", "Cotton Pants"),
        ]
        
        for question, target_val in negative_cases:
            results = DimensionValueResolver.resolve(
                connection_id="test-conn",
                question=question
            )
            matched_values = [r["value"] for r in results]
            self.assertNotIn(target_val, matched_values, f"Failed negative match for: {question} matching {target_val}")

    def test_protected_words_handling(self):
        from semantic.singular_plural_matcher import SingularPluralMatcher
        self.assertEqual(SingularPluralMatcher._to_singular("business"), "business")
        self.assertEqual(SingularPluralMatcher._to_singular("analysis"), "analysis")
        self.assertEqual(SingularPluralMatcher._to_singular("glass"), "glass")
        # Regular plurals/irregulars should still be reduced
        self.assertEqual(SingularPluralMatcher._to_singular("children"), "child")
        self.assertEqual(SingularPluralMatcher._to_singular("women"), "woman")

    def test_typed_match_result(self):
        from semantic.singular_plural_matcher import SingularPluralMatcher
        from semantic.matching.models import MatchResult, MatchType
        res = SingularPluralMatcher.matches("formal shirts", "formal shirt")
        self.assertTrue(isinstance(res, MatchResult))
        self.assertTrue(res.matched)
        self.assertEqual(res.confidence, 0.95)
        self.assertEqual(res.match_type, MatchType.SINGULAR_PLURAL)
        self.assertIn("formal", res.matched_question_tokens)

    @patch("semantic.dimension_value_resolver.engine")
    def test_stopword_filtering(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Formal Shirts", "normalized_value": "formal shirts"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows
        
        # 'show me', 'sales' are stopwords, so it should match 'Formal Shirts' via singular/plural matching
        results = DimensionValueResolver.resolve(
            connection_id="test-conn",
            question="show me formal shirt sales"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Formal Shirts")

    def test_candidate_ranking_direct(self):
        from semantic.matching.models import MatchResult, MatchType
        # We can construct two mock MatchResult objects and run _rank_matches on them
        match1 = MatchResult(
            matched=True,
            value="Shirt",
            normalized_value="shirt",
            match_type=MatchType.EXACT,
            confidence=1.0,
            matched_question_tokens=["formal", "shirt"],
            matched_value_tokens=["shirt"],
            reason="Exact"
        )
        match2 = MatchResult(
            matched=True,
            value="Formal Shirt",
            normalized_value="formal shirt",
            match_type=MatchType.EXACT,
            confidence=1.0,
            matched_question_tokens=["formal", "shirt"],
            matched_value_tokens=["formal", "shirt"],
            reason="Exact"
        )
        
        # Question is "formal shirt" -> token list has length 2
        q_tokens = ["formal", "shirt"]
        
        # Rank them
        ranked = DimensionValueResolver._rank_matches([match1, match2], q_tokens)
        
        # "Formal Shirt" has token count 2, diff with q_tokens (len 2) is 0
        # "Shirt" has token count 1, diff with q_tokens (len 2) is 1
        # Therefore "Formal Shirt" must be first
        self.assertEqual(ranked[0].value, "Formal Shirt")
        self.assertEqual(ranked[1].value, "Shirt")

    @patch("semantic.dimension_value_resolver.engine")
    def test_preprocessed_cache_usage(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts", "normalized_value": "shirts"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Call resolve
        res1 = DimensionValueResolver.resolve("test-conn", "Shirts")
        self.assertEqual(len(res1), 1)
        self.assertEqual(mock_conn.execute.call_count, 1)

        # Call resolve again. Since it is cached, it should NOT query the DB again.
        res2 = DimensionValueResolver.resolve("test-conn", "Shirts")
        self.assertEqual(len(res2), 1)
        self.assertEqual(mock_conn.execute.call_count, 1)  # call_count remains 1

        # Clear cache and resolve again. It should query the DB.
        DimensionValueResolver.clear_cache("test-conn")
        res3 = DimensionValueResolver.resolve("test-conn", "Shirts")
        self.assertEqual(len(res3), 1)
        self.assertEqual(mock_conn.execute.call_count, 2)

    @patch("semantic.dimension_value_resolver.engine")
    def test_match_statistics(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Banians", "normalized_value": "banians"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        res = DimensionValueResolver.resolve("test-conn", "Show Banians sales")
        self.assertEqual(len(res), 1)
        
        # Verify stats
        stats = DimensionValueResolver.last_match_stats
        self.assertIsNotNone(stats)
        self.assertTrue(stats.exact_attempted)
        self.assertIsNone(stats.winning_match)
        self.assertTrue(stats.exact_attempted)
        self.assertTrue(stats.normalized_attempted)
        self.assertTrue(stats.plural_attempted)
        self.assertTrue(stats.fuzzy_attempted)
        self.assertGreaterEqual(stats.execution_time_ms, 0.0)

    def test_candidate_ranking_with_coverage(self):
        from semantic.matching.models import MatchResult, MatchType
        # Question: "Formal White Shirt"
        q_tokens = ["formal", "white", "shirt"]

        # Candidate A: "White Shirt" (Coverage: 2/3 = 66.7%)
        match_a = MatchResult(
            matched=True,
            value="White Shirt",
            normalized_value="white shirt",
            match_type=MatchType.EXACT,
            confidence=1.0,
            matched_question_tokens=q_tokens,
            matched_value_tokens=["white", "shirt"],
            reason="Exact"
        )
        # Candidate B: "Formal White Shirt" (Coverage: 3/3 = 100%)
        match_b = MatchResult(
            matched=True,
            value="Formal White Shirt",
            normalized_value="formal white shirt",
            match_type=MatchType.EXACT,
            confidence=1.0,
            matched_question_tokens=q_tokens,
            matched_value_tokens=["formal", "white", "shirt"],
            reason="Exact"
        )

        ranked = DimensionValueResolver._rank_matches([match_a, match_b], q_tokens)
        self.assertEqual(ranked[0].value, "Formal White Shirt")
        self.assertEqual(ranked[1].value, "White Shirt")

    @patch("semantic.dimension_value_resolver.engine")
    def test_dependency_injection_pipeline(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Banians", "normalized_value": "banians"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Create a custom pipeline containing only ExactMatcher (excluding plural)
        from semantic.matching import MatchingPipeline, ExactMatcher
        custom_pipeline = MatchingPipeline(matchers=[ExactMatcher()])
        
        resolver = DimensionValueResolver(pipeline=custom_pipeline)
        
        # Test plural query: "banian" should fail to match "Banians" because PluralMatcher is excluded from custom pipeline
        res = resolver.resolve_matches("test-conn", "banian")
        self.assertEqual(len(res), 0)

        # Test exact query: "Banians" should still match
        res_exact = resolver.resolve_matches("test-conn", "Banians")
        self.assertEqual(len(res_exact), 1)
        self.assertEqual(res_exact[0]["value"], "Banians")

    @patch("semantic.dimension_value_resolver.engine")
    def test_cache_invalidation_versioning(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows_1 = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts", "normalized_value": "shirts"}),
        ]
        mock_rows_2 = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts Updated", "normalized_value": "shirts updated"}),
        ]
        
        # Setup sequence of DB query results
        mock_conn.execute.return_value.fetchall.side_effect = [mock_rows_1, mock_rows_2]

        resolver = DimensionValueResolver()
        
        # First call loads mock_rows_1
        res1 = resolver.resolve_matches("test-conn", "Shirts")
        self.assertEqual(res1[0]["value"], "Shirts")

        # Second call uses cache, so still returns "Shirts"
        res2 = resolver.resolve_matches("test-conn", "Shirts")
        self.assertEqual(res2[0]["value"], "Shirts")

        # Invalidate connection cache (bumps cache version)
        DimensionValueResolver.clear_cache("test-conn")

        # Third call should trigger DB reload (mock_rows_2)
        res3 = resolver.resolve_matches("test-conn", "Shirts Updated")
        self.assertEqual(res3[0]["value"], "Shirts Updated")

    @patch("semantic.dimension_value_resolver.engine")
    def test_cache_injection(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts", "normalized_value": "shirts"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        from semantic.cache import DimensionValueCache
        custom_cache = DimensionValueCache()
        resolver = DimensionValueResolver(cache=custom_cache)

        # Execute query. Values should populate custom_cache.
        res = resolver.resolve_matches("test-conn", "Shirts")
        self.assertEqual(len(res), 1)

        # custom_cache should have values, whereas default_cache should still be empty
        self.assertIsNotNone(custom_cache.get("test-conn"))
        self.assertIsNone(DimensionValueResolver.default_cache.get("test-conn"))

    @patch("semantic.dimension_value_resolver.engine")
    def test_fuzzy_matcher_variations(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Banians", "normalized_value": "banians"}),
            MagicMock(_mapping={"semantic_dimension_id": 2, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Cotton Shirt", "normalized_value": "cotton shirt"}),
            MagicMock(_mapping={"semantic_dimension_id": 3, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "T Shirt", "normalized_value": "t shirt"}),
            MagicMock(_mapping={"semantic_dimension_id": 4, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Ram Raj", "normalized_value": "ram raj"}),
            MagicMock(_mapping={"semantic_dimension_id": 5, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Pants", "normalized_value": "pants"}),
            MagicMock(_mapping={"semantic_dimension_id": 6, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts", "normalized_value": "shirts"}),
            MagicMock(_mapping={"semantic_dimension_id": 7, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Cotton Pants", "normalized_value": "cotton pants"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Instantiate a resolver with an isolated FuzzyMatcher pipeline and custom cutoff
        from semantic.matching import MatchingPipeline, FuzzyMatcher
        custom_pipeline = MatchingPipeline(matchers=[FuzzyMatcher()])
        resolver = DimensionValueResolver(pipeline=custom_pipeline, settings={"FUZZY_SCORE_CUTOFF": 75})

        # Positive fuzzy cases
        positive_cases = [
            ("Baniaan", "Banians"),
            ("Banain", "Banians"),
            ("Bniyan", "Banians"),
            ("Cottn Shirt", "Cotton Shirt"),
            ("T Shrt", "T Shirt"),
            ("Ramraj", "Ram Raj"),
        ]

        for question, expected in positive_cases:
            res = resolver.resolve_matches("test-conn", question)
            self.assertGreaterEqual(len(res), 1, f"Fuzzy matching failed for positive case: {question}")
            
            # Verify the expected match exists in the results
            expected_matches = [m for m in res if m["value"] == expected]
            self.assertEqual(len(expected_matches), 1, f"Expected value '{expected}' not found in results for query '{question}': {res}")
            
            # Verify the expected match properties
            m = expected_matches[0]
            self.assertEqual(m["match_type"], "FUZZY")
            self.assertGreaterEqual(m["confidence"], 0.75)

        # Negative fuzzy cases
        negative_cases = [
            ("Laptop", "Pants"),
            ("Phone", "Shirts"),
            ("Mobile", "Cotton Pants"),
            ("Computer", "Banians"),
        ]

        for question, forbidden in negative_cases:
            res = resolver.resolve_matches("test-conn", question)
            matched_values = [r["value"] for r in res]
            self.assertNotIn(forbidden, matched_values, f"Fuzzy matching matched forbidden value for negative case: {question}")

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_phrase_extraction(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Banians", "normalized_value": "banians"}),
            MagicMock(_mapping={"semantic_dimension_id": 2, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Cotton Shirt", "normalized_value": "cotton shirt"}),
            MagicMock(_mapping={"semantic_dimension_id": 3, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "T Shirt", "normalized_value": "t shirt"}),
            MagicMock(_mapping={"semantic_dimension_id": 4, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Ram Raj", "normalized_value": "ram raj"}),
            MagicMock(_mapping={"semantic_dimension_id": 5, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Men's Wear", "normalized_value": "mens wear"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Use full default pipeline with custom score cutoff
        resolver = DimensionValueResolver(settings={"FUZZY_SCORE_CUTOFF": 75})

        integration_cases = [
            ("Show Banian sales", "Banians"),
            ("Show Baniaan sales", "Banians"),
            ("Show Banain sales", "Banians"),
            ("Show Ramraj sales", "Ram Raj"),
            ("Show T Shrt sales", "T Shirt"),
            ("Show Mens Wear sales", "Men's Wear"),
        ]

        for question, expected in integration_cases:
            res = resolver.resolve_matches("test-conn", question)
            self.assertGreaterEqual(len(res), 1, f"Integration matching failed for query: {question}")
            
            # Verify the expected match exists in the results
            expected_matches = [m for m in res if m["value"] == expected]
            self.assertEqual(len(expected_matches), 1, f"Expected value '{expected}' not found in results for query '{question}': {res}")

        negative_cases = [
            "Show Laptop sales",
            "Show Computer sales",
            "Show Mobile sales",
        ]

        for question in negative_cases:
            res = resolver.resolve_matches("test-conn", question)
            self.assertEqual(len(res), 0, f"Expected no match for: {question}, but got {res}")

    @patch("semantic.dimension_value_resolver.engine")
    def test_original_bug_fixed_resolver_tokens(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        
        resolver = DimensionValueResolver()
        
        with patch.object(resolver.pipeline, "execute") as mock_execute:
            mock_execute.return_value = ([], MagicMock())
            
            input_text = """
            Original Question:
            Show banian sales

            Follow-up Question:
            Quarterly trend
            """
            
            resolver.resolve_matches("test-conn", input_text)
            
            self.assertTrue(mock_execute.called)
            called_context = mock_execute.call_args[0][0]
            q_context = called_context.question_context
            
            self.assertIn("show", q_context.normalized_question.split())
            self.assertIn("banian", q_context.normalized_question.split())
            self.assertIn("sales", q_context.normalized_question.split())
            
            self.assertNotIn("follow", q_context.q_tokens)
            self.assertNotIn("up", q_context.q_tokens)
            self.assertNotIn("question", q_context.q_tokens)


    def test_duplicate_matchers_are_consolidated(self):
        matches = [
            MatchResult(
                matched=True,
                value="T-Shirt",
                normalized_value="t-shirt",
                confidence=1.0,
                match_type=MatchType.EXACT,
                matched_question_tokens=["t", "shirt"],
                matched_value_tokens=["t", "shirt"],
                reason="exact",
                dimension_id=1,
                business_name="Product Category",
                table_name="Products",
                column_name="CategoryName",
            ),
            MatchResult(
                matched=True,
                value="T-Shirt",
                normalized_value="t-shirt",
                confidence=0.98,
                match_type=MatchType.NORMALIZED,
                matched_question_tokens=["t", "shirt"],
                matched_value_tokens=["t", "shirt"],
                reason="normalized",
                dimension_id=1,
                business_name="Product Category",
                table_name="Products",
                column_name="CategoryName",
            ),
        ]

        result = DimensionValueResolver._consolidate_duplicate_matches(
            matches
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, "T-Shirt")
        self.assertEqual(
            result[0].match_type,
            MatchType.EXACT,
        )
        self.assertEqual(
            result[0].confidence,
            1.0,
        )

    def test_same_value_in_different_dimensions_is_not_consolidated(self):
        matches = [
            MatchResult(
                matched=True,
                value="RR",
                normalized_value="rr",
                confidence=1.0,
                match_type=MatchType.EXACT,
                matched_question_tokens=["rr"],
                matched_value_tokens=["rr"],
                reason="exact",
                dimension_id=1,
                business_name="Division",
                table_name="Sales",
                column_name="Division",
            ),
            MatchResult(
                matched=True,
                value="RR",
                normalized_value="rr",
                confidence=1.0,
                match_type=MatchType.EXACT,
                matched_question_tokens=["rr"],
                matched_value_tokens=["rr"],
                reason="exact",
                dimension_id=2,
                business_name="Brand",
                table_name="Products",
                column_name="Brand",
            ),
        ]

        result = DimensionValueResolver._consolidate_duplicate_matches(
            matches
        )

        self.assertEqual(len(result), 2)

    @patch("semantic.dimension_value_resolver.engine")
    def test_focused_regression_phase1b(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Shirts", "normalized_value": "shirts"}),
            MagicMock(_mapping={"semantic_dimension_id": 2, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Formal Shirts", "normalized_value": "formal shirts"}),
            MagicMock(_mapping={"semantic_dimension_id": 3, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Pants", "normalized_value": "pants"}),
            MagicMock(_mapping={"semantic_dimension_id": 8, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Cotton Pants", "normalized_value": "cotton pants"}),
            MagicMock(_mapping={"semantic_dimension_id": 9, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "T-Shirt", "normalized_value": "t-shirt"}),
            # Same value, different semantic dimensions:
            MagicMock(_mapping={"semantic_dimension_id": 10, "business_name": "Category1", "table_name": "T1", "column_name": "C1", "value": "CommonVal", "normalized_value": "commonval"}),
            MagicMock(_mapping={"semantic_dimension_id": 11, "business_name": "Category2", "table_name": "T2", "column_name": "C2", "value": "CommonVal", "normalized_value": "commonval"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Test A: Question "Pant" -> Pants (among other pant candidates)
        results_a = DimensionValueResolver.resolve("test-conn", "Pant")
        matched_a = [r["value"] for r in results_a]
        self.assertIn("Pants", matched_a, "Pant must match Pants")

        # Test B: Question "Cotton Pant" -> Cotton Pants
        results_b = DimensionValueResolver.resolve("test-conn", "Cotton Pant")
        self.assertEqual(len(results_b), 1)
        self.assertEqual(results_b[0]["value"], "Cotton Pants")

        # Test C: Question "Formal Shirt" -> Formal Shirts
        results_c = DimensionValueResolver.resolve("test-conn", "Formal Shirt")
        self.assertEqual(len(results_c), 1)
        self.assertEqual(results_c[0]["value"], "Formal Shirts")

        # Test D: Question "cotton sales pant" vs "cotton laptop pant"
        # "cotton sales pant" matches Cotton Pants because "sales" is a stopword and is removed, which is intentional.
        results_d_intentional = DimensionValueResolver.resolve("test-conn", "cotton sales pant")
        self.assertEqual(len(results_d_intentional), 1)
        self.assertEqual(results_d_intentional[0]["value"], "Cotton Pants")

        # "cotton laptop pant" must NOT select Cotton Pants because "laptop" is not a stopword and keeps them non-contiguous.
        results_d_negative = DimensionValueResolver.resolve("test-conn", "cotton laptop pant")
        results_d_negative_vals = [r["value"] for r in results_d_negative]
        self.assertNotIn("Cotton Pants", results_d_negative_vals)

        # Test E: Question "Show t shirt sales" -> T-Shirt
        results_e = DimensionValueResolver.resolve("test-conn", "Show t shirt sales")
        self.assertEqual(len(results_e), 1)
        self.assertEqual(results_e[0]["value"], "T-Shirt")

        # Test F: Same normalized value in different semantic dimensions remains separate
        results_f = DimensionValueResolver.resolve("test-conn", "CommonVal")
        self.assertEqual(len(results_f), 2)
        dimensions = {r["dimension_id"] for r in results_f}
        self.assertEqual(dimensions, {10, 11})

    def test_fuzzy_multiple_candidates_preserved(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher
        from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
        
        q_ctx = QuestionContext(
            raw_question="pant",
            normalized_question="pant",
            q_tokens=["pant"],
            q_singulars=["pant"]
        )
        
        indexed = []
        vals = ["Pants", "Cotton Pants", "Formal Pants", "Children Pants"]
        for idx, val in enumerate(vals):
            norm = val.lower()
            indexed.append(CachedDimensionValue(
                semantic_dimension_id=idx + 1,
                business_name="Category",
                table_name="T",
                column_name="C",
                value=val,
                normalized_value=norm,
                runtime_stored_norm=norm,
                runtime_stored_tokens=norm.split(),
                runtime_stored_singulars=norm.split(),
                runtime_raw_norm=norm,
                runtime_raw_tokens=norm.split(),
                runtime_raw_singulars=norm.split()
            ))
            
        context = MatchingContext(
            question_context=q_ctx,
            connection_id="test-conn",
            indexed_values=indexed
        )
        
        matcher = FuzzyMatcher()
        results = matcher.match(context)
        
        # Verify that all 4 are preserved (all score >= 85)
        self.assertEqual(len(results), 4)
        resolved_vals = {r.value for r in results}
        self.assertEqual(resolved_vals, set(vals))

    def test_fuzzy_specific_phrase_evidence_preserved(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher
        from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
        
        q_ctx = QuestionContext(
            raw_question="cotton pant",
            normalized_question="cotton pant",
            q_tokens=["cotton", "pant"],
            q_singulars=["cotton", "pant"]
        )
        
        indexed = []
        vals = ["Pants", "Cotton Pants", "Formal Pants"]
        for idx, val in enumerate(vals):
            norm = val.lower()
            indexed.append(CachedDimensionValue(
                semantic_dimension_id=idx + 1,
                business_name="Category",
                table_name="T",
                column_name="C",
                value=val,
                normalized_value=norm,
                runtime_stored_norm=norm,
                runtime_stored_tokens=norm.split(),
                runtime_stored_singulars=norm.split(),
                runtime_raw_norm=norm,
                runtime_raw_tokens=norm.split(),
                runtime_raw_singulars=norm.split()
            ))
            
        context = MatchingContext(
            question_context=q_ctx,
            connection_id="test-conn",
            indexed_values=indexed
        )
        
        matcher = FuzzyMatcher()
        results = matcher.match(context)
        
        cotton_pants_res = next(r for r in results if r.value == "Cotton Pants")
        self.assertEqual(cotton_pants_res.matched_question_tokens, ["cotton", "pant"])

    def test_fuzzy_formal_shirt_evidence_preserved(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher
        from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
        
        q_ctx = QuestionContext(
            raw_question="formal shirt",
            normalized_question="formal shirt",
            q_tokens=["formal", "shirt"],
            q_singulars=["formal", "shirt"]
        )
        
        indexed = []
        vals = ["Shirts", "Formal Shirts", "T-Shirts"]
        for idx, val in enumerate(vals):
            norm = val.lower()
            indexed.append(CachedDimensionValue(
                semantic_dimension_id=idx + 1,
                business_name="Category",
                table_name="T",
                column_name="C",
                value=val,
                normalized_value=norm,
                runtime_stored_norm=norm,
                runtime_stored_tokens=norm.split(),
                runtime_stored_singulars=norm.split(),
                runtime_raw_norm=norm,
                runtime_raw_tokens=norm.split(),
                runtime_raw_singulars=norm.split()
            ))
            
        context = MatchingContext(
            question_context=q_ctx,
            connection_id="test-conn",
            indexed_values=indexed
        )
        
        matcher = FuzzyMatcher()
        results = matcher.match(context)
        
        formal_shirts_res = next(r for r in results if r.value == "Formal Shirts")
        self.assertEqual(formal_shirts_res.matched_question_tokens, ["formal", "shirt"])

    def test_fuzzy_duplicate_evidence_consolidation(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher
        from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
        
        q_ctx = QuestionContext(
            raw_question="cotton pant",
            normalized_question="cotton pant",
            q_tokens=["cotton", "pant"],
            q_singulars=["cotton", "pant"]
        )
        
        indexed = [
            CachedDimensionValue(
                semantic_dimension_id=1,
                business_name="Category",
                table_name="T",
                column_name="C",
                value="Cotton Pants",
                normalized_value="cotton pants",
                runtime_stored_norm="cotton pants",
                runtime_stored_tokens=["cotton", "pants"],
                runtime_stored_singulars=["cotton", "pant"],
                runtime_raw_norm="cotton pants",
                runtime_raw_tokens=["cotton", "pants"],
                runtime_raw_singulars=["cotton", "pant"]
            )
        ]
        
        context = MatchingContext(
            question_context=q_ctx,
            connection_id="test-conn",
            indexed_values=indexed
        )
        
        matcher = FuzzyMatcher()
        results = matcher.match(context)
        
        # Verify that only ONE candidate is returned for Cotton Pants
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value, "Cotton Pants")

    def test_fuzzy_same_value_different_dimensions(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher
        from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
        
        q_ctx = QuestionContext(
            raw_question="pants",
            normalized_question="pants",
            q_tokens=["pants"],
            q_singulars=["pant"]
        )
        
        indexed = [
            CachedDimensionValue(
                semantic_dimension_id=1,
                business_name="Category1",
                table_name="T1",
                column_name="C1",
                value="Pants",
                normalized_value="pants",
                runtime_stored_norm="pants",
                runtime_stored_tokens=["pants"],
                runtime_stored_singulars=["pant"],
                runtime_raw_norm="pants",
                runtime_raw_tokens=["pants"],
                runtime_raw_singulars=["pant"]
            ),
            CachedDimensionValue(
                semantic_dimension_id=2,
                business_name="Category2",
                table_name="T2",
                column_name="C2",
                value="Pants",
                normalized_value="pants",
                runtime_stored_norm="pants",
                runtime_stored_tokens=["pants"],
                runtime_stored_singulars=["pant"],
                runtime_raw_norm="pants",
                runtime_raw_tokens=["pants"],
                runtime_raw_singulars=["pant"]
            )
        ]
        
        context = MatchingContext(
            question_context=q_ctx,
            connection_id="test-conn",
            indexed_values=indexed
        )
        
        matcher = FuzzyMatcher()
        results = matcher.match(context)
        
        # Both must remain
        self.assertEqual(len(results), 2)
        dims = {r.dimension_id for r in results}
        self.assertEqual(dims, {1, 2})

    def test_fuzzy_false_positives(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher
        from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
        
        questions = ["laptop", "banana", "hospital", "xyzabc"]
        indexed = []
        vals = ["Pants", "Cotton Pants", "Shirts", "Banians"]
        for idx, val in enumerate(vals):
            norm = val.lower()
            indexed.append(CachedDimensionValue(
                semantic_dimension_id=idx + 1,
                business_name="Category",
                table_name="T",
                column_name="C",
                value=val,
                normalized_value=norm,
                runtime_stored_norm=norm,
                runtime_stored_tokens=norm.split(),
                runtime_stored_singulars=norm.split(),
                runtime_raw_norm=norm,
                runtime_raw_tokens=norm.split(),
                runtime_raw_singulars=norm.split()
            ))
            
        matcher = FuzzyMatcher()
        for q in questions:
            q_ctx = QuestionContext(
                raw_question=q,
                normalized_question=q,
                q_tokens=[q],
                q_singulars=[q]
            )
            context = MatchingContext(
                question_context=q_ctx,
                connection_id="test-conn",
                indexed_values=indexed
            )
            results = matcher.match(context)
            self.assertEqual(len(results), 0, f"False positive matched for {q}: {results}")

class TestFuzzyTokenLevelEvidence(unittest.TestCase):
    def test_token_level_evidence_helper(self):
        from semantic.matching.fuzzy_matcher import FuzzyMatcher

        # MUST PASS:
        # pant ↔ LINEN PANT
        # pant ↔ RAMRAJ PANT
        # Banain ↔ Banians
        # T Shrt ↔ T Shirt
        
        pass_cases = [
            ("pant", "LINEN PANT", "pant", "pant"),
            ("pant", "RAMRAJ PANT", "pant", "pant"),
            ("Banain", "Banians", "banain", "barians"), # Wait, "Banians" normalized has "banians"
            ("T Shrt", "T Shirt", "shrt", "shirt"),
            ("t", "t", "t", "t") # Fallback case
        ]
        # Wait, for "Banians", the original token in c_tokens is "banians" (since norm_candidate is "banians")
        # Let's write the expected tokens carefully:
        pass_cases = [
            ("pant", "LINEN PANT", "pant", "pant"),
            ("pant", "RAMRAJ PANT", "pant", "pant"),
            ("Banain", "Banians", "banain", "banians"),
            ("T Shrt", "T Shirt", "shrt", "shirt"),
            ("t", "t", "t", "t"),
            ("Ramraj", "Ram Raj", "Ramraj", "Ram Raj")
        ]
        for q, c, expected_q, expected_c in pass_cases:
            res = FuzzyMatcher._has_token_level_evidence(q, c)
            self.assertTrue(
                res["passed"],
                f"Expected pass for query '{q}' and candidate '{c}', but got: {res}"
            )
            self.assertEqual(
                res["matched_query_token"], expected_q,
                f"Expected matched query token '{expected_q}' for '{q}' and '{c}', but got: {res}"
            )
            self.assertEqual(
                res["matched_candidate_token"], expected_c,
                f"Expected matched candidate token '{expected_c}' for '{q}' and '{c}', but got: {res}"
            )

        # MUST FAIL:
        # pant ↔ VEPPANTHATTAI
        # pant ↔ PANTHEERANKAVU
        # pant ↔ IYYAPPANTHANGAL
        # cotton pant ↔ AN
        
        fail_cases = [
            ("pant", "VEPPANTHATTAI"),
            ("pant", "PANTHEERANKAVU"),
            ("pant", "IYYAPPANTHANGAL"),
            ("cotton pant", "AN")
        ]
        for q, c in fail_cases:
            res = FuzzyMatcher._has_token_level_evidence(q, c)
            self.assertFalse(
                res["passed"],
                f"Expected fail for query '{q}' and candidate '{c}', but got: {res}"
            )

        # Edge cases: empty and completely unrelated
        edge_cases = [
            ("", "LINEN PANT"),
            ("pant", ""),
            ("", ""),
            ("pant", "completely unrelated")
        ]
        for q, c in edge_cases:
            res = FuzzyMatcher._has_token_level_evidence(q, c)
            self.assertFalse(
                res["passed"],
                f"Expected fail for edge case query '{q}' and candidate '{c}', but got: {res}"
            )

class TestFuzzyMatcherIntegration(unittest.TestCase):
    def test_fuzzy_matcher_integration_filtering(self):
        from semantic.matching import FuzzyMatcher, QuestionContext, MatchingContext
        from semantic.matching.models import CachedDimensionValue

        vals = [
            "LINEN PANT",
            "RAMRAJ PANT",
            "VEPPANTHATTAI",
            "PANTHEERANKAVU",
            "IYYAPPANTHANGAL",
            "AN",
            "Banians",
            "T Shirt",
            "Ram Raj"
        ]
        indexed = []
        for idx, val in enumerate(vals):
            norm = val.lower()
            indexed.append(CachedDimensionValue(
                semantic_dimension_id=idx + 1,
                business_name="Category",
                table_name="T",
                column_name="C",
                value=val,
                normalized_value=norm,
                runtime_stored_norm=norm,
                runtime_stored_tokens=norm.split(),
                runtime_stored_singulars=norm.split(),
                runtime_raw_norm=norm,
                runtime_raw_tokens=norm.split(),
                runtime_raw_singulars=norm.split()
            ))

        matcher = FuzzyMatcher()

        def get_matched_values(query):
            q_ctx = QuestionContext(
                raw_question=query,
                normalized_question=query.lower(),
                q_tokens=query.lower().split(),
                q_singulars=query.lower().split()
            )
            context = MatchingContext(
                question_context=q_ctx,
                connection_id="test-conn",
                indexed_values=indexed,
                settings={"FUZZY_SCORE_CUTOFF": 75}
            )
            results = matcher.match(context)
            return [r.value for r in results]

        res_pant = get_matched_values("pant")
        self.assertIn("LINEN PANT", res_pant)
        self.assertIn("RAMRAJ PANT", res_pant)
        self.assertNotIn("VEPPANTHATTAI", res_pant)
        self.assertNotIn("PANTHEERANKAVU", res_pant)
        self.assertNotIn("IYYAPPANTHANGAL", res_pant)

        res_cotton = get_matched_values("cotton pant")
        self.assertNotIn("AN", res_cotton)

        res_banain = get_matched_values("Banain")
        self.assertIn("Banians", res_banain)

        res_tshirt = get_matched_values("T Shrt")
        self.assertIn("T Shirt", res_tshirt)

        res_ramraj = get_matched_values("Ramraj")
        self.assertIn("Ram Raj", res_ramraj)

class TestContainmentRegression(unittest.TestCase):
    def setUp(self):
        DimensionValueResolver.clear_cache()

    @patch("semantic.dimension_value_resolver.engine")
    def test_containment_regression_cotton_pant(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        # Mock database rows for load_dimension_values
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Prod Grp2", "table_name": "T", "column_name": "C", "value": "LS PANT", "normalized_value": "ls pant"}),
            MagicMock(_mapping={"semantic_dimension_id": 2, "business_name": "Brand", "table_name": "T", "column_name": "C", "value": "LINEN PANT", "normalized_value": "linen pant"}),
            MagicMock(_mapping={"semantic_dimension_id": 3, "business_name": "Brand", "table_name": "T", "column_name": "C", "value": "RAMRAJ PANT", "normalized_value": "ramraj pant"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        # Resolve "cotton pant"
        results = DimensionValueResolver.resolve("test-conn", "cotton pant")
        matched_values = [r["value"] for r in results]
        
        # TEST 1: LINEN PANT survives
        self.assertIn("LINEN PANT", matched_values)
        # TEST 2: RAMRAJ PANT survives
        self.assertIn("RAMRAJ PANT", matched_values)
        # TEST 3: LS PANT survives
        self.assertIn("LS PANT", matched_values)

    @patch("semantic.dimension_value_resolver.engine")
    def test_legitimate_containment_behavior(self, mock_engine):
        # TEST 4: Existing legitimate containment behavior still works
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        mock_rows = [
            MagicMock(_mapping={"semantic_dimension_id": 1, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Cotton Pants", "normalized_value": "cotton pants"}),
            MagicMock(_mapping={"semantic_dimension_id": 2, "business_name": "Category", "table_name": "T", "column_name": "C", "value": "Pants", "normalized_value": "pants"}),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows

        results = DimensionValueResolver.resolve("test-conn", "Cotton Pant")
        matched_values = [r["value"] for r in results]
        
        # Pants (confidence 1.0) is suppressed by Cotton Pants (confidence 1.0)
        self.assertIn("Cotton Pants", matched_values)
        self.assertNotIn("Pants", matched_values)

class TestSingularPluralMatcherPhase1B(unittest.TestCase):
    """
    Phase 1D.1-B focused regression tests.

    setUp / tearDown clear the default resolver cache so that
    every test starts with a clean index, preventing mock row
    pollution across tests that share the same connection_id key.
    """

    def setUp(self):
        DimensionValueResolver.clear_cache()

    def tearDown(self):
        DimensionValueResolver.clear_cache()

    # ---

    # ------------------------------------------------------------------
    # Unit tests: matches_tokens() directly
    # ------------------------------------------------------------------

    def test_pant_matches_pant_singulars(self):
        """Case 1 — pant ↔ pant (sublist path, unchanged behaviour)."""
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=["pant"],
            val_singulars=["pant"],
        )
        self.assertTrue(result)

    def test_pants_matches_pant_singulars(self):
        """Case 2 — pants (singularised → pant) ↔ pant (sublist path)."""
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher as SPM
        q_sing = [SPM._to_singular("pants")]   # → ["pant"]
        v_sing = [SPM._to_singular("pant")]    # → ["pant"]
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=q_sing,
            val_singulars=v_sing,
        )
        self.assertTrue(result)

    def test_banian_matches_banian_singulars(self):
        """Case 3 — banian ↔ banian (sublist path, unchanged behaviour)."""
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=["banian"],
            val_singulars=["banian"],
        )
        self.assertTrue(result)

    def test_banians_matches_banian_singulars(self):
        """Case 4 — banians (singularised → banian) ↔ banian (sublist path)."""
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher as SPM
        q_sing = [SPM._to_singular("banians")]  # → ["banian"]
        v_sing = [SPM._to_singular("banian")]   # → ["banian"]
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=q_sing,
            val_singulars=v_sing,
        )
        self.assertTrue(result)

    def test_pants_matches_linen_pant_singulars(self):
        """Case 5 — pants (→ ["pant"]) ↔ LINEN PANT (→ ["linen","pant"]) via intersection."""
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher as SPM
        q_sing = [SPM._to_singular("pants")]               # → ["pant"]
        v_sing = [SPM._to_singular(t) for t in ["linen", "pant"]]  # → ["linen","pant"]
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=q_sing,
            val_singulars=v_sing,
        )
        self.assertTrue(result, "pants should match LINEN PANT via shared singular token 'pant'")

    def test_pants_matches_ramraj_pant_singulars(self):
        """Case 6 — pants (→ ["pant"]) ↔ RAMRAJ PANT (→ ["ramraj","pant"]) via intersection."""
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher as SPM
        q_sing = [SPM._to_singular("pants")]                    # → ["pant"]
        v_sing = [SPM._to_singular(t) for t in ["ramraj", "pant"]]  # → ["ramraj","pant"]
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=q_sing,
            val_singulars=v_sing,
        )
        self.assertTrue(result, "pants should match RAMRAJ PANT via shared singular token 'pant'")

    def test_unrelated_token_does_not_match_multi_token_value(self):
        """Case 7 — completely unrelated query must NOT fire the fallback."""
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=["laptop"],
            val_singulars=["linen", "pant"],
        )
        self.assertFalse(result, "'laptop' must not match 'LINEN PANT'")

    def test_cotton_laptop_pant_does_not_match_cotton_pants(self):
        """
        Guard: query LONGER than candidate — sublist must be contiguous.

        'cotton laptop pant' must NOT match 'Cotton Pants' even though
        both 'cotton' and 'pant' appear in the query, because 'laptop'
        breaks the contiguous sequence.  The asymmetric-query fallback
        must NOT fire when len(q) >= len(v).
        """
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher as SPM
        q_sing = [SPM._to_singular(t) for t in ["cotton", "laptop", "pant"]]
        v_sing = [SPM._to_singular(t) for t in ["cotton", "pant"]]
        result = SingularPluralMatcher.matches_tokens(
            q_singulars=q_sing,
            val_singulars=v_sing,
        )
        self.assertFalse(result, "'cotton laptop pant' must not match 'Cotton Pants'")

    # ------------------------------------------------------------------
    # Static API tests: matches() end-to-end string interface
    # ------------------------------------------------------------------

    def test_static_api_pants_matches_linen_pant(self):
        """matches() static API: 'pants' ↔ 'LINEN PANT' must return matched=True."""
        result = SingularPluralMatcher.matches("pants", "LINEN PANT")
        self.assertTrue(result.matched)
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(result.match_type, MatchType.SINGULAR_PLURAL)

    def test_static_api_pants_matches_ramraj_pant(self):
        """matches() static API: 'pants' ↔ 'RAMRAJ PANT' must return matched=True."""
        result = SingularPluralMatcher.matches("pants", "RAMRAJ PANT")
        self.assertTrue(result.matched)
        self.assertEqual(result.confidence, 0.95)

    def test_static_api_pant_matches_pant(self):
        """matches() static API: 'pant' ↔ 'pant' (unchanged behaviour)."""
        result = SingularPluralMatcher.matches("pant", "pant")
        self.assertTrue(result.matched)

    def test_static_api_banian_matches_banian(self):
        """matches() static API: 'banian' ↔ 'banian' (unchanged behaviour)."""
        result = SingularPluralMatcher.matches("banian", "banian")
        self.assertTrue(result.matched)

    def test_static_api_banians_matches_banian(self):
        """matches() static API: 'banians' ↔ 'banian' (unchanged behaviour)."""
        result = SingularPluralMatcher.matches("banians", "banian")
        self.assertTrue(result.matched)

    def test_static_api_laptop_does_not_match_linen_pant(self):
        """matches() static API: unrelated token must not match multi-token value."""
        result = SingularPluralMatcher.matches("laptop", "LINEN PANT")
        self.assertFalse(result.matched)

    # ------------------------------------------------------------------
    # Safety Guard focused unit tests (Phase 1D.1-C.1)
    # ------------------------------------------------------------------

    def test_safety_guard_matches_tokens_positives(self):
        # 1. matches_tokens(["pant"], ["linen", "pant"]) == True
        self.assertTrue(SingularPluralMatcher.matches_tokens(["pant"], ["linen", "pant"]))
        # 2. matches_tokens(["banian"], ["1", "banian"]) == True
        self.assertTrue(SingularPluralMatcher.matches_tokens(["banian"], ["1", "banian"]))
        # 3. matches_tokens(["banian"], ["banians"]) == True (where "banians" -> "banian" singularized)
        self.assertTrue(SingularPluralMatcher.matches_tokens(["banian"], ["banian"]))

    def test_safety_guard_matches_tokens_negatives(self):
        # 4. matches_tokens(["t"], ["t", "shirt"]) == False
        self.assertFalse(SingularPluralMatcher.matches_tokens(["t"], ["t", "shirt"]))
        # 5. matches_tokens(["r"], ["r", "neck"]) == False
        self.assertFalse(SingularPluralMatcher.matches_tokens(["r"], ["r", "neck"]))
        # 6. matches_tokens(["ap"], ["vt", "showroom", "ap"]) == False
        self.assertFalse(SingularPluralMatcher.matches_tokens(["ap"], ["vt", "showroom", "ap"]))
        # 7. matches_tokens(["ts"], ["vt", "marketing", "ts"]) == False
        self.assertFalse(SingularPluralMatcher.matches_tokens(["ts"], ["vt", "marketing", "ts"]))

    def test_safety_guard_static_api_consistency(self):
        # Pants ↔ LINEN PANT must match (meaningful token >= 3)
        self.assertTrue(SingularPluralMatcher.matches("pants", "LINEN PANT").matched)
        # Banians ↔ banian must match
        self.assertTrue(SingularPluralMatcher.matches("banians", "banian").matched)

        # t ↔ T SHIRT must not match via SingularPluralMatcher
        self.assertFalse(SingularPluralMatcher.matches("t", "T SHIRT").matched)
        # r ↔ R.NECK must not match
        self.assertFalse(SingularPluralMatcher.matches("r", "R.NECK").matched)
        # ap ↔ VT-Showroom-AP must not match
        self.assertFalse(SingularPluralMatcher.matches("ap", "VT-Showroom-AP").matched)
        # ts ↔ VT-Marketing-TS must not match
        self.assertFalse(SingularPluralMatcher.matches("ts", "VT-Marketing-TS").matched)

        # Standalone exact match must still match (sublist length is equal, so contiguous check handles it)
        self.assertTrue(SingularPluralMatcher.matches("ap", "AP").matched)
        self.assertTrue(SingularPluralMatcher.matches("ts", "TS").matched)

    # ------------------------------------------------------------------
    # Integration tests: full pipeline via DimensionValueResolver
    # ------------------------------------------------------------------

    def _make_mock_rows(self):
        """Shared set of indexed values for integration tests."""
        rows_data = [
            {"semantic_dimension_id": 1,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "LINEN PANT",    "normalized_value": "linen pant"},
            {"semantic_dimension_id": 2,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "RAMRAJ PANT",   "normalized_value": "ramraj pant"},
            {"semantic_dimension_id": 3,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "FORMAL PANTS",  "normalized_value": "formal pants"},
            {"semantic_dimension_id": 4,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "Banians",       "normalized_value": "banians"},
            {"semantic_dimension_id": 5,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "Banian",        "normalized_value": "banian"},
            {"semantic_dimension_id": 6,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "Laptop",        "normalized_value": "laptop"},
            {"semantic_dimension_id": 7,  "business_name": "Product", "table_name": "T", "column_name": "C",
             "value": "Mobile Phone",  "normalized_value": "mobile phone"},
        ]
        return [MagicMock(_mapping=d) for d in rows_data]

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_pants_resolves_linen_pant(self, mock_engine):
        """
        End-to-end: question 'pants' must return LINEN PANT as a candidate.
        This is the primary bug case from the Phase 1D.1-B specification.
        """
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "pants")
        matched_values = [r["value"] for r in results]

        self.assertIn("LINEN PANT", matched_values,
                      f"'pants' must resolve LINEN PANT. Got: {matched_values}")

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_pants_resolves_ramraj_pant(self, mock_engine):
        """
        End-to-end: question 'pants' must return RAMRAJ PANT as a candidate.
        This is the primary bug case from the Phase 1D.1-B specification.
        """
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "pants")
        matched_values = [r["value"] for r in results]

        self.assertIn("RAMRAJ PANT", matched_values,
                      f"'pants' must resolve RAMRAJ PANT. Got: {matched_values}")

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_pants_all_pant_candidates_returned(self, mock_engine):
        """
        Ambiguity safety: all three pant-related candidates must survive.
        The matcher must NOT collapse multiple candidates into one.
        """
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "pants")
        matched_values = [r["value"] for r in results]

        self.assertIn("LINEN PANT",   matched_values)
        self.assertIn("RAMRAJ PANT",  matched_values)
        self.assertIn("FORMAL PANTS", matched_values)

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_pant_singular_still_works(self, mock_engine):
        """
        Regression guard: 'pant' (singular) must still resolve correctly.
        """
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "pant")
        matched_values = [r["value"] for r in results]

        self.assertIn("LINEN PANT",  matched_values)
        self.assertIn("RAMRAJ PANT", matched_values)

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_banian_resolves(self, mock_engine):
        """Case 3 end-to-end: 'banian' must resolve Banian."""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "banian")
        matched_values = [r["value"] for r in results]
        self.assertIn("Banian", matched_values)

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_banians_resolves(self, mock_engine):
        """Case 4 end-to-end: 'banians' must resolve Banians (and Banian)."""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "banians")
        matched_values = [r["value"] for r in results]
        self.assertIn("Banians", matched_values)

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_unrelated_token_no_match(self, mock_engine):
        """Unrelated query 'laptop' must only match the Laptop value, not pant values."""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = self._make_mock_rows()

        results = DimensionValueResolver.resolve("test-conn", "laptop")
        matched_values = [r["value"] for r in results]

        self.assertNotIn("LINEN PANT",  matched_values)
        self.assertNotIn("RAMRAJ PANT", matched_values)

    @patch("semantic.dimension_value_resolver.engine")
    def test_integration_match_type_is_singular_plural_for_pants(self, mock_engine):
        """
        For the pants → LINEN PANT match the match_type must be
        SINGULAR_PLURAL (not FUZZY), confirming the matcher path used.
        """
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        # Use a minimal index: only LINEN PANT so containment cannot suppress it.
        mock_conn.execute.return_value.fetchall.return_value = [
            MagicMock(_mapping={
                "semantic_dimension_id": 1, "business_name": "Product",
                "table_name": "T", "column_name": "C",
                "value": "LINEN PANT", "normalized_value": "linen pant",
            })
        ]

        results = DimensionValueResolver.resolve("test-conn", "pants")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "LINEN PANT")
        self.assertEqual(results[0]["match_type"], MatchType.SINGULAR_PLURAL.value)
        self.assertEqual(results[0]["confidence"], 0.95)


class TestFuzzyCoverageRankingFix(unittest.TestCase):
    def test_fuzzy_coverage_precedes_confidence(self):
        from semantic.matching.models import MatchResult, MatchType
        from semantic.matching.ranker import MatchRanker

        # Candidate A: FUZZY, coverage 2/2, confidence 0.90
        # Candidate B: FUZZY, coverage 1/2, confidence 0.95
        cand_a = MatchResult(
            matched=True,
            value="Cotton Pants",
            normalized_value="cotton pants",
            confidence=0.90,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["cotton", "pant"],
            matched_value_tokens=["cotton", "pants"],
            reason="fuzzy",
            dimension_id=1,
            business_name="Product Group",
            table_name="Products",
            column_name="ProductGroup"
        )
        cand_b = MatchResult(
            matched=True,
            value="Formal Socks",
            normalized_value="formal socks",
            confidence=0.95,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["pant"],
            matched_value_tokens=["socks"],
            reason="fuzzy",
            dimension_id=2,
            business_name="Product Category",
            table_name="Products",
            column_name="CategoryName"
        )

        # Ranked list with input question tokens "cotton pant"
        ranked = MatchRanker.rank([cand_b, cand_a], ["cotton", "pant"])
        
        # Candidate A (Cotton Pants) must rank first due to higher coverage (2/2 vs 1/2)
        self.assertEqual(ranked[0].value, "Cotton Pants")
        self.assertEqual(ranked[1].value, "Formal Socks")

    def test_fuzzy_confidence_breaks_tie_when_coverage_equal(self):
        from semantic.matching.models import MatchResult, MatchType
        from semantic.matching.ranker import MatchRanker

        # Candidate A: FUZZY, coverage 2/2, confidence 0.90
        # Candidate B: FUZZY, coverage 2/2, confidence 0.85
        cand_a = MatchResult(
            matched=True,
            value="Cotton Pants",
            normalized_value="cotton pants",
            confidence=0.90,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["cotton", "pant"],
            matched_value_tokens=["cotton", "pants"],
            reason="fuzzy",
            dimension_id=1,
            business_name="Product Group",
            table_name="Products",
            column_name="ProductGroup"
        )
        cand_b = MatchResult(
            matched=True,
            value="Formal Shirts",
            normalized_value="formal shirts",
            confidence=0.85,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["cotton", "pant"],
            matched_value_tokens=["formal", "shirts"],
            reason="fuzzy",
            dimension_id=2,
            business_name="Product Category",
            table_name="Products",
            column_name="CategoryName"
        )

        ranked = MatchRanker.rank([cand_b, cand_a], ["cotton", "pant"])

        # Candidate A (0.90 conf) must rank first since coverage is equal (2/2)
        self.assertEqual(ranked[0].value, "Cotton Pants")
        self.assertEqual(ranked[1].value, "Formal Shirts")


if __name__ == "__main__":
    unittest.main()


