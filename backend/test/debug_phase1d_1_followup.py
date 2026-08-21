import sys
import os
import re

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

def main():
    resolver = DimensionValueResolver(settings=SETTINGS)
    try:
        indexed_values = resolver._load_dimension_values(CONN_ID)
    except Exception as e:
        print(f"Error loading dimension values: {e}")
        return

    exact_matcher = ExactMatcher()
    normalized_matcher = NormalizedMatcher()
    sp_matcher = SingularPluralMatcher()
    fuzzy_matcher = FuzzyMatcher()

    pipeline = MatchingPipeline([exact_matcher, normalized_matcher, sp_matcher, fuzzy_matcher])

    output_lines = []
    def log(msg=""):
        output_lines.append(msg)
        print(msg)

    log("="*80)
    log("ISSUE 1 — CONTAINMENT SUPPRESSION: Trace for 'cotton pant'")
    log("="*80)

    question = "cotton pant"
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

    # 1. Matching Pipeline execution (before containment & consolidation)
    raw_matches, _ = pipeline.execute(matching_context)
    
    log("\n--- ALL CANDIDATES PRODUCED BEFORE CONTAINMENT ---")
    for m in raw_matches:
        log(f"value: {m.value}")
        log(f"  matched_question_tokens: {m.matched_question_tokens}")
        log(f"  match_type: {m.match_type.value}")
        log(f"  confidence: {m.confidence:.2f}")
        log(f"  dimension_id: {m.dimension_id}")
        log(f"  dimension_name: {m.business_name}")
        log(f"  table: {m.table_name}")
        log(f"  column: {m.column_name}")
        log()

    # Verify if LS PANT, LINEN PANT, RAMRAJ PANT are produced
    values_produced = [m.value for m in raw_matches]
    log(f"Are LS PANT, LINEN PANT, RAMRAJ PANT all produced? "
        f"LS PANT: {'LS PANT' in values_produced}, "
        f"LINEN PANT: {'LINEN PANT' in values_produced}, "
        f"RAMRAJ PANT: {'RAMRAJ PANT' in values_produced}\n")

    # Step 1: Duplicate consolidation (run it first to get consolidated matches)
    consolidated_matches = resolver._consolidate_duplicate_matches(raw_matches)

    # Trace containment decisions inside _remove_contained_matches
    log("--- TRACING CONTAINMENT DECISIONS IN _remove_contained_matches() ---")
    matches = consolidated_matches

    def get_span(m):
        if m.match_type == MatchType.FUZZY and m.matched_question_tokens:
            return m.matched_question_tokens
        return DimensionValueResolver._find_matched_question_span(m.matched_value_tokens, q_tokens)

    def sort_key(m):
        span = get_span(m)
        is_direct = m.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL)
        return (len(span), 1 if is_direct else 0, len(m.normalized_value))

    sorted_matches = sorted(matches, key=sort_key, reverse=True)

    log("\nSorted matches by span length descending:")
    for m in sorted_matches:
        log(f"  - {m.value} ({m.match_type.value}) span={get_span(m)}")

    filtered = []
    for candidate in sorted_matches:
        candidate_span = get_span(candidate)
        
        # Discard FUZZY candidates whose matching tokens are split non-contiguously in the question
        if candidate.match_type == MatchType.FUZZY:
            q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
            v_sing = [SingularPluralMatcher._to_singular(t) for t in candidate.matched_value_tokens]
            present_tokens = {t for t in v_sing if t in q_sing}
            candidate_span_sing = {SingularPluralMatcher._to_singular(t) for t in candidate_span}
            if len(present_tokens) > len(candidate_span_sing):
                log(f"\nREMOVED (Non-contiguous Fuzzy Tokens check):")
                log(f"candidate = {candidate.value}")
                log(f"candidate_span = {candidate_span}")
                log(f"candidate_confidence = {candidate.confidence:.2f}")
                log(f"RULE: Discard FUZZY candidates whose matching tokens are split non-contiguously")
                continue

        suppressed = False
        for kept in filtered:
            kept_span = get_span(kept)
            
            # Rule 1: Direct match suppresses fuzzy match on the same question span
            if (candidate.match_type == MatchType.FUZZY and 
                kept.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL) and 
                candidate_span == kept_span and len(candidate_span) > 0):
                suppressed = True
                log(f"\nREMOVED:")
                log(f"candidate = {candidate.value}")
                log(f"candidate_span = {candidate_span}")
                log(f"candidate_confidence = {candidate.confidence:.2f}")
                log(f"SUPPRESSED_BY:")
                log(f"candidate = {kept.value}")
                log(f"suppressor_span = {kept_span}")
                log(f"suppressor_confidence = {kept.confidence:.2f}")
                log(f"RULE: Rule 1: Direct match suppresses fuzzy match on the same question span")
                break
            
            # Rule 2: Strict contiguous sublist containment
            if (len(candidate_span) < len(kept_span) and 
                len(candidate_span) > 0 and
                DimensionValueResolver._is_contiguous_sublist(candidate_span, kept_span)):
                suppressed = True
                log(f"\nREMOVED:")
                log(f"candidate = {candidate.value}")
                log(f"candidate_span = {candidate_span}")
                log(f"candidate_confidence = {candidate.confidence:.2f}")
                log(f"SUPPRESSED_BY:")
                log(f"candidate = {kept.value}")
                log(f"suppressor_span = {kept_span}")
                log(f"suppressor_confidence = {kept.confidence:.2f}")
                log(f"RULE: Rule 2: Strict contiguous sublist containment (candidate span length < suppressor span length and candidate span is a contiguous sublist of suppressor span)")
                break
                
        if not suppressed:
            filtered.append(candidate)

    log("\n--- RESOLVER FINAL SURVIVORS ---")
    for m in filtered:
        log(f"  - {m.value} ({m.match_type.value}, conf={m.confidence:.2f})")

    log("\n" + "="*80)
    log("ISSUE 2 — PLURAL MATCHING: Trace for pant, pants, banian, banians")
    log("="*80)

    test_queries = ["pant", "pants", "banian", "banians"]
    target_values = ["LINEN PANT", "RAMRAJ PANT", "BANIANS"]

    # Filter indexed values to only targets for detailed tracing
    traced_vals = [val for val in indexed_values if val.value in target_values]

    for q_text in test_queries:
        log(f"\nQuery: '{q_text}'")
        log("-" * 40)
        norm_q = resolver._normalize_text(q_text)
        q_tok = [t for t in norm_q.split() if t not in STOPWORDS]
        q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tok]

        for val in traced_vals:
            log(f"  Candidate Value: '{val.value}'")
            log(f"    query tokens: {q_tok}")
            log(f"    candidate tokens: {val.runtime_raw_tokens}")
            log(f"    singularized query tokens: {q_sing}")
            log(f"    singularized candidate tokens: {val.runtime_raw_singulars}")
            
            # Trace singular plural matching comparison
            is_sub = SingularPluralMatcher._is_sublist(val.runtime_raw_singulars, q_sing)
            log(f"    comparison: matches_tokens check -> check if candidate singulars {val.runtime_raw_singulars} is sublist of query singulars {q_sing}")
            log(f"    condition passes/fails: {'PASS' if is_sub else 'FAIL'}")
            
            if is_sub:
                log(f"    RESULT: MatchResult IS produced (Morphological singular/plural match)")
            else:
                log(f"    RESULT: MatchResult IS NOT produced (Sublist check failed)")
            log()

    # Save to followup_output.txt
    followup_file_path = os.path.join(os.path.dirname(__file__), "followup_output.txt")
    with open(followup_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
    print(f"\nFollow-up output successfully written to: {followup_file_path}")

if __name__ == "__main__":
    main()
