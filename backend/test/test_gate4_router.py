"""
Gate 4 Steps 22, 23, 24 - routing tests.

Structured around the four things that must hold:

  positive         each destination is reached by questions that belong to it
  negative         each destination is NOT reached by questions that do not
  false positive   the specific traps that broke the previous router
  regression       the demo vocabulary is gone and cannot come back

No database and no model. The vocabulary stage is fed through
vocabulary_service.prime() and the model stage is patched, so these tests state
facts about the routing rules rather than about whichever provider answered.
"""

import unittest
from unittest.mock import patch

from ai.intent_classifier import (
    Destination,
    LEGACY_ANALYTICS,
    LEGACY_GENERAL,
    answer_metadata,
    classify_intent,
    route_question,
)
from semantic import vocabulary_service
from semantic.vocabulary_service import Vocabulary, VocabularyTerm


CONNECTION = "TEST-CONNECTION-GATE4"


class RoutingDecisionStub:
    """Stand-in for a model decision, so patched tests need no provider."""
    destination = Destination.SMALL_TALK
    reason = "stub"
    method = "llm"
    matched_terms: list = []


def _term(term, canonical, kind, synonym=False):
    return VocabularyTerm(
        term=term, canonical=canonical, kind=kind, is_synonym=synonym
    )


def _textile_vocabulary() -> Vocabulary:
    """
    A vocabulary shaped like this customer's: textiles, not AdventureWorks.

    Deliberately contains no term from the old hardcoded lists, so any test that
    passes because of a leftover keyword rather than configuration will fail.
    """
    metrics = [
        {"metric_name": "Qty", "business_name": "Quantity", "table_name": "SALES",
         "column_name": "QTY", "synonyms": "qty, units, pieces", "description": None,
         "aggregation_type": "SUM"},
        {"metric_name": "Amt", "business_name": "Amount", "table_name": "SALES",
         "column_name": "AMT", "synonyms": "amount, value", "description": None,
         "aggregation_type": "SUM"},
        {"metric_name": "pendamt", "business_name": "Pending Amount",
         "table_name": "PENDING", "column_name": "PENDAMT",
         "synonyms": "pending, outstanding", "description": None,
         "aggregation_type": "SUM"},
    ]
    dimensions = [
        {"dimension_name": "brand", "business_name": "Brand", "table_name": "SALES",
         "column_name": "BRAND", "synonyms": "brands", "semantic_category": None,
         "description": None},
        {"dimension_name": "city", "business_name": "City", "table_name": "SALES",
         "column_name": "CITY", "synonyms": "cities, town", "semantic_category": None,
         "description": None},
        {"dimension_name": "product", "business_name": "Product", "table_name": "SALES",
         "column_name": "PRODUCT", "synonyms": "products, item, items",
         "semantic_category": None, "description": None},
    ]
    domains = [
        {"domain_name": "sales", "business_name": "Sales", "synonyms": "selling",
         "description": None},
    ]
    return Vocabulary(
        connection_id=CONNECTION,
        metrics=metrics,
        dimensions=dimensions,
        domains=domains,
        terms=vocabulary_service._build_terms(metrics, dimensions, domains),
    )


class RouterTestBase(unittest.TestCase):
    def setUp(self):
        vocabulary_service.invalidate()
        vocabulary_service.prime(CONNECTION, _textile_vocabulary())

    def tearDown(self):
        vocabulary_service.invalidate()

    def route(self, question):
        return route_question(question, connection_id=CONNECTION)


class TestSmallTalk(RouterTestBase):
    """SMALL_TALK must never reach the analytical pipeline."""

    def test_greetings_route_to_small_talk(self):
        for question in ["hi", "Hello", "hello!", "good morning", "thanks",
                         "thank you", "bye", "how are you", "who are you"]:
            with self.subTest(question=question):
                self.assertEqual(
                    self.route(question).destination, Destination.SMALL_TALK
                )

    def test_greeting_never_runs_analytics(self):
        # The headline Done criterion for step 22.
        for question in ["hi", "hello", "thanks", "ok", "bye"]:
            with self.subTest(question=question):
                self.assertNotEqual(
                    self.route(question).destination, Destination.ANALYTICAL
                )

    def test_small_talk_is_decided_without_a_model(self):
        # A greeting must cost nothing. If this ever calls the model, the router
        # has stopped being deterministic where it can be.
        with patch("ai.intent_classifier._llm_stage") as llm:
            self.route("hello")
            llm.assert_not_called()

    def test_greeting_attached_to_a_real_question_is_not_small_talk(self):
        # False-positive guard. Matching "hello" anywhere would swallow this.
        decision = self.route("hello, what is the total amount by brand")
        self.assertEqual(decision.destination, Destination.ANALYTICAL)

    def test_empty_message_is_small_talk(self):
        self.assertEqual(self.route("").destination, Destination.SMALL_TALK)
        self.assertEqual(self.route("   ").destination, Destination.SMALL_TALK)


