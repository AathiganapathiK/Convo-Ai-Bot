from typing import List, Optional, Any
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
from semantic.temporal.models import TimeContext


import threading

SNAPSHOT_SALES_BINDINGS = {
    "CURRENT_YEAR": "CY",
    "PREVIOUS_YEAR": "PY",
    "PPY": "PPY",
    "PPPY": "PPPY",
    "PPPPY": "PPPPY",
}


class SemanticPlanBuilder:
    _thread_local = threading.local()

    @classmethod
    def get_last_plan(cls) -> Optional[SemanticPlan]:
        return getattr(cls._thread_local, "last_plan", None)

    @classmethod
    def clear_last_plan(cls):
        cls._thread_local.last_plan = None

    @staticmethod
    def _is_explicit_temporal_breakdown(question: str) -> bool:
        q = question.lower()
        # Look for explicit breakdown keywords
        keywords = [
            "monthly", "weekly", "daily", "yearly", "quarterly", "hourly",
            "month wise", "month-wise", "year wise", "year-wise", "date wise", "date-wise",
            "day wise", "day-wise", "quarter wise", "quarter-wise", "week wise", "week-wise",
            "trend"
        ]
        if any(kw in q for kw in keywords):
            return True
        
        # Look for "by <time_unit>"
        import re
        if re.search(r"\bby\s+(month|year|week|day|quarter|date|hour|createddate|docdate)\b", q):
            return True
            
        return False

    @staticmethod
    def _is_temporal_dimension(dim: Any) -> bool:
        if isinstance(dim, dict):
            category = (dim.get("semantic_category") or "").upper()
            col = (dim.get("column_name") or "").lower()
            bname = (dim.get("business_name") or dim.get("dimension_name") or "").lower()
        else:
            category = (dim.semantic_category or "").upper()
            col = (dim.column_name or "").lower()
            bname = (dim.business_name or dim.dimension_name or "").lower()
            
        if category.startswith("TIME_") or category == "TIME":
            return True
        if col in {"createddate", "docdate", "orderdate", "shipdate", "due_date"}:
            return True
        if any(term in bname for term in ["year", "month", "day", "quarter", "week", "date", "time"]):
            return True
        return False

    @staticmethod
    def classify_query_shape(
        question: str,
        metrics: List[Any],
        dimensions: List[Any],
        time_ctx: Optional[TimeContext]
    ) -> SemanticQueryShape:
        q = question.lower()

        # 1. COMPARISON
        if (time_ctx and time_ctx.comparison) or "compare" in q or "comparison" in q or len(metrics) > 1:
            return SemanticQueryShape.COMPARISON

        # 2. RANKED_LIST
        if any(w in q for w in ["top", "limit", "highest", "lowest", "best", "worst", "rank"]):
            return SemanticQueryShape.RANKED_LIST

        # 3. TREND
        if "trend" in q or "over time" in q or (time_ctx and time_ctx.grouping and SemanticPlanBuilder._is_explicit_temporal_breakdown(question)):
            return SemanticQueryShape.TREND

        # 4. DETAIL (when dimensions exist)
        if dimensions:
            return SemanticQueryShape.DETAIL

        # 5. SINGLE_VALUE (when only metrics exist)
        if metrics:
            return SemanticQueryShape.SINGLE_VALUE

        return SemanticQueryShape.DETAIL

    @classmethod
    def build(
        cls,
        question: str,
        semantic_result: Optional[dict] = None,
        time_context: Optional[TimeContext] = None,
        relevant_tables: Optional[List[str]] = None,
        connection_id: Optional[str] = None,
        clarified_candidate: Optional[dict] = None
    ) -> SemanticPlan:
        if semantic_result is None:
            semantic_result = {}

        metric_objs = semantic_result.get("metric_objects", [])
        dimension_objs = semantic_result.get("dimension_objects", [])
        value_matches = semantic_result.get("value_matches", [])
        retrieval = semantic_result.get("retrieval", {})

        # Check if the query has any sales metrics
        has_sales = False
        sales_table = "QB_MDJMD_SALES_5YRS_SUMMARY"
        sales_columns = {"CY", "PY", "PPY", "PPPY", "PPPPY", "CYQ", "PYQ", "PPYQ", "PPPYQ", "PPPPYQ"}

        # Collect non-sales metrics normally
        other_metrics = []
        for m in metric_objs:
            if isinstance(m, dict):
                col = m.get("column_name")
                tbl = m.get("table_name")
                if tbl == sales_table and col in sales_columns:
                    has_sales = True
                else:
                    other_metrics.append(m)

        # 1. Build metrics
        plan_metrics = []
        for m in other_metrics:
            plan_metrics.append(SemanticMetric(
                metric_name=m.get("metric_name") or m.get("business_name") or "",
                business_name=m.get("business_name") or m.get("metric_name") or "",
                table_name=m.get("table_name") or "",
                column_name=m.get("column_name") or "",
                aggregation_type=m.get("aggregation_type"),
                connection_id=connection_id
            ))

        if has_sales:
            # Determine column bindings
            q_lower = question.lower()
            import re
            has_cy_word = bool(re.search(r"\bcy\b", q_lower))
            has_py_word = bool(re.search(r"\bpy\b", q_lower))

            resolved_cols = []

            # Check if this is a clarification resume
            candidates_list = clarified_candidate if isinstance(clarified_candidate, list) else [clarified_candidate] if clarified_candidate else []
            for cand in candidates_list:
                if isinstance(cand, dict):
                    val = cand.get("value")
                    val_lower = val.lower() if val else ""
                    if val_lower == "this year":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["CURRENT_YEAR"])
                    elif val_lower == "last year":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PREVIOUS_YEAR"])
                    elif val_lower == "2 years ago":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PPY"])
                    elif val_lower == "3 years ago":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PPPY"])
                    elif val_lower == "4 years ago":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PPPPY"])

            if not resolved_cols:
                if has_cy_word:
                    resolved_cols.append(SNAPSHOT_SALES_BINDINGS["CURRENT_YEAR"])
                elif has_py_word:
                    resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PREVIOUS_YEAR"])
                elif time_context:
                    from semantic.temporal.enums import TimeIntentType
                    intent_type = getattr(time_context.intent, "intent_type", None)
                    intent_cls = time_context.intent.__class__.__name__ if time_context.intent else ""

                    if intent_type in (TimeIntentType.YEAR_COMPARISON, "YEAR_COMPARISON") or intent_cls == "YearComparisonIntent":
                        resolved_cols.extend([SNAPSHOT_SALES_BINDINGS["CURRENT_YEAR"], SNAPSHOT_SALES_BINDINGS["PREVIOUS_YEAR"]])
                    elif intent_type in (TimeIntentType.CURRENT_YEAR, "CURRENT_YEAR") or intent_cls == "CurrentYearIntent":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["CURRENT_YEAR"])
                    elif intent_type in (TimeIntentType.PREVIOUS_YEAR, "PREVIOUS_YEAR") or intent_cls == "PreviousYearIntent":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PREVIOUS_YEAR"])
                    elif intent_type == "PPY" or intent_cls == "PPY" or intent_type == "PPYIntent" or intent_cls == "PPYIntent":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PPY"])
                    elif intent_type == "PPPY" or intent_cls == "PPPY" or intent_type == "PPPYIntent" or intent_cls == "PPPYIntent":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PPPY"])
                    elif intent_type == "PPPPY" or intent_cls == "PPPPY" or intent_type == "PPPPYIntent" or intent_cls == "PPPPYIntent":
                        resolved_cols.append(SNAPSHOT_SALES_BINDINGS["PPPPY"])
                    elif time_context.snapshot_columns:
                        resolved_cols.extend(time_context.snapshot_columns)
                    else:
                        resolved_cols.append("None")
                else:
                    resolved_cols.append("None")

            for col in resolved_cols:
                plan_metrics.append(SemanticMetric(
                    metric_name="sales",
                    business_name="Sales",
                    table_name=sales_table,
                    column_name=col,
                    aggregation_type="SUM",
                    connection_id=connection_id
                ))

        # 2. Build dimensions
        plan_dims = []
        is_breakdown = cls._is_explicit_temporal_breakdown(question)
        for d in dimension_objs:
            if isinstance(d, dict):
                # Filter out temporal dimensions if not an explicit breakdown
                if cls._is_temporal_dimension(d) and not is_breakdown:
                    continue
                plan_dims.append(SemanticDimension(
                    dimension_name=d.get("dimension_name") or d.get("business_name") or "",
                    business_name=d.get("business_name") or d.get("dimension_name") or "",
                    table_name=d.get("table_name") or "",
                    column_name=d.get("column_name") or "",
                    semantic_category=d.get("semantic_category"),
                    connection_id=connection_id
                ))

        # 3. Build filters
        plan_filters = []
        for v in value_matches:
            if isinstance(v, dict):
                operator_str = v.get("operator", "=")
                try:
                    operator = FilterOperator(operator_str)
                except ValueError:
                    operator = FilterOperator.EQUAL

                dim_name = v.get("business_name") or v.get("dimension") or v.get("dimension_name") or ""
                plan_filters.append(SemanticFilter(
                    dimension_name=dim_name,
                    table_name=v.get("table_name") or "",
                    column_name=v.get("column_name") or "",
                    operator=operator,
                    values=[v.get("value")]
                ))

        # 4. Build tables
        plan_tables = []
        if relevant_tables:
            for tname in relevant_tables:
                plan_tables.append(SemanticTable(
                    table_name=tname
                ))
        primary_table = relevant_tables[0] if relevant_tables else None

        # 5. Build joins
        plan_joins = []
        try:
            from semantic.relationship_service import SemanticRelationshipService
            if connection_id and relevant_tables and len(relevant_tables) > 1:
                all_relationships = SemanticRelationshipService.build_relationships(connection_id)
                resolved_set = set(relevant_tables)
                for rel in all_relationships:
                    if rel[0] in resolved_set and rel[2] in resolved_set:
                        plan_joins.append(SemanticJoin(
                            source_table=rel[0],
                            source_key=rel[1],
                            target_table=rel[2],
                            target_key=rel[3]
                        ))
        except Exception:
            pass

        # 6. Build confidence
        plan_confidence = None
        if retrieval:
            plan_confidence = SemanticPlanConfidence(
                status=retrieval.get("status", "Unknown"),
                confidence=float(retrieval.get("confidence", 1.0)),
                reason=retrieval.get("reason")
            )

        # 7. Map semantic intent
        intent = None
        if time_context and time_context.comparison:
            intent = SemanticIntent.COMPARISON
        elif "trend" in question.lower():
            intent = SemanticIntent.TREND
        elif plan_metrics:
            intent = SemanticIntent.AGGREGATE
        elif plan_dims:
            intent = SemanticIntent.DETAIL
        else:
            intent = SemanticIntent.LOOKUP

        # 8. Classify query shape
        query_shape = cls.classify_query_shape(question, plan_metrics, plan_dims, time_context)

        plan = SemanticPlan(
            intent=intent,
            metrics=plan_metrics,
            dimensions=plan_dims,
            filters=plan_filters,
            temporal=time_context,
            query_shape=query_shape,
            primary_table=primary_table,
            relevant_tables=plan_tables,
            joins=plan_joins,
            confidence=plan_confidence
        )
        cls._thread_local.last_plan = plan
        return plan
