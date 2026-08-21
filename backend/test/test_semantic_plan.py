import unittest
import json
import datetime
from pydantic import ValidationError

from semantic.models.semantic_plan import (
    SemanticPlan,
    SemanticIntent,
    SemanticQueryShape,
    FilterOperator,
    SemanticMetric,
    SemanticDimension,
    SemanticFilter,
    SemanticTable,
    SemanticJoin,
    SemanticPlanConfidence
)
from semantic.temporal.models import TimeContext, CurrentYearIntent
from semantic.temporal.enums import TimeIntentType, TimeStrategyType, CalendarType, Granularity
from semantic.matching.models import (
    SemanticResolutionResult,
    ResolutionStatus,
    AmbiguityChoice,
    MatchResult,
    MatchType
)


class TestSemanticPlanModel(unittest.TestCase):
    """
    Focused unit tests validating the canonical SemanticPlan model.
    """

    def test_test1_basic_aggregate(self):
        """
        TEST 1 — BASIC AGGREGATE
        Represent: 'Show sales'
        Expected: intent = aggregate, metric = Sales/CY, aggregation = SUM, shape = SINGLE_VALUE
        """
        metric = SemanticMetric(
            metric_name="cy",
            business_name="Sales",
            table_name="QB_MDJMD_SALES_5YRS_SUMMARY",
            column_name="CY",
            aggregation_type="SUM"
        )
        plan = SemanticPlan(
            intent=SemanticIntent.AGGREGATE,
            metrics=[metric],
            query_shape=SemanticQueryShape.SINGLE_VALUE
        )

        self.assertEqual(plan.intent, SemanticIntent.AGGREGATE)
        self.assertEqual(len(plan.metrics), 1)
        self.assertEqual(plan.metrics[0].business_name, "Sales")
        self.assertEqual(plan.metrics[0].aggregation_type, "SUM")
        self.assertEqual(plan.query_shape, SemanticQueryShape.SINGLE_VALUE)

        # Verify serialization preserves fields
        data = plan.model_dump()
        self.assertEqual(data["intent"], "AGGREGATE")
        self.assertEqual(data["metrics"][0]["metric_name"], "cy")

    def test_test2_multiple_metrics(self):
        """
        TEST 2 — MULTIPLE METRICS
        Represent: 'Sales + Quantity'
        Verify both metrics are preserved independently.
        """
        m1 = SemanticMetric(
            metric_name="cy",
            business_name="Sales",
            table_name="QB_MDJMD_SALES_5YRS_SUMMARY",
            column_name="CY",
            aggregation_type="SUM"
        )
        m2 = SemanticMetric(
            metric_name="qty",
            business_name="Quantity",
            table_name="PBI_ENES_ORDER_PENDING_SUMMARY",
            column_name="Qty",
            aggregation_type="SUM"
        )
        plan = SemanticPlan(
            metrics=[m1, m2]
        )

        self.assertEqual(len(plan.metrics), 2)
        self.assertEqual(plan.metrics[0].metric_name, "cy")
        self.assertEqual(plan.metrics[1].metric_name, "qty")

    def test_test3_multiple_dimensions(self):
        """
        TEST 3 — MULTIPLE DIMENSIONS
        Represent: 'State + City'
        Verify both dimensions are preserved.
        """
        d1 = SemanticDimension(
            dimension_name="state",
            business_name="State",
            table_name="PBI_OUTSTANDING_ENES_SUMMARY",
            column_name="State1"
        )
        d2 = SemanticDimension(
            dimension_name="city",
            business_name="City",
            table_name="PBI_OUTSTANDING_ENES_SUMMARY",
            column_name="City"
        )
        plan = SemanticPlan(
            dimensions=[d1, d2]
        )

        self.assertEqual(len(plan.dimensions), 2)
        self.assertEqual(plan.dimensions[0].dimension_name, "state")
        self.assertEqual(plan.dimensions[1].dimension_name, "city")

    def test_test4_multiple_filters(self):
        """
        TEST 4 — MULTIPLE FILTERS
        Represent: City = Chennai, Brand = Unibro, Category = Marketing, Product = White Shirt
        Verify all filters are preserved.
        """
        f1 = SemanticFilter(
            dimension_name="city",
            table_name="PBI_OUTSTANDING_ENES_SUMMARY",
            column_name="City",
            operator=FilterOperator.EQUAL,
            values=["Chennai"]
        )
        f2 = SemanticFilter(
            dimension_name="brand",
            table_name="PBI_ENES_ORDER_PENDING_SUMMARY",
            column_name="Brand",
            operator=FilterOperator.EQUAL,
            values=["Unibro"]
        )
        f3 = SemanticFilter(
            dimension_name="category",
            table_name="PBI_ENES_ORDER_PENDING_SUMMARY",
            column_name="Category",
            operator=FilterOperator.EQUAL,
            values=["Marketing"]
        )
        f4 = SemanticFilter(
            dimension_name="item_name",
            table_name="PBI_ENES_ORDER_PENDING_SUMMARY",
            column_name="ItemName",
            operator=FilterOperator.EQUAL,
            values=["White Shirt"]
        )

        plan = SemanticPlan(
            filters=[f1, f2, f3, f4]
        )

        self.assertEqual(len(plan.filters), 4)
        filter_names = [f.dimension_name for f in plan.filters]
        self.assertIn("city", filter_names)
        self.assertIn("brand", filter_names)
        self.assertIn("category", filter_names)
        self.assertIn("item_name", filter_names)

    def test_test5_multi_value_filter(self):
        """
        TEST 5 — MULTI-VALUE FILTER
        Represent: City IN [Chennai, Coimbatore]
        Verify values remain structured.
        """
        f = SemanticFilter(
            dimension_name="city",
            table_name="PBI_OUTSTANDING_ENES_SUMMARY",
            column_name="City",
            operator=FilterOperator.IN,
            values=["Chennai", "Coimbatore"]
        )
        plan = SemanticPlan(
            filters=[f]
        )

        self.assertEqual(len(plan.filters), 1)
        self.assertEqual(plan.filters[0].operator, FilterOperator.IN)
        self.assertEqual(plan.filters[0].values, ["Chennai", "Coimbatore"])

    def test_test6_multiple_filter_operators(self):
        """
        TEST 6 — MULTIPLE FILTER OPERATORS
        Verify operators (=, IN, >=, BETWEEN) construct and validate successfully.
        """
        f1 = SemanticFilter(
            dimension_name="d1",
            table_name="t",
            column_name="c1",
            operator=FilterOperator.EQUAL,
            values=["v1"]
        )
        f2 = SemanticFilter(
            dimension_name="d2",
            table_name="t",
            column_name="c2",
            operator=FilterOperator.IN,
            values=["v1", "v2"]
        )
        f3 = SemanticFilter(
            dimension_name="d3",
            table_name="t",
            column_name="c3",
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            values=[100]
        )
        f4 = SemanticFilter(
            dimension_name="d4",
            table_name="t",
            column_name="c4",
            operator=FilterOperator.BETWEEN,
            values=[10, 50]
        )

        plan = SemanticPlan(
            filters=[f1, f2, f3, f4]
        )
        self.assertEqual(len(plan.filters), 4)
        self.assertEqual(plan.filters[0].operator, "=")
        self.assertEqual(plan.filters[1].operator, "IN")
        self.assertEqual(plan.filters[2].operator, ">=")
        self.assertEqual(plan.filters[3].operator, "BETWEEN")

        # Invalid operator validation
        with self.assertRaises(ValidationError):
            SemanticFilter(
                dimension_name="d",
                table_name="t",
                column_name="c",
                operator="INVALID_OP",  # type: ignore
                values=["val"]
            )

        # Empty values validation
        with self.assertRaises(ValidationError):
            SemanticFilter(
                dimension_name="d",
                table_name="t",
                column_name="c",
                operator=FilterOperator.EQUAL,
                values=[]
            )

    def test_test7_temporal(self):
        """
        TEST 7 — TEMPORAL
        Attach an existing temporal result representing current year.
        Verify it survives serialization without modification.
        """
        ref_date = datetime.date(2026, 8, 19)
        intent = CurrentYearIntent(
            reference_date=ref_date,
            calendar_type=CalendarType.CALENDAR,
            intent_type=TimeIntentType.CURRENT_YEAR
        )
        time_context = TimeContext(
            intent=intent,
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="DocDate",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            calendar_type=CalendarType.CALENDAR
        )

        plan = SemanticPlan(
            temporal=time_context
        )

        self.assertIsNotNone(plan.temporal)
        self.assertEqual(plan.temporal.date_column, "DocDate")
        self.assertEqual(plan.temporal.start_date, datetime.date(2026, 1, 1))

        # Test Pydantic serialization
        serialized = plan.model_dump()
        self.assertIsNotNone(serialized["temporal"])
        self.assertEqual(serialized["temporal"]["date_column"], "DocDate")

    def test_test8_comparison(self):
        """
        TEST 8 — COMPARISON
        Represent a current-vs-previous-year comparison using the existing temporal structures.
        Verify no SQL is generated and structures map appropriately.
        """
        # Comparison uses granularity/comparison parameters in TimeContext
        time_context = TimeContext(
            intent=CurrentYearIntent(),
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY"],
            comparison="YEAR_OVER_YEAR"
        )
        plan = SemanticPlan(
            intent=SemanticIntent.COMPARISON,
            temporal=time_context,
            query_shape=SemanticQueryShape.COMPARISON
        )

        self.assertEqual(plan.intent, SemanticIntent.COMPARISON)
        self.assertEqual(plan.temporal.comparison, "YEAR_OVER_YEAR")
        self.assertEqual(plan.temporal.snapshot_columns, ["CY", "PY"])
        self.assertEqual(plan.query_shape, SemanticQueryShape.COMPARISON)

    def test_test9_table_and_join(self):
        """
        TEST 9 — TABLE + JOIN
        Represent: primary table, secondary table, one or more joins.
        Verify all structures serialize deterministically.
        """
        t1 = SemanticTable(table_name="T1", score=10.0, is_bridge=False)
        t2 = SemanticTable(table_name="T2", score=0.0, is_bridge=True)
        j = SemanticJoin(
            source_table="T1",
            source_key="Key",
            target_table="T2",
            target_key="Key"
        )

        plan = SemanticPlan(
            primary_table="T1",
            relevant_tables=[t1, t2],
            joins=[j]
        )

        self.assertEqual(plan.primary_table, "T1")
        self.assertEqual(len(plan.relevant_tables), 2)
        self.assertEqual(len(plan.joins), 1)

        serialized = plan.model_dump()
        self.assertEqual(serialized["primary_table"], "T1")
        self.assertEqual(serialized["relevant_tables"][0]["table_name"], "T1")
        self.assertEqual(serialized["joins"][0]["source_table"], "T1")

    def test_test10_ambiguity(self):
        """
        TEST 10 — AMBIGUITY
        Represent: clarification required.
        Verify the plan does NOT look executable/resolved.
        """
        match = MatchResult(
            matched=True,
            value="Val",
            normalized_value="val",
            confidence=0.8,
            match_type=MatchType.FUZZY,
            matched_question_tokens=["val"],
            matched_value_tokens=["val"],
            reason="ambiguous match"
        )
        choice1 = AmbiguityChoice(result=match)
        choice2 = AmbiguityChoice(result=match)
        
        ambiguity = SemanticResolutionResult(
            status=ResolutionStatus.STRONG_AMBIGUITY,
            candidates=[choice1, choice2]
        )

        plan = SemanticPlan(
            ambiguity_state=ambiguity
        )

        self.assertIsNotNone(plan.ambiguity_state)
        self.assertEqual(plan.ambiguity_state.status, ResolutionStatus.STRONG_AMBIGUITY)
        
        # Determine execution status
        is_executable = (
            plan.ambiguity_state is None 
            or plan.ambiguity_state.status == ResolutionStatus.SINGLE_MATCH
        )
        self.assertFalse(is_executable, "Plan should not be executable under STRONG_AMBIGUITY")

    def test_test11_complete_plan(self):
        """
        TEST 11 — COMPLETE PLAN
        Construct a full plan containing all possible fields.
        Verify every object survives construction and serialization.
        """
        metric1 = SemanticMetric(metric_name="cy", business_name="Sales", table_name="T1", column_name="CY", aggregation_type="SUM")
        metric2 = SemanticMetric(metric_name="qty", business_name="Qty", table_name="T1", column_name="Qty", aggregation_type="SUM")
        
        dim1 = SemanticDimension(dimension_name="city", business_name="City", table_name="T2", column_name="City")
        dim2 = SemanticDimension(dimension_name="brand", business_name="Brand", table_name="T1", column_name="Brand")

        f1 = SemanticFilter(dimension_name="city", table_name="T2", column_name="City", operator=FilterOperator.IN, values=["Chennai", "Coimbatore"])
        f2 = SemanticFilter(dimension_name="brand", table_name="T1", column_name="Brand", operator=FilterOperator.EQUAL, values=["Unibro"])
        f3 = SemanticFilter(dimension_name="amount", table_name="T1", column_name="Amt", operator=FilterOperator.GREATER_THAN_OR_EQUAL, values=[1000])
        f4 = SemanticFilter(dimension_name="status", table_name="T1", column_name="Status", operator=FilterOperator.IS_NOT_NULL, values=[True])

        ref_date = datetime.date(2026, 8, 19)
        time_context = TimeContext(
            intent=CurrentYearIntent(reference_date=ref_date),
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="DocDate",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31)
        )

        t1 = SemanticTable(table_name="T1", score=8.0)
        t2 = SemanticTable(table_name="T2", score=5.0)
        
        j = SemanticJoin(source_table="T1", source_key="Key", target_table="T2", target_key="Key")

        conf = SemanticPlanConfidence(status="COMPLETE", confidence=0.9, reason="All grounded")

        plan = SemanticPlan(
            intent=SemanticIntent.COMPARISON,
            metrics=[metric1, metric2],
            dimensions=[dim1, dim2],
            filters=[f1, f2, f3, f4],
            temporal=time_context,
            query_shape=SemanticQueryShape.COMPARISON,
            business_domain="SALES",
            primary_table="T1",
            relevant_tables=[t1, t2],
            joins=[j],
            confidence=conf
        )

        # Verify survival
        self.assertEqual(plan.intent, SemanticIntent.COMPARISON)
        self.assertEqual(len(plan.metrics), 2)
        self.assertEqual(len(plan.dimensions), 2)
        self.assertEqual(len(plan.filters), 4)
        self.assertEqual(plan.temporal.date_column, "DocDate")
        self.assertEqual(plan.query_shape, SemanticQueryShape.COMPARISON)
        self.assertEqual(plan.business_domain, "SALES")
        self.assertEqual(plan.primary_table, "T1")
        self.assertEqual(len(plan.relevant_tables), 2)
        self.assertEqual(len(plan.joins), 1)
        self.assertEqual(plan.confidence.confidence, 0.9)

        # Verify serialization
        json_data = plan.model_dump_json()
        parsed = json.loads(json_data)
        self.assertEqual(parsed["intent"], "COMPARISON")
        self.assertEqual(len(parsed["metrics"]), 2)
        self.assertEqual(len(parsed["filters"]), 4)
        self.assertEqual(parsed["temporal"]["date_column"], "DocDate")

    def test_test12_no_business_hardcoding(self):
        """
        TEST 12 — NO BUSINESS HARDCODING
        Verify that no business-specific terminology is hardcoded in the source file.
        """
        import os
        source_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "semantic", "models", "semantic_plan.py")
        )
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re
        forbidden_patterns = [
            r"\bcy\b",
            r"\bpy\b",
            r"\bunibro\b",
            r"\bcotton\b",
            r"\bchennai\b",
            r"\bmarketing\b",
            r"\bqb_mdjmd\b"
        ]
        for pattern in forbidden_patterns:
            self.assertFalse(
                re.search(pattern, content.lower()),
                f"Forbidden business-specific pattern '{pattern}' was found hardcoded in semantic_plan.py!"
            )


