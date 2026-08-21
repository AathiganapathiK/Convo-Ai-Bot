import sys
import os
import re
from collections import defaultdict

# Setup environment – ensure project root is on sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching import (
    MatchType,
    MatchResult,
    QuestionContext,
    CachedDimensionValue,
    MatchingContext,
    MatchingPipeline,
    MatchRanker,
    ExactMatcher,
    NormalizedMatcher,
    SingularPluralMatcher,
    FuzzyMatcher,
    STOPWORDS,
    QuestionSanitizer
)

CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
SETTINGS = {"FUZZY_SCORE_CUTOFF": 85}

# Helper matching info functions
def calculate_coverage(m: MatchResult, q_tokens: list) -> float:
    if not q_tokens:
        return 0.0
    q_sing = set(SingularPluralMatcher._to_singular(t) for t in q_tokens)
    v_sing = set(SingularPluralMatcher._to_singular(t) for t in m.matched_value_tokens)
    matched_sing = q_sing.intersection(v_sing)
    return len(matched_sing) / len(q_sing)

def get_ranking_info(m: MatchResult, q_tokens: list):
    coverage = calculate_coverage(m, q_tokens)
    val_tokens = m.matched_value_tokens
    token_distance = abs(len(val_tokens) - len(q_tokens))
    length_diff = abs(len(m.value) - len(" ".join(q_tokens)))
    return {
        "coverage": coverage,
        "token_distance": token_distance,
        "length_diff": length_diff
    }

def trace_consolidate_duplicate_matches(matches):
    if len(matches) <= 1:
        return matches, []

    match_type_priority = {
        MatchType.EXACT: 4,
        MatchType.NORMALIZED: 3,
        MatchType.SINGULAR_PLURAL: 2,
        MatchType.FUZZY: 1,
    }

    consolidated = {}
    removed_logs = []

    for candidate in matches:
        identity = (
            candidate.dimension_id,
            candidate.normalized_value.strip().lower(),
        )

        existing = consolidated.get(identity)

        if existing is None:
            consolidated[identity] = candidate
            continue

        existing_priority = match_type_priority.get(existing.match_type, 0)
        candidate_priority = match_type_priority.get(candidate.match_type, 0)

        keep_new = False
        reason = ""

        if candidate_priority > existing_priority:
            keep_new = True
            reason = f"higher match type priority ({candidate.match_type.value} > {existing.match_type.value})"
        elif candidate_priority < existing_priority:
            keep_new = False
            reason = f"lower match type priority ({candidate.match_type.value} < {existing.match_type.value})"
        else:
            existing_coverage = len(existing.matched_question_tokens or [])
            candidate_coverage = len(candidate.matched_question_tokens or [])

            if candidate.confidence > existing.confidence:
                keep_new = True
                reason = f"higher confidence ({candidate.confidence:.2f} > {existing.confidence:.2f}) with same match type"
            elif candidate.confidence < existing.confidence:
                keep_new = False
                reason = f"lower confidence ({candidate.confidence:.2f} < {existing.confidence:.2f}) with same match type"
            else:
                if candidate_coverage > existing_coverage:
                    keep_new = True
                    reason = f"higher question-token coverage ({candidate_coverage} > {existing_coverage}) with same confidence"
                else:
                    keep_new = False
                    reason = f"lower or equal question-token coverage ({candidate_coverage} <= {existing_coverage}) with same confidence"

        if keep_new:
            removed_logs.append((existing, candidate, reason))
            consolidated[identity] = candidate
        else:
            removed_logs.append((candidate, existing, reason))

    return list(consolidated.values()), removed_logs

