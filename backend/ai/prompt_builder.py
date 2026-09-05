import time
from pprint import pprint
from typing import Optional, Dict, Any, List
from core.exceptions import SemanticRetrievalException
from database import engine
from sqlalchemy import text

from services.schema_context_service import SchemaContextService
from services.connection_service import ConnectionService

from semantic.semantic_resolver import  SemanticResolver
from semantic.semantic_context_service import SemanticContextService
from semantic.discovery_service import SemanticDiscoveryService
from semantic.query_examples_service import QueryExamplesService
from semantic.relationship_context_service import RelationshipContextService
from semantic.relevant_table_resolver import RelevantTableResolver
from semantic.relevant_schema_service import RelevantSchemaService
from semantic.relationship_expander import RelationshipExpander
from semantic.runtime_context_builder import RuntimeContextBuilder
from semantic.semantic_gate import SemanticGate
from core.logger import debug_print as print

from semantic.temporal import TimeResolver, TimeContextBuilder, TemporalPromptFormatter, TimeSettings, TemporalPipeline
from semantic.execution_context import SemanticExecutionContext

def get_dynamic_business_context(connection_id: str, company_id: str) -> str:
    query = """
    SELECT st.table_name, sc.column_name
    FROM schema_tables st
    INNER JOIN schema_columns sc ON st.table_id = sc.table_id
    WHERE st.connection_id = :connection_id
      AND st.company_id = :company_id
      AND LOWER(st.table_name) NOT IN (
          'companies',
          'users',
          'roles',
          'permissions',
          'role_permissions',
          'user_roles',
          'chat_sessions',
          'chat_messages',    
          'schema_tables',
          'schema_columns',
          'schema_relationships',
          'schema_drift_events',
          'database_connections',
          'audit_logs',
          'user_queries',
          'user_usage',
          'user_data_access',
          'role_column_access',
          'semantic_metrics',
          'semantic_dimensions',
          'api_keys',
          'base_config',
          'drifttest',
          'llm_fallbacks',
          'llm_models',
          'llm_providers',
          'provider_health'
      )
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query), {"connection_id": connection_id, "company_id": company_id}).fetchall()
    except Exception:
        return ""

    context_lines = []
    seen_mappings = set()

    heuristics = [
        ("revenue / sales amount", ["salesamount", "sales_amount", "revenue", "linetotal", "line_total", "amount", "price"]),
        ("product cost", ["productcost", "product_cost", "cost", "expense"]),
        ("units sold / quantity", ["quantity", "qty", "units"]),
        ("unit price / selling price", ["unitprice", "unit_price"]),
        ("sales date / date", ["orderdate", "order_date", "date", "timestamp", "created_at"]),
        ("customer / reseller / buyer", ["customer", "reseller", "buyer", "client", "customer_id", "reseller_id"]),
        ("employee / salesperson / staff", ["employee", "salesperson", "sales_rep", "salesrep", "staff"]),
        ("region / territory / location", ["region", "territory", "location", "country", "state", "city"]),
        ("sales target / goal", ["target", "goal", "quota"])
    ]

    for row in rows:
        table_name = row[0]
        column_name = row[1]
        
        # Exclude technical and audit columns
        if SemanticDiscoveryService.is_technical_column(column_name):
            continue
            
        col_lower = column_name.lower()
        tbl_lower = table_name.lower()

        for concept, substrings in heuristics:
            for sub in substrings:
                if sub in col_lower:
                    mapping = f"{table_name}.{column_name} = {concept}"
                    if mapping not in seen_mappings:
                        context_lines.append(f"- {mapping}")
                        seen_mappings.add(mapping)
                    break
        
        # Also check table name match for generic mapping
        if "product" in tbl_lower and "name" in col_lower:
            mapping = f"{table_name}.{column_name} = product name"
            if mapping not in seen_mappings:
                context_lines.append(f"- {mapping}")
                seen_mappings.add(mapping)
        elif "customer" in tbl_lower and "name" in col_lower:
            mapping = f"{table_name}.{column_name} = customer name"
            if mapping not in seen_mappings:
                context_lines.append(f"- {mapping}")
                seen_mappings.add(mapping)

    if not context_lines:
        return ""

    return "Business Context:\n" + "\n".join(context_lines)


class PromptBuilder:
    def __init__(
        self,
        temporal_pipeline: Optional[TemporalPipeline] = None,
        time_resolver: Optional[TimeResolver] = None,
        context_builder: Optional[TimeContextBuilder] = None,
        temporal_formatter: Optional[TemporalPromptFormatter] = None
    ):
        if temporal_pipeline:
            self.temporal_pipeline = temporal_pipeline
        else:
            self.temporal_pipeline = TemporalPipeline(
                time_resolver=time_resolver,
                context_builder=context_builder,
                temporal_formatter=temporal_formatter
            )

    # Words that turn "last year" into "last year to date". Kept here beside
    # the only code that reads them; the periods themselves come from config.
    _TO_DATE_MARKERS = ("till date", "til date", "to date", "todate",
                        "ytd", "lytd", "pytd", "so far", "till now", "to now")

    @staticmethod
    def _fiscal_offset_for_year(target_year, target_month, fiscal_start_month, today=None):
        """
        How many fiscal years back a calendar month/year falls, or None.

        A snapshot table has one column per fiscal year, so an explicit date
        like "August 2025" has to become an offset before it can become a
        column. With an April start, August 2025 belongs to FY 2025-26; if the
        current fiscal year began April 2026 that is one year back, so PY.

        Returns None for a future period or one further back than configured -
        the caller then leaves the question alone rather than answering it
        with the nearest column it happens to have.
        """
        import datetime

        if not target_year:
            return None

        today = today or datetime.date.today()
        start = int(fiscal_start_month or 1)

        def fiscal_start_year(year, month):
            return year if month >= start else year - 1

        current = fiscal_start_year(today.year, today.month)
        target = fiscal_start_year(int(target_year), int(target_month or start))

        offset = current - target
        return offset if offset >= 0 else None

    @staticmethod
    def _trend_year_offset(question):
        """
        Which year a trend question names, or None if it names none.

        Normalized through the temporal normalizer so "current year" and
        "this year" are one phrase, and so this reads the same vocabulary the
        detector does rather than a second list that could drift from it.
        """
        try:
            from semantic.temporal.normalizer import TimeNormalizer
            from semantic.temporal.tokenizer import TimeTokenizer
            text = TimeNormalizer().normalize(TimeTokenizer().tokenize(question or ""))
        except Exception:
            text = (question or "").lower()

        text = text or ""
        if "last year" in text or "previous year" in text:
            return 1
        if "this year" in text or "current year" in text:
            return 0
        return None

    def _bind_snapshot_period(self, time_context, connection_id, table_names, question):
        """
        Attach the configured period column to a detected year intent.

        Returns the context unchanged unless ALL of these hold: a year-level
        intent was detected, no snapshot column is attached yet, and exactly
        one selected table is snapshot-configured. Anything less ambiguous is
        left alone - this fills a gap, it does not override a decision.
        """
        if time_context is not None and getattr(time_context, "snapshot_columns", None):
            return time_context

        # The intent and the context are published separately, and resolution
        # can produce an intent with no context at all - which is exactly the
        # state "Show current year sales" reached. Read the intent from
        # whichever of the two actually carries it.
        intent = getattr(time_context, "intent", None)
        if intent is None:
            try:
                intent = self.temporal_pipeline.get_last_intent()
            except Exception:
                intent = None

        name = type(intent).__name__ if intent is not None else ""
        if name not in ("CurrentYearIntent", "PreviousYearIntent",
                        "YearComparisonIntent", "TrendIntent",
                        "YearRangeIntent", "MonthRangeIntent"):
            return time_context

        try:
            from semantic.temporal.enums import TimeStrategyType
            from semantic.temporal.snapshot_config import SnapshotConfigLoader

            configured = []
            for table in (table_names or []):
                cfg = SnapshotConfigLoader.for_table(connection_id, table)
                if cfg and cfg.is_configured and cfg.bindings:
                    configured.append(cfg)

            if len(configured) != 1:
                return time_context

            config = configured[0]
            lowered = (question or "").lower()
            scope = "TO_DATE" if any(m in lowered for m in self._TO_DATE_MARKERS) else None

            if name == "YearComparisonIntent":
                # comparison_columns already owns the like-for-like rule: with
                # the running year in the comparison every other period
                # resolves to-date, so this returns CY and PYTD rather than
                # CY and a complete PY. That rule lives in one place and is
                # not restated here.
                columns, warns = config.comparison_columns([0, 1], "VALUE")
                for warning in warns or []:
                    print(f"[Temporal binding] {warning}")
                if not columns:
                    return time_context
                column = columns[0]
                extra_columns = list(columns)
            elif name in ("YearRangeIntent", "MonthRangeIntent"):
                # An explicit date the user gave - "August 2025". Turned into a
                # fiscal offset and then into that year's column, so a question
                # that already named its period is never asked for one.
                offset = self._fiscal_offset_for_year(
                    getattr(intent, "start_year", None),
                    getattr(intent, "start_month", None),
                    config.fiscal_year_start_month,
                )
                if offset is None:
                    return time_context
                column = config.column_for(offset, "VALUE", scope)
                if not column:
                    # The period is real but this table does not reach that far
                    # back. Saying nothing is better than answering with the
                    # oldest column we happen to have.
                    print(f"[Temporal binding] {name} is {offset} fiscal years "
                          f"back; {config.table_name} has no column for it")
                    return time_context
                extra_columns = [column]
            elif name == "TrendIntent":
                # "Show last year sales trend" is read as a trend, and the
                # year inside it is then never resolved - so the plan asked
                # which period a question that already said "last year".
                # The year phrases come from the temporal normalizer's own
                # vocabulary ("current year" normalizes to "this year"), so
                # no new wording is invented here.
                offset = self._trend_year_offset(question)
                if offset is None:
                    # Genuinely unspecified. Leave it: the period
                    # clarification is the correct response, and the trend
                    # survives it because the follow-up carries the question.
                    return time_context
                column = config.column_for(offset, "VALUE", scope)
                if not column:
                    return time_context
                extra_columns = [column]
            else:
                offset = 0 if name == "CurrentYearIntent" else 1
                column = config.column_for(offset, "VALUE", scope)
                if not column:
                    return time_context
                extra_columns = [column]

            # TimeContext is frozen, so this replaces rather than mutates.
            from semantic.temporal.models import TimeContext

            if time_context is None:
                time_context = TimeContext(
                    intent=intent,
                    strategy=TimeStrategyType.SNAPSHOT,
                    snapshot_columns=list(extra_columns),
                )
            else:
                import dataclasses
                time_context = dataclasses.replace(
                    time_context,
                    strategy=TimeStrategyType.SNAPSHOT,
                    snapshot_columns=list(extra_columns),
                )

            self.temporal_pipeline._thread_local.last_time_context = time_context

            print(f"\n[Temporal binding] {name} + scope={scope or 'natural'} "
                  f"-> {column} on {config.table_name}")
        except Exception as exc:
            print(f"\n[Temporal binding] skipped: {exc}")

        return time_context

    def build_sql_prompt(
        self,
        question: str,
        history = None,
        company_id = None,
        connection_id: Optional[str] = None,
        settings: Optional[TimeSettings] = None,
        context: Optional[SemanticExecutionContext] = None,
        clarified_candidate = None
    ) -> tuple[str, dict, str]:
        history_text = ""

        if history:
            history_text = "\nConversation History:\n"

            for item in history[-2:]:
                history_text += (
                    f"\nUser: {item['question']}"
                    f"\nPrevious SQL: {item['sql_query']}"
                )

        if context is None:
            context = SemanticExecutionContext(
                connection_id=connection_id,
                company_id=company_id,
                settings=settings
            )

        active_connection = context.connection
        if not active_connection:
            raise ValueError("No active database connection found.")

        # Print all the Aggregation metrics, Dimensions, and Joins for the current active database connection
        try:
            from semantic.semantic_service import SemanticService
            from semantic.relationship_service import SemanticRelationshipService

            conn_id = active_connection["connection_id"]
            all_metrics = SemanticService.get_metrics(conn_id)
            all_dims = SemanticService.get_dimensions(conn_id)
            all_joins = SemanticRelationshipService.build_relationships(conn_id)

            print("\n========== ALL DB SEMANTIC METRICS, DIMENSIONS, AND JOINS (CURRENT DB) ==========")
            print(f"Connection Name: {active_connection.get('connection_name')}")
            print("Aggregation Metrics:")
            if all_metrics:
                for metric in all_metrics:
                    print(f"- {metric.get('metric_name')} ({metric.get('business_name')}): {metric.get('aggregation_type')}({metric.get('table_name')}.{metric.get('column_name')})")
            else:
                print("- (None)")

            print("Dimensions:")
            if all_dims:
                for dim in all_dims:
                    print(f"- {dim.get('dimension_name')} ({dim.get('business_name')}): {dim.get('table_name')}.{dim.get('column_name')}")
            else:
                print("- (None)")

            print("Joins:")
            if all_joins:
                for join in all_joins:
                    print(f"- {join[0]}.{join[1]} -> {join[2]}.{join[3]}")
            else:
                print("- (None)")
            print("=================================================================================\n")
        except Exception as e:
            print(f"Error printing DB semantic metadata: {e}")

        # Resolve temporal context
        t_temp_start = time.time()
        temporal_section = self.temporal_pipeline.build(
            question=question,
            connection_id=context.connection_id,
            settings=context.settings
        )
        t_temp_sec = time.time() - t_temp_start

        # Intercept temporal clarification resume
        if clarified_candidate:
            candidates_list = clarified_candidate if isinstance(clarified_candidate, list) else [clarified_candidate]
            for cand in candidates_list:
                if isinstance(cand, dict):
                    val = cand.get("value")
                    val_lower = val.lower() if val else ""
                    if val_lower in ("this year", "last year", "2 years ago", "3 years ago", "4 years ago"):
                        from semantic.temporal.models import TimeContext, CurrentYearIntent, PreviousYearIntent
                        from semantic.temporal.enums import TimeIntentType, TimeStrategyType
                        from semantic.temporal.models import BaseTimeIntent
                        from semantic.temporal.capability_cache import TimeResolutionCache
                        
                        cached_entry = TimeResolutionCache.get(connection_id)
                        capability = cached_entry.capability if cached_entry else None
                        
                        new_ctx = None
                        if val_lower == "this year":
                            col = capability.snapshot_mapping.get(0) if capability and capability.snapshot_mapping else "CY"
                            new_ctx = TimeContext(
                                intent=CurrentYearIntent(intent_type=TimeIntentType.CURRENT_YEAR),
                                strategy=TimeStrategyType.SNAPSHOT,
                                snapshot_columns=[col]
                            )
                        elif val_lower == "last year":
                            col = capability.snapshot_mapping.get(1) if capability and capability.snapshot_mapping else "PY"
                            new_ctx = TimeContext(
                                intent=PreviousYearIntent(intent_type=TimeIntentType.PREVIOUS_YEAR),
                                strategy=TimeStrategyType.SNAPSHOT,
                                snapshot_columns=[col]
                            )
                        elif val_lower == "2 years ago":
                            intent = BaseTimeIntent()
                            intent.intent_type = "PPY"
                            col = capability.snapshot_mapping.get(2) if capability and capability.snapshot_mapping else "PPY"
                            new_ctx = TimeContext(
                                intent=intent,
                                strategy=TimeStrategyType.SNAPSHOT,
                                snapshot_columns=[col]
                            )
                        elif val_lower == "3 years ago":
                            intent = BaseTimeIntent()
                            intent.intent_type = "PPPY"
                            col = capability.snapshot_mapping.get(3) if capability and capability.snapshot_mapping else "PPPY"
                            new_ctx = TimeContext(
                                intent=intent,
                                strategy=TimeStrategyType.SNAPSHOT,
                                snapshot_columns=[col]
                            )
                        elif val_lower == "4 years ago":
                            intent = BaseTimeIntent()
                            intent.intent_type = "PPPPY"
                            col = capability.snapshot_mapping.get(4) if capability and capability.snapshot_mapping else "PPPPY"
                            new_ctx = TimeContext(
                                intent=intent,
                                strategy=TimeStrategyType.SNAPSHOT,
                                snapshot_columns=[col]
                            )
                        if new_ctx:
                            self.temporal_pipeline._thread_local.last_time_context = new_ctx
                            break

        # TEMP_PIPELINE_TRACE_REMOVE_LATER
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_timing("temporal", t_temp_sec)
        except Exception:
            pass

        # Extract previous semantic context from history
        previous_semantic_context = None
        if history:
            for item in reversed(history):
                sem_ctx = item.get("semantic_context")
                if sem_ctx and isinstance(sem_ctx, dict):
                    if sem_ctx.get("resolved_values") or sem_ctx.get("dimensions"):
                        previous_semantic_context = sem_ctx
                        break

        # --------------------------------------------------
        # Gate 4 Steps 25-28: structured intent extraction
        # --------------------------------------------------
        # Placed above semantic resolution deliberately. Extraction reads the
        # question's wording, not the resolver's output, so it is valid whether
        # or not retrieval runs - and when the gate blocks, the extracted
        # mode is what lets the block explain itself in the user's own terms.
        #
        # Wrapped whole: extraction is an enrichment, and the plan builder falls
        # back to its Gate 1 heuristics when `extracted` is None. A failure here
        # must never cost the user their answer.
        extracted_intent = None
        try:
            from ai.extraction.slot_extractor import extract_intent
            from ai import assumptions as gate4_assumptions

            extracted_intent = extract_intent(
                question=question,
                connection_id=active_connection["connection_id"],
                company_id=company_id,
                history_summary=history_text or "",
            )

            outcome = gate4_assumptions.resolve(extracted_intent)
            extracted_intent.assumptions_made = gate4_assumptions.merge_into(
                extracted_intent.assumptions_made,
                outcome.assumptions,
            )
            if outcome.clarification is not None:
                extracted_intent.clarification = outcome.clarification

            print("\n========== GATE 4 EXTRACTION ==========")
            print(f"Mode        : {extracted_intent.mode}")
            print(f"Ranking     : dir={extracted_intent.direction} "
                  f"measure={extracted_intent.measure} top_n={extracted_intent.top_n}")
            print(f"Benchmark   : {extracted_intent.benchmark}")
            print(f"Period      : {extracted_intent.time_period} "
                  f"vs {extracted_intent.comparison_period}")
            print(f"Values      : {[p.to_dict() for p in extracted_intent.value_phrases]}")
            print(f"Tier        : {extracted_intent.escalation_tier.value}")
            print(f"Assumptions : {extracted_intent.assumptions_made}")
            print(f"Unsupported : {extracted_intent.unsupported}")
            print("=======================================")
        except Exception as exc:
            extracted_intent = None
            print(f"\n[Gate 4] Extraction skipped: {exc}")

        semantic_start_time = time.time()
        semantic_result = (
            SemanticResolver.resolve(
                active_connection["connection_id"],
                question,
                clarified_candidate=clarified_candidate,
                previous_semantic_context=previous_semantic_context,
                # Step 3 - the spans extraction identified as values. Consumed
                # only when SEMANTIC_VALUE_MODE=enforce; otherwise carried and
                # ignored, exactly as in Step 2.
                value_phrases=(
                    extracted_intent.value_phrases if extracted_intent is not None else None
                )
            )
        )
        semantic_time = round(time.time() - semantic_start_time, 2)
        if isinstance(semantic_result, dict):
            ret_dict = semantic_result.setdefault("retrieval", {})
            if isinstance(ret_dict, dict):
                ret_dict["time"] = semantic_time

        # Gate 4: the extraction above ran before the resolver, so its
        # diagnostic form is attached here, once semantic_result exists.
        if extracted_intent is not None and isinstance(semantic_result, dict):
            semantic_result["extracted_intent"] = extracted_intent.to_dict()

            # Step 2 - OBSERVATION ONLY. Surfaced at the top level so the
            # phrases the extractor proposes can be reviewed against what the
            # deterministic resolver independently found, before anything is
            # allowed to depend on them. Nothing reads this key yet.
            semantic_result["value_phrases"] = [
                p.to_dict() for p in extracted_intent.value_phrases
            ]

        # TEMP_PIPELINE_TRACE_REMOVE_LATER
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_timing("semantic", semantic_time)
            PipelineDiagnosticTracer.record_semantic(semantic_result)
            PipelineDiagnosticTracer.record_temporal()
        except Exception:
            pass

        ret_confidence = 0.0
        ret_status = "Unknown"
        ret_reason = "None"
        if isinstance(semantic_result, dict):
            ret_data = semantic_result.get("retrieval")
            if isinstance(ret_data, dict):
                conf = ret_data.get("confidence")
                if isinstance(conf, (int, float)):
                    ret_confidence = float(conf)
                stat = ret_data.get("status")
                if isinstance(stat, str):
                    ret_status = stat
                reas = ret_data.get("reason")
                if isinstance(reas, str):
                    ret_reason = reas
        
        metric_objs = semantic_result.get("metric_objects", []) if isinstance(semantic_result, dict) else []

        # If any resolved metric is a snapshot period metric, set strategy to SNAPSHOT to avoid redundant date predicates
        has_snapshot_metric = any(
            m.get("column_name") in {"CY", "PY", "PPY", "PPPY", "PPPPY", "CYQ", "PYQ"}
            for m in metric_objs
        )
        if has_snapshot_metric:
            last_res = TemporalPipeline.get_last_resolution()
            if last_res and last_res.plan:
                from semantic.temporal.enums import TimeStrategyType
                from semantic.temporal.models import TimeContext
                active_settings = settings or TimeSettings()
                raw_ctx = self.temporal_pipeline.context_builder.build(last_res, active_settings)
                time_ctx = TimeContext(
                    intent=raw_ctx.intent,
                    strategy=TimeStrategyType.SNAPSHOT,
                    date_column=raw_ctx.date_column,
                    calendar_table=raw_ctx.calendar_table,
                    snapshot_columns=raw_ctx.snapshot_columns,
                    grouping=raw_ctx.grouping,
                    start_date=raw_ctx.start_date,
                    end_date=raw_ctx.end_date,
                    comparison=raw_ctx.comparison,
                    calendar_type=raw_ctx.calendar_type,
                    financial_year_start_month=raw_ctx.financial_year_start_month,
                    timezone=raw_ctx.timezone,
                    locale=raw_ctx.locale,
                    is_partial=raw_ctx.is_partial,
                    warnings=raw_ctx.warnings
                )
                temporal_section = self.temporal_pipeline.temporal_formatter.format(time_ctx, style="llm")

        # Gate 3 - table-aware DATE_COLUMN. TemporalPipeline.build() ran
        # before any metric table was known, so it could only ever use the
        # connection-wide capability - which never carries date_columns (see
        # TimeStrategyResolver._discover_capability()'s own docstring: that
        # is a per-TABLE fact, and publishing one table's date column
        # connection-wide would offer it for a query against an unrelated
        # table). Once the metric's table IS known, re-resolve the SAME
        # detected intent against THAT table's own capability
        # (discover_capability_for_table() - Step 7a's SnapshotConfigLoader.
        # for_table() pattern, validated against the real schema the same
        # way month_column already is). That capability is a strict
        # superset of the connection-wide one (only date_columns is ever
        # added), so re-resolving can only make a DATE_COLUMN-dependent
        # strategy available, never change or remove anything the original
        # resolution already produced. Mutually exclusive with the SNAPSHOT
        # correction above: a snapshot metric's table has no DATE_COLUMN
        # configuration, so the two never both fire.
        elif not has_snapshot_metric:
            last_intent = TemporalPipeline.get_last_intent()
            if last_intent and metric_objs:
                metric_table = None
                for m in metric_objs:
                    if isinstance(m, dict) and m.get("table_name"):
                        metric_table = m["table_name"]
                        break

                if metric_table:
                    from semantic.temporal.resolver import TimeStrategyResolver

                    table_capability = TimeStrategyResolver().discover_capability_for_table(
                        context.connection_id, metric_table
                    )
                    if table_capability.date_columns:
                        active_settings = settings or TimeSettings()
                        # connection_id deliberately NOT passed through here:
                        # TimeStrategySelector.select() memoizes its winning
                        # strategy per (connection_id, intent_type) in
                        # TimeResolutionCache and reuses it on a later call
                        # for the SAME connection regardless of which
                        # capability is passed in. Two different tables on
                        # one connection share a connection_id, so the first
                        # table's chosen strategy for an intent type was
                        # being wrongly replayed for the second table's
                        # explicit, table-scoped capability. capability is
                        # already supplied directly here, so no connection_id
                        # is needed for resolve_intent's own cache fallback
                        # either - this omission is safe and touches no
                        # shared state.
                        new_res = self.temporal_pipeline.time_resolver.resolve_intent(
                            intent=last_intent,
                            capability=table_capability,
                            settings=active_settings,
                        )
                        if new_res.resolved and new_res.plan:
                            new_ctx = self.temporal_pipeline.context_builder.build(
                                new_res, active_settings
                            )
                            temporal_section = self.temporal_pipeline.temporal_formatter.format(
                                new_ctx, style="llm"
                            )
                            self.temporal_pipeline._thread_local.last_time_context = new_ctx
                            self.temporal_pipeline._thread_local.last_resolution = new_res

        dimension_objs = semantic_result.get("dimension_objects", []) if isinstance(semantic_result, dict) else []
        value_matches = semantic_result.get("value_matches", []) if isinstance(semantic_result, dict) else []
        
        resolved_tables_set = set()
        for obj in metric_objs:
            if isinstance(obj, dict):
                tname = obj.get("table_name")
                if isinstance(tname, str):
                    resolved_tables_set.add(tname)
        for obj in dimension_objs:
            if isinstance(obj, dict):
                tname = obj.get("table_name")
                if isinstance(tname, str):
                    resolved_tables_set.add(tname)
        for val in value_matches:
            if isinstance(val, dict):
                tname = val.get("table_name")
                if isinstance(tname, str):
                    resolved_tables_set.add(tname)
                
        resolved_tables = sorted(list(resolved_tables_set))
        
        filters_list: list[str] = []
        for v in value_matches:
            if isinstance(v, dict):
                col = v.get("column_name")
                op = v.get("operator", "=")
                val = v.get("value")
                if isinstance(col, str) and isinstance(val, (str, int, float)):
                    op_str = str(op) if op is not None else "="
                    filters_list.append(f"{col} {op_str} {str(val)}")
        resolved_filters_str = ', '.join(filters_list) or 'None'
        
        values_list: list[str] = []
        for v in value_matches:
            if isinstance(v, dict):
                val = v.get("value")
                if val is not None:
                    values_list.append(str(val))
        resolved_values_str = ', '.join(values_list) or 'None'

        metrics_list: list[str] = []
        for m in metric_objs:
            if isinstance(m, dict):
                bname = m.get("business_name")
                if isinstance(bname, str):
                    metrics_list.append(bname)
        resolved_metrics_str = ', '.join(metrics_list) or 'None'

        dims_list: list[str] = []
        for d in dimension_objs:
            if isinstance(d, dict):
                bname = d.get("business_name")
                if isinstance(bname, str):
                    dims_list.append(bname)
        resolved_dims_str = ', '.join(dims_list) or 'None'

        resolved_tables_str = ', '.join(resolved_tables) or 'None'

        print("\n========== SEMANTIC RESOLUTION ==========")
        print(f"Question: {question}")
        print(f"Resolved Metrics: {resolved_metrics_str}")
        print(f"Resolved Dimensions: {resolved_dims_str}")
        print(f"Resolved Filters: {resolved_filters_str}")
        print(f"Resolved Values: {resolved_values_str}")
        print(f"Resolved Tables: {resolved_tables_str}")
        print(f"Semantic Confidence: {ret_confidence}")
        print(f"Retrieval Status: {ret_status}")
        print(f"Reason: {ret_reason}")
        print("=========================================")

        # --------------------------------------------------
        # Semantic Retrieval Gate
        # --------------------------------------------------

        gate_result = SemanticGate.evaluate(semantic_result)

        print("\n========== RETRIEVAL GATE ==========")

        retrieval = semantic_result.get("retrieval")

        if isinstance(retrieval, dict):
            print(f"Retrieval Status: {retrieval.get('status', 'Unknown')}")
            print(f"Confidence: {retrieval.get('confidence', 0.0)}")
        else:
            print("Retrieval Status: Unknown")
            print("Confidence: 0.0")

        print(f"Decision: {'ALLOW SQL' if gate_result['allowed'] else 'BLOCK SQL'}")
        print(f"Reason: {gate_result.get('reason', 'None')}")
        print("====================================")
        
        # --------------------------------------------------
        # Stop pipeline if semantic retrieval failed
        # --------------------------------------------------

        if not gate_result["allowed"]:

            print("\n========== SEMANTIC GATE BLOCKED ==========")
            print(gate_result["reason"])

            if gate_result.get("status") == "PARTIAL_MATCH":
                from core.exceptions import AmbiguityException
                value_matches = semantic_result.get("value_matches", [])
                if value_matches:
                    # Gate 3 Step 21c. value_matches already carries every
                    # genuine value the resolver retained (dominant first,
                    # from the candidate-retention fix), not just the top one -
                    # build one option per entry instead of only value_matches[0]
                    # so a real alternative like N--NIGHT WEARS is not silently
                    # dropped from the choice a user is offered.
                    best_match = value_matches[0]
                    options = [
                        {
                            "option_id": idx + 1,
                            "value": m["value"],
                            "dimension": m.get("business_name") or m.get("dimension"),
                            "business_name": m.get("business_name"),
                            "dimension_id": m.get("dimension_id"),
                            "table_name": m.get("table_name"),
                            "column_name": m.get("column_name"),
                            "normalized_value": m.get("normalized_value", m["value"].lower()),
                            "match_type": m.get("match_type"),
                            "matched_question_tokens": m.get("matched_question_tokens", []),
                            "matched_value_tokens": m.get("matched_value_tokens", [])
                        }
                        for idx, m in enumerate(value_matches)
                    ]

                    if len(options) == 1:
                        # Unchanged: the single "did you mean" prompt.
                        msg = f"I couldn't find \"{question}\" in the available business data. I found \"{best_match['value']}\" instead. Would you like to use that?"
                    else:
                        opt_str = "\n".join(f"{opt['option_id']}. {opt['value']}" for opt in options[:5])
                        msg = f"I couldn't find \"{question}\" exactly. I found multiple possible matches:\n\n{opt_str}\n\nPlease choose one:"

                    raise AmbiguityException(
                        message=msg,
                        details={
                            "original_question": question,
                            "ambiguity_type": "PARTIAL_MATCH",
                            "options": options
                        }
                    )
                else:
                    msg = f"I couldn't find any data matching \"{question}\" in the available business data. Please try another product, category, or business term."
                    raise SemanticRetrievalException(
                        message=msg,
                        details={
                            "question": question,
                            "retrieval": semantic_result["retrieval"]
                        }
                    )

            if gate_result.get("status") == "WEAK_AMBIGUITY":
                # Gate 3 Step 21c. The gate only reaches this status when
                # value_matches held more than one genuine alternative (see
                # semantic/semantic_gate.py) - a WEAK_AMBIGUITY that filtered
                # down to one value never sets allowed=False, so this branch
                # is never entered for the single-candidate case. Reuses the
                # existing AmbiguityException/options clarification flow -
                # same shape as PARTIAL_MATCH and STRONG_AMBIGUITY above, no
                # new mechanism. Genuine alternatives are same-column by
                # construction (that is what "genuine" means here), so this
                # is always a same-dimension choice.
                from core.exceptions import AmbiguityException
                value_matches = semantic_result.get("value_matches", [])
                options = [
                    {
                        "option_id": idx + 1,
                        "value": m["value"],
                        "dimension": m.get("business_name") or m.get("dimension"),
                        "business_name": m.get("business_name"),
                        "dimension_id": m.get("dimension_id"),
                        "table_name": m.get("table_name"),
                        "column_name": m.get("column_name"),
                        "normalized_value": m.get("normalized_value", m["value"].lower()),
                        "match_type": m.get("match_type"),
                        "matched_question_tokens": m.get("matched_question_tokens", []),
                        "matched_value_tokens": m.get("matched_value_tokens", [])
                    }
                    for idx, m in enumerate(value_matches)
                ]
                opt_str = "\n".join(f"{opt['option_id']}. {opt['value']}" for opt in options[:5])
                msg = f"I found multiple possible matches for \"{question}\".\nPlease choose one:\n\n{opt_str}"
                raise AmbiguityException(
                    message=msg,
                    details={
                        "original_question": question,
                        "ambiguity_type": "SAME_DIMENSION",
                        "options": options
                    }
                )

            if gate_result.get("status") == "STRONG_AMBIGUITY":
                from core.exceptions import AmbiguityException
                
                # Expose options with option_id, value, and dimension/business_name, dimension_id
                options = []
                for idx, m in enumerate(semantic_result.get("value_matches", [])):
                    options.append({
                        "option_id": idx + 1,
                        "value": m["value"],
                        "dimension": m["business_name"],
                        "business_name": m["business_name"],
                        "dimension_id": m["dimension_id"],
                        "table_name": m["table_name"],
                        "column_name": m["column_name"],
                        "normalized_value": m.get("normalized_value", m["value"].lower()),
                        "match_type": m.get("match_type"),
                        "matched_question_tokens": m.get("matched_question_tokens", []),
                        "matched_value_tokens": m.get("matched_value_tokens", [])
                    })
                
                matched_tokens = []
                for m in semantic_result.get("value_matches", []):
                    for tok in m.get("matched_question_tokens", []):
                        if tok.lower() not in [t.lower() for t in matched_tokens]:
                            matched_tokens.append(tok)
                
                # Sort matched_tokens by their order in the original question
                words = question.lower().split()
                matched_tokens.sort(key=lambda x: words.index(x.lower()) if x.lower() in words else 999)
                matched_phrase = " ".join(matched_tokens)
                if not matched_phrase:
                    matched_phrase = question
                
                # Gate 3 - a STRONG_AMBIGUITY tie that already collapsed to
                # zero candidates (see dimension_value_resolver.py's
                # all-unreachable/unqualified collapse) has nothing left to
                # offer a choice between. Raising "please choose one" with no
                # options was the actual live symptom for "Show sales for
                # Mumbai": value_matches was already correctly empty, but
                # this block raised the clarification unconditionally
                # anyway. Only raise it when there is something to choose;
                # an empty options list falls through, unmodified, to the
                # existing unresolved-value/escalation handling below.
                if options:
                    opt_str = "\n".join(f"{opt['option_id']}. {opt['value']}" for opt in options[:5])
                    msg = f"I found multiple possible matches for \"{matched_phrase}\".\nPlease choose one:\n\n{opt_str}"

                    dimensions_seen = {opt["dimension"] for opt in options if opt["dimension"]}
                    if len(dimensions_seen) <= 1:
                        ambiguity_type = "SAME_DIMENSION"
                    else:
                        ambiguity_type = "CROSS_DIMENSION"

                    raise AmbiguityException(
                        message=msg,
                        details={
                            "original_question": question,
                            "ambiguity_type": ambiguity_type,
                            "options": options
                        }
                    )

                # Falls through here only when the tie collapsed to zero
                # options. gate_result["reason"] is SemanticGate's own
                # STRONG_AMBIGUITY text ("...Clarification is required.") -
                # accurate when options were offered, misleading here since
                # none were. State plainly that nothing matched instead of
                # asking for a clarification this flow cannot provide.
                msg = (
                    f"I couldn't find a specific value matching \"{matched_phrase}\" "
                    f"that applies to this data. Please try another product, "
                    f"category, or business term."
                )
                raise SemanticRetrievalException(
                    message=msg,
                    details={
                        "question": question,
                        "retrieval": semantic_result["retrieval"]
                    }
                )

            msg = gate_result.get("reason") or f"I couldn't find any data matching \"{question}\" in the available business data. Please try another product, category, or business term."
            raise SemanticRetrievalException(
                message=msg,
                details={
                    "question": question,
                    "retrieval": semantic_result["retrieval"]
                }
            )

        # Resolve initial relevant tables from matched semantic objects and keyword fallback
        relevant_tables = RelevantTableResolver.resolve(
            semantic_result
        )
        print("\n========== RELEVANT TABLES ==========")
        pprint(relevant_tables)

        # Expand relationship bridge tables
        expanded_tables = RelationshipExpander.expand(
            active_connection["connection_id"],
            relevant_tables
        )

        table_names: list[str] = []
        if isinstance(expanded_tables, list):
            for t in expanded_tables:
                if isinstance(t, dict):
                    tname = t.get("table_name")
                    if isinstance(tname, str):
                        table_names.append(tname)

        relationship_context = (
            RelationshipContextService.build_context(
                active_connection["connection_id"],
                table_names
            )
        )

        print("\n========== EXPANDED TABLES ==========")
        pprint(expanded_tables)

        from semantic.metadata_resolver import MetadataResolver
        
        metadata_result = MetadataResolver.resolve(
            question=question,
            connection_id=active_connection["connection_id"],
            semantic_result=semantic_result,
            expanded_tables=expanded_tables
        )

        print("\n========== METADATA RESULT ==========")
        pprint(metadata_result)

        runtime_context = RuntimeContextBuilder.build(
            metadata_result
        )

        if relationship_context:
            runtime_context += (
                "\n\n"
                "=== RELATIONSHIP CONTEXT ===\n\n"
                f"{relationship_context}"
            )

        # Add required tables from metadata resolver if any extra display tables were needed
        extra_req = metadata_result.get("required_tables", []) if isinstance(metadata_result, dict) else []
        if isinstance(extra_req, list):
            for req in extra_req:
                if isinstance(req, str) and req not in table_names:
                    table_names.append(req)
        table_names = sorted(table_names)

        # GATE 3A - Structured SemanticPlan Construction
        semantic_plan = None
        try:
            from semantic.semantic_plan_builder import SemanticPlanBuilder
            from core.exceptions import EnterpriseException
            time_context = self.temporal_pipeline.get_last_time_context()

            # Bind a detected year expression to this table's period column.
            #
            # The temporal pipeline runs before the metric table is known, and
            # the connection-level capability it consults is empty for this
            # deployment, so a perfectly good CurrentYearIntent arrived with no
            # snapshot column attached. The plan then had a Sales metric it
            # could not bind and asked "which time period?" about a question
            # that had already said "current year".
            #
            # Now that the table IS known, the same TimeContext the clarified
            # answer produces is built here from that table's configuration.
            # Answering the clarification stays exactly as it was; this only
            # removes the need to ask when the user already told us.
            time_context = self._bind_snapshot_period(
                time_context,
                active_connection["connection_id"],
                table_names,
                question,
            )

            semantic_plan = SemanticPlanBuilder.build(
                question=question,
                semantic_result=semantic_result,
                time_context=time_context,
                relevant_tables=table_names,
                connection_id=active_connection["connection_id"],
                clarified_candidate=clarified_candidate,
                extracted=extracted_intent
            )
            # Store in semantic_result for downstream safety
            semantic_result["semantic_plan"] = semantic_plan
            
            # Propagate physical metrics column bindings from SemanticPlan to prompt context
            if semantic_plan:
                bound_metric_objs = []
                for m in semantic_plan.metrics:
                    bound_metric_objs.append({
                        "metric_name": m.metric_name,
                        "business_name": m.business_name,
                        "table_name": m.table_name,
                        "column_name": m.column_name,
                        "aggregation_type": m.aggregation_type
                    })
                semantic_result["metric_objects"] = bound_metric_objs
                semantic_result["metrics"] = [m.business_name for m in semantic_plan.metrics]
            
            # Record in diagnostic tracer
            try:
                from semantic.diagnostic_trace import PipelineDiagnosticTracer
                PipelineDiagnosticTracer.record_semantic_plan(semantic_plan)
            except Exception:
                pass
        except EnterpriseException:
            raise
        except Exception as spe:
            print(f"Error compiling SemanticPlan: {spe}")

        # Check if clarification is required
        if semantic_plan:
            is_sales_unresolved = False
            for m in semantic_plan.metrics:
                if m.business_name == "Sales" and m.column_name == "None":
                    is_sales_unresolved = True
                    break
            if is_sales_unresolved:
                from core.exceptions import AmbiguityException
                from semantic.temporal.capability_cache import TimeResolutionCache
                
                cached_entry = TimeResolutionCache.get(active_connection["connection_id"])
                capability = cached_entry.capability if cached_entry else None
                
                INDEX_TO_DISPLAY = {
                    0: "This Year",
                    1: "Last Year",
                    2: "2 Years Ago",
                    3: "3 Years Ago",
                    4: "4 Years Ago"
                }
                
                options = []
                if capability and capability.snapshot_mapping:
                    sorted_indices = sorted(capability.snapshot_mapping.keys())
                    opt_id = 1
                    for idx in sorted_indices:
                        display_val = INDEX_TO_DISPLAY.get(idx)
                        if display_val:
                            options.append({
                                "option_id": opt_id,
                                "value": display_val,
                                "display_dimension": "Time Period"
                            })
                            opt_id += 1
                            
                if not options:
                    options = [
                        {"option_id": 1, "value": "This Year", "display_dimension": "Time Period"},
                        {"option_id": 2, "value": "Last Year", "display_dimension": "Time Period"},
                        {"option_id": 3, "value": "2 Years Ago", "display_dimension": "Time Period"},
                        {"option_id": 4, "value": "3 Years Ago", "display_dimension": "Time Period"},
                        {"option_id": 5, "value": "4 Years Ago", "display_dimension": "Time Period"}
                    ]
                    
                raise AmbiguityException(
                    message="Which time period would you like for sales?",
                    details={
                        "original_question": question,
                        "ambiguity_type": "TEMPORAL_INTENT",
                        "options": options
                    }
                )

        schema_text = RelevantSchemaService.get_schema(
            active_connection["connection_id"],
            table_names
        )

        # Format Metadata Rules
        metadata_rules_text = ""
        rules = metadata_result.get("metadata_rules", []) if isinstance(metadata_result, dict) else []
        if isinstance(rules, list) and rules:
            metadata_rules_text = (
                "\n"
                "--------------------------------\n"
                "Metadata Rules\n\n"
                "Technical key columns are relationship columns.\n"
                "Use them ONLY for JOIN conditions.\n"
                "Never return them in SELECT unless explicitly requested.\n\n"
            )
            formatted_rules: list[str] = []
            for rule in rules:
                if not isinstance(rule, str):
                    continue
                if rule.startswith("Use ") and " instead of " in rule:
                    parts = rule.split(" instead of ")
                    bus_col = parts[0][4:]
                    remainder = parts[1]
                    
                    if " for SELECT, GROUP BY, ORDER BY. Continue using " in remainder:
                        parts2 = remainder.split(" for SELECT, GROUP BY, ORDER BY. Continue using ")
                        tech_col = parts2[0]
                        join_cond = parts2[1].replace(" inside JOIN.", "")
                        
                        formatted_rules.append(
                            f"Use\n{bus_col}\ninstead of\n{tech_col}\nfor\nSELECT\nGROUP BY\nORDER BY\n\n"
                            f"Continue using\n{join_cond}\ninside JOIN."
                        )
                    else:
                        tech_col = remainder.replace(" for SELECT, GROUP BY, ORDER BY", "")
                        formatted_rules.append(
                            f"Use\n{bus_col}\ninstead of\n{tech_col}\nfor\nSELECT\nGROUP BY\nORDER BY"
                        )
                elif rule.startswith("Keep ") and " because user explicitly requested it. Include both " in rule:
                    parts = rule.split(" because user explicitly requested it. Include both ")
                    tech_col = parts[0][5:]
                    remainder = parts[1]
                    
                    parts2 = remainder.split(" and ")
                    remainder2 = parts2[1]
                    
                    if " in SELECT. Continue using " in remainder2:
                        parts3 = remainder2.split(" in SELECT. Continue using ")
                        bus_col = parts3[0]
                        join_cond = parts3[1].replace(" inside JOIN.", "")
                        
                        formatted_rules.append(
                            f"Keep {tech_col} because user explicitly requested it.\n"
                            f"Include both\n{tech_col}\n+\n{bus_col}\nin SELECT.\n\n"
                            f"Continue using\n{join_cond}\ninside JOIN."
                        )
                    else:
                        bus_col = remainder2.replace(" in SELECT.", "")
                        formatted_rules.append(
                            f"Keep {tech_col} because user explicitly requested it.\n"
                            f"Include both\n{tech_col}\n+\n{bus_col}\nin SELECT."
                        )
                else:
                    formatted_rules.append(rule)
            
            metadata_rules_text += "\n\n".join(formatted_rules) + "\n\n"
            metadata_rules_text += (
                "LLM SQL Rules:\n"
                "Rule 1: JOINs always use technical keys.\n"
                "        Example: ON Sales.ProductKey = Products.ProductKey\n"
                "Rule 2: SELECT always uses descriptive columns.\n"
                "        Example: Products.Product\n"
                "Rule 3: GROUP BY uses descriptive columns.\n"
                "        Example: GROUP BY Products.Product\n"
                "Rule 4: ORDER BY uses aliases or descriptive columns.\n"
                "Rule 5: If user explicitly requests Key, ID, Code, Identifier, Number, Reference,\n"
                "        then include BOTH technical key and descriptive column.\n"
                "--------------------------------\n"
            )

        ret_metrics: list[str] = []
        if isinstance(semantic_result, dict):
            m_objects = semantic_result.get("metric_objects", [])
            if isinstance(m_objects, list):
                for m in m_objects:
                    if isinstance(m, dict):
                        mname = m.get("metric_name")
                        if isinstance(mname, str):
                            ret_metrics.append(mname)

        ret_dims: list[str] = []
        if isinstance(semantic_result, dict):
            d_objects = semantic_result.get("dimension_objects", [])
            if isinstance(d_objects, list):
                for d in d_objects:
                    if isinstance(d, dict):
                        dname = d.get("dimension_name")
                        if isinstance(dname, str):
                            ret_dims.append(dname)

        # === Pipeline Logging: STAGE RETRIEVAL DEBUG LOGS ===
        print("\n========== STAGE RETRIEVAL DEBUG LOGS ==========")
        print(f"Question                : {question}")
        print(f"Retrieved Tables        : {table_names}")
        print(f"Retrieved Metrics       : {ret_metrics}")
        print(f"Retrieved Dimensions    : {ret_dims}")
        print(f"Retrieved Metadata Rules: {rules}")
        print(f"Retrieved Relationships :\n{relationship_context.strip() if relationship_context else '(None)'}")
        print("================================================\n")

        ex_start = time.time()
        examples = (
            QueryExamplesService
            .retrieve(
                active_connection["connection_id"],
                relevant_tables=table_names,
                value_matches=value_matches,
                metric_objects=metric_objs
            )
        )
        ex_sec = time.time() - ex_start
        # TEMP_PIPELINE_TRACE_REMOVE_LATER
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_timing("examples", ex_sec)
        except Exception:
            pass

        examples_text = ""

        if examples:
            examples_text = "\n"
            for example in examples:
                examples_text += (
                    f"\nQuestion: "
                    f"{example['question']}"
                    f"\nSQL: "
                    f"{example['sql_query']}\n"
                )

        metric_objects_list = semantic_result.get("metric_objects", []) if isinstance(semantic_result, dict) else []
        dimension_objects_list = semantic_result.get("dimension_objects", []) if isinstance(semantic_result, dict) else []
        semantic_context = SemanticContextService.build_context(
            metric_objects_list,
            dimension_objects_list,
            dialect=active_connection.get("database_type")
        )

        print("\n========== SEMANTIC CONTEXT ==========")
        print("Metrics:")
        metric_objs_ctx = semantic_result.get("metric_objects") if isinstance(semantic_result, dict) else None
        if isinstance(metric_objs_ctx, list) and metric_objs_ctx:
            for m in metric_objs_ctx:
                if isinstance(m, dict):
                    bname = m.get("business_name")
                    tname = m.get("table_name")
                    cname = m.get("column_name")
                    agg = m.get("aggregation_type")
                    if bname is not None and tname is not None and cname is not None and agg is not None:
                        print(f"- {bname} ({tname}.{cname} as {agg})")
        else:
            print("- None")
        
        print("\nDimensions:")
        dimension_objs_ctx = semantic_result.get("dimension_objects") if isinstance(semantic_result, dict) else None
        if isinstance(dimension_objs_ctx, list) and dimension_objs_ctx:
            for d in dimension_objs_ctx:
                if isinstance(d, dict):
                    bname = d.get("business_name")
                    tname = d.get("table_name")
                    cname = d.get("column_name")
                    if bname is not None and tname is not None and cname is not None:
                        print(f"- {bname} ({tname}.{cname})")
        else:
            print("- None")
            
        print("\nRelationships:")
        if relationship_context:
            print(relationship_context.strip())
        else:
            print("- None")
            
        print("\nValues:")
        val_matches_ctx = semantic_result.get("value_matches") if isinstance(semantic_result, dict) else None
        if isinstance(val_matches_ctx, list) and val_matches_ctx:
            for v in val_matches_ctx:
                if isinstance(v, dict):
                    val = v.get("value")
                    tname = v.get("table_name")
                    cname = v.get("column_name")
                    if val is not None and tname is not None and cname is not None:
                        print(f"- {val} ({tname}.{cname})")
        else:
            print("- None")
            
        print("\nSQL Expressions:")
        has_expr = False
        dimension_objs_expr = semantic_result.get("dimension_objects") if isinstance(semantic_result, dict) else None
        if isinstance(dimension_objs_expr, list) and dimension_objs_expr:
            for d in dimension_objs_expr:
                if isinstance(d, dict):
                    category = d.get("semantic_category")
                    dialect = active_connection.get("database_type")
                    col_name = d.get("column_name")
                    bname = d.get("business_name")
                    if isinstance(category, str) and category.startswith("TIME_") and isinstance(dialect, str) and isinstance(col_name, str) and bname is not None:
                        from semantic.sql.temporal_mapper import TemporalMapper
                        expr = TemporalMapper.get_sql_expression(dialect, category, col_name)
                        print(f"- {bname}: {expr}")
                        has_expr = True
        if not has_expr:
            print("- None")
        print("======================================")

        # === GENERAL/ALL-SCHEMA PROMPT GENERATION (FOR COMPARISON LOGGING) ===
        try:
            all_tables_query = "SELECT st.table_name FROM schema_tables st WHERE st.connection_id = :connection_id"
            with engine.connect() as conn:
                all_tables_rows = conn.execute(text(all_tables_query), {"connection_id": active_connection["connection_id"]}).fetchall()
            all_tables = [r[0] for r in all_tables_rows]
            all_schema_text = RelevantSchemaService.get_schema(active_connection["connection_id"], all_tables)
        except Exception as e:
            all_schema_text = f"Error loading all schema: {e}"

        required_filters_section = ""
        required_filters_lines = []
        for v in value_matches:
            if isinstance(v, dict):
                col = v.get("column_name")
                op = v.get("operator", "=")
                val = v.get("value")
                if isinstance(col, str) and isinstance(val, (str, int, float)):
                    op_str = str(op) if op is not None else "="
                    val_str = f"'{val}'" if isinstance(val, str) else str(val)
                    required_filters_lines.append(f"- {col} {op_str} {val_str}")
        if required_filters_lines:
            formatted_filters = "\n".join(required_filters_lines)
            required_filters_section = f"\n===========================================================\nREQUIRED VALUE FILTERS\n===========================================================\n\n{formatted_filters}\n"

        # Format Semantic Plan Context block for LLM prompt
        semantic_plan_context_lines = []
        if semantic_plan:
            for m in semantic_plan.metrics:
                if m.business_name == "Sales":
                    temp_intent_name = "UNSPECIFIED"
                    if time_context and time_context.intent:
                        intent_type = getattr(time_context.intent, "intent_type", None)
                        if intent_type:
                            temp_intent_name = intent_type.value if hasattr(intent_type, "value") else str(intent_type)
                        else:
                            temp_intent_name = time_context.intent.__class__.__name__.replace("Intent", "").upper()
                    elif clarified_candidate:
                        cands = clarified_candidate if isinstance(clarified_candidate, list) else [clarified_candidate]
                        for c in cands:
                            val = c.get("value") if isinstance(c, dict) else ""
                            val_lower = val.lower() if val else ""
                            if val_lower in ("this year", "last year", "2 years ago", "3 years ago", "4 years ago"):
                                if val_lower == "this year": temp_intent_name = "CURRENT_YEAR"
                                elif val_lower == "last year": temp_intent_name = "PREVIOUS_YEAR"
                                elif val_lower == "2 years ago": temp_intent_name = "PPY"
                                elif val_lower == "3 years ago": temp_intent_name = "PPPY"
                                elif val_lower == "4 years ago": temp_intent_name = "PPPPY"
                    
                    strategy_name = "SNAPSHOT"
                    if time_context and time_context.strategy:
                        strategy_name = time_context.strategy.value if hasattr(time_context.strategy, "value") else str(time_context.strategy)
                    
                    date_filter_req = "NO" if strategy_name == "SNAPSHOT" else "YES"
                    semantic_plan_context_lines.append(
                        f"Business Metric: {m.business_name}\n"
                        f"Temporal: {temp_intent_name}\n"
                        f"Physical Metric: {m.column_name}\n"
                        f"Temporal Strategy: {strategy_name}\n"
                        f"Date Filter Required: {date_filter_req}\n"
                        f"Authoritative Binding: You MUST use physical column '{m.column_name}' for any references to Business Metric '{m.business_name}' in SELECT, GROUP BY, and aggregations (e.g. SUM({m.column_name}))."
                    )

            # Gate 3 Step 7b Fix B - the plan's dimension bindings, stated with
            # the same authority as the metric binding above.
            #
            # SemanticPlanBuilder can already replace a matched dimension with
            # the administrator's configured one - "sales by month" resolves
            # to Document Month, but the sales table's configured month column
            # is Inv Month, and the plan swaps it in because Inv Month's
            # leading letter (A April ... L March) sorts fiscally while
            # DocMonth is a calendar number that would place January first.
            # Until this block existed that correction lived only in the
            # SemanticPlan object: the prompt still rendered the resolver's
            # original dimension under SEMANTIC CONTEXT, and nothing told the
            # model to group or order by the configured one, so the plan's
            # decision never reached SQL. This is prompt-only - it does not
            # touch what SemanticPlanBuilder decides, does not change
            # dimension_objects/SEMANTIC CONTEXT, and does not touch the guard.
            for d in semantic_plan.dimensions:
                dim_lines = [
                    f"Business Dimension: {d.business_name}",
                    f"Physical Dimension: {d.column_name}",
                    (
                        f"Authoritative Binding: You MUST use physical column "
                        f"'{d.column_name}' for any references to Business "
                        f"Dimension '{d.business_name}' in SELECT and GROUP BY."
                    ),
                ]
                if d.order_by_column:
                    dim_lines.append(
                        f"Authoritative Ordering: You MUST ORDER BY physical "
                        f"column '{d.order_by_column}' when the query is "
                        f"broken down by Business Dimension '{d.business_name}' "
                        f"- it is the configured sort column and is not "
                        f"necessarily the same column as the one displayed or "
                        f"grouped by."
                    )
                semantic_plan_context_lines.append("\n".join(dim_lines))

        semantic_plan_context = "\n".join(semantic_plan_context_lines) if semantic_plan_context_lines else "None"

        # Per-table semantic contract, for snapshot tables only.
        #
        # A pre-aggregated table cannot be understood from its schema: CY and
        # PYTD look like ordinary numbers, and production proved the generator
        # will date-filter them if nothing says otherwise. The contract is
        # built from the same configuration the resolver uses, so the rules
        # exist in exactly one place, and it is empty for tables that have a
        # real business date and need none of it.
        table_contract = ""
        try:
            from semantic.table_contract import build_table_contract
            table_contract = build_table_contract(
                active_connection["connection_id"], table_names
            )
        except Exception as exc:
            print(f"\n[Table contract] skipped: {exc}")

        table_contract_section = (
            "===========================================================\n"
            "TABLE SEMANTIC CONTRACT - AUTHORITATIVE, OVERRIDES INFERENCE\n"
            "===========================================================\n\n"
            f"{table_contract}\n"
        ) if table_contract else ""

        prompt = f"""
