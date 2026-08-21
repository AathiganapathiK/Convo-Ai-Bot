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
    QuestionSanitizer
)

CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
SETTINGS = {"FUZZY_SCORE_CUTOFF": 85}

# Exact real-world dimension values for fallback if the DB is unreachable
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
    
    # Attempt to load from DB
    try:
        print("Attempting to load dimension values from live database...")
        indexed_values = resolver._load_dimension_values(CONN_ID)
        print(f"Success! Loaded {len(indexed_values)} values from live index.")
    except Exception as e:
        print(f"Database connection timed out or failed: {e}")
        print("Falling back to pre-recorded real-data semantic values for simulation.")
        indexed_values = REAL_WORLD_FALLBACK_VALUES
        resolver.cache.put(CONN_ID, indexed_values)

    print("\n" + "="*80)
    print("PHASE 1D.2.A — AMBIGUITY CANDIDATE AUDIT RUN")
    print("="*80)

    for q in QUERIES:
        print(f"\nQUERY: \"{q}\"")
        results = resolver.resolve_matches(CONN_ID, q)
        print(f"Total resolved candidates: {len(results)}")
        for idx, r in enumerate(results, 1):
            print(f"  Candidate #{idx}:")
            print(f"    value: '{r['value']}'")
            print(f"    normalized_value: '{r['normalized_value']}'")
            print(f"    confidence: {r['confidence']:.2f}")
            print(f"    match_type: {r['match_type']}")
            print(f"    matched_question_tokens: {r['matched_question_tokens']}")
            print(f"    matched_value_tokens: {r['matched_value_tokens']}")
            print(f"    dimension_id: {r['dimension_id']}")
            print(f"    business_name: '{r['business_name']}'")
            print(f"    table_name: '{r['table_name']}'")
            print(f"    column_name: '{r['column_name']}'")
            print(f"    reason: '{r['reason']}'")

if __name__ == "__main__":
    main()
