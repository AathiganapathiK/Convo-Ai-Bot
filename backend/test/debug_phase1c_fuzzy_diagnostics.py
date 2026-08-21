import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching import MatchType

def run_diagnostics():
    connection_id = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
    questions = [
        "pant",
        "cotton pant",
        "formal shirt",
        "child wear",
        "mens wear",
        "womens wear",
        "persn choice"
    ]
    
    resolver = DimensionValueResolver()
    
    print("==================================================")
    print("PHASE 1C FUZZY RETRIEVAL DIAGNOSTIC")
    print(f"Connection ID: {connection_id}")
    print("==================================================")
    
    for q in questions:
        print(f"\nQuestion: \"{q}\"")
        print("-" * 50)
        
        # Clear cache to guarantee a fresh pipeline run
        resolver.invalidate_cache()
        DimensionValueResolver.clear_cache()
        
        # Run resolver
        results = resolver.resolve_matches(connection_id, q)
        
        # Filter for FUZZY match types to show the actual fuzzy candidates
        fuzzy_results = [r for r in results if r["match_type"] == MatchType.FUZZY.value]
        
        if not fuzzy_results:
            print("  No fuzzy candidates resolved.")
            continue
            
        for r in fuzzy_results:
            score = r["confidence"] * 100
            matched_phrase = " ".join(r["matched_question_tokens"]) if r["matched_question_tokens"] else "N/A"
            print(f"  Value                  : {r['value']}")
            print(f"  Semantic Dimension ID  : {r['dimension_id']}")
            print(f"  Score                  : {score:.1f}%")
            print(f"  Matched Phrase         : {matched_phrase}")
            print(f"  Matched Q Tokens       : {r['matched_question_tokens']}")
            print(f"  Confidence             : {r['confidence']}")
            print(f"  Reason                 : {r['reason']}")
            print("-" * 30)

if __name__ == "__main__":
    run_diagnostics()