You are an expert Microsoft SQL Server SQL generator for an Enterprise Conversational Analytics Platform.

Your objective is to generate ONE correct Microsoft SQL Server SELECT query.

===========================================================
USER QUESTION
===========================================================

{question}

===========================================================
CONVERSATION HISTORY
===========================================================

{history_text}

{temporal_section}

===========================================================
SEMANTIC RUNTIME
===========================================================

{runtime_context}

===========================================================
SEMANTIC PLAN
===========================================================

{semantic_plan_context}

{table_contract_section}
===========================================================
SEMANTIC CONTEXT
===========================================================

{semantic_context}

===========================================================
RELEVANT METRICS
===========================================================

{semantic_result["metrics"]}

===========================================================
RELEVANT DIMENSIONS
===========================================================

{semantic_result["dimensions"]}

===========================================================
MATCHED DIMENSION VALUES
===========================================================

{semantic_result.get("value_matches", [])}
{required_filters_section}

===========================================================
PREVIOUS SUCCESSFUL QUERIES
===========================================================

{examples_text}

===========================================================
METADATA RULES
===========================================================

{metadata_rules_text}

===========================================================
DATABASE SCHEMA
===========================================================

{schema_text}

===========================================================
SQL GENERATION RULES
===========================================================

1. Database Schema is the only physical source of truth.
2. Never invent tables.
3. Never invent columns.
4. Generate Microsoft SQL Server SQL only.
5. Generate exactly ONE executable SELECT statement.
6. Never generate INSERT.
7. Never generate UPDATE.
8. Never generate DELETE.
9. Never generate DROP.
10. Never generate ALTER.
11. Never generate CREATE.

