import sys
import os

# Setup environment – ensure project root is on sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching import (
    MatchType,
    QuestionContext,
    MatchingContext,
    ExactMatcher,
    NormalizedMatcher,
    SingularPluralMatcher,
    FuzzyMatcher,
    STOPWORDS,
    QuestionSanitizer,
    MatchingPipeline
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

    # 1. Matches from pipeline
    raw_matches, _ = pipeline.execute(matching_context)
    
    # 2. Consolidation
    consolidated_matches = resolver._consolidate_duplicate_matches(raw_matches)

    # 3. Print BEFORE CONTAINMENT
    print("BEFORE CONTAINMENT:")
    print(f"{'candidate':<30} | {'confidence':<10} | {'match_type':<15} | {'matched_question_tokens'}")
    print("-" * 80)
    for m in consolidated_matches:
        print(f"{m.value:<30} | {m.confidence:<10.2f} | {m.match_type.value:<15} | {m.matched_question_tokens}")
    print()

    # 4. Containment simulation & printing REMOVED
    def get_span(m):
        if m.match_type == MatchType.FUZZY and m.matched_question_tokens:
            return m.matched_question_tokens
        return DimensionValueResolver._find_matched_question_span(m.matched_value_tokens, q_tokens)

    def sort_key(m):
        span = get_span(m)
        is_direct = m.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL)
        return (len(span), 1 if is_direct else 0, len(m.normalized_value))

    sorted_matches = sorted(consolidated_matches, key=sort_key, reverse=True)

    filtered = []
    removed_records = []

    for candidate in sorted_matches:
        candidate_span = get_span(candidate)
        
        # Discard non-contiguous fuzzy
        if candidate.match_type == MatchType.FUZZY:
            q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
            v_sing = [SingularPluralMatcher._to_singular(t) for t in candidate.matched_value_tokens]
            present_tokens = {t for t in v_sing if t in q_sing}
            candidate_span_sing = {SingularPluralMatcher._to_singular(t) for t in candidate_span}
            if len(present_tokens) > len(candidate_span_sing):
                removed_records.append((candidate.value, "Non-contiguous fuzzy tokens", "N/A"))
                continue

        suppressed = False
        for kept in filtered:
            kept_span = get_span(kept)
            
            # Rule 1
            if (candidate.match_type == MatchType.FUZZY and 
                kept.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL) and 
                candidate_span == kept_span and len(candidate_span) > 0):
                suppressed = True
                removed_records.append((candidate.value, "Rule 1: Direct match on same span", kept.value))
                break
            
            # Rule 2
            if (len(candidate_span) < len(kept_span) and 
                len(candidate_span) > 0 and
                DimensionValueResolver._is_contiguous_sublist(candidate_span, kept_span)):
                if candidate.confidence > kept.confidence:
                    continue
                suppressed = True
                removed_records.append((candidate.value, f"Rule 2: Sublist span contained in {kept_span} with suppressor confidence {kept.confidence:.2f} >= candidate confidence {candidate.confidence:.2f}", kept.value))
                break
                
        if not suppressed:
            filtered.append(candidate)

    # 5. Print AFTER CONTAINMENT
    print("AFTER CONTAINMENT:")
    print(f"{'candidate':<30} | {'confidence':<10} | {'match_type':<15} | {'matched_question_tokens'}")
    print("-" * 80)
    for m in filtered:
        print(f"{m.value:<30} | {m.confidence:<10.2f} | {m.match_type.value:<15} | {m.matched_question_tokens}")
    print()

    # 6. Print REMOVED
    print("REMOVED:")
    print(f"{'candidate':<30} | {'reason':<65} | {'suppressor'}")
    print("-" * 115)
    for name, reason, suppressor in removed_records:
        print(f"{name:<30} | {reason:<65} | {suppressor}")

if __name__ == "__main__":
    main()
