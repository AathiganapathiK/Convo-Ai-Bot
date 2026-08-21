# TEMP_PIPELINE_TRACE_REMOVE_LATER
import time
import threading
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("PipelineDiagnosticTracer")


class PipelineDiagnosticTracer:
    """
    TEMP_PIPELINE_TRACE_REMOVE_LATER
    Temporary final backend pipeline diagnostic tracer.
    Collects diagnostic metadata and timings during request lifecycle,
    and prints ONE consolidated diagnostic block AFTER existing backend output.
    """

    _local = threading.local()

    @classmethod
    def start_trace(cls, question: str, session_id: Optional[int] = None, connection_id: Optional[str] = None):
        cls._local.data = {
            "question": question,
            "session_id": session_id,
            "connection_id": connection_id,
            "start_time": time.monotonic(),
            "timings": {},
            "clarification": {
                "required": "NO",
                "candidate_count": 0,
                "selected_candidate": None,
                "selected_value": None,
                "selected_dimension": None,
                "selected_column": None
            },
            "semantic": {
                "intent": "<not available>",
                "metric": "<not available>",
                "physical_metric": "<not available>",
                "aggregation": "<not available>",
                "query_shape": "<not available>",
                "business_domain": "<not available>"
            },
            "temporal": {
                "detected": "NO",
                "intent": "<not available>",
                "strategy": "<not available>",
                "granularity": "<not available>",
                "start_date": "<not available>",
                "end_date": "<not available>",
                "snapshot_strategy": "<not available>",
                "snapshot_columns": []
            },
            "filters": [],
            "table": {
                "primary": "<not available>",
                "relevant_tables": [],
                "connection_id": connection_id or "<not available>",
                "join_plan": "<not available>"
            },
            "sql": {
                "generated": "<not available>",
                "validated": "<not available>",
                "executed": "<not available>"
            },
            "result": {
                "row_count": 0,
                "column_count": 0,
                "result_status": "<not available>",
                "is_empty": "YES"
            },
            "context": {
                "inherited_filters": "NONE",
                "reset_filters": "NONE",
                "inherited_metric": "NONE",
                "inherited_dimension": "NONE",
                "inherited_temporal": "NONE",
                "context_status": "FRESH_QUERY"
            }
        }

    @classmethod
    def get_data(cls) -> Optional[Dict[str, Any]]:
        return getattr(cls._local, "data", None)

    @classmethod
    def record_timing(cls, stage: str, elapsed_sec: float):
        data = cls.get_data()
        if data is not None:
            ms = round(elapsed_sec * 1000, 2)
            data["timings"][stage] = ms

    @classmethod
    def record_clarification(
        cls,
        required: bool,
        candidate_count: int = 0,
        selected_candidate: Optional[Dict[str, Any]] = None
    ):
        data = cls.get_data()
        if data is not None:
            clar = data["clarification"]
            clar["required"] = "YES" if required else "NO"
            clar["candidate_count"] = candidate_count
            if selected_candidate and isinstance(selected_candidate, dict):
                clar["selected_candidate"] = selected_candidate.get("value") or selected_candidate.get("business_name")
                clar["selected_value"] = selected_candidate.get("value")
                clar["selected_dimension"] = selected_candidate.get("dimension") or selected_candidate.get("business_name")
                clar["selected_column"] = selected_candidate.get("column_name")

    @classmethod
    def record_semantic(cls, semantic_result: Dict[str, Any]):
        data = cls.get_data()
        if data is None or not isinstance(semantic_result, dict):
            return

        sem = data["semantic"]
        metric_objs = semantic_result.get("metric_objects", [])
        if metric_objs and isinstance(metric_objs, list):
            first_m = metric_objs[0]
            if isinstance(first_m, dict):
                sem["metric"] = first_m.get("business_name") or first_m.get("metric_name", "<not available>")
                sem["physical_metric"] = first_m.get("column_name", "<not available>")
                sem["aggregation"] = first_m.get("aggregation_type", "<not available>")

        dimension_objs = semantic_result.get("dimension_objects", [])
        if dimension_objs and isinstance(dimension_objs, list):
            sem["intent"] = "AGGREGATE" if metric_objs else "DIMENSION_LIST"
            sem["query_shape"] = "BREAKDOWN" if len(dimension_objs) == 1 else "MULTI_DIMENSION"
        elif metric_objs:
            sem["intent"] = "AGGREGATE"
            sem["query_shape"] = "SINGLE_VALUE"
        else:
            sem["intent"] = "GENERAL_QUERY"
            sem["query_shape"] = "UNKNOWN"

        # Record filters
        value_matches = semantic_result.get("value_matches", [])
        if value_matches and isinstance(value_matches, list):
            filters_list = []
            for v in value_matches:
                if isinstance(v, dict):
                    provenance = v.get("provenance", "EXPLICIT_THIS_TURN")
                    filters_list.append({
                        "dimension": v.get("business_name") or v.get("dimension", "<not available>"),
                        "table": v.get("table_name", "<not available>"),
                        "column": v.get("column_name", "<not available>"),
                        "operator": v.get("operator", "="),
                        "value": v.get("value", "<not available>"),
                        "provenance": provenance
                    })
            data["filters"] = filters_list

        # Record table
        tbl = data["table"]
        resolved_tables = set()
        for m in metric_objs:
            if isinstance(m, dict) and m.get("table_name"):
                resolved_tables.add(m["table_name"])
        for d in dimension_objs:
            if isinstance(d, dict) and d.get("table_name"):
                resolved_tables.add(d["table_name"])
        for v in value_matches:
            if isinstance(v, dict) and v.get("table_name"):
                resolved_tables.add(v["table_name"])

        if resolved_tables:
            sorted_tbls = sorted(list(resolved_tables))
            tbl["primary"] = sorted_tbls[0]
            tbl["relevant_tables"] = sorted_tbls

    @classmethod
    def record_semantic_plan(cls, semantic_plan):
        data = cls.get_data()
        if data is None or not semantic_plan:
            return
        
        metrics_details = []
        for m in semantic_plan.metrics:
            metrics_details.append(f"{m.business_name} ({m.table_name}.{m.column_name} as {m.aggregation_type or 'None'})")
            
        dimensions_details = []
        for d in semantic_plan.dimensions:
            dimensions_details.append(f"{d.business_name} ({d.table_name}.{d.column_name})")
            
        filters_details = []
        for f in semantic_plan.filters:
            filters_details.append(f"{f.dimension_name} ({f.table_name}.{f.column_name}) {f.operator.value} {f.values}")
            
        temp_intent = semantic_plan.temporal.intent.__class__.__name__ if (semantic_plan.temporal and semantic_plan.temporal.intent) else "<not available>"
        temp_strategy = semantic_plan.temporal.strategy.value if (semantic_plan.temporal and semantic_plan.temporal.strategy) else "<not available>"
        
        data["semantic_plan_trace"] = {
            "intent": str(semantic_plan.intent.value if semantic_plan.intent else "None"),
            "metrics": metrics_details,
            "aggregation": ", ".join(set(m.aggregation_type for m in semantic_plan.metrics if m.aggregation_type)),
            "temporal_intent": temp_intent,
            "temporal_strategy": temp_strategy,
            "physical_metrics": ", ".join(m.column_name for m in semantic_plan.metrics),
            "dimensions": dimensions_details,
            "value_filters": filters_details,
            "selected_table": str(semantic_plan.primary_table),
            "query_shape": str(semantic_plan.query_shape.value if semantic_plan.query_shape else "None")
        }

    @classmethod
    def record_temporal(cls):
        data = cls.get_data()
        if data is None:
            return

        try:
            from semantic.temporal.pipeline import TemporalPipeline
            last_res = TemporalPipeline.get_last_resolution()
            last_intent = TemporalPipeline.get_last_intent()

            temp = data["temporal"]
            if last_intent or (last_res and last_res.resolved):
                temp["detected"] = "YES"
                if last_intent:
                    temp["intent"] = last_intent.__class__.__name__.replace("Intent", "").upper()
                if last_res and last_res.plan:
                    plan = last_res.plan
                    temp["strategy"] = plan.strategy.value if plan.strategy else "<not available>"
                    temp["snapshot_strategy"] = plan.strategy.value if plan.strategy else "<not available>"
                    temp["snapshot_columns"] = plan.snapshot_columns or []
                    if plan.start_date:
                        temp["start_date"] = str(plan.start_date)
                    if plan.end_date:
                        temp["end_date"] = str(plan.end_date)
                    if plan.grouping:
                        temp["granularity"] = plan.grouping.value if hasattr(plan.grouping, "value") else str(plan.grouping)
            else:
                temp["detected"] = "NO"
        except Exception as e:
            logger.debug(f"Tracer record_temporal error: {e}")

    @classmethod
    def record_sql(cls, stage: str, sql_text: str):
        data = cls.get_data()
        if data is not None and isinstance(sql_text, str):
            data["sql"][stage] = sql_text

    @classmethod
    def record_result(cls, row_count: int, col_count: int = 0, status: str = "SUCCESS"):
        data = cls.get_data()
        if data is not None:
            res = data["result"]
            res["row_count"] = row_count
            res["column_count"] = col_count
            res["result_status"] = status
            res["is_empty"] = "YES" if row_count == 0 else "NO"

    @classmethod
    def record_memory(cls, source: str, count: int):
        data = cls.get_data()
        if data is not None:
            if "context" not in data:
                data["context"] = {}
            data["context"]["memory_source"] = source
            data["context"]["hydrated_count"] = count

    @classmethod
    def record_context(cls, history: List[Dict[str, Any]]):
        data = cls.get_data()
        if data is None:
            return
        if "context" not in data:
            data["context"] = {
                "inherited_filters": "NONE",
                "reset_filters": "NONE",
                "inherited_metric": "NONE",
                "inherited_dimension": "NONE",
                "inherited_temporal": "NONE",
                "context_status": "FRESH_QUERY"
            }
        ctx = data["context"]
        if history and isinstance(history, list) and len(history) > 0:
            ctx["context_status"] = "INHERITED_CONTEXT"
            last_turn = history[-1]
            if isinstance(last_turn, dict):
                sem_ctx = last_turn.get("semantic_context")
                if sem_ctx and isinstance(sem_ctx, dict):
                    if sem_ctx.get("resolved_values"):
                        vals = [v.get("value") for v in sem_ctx["resolved_values"] if isinstance(v, dict)]
                        ctx["inherited_filters"] = ", ".join(str(x) for x in vals) if vals else "NONE"
                    if sem_ctx.get("metrics"):
                        mets = [m.get("business_name") for m in sem_ctx["metrics"] if isinstance(m, dict)]
                        ctx["inherited_metric"] = ", ".join(str(x) for x in mets) if mets else "NONE"
                    if sem_ctx.get("dimensions"):
                        dims = [d.get("business_name") for d in sem_ctx["dimensions"] if isinstance(d, dict)]
                        ctx["inherited_dimension"] = ", ".join(str(x) for x in dims) if dims else "NONE"
        else:
            ctx["context_status"] = "FRESH_QUERY"

    @classmethod
    def print_final_trace(cls):
        data = cls.get_data()
        if not data:
            return

        try:
            total_sec = time.monotonic() - data["start_time"]
            total_ms = round(total_sec * 1000, 2)
            timings = data["timings"]

            print("\n================ TEMPORARY PIPELINE TRACE — REMOVE AFTER STABILIZATION ================\n")

            # 1. QUESTION
            print(f"QUESTION:\n{data['question']}\n")

            # 2. CLARIFICATION
            clar = data["clarification"]
            print("CLARIFICATION:")
            print(f"Required: {clar['required']}")
            if clar["required"] == "YES" or clar.get("selected_candidate"):
                print(f"Candidate Count: {clar.get('candidate_count', 0)}")
                print(f"Selected: {clar.get('selected_candidate', '<not available>')}")
                print(f"Value: {clar.get('selected_value', '<not available>')}")
                print(f"Dimension: {clar.get('selected_dimension', '<not available>')}")
                print(f"Column: {clar.get('selected_column', '<not available>')}")
            print("")

            # 3. SEMANTIC
            sem = data["semantic"]
            print("SEMANTIC:")
            print(f"Intent: {sem['intent']}")
            print(f"Metric: {sem['metric']}")
            print(f"Physical Metric: {sem['physical_metric']}")
            print(f"Aggregation: {sem['aggregation']}")
            print(f"Query Shape: {sem['query_shape']}")
            print(f"Business Domain: {sem['business_domain']}")
            print("")

            # 3A. SEMANTIC PLAN
            plan_trace = data.get("semantic_plan_trace")
            if plan_trace:
                print("SEMANTIC PLAN:")
                print(f"Intent: {plan_trace['intent']}")
                print(f"Metrics: {', '.join(plan_trace['metrics']) or 'None'}")
                print(f"Aggregation: {plan_trace['aggregation'] or 'None'}")
                print(f"Temporal Intent: {plan_trace['temporal_intent']}")
                print(f"Temporal Strategy: {plan_trace['temporal_strategy']}")
                print(f"Physical Metrics: {plan_trace['physical_metrics'] or 'None'}")
                print(f"Dimensions: {', '.join(plan_trace['dimensions']) or 'None'}")
                print(f"Value/Filter Bindings: {', '.join(plan_trace['value_filters']) or 'None'}")
                print(f"Selected Table: {plan_trace['selected_table']}")
                print(f"Query Shape: {plan_trace['query_shape']}")
                print("")

            # 4. TEMPORAL
            temp = data["temporal"]
            print("TEMPORAL:")
            print(f"Detected: {temp['detected']}")
            print(f"Intent: {temp['intent']}")
            print(f"Strategy: {temp['strategy']}")
            print(f"Granularity: {temp['granularity']}")
            print(f"Start: {temp['start_date']}")
            print(f"End: {temp['end_date']}")
            print(f"Snapshot Strategy: {temp['snapshot_strategy']}")
            print(f"Snapshot Columns: {temp['snapshot_columns']}")
            print("")

            # 5. VALUE / FILTER
            print("FILTERS:")
            filters = data.get("filters", [])
            if filters:
                for f in filters:
                    print(f"- {f['dimension']} ({f['table']}.{f['column']}) {f['operator']} '{f['value']}' [{f['provenance']}]")
            else:
                print("- NONE")
            print("")

            # 6. TABLE
            tbl = data["table"]
            print("TABLE:")
            print(f"Primary: {tbl['primary']}")
            print(f"Relevant Tables: {tbl['relevant_tables']}")
            print(f"Connection ID: {tbl['connection_id']}")
            print(f"Joins: {tbl['join_plan']}")
            print("")

            # 7. SQL
            sql_data = data["sql"]
            print("SQL:")
            print("Generated:")
            print(sql_data.get("generated", "<not available>"))
            print("\nValidated:")
            print(sql_data.get("validated", "<not available>"))
            print("\nExecuted:")
            print(sql_data.get("executed", "<not available>"))
            print("")

            # 8. RESULT
            res = data["result"]
            print("RESULT:")
            print(f"Rows: {res['row_count']}")
            print(f"Columns: {res['column_count']}")
            print(f"Status: {res['result_status']}")
            print(f"Empty: {res['is_empty']}")
            print("")

            # 9. CONTEXT
            ctx = data["context"]
            print("CONTEXT:")
            print(f"Status: {ctx['context_status']}")
            print(f"Inherited Filters: {ctx['inherited_filters']}")
            print(f"Reset Filters: {ctx['reset_filters']}")
            print(f"Inherited Metric: {ctx['inherited_metric']}")
            print(f"Inherited Dimension: {ctx['inherited_dimension']}")
            print(f"Inherited Temporal: {ctx['inherited_temporal']}")
            print("")

            # 10. PERFORMANCE TIMING
            print("TIMING:")
            print(f"Semantic: {timings.get('semantic', '<not available>')} ms")
            print(f"Temporal: {timings.get('temporal', '<not available>')} ms")
            print(f"Prompt: {timings.get('prompt', '<not available>')} ms")
            print(f"Examples: {timings.get('examples', '<not available>')} ms")
            print(f"Ollama/LLM: {timings.get('ollama', '<not available>')} ms")
            print(f"Validation: {timings.get('validation', '<not available>')} ms")
            print(f"SQL Execution: {timings.get('sql_execution', '<not available>')} ms")
            print(f"Summary: {timings.get('summary', '<not available>')} ms")
            print(f"TOTAL: {total_ms} ms")
            print("")

            print("================ END TEMPORARY PIPELINE TRACE ================\n")
        except Exception as ex:
            logger.error(f"Error printing temporary pipeline trace: {ex}")
