import re
from typing import List, Optional, Any
from semantic.models.semantic_plan import (
    SemanticPlan,
    SemanticIntent,
    SemanticQueryShape,
    AnalysisMode,
    RankDirection,
    SemanticOutput,
    SemanticRanking,
    MODE_FROM_INTENT,
    MODE_FROM_QUERY_SHAPE,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_OUTPUT_FROM_SHAPE,
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

# SNAPSHOT_SALES_BINDINGS used to live here: five column names, one customer's
# table, hardcoded into the query planner. It is now read from
# semantic_snapshot_mapping through SnapshotConfigLoader (Gate 2 Step 11a).
# The pre-configuration values survive as the documented fallback in
# semantic/temporal/snapshot_config.py, used only by a caller with no
# connection or no configuration.


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

    # Whole-word cues for shape classification.
    #
    # These were previously plain substring tests, which matched keywords hidden
    # inside longer words: "stopped" and "laptop" both contain "top", so both were
    # classified as ranking questions. Word forms are listed explicitly rather than
    # using a stem-plus-wildcard, because "rank" must still catch "ranking" while
    # "top" must NOT catch "topic".
    _RANKING_CUES = re.compile(
        r"\b(top|highest|lowest|best|worst|rank|ranks|ranked|ranking|limit)\b"
    )
    _COMPARISON_CUES = re.compile(
        r"\b(compare|compares|compared|comparison)\b"
    )
    _TREND_CUES = re.compile(
        r"\b(trend|trends|trending)\b|\bover\s+time\b"
    )

    @staticmethod
    def classify_query_shape(
        question: str,
        metrics: List[Any],
        dimensions: List[Any],
        time_ctx: Optional[TimeContext]
    ) -> SemanticQueryShape:
        q = question.lower()

        # 1. COMPARISON
        if (time_ctx and time_ctx.comparison) or SemanticPlanBuilder._COMPARISON_CUES.search(q) or len(metrics) > 1:
            return SemanticQueryShape.COMPARISON

        # 2. RANKED_LIST
        if SemanticPlanBuilder._RANKING_CUES.search(q):
            return SemanticQueryShape.RANKED_LIST

        # 3. TREND
        if SemanticPlanBuilder._TREND_CUES.search(q) or (time_ctx and time_ctx.grouping and SemanticPlanBuilder._is_explicit_temporal_breakdown(question)):
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

        # Gate 1 step 6: record decisions the builder makes on the user's behalf.
        # These choices already happened; they were simply invisible until now.
        assumptions: list[str] = []

        metric_objs = semantic_result.get("metric_objects", [])
        dimension_objs = semantic_result.get("dimension_objects", [])
        value_matches = semantic_result.get("value_matches", [])
        retrieval = semantic_result.get("retrieval", {})

        # Which table holds period-per-column measures, and which columns they
        # are, both come from configuration now.
        #
        # Gate 3 Step 7a - resolved for the table this plan's own metric sits
        # on. The previous call asked for_connection(), whose loader settles the
        # question with SELECT TOP 1 ... ORDER BY table_name, so one SNAPSHOT
        # table per connection won alphabetically and a metric on any other one
        # was measured against the wrong table's period columns.
        #
        # A table that is not configured SNAPSHOT comes back unconfigured, which
        # leaves sales_table None and sales_columns empty, so the snapshot
        # branch below is skipped entirely - correct for a table whose periods
        # are rows rather than columns.
        from semantic.temporal.snapshot_config import SnapshotConfig, SnapshotConfigLoader

        snapshot_config = SnapshotConfig()
        sales_table = None

        for m in metric_objs:
            if not isinstance(m, dict):
                continue
            candidate_table = m.get("table_name")
            if not candidate_table or candidate_table == sales_table:
                continue
            candidate_config = SnapshotConfigLoader.for_table(
                connection_id, candidate_table
            )
            if candidate_config.is_configured:
                snapshot_config = candidate_config
                sales_table = candidate_table
                break

        if sales_table is None:
            # No metric sits on a configured snapshot table - which is also the
            # case when there is no connection at all, or the connection has
            # never been configured. Fall back to the connection-wide answer,
            # exactly as this code did before Step 7a, so an unconfigured
            # environment keeps working and the fallback stays visible on the
            # plan. Where a metric DID resolve per table, that precise
            # configuration is used and this branch never runs.
            snapshot_config = SnapshotConfigLoader.for_connection(connection_id)
            sales_table = snapshot_config.table_name

            if not snapshot_config.is_configured:
                # Said out loud rather than assumed. A plan built on the
                # fallback bindings is built on one customer's column names,
                # and a reviewer reading the plan should be able to see that.
                assumptions.append(
                    "No snapshot configuration was found for this connection, "
                    "so the pre-configuration column bindings were used."
                )

        has_sales = False
        sales_columns = snapshot_config.resolvable_columns

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
                    offset = {
                        "this year": 0,
                        "last year": 1,
                        "2 years ago": 2,
                        "3 years ago": 3,
                        "4 years ago": 4,
                    }.get(val_lower)

                    if offset is not None:
                        column = snapshot_config.column_for_offset(offset)
                        if column:
                            resolved_cols.append(column)

            if not resolved_cols:
                if has_cy_word:
                    resolved_cols.append(snapshot_config.column_for_offset(0))
                elif has_py_word:
                    resolved_cols.append(snapshot_config.column_for_offset(1))
                elif time_context:
                    from semantic.temporal.enums import TimeIntentType
                    intent_type = getattr(time_context.intent, "intent_type", None)
                    intent_cls = time_context.intent.__class__.__name__ if time_context.intent else ""

                    if intent_type in (TimeIntentType.YEAR_COMPARISON, "YEAR_COMPARISON") or intent_cls == "YearComparisonIntent":
                        # Step 11b: the current year is part-finished, so last
                        # year resolves to its to-date column. CY against PY
                        # reads as a 63% collapse; CY against PYTD is 14.5%
                        # growth, and that is the honest answer.
                        comparison_cols, comparison_warnings = (
                            snapshot_config.comparison_columns([0, 1])
                        )

                        if comparison_cols:
                            resolved_cols.extend(comparison_cols)
                            assumptions.extend(comparison_warnings)
                        else:
                            resolved_cols.extend([
                                snapshot_config.column_for_offset(0),
                                snapshot_config.column_for_offset(1),
                            ])
                    elif intent_type in (TimeIntentType.CURRENT_YEAR, "CURRENT_YEAR") or intent_cls == "CurrentYearIntent":
                        resolved_cols.append(snapshot_config.column_for_offset(0))
                    elif intent_type in (TimeIntentType.PREVIOUS_YEAR, "PREVIOUS_YEAR") or intent_cls == "PreviousYearIntent":
                        resolved_cols.append(snapshot_config.column_for_offset(1))
                    elif intent_type == "PPY" or intent_cls == "PPY" or intent_type == "PPYIntent" or intent_cls == "PPYIntent":
                        resolved_cols.append(snapshot_config.column_for_offset(2))
                    elif intent_type == "PPPY" or intent_cls == "PPPY" or intent_type == "PPPYIntent" or intent_cls == "PPPYIntent":
                        resolved_cols.append(snapshot_config.column_for_offset(3))
                    elif intent_type == "PPPPY" or intent_cls == "PPPPY" or intent_type == "PPPPYIntent" or intent_cls == "PPPPYIntent":
                        resolved_cols.append(snapshot_config.column_for_offset(4))
                    elif time_context.snapshot_columns:
                        resolved_cols.extend(time_context.snapshot_columns)
                    else:
                        resolved_cols.append("None")
                        assumptions.append(
                            "No time period could be determined for Sales; "
                            "the period was left unresolved."
                        )
                else:
                    resolved_cols.append("None")
                    assumptions.append(
                        "No time period was stated for Sales and none could be "
                        "inferred; the period was left unresolved."
                    )

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
        dropped_time_dims: list[str] = []
        for d in dimension_objs:
            if isinstance(d, dict):
                # Filter out temporal dimensions if not an explicit breakdown
                if cls._is_temporal_dimension(d) and not is_breakdown:
                    dropped_time_dims.append(
                        d.get("business_name") or d.get("dimension_name") or "a time dimension"
                    )
                    continue
                plan_dims.append(SemanticDimension(
                    dimension_name=d.get("dimension_name") or d.get("business_name") or "",
                    business_name=d.get("business_name") or d.get("dimension_name") or "",
                    table_name=d.get("table_name") or "",
                    column_name=d.get("column_name") or "",
                    semantic_category=d.get("semantic_category"),
                    connection_id=connection_id,
                    dimension_role=d.get("dimension_role")
                ))

        if dropped_time_dims:
            assumptions.append(
                "Question did not ask for a breakdown over time, so "
                + ", ".join(sorted(set(dropped_time_dims)))
                + " was not used as a grouping."
            )

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

        # 9. Gate 1 step 6 - derive the new plan fields from what is already known.
        # Translation and lookup only: no new detection happens here. Reading a
        # top-N count out of the question, spotting a benchmark, or identifying a
        # diagnostic question are all Gate 4 work, so ranking.top_n, benchmark and
        # diagnostic are deliberately left unset.
        # query_shape is the stronger signal and is tried first. The intent chain
        # above can only ever return five of SemanticIntent's nine values - it has
        # no branch producing RANKED_LIST, DISTRIBUTION, GROWTH or DEGROWTH - so
        # deriving mode from intent alone silently loses rankings.
        mode = MODE_FROM_QUERY_SHAPE.get(query_shape) if query_shape else None
        if mode is None and intent is not None:
            mode = MODE_FROM_INTENT.get(intent)

        # Output likewise prefers the shape, which distinguishes a single figure
        # from a breakdown; mode alone cannot.
        output_format = None
        if query_shape is not None:
            output_format = DEFAULT_OUTPUT_FROM_SHAPE.get(query_shape)
        if output_format is None and mode is not None:
            output_format = DEFAULT_OUTPUT_FORMAT.get(mode)
        output = SemanticOutput(output_format=output_format) if output_format else None

        # Direction is inferable from the wording the shape classifier already
        # matched; the count is not, so top_n stays None until Gate 4.
        ranking = None
        if mode == AnalysisMode.RANKING:
            q_lower = question.lower()
            if any(w in q_lower for w in ("lowest", "bottom", "worst", "least")):
                direction = RankDirection.ASC
            else:
                direction = RankDirection.DESC
            ranking = SemanticRanking(direction=direction)

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
            confidence=plan_confidence,
            mode=mode,
            output=output,
            ranking=ranking,
            assumptions_made=assumptions
        )
        cls._thread_local.last_plan = plan
        return plan
