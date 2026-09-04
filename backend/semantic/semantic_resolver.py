from semantic import test_metrics
from semantic import discovery_service
import re
from sqlalchemy import text

from database import engine
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic import runtime_config_filter
from core.logger import debug_print as print

def _normalize_string(s: str) -> str:
    if not s:
        return ""
    return " ".join(s.lower().split())


def _get_words(s: str) -> list:
    if not s:
        return []
    # Replace underscores with spaces, then split by non-alphanumeric characters
    cleaned = re.sub(r'[^a-zA-Z0-9]', ' ', s.lower().replace("_", " "))
    return [w for w in cleaned.split() if w]


def _find_phrase_spans(phrase: str, text: str):
    if not phrase or not text:
        return []
    # Match the phrase ensuring boundaries are not alphanumeric or underscore
    pattern = rf"(?<![a-zA-Z0-9_]){re.escape(phrase)}(?![a-zA-Z0-9_])"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def _find_whole_word_match_spans(name: str, text: str):
    name_words = _get_words(name)
    if not name_words:
        return []
    spans = []
    for word in name_words:
        pattern = rf"(?<![a-zA-Z0-9]){re.escape(word)}(?![a-zA-Z0-9])"
        word_spans = [(m.start(), m.end()) for m in re.finditer(pattern, text)]
        if not word_spans:
            return []  # All words of the name must be present in the text
        spans.extend(word_spans)
    spans.sort()
    return spans


def _spans_overlap(span1, span2):
    return max(span1[0], span2[0]) < min(span1[1], span2[1])


def _stem_word(w: str) -> str:
    w = w.lower()
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 3:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    if w.endswith("ing") and len(w) > 4:
        return w[:-3]
    return w


def _get_match_info(technical_name: str, business_name: str, synonyms: str, question: str):
    """
    Computes a match score, matched length, and spans based on deterministic ranking.
    
    Priority Rules:
    1. Exact technical name equals complete user phrase
    2. Exact business name equals complete user phrase
    3. Exact business phrase contained in the question
    4. Whole-word technical name match
    5. Whole-word business name match (ignoring noise words like English/Name)
    6. Synonym match
    7. Stemmed/Domain synonym token overlap match
    """
    if not question:
        return 0, 0, [], None, None
        
    q_norm = _normalize_string(question)
    tech_norm = _normalize_string(technical_name)
    bus_norm = _normalize_string(business_name)
    
    matches = []
    
    # Priority 1: Exact technical name equals complete user phrase
    if tech_norm and q_norm == tech_norm:
        matches.append((50000, len(q_norm), [(0, len(q_norm))], "Technical Name", technical_name))
        
    # Priority 2: Exact business name equals complete user phrase
    if bus_norm and q_norm == bus_norm:
        matches.append((40000, len(q_norm), [(0, len(q_norm))], "Business Name", business_name))
        
    # Priority 3: Exact business phrase contained in the question
    bus_phrase_spans = _find_phrase_spans(bus_norm, q_norm)
    if bus_phrase_spans:
        matches.append((30000, len(bus_norm), bus_phrase_spans, "Business Name", business_name))
        
    # Priority 4: Whole-word technical name match
    tech_phrase_spans = _find_phrase_spans(tech_norm, q_norm)
    if tech_phrase_spans:
        matches.append((20000, len(tech_norm), tech_phrase_spans, "Technical Name", technical_name))
        
    tech_word_spans = _find_whole_word_match_spans(technical_name, q_norm)
    if tech_word_spans:
        matches.append((20000, len(tech_norm), tech_word_spans, "Technical Name", technical_name))
        
    # Priority 5: Whole-word business name match (with noise word filtering)
    bus_words = _get_words(business_name)
    noise_words = {"english", "spanish", "french", "name", "description", "desc", "type", "number", "key", "id", "flag", "code"}
    core_bus_words = [w for w in bus_words if w.lower() not in noise_words]
    
    if core_bus_words:
        core_bus_name = " ".join(core_bus_words)
        core_spans = _find_whole_word_match_spans(core_bus_name, q_norm)
        if core_spans:
            matches.append((15000, len(core_bus_name), core_spans, "Business Name", business_name))

    bus_word_spans = _find_whole_word_match_spans(business_name, q_norm)
    if bus_word_spans:
        matches.append((10000, len(bus_norm), bus_word_spans, "Business Name", business_name))

    # Priority 6: Database Synonym match
    if synonyms:
        synonym_list = [s.strip().lower() for s in synonyms.split(",") if s.strip()]
        for synonym in synonym_list:
            synonym_spans = _find_phrase_spans(synonym, q_norm)
            if synonym_spans:
                matches.append((9000, len(synonym), synonym_spans, "Synonym", synonym))
                
    # Priority 7: Stemmed & Domain Synonym Overlap Match
    q_tokens = _get_words(question)
    q_stems = {_stem_word(t) for t in q_tokens}
    
    candidate_tokens = _get_words(business_name) + _get_words(technical_name)
    cand_stems = [_stem_word(t) for t in candidate_tokens if t.lower() not in noise_words]
    
    matched_stems = [
        s for s in cand_stems
        if s in q_stems
    ]

    match_ratio = len(set(matched_stems)) / max(len(set(cand_stems)), 1)


    if match_ratio >= 0.5:
        score = int(match_ratio * 8000)

        # Gate 3 Step 19b - report the span of the question tokens that
        # actually matched, not the whole question.
        #
        # Every other priority above reports the span of the words it
        # matched; this one claimed [(0, len(q_norm))]. A plural dimension
        # name only ever reaches this path - "cities" matches no literal,
        # whole-word or synonym rule - so it arrived at _remove_overlaps
        # claiming the entire question, collided with the metric's span
        # ("sales"), and was discarded. That is why every plural-qualified
        # question resolved dimensions=[] while its singular form resolved
        # correctly:
        #
        #   "…Chennai city"   -> (30000, 4, [(23, 27)], 'Business Name')
        #   "…Chennai cities" -> ( 8000, 2, [(0, 29)],  'Stem Overlap')
        #
        # The stems themselves were always right; only the span contract
        # was wrong. Score and matched length are deliberately unchanged,
        # and no stem matching is broadened - this is purely the span.
        matched_stem_set = set(matched_stems)
        stem_spans = [
            (m.start(), m.end())
            for m in re.finditer(r"[a-zA-Z0-9]+", q_norm)
            if _stem_word(m.group(0)) in matched_stem_set
        ]

        # If the matched stems cannot be located in the normalized question
        # the candidate is dropped rather than falling back to the whole
        # question, which is the behaviour being corrected here.
        if stem_spans:
            matches.append((
                score,
                len(matched_stems),
                stem_spans,
                "Stem Overlap",
                business_name,
            ))

    if not matches:
        return 0, 0, [], None, None

    # Sort matches by matched length desc, then score desc
    matches.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return matches[0]


