"""
Gate 3 Step 21c - focused tests.

Two surgical production changes are covered here:

1. semantic/semantic_gate.py: WEAK_AMBIGUITY now blocks SQL generation when
   more than one genuine value survived the candidate-retention filtering
   (semantic_result["value_matches"]), and is unchanged (falls through,
   allowed) when exactly one genuine value remains.

2. ai/prompt_builder.py: the PARTIAL_MATCH clarification branch now offers
   every genuine value_matches entry as an option (dominant first), instead
   of only the first one; the single-value case is unchanged. A new
   WEAK_AMBIGUITY branch reuses the same AmbiguityException/options shape to
   surface the gate's new WEAK_AMBIGUITY block - no new mechanism.

SemanticGate itself is exercised for real (not mocked) so both changes are
tested together, the way production actually calls them.
"""
import unittest
from unittest.mock import MagicMock, patch

from semantic.matching.models import SemanticResolutionResult, ResolutionStatus
from semantic.semantic_gate import SemanticGate
from semantic.execution_context import SemanticExecutionContext
from semantic.temporal.pipeline import TemporalPipeline
from ai.prompt_builder import PromptBuilder
from core.exceptions import AmbiguityException


def _value(value, business_name, table_name, column_name, dimension_id,
           match_type="EXACT", confidence=0.9):
    return {
        "dimension_id": dimension_id,
        "business_name": business_name,
        "table_name": table_name,
        "column_name": column_name,
        "value": value,
        "normalized_value": value.lower(),
        "confidence": confidence,
        "match_type": match_type,
        "matched_question_tokens": [],
        "matched_value_tokens": [],
        "reason": "test"
    }


class TestSemanticGateWeakAmbiguity(unittest.TestCase):
    """The gate change in isolation, no HTTP/prompt layer involved."""

    def _semantic_result(self, status, value_matches):
        ambig_res = SemanticResolutionResult(status=status, candidates=[])
        return {
            "retrieval": {"status": "COMPLETE", "confidence": 0.75, "resolved_components": 2},
            "ambiguity_result": ambig_res,
            "value_matches": value_matches
        }

    def test_weak_ambiguity_two_genuine_candidates_blocks(self):
        sr = self._semantic_result(
            ResolutionStatus.WEAK_AMBIGUITY,
            [_value("ETHNIC WEAR", "Prod Grp2", "SALES", "ProdGrp2", 1),
             _value("N--NIGHT WEARS", "Prod Grp2", "SALES", "ProdGrp2", 1)]
        )
        gate_res = SemanticGate.evaluate(sr)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "WEAK_AMBIGUITY")

    def test_weak_ambiguity_one_candidate_unchanged(self):
        sr = self._semantic_result(
            ResolutionStatus.WEAK_AMBIGUITY,
            [_value("CHENNAI", "City", "SALES", "City", 1)]
        )
        gate_res = SemanticGate.evaluate(sr)
        self.assertTrue(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "COMPLETE")

    def test_strong_ambiguity_behavior_unchanged(self):
        sr = self._semantic_result(ResolutionStatus.STRONG_AMBIGUITY, [])
        gate_res = SemanticGate.evaluate(sr)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "STRONG_AMBIGUITY")

    def test_partial_match_behavior_unchanged(self):
        sr = self._semantic_result(
            ResolutionStatus.PARTIAL_MATCH,
            [_value("BANIANS", "Prod Grp1", "SALES", "ProdGrp1", 1)]
        )
        gate_res = SemanticGate.evaluate(sr)
        self.assertFalse(gate_res["allowed"])
        self.assertEqual(gate_res["status"], "PARTIAL_MATCH")

    def test_complete_and_insufficient_unchanged(self):
        # No ambiguity_result at all - the pre-existing count-based path.
        self.assertTrue(SemanticGate.evaluate(
            {"retrieval": {"status": "COMPLETE", "confidence": 1.0, "resolved_components": 3}}
        )["allowed"])
        self.assertFalse(SemanticGate.evaluate(
            {"retrieval": {"status": "INSUFFICIENT", "confidence": 0.0, "resolved_components": 0}}
        )["allowed"])