class TestMetadata(RouterTestBase):
    """METADATA is answered from configuration and never generates SQL."""

    def test_capability_questions_route_to_metadata(self):
        for question in [
            "what can I ask?",
            "what data do you have",
            "what metrics do you have",
            "which dimensions are available",
            "do you track returns?",
            "list the fields",
            "what can you do",
        ]:
            with self.subTest(question=question):
                self.assertEqual(
                    self.route(question).destination, Destination.METADATA
                )

    def test_value_question_with_capability_framing_is_analytical(self):
        # False-positive guard: "do you have" is a capability frame, but this
        # question asks for a figure, not for the schema.
        decision = self.route("do you have the total amount for last month")
        self.assertEqual(decision.destination, Destination.ANALYTICAL)

    def test_metadata_answer_lists_only_configured_names(self):
        answer = answer_metadata("what can I ask?", CONNECTION)
        self.assertIsNotNone(answer)
        for configured in ["Quantity", "Amount", "Brand", "City", "Product"]:
            self.assertIn(configured, answer)

    def test_metadata_answer_never_invents(self):
        # Terms from the demo database must not appear in an answer built from
        # this customer's configuration.
        answer = answer_metadata("what can I ask?", CONNECTION) or ""
        for invented in ["Reseller", "Salesperson", "Subcategory", "OrderDate"]:
            self.assertNotIn(invented, answer)

    def test_metric_focus_does_not_recite_dimensions(self):
        answer = answer_metadata("what metrics do you have", CONNECTION) or ""
        self.assertIn("Quantity", answer)
        self.assertNotIn("Ways I can break", answer)

    def test_coverage_question_answers_yes_for_configured(self):
        answer = answer_metadata("do you track brand?", CONNECTION) or ""
        self.assertTrue(answer.lower().startswith("yes"))

    def test_coverage_question_answers_no_for_unconfigured(self):
        answer = answer_metadata("do you track returns?", CONNECTION) or ""
        self.assertTrue(answer.lower().startswith("no"))

    def test_metadata_returns_none_without_configuration(self):
        # No configuration must produce "I cannot tell", never a confident list.
        vocabulary_service.invalidate()
        vocabulary_service.prime("EMPTY", Vocabulary(connection_id="EMPTY"))
        self.assertIsNone(answer_metadata("what can I ask?", "EMPTY"))


class TestAnalytical(RouterTestBase):
    """ANALYTICAL is reached from configured vocabulary, not a static list."""

    def test_metric_with_operation_routes_analytical(self):
        for question in [
            "total amount",
            "quantity by brand",
            "top 5 products by amount",
            "pending amount last month",
            "compare amount this year vs last year",
        ]:
            with self.subTest(question=question):
                decision = self.route(question)
                self.assertEqual(decision.destination, Destination.ANALYTICAL)
                self.assertEqual(decision.method, "vocabulary")

    def test_synonyms_route_as_well_as_business_names(self):
        # "units" is a configured synonym of Quantity and must route.
        decision = self.route("total units by city")
        self.assertEqual(decision.destination, Destination.ANALYTICAL)
        self.assertIn("Quantity", decision.matched_terms)

    def test_two_configured_terms_route_without_an_operation(self):
        decision = self.route("quantity brand")
        self.assertEqual(decision.destination, Destination.ANALYTICAL)

    def test_one_generic_term_alone_does_not_route(self):
        # "Amount" is a configured metric here, but it is also an ordinary
        # English word. Alone and without an operation it is not evidence.
        with patch("ai.intent_classifier._llm_stage") as llm:
            llm.return_value = RoutingDecisionStub()
            self.route("amount")
            llm.assert_called_once()

    def test_single_bare_term_defers_to_the_model(self):
        # "brand" alone is genuinely ambiguous, and the counting rule must not
        # pretend otherwise.
        with patch("ai.intent_classifier._llm_stage") as llm:
            llm.return_value = type(
                "D", (), {"destination": Destination.SMALL_TALK}
            )()
            self.route("brand")
            llm.assert_called_once()

    def test_unconfigured_connection_falls_through_to_model(self):
        vocabulary_service.invalidate()
        with patch("ai.intent_classifier._llm_stage") as llm:
            route_question("total amount", connection_id=None)
            llm.assert_called_once()


