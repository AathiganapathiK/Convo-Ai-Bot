from semantic import test_metrics
from semantic import discovery_service
import re
from sqlalchemy import text

from database import engine
from semantic.dimension_value_resolver import DimensionValueResolver
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
        matches.append((
            score,
            len(matched_stems),
            [(0, len(q_norm))],
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
        metric_query = """
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
        """
        
        dimension_query = """
        SELECT
            dimension_name,
            business_name,
            table_name,
            column_name,
            synonyms,
            semantic_category
        FROM semantic_dimensions
        WHERE connection_id = :connection_id
          AND is_active = 1
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
                    "semantic_category": row[5] if len(row) > 5 else None
                })

        return candidates

    @staticmethod
    def _remove_overlaps(candidates):
        # Sort candidates:
        # 1. Base score (integer part of score) descending
        # 2. Type is metric descending (metrics first to prevent dimensions from discarding them)
        # 3. Full score descending (tie-breaker for table-boosted dimensions)
        # 4. Matched length descending
        candidates.sort(key=lambda x: (int(x["score"]), x["type"] == "metric", x["score"], x["length"]), reverse=True)

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

        # Apply temporal intent metric binding
        from semantic.temporal.detector import TemporalDetector
        from semantic.temporal.enums import TimeIntentType

        try:
            temporal_intent = TemporalDetector().detect(question)
        except Exception:
            temporal_intent = None

        intent_type = getattr(temporal_intent, "intent_type", None)
        intent_cls = temporal_intent.__class__.__name__ if temporal_intent else ""

        if intent_type in (TimeIntentType.PREVIOUS_YEAR, "PREVIOUS_YEAR") or intent_cls == "PreviousYearIntent":
            for m in metric_objects:
                if m.get("column_name") == "CY" and m.get("table_name") == "QB_MDJMD_SALES_5YRS_SUMMARY":
                    m["metric_name"] = "py"
                    m["business_name"] = "P Y"
                    m["column_name"] = "PY"
            metrics = [m["business_name"] for m in metric_objects]

        elif intent_type in (TimeIntentType.YEAR_COMPARISON, "YEAR_COMPARISON") or intent_cls == "YearComparisonIntent":
            has_cy = any(m.get("column_name") == "CY" for m in metric_objects)
            has_py = any(m.get("column_name") == "PY" for m in metric_objects)
            if (has_cy or has_py) and not (has_cy and has_py):
                if has_cy and not has_py:
                    metric_objects.append({
                        "metric_name": "py",
                        "business_name": "P Y",
                        "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                        "column_name": "PY",
                        "aggregation_type": "SUM"
                    })
                elif has_py and not has_cy:
                    metric_objects.append({
                        "metric_name": "cy",
                        "business_name": "C Y",
                        "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                        "column_name": "CY",
                        "aggregation_type": "SUM"
                    })
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
                        "semantic_category": candidate.get("semantic_category")
                    })

        dimension_context = [
            {
                "dimension_name": cand.get("dimension_name"),
                "business_name": cand.get("business_name"),
                "table_name": cand.get("table_name"),
                "column_name": cand.get("column_name"),
                "matched_text": cand.get("matched_text"),
                "spans": cand.get("spans")
            }
            for cand in candidates
            if cand.get("type") == "dimension"
        ]

        value_matches = DimensionValueResolver.resolve(
            connection_id,
            question,
            clarified_candidate=clarified_candidate,
            dimension_context=dimension_context,
            previous_semantic_context=previous_semantic_context,
            current_metrics=metric_objects,
            all_metrics=metric_rows,
            all_dimensions=dimension_rows
        )

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


        if resolved_components == 0:

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

            "metrics": metrics,

            "dimensions": dimensions,

            "metric_objects": metric_objects,

            "dimension_objects": dimension_objects,

            "value_matches": value_matches,

            "followup_context": followup_context,

            "retrieval": {

                "status": retrieval_status,

                "reason": retrieval_reason,

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