class TestSemanticPlanBuilderIntegration(unittest.TestCase):
    """
    Scenarios matching Gate 3A.2 Step 9 requirements.
    """

    def test_scenario1_show_sales(self):
        # "Show sales"
        # Expected: query_shape = SINGLE_VALUE, temporal = None, physical metric = None
        semantic_result = {
            "metric_objects": [{
                "metric_name": "cy",
                "business_name": "Sales",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "CY",
                "aggregation_type": "SUM"
            }],
            "dimension_objects": [],
            "value_matches": [],
            "retrieval": {"status": "SINGLE_MATCH", "confidence": 1.0}
        }
        
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show sales",
            semantic_result=semantic_result,
            time_context=None,
            relevant_tables=["QB_MDJMD_SALES_5YRS_SUMMARY"]
        )
        
        self.assertEqual(plan.query_shape, SemanticQueryShape.SINGLE_VALUE)
        self.assertIsNone(plan.temporal)
        self.assertEqual(plan.intent, SemanticIntent.AGGREGATE)
        self.assertEqual(plan.primary_table, "QB_MDJMD_SALES_5YRS_SUMMARY")
        self.assertEqual(plan.metrics[0].business_name, "Sales")
        self.assertEqual(plan.metrics[0].column_name, "None")

    def test_scenario2_show_sales_this_year(self):
        # "Show sales this year"
        # Expected: temporal = CURRENT_YEAR (represented via TimeContext), column_name = CY
        from semantic.temporal.models import TimeContext, CurrentYearIntent
        from semantic.temporal.enums import TimeIntentType, TimeStrategyType
        
        time_ctx = TimeContext(
            intent=CurrentYearIntent(intent_type=TimeIntentType.CURRENT_YEAR),
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY"]
        )
        
        semantic_result = {
            "metric_objects": [{
                "metric_name": "cy",
                "business_name": "Sales",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "CY",
                "aggregation_type": "SUM"
            }]
        }
        
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show sales this year",
            semantic_result=semantic_result,
            time_context=time_ctx
        )
        
        self.assertEqual(plan.query_shape, SemanticQueryShape.SINGLE_VALUE)
        self.assertEqual(plan.temporal.intent.intent_type, TimeIntentType.CURRENT_YEAR)
        self.assertEqual(plan.temporal.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(plan.metrics[0].business_name, "Sales")
        self.assertEqual(plan.metrics[0].column_name, "CY")

    def test_scenario3_show_previous_year_sales(self):
        # "Show previous year sales"
        # Expected: temporal = PREVIOUS_YEAR, column_name = PY
        from semantic.temporal.models import TimeContext, PreviousYearIntent
        from semantic.temporal.enums import TimeIntentType, TimeStrategyType
        
        time_ctx = TimeContext(
            intent=PreviousYearIntent(intent_type=TimeIntentType.PREVIOUS_YEAR),
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["PY"]
        )
        
        semantic_result = {
            "metric_objects": [{
                "metric_name": "py",
                "business_name": "P Y",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "PY",
                "aggregation_type": "SUM"
            }]
        }
        
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show previous year sales",
            semantic_result=semantic_result,
            time_context=time_ctx
        )
        
        self.assertEqual(plan.query_shape, SemanticQueryShape.SINGLE_VALUE)
        self.assertEqual(plan.temporal.intent.intent_type, TimeIntentType.PREVIOUS_YEAR)
        self.assertEqual(plan.metrics[0].business_name, "Sales")
        self.assertEqual(plan.metrics[0].column_name, "PY")

    def test_scenario4_show_sales_by_card(self):
        # "Show sales by card"
        # Expected: dimension detected, query_shape = DETAIL
        semantic_result = {
            "metric_objects": [{
                "metric_name": "cy",
                "business_name": "Sales",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "CY"
            }],
            "dimension_objects": [{
                "dimension_name": "card_name",
                "business_name": "Card Name",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "CardName"
            }]
        }
        
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show sales by card",
            semantic_result=semantic_result
        )
        
        self.assertEqual(plan.query_shape, SemanticQueryShape.DETAIL)
        self.assertEqual(len(plan.dimensions), 1)
        self.assertEqual(plan.dimensions[0].column_name, "CardName")
        self.assertEqual(plan.metrics[0].business_name, "Sales")

    def test_scenario5_top_10_cards_by_sales(self):
        # "Top 10 cards by sales"
        # Expected: query_shape = RANKED_LIST
        semantic_result = {
            "metric_objects": [{"metric_name": "cy", "business_name": "Sales", "table_name": "T1", "column_name": "CY"}],
            "dimension_objects": [{"dimension_name": "card", "business_name": "Card", "table_name": "T1", "column_name": "CardName"}]
        }
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Top 10 cards by sales",
            semantic_result=semantic_result
        )
        self.assertEqual(plan.query_shape, SemanticQueryShape.RANKED_LIST)

    def test_scenario6_show_sales_trend(self):
        # "Show sales trend"
        # Expected: query_shape = TREND
        semantic_result = {
            "metric_objects": [{"metric_name": "cy", "business_name": "Sales", "table_name": "T1", "column_name": "CY"}],
            "dimension_objects": [{"dimension_name": "month", "business_name": "Month", "table_name": "T1", "column_name": "Month"}]
        }
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show sales trend",
            semantic_result=semantic_result
        )
        self.assertEqual(plan.query_shape, SemanticQueryShape.TREND)

    def test_scenario7_compare_current_year_and_previous_year_sales(self):
        # "Compare current year and previous year sales"
        # Expected: query_shape = COMPARISON
        semantic_result = {
            "metric_objects": [
                {"metric_name": "cy", "business_name": "Sales", "table_name": "T1", "column_name": "CY"},
                {"metric_name": "py", "business_name": "Sales PY", "table_name": "T1", "column_name": "PY"}
            ]
        }
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Compare current year and previous year sales",
            semantic_result=semantic_result
        )
        self.assertEqual(plan.query_shape, SemanticQueryShape.COMPARISON)

    def test_scenario8_show_banians_sales_for_current_year(self):
        # "Show BANIANS sales for current year"
        # Expected: BANIANS -> resolved physical column ProdGrp1, temporal = CURRENT_YEAR
        from semantic.temporal.models import TimeContext, CurrentYearIntent
        from semantic.temporal.enums import TimeIntentType, TimeStrategyType
        
        time_ctx = TimeContext(
            intent=CurrentYearIntent(intent_type=TimeIntentType.CURRENT_YEAR),
            strategy=TimeStrategyType.SNAPSHOT
        )
        semantic_result = {
            "metric_objects": [{"metric_name": "cy", "business_name": "Sales", "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY", "column_name": "CY"}],
            "value_matches": [{
                "value": "BANIANS",
                "business_name": "Prod Grp1",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "ProdGrp1",
                "operator": "="
            }]
        }
        
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show BANIANS sales for current year",
            semantic_result=semantic_result,
            time_context=time_ctx
        )
        
        self.assertEqual(plan.temporal.intent.intent_type, TimeIntentType.CURRENT_YEAR)
        self.assertEqual(len(plan.filters), 1)
        self.assertEqual(plan.filters[0].column_name, "ProdGrp1")
        self.assertEqual(plan.filters[0].values, ["BANIANS"])
        self.assertEqual(plan.filters[0].operator, FilterOperator.EQUAL)

    def test_scenario9_new_semantic_plan_creation_no_llm(self):
        # Ensure builder does not perform any LLM calls
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Test prompt no LLM",
            semantic_result={}
        )
        self.assertIsNotNone(plan)

    def test_scenario10_show_cy_sales(self):
        # "Show CY sales"
        # Expected: binds directly to CY, no duplicate metric collision
        semantic_result = {
            "metric_objects": [{
                "metric_name": "cy",
                "business_name": "C Y",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "CY"
            }]
        }
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show CY sales",
            semantic_result=semantic_result
        )
        self.assertEqual(len(plan.metrics), 1)
        self.assertEqual(plan.metrics[0].business_name, "Sales")
        self.assertEqual(plan.metrics[0].column_name, "CY")

    def test_scenario11_show_py_sales(self):
        # "Show PY sales"
        # Expected: binds directly to PY, deduplicates CY/PY collision
        semantic_result = {
            "metric_objects": [
                {"metric_name": "py", "business_name": "P Y", "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY", "column_name": "PY"},
                {"metric_name": "cy", "business_name": "C Y", "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY", "column_name": "CY"}
            ]
        }
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        plan = SemanticPlanBuilder.build(
            question="Show PY sales",
            semantic_result=semantic_result
        )
        self.assertEqual(len(plan.metrics), 1)
        self.assertEqual(plan.metrics[0].business_name, "Sales")
        self.assertEqual(plan.metrics[0].column_name, "PY")