===========================================================
SEMANTIC SQL RULES
===========================================================

1. Use the Semantic Runtime as the primary reasoning source.
2. Use the Database Schema only for validation.
3. Use only the Resolved Tables unless another table is absolutely required.
4. Use only the Relationships provided in the Semantic Runtime.
5. Never invent joins.
6. Prefer descriptive business columns over technical columns.
7. Technical keys must only be used in JOIN conditions unless the user explicitly requests them.
8. Respect all Metadata Rules.
9. Follow the style demonstrated by Previous Successful Queries whenever possible.
10. If a dimension has a specified SQL Expression under SEMANTIC CONTEXT, you MUST use that SQL Expression in the SELECT, GROUP BY, WHERE, and ORDER BY clauses instead of the raw physical column name.
11. Every REQUIRED VALUE FILTER listed in the prompt is an authoritative semantic decision already resolved by the backend. The generated SQL MUST apply every required value filter using the specified column or a validated/required join path to constrain the query results. You are NOT allowed to decide if the filter is relevant, nor are you allowed to omit, replace, generalize, reinterpret, silently discard, or merely comment on a required value filter.
12. You MUST use the exact physical column name specified for the metric in the SEMANTIC PLAN or SEMANTIC CONTEXT (e.g. use 'PY' for Sales if Column/Physical Metric is PY, 'PPY' if Column/Physical Metric is PPY, etc.). The physical column binding is authoritative and must not be overridden or defaulted back to 'CY'. When Temporal Strategy is SNAPSHOT and Date Filter Required is NO, you MUST NOT generate any additional date-column predicate or filter (such as YEAR(createddate) = ... or createddate BETWEEN ...) representing the same time period.
13. Where the SEMANTIC PLAN section lists a Business Dimension with a Physical Dimension, that Physical Dimension is the authoritative column for that dimension in SELECT and GROUP BY - it overrides any different physical column shown for the same Business Dimension under SEMANTIC CONTEXT or RELEVANT DIMENSIONS. Where that Business Dimension also carries an Authoritative Ordering line, you MUST ORDER BY the physical column it names whenever the query is broken down by that dimension. The ordering column is not necessarily the column displayed or grouped by - do not substitute the grouping column for it.