class SemanticResolver:

    @staticmethod
    def _fetch_active_metadata(connection_id):
        print("Entered: _fetch_active_metadata")
        """
        Fetches active metrics and dimensions from database.
        """
        # Gate 3 P0 - the administrator's exclusions are applied here.
        #
        # These two queries used to filter on is_active alone, which meant a
        # column excluded in the Semantic Control Center was still offered to
        # every question. The predicates come from runtime_config_filter so
        # that a database without migration 004 keeps working rather than
        # failing on every question; see that module for why.
        metric_query = f"""
        SELECT
            metric_name,
            business_name,
            table_name,
            column_name,
            aggregation_type,
            synonyms
        FROM semantic_metrics
        WHERE connection_id = :connection_id
          AND is_active = 1
          {runtime_config_filter.metric_filter()}
        """

        dimension_query = f"""
        SELECT
            dimension_name,
            business_name,
            table_name,
            column_name,
            synonyms,
            semantic_category,
            {runtime_config_filter.dimension_role_column()},
            {runtime_config_filter.dimension_confirmed_column()}
        FROM semantic_dimensions
        WHERE connection_id = :connection_id
          AND is_active = 1
          {runtime_config_filter.dimension_filter()}
        """

        with engine.connect() as conn:
            metric_rows = conn.execute(
                text(metric_query),
                {"connection_id": connection_id}
            ).fetchall()
            
            dimension_rows = conn.execute(
                text(dimension_query),
                {"connection_id": connection_id}
            ).fetchall()

        print("\n========== SEMANTIC METADATA LOAD DEBUG ==========")
        print(f"Incoming connection_id: {connection_id}")
        print(f"Metrics SQL:\n{metric_query}")
        print(f"Dimensions SQL:\n{dimension_query}")
        print(f"Rows returned from semantic_metrics: {len(metric_rows)}")
        print(f"Rows returned from semantic_dimensions: {len(dimension_rows)}")
        print("==================================================\n")



        return metric_rows, dimension_rows

    @staticmethod
    def _generate_candidates(metric_rows, dimension_rows, question):
        """
        Scores and creates candidate matches from raw metadata.
        """
        candidates = []

        # Process Metrics
        for row in metric_rows:
            metric_name = row[0]
            business_name = row[1]
            score, matched_len, spans, matched_by, matched_text = _get_match_info(metric_name, business_name,row[5], question)
            if score > 0:
                candidates.append({
                    "score": score,
                    "length": matched_len,
                    "type": "metric",
                    "metric_name": metric_name,
                    "business_name": business_name,
                    "table_name": row[2],
                    "column_name": row[3],
                    "aggregation_type": row[4],
                    "matched_by": matched_by,
                    "matched_text": matched_text,
                    "spans": spans
                })

        # Process Dimensions
        for row in dimension_rows:
            dimension_name = row[0]
            business_name = row[1]
            score, matched_len, spans, matched_by, matched_text = _get_match_info(dimension_name, business_name, row[4], question)
            if score > 0:
                candidates.append({
                    "score": score,
                    "length": matched_len,
                    "type": "dimension",
                    "dimension_name": dimension_name,
                    "business_name": business_name,
                    "table_name": row[2],
                    "column_name": row[3],
                    "matched_by": matched_by,
                    "matched_text": matched_text,
                    "spans": spans,
                    "semantic_category": row[5] if len(row) > 5 else None,
                    # Gate 3 P0 - carried, not acted on. Step 17 uses this to
                    # tell a grouping dimension from a filter dimension; until
                    # then it simply travels with the candidate.
                    "dimension_role": row[6] if len(row) > 6 else None
                })

        return candidates

    @staticmethod
    def _overlap_sort_key(candidate):
        """
        Gate 3 RC-03b - generic phrase-level precedence for overlap resolution.

        _get_match_info's priority tiers (50000..8000) encode WHICH FIELD
        matched - technical name, business name, synonym, or stem overlap -
        not how much of the question that field explained. Comparing
        candidates by raw tier therefore let a one-word technical name always
        beat a longer, more specific business synonym: "due" (Business Name,
        tier 30000, 3 chars) always outranked "due amount" (Synonym, tier
        9000, 10 chars) for the question "Show due amount", even though the
        synonym is the administrator's own configured phrase for a completely
        different metric and explains more of what was actually asked.

        Three tiers by evidence KIND, not by field:

          bucket 2 (score >= 40000) - the ENTIRE question equals the
          candidate's own name (Priority 1/2). This is already the strongest
          possible signal and its matched length is already the maximum any
          candidate can reach, so it keeps the original score-first ordering
          unchanged.

          bucket 1 (9000 <= score < 40000) - a literal, administrator
          configured phrase - technical name, business name, or synonym -
          found in the question (Priority 3-6). These are the SAME kind of
          evidence differing only in which field held the phrase, so within
          this bucket the longer matched phrase wins: more of the
          administrator's own configured text explained is stronger evidence
          of intent than which field it happened to live in. Score remains
          the tie-breaker when two phrases match the same length.

          bucket 0 (score < 9000) - heuristic stemmed token overlap
          (Priority 7), not a literal configured phrase. Kept on its original
          score-first ordering so it is never strengthened relative to a
          genuine phrase match - it must keep losing to any Priority 1-6
          candidate exactly as before.

        This is data-driven throughout: nothing here names a metric, a
        dimension, or a phrase. It reorders exactly one thing - whether tier
        or length is compared first - and only inside the bracket where both
        candidates are already genuine configured-phrase evidence.
        """
        score = candidate["score"]
        length = candidate["length"]
        is_metric = candidate["type"] == "metric"

        if score >= 40000:
            return (2, score, is_metric, length)
        if score >= 9000:
            return (1, length, is_metric, score)
        return (0, score, is_metric, length)

    @staticmethod
    def _remove_overlaps(candidates):
        candidates.sort(key=SemanticResolver._overlap_sort_key, reverse=True)

        selected_candidates = []
        global_selected_spans = []

        for candidate in candidates:
            has_non_overlapping_span = False
            valid_spans = []
            for span in candidate["spans"]:
                if not any(_spans_overlap(span, s_span) for s_span in global_selected_spans):
                    has_non_overlapping_span = True
                    valid_spans.append(span)
            
            if has_non_overlapping_span:
                # Keep the candidate and track its non-overlapping spans
                selected_candidate = dict(candidate)
                selected_candidate["spans"] = valid_spans
                selected_candidates.append(selected_candidate)
                global_selected_spans.extend(valid_spans)

        return selected_candidates

    @staticmethod
    def resolve(connection_id, question, clarified_candidate=None, previous_semantic_context=None):
        print("Entered: resolve")
        print(f"connection_id = {connection_id}")
        """
        Resolves semantic metrics and dimensions based on deterministic ranking and overlap resolution.
        """
        # 1. Candidate Generation & Fetching
        metric_rows, dimension_rows = SemanticResolver._fetch_active_metadata(connection_id)
        candidates = SemanticResolver._generate_candidates(metric_rows, dimension_rows, question)

        # 2. Extract resolved metric tables by doing a quick first pass on metrics
        temp_selected = SemanticResolver._remove_overlaps(candidates)
        resolved_metric_tables = set()
        for cand in temp_selected:
            if cand["type"] == "metric":
                resolved_metric_tables.add(cand["table_name"])

        # 3. Second ranking pass: Apply SAME_TABLE_BONUS
        SAME_TABLE_BONUS = 0.35
        if resolved_metric_tables:
            print("\n========== CONTEXT RANKING ==========")
            for table_name in sorted(resolved_metric_tables):
                print(f"Metric Table : {table_name}")
            print("")

            for cand in candidates:
                if isinstance(cand, dict) and cand.get("type") == "dimension":
                    score_val = cand.get("score")
                    keyword_score = float(score_val) if isinstance(score_val, (int, float)) else 0.0
                    table_bonus = 0.0
                    tname = cand.get("table_name")
                    if isinstance(tname, str) and tname in resolved_metric_tables:
                        table_bonus = SAME_TABLE_BONUS
                    cand["score"] = keyword_score + table_bonus
                    
                    bname = cand.get("business_name")
                    bname_str = str(bname) if bname is not None else ""
                    print(f"Candidate: {bname_str}")
                    print(f"Keyword Score : {keyword_score:.2f}")
                    print(f"Table Bonus : +{table_bonus:.2f}")
                    print(f"Final Score : {keyword_score + table_bonus:.2f}")
                    print("")

        # 4. Overlap Removal
        selected_candidates = SemanticResolver._remove_overlaps(candidates)

        # Build selected dimension list
        selected_dims = []
        if isinstance(selected_candidates, list):
            for cand in selected_candidates:
                if isinstance(cand, dict) and cand.get("type") == "dimension":
                    bname = cand.get("business_name")
                    if isinstance(bname, str):
                        selected_dims.append(bname)
                        
        # Build rejected dimension list
        rejected_dims = []
        for cand in candidates:
            if isinstance(cand, dict) and cand.get("type") == "dimension":
                bname = cand.get("business_name")
                if isinstance(bname, str) and bname not in selected_dims:
                    rejected_dims.append(bname)
        
        if resolved_metric_tables:
            print("Selected Dimension:")
            if selected_dims:
                for s in sorted(set(selected_dims)):
                    print(f"- {s}")
            else:
                print("- None")
            print("Rejected Dimensions:")
            if rejected_dims:
                for r in sorted(set(rejected_dims)):
                    print(f"- {r}")
            else:
                print("- None")
            print("=====================================")

        # 3. Final Selection & Deduplication
        metrics = []
        seen_metrics = set()
        dimensions = []
        seen_dimensions = set()
        metric_debug = []
        dimension_debug = []

        for candidate in selected_candidates:
            bname = candidate["business_name"]
            if candidate["type"] == "metric":
                if bname not in seen_metrics:
                    metrics.append(bname)
                    metric_debug.append({
                        "business_name": candidate["business_name"],
                        "technical_name": candidate["metric_name"],
                        "matched_by": candidate["matched_by"],
                        "matched_text": candidate["matched_text"],
                        "table_name": candidate["table_name"],
                        "column_name": candidate["column_name"],
                        "aggregation": candidate["aggregation_type"]
                    })
                    seen_metrics.add(bname)
            else:
                if bname not in seen_dimensions:
                    dimensions.append(bname)
                    dimension_debug.append({
                        "business_name": candidate["business_name"],
                        "technical_name": candidate["dimension_name"],
                        "matched_by": candidate["matched_by"],
                        "matched_text": candidate["matched_text"],
                        "table_name": candidate["table_name"],
                        "column_name": candidate["column_name"],
                        "semantic_category": candidate.get("semantic_category")
                    })
                    seen_dimensions.add(bname)



        print("\n========== SEMANTIC CACHE ==========")
        print(f"Metrics Loaded    : {len(metrics)}")
        print(f"Dimensions Loaded : {len(dimensions)}")

        print("\nSample Metrics:")
        for metric in metrics[:5]:
            print(metric)

        print("\nSample Dimensions:")
        for dimension in dimensions[:5]:
            print(dimension)

        # Build rich unique objects
        metric_objects = []
        seen_metric_keys = set()
        for candidate in selected_candidates:
            if candidate["type"] == "metric":
                key = (candidate["metric_name"], candidate["table_name"], candidate["column_name"])
                if key not in seen_metric_keys:
                    seen_metric_keys.add(key)
                    metric_objects.append({
                        "metric_name": candidate["metric_name"],
                        "business_name": candidate["business_name"],
                        "table_name": candidate["table_name"],
                        "column_name": candidate["column_name"],
                        "aggregation_type": candidate["aggregation_type"]
                    })

        # Gate 3 Item #2 - carry the previous turn's metric into a follow-up
        # that names no metric of its own.
        #
        # Metric resolution above runs on the CURRENT question's text only.
        # "How about Ramraj brand?" matches the Brand dimension but no
        # metric, so metric_objects came back empty even though a metric was
        # clearly implied by the conversation - the plan built from this turn
        # had no metric at all.
        #
        # Carried ONLY when every one of the following holds, each guarding
        # against guessing (Gate 3's carry-forward-only-validated-context
        # rule):
        #   - metric_objects is empty: an explicit current-turn metric always
        #     wins outright, because this block never runs otherwise.
        #   - previous_semantic_context names EXACTLY ONE previous metric: a
        #     multi-metric or absent previous turn is ambiguous and is left
        #     alone rather than guessed from.
        #   - the current question has at least one non-stopword token: guards
        #     against carrying a metric into a turn with no usable content at
        #     all (an empty or purely conversational message), using the same
        #     STOPWORDS vocabulary already trusted elsewhere in this module
        #     for "is this word meaningful" decisions - no new heuristic.
        #
        # Read only from previous_semantic_context's own structured fields
        # (table_name/column_name/business_name/metric_name) - never from
        # prior SQL or raw text. Nothing here names a metric, dimension, or
        # phrase; it generalizes to any configured metric.
        if not metric_objects and previous_semantic_context:
            prev_metrics = previous_semantic_context.get("metrics") or []
            if len(prev_metrics) == 1:
                from semantic.matching.stopwords import STOPWORDS
                question_has_content = any(
                    w not in STOPWORDS for w in _get_words(question)
                )
                prev_metric = prev_metrics[0]
                if (
                    question_has_content
                    and isinstance(prev_metric, dict)
                    and prev_metric.get("table_name")
                    and prev_metric.get("column_name")
                ):
                    carried_business_name = (
                        prev_metric.get("business_name")
                        or prev_metric.get("metric_name")
                    )
                    metric_objects.append({
                        "metric_name": prev_metric.get("metric_name")
                                       or carried_business_name,
                        "business_name": carried_business_name,
                        "table_name": prev_metric.get("table_name"),
                        "column_name": prev_metric.get("column_name"),
                        "aggregation_type": prev_metric.get("aggregation_type"),
                    })
                    # Keep the earlier business-name-only list (used for
                    # display/logging) consistent with metric_objects, the
                    # field every downstream consumer (plan builder, guard,
                    # benchmark) actually reads.
                    if carried_business_name and carried_business_name not in metrics:
                        metrics.append(carried_business_name)

        # Apply temporal intent metric binding
        from semantic.temporal.detector import TemporalDetector
        from semantic.temporal.enums import TimeIntentType

        try:
            temporal_intent = TemporalDetector().detect(question)
        except Exception:
            temporal_intent = None

        intent_type = getattr(temporal_intent, "intent_type", None)
        intent_cls = temporal_intent.__class__.__name__ if temporal_intent else ""

        # Snapshot period rebinding.
        #
        # On a snapshot table a period is a separate column, so "last year's
        # sales" is not a date filter - it is a different column. This block
        # moves a metric from the current-period column to the previous-period
        # one, and pairs the two for a comparison.
        #
        # It used to name the columns and the table literally - "CY", "PY" and
        # QB_MDJMD_SALES_5YRS_SUMMARY - which meant it could only ever work for
        # one customer's Sales table, and it fabricated metric rows with
        # hand-written names. Both now come from Gate 2 configuration:
        # SnapshotConfigLoader supplies the period columns for whichever table
        # this connection has configured, and the names come from the metric
        # registry that was already loaded above. Nothing here is read from the
        # database that was not already fetched for this request - the loader is
        # cached per connection and metric_rows is the metadata this call
        # started with.
        #
        # If the connection has no snapshot configuration, or no column is
        # bound to a period, the block does nothing: a table whose periods are
        # rows rather than columns must not be rewritten this way.
        # Gate 3 Step 7a - the configuration is per TABLE, so it is read for the
        # table this request's own metric sits on rather than for a single
        # connection-wide snapshot table. The previous call asked
        # for_connection(), whose loader settles the question with
        # SELECT TOP 1 ... ORDER BY table_name: one SNAPSHOT table per
        # connection won alphabetically and a metric on any other one was
        # rewritten against the wrong table's columns, or not rewritten at all.
        #
        # A table that is not configured SNAPSHOT comes back unconfigured, so
        # current_column and previous_column stay None and every branch below
        # is skipped - which is what must happen for a table whose periods are
        # rows rather than columns.
        from semantic.temporal.snapshot_config import SnapshotConfig, SnapshotConfigLoader

        snapshot_config = SnapshotConfig()
        snapshot_table = None

        for metric_obj in metric_objects:
            candidate_table = metric_obj.get("table_name")
            if not candidate_table or candidate_table == snapshot_table:
                continue
            candidate_config = SnapshotConfigLoader.for_table(
                connection_id, candidate_table
            )
            if candidate_config.is_configured:
                snapshot_config = candidate_config
                snapshot_table = candidate_table
                break

        if snapshot_table is None:
            # No metric sits on a configured snapshot table - which is also the
            # case when there is no connection, or the connection has never
            # been configured. Fall back to the connection-wide answer, exactly
            # as this code did before Step 7a, so an unconfigured environment
            # keeps behaving as it did. Where a metric DID resolve per table,
            # that precise configuration is used and this branch never runs.
            snapshot_config = SnapshotConfigLoader.for_connection(connection_id)
            snapshot_table = snapshot_config.table_name

        current_column = snapshot_config.column_for_offset(0)
        previous_column = snapshot_config.column_for_offset(1)

        def _is_snapshot_metric(metric_obj, column_name):
            """A metric bound to the given period column of the snapshot table."""
            return (
                column_name is not None
                and metric_obj.get("column_name") == column_name
                and metric_obj.get("table_name") == snapshot_table
            )

        def _configured_metric(column_name):
            """
            The registered metric for a period column, from the metadata this
            request already loaded. Returns None when the administrator has not
            configured one, in which case no metric is invented for it.
            """
            if not column_name:
                return None

            for row in metric_rows:
                # (metric_name, business_name, table_name, column_name, ...)
                if row[2] == snapshot_table and row[3] == column_name:
                    return {
                        "metric_name": row[0],
                        "business_name": row[1],
                        "table_name": row[2],
                        "column_name": row[3],
                        "aggregation_type": row[4] or "SUM"
                    }
            return None

        snapshot_periods_configured = bool(current_column or previous_column)

        if not snapshot_periods_configured:
            pass

        elif intent_type in (TimeIntentType.PREVIOUS_YEAR, "PREVIOUS_YEAR") or intent_cls == "PreviousYearIntent":
            previous_metric = _configured_metric(previous_column)

            if previous_metric:
                for m in metric_objects:
                    if _is_snapshot_metric(m, current_column):
                        m["metric_name"] = previous_metric["metric_name"]
                        m["business_name"] = previous_metric["business_name"]
                        m["column_name"] = previous_metric["column_name"]

            metrics = [m["business_name"] for m in metric_objects]

        elif intent_type in (TimeIntentType.YEAR_COMPARISON, "YEAR_COMPARISON") or intent_cls == "YearComparisonIntent":
            has_current = any(_is_snapshot_metric(m, current_column) for m in metric_objects)
            has_previous = any(_is_snapshot_metric(m, previous_column) for m in metric_objects)

            if (has_current or has_previous) and not (has_current and has_previous):
                counterpart = _configured_metric(
                    previous_column if has_current else current_column
                )

                # Only a configured metric is added. Inventing one, as the
                # previous hardcoded version did, would put a column into the
                # plan that the administrator never approved.
                if counterpart:
                    metric_objects.append(counterpart)

            metrics = [m["business_name"] for m in metric_objects]

        dimension_objects = []
        seen_dim_keys = set()
        for candidate in selected_candidates:
            if candidate["type"] == "dimension":
                key = (candidate["dimension_name"], candidate["table_name"], candidate["column_name"])
                if key not in seen_dim_keys:
                    seen_dim_keys.add(key)
                    dimension_objects.append({
                        "dimension_name": candidate["dimension_name"],
                        "business_name": candidate["business_name"],
                        "table_name": candidate["table_name"],
                        "column_name": candidate["column_name"],
                        "semantic_category": candidate.get("semantic_category"),
                        "dimension_role": candidate.get("dimension_role")
                    })

        dimension_context = [
            {
                "dimension_name": cand.get("dimension_name"),
                "business_name": cand.get("business_name"),
                "table_name": cand.get("table_name"),
                "column_name": cand.get("column_name"),
                "synonyms": cand.get("synonyms"),
                "matched_text": cand.get("matched_text"),
                "spans": cand.get("spans")
            }
            for cand in candidates
            if cand.get("type") == "dimension"
        ]

        # Gate 3 - the tokens a selected METRIC candidate's own configured
        # phrase (technical name, business name, or synonym) already
        # accounted for in this question. Passed to DimensionValueResolver so
        # a value candidate whose only question evidence is the same words -
        # "due" for "Show due amount", already spent on the Pending Amount
        # synonym "due amount" - is not treated as independent dimension/
        # value evidence. Generic: built only from whichever metric this
        # connection's own configuration matched, never a fixed word list.
        metric_claimed_tokens = set()
        for candidate in selected_candidates:
            if candidate.get("type") == "metric":
                metric_claimed_tokens.update(_get_words(candidate.get("matched_text") or ""))

        value_matches = DimensionValueResolver.resolve(
            connection_id,
            question,
            clarified_candidate=clarified_candidate,
            dimension_context=dimension_context,
            previous_semantic_context=previous_semantic_context,
            current_metrics=metric_objects,
            metric_claimed_tokens=metric_claimed_tokens,
            all_metrics=metric_rows,
            all_dimensions=dimension_rows
        )

        # --------------------------------------------------
        # Gate 3 Step 21a - an explicit value that does not resolve.
        #
        # ResolutionStatus.NO_MATCH was produced by the matching pipeline and
        # read by nothing, so a question naming a value that does not exist
        # still came back executable:
        #
        #   "Show sales for xyzabc" -> metrics=['C Y'], values=[], PARTIAL
        #
        # which answers "all sales" - a question the user did not ask.
        #
        # The frozen rule is: an explicit value reference that does not resolve
        # sets retrieval_status = INSUFFICIENT, and the existing SemanticGate
        # (semantic/semantic_gate.py, called from prompt_builder) refuses to
        # generate SQL for that status. No second blocking mechanism is added.
        #
        # Resolved metrics and dimensions are deliberately KEPT. They are what
        # lets the clarification say "I understood you want sales, but I do not
        # know 'xyzabc'" instead of pretending nothing was understood. Nothing
        # is substituted and no nearest value is chosen.
        # --------------------------------------------------

        _ambiguity_result = (
            getattr(value_matches, "resolution_result", None)
            or DimensionValueResolver.last_resolution_result
        )
        _ambiguity_status = getattr(_ambiguity_result, "status", None)
        _no_value_matched = (
            not value_matches
            and _ambiguity_status is not None
            and getattr(_ambiguity_status, "value", _ambiguity_status) == "NO_MATCH"
        )

        unresolved_terms = []

        if _no_value_matched:
            from semantic.matching.stopwords import STOPWORDS

            # Condition 2 - every word the configuration knows about, taken
            # from the metadata this request already loaded. No extra query.
            known_vocabulary = set()
            for row in metric_rows:
                for field in (row[0], row[1], row[5]):
                    known_vocabulary.update(_get_words(field or ""))
            for row in dimension_rows:
                for field in (row[0], row[1], row[4]):
                    known_vocabulary.update(_get_words(field or ""))

            # Condition 3 - words already explained by a selected candidate.
            claimed_words = set()
            for candidate in selected_candidates:
                claimed_words.update(_get_words(candidate.get("matched_text") or ""))
                claimed_words.update(_get_words(candidate.get("business_name") or ""))

            # Condition 4b - the trailing dimension words that mark a
            # value-first phrasing such as "Ramraj brand" or "Chennai city".
            #
            # Gate 3 Step 21a escalation - a configured SYNONYM is as much a
            # "this is a dimension label" marker as the business name is.
            # known_vocabulary (Condition 2, above) already reads synonyms;
            # this set did not, so an unresolved value trailing only a
            # synonym word - never the literal business name - fell through
            # Condition 4 unescalated. Generic: reads whatever synonyms this
            # connection's own configuration carries, names none of its own.
            #
            # Excludes any word that is ALSO part of a configured METRIC's own
            # vocabulary (name/business name/synonym): "amount" is a dimension
            # synonym word here but also sits inside the metric synonym "due
            # amount"/"pending amount". Without the exclusion, "Total pending
            # amount" escalated on "total" - a metric-completing word, not an
            # attempted value - because "amount" alone was enough to look like
            # a trailing dimension marker. A word that belongs to a metric's
            # own configured phrase is metric vocabulary first; it cannot
            # simultaneously stand as evidence that the PRECEDING word must be
            # a dimension value.
            metric_vocabulary = set()
            for row in metric_rows:
                for field in (row[0], row[1], row[5]):
                    metric_vocabulary.update(_get_words(field or ""))

            dimension_name_words = set()
            for row in dimension_rows:
                dimension_name_words.update(_get_words(row[1] or ""))
                dimension_name_words.update(_get_words(row[4] if len(row) > 4 else ""))
            dimension_name_words -= metric_vocabulary

            ENTITY_PREPOSITIONS = ("for", "in", "of", "at")

            question_tokens = _get_words(question)

            for index, token in enumerate(question_tokens):
                # Conditions 1, 2 and 3.
                if token in STOPWORDS:
                    continue
                if token in known_vocabulary or token in claimed_words:
                    continue

                # Condition 4 - the token must sit in an entity position.
                # Without this the guard fires on ordinary unknown words that
                # name nothing: "orders" in "Show last year pending orders",
                # "compare" in "compare current year and previous year sales".
                # Refusing those questions would be worse than the defect.
                after_preposition = (
                    index > 0
                    and question_tokens[index - 1] in ENTITY_PREPOSITIONS
                )
                before_dimension_word = (
                    index + 1 < len(question_tokens)
                    and question_tokens[index + 1] in dimension_name_words
                )

                if after_preposition or before_dimension_word:
                    unresolved_terms.append(token)

        explicit_value_unresolved = bool(unresolved_terms)

        # --------------------------------------------------
        # Retrieval Statistics
        # --------------------------------------------------

        resolved_tables = set()

        for metric in metric_objects:
            resolved_tables.add(metric["table_name"])

        for dimension in dimension_objects:
            resolved_tables.add(dimension["table_name"])

        for value in value_matches:
            resolved_tables.add(value["table_name"])

        resolved_metric_count = len(metric_objects)

        resolved_dimension_count = len(dimension_objects)

        resolved_value_count = len(value_matches)

        resolved_table_count = len(resolved_tables)


        # --------------------------------------------------
        # Retrieval Status
        # --------------------------------------------------

        # How many semantic components were resolved?
        resolved_components = 0

        if resolved_metric_count > 0:
            resolved_components += 1

        if resolved_dimension_count > 0:
            resolved_components += 1

        if resolved_value_count > 0:
            resolved_components += 1


        if explicit_value_unresolved:

            # Gate 3 Step 21a. The component count below cannot express this:
            # the question was understood well enough to know a value was
            # named, and that value matched nothing. SemanticGate refuses
            # INSUFFICIENT, so execution stops here.
            retrieval_status = "INSUFFICIENT"

            retrieval_reason = (
                "The question refers to "
                + ", ".join(sorted(set(unresolved_terms)))
                + ", which does not match any known value. "
                "No substitute value was used."
            )

        elif resolved_components == 0:

            retrieval_status = "INSUFFICIENT"

            retrieval_reason = (
                "No semantic metrics, dimensions or values could be resolved."
            )

        elif resolved_components == 1:

            retrieval_status = "PARTIAL"

            retrieval_reason = (
                "Only partial semantic context could be resolved."
            )

        else:

            retrieval_status = "COMPLETE"

            retrieval_reason = None

        # --------------------------------------------------
        # Retrieval Confidence
        # --------------------------------------------------

        confidence = 0.0

        confidence += min(
            resolved_metric_count * 0.35,
            0.35
        )

        confidence += min(
            resolved_dimension_count * 0.25,
            0.25
        )

        confidence += min(
            resolved_value_count * 0.20,
            0.20
        )

        confidence += min(
            resolved_table_count * 0.20,
            0.20
        )

        confidence = round(
            min(confidence, 1.0),
            2
        )

        followup_context = getattr(value_matches, "followup_context", None)
        if followup_context is None:
            followup_context = getattr(DimensionValueResolver, "last_followup_context", None)
        if followup_context is None:
            followup_context = {
                "applied": False,
                "reason": "NO_ELIGIBLE_PREVIOUS_CONTEXT"
            }

        return {

            "connection_id": connection_id,

            "metrics": metrics,

            "dimensions": dimensions,

            "metric_objects": metric_objects,

            "dimension_objects": dimension_objects,

            "value_matches": value_matches,

            "followup_context": followup_context,

            "retrieval": {

                "status": retrieval_status,

                "reason": retrieval_reason,

                # Gate 3 Step 21a. The value terms the question named that
                # matched nothing. Empty in the normal case. Carried so a
                # clarification can name what was not found alongside the
                # metrics and dimensions that were resolved.
                "unresolved_terms": unresolved_terms,

                "resolved_components": resolved_components,

                "resolved_metric_count": resolved_metric_count,

                "resolved_dimension_count": resolved_dimension_count,

                "resolved_value_count": resolved_value_count,

                "resolved_table_count": resolved_table_count,

                "confidence": confidence

            },

            "ambiguity_result": getattr(value_matches, "resolution_result", None) or DimensionValueResolver.last_resolution_result,

            "debug": {

                "metrics": metric_debug,

                "dimensions": dimension_debug

            }

        }