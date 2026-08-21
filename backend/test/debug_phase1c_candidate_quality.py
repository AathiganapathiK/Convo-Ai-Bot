import sys
import os
import re
from rapidfuzz import fuzz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching import MatchingPipeline, FuzzyMatcher, MatchType
from semantic.matching.singular_plural_matcher import SingularPluralMatcher
from semantic.matching.stopwords import STOPWORDS

def run_audit():
    connection_id = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
    resolver = DimensionValueResolver(settings={"FUZZY_SCORE_CUTOFF": 85})
    
    # Load all dimension values once
    indexed_values = resolver._load_dimension_values(connection_id)
    
    print("==================================================")
    print("TOKEN-TO-TOKEN SIMILARITY STRATEGY SIMULATION")
    print("==================================================")

    # 1) Target test questions with spelling variations
    test_cases = [
        # (Query, Expected Candidate in Index)
        ("Banain", "Banians"),
        ("Bniyan", "Banians"),
        ("Cottn Shirt", "Cotton Shirt"),
        ("T Shrt", "T Shirt"),
        ("pant", "VEPPANTHATTAI"), # Should be rejected
        ("pant", "RAMRAJ PANT"),   # Should be kept
        ("cotton pant", "AN"),      # Should be rejected
        ("cotton pant", "LS PANT")  # Should be kept
    ]

    for query, candidate_val in test_cases:
        q_tokens = [t for t in DimensionValueResolver._normalize_text(query).split() if t not in STOPWORDS]
        q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
        
        c_tokens = [t for t in DimensionValueResolver._normalize_text(candidate_val).split() if t not in STOPWORDS]
        c_sing = [SingularPluralMatcher._to_singular(t) for t in c_tokens]
        
        # Calculate max token-to-token similarity
        max_ratio = 0.0
        best_pair = ("", "")
        for qt in q_sing:
            for ct in c_sing:
                ratio = fuzz.ratio(qt, ct)
                if ratio > max_ratio:
                    max_ratio = ratio
                    best_pair = (qt, ct)
                    
        is_accepted = max_ratio >= 75.0
        decision = "KEEP" if is_accepted else "REJECT"
        print(f"Query: \"{query:<12}\" | Candidate: \"{candidate_val:<18}\" | Max Token Ratio: {max_ratio:.1f}% ({best_pair[0]} vs {best_pair[1]}) | Decision: {decision}")

if __name__ == "__main__":
    run_audit()
