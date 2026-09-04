"""
Gate 3 Step 7b Fix B - the plan's dimension bindings reach the prompt.

Proves the exact gap the end-to-end validation found: SemanticPlanBuilder
could already substitute a configured month dimension and carry a sort
column on SemanticPlan.dimensions[i].order_by_column, but nothing in
prompt_builder read plan.dimensions, so the substitution never reached the
text the model writes SQL from. This is prompt-only - it does not touch
SemanticResolver, SemanticPlanBuilder, or the conformance guard.

Mocking follows the same scaffold as test_prompt_builder_temporal.py so the
pipeline reaches a real rendered prompt string rather than testing a private
helper in isolation.

    python backend/test/test_prompt_builder_dimension_binding.py
"""
import unittest
from unittest.mock import MagicMock, patch

from ai.prompt_builder import PromptBuilder
from semantic.models.semantic_plan import (
    SemanticDimension,
    SemanticIntent,
    SemanticMetric,
    SemanticPlan,
    SemanticTable,
)
from semantic.temporal.pipeline import TemporalPipeline

SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"


def _plan(dimensions, metrics=None):
    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=metrics or [
            SemanticMetric(metric_name="cy", business_name="Sales",
                           table_name=SALES, column_name="CY",
                           aggregation_type="SUM")
        ],
        dimensions=dimensions,
        filters=[],
        primary_table=SALES,
        relevant_tables=[SemanticTable(table_name=SALES)],
        assumptions_made=[],
    )