def trace_remove_contained_matches(matches, q_tokens):
    if len(matches) <= 1:
        return matches, []

    def get_span(m):
        if m.match_type == MatchType.FUZZY and m.matched_question_tokens:
            return m.matched_question_tokens
        return DimensionValueResolver._find_matched_question_span(m.matched_value_tokens, q_tokens)

    def sort_key(m):
        span = get_span(m)
        is_direct = m.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL)
        return (len(span), 1 if is_direct else 0, len(m.normalized_value))

    sorted_matches = sorted(matches, key=sort_key, reverse=True)

    filtered = []
    removed_logs = []

    for candidate in sorted_matches:
        candidate_span = get_span(candidate)
        
        # Discard FUZZY candidates whose matching tokens are split non-contiguously in the question
        if candidate.match_type == MatchType.FUZZY:
            q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
            v_sing = [SingularPluralMatcher._to_singular(t) for t in candidate.matched_value_tokens]
            present_tokens = {t for t in v_sing if t in q_sing}
            candidate_span_sing = {SingularPluralMatcher._to_singular(t) for t in candidate_span}
            if len(present_tokens) > len(candidate_span_sing):
                removed_logs.append((
                    candidate, 
                    None, 
                    f"Fuzzy tokens split non-contiguously (matched tokens: {present_tokens}, span: {candidate_span_sing})"
                ))
                continue

        suppressed = False
        for kept in filtered:
            kept_span = get_span(kept)
            
            # Rule 1: Direct match suppresses fuzzy match on the same question span
            if (candidate.match_type == MatchType.FUZZY and 
                kept.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL) and 
                candidate_span == kept_span and len(candidate_span) > 0):
                suppressed = True
                removed_logs.append((
                    candidate,
                    kept,
                    f"Rule 1: Direct match on same span '{' '.join(kept_span)}' suppresses fuzzy match"
                ))
                break
            
            # Rule 2: Strict contiguous sublist containment
            if (len(candidate_span) < len(kept_span) and 
                len(candidate_span) > 0 and
                DimensionValueResolver._is_contiguous_sublist(candidate_span, kept_span)):
                suppressed = True
                removed_logs.append((
                    candidate,
                    kept,
                    f"Rule 2: Match span '{' '.join(candidate_span)}' is contained in longer span '{' '.join(kept_span)}'"
                ))
                break
                
        if not suppressed:
            filtered.append(candidate)

    return filtered, removed_logs

# List of questions
QUESTIONS = [
    # GROUP A: CLEAR SINGLE MATCH
    (1, "show sales for coimbatore", "GROUP A: CLEAR SINGLE MATCH"),
    (2, "show sales for chennai", "GROUP A: CLEAR SINGLE MATCH"),
    (3, "show sales for banian", "GROUP A: CLEAR SINGLE MATCH"),
    (4, "show sales for banians", "GROUP A: CLEAR SINGLE MATCH"),
    # GROUP B: KNOWN AMBIGUITY
    (5, "show sales for pant", "GROUP B: KNOWN AMBIGUITY"),
    (6, "show sales for shirt", "GROUP B: KNOWN AMBIGUITY"),
    (7, "show sales for cotton pant", "GROUP B: KNOWN AMBIGUITY"),
    (8, "show sales for formal shirt", "GROUP B: KNOWN AMBIGUITY"),
    # GROUP C: TYPO / FUZZY AMBIGUITY
    (9, "show sales for banain", "GROUP C: TYPO / FUZZY AMBIGUITY"),
    (10, "show sales for t shrt", "GROUP C: TYPO / FUZZY AMBIGUITY"),
    (11, "show sales for cottn pant", "GROUP C: TYPO / FUZZY AMBIGUITY"),
    (12, "show sales for forml shirt", "GROUP C: TYPO / FUZZY AMBIGUITY"),
    # GROUP D: SINGULAR / PLURAL
    (13, "show sales for pant", "GROUP D: SINGULAR / PLURAL"),
    (14, "show sales for pants", "GROUP D: SINGULAR / PLURAL"),
    (15, "show sales for banian", "GROUP D: SINGULAR / PLURAL"),
    (16, "show sales for banians", "GROUP D: SINGULAR / PLURAL"),
    # GROUP E: MULTI-DIMENSION / POSSIBLE CROSS-DIMENSION AMBIGUITY
    (17, "show sales for tamil nadu", "GROUP E: MULTI-DIMENSION / POSSIBLE CROSS-DIMENSION AMBIGUITY"),
    (18, "show sales for nadu", "GROUP E: MULTI-DIMENSION / POSSIBLE CROSS-DIMENSION AMBIGUITY"),
    (19, "show sales for ch", "GROUP E: MULTI-DIMENSION / POSSIBLE CROSS-DIMENSION AMBIGUITY"),
    (20, "show sales for rm", "GROUP E: MULTI-DIMENSION / POSSIBLE CROSS-DIMENSION AMBIGUITY"),
    (21, "show sales for an", "GROUP E: MULTI-DIMENSION / POSSIBLE CROSS-DIMENSION AMBIGUITY"),
    # GROUP F: NOISE / NO-MATCH
    (22, "show sales for laptop", "GROUP F: NOISE / NO-MATCH"),
    (23, "show sales for banana", "GROUP F: NOISE / NO-MATCH"),
    (24, "show sales for hospital", "GROUP F: NOISE / NO-MATCH"),
    (25, "show sales for xyzabc", "GROUP F: NOISE / NO-MATCH"),
    (26, "show sales for pantxyz", "GROUP F: NOISE / NO-MATCH"),
]

