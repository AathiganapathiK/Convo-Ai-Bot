from semantic import test_metrics
from semantic import discovery_service
import re
from sqlalchemy import text

from database import engine


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
    
    # Priority 1: Exact technical name equals complete user phrase
    if tech_norm and q_norm == tech_norm:
        return 50000, len(q_norm), [(0, len(q_norm))], "Technical Name", technical_name
        
    # Priority 2: Exact business name equals complete user phrase
    if bus_norm and q_norm == bus_norm:
        return 40000, len(q_norm), [(0, len(q_norm))], "Business Name", business_name
        
    # Priority 3: Exact business phrase contained in the question
    bus_phrase_spans = _find_phrase_spans(bus_norm, q_norm)
    if bus_phrase_spans:
        return 30000, len(bus_norm), bus_phrase_spans, "Business Name", business_name
        
    # Priority 4: Whole-word technical name match
    tech_phrase_spans = _find_phrase_spans(tech_norm, q_norm)
    if tech_phrase_spans:
        return 20000, len(tech_norm), tech_phrase_spans, "Technical Name", technical_name
        
    tech_word_spans = _find_whole_word_match_spans(technical_name, q_norm)
    if tech_word_spans:
        return 20000, len(tech_norm), tech_word_spans, "Technical Name", technical_name
        
    # Priority 5: Whole-word business name match (with noise word filtering)
    bus_words = _get_words(business_name)
    noise_words = {"english", "spanish", "french", "name", "description", "desc", "type", "number", "key", "id", "flag", "code"}
    core_bus_words = [w for w in bus_words if w.lower() not in noise_words]
    
    if core_bus_words:
        core_bus_name = " ".join(core_bus_words)
        core_spans = _find_whole_word_match_spans(core_bus_name, q_norm)
        if core_spans:
            return 15000, len(core_bus_name), core_spans, "Business Name", business_name

    bus_word_spans = _find_whole_word_match_spans(business_name, q_norm)
    if bus_word_spans:
        return 10000, len(bus_norm), bus_word_spans, "Business Name", business_name

    # Priority 6: Database Synonym match
    if synonyms:
        synonym_list = [s.strip().lower() for s in synonyms.split(",") if s.strip()]
        for synonym in synonym_list:
            synonym_spans = _find_phrase_spans(synonym, q_norm)
            if synonym_spans:
                return 9000, len(synonym), synonym_spans, "Synonym", synonym
                
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
        return (
                score,
                len(matched_stems),
                [(0, len(q_norm))],
                "Stem Overlap",
                business_name,
            )

    return 0, 0, [], None, None


class SemanticResolver:

    @staticmethod
    def _fetch_active_metadata(connection_id):
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
            synonyms
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
                    "spans": spans
                })

        return candidates

    @staticmethod
    def _remove_overlaps(candidates):
        """
        Deterministic overlap resolution.
        Sorts candidates by score (desc), then by length (desc), and discards overlapping matches.
        """
        # Sort candidates: primary by score desc, secondary by matched length desc
        candidates.sort(key=lambda x: (x["score"], x["length"]), reverse=True)

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
    def resolve(connection_id, question):
        """
        Resolves semantic metrics and dimensions based on deterministic ranking and overlap resolution.
        """
        # 1. Candidate Generation & Fetching
        metric_rows, dimension_rows = SemanticResolver._fetch_active_metadata(connection_id)
        candidates = SemanticResolver._generate_candidates(metric_rows, dimension_rows, question)

        # 2. Overlap Removal
        selected_candidates = SemanticResolver._remove_overlaps(candidates)

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
                        "column_name": candidate["column_name"]
                    })
                    seen_dimensions.add(bname)



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
                        "column_name": candidate["column_name"]
                    })

        return {
            "metrics": metrics,
            "dimensions": dimensions,
            "metric_objects": metric_objects,
            "dimension_objects": dimension_objects,

            "debug": {
                "metrics": metric_debug,
                "dimensions": dimension_debug
            }
        }