class TestDimensionBindingReachesPrompt(unittest.TestCase):
    """Same mocking scaffold as TestPromptBuilderTemporalUnit."""

    def setUp(self):
        self.mock_pipeline = MagicMock(spec=TemporalPipeline)
        self.mock_pipeline.build.return_value = ""
        self.prompt_builder = PromptBuilder(temporal_pipeline=self.mock_pipeline)

        self.conn_patcher = patch("services.connection_service.ConnectionService")
        self.mock_conn_service = self.conn_patcher.start()
        self.mock_conn_service.get_connection.return_value = {
            "connection_id": "test_conn", "connection_name": "Test DB",
            "database_type": "mssql",
        }

        self.resolver_patcher = patch("ai.prompt_builder.SemanticResolver")
        self.mock_semantic_resolver = self.resolver_patcher.start()
        self.mock_semantic_resolver.resolve.return_value = {
            "metrics": "Sales", "dimensions": "Document Month",
            "metric_objects": [{
                "metric_name": "cy", "business_name": "Sales",
                "table_name": SALES, "column_name": "CY",
                "aggregation_type": "SUM",
            }],
            # The resolver's own pick - DocMonth, the pre-Fix-B behaviour.
            "dimension_objects": [{
                "dimension_name": "docmonth", "business_name": "Document Month",
                "table_name": SALES, "column_name": "DocMonth",
                "semantic_category": None, "dimension_role": "TIME_LABEL",
            }],
            "value_matches": [],
            "retrieval": {"status": "COMPLETE", "confidence": 1.0, "reason": None},
        }

        self.gate_patcher = patch("ai.prompt_builder.SemanticGate")
        self.mock_semantic_gate = self.gate_patcher.start()
        self.mock_semantic_gate.evaluate.return_value = {"allowed": True, "reason": None}

        self.table_patcher = patch("ai.prompt_builder.RelevantTableResolver")
        self.table_patcher.start()

        self.expander_patcher = patch("ai.prompt_builder.RelationshipExpander")
        self.expander_patcher.start()

        self.rel_context_patcher = patch("ai.prompt_builder.RelationshipContextService")
        self.rel_context_patcher.start()

        self.metadata_patcher = patch("semantic.metadata_resolver.MetadataResolver")
        self.mock_metadata_resolver = self.metadata_patcher.start()
        self.mock_metadata_resolver.resolve.return_value = {
            "metadata_rules": [], "required_tables": [],
        }

        self.schema_patcher = patch("ai.prompt_builder.RelevantSchemaService")
        self.mock_schema_service = self.schema_patcher.start()
        self.mock_schema_service.get_schema.return_value = (
            f"CREATE TABLE {SALES} (CY INT, DocMonth INT, InvMonth NVARCHAR(10))"
        )

        self.examples_patcher = patch("ai.prompt_builder.QueryExamplesService")
        self.examples_patcher.start()

        self.sem_ctx_patcher = patch("ai.prompt_builder.SemanticContextService")
        self.sem_ctx_patcher.start()

        # The plan builder itself - stubbed with a fixed SemanticPlan so this
        # test is about prompt rendering, not plan construction. Step 7b's
        # own substitution logic is covered by test_temporal_config_authority.py.
        self.plan_patcher = patch(
            "semantic.semantic_plan_builder.SemanticPlanBuilder.build"
        )
        self.mock_plan_build = self.plan_patcher.start()
        self.mock_plan_build.return_value = _plan([
            SemanticDimension(
                dimension_name="invmonth", business_name="Inv Month",
                table_name=SALES, column_name="InvMonth",
                semantic_category="Time", dimension_role="TIME_LABEL",
                order_by_column="InvMonth",
            )
        ])

    def tearDown(self):
        self.conn_patcher.stop()
        self.resolver_patcher.stop()
        self.gate_patcher.stop()
        self.table_patcher.stop()
        self.expander_patcher.stop()
        self.rel_context_patcher.stop()
        self.metadata_patcher.stop()
        self.schema_patcher.stop()
        self.examples_patcher.stop()
        self.sem_ctx_patcher.stop()
        self.plan_patcher.stop()

    # -- 1. the planned month dimension reaches the prompt -----------------

    def test_planned_dimension_business_name_is_in_the_prompt(self):
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month", connection_id="test_conn")
        self.assertIn("Business Dimension: Inv Month", prompt)

    def test_planned_dimension_physical_column_is_in_the_prompt(self):
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month", connection_id="test_conn")
        self.assertIn("Physical Dimension: InvMonth", prompt)

    def test_the_authoritative_binding_names_invmonth_not_docmonth(self):
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month", connection_id="test_conn")
        section = prompt.split("SEMANTIC PLAN")[1].split("SEMANTIC CONTEXT")[0]
        self.assertIn(
            "You MUST use physical column 'InvMonth' for any references to "
            "Business Dimension 'Inv Month' in SELECT and GROUP BY.",
            section,
        )

    def test_relevant_dimensions_still_shows_the_resolvers_own_pick(self):
        # Fix A (propagating plan.dimensions into dimension_objects) is
        # explicitly NOT done here - RELEVANT DIMENSIONS (built straight from
        # SemanticResolver's own output, untouched by this change) still names
        # the resolver's pick, and SEMANTIC PLAN is what overrides it for SQL
        # generation. Rule 13 is what tells the model which one wins.
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month", connection_id="test_conn")
        section = prompt.split("RELEVANT DIMENSIONS")[1].split("MATCHED DIMENSION")[0]
        self.assertIn("Document Month", section)

    # -- 2. order_by_column reaches the prompt ------------------------------

    @staticmethod
    def _plan_section(prompt):
        """The SEMANTIC PLAN block only, excluding rule 13's static text
        (which also contains the words "Authoritative Ordering") so these
        assertions test what was RENDERED FOR THIS DIMENSION, not whether the
        static rule text happens to be present."""
        return prompt.split("SEMANTIC PLAN")[1].split("SEMANTIC CONTEXT")[0]

    def test_order_by_column_produces_an_authoritative_ordering_line(self):
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month", connection_id="test_conn")
        section = self._plan_section(prompt)
        self.assertIn(
            "Authoritative Ordering: You MUST ORDER BY physical column "
            "'InvMonth' when the query is broken down by Business Dimension "
            "'Inv Month'",
            section,
        )

    def test_no_order_by_column_emits_no_ordering_line_for_that_dimension(self):
        self.mock_plan_build.return_value = _plan([
            SemanticDimension(
                dimension_name="category", business_name="Category",
                table_name=SALES, column_name="Category",
                semantic_category="Product", dimension_role="GROUPING",
                order_by_column=None,
            )
        ])
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by category", connection_id="test_conn")
        section = self._plan_section(prompt)
        self.assertIn("Business Dimension: Category", section)
        self.assertNotIn("Authoritative Ordering", section)

    def test_multiple_dimensions_each_get_their_own_block(self):
        self.mock_plan_build.return_value = _plan([
            SemanticDimension(
                dimension_name="invmonth", business_name="Inv Month",
                table_name=SALES, column_name="InvMonth",
                order_by_column="InvMonth",
            ),
            SemanticDimension(
                dimension_name="category", business_name="Category",
                table_name=SALES, column_name="Category",
                order_by_column=None,
            ),
        ])
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month and category",
            connection_id="test_conn")
        section = self._plan_section(prompt)
        self.assertIn("Business Dimension: Inv Month", section)
        self.assertIn("Business Dimension: Category", section)
        self.assertEqual(section.count("Authoritative Ordering"), 1)

    # -- 3. the rule the model is told to follow ----------------------------

    def test_rule_13_governs_semantic_plan_dimension_authority(self):
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales by month", connection_id="test_conn")
        self.assertIn(
            "13. Where the SEMANTIC PLAN section lists a Business Dimension "
            "with a Physical Dimension, that Physical Dimension is the "
            "authoritative column",
            prompt,
        )
        self.assertIn("do not substitute the grouping column for it", prompt)

    def test_no_plan_dimensions_means_no_dimension_block(self):
        self.mock_plan_build.return_value = _plan([])
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales", connection_id="test_conn")
        self.assertNotIn("Business Dimension:", prompt)
        # Rule 13 itself is static prompt text and is always present.
        self.assertIn("13. Where the SEMANTIC PLAN section", prompt)

    def test_no_plan_at_all_produces_none_semantic_plan_section(self):
        self.mock_plan_build.side_effect = Exception("plan compilation failed")
        prompt, _, _ = self.prompt_builder.build_sql_prompt(
            question="Show CY sales", connection_id="test_conn")
        self.assertNotIn("Business Dimension:", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