class TestPromptBuilderClarificationOptions(unittest.TestCase):
    """
    The options-building change in ai/prompt_builder.py, exercised through
    PromptBuilder.build_sql_prompt with SemanticResolver mocked (controls
    value_matches/ambiguity_result) and SemanticGate left real, mirroring the
    isolation pattern already used in test_prompt_builder_temporal.py.
    """

    def setUp(self):
        self.mock_pipeline = MagicMock(spec=TemporalPipeline)
        self.mock_pipeline.build.return_value = ""
        self.prompt_builder = PromptBuilder(temporal_pipeline=self.mock_pipeline)

        self.conn_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_service = self.conn_patcher.start()
        self.mock_conn_service.get_connection.return_value = {
            "connection_id": "test_conn",
            "connection_name": "Test DB",
            "database_type": "mssql"
        }

        self.resolver_patcher = patch("ai.prompt_builder.SemanticResolver")
        self.mock_semantic_resolver = self.resolver_patcher.start()

        self.table_patcher = patch("ai.prompt_builder.RelevantTableResolver")
        self.table_patcher.start()
        self.expander_patcher = patch("ai.prompt_builder.RelationshipExpander")
        self.expander_patcher.start()
        self.rel_context_patcher = patch("ai.prompt_builder.RelationshipContextService")
        self.rel_context_patcher.start()
        self.metadata_patcher = patch("semantic.metadata_resolver.MetadataResolver")
        self.mock_metadata_resolver = self.metadata_patcher.start()
        self.mock_metadata_resolver.resolve.return_value = {"metadata_rules": [], "required_tables": []}
        self.schema_patcher = patch("ai.prompt_builder.RelevantSchemaService")
        self.mock_schema_service = self.schema_patcher.start()
        self.mock_schema_service.get_schema.return_value = "CREATE TABLE Sales (SalesID INT)"
        self.examples_patcher = patch("ai.prompt_builder.QueryExamplesService")
        self.examples_patcher.start()
        self.sem_ctx_patcher = patch("ai.prompt_builder.SemanticContextService")
        self.sem_ctx_patcher.start()

    def tearDown(self):
        self.conn_patcher.stop()
        self.resolver_patcher.stop()
        self.table_patcher.stop()
        self.expander_patcher.stop()
        self.rel_context_patcher.stop()
        self.metadata_patcher.stop()
        self.schema_patcher.stop()
        self.examples_patcher.stop()
        self.sem_ctx_patcher.stop()

    def _mock_resolve(self, status, value_matches, metric_objects=None, dimension_objects=None):
        ambig_res = SemanticResolutionResult(status=status, candidates=[])
        self.mock_semantic_resolver.resolve.return_value = {
            "metrics": "C Y",
            "dimensions": "None",
            "metric_objects": metric_objects or [{"business_name": "C Y", "table_name": "SALES", "column_name": "CY"}],
            "dimension_objects": dimension_objects or [],
            "value_matches": value_matches,
            "retrieval": {
                "status": "COMPLETE",
                "confidence": 0.75,
                "reason": None,
                "unresolved_terms": [],
                "resolved_components": 2,
                "resolved_metric_count": 1,
                "resolved_dimension_count": 0,
                "resolved_value_count": len(value_matches),
                "resolved_table_count": 1
            },
            "ambiguity_result": ambig_res,
            "followup_context": {"applied": False, "reason": "NO_ELIGIBLE_PREVIOUS_CONTEXT"}
        }

    def test_children_wear_both_genuine_options_reach_clarification(self):
        self._mock_resolve(
            ResolutionStatus.PARTIAL_MATCH,
            [_value("ETHNIC WEAR", "Prod Grp2", "SALES", "ProdGrp2", 1),
             _value("N--NIGHT WEARS", "Prod Grp2", "SALES", "ProdGrp2", 1)]
        )
        with self.assertRaises(AmbiguityException) as ctx:
            self.prompt_builder.build_sql_prompt(
                question="Total sales for children wear", connection_id="test_conn"
            )
        options = ctx.exception.details["options"]
        self.assertEqual([o["value"] for o in options], ["ETHNIC WEAR", "N--NIGHT WEARS"])
        self.assertEqual(ctx.exception.details["ambiguity_type"], "PARTIAL_MATCH")

    def test_women_wear_both_genuine_options_reach_clarification(self):
        self._mock_resolve(
            ResolutionStatus.PARTIAL_MATCH,
            [_value("ETHNIC WEAR", "Prod Grp2", "SALES", "ProdGrp2", 1),
             _value("N--NIGHT WEARS", "Prod Grp2", "SALES", "ProdGrp2", 1)]
        )
        with self.assertRaises(AmbiguityException) as ctx:
            self.prompt_builder.build_sql_prompt(
                question="Total sales for women wear", connection_id="test_conn"
            )
        options = ctx.exception.details["options"]
        self.assertEqual({o["value"] for o in options}, {"ETHNIC WEAR", "N--NIGHT WEARS"})

    def test_partial_match_two_values_both_options_dominant_first(self):
        self._mock_resolve(
            ResolutionStatus.PARTIAL_MATCH,
            [_value("BANIANS", "Prod Grp1", "SALES", "ProdGrp1", 1),
             _value("SECONDS BANIAN", "Prod Grp1", "SALES", "ProdGrp1", 1)]
        )
        with self.assertRaises(AmbiguityException) as ctx:
            self.prompt_builder.build_sql_prompt(question="q", connection_id="test_conn")
        options = ctx.exception.details["options"]
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]["value"], "BANIANS")
        self.assertEqual(options[0]["option_id"], 1)
        self.assertEqual(options[1]["option_id"], 2)

    def test_partial_match_one_value_single_option_unchanged(self):
        self._mock_resolve(
            ResolutionStatus.PARTIAL_MATCH,
            [_value("BANIANS", "Prod Grp1", "SALES", "ProdGrp1", 1)]
        )
        with self.assertRaises(AmbiguityException) as ctx:
            self.prompt_builder.build_sql_prompt(
                question="Total sales for Banians", connection_id="test_conn"
            )
        options = ctx.exception.details["options"]
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["value"], "BANIANS")
        self.assertIn("Would you like to use that?", ctx.exception.message)

    def test_chennai_city_single_genuine_value_no_new_clarification_from_ambiguity(self):
        # After the candidate-retention filter, "Chennai city" leaves exactly
        # one genuine value - WEAK_AMBIGUITY with one candidate must not be
        # blocked by the gate, so build_sql_prompt must not raise here.
        self._mock_resolve(
            ResolutionStatus.WEAK_AMBIGUITY,
            [_value("CHENNAI", "City", "SALES", "City", 1)]
        )
        prompt, semantic_result, _ = self.prompt_builder.build_sql_prompt(
            question="Show sales for Chennai city", connection_id="test_conn"
        )
        self.assertIsNotNone(prompt)

    def test_weak_ambiguity_two_genuine_values_triggers_clarification(self):
        self._mock_resolve(
            ResolutionStatus.WEAK_AMBIGUITY,
            [_value("VT", "Division", "SALES", "Division", 1),
             _value("VT2", "Division", "SALES", "Division", 1)]
        )
        with self.assertRaises(AmbiguityException) as ctx:
            self.prompt_builder.build_sql_prompt(question="Show sales for VT", connection_id="test_conn")
        options = ctx.exception.details["options"]
        self.assertEqual([o["value"] for o in options], ["VT", "VT2"])
        self.assertEqual(ctx.exception.details["ambiguity_type"], "SAME_DIMENSION")


if __name__ == "__main__":
    unittest.main()