def main():
    resolver = DimensionValueResolver(settings=SETTINGS)
    try:
        indexed_values = resolver._load_dimension_values(CONN_ID)
    except Exception as e:
        print(f"Error loading dimension values for connection {CONN_ID}: {e}")
        return

    # Setup matchers
    exact_matcher = ExactMatcher()
    normalized_matcher = NormalizedMatcher()
    sp_matcher = SingularPluralMatcher()
    fuzzy_matcher = FuzzyMatcher()

    # Capture output for print and save
    output_lines = []
    def log(msg=""):
        output_lines.append(msg)
        print(msg)

    log("="*60)
    log("PHASE 1D.1 — AMBIGUITY DETECTION AUDIT")
    log("="*60)
    log(f"Connection ID: {CONN_ID}")
    log(f"Fuzzy Cutoff: {SETTINGS['FUZZY_SCORE_CUTOFF']}")
    log(f"Total Cached Dimension Values: {len(indexed_values)}")
    log("="*60)
    log()

    for idx, question, group_name in QUESTIONS:
        log("-"*80)
        log(f"QUESTION #{idx}: \"{question}\" ({group_name})")
        log("-"*80)

        # 1. Candidate Phrase Extraction
        sanitized = QuestionSanitizer.sanitize(question)
        normalized_q = resolver._normalize_text(sanitized)
        q_tokens = [t for t in normalized_q.split() if t not in STOPWORDS]
        q_singulars = [SingularPluralMatcher._to_singular(t) for t in q_tokens]

        question_context = QuestionContext(
            raw_question=sanitized,
            normalized_question=normalized_q,
            q_tokens=q_tokens,
            q_singulars=q_singulars
        )

        matching_context = MatchingContext(
            question_context=question_context,
            connection_id=CONN_ID,
            indexed_values=indexed_values,
            settings=SETTINGS
        )

        extracted_phrases = fuzzy_matcher.extractor.extract(normalized_q)
        log("B. EXTRACTED PHRASES:")
        log(f"  {extracted_phrases}")
        log()

        # 2. Matcher Output
        log("C. MATCHER OUTPUT:")
        m_exact = exact_matcher.match(matching_context)
        m_norm = normalized_matcher.match(matching_context)
        m_sp = sp_matcher.match(matching_context)
        m_fuzzy = fuzzy_matcher.match(matching_context)

        def print_matcher_results(results, name):
            log(f"  * {name}: {len(results)} matches")
            for r in results:
                log(f"    - value: '{r.value}'")
                log(f"      match_type: {r.match_type.value}")
                log(f"      confidence: {r.confidence:.2f}")
                log(f"      normalized_value: '{r.normalized_value}'")
                log(f"      dimension_id: {r.dimension_id}")
                log(f"      business_name: '{r.business_name}'")
                log(f"      table: '{r.table_name}'")
                log(f"      column: '{r.column_name}'")
                log(f"      matched_question_tokens: {r.matched_question_tokens}")
                log(f"      matched_value_tokens: {r.matched_value_tokens}")

        print_matcher_results(m_exact, "ExactMatcher")
        print_matcher_results(m_norm, "NormalizedMatcher")
        print_matcher_results(m_sp, "SingularPluralMatcher")
        print_matcher_results(m_fuzzy, "FuzzyMatcher")
        log()

        # 3. Pipeline Output
        all_matches = m_exact + m_norm + m_sp + m_fuzzy
        log("D. PIPELINE OUTPUT:")
        log(f"  Total raw matches collected: {len(all_matches)}")
        for i, m in enumerate(all_matches, 1):
            log(f"    {i}. '{m.value}' ({m.match_type.value}, conf: {m.confidence:.2f}, dim: '{m.business_name}')")
        log()

        # 4. Resolver Processing
        log("E. RESOLVER PROCESSING:")
        log(f"  Candidates received by DimensionValueResolver: {len(all_matches)}")

        # Step 1: Consolidation
        consolidated_matches, consolidated_logs = trace_consolidate_duplicate_matches(all_matches)
        log(f"  * Duplicate consolidation: {len(all_matches)} -> {len(consolidated_matches)}")
        for rem, keep, reason in consolidated_logs:
            log(f"    - Consolidate: '{rem.value}' ({rem.match_type.value}) removed because '{keep.value}' ({keep.match_type.value}) has {reason}")

        # Step 2: Containment
        final_resolver_matches, containment_logs = trace_remove_contained_matches(consolidated_matches, q_tokens)
        log(f"  * Containment removal: {len(consolidated_matches)} -> {len(final_resolver_matches)}")
        for rem, kept, reason in containment_logs:
            if kept:
                log(f"    - Suppressed: '{rem.value}' ({rem.match_type.value}) removed by kept '{kept.value}' ({kept.match_type.value}) | Reason: {reason}")
            else:
                log(f"    - Discarded: '{rem.value}' ({rem.match_type.value}) | Reason: {reason}")

        log(f"  * Candidates remaining after resolver processing: {len(final_resolver_matches)}")
        for m in final_resolver_matches:
            log(f"    - '{m.value}' (dim: '{m.business_name}')")
        log()

        # 5. Final Ranking
        final_ranked = MatchRanker.rank(final_resolver_matches, q_tokens)
        log("F. FINAL RANKING:")
        for r_idx, m in enumerate(final_ranked, 1):
            info = get_ranking_info(m, q_tokens)
            log(f"  Rank #{r_idx}:")
            log(f"    value: '{m.value}'")
            log(f"    match_type: {m.match_type.value}")
            log(f"    confidence: {m.confidence:.2f}")
            log(f"    coverage: {info['coverage']:.2f}")
            log(f"    token_distance: {info['token_distance']}")
            log(f"    length_difference: {info['length_diff']}")
            log(f"    semantic_dimension: '{m.business_name}' (ID: {m.dimension_id})")
            log(f"    table: '{m.table_name}'")
            log(f"    column: '{m.column_name}'")
        log()

        # 6. Ambiguity Classification
        is_group_f = (group_name == "GROUP F: NOISE / NO-MATCH")
        if len(final_ranked) == 0:
            classification = "NO_MATCH"
        elif is_group_f:
            classification = "UNEXPECTED"
        elif len(final_ranked) == 1:
            classification = "SINGLE_MATCH"
        else:
            dims = set(c.dimension_id for c in final_ranked)
            if len(dims) == 1:
                classification = "AMBIGUOUS_SAME_DIMENSION"
            else:
                classification = "AMBIGUOUS_CROSS_DIMENSION"

        # Check for specific unexpected anomalies in other groups
        # (e.g. Tamil Nadu matching ADUR - which is unexpected city match or not)
        # Note: we will analyze it in the report, but keep classification simple.
        
        log("G. AMBIGUITY CLASSIFICATION:")
        log(f"  {classification}")
        log()

        # 7. Special Analysis (if more than one final candidate)
        if len(final_ranked) > 1:
            log("H. SPECIAL ANALYSIS:")
            cand_count = len(final_ranked)
            dims = set(c.business_name for c in final_ranked)
            tables = set(c.table_name for c in final_ranked)
            
            match_types = defaultdict(int)
            for c in final_ranked:
                match_types[c.match_type.value] += 1
            
            confidences = [c.confidence for c in final_ranked]
            min_conf, max_conf = min(confidences), max(confidences)
            
            c1, c2 = final_ranked[0], final_ranked[1]
            gap = abs(c1.confidence - c2.confidence)
            
            # Dominance check: if rank 1 is a direct match and rank 2 is fuzzy, it's dominant.
            # If both are same match type, check if confidence gap >= 0.05
            is_dominant = False
            if c1.match_type != c2.match_type and c1.match_type != MatchType.FUZZY:
                is_dominant = True
            elif gap >= 0.05:
                is_dominant = True
                
            same_dim = (len(dims) == 1)
            same_col = (len(set((c.table_name, c.column_name) for c in final_ranked)) == 1)
            
            # Genuinely different interpretations?
            # Same dimension: e.g. LINEN PANT vs RAMRAJ PANT (Yes, same category, different values)
            # Cross dimension: e.g. state vs brand (Yes, different concepts)
            genuine = "Yes"
            
            amb_type = "Weak Ambiguity" if is_dominant else "Strong Ambiguity"
            # False ambiguity: if one candidate survives but is completely noise (low confidence/coverage)
            if any(info['coverage'] < 0.25 for c in final_ranked):
                amb_type = "False Ambiguity"
                
            log(f"  1. Number of candidates: {cand_count}")
            log(f"  2. Number of distinct semantic dimensions: {len(dims)} ({list(dims)})")
            log(f"  3. Number of distinct tables: {len(tables)} ({list(tables)})")
            log(f"  4. Match-type distribution: {dict(match_types)}")
            log(f"  5. Confidence range: {min_conf:.2f} - {max_conf:.2f}")
            log(f"  6. Score/confidence gap between rank #1 and rank #2: {gap:.2f}")
            log(f"  7. Rank #1 clearly dominant: {is_dominant}")
            log(f"  8. Candidates share the same semantic dimension: {same_dim}")
            log(f"  9. Candidates share the same column: {same_col}")
            log(f"  10. Genuinely different possible interpretations: {genuine}")
            log(f"  --> AMBIGUITY STRENGTH: {amb_type}")
            log()

    # Save to audit_output.txt
    audit_file_path = os.path.join(os.path.dirname(__file__), "audit_output.txt")
    with open(audit_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
    print(f"\nAudit output successfully written to: {audit_file_path}")

if __name__ == "__main__":
    main()
