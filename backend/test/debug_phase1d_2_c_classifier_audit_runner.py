import sys
import os

# Setup environment
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
    QuestionSanitizer,
    ResolutionStatus,
    AmbiguityChoice,
    SemanticResolutionResult,
    AmbiguityClassifier
)

CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
SETTINGS = {"FUZZY_SCORE_CUTOFF": 85}

REAL_WORLD_FALLBACK_VALUES = [
    # City / District Coimbatore
    CachedDimensionValue(
        semantic_dimension_id=101, business_name="City", table_name="PBI_OUTSTANDING_ENES_SUMMARY", column_name="City",
        value="COIMBATORE", normalized_value="coimbatore",
        runtime_stored_norm="coimbatore", runtime_stored_tokens=["coimbatore"], runtime_stored_singulars=["coimbatore"],
        runtime_raw_norm="coimbatore", runtime_raw_tokens=["coimbatore"], runtime_raw_singulars=["coimbatore"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=102, business_name="District", table_name="PBI_OUTSTANDING_ENES_SUMMARY", column_name="District",
        value="COIMBATORE", normalized_value="coimbatore",
        runtime_stored_norm="coimbatore", runtime_stored_tokens=["coimbatore"], runtime_stored_singulars=["coimbatore"],
        runtime_raw_norm="coimbatore", runtime_raw_tokens=["coimbatore"], runtime_raw_singulars=["coimbatore"]
    ),
    
    # Pants
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
    
    # Shirts
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="ADD SHIRT", normalized_value="add shirt",
        runtime_stored_norm="add shirt", runtime_stored_tokens=["add", "shirt"], runtime_stored_singulars=["add", "shirt"],
        runtime_raw_norm="add shirt", runtime_raw_tokens=["add", "shirt"], runtime_raw_singulars=["add", "shirt"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="ARISER SHIRT", normalized_value="ariser shirt",
        runtime_stored_norm="ariser shirt", runtime_stored_tokens=["ariser", "shirt"], runtime_stored_singulars=["ariser", "shirt"],
        runtime_raw_norm="ariser shirt", runtime_raw_tokens=["ariser", "shirt"], runtime_raw_singulars=["ariser", "shirt"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="RAMRAJ SHIRT", normalized_value="ramraj shirt",
        runtime_stored_norm="ramraj shirt", runtime_stored_tokens=["ramraj", "shirt"], runtime_stored_singulars=["ramraj", "shirt"],
        runtime_raw_norm="ramraj shirt", runtime_raw_tokens=["ramraj", "shirt"], runtime_raw_singulars=["ramraj", "shirt"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=201, business_name="Brand", table_name="PBI_ENES_ORDER_PENDING_SUMMARY", column_name="Brand",
        value="UATHAYAM SHIRTING", normalized_value="uathayam shirting",
        runtime_stored_norm="uathayam shirting", runtime_stored_tokens=["uathayam", "shirting"], runtime_stored_singulars=["uathayam", "shirting"],
        runtime_raw_norm="uathayam shirting", runtime_raw_tokens=["uathayam", "shirting"], runtime_raw_singulars=["uathayam", "shirting"]
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

    # Banians
    CachedDimensionValue(
        semantic_dimension_id=301, business_name="Prod Grp1", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp1",
        value="BANIANS", normalized_value="banians",
        runtime_stored_norm="banians", runtime_stored_tokens=["banians"], runtime_stored_singulars=["banian"],
        runtime_raw_norm="banians", runtime_raw_tokens=["banians"], runtime_raw_singulars=["banian"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=302, business_name="Prod Grp2", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp2",
        value="1 BANIAN", normalized_value="1 banian",
        runtime_stored_norm="1 banian", runtime_stored_tokens=["1", "banian"], runtime_stored_singulars=["1", "banian"],
        runtime_raw_norm="1 banian", runtime_raw_tokens=["1", "banian"], runtime_raw_singulars=["1", "banian"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=303, business_name="Prod Grp3", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp3",
        value="ADVERTISEMENT BANIAN", normalized_value="advertisement banian",
        runtime_stored_norm="advertisement banian", runtime_stored_tokens=["advertisement", "banian"], runtime_stored_singulars=["advertisement", "banian"],
        runtime_raw_norm="advertisement banian", runtime_raw_tokens=["advertisement", "banian"], runtime_raw_singulars=["advertisement", "banian"]
    ),
    
    # Children Wear
    CachedDimensionValue(
        semantic_dimension_id=401, business_name="Category", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="Category",
        value="Children Wear", normalized_value="children wear",
        runtime_stored_norm="children wear", runtime_stored_tokens=["children", "wear"], runtime_stored_singulars=["child", "wear"],
        runtime_raw_norm="children wear", runtime_raw_tokens=["children", "wear"], runtime_raw_singulars=["child", "wear"]
    ),
    CachedDimensionValue(
        semantic_dimension_id=401, business_name="Category", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="Category",
        value="Kids Wear", normalized_value="kids wear",
        runtime_stored_norm="kids wear", runtime_stored_tokens=["kids", "wear"], runtime_stored_singulars=["kid", "wear"],
        runtime_raw_norm="kids wear", runtime_raw_tokens=["kids", "wear"], runtime_raw_singulars=["kid", "wear"]
    )
]

QUERIES = [
    "pant",
    "shirt",
    "cotton pant",
    "formal shirt",
    "banian",
    "children wear"
]

def main():
    resolver = DimensionValueResolver(settings=SETTINGS)
    
    # Try to load dimension values from DB, or fallback
    try:
        resolver._load_dimension_values(CONN_ID)
    except Exception:
        resolver.cache.put(CONN_ID, REAL_WORLD_FALLBACK_VALUES)

    print("=" * 80)
    print("PART 1: REAL-DATA CLASSIFICATION AUDIT")
    print("=" * 80)

    for q in QUERIES:
        print(f"\nQUERY: \"{q}\"")
        resolver.resolve_matches(CONN_ID, q)
        res = resolver.last_resolution_result
        print(f"Status: {res.status.value}")
        print(f"Dominant Match: {res.dominant_match.value if res.dominant_match else 'None'}")
        print(f"Candidates:")
        for idx, c in enumerate(res.candidates, 1):
            print(f"  #{idx} {c.value} ({c.match_type.value}, Conf: {c.confidence:.2f}, Span: {c.matched_question_tokens})")
            print(f"      Dim ID: {c.dimension_id}, Biz Name: {c.business_name}, Table: {c.table_name}, Col: {c.column_name}")

    print("\n" + "=" * 80)
    print("PART 2: SYNTHETIC CLASSIFIER CASES")
    print("=" * 80)

    # Case A: EXACT 1.00 vs FUZZY 0.85
    c_a_1 = MatchResult(True, "Exact Val", "exact val", 1.00, MatchType.EXACT, ["val"], ["exact", "val"], "reason", 1, "Biz")
    c_a_2 = MatchResult(True, "Fuzzy Val", "fuzzy val", 0.85, MatchType.FUZZY, ["val"], ["fuzzy", "val"], "reason", 1, "Biz")
    res_a = AmbiguityClassifier.classify([c_a_1, c_a_2])
    print(f"\nCase A: EXACT 1.00 vs FUZZY 0.85")
    print(f"  Status: {res_a.status.value}")
    print(f"  Dominant Match: {res_a.dominant_match.value if res_a.dominant_match else 'None'}")

    # Case B: SINGULAR_PLURAL 0.95 vs SINGULAR_PLURAL 0.95
    c_b_1 = MatchResult(True, "Plural 1", "plural 1", 0.95, MatchType.SINGULAR_PLURAL, ["val"], ["plural", "1"], "reason", 1, "Biz")
    c_b_2 = MatchResult(True, "Plural 2", "plural 2", 0.95, MatchType.SINGULAR_PLURAL, ["val"], ["plural", "2"], "reason", 1, "Biz")
    res_b = AmbiguityClassifier.classify([c_b_1, c_b_2])
    print(f"\nCase B: SINGULAR_PLURAL 0.95 vs SINGULAR_PLURAL 0.95")
    print(f"  Status: {res_b.status.value}")
    print(f"  Dominant Match: {res_b.dominant_match.value if res_b.dominant_match else 'None'}")

    # Case C: FUZZY 0.90 vs FUZZY 0.86
    c_c_1 = MatchResult(True, "Fuzzy 1", "fuzzy 1", 0.90, MatchType.FUZZY, ["val"], ["fuzzy", "1"], "reason", 1, "Biz")
    c_c_2 = MatchResult(True, "Fuzzy 2", "fuzzy 2", 0.86, MatchType.FUZZY, ["val"], ["fuzzy", "2"], "reason", 1, "Biz")
    res_c = AmbiguityClassifier.classify([c_c_1, c_c_2])
    print(f"\nCase C: FUZZY 0.90 vs FUZZY 0.86")
    print(f"  Status: {res_c.status.value}")
    print(f"  Dominant Match: {res_c.dominant_match.value if res_c.dominant_match else 'None'}")

    # Case D: EXACT 1.00 vs EXACT 1.00
    c_d_1 = MatchResult(True, "Exact 1", "exact 1", 1.00, MatchType.EXACT, ["val"], ["exact", "1"], "reason", 1, "Biz")
    c_d_2 = MatchResult(True, "Exact 2", "exact 2", 1.00, MatchType.EXACT, ["val"], ["exact", "2"], "reason", 1, "Biz")
    res_d = AmbiguityClassifier.classify([c_d_1, c_d_2])
    print(f"\nCase D: EXACT 1.00 vs EXACT 1.00")
    print(f"  Status: {res_d.status.value}")
    print(f"  Dominant Match: {res_d.dominant_match.value if res_d.dominant_match else 'None'}")

    # Case E: candidate matching 2 query tokens at 0.90 vs candidate matching 1 query token at 0.95
    c_e_1 = MatchResult(True, "Two Tokens", "two tokens", 0.90, MatchType.FUZZY, ["cotton", "pant"], ["cotton", "pant"], "reason", 1, "Biz")
    c_e_2 = MatchResult(True, "One Token", "one token", 0.95, MatchType.FUZZY, ["pant"], ["one", "token"], "reason", 1, "Biz")
    res_e = AmbiguityClassifier.classify([c_e_1, c_e_2])
    print(f"\nCase E: 2 tokens 0.90 vs 1 token 0.95")
    print(f"  Status: {res_e.status.value}")
    print(f"  Dominant Match: {res_e.dominant_match.value if res_e.dominant_match else 'None'}")

if __name__ == "__main__":
    main()
