
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from unittest.mock import MagicMock, patch
from semantic.matching import MatchResult
from semantic.dimension_value_resolver import DimensionValueResolver, MatchType, ResolvedDimensionValue


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
            self.assertEqual(len(results), 1, f"Failed positive match for: {question}")
            self.assertEqual(results[0]["value"], expected_value)
            self.assertEqual(results[0]["match_type"], MatchType.SINGULAR_PLURAL.value)
            self.assertEqual(results[0]["confidence"], 0.95)

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
            self.assertEqual(len(res), 1, f"Fuzzy matching failed for positive case: {question}")
            self.assertEqual(res[0]["value"], expected)
            self.assertEqual(res[0]["match_type"], "FUZZY")
            self.assertGreaterEqual(res[0]["confidence"], 0.75)

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
            self.assertEqual(len(res), 1, f"Integration matching failed for query: {question}")
            self.assertEqual(res[0]["value"], expected)

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

        # Test A: Question "Pant" -> Pants
        results_a = DimensionValueResolver.resolve("test-conn", "Pant")
        self.assertEqual(len(results_a), 1)
        self.assertEqual(results_a[0]["value"], "Pants")

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

if __name__ == "__main__":
    unittest.main()

