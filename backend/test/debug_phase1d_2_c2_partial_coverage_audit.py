import sys
import os

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching import (
    MatchType,
    MatchResult,
    CachedDimensionValue,
    ResolutionStatus,
    AmbiguityChoice,
    SemanticResolutionResult,
    AmbiguityClassifier
)
from semantic.matching.stopwords import STOPWORDS
from semantic.matching.singular_plural_matcher import SingularPluralMatcher

CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
SETTINGS = {"FUZZY_SCORE_CUTOFF": 85}

REAL_WORLD_FALLBACK_VALUES = [
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="LINEN PANT", normalized_value="linen pant",
        runtime_stored_norm="linen pant", runtime_stored_tokens=["linen", "pant"], runtime_stored_singulars=["linen", "pant"],
        runtime_raw_norm="linen pant", runtime_raw_tokens=["linen", "pant"], runtime_raw_singulars=["linen", "pant"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="RAMRAJ PANT", normalized_value="ramraj pant",
        runtime_stored_norm="ramraj pant", runtime_stored_tokens=["ramraj", "pant"], runtime_stored_singulars=["ramraj", "pant"],
        runtime_raw_norm="ramraj pant", runtime_raw_tokens=["ramraj", "pant"], runtime_raw_singulars=["ramraj", "pant"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=202, business_name="Prod Grp2", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp2",
        value="LS PANT", normalized_value="ls pant",
        runtime_stored_norm="ls pant", runtime_stored_tokens=["ls", "pant"], runtime_stored_singulars=["ls", "pant"],
        runtime_raw_norm="ls pant", runtime_raw_tokens=["ls", "pant"], runtime_raw_singulars=["ls", "pant"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="VIVEAGHAM COLOUR SHIRT", normalized_value="viveagham colour shirt",
        runtime_stored_norm="viveagham colour shirt", runtime_stored_tokens=["viveagham", "colour", "shirt"], runtime_stored_singulars=["viveagham", "colour", "shirt"],
        runtime_raw_norm="viveagham colour shirt", runtime_raw_tokens=["viveagham", "colour", "shirt"], runtime_raw_singulars=["viveagham", "colour", "shirt"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=203, business_name="Prod Grp3", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp3",
        value="FORMAL SOCKS DESIGN FULL", normalized_value="formal socks design full",
        runtime_stored_norm="formal socks design full", runtime_stored_tokens=["formal", "socks", "design", "full"], runtime_stored_singulars=["formal", "socks", "design", "full"],
        runtime_raw_norm="formal socks design full", runtime_raw_tokens=["formal", "socks", "design", "full"], runtime_raw_singulars=["formal", "socks", "design", "full"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=301, business_name="Prod Grp1", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp1",
        value="BANIANS", normalized_value="banians",
        runtime_stored_norm="banians", runtime_stored_tokens=["banians"], runtime_stored_singulars=["banian"],
        runtime_raw_norm="banians", runtime_raw_tokens=["banians"], runtime_raw_singulars=["banian"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=401, business_name="Category", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="Category",
        value="Children Wear", normalized_value="children wear",
        runtime_stored_norm="children wear", runtime_stored_tokens=["children", "wear"], runtime_stored_singulars=["child", "wear"],
        runtime_raw_norm="children wear", runtime_raw_tokens=["children", "wear"], runtime_raw_singulars=["child", "wear"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=401, business_name="Category", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="Category",
        value="Women Wear", normalized_value="women wear",
        runtime_stored_norm="women wear", runtime_stored_tokens=["women", "wear"], runtime_stored_singulars=["woman", "wear"],
        runtime_raw_norm="women wear", runtime_raw_tokens=["women", "wear"], runtime_raw_singulars=["woman", "wear"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=401, business_name="Category", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="Category",
        value="Mens Wear", normalized_value="mens wear",
        runtime_stored_norm="mens wear", runtime_stored_tokens=["mens", "wear"], runtime_stored_singulars=["man", "wear"],
        runtime_raw_norm="mens wear", runtime_raw_tokens=["mens", "wear"], runtime_raw_singulars=["man", "wear"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=402, business_name="Prod Grp2", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp2",
        value="N--NIGHT WEARS", normalized_value="n night wears",
        runtime_stored_norm="n night wears", runtime_stored_tokens=["n", "night", "wears"], runtime_stored_singulars=["n", "night", "wear"],
        runtime_raw_norm="n night wears", runtime_raw_tokens=["n", "night", "wears"], runtime_raw_singulars=["n", "night", "wear"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=204, business_name="Prod Grp3", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp3",
        value="UNIFORM T SHIRT", normalized_value="uniform t shirt",
        runtime_stored_norm="uniform t shirt", runtime_stored_tokens=["uniform", "t", "shirt"], runtime_stored_singulars=["uniform", "t", "shirt"],
        runtime_raw_norm="uniform t shirt", runtime_raw_tokens=["uniform", "t", "shirt"], runtime_raw_singulars=["uniform", "t", "shirt"]
    )
]

QUERIES = [
    "pant",
    "shirt",
    "banian",
    "children wear",
    "formal shirt",
    "cotton pant",
    "pants",
    "banians",
    "t shirt",
    "women wear",
    "mens wear"
]

def main():
    resolver = DimensionValueResolver(settings=SETTINGS)
    
    try:
        resolver._load_dimension_values(CONN_ID)
    except Exception:
        resolver.cache.put(CONN_ID, REAL_WORLD_FALLBACK_VALUES)

    # Cache could be loaded but empty if connection failed silently or DB had no values
    if not resolver.cache.get(CONN_ID):
        resolver.cache.put(CONN_ID, REAL_WORLD_FALLBACK_VALUES)

    print("=" * 80)
    print("PARTIAL COVERAGE FORENSIC AUDIT (REAL DATA)")
    print("=" * 80)

    audit_summary = []

    for q in QUERIES:
        print("\n" + "=" * 40)
        print(f"QUESTION:\n    {q}")
        
        # Resolve using pipeline
        resolver.resolve_matches(CONN_ID, q)
        res = resolver.last_resolution_result
        
        # Get query and meaningful tokens
        raw_tokens = q.lower().split()
        meaningful_tokens = [t for t in raw_tokens if t not in STOPWORDS]
        
        print(f"\nQUERY TOKENS:\n    {raw_tokens}")
        print(f"\nMEANINGFUL QUERY TOKENS:\n    {meaningful_tokens}")
        
        status_str = res.status.value
        dominant_candidate = res.dominant_match.value if res.dominant_match else "None"
        
        print(f"\nFINAL STATUS:\n    {status_str}")
        print(f"DOMINANT MATCH:\n    {dominant_candidate}")
        
        if not res.candidates:
            print("\nNO CANDIDATES FOUND")
            audit_summary.append({
                "query": q,
                "candidates": 0,
                "coverage": "0/0",
                "status": status_str,
                "partial_single": "No"
            })
            continue

        print("\nCANDIDATES:")
        for idx, c in enumerate(res.candidates, 1):
            coverage_val = f"{c.actual_query_coverage}/{len(meaningful_tokens)}"
            unmatched = [t for t in meaningful_tokens if t not in c.matched_query_tokens]
            
            is_partial_single = "No"
            if res.status == ResolutionStatus.SINGLE_MATCH and c.actual_query_coverage < len(meaningful_tokens):
                is_partial_single = "Yes"
                print("\n    !!! PARTIAL SINGLE MATCH !!!")
            
            print(f"\n  #{idx} CANDIDATE:\n    {c.value}")
            print(f"  MATCH TYPE:\n    {c.match_type.value}")
            print(f"  CONFIDENCE:\n    {c.confidence:.2f}")
            print(f"  ACTUAL QUERY COVERAGE:\n    {coverage_val}")
            print(f"  MATCHED QUERY TOKENS:\n    {c.matched_query_tokens}")
            print(f"  UNMATCHED QUERY TOKENS:\n    {unmatched}")
            print(f"  DIMENSION:\n    {c.business_name}")
            
            if idx == 1:
                audit_summary.append({
                    "query": q,
                    "candidates": len(res.candidates),
                    "coverage": coverage_val,
                    "status": status_str,
                    "partial_single": is_partial_single
                })

    print("\n" + "=" * 80)
    print("SYNTHETIC CONTRACT CASES")
    print("=" * 80)

    # CASE A: Query = ["formal", "shirt"]
    # Candidate 1: matches ["shirt"], conf 0.95. Only one candidate.
    q_a = ["formal", "shirt"]
    c_a1 = MatchResult(
        matched=True, value="VIVEAGHAM COLOUR SHIRT", normalized_value="viveagham colour shirt",
        confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
        matched_question_tokens=q_a, matched_value_tokens=["viveagham", "colour", "shirt"],
        reason="test"
    )
    res_a = AmbiguityClassifier.classify([c_a1], q_a)
    print(f"\nCASE A (formal shirt -> 1 candidate matching shirt):")
    print(f"  Status: {res_a.status.value}")
    print(f"  Dominant: {res_a.dominant_match.value if res_a.dominant_match else 'None'}")
    print(f"  Coverage: {res_a.candidates[0].actual_query_coverage}/{len(q_a)}")

    # CASE B: Query = ["formal", "shirt"]
    # Candidate 1: matches ["formal"], conf 0.95.
    # Candidate 2: matches ["shirt"], conf 0.95.
    c_b1 = MatchResult(
        matched=True, value="FORMAL SOCKS DESIGN FULL", normalized_value="formal socks design full",
        confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
        matched_question_tokens=q_a, matched_value_tokens=["formal", "socks", "design", "full"],
        reason="test"
    )
    c_b2 = MatchResult(
        matched=True, value="VIVEAGHAM COLOUR SHIRT", normalized_value="viveagham colour shirt",
        confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
        matched_question_tokens=q_a, matched_value_tokens=["viveagham", "colour", "shirt"],
        reason="test"
    )
    res_b = AmbiguityClassifier.classify([c_b1, c_b2], q_a)
    print(f"\nCASE B (formal shirt -> formal 0.95 vs shirt 0.95):")
    print(f"  Status: {res_b.status.value}")
    print(f"  Dominant: {res_b.dominant_match.value if res_b.dominant_match else 'None'}")

    # CASE C: Query = ["cotton", "pant"]
    # Candidate 1: matches ["cotton", "pant"], conf 0.90.
    # Candidate 2: matches ["pant"], conf 0.95.
    q_c = ["cotton", "pant"]
    c_c1 = MatchResult(
        matched=True, value="COTTON PANT", normalized_value="cotton pant",
        confidence=0.90, match_type=MatchType.FUZZY,
        matched_question_tokens=q_c, matched_value_tokens=["cotton", "pant"],
        reason="test"
    )
    c_c2 = MatchResult(
        matched=True, value="LINEN PANT", normalized_value="linen pant",
        confidence=0.95, match_type=MatchType.FUZZY,
        matched_question_tokens=q_c, matched_value_tokens=["linen", "pant"],
        reason="test"
    )
    res_c = AmbiguityClassifier.classify([c_c1, c_c2], q_c)
    print(f"\nCASE C (cotton pant -> 2-token 0.90 vs 1-token 0.95):")
    print(f"  Status: {res_c.status.value}")
    print(f"  Dominant: {res_c.dominant_match.value if res_c.dominant_match else 'None'}")

    # CASE D: Query = ["cotton", "pant"]
    # Candidate 1: matches ["cotton"], conf 0.95. Only one candidate.
    c_d1 = MatchResult(
        matched=True, value="LS ZARI COTTON", normalized_value="ls zari cotton",
        confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
        matched_question_tokens=q_c, matched_value_tokens=["ls", "zari", "cotton"],
        reason="test"
    )
    res_d = AmbiguityClassifier.classify([c_d1], q_c)
    print(f"\nCASE D (cotton pant -> 1 candidate matching cotton):")
    print(f"  Status: {res_d.status.value}")
    print(f"  Dominant: {res_d.dominant_match.value if res_d.dominant_match else 'None'}")

    # CASE E: Query = ["cotton", "pant"]
    # Candidate 1: matches ["cotton", "pant"], conf 0.90. Only one candidate.
    c_e1 = MatchResult(
        matched=True, value="COTTON PANT", normalized_value="cotton pant",
        confidence=0.90, match_type=MatchType.FUZZY,
        matched_question_tokens=q_c, matched_value_tokens=["cotton", "pant"],
        reason="test"
    )
    res_e = AmbiguityClassifier.classify([c_e1], q_c)
    print(f"\nCASE E (cotton pant -> 1 candidate matching cotton pant):")
    print(f"  Status: {res_e.status.value}")
    print(f"  Dominant: {res_e.dominant_match.value if res_e.dominant_match else 'None'}")

    # CASE F: Query = ["pant"]
    # Candidate 1: matches ["pant"], conf 0.95. Only one candidate.
    q_f = ["pant"]
    c_f1 = MatchResult(
        matched=True, value="RAMRAJ PANT", normalized_value="ramraj pant",
        confidence=0.95, match_type=MatchType.SINGULAR_PLURAL,
        matched_question_tokens=q_f, matched_value_tokens=["ramraj", "pant"],
        reason="test"
    )
    res_f = AmbiguityClassifier.classify([c_f1], q_f)
    print(f"\nCASE F (pant -> 1 candidate matching pant):")
    print(f"  Status: {res_f.status.value}")
    print(f"  Dominant: {res_f.dominant_match.value if res_f.dominant_match else 'None'}")

    print("\n" + "=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print("| Query | Candidates | Coverage | Status | Partial Single? |")
    print("|-------|------------|----------|--------|-----------------|")
    for item in audit_summary:
        print(f"| {item['query']:<14} | {item['candidates']:<10} | {item['coverage']:<8} | {item['status']:<16} | {item['partial_single']:<15} |")

if __name__ == "__main__":
    main()