class TestNoDemoVocabulary(unittest.TestCase):
    """
    Regression: step 23's whole point.

    The demo terms must not appear as literals anywhere in the router. This
    reads the module source, because a keyword list that comes back in a later
    edit is exactly the failure being guarded against, and a behavioural test
    would only catch it for the questions it happened to try.
    """

    DEMO_TERMS = [
        "reseller", "salesperson", "subcategory", "orderdate",
        "unitprice", "adventureworks",
    ]

    @staticmethod
    def _executable_source(module) -> str:
        """
        Module source with comments and docstrings stripped.

        The router's own docstring names the demo terms in order to explain that
        they were removed, and a naive substring scan would flag that as the
        very thing it is documenting. Only executable code is searched, which is
        the only place a keyword could actually influence a routing decision.
        """
        import ast
        import inspect
        import io
        import tokenize

        raw = inspect.getsource(module)

        stripped = []
        for token in tokenize.generate_tokens(io.StringIO(raw).readline):
            if token.type == tokenize.COMMENT:
                continue
            stripped.append(token)

        tree = ast.parse(raw)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)

        parts = []
        for token in stripped:
            if token.type == tokenize.STRING:
                literal = ast.literal_eval(token.string)
                if isinstance(literal, str) and literal in docstrings:
                    continue
            parts.append(token.string)

        return " ".join(parts).lower()

    def test_demo_terms_are_absent_from_the_router(self):
        from ai import intent_classifier

        source = self._executable_source(intent_classifier)
        for term in self.DEMO_TERMS:
            with self.subTest(term=term):
                self.assertNotIn(term, source)

    def test_no_static_analytics_keyword_list_remains(self):
        from ai import intent_classifier

        for removed in ("_ANALYTICS_KEYWORDS", "_STRONG_KEYWORDS", "_WEAK_KEYWORDS"):
            with self.subTest(name=removed):
                self.assertFalse(hasattr(intent_classifier, removed))


class TestLegacyCompatibility(RouterTestBase):
    """
    classify_intent() keeps its old contract.

    app.py branches on these two strings and roughly thirty existing tests patch
    this function. Changing what it returns would break them silently.
    """

    def test_returns_only_legacy_values(self):
        for question in ["hi", "what can I ask?", "total amount by brand"]:
            with self.subTest(question=question):
                result = classify_intent(question, connection_id=CONNECTION)
                self.assertIn(result, (LEGACY_ANALYTICS, LEGACY_GENERAL))

    def test_analytical_maps_to_analytics(self):
        self.assertEqual(
            classify_intent("total amount by brand", connection_id=CONNECTION),
            LEGACY_ANALYTICS,
        )

    def test_small_talk_maps_to_general(self):
        self.assertEqual(
            classify_intent("hello", connection_id=CONNECTION), LEGACY_GENERAL
        )

    def test_metadata_maps_to_general_until_app_is_updated(self):
        # Where these questions already went. Mapping them anywhere else would
        # be a behaviour change this file is not allowed to make on its own.
        self.assertEqual(
            classify_intent("what can I ask?", connection_id=CONNECTION),
            LEGACY_GENERAL,
        )

    def test_signature_still_accepts_positional_question_only(self):
        self.assertIn(classify_intent("hello"), (LEGACY_ANALYTICS, LEGACY_GENERAL))


class TestExclusionsReachTheRouter(unittest.TestCase):
    """
    Gate 2 exclusions must remove routing keywords, not just answers.

    A hidden column that still steers the conversation has not really been
    hidden. The filter itself belongs to Gate 3; what is asserted here is that
    this module calls it rather than reimplementing it.
    """

    def test_vocabulary_service_uses_runtime_config_filter(self):
        import inspect
        from semantic import vocabulary_service as module

        source = inspect.getsource(module)
        self.assertIn("runtime_config_filter.metric_filter()", source)
        self.assertIn("runtime_config_filter.dimension_filter()", source)

    def test_no_second_exclusion_mechanism(self):
        import inspect
        from semantic import vocabulary_service as module

        source = inspect.getsource(module)
        # The predicate must come from the shared helper, never be spelled out
        # here. A second copy is a second thing to keep in step with Gate 2.
        self.assertNotIn("is_excluded = 0", source)
        self.assertNotIn("dimension_role", source.split('"""', 2)[-1])


if __name__ == "__main__":
    unittest.main()