===========================================================
SQL SERVER RULES
===========================================================

- Never use ROW_NUMBER() inside GROUP BY.
- Never add integers directly to DATE values.
- Use DATEADD() for all date arithmetic.
- Window functions are allowed only in SELECT or ORDER BY.
- Always qualify ambiguous columns with table names.
- Use aliases only when they improve readability.

===========================================================
FOLLOW-UP RULES
===========================================================

If conversation history exists:

- Preserve previous analytical intent.
- Understand references such as:
    • show only
    • those
    • them
    • previous result
    • what about
    • instead
    • top
    • filter
    • sort

Modify the previous SQL whenever appropriate instead of generating an entirely unrelated query.

===========================================================
OUTPUT RULES
===========================================================

- Return SQL only.
- No explanation.
- No markdown.
- No code fences.
- Never output <think>.
- Never output </think>.
- First character must be SELECT.

"""

        # Estimate tokens: roughly 1 token = 4 characters or word count
        estimated_tokens = len(prompt) // 4
        
        print("\n========== PROMPT ==========")
        print(f"Prompt Length: {len(prompt)}")
        print(f"Prompt Tokens (estimated): {estimated_tokens}")
        print(f"Database Type: {active_connection.get('database_type')}")
        print(f"Schema Tables Used: {', '.join(table_names) if table_names else 'None'}")
        print(f"Semantic Objects: {len(semantic_result.get('metric_objects', [])) + len(semantic_result.get('dimension_objects', []))}")
        print(f"Conversation Messages: {len(history) if history else 0}")
        print("================================\n")

        return prompt, semantic_result, runtime_context


def build_sql_prompt(
    question: str,
    history = None,
    company_id = None,
    connection_id: Optional[str] = None,
    settings: Optional[TimeSettings] = None,
    context: Optional[SemanticExecutionContext] = None,
    clarified_candidate = None
) -> tuple[str, dict, str]:
    builder = PromptBuilder()
    return builder.build_sql_prompt(
        question=question,
        history=history,
        company_id=company_id,
        connection_id=connection_id,
        settings=settings,
        context=context,
        clarified_candidate=clarified_candidate
    )


def build_summary_prompt(
    question,
    sql_query,
    serialized_data,
    template
):

    prompt = f"""
    User Question:
    {question}

    SQL Query:
    {sql_query}

    Query Result:
    {serialized_data}

    {template}
    """

    return prompt
