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
    MatchingPipeline,
    MatchRanker
)

CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
SETTINGS = {"FUZZY_SCORE_CUTOFF": 85}

# List of queries to test
QUERIES = [
    "t", "r", "a", "m",
    "an", "ch", "ld", "rm", "ap", "ts",
    "t shirt", "t shrt", "an shirt", "ch shirt", "rm shirt"
]

# Classification logic (ad-hoc rules for this specific audit based on human inspection)
def classify_candidate(query: str, value: str, match_type: MatchType) -> str:
    q = query.lower().strip()
    v = value.lower().strip()
    
    # "pants" -> "LINEN PANT" = LEGITIMATE
    # "t" -> some T-shirt value = potentially LEGITIMATE
    # "banana" -> "AN" = NOISE
    # "laptop" -> "AP" = NOISE
    
    # Let's write rules:
    if q == "t":
        if "t shirt" in v or "tshirt" in v or "t shrt" in v or v == "t":
            return "LEGITIMATE"
        return "NOISE"
    if q in ("t shirt", "t shrt"):
        if "t shirt" in v or "tshirt" in v or "t shrt" in v or v == "t":
            return "LEGITIMATE"
        return "NOISE"
    if q == "an":
        if v == "an": # State code AN (Andhra Pradesh) could be legitimate if searched explicitly, but usually noise.
            # But wait, if they search for "an" as a query, is it legitimate? If the query is just "an", maybe they mean the state.
            # But we'll classify based on common sense.
            return "LEGITIMATE" if v == "an" else "NOISE"
        return "NOISE"
    if q == "ch":
        return "LEGITIMATE" if v == "ch" else "NOISE"
    if q == "rm":
        return "LEGITIMATE" if v == "rm" else "NOISE"
    if "shirt" in q:
        # e.g., "an shirt", "ch shirt", "rm shirt"
        # If the query is "ch shirt", matching state "CH" is pure NOISE.
        # If it matches a shirt, it could be legitimate.
        if "shirt" in v and not (v in ("ch", "an", "rm")):
            return "LEGITIMATE"
        return "NOISE"
    
    # Generic rule:
    # If the query is a short code (e.g. "ch", "rm", "an") and matches the exact value (e.g. "CH", "RM", "AN"), it's LEGITIMATE.
    # If it matches something else (like "ch" matching "CH SHIRT"), it could be legitimate or noise.
    if q == v:
        return "LEGITIMATE"
        
    return "NOISE"

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

    # We will run SingularPluralMatcher and FuzzyMatcher separately to compare them
    sp_pipeline = MatchingPipeline([sp_matcher])
    fuzzy_pipeline = MatchingPipeline([fuzzy_matcher])
    full_pipeline = MatchingPipeline([exact_matcher, normalized_matcher, sp_matcher, fuzzy_matcher])

    print("="*80)
    print("SHORT TOKEN SAFETY AUDIT")
    print("="*80)

    for query in QUERIES:
        print(f"\n==================================================")
        print(f"QUESTION: \"{query}\"")
        print(f"==================================================")

        sanitized = QuestionSanitizer.sanitize(query)
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

        # 1. Run Singular/Plural Matcher only (before containment)
        sp_matches, _ = sp_pipeline.execute(matching_context)
        
        # 2. Run Fuzzy Matcher only (before containment)
        fuzzy_matches, _ = fuzzy_pipeline.execute(matching_context)

        # 3. Run full pipeline & resolver to see final survivors
        final_results = resolver.resolve_matches(CONN_ID, query)
        final_values = [r["value"] for r in final_results]

        # Gather all consolidated matches before containment for full pipeline
        raw_matches, _ = full_pipeline.execute(matching_context)
        consolidated_matches = resolver._consolidate_duplicate_matches(raw_matches)

        print("\n1. Singular/plural candidates BEFORE containment:")
        if not sp_matches:
            print("  None")
        else:
            for m in sp_matches:
                survived = m.value in final_values
                classification = classify_candidate(query, m.value, m.match_type)
                print(f"  - Value: {m.value}")
                print(f"    Match Type: {m.match_type.value}")
                print(f"    Confidence: {m.confidence:.2f}")
                print(f"    Matched Q Tokens: {m.matched_question_tokens}")
                print(f"    Matched Val Tokens: {m.matched_value_tokens}")
                print(f"    Survived Containment: {survived}")
                print(f"    Classification: {classification}")
                print()

        # Let's compare SP vs Fuzzy
        print("2. Comparison: Singular/Plural vs Fuzzy + Token Gate:")
        sp_vals = {m.value for m in sp_matches}
        fuzzy_vals = {m.value for m in fuzzy_matches}
        
        print(f"  Singular/Plural candidates count: {len(sp_vals)}")
        print(f"  Fuzzy + Token Gate candidates count: {len(fuzzy_vals)}")
        
        only_sp = sp_vals - fuzzy_vals
        only_fuzzy = fuzzy_vals - sp_vals
        both = sp_vals & fuzzy_vals
        
        print(f"  Both matched: {list(both)[:10]} (total: {len(both)})")
        print(f"  Only SP matched: {list(only_sp)[:10]} (total: {len(only_sp)})")
        print(f"  Only Fuzzy matched: {list(only_fuzzy)[:10]} (total: {len(only_fuzzy)})")

        print("\n3. Final survivors (after containment & ranking):")
        if not final_results:
            print("  None")
        else:
            for idx, r in enumerate(final_results):
                classification = classify_candidate(query, r["value"], MatchType(r["match_type"]))
                print(f"  {idx+1}. {r['value']} | conf={r['confidence']:.2f} | type={r['match_type']} | class={classification}")

if __name__ == "__main__":
    main()
