import sys
import os

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai.prompt_builder import PromptBuilder
from semantic.semantic_resolver import SemanticResolver
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
    ),
    
    # Extra Night wears
    CachedDimensionValue(
        semantic_dimension_id=402, business_name="Prod Grp2", table_name="QB_MDJMD_SALES_5YRS_SUMMARY", column_name="ProdGrp2",
        value="N--NIGHT WEARS", normalized_value="n night wears",
        runtime_stored_norm="n night wears", runtime_stored_tokens=["n", "night", "wears"], runtime_stored_singulars=["n", "night", "wear"],
        runtime_raw_norm="n night wears", runtime_raw_tokens=["n", "night", "wears"], runtime_raw_singulars=["n", "night", "wear"]
    )
]

QUERIES = [
    "children wear",
    "women wear",
    "formal shirt",
    "cotton pant",
    "pant",
    "shirt",
    "banian",
    "t shirt",
    "red shirt",
    "blue pant"
]

def trace_query(q):
    print("\n" + "=" * 60)
    print(f"QUESTION: {q}")
    print("=" * 60)
    
    resolver = DimensionValueResolver(settings=SETTINGS)
    try:
        resolver._load_dimension_values(CONN_ID)
    except Exception:
        resolver.cache.put(CONN_ID, REAL_WORLD_FALLBACK_VALUES)
        
    if not resolver.cache.get(CONN_ID):
        resolver.cache.put(CONN_ID, REAL_WORLD_FALLBACK_VALUES)

    # 1. SemanticResolver resolve
    sem_res = SemanticResolver.resolve(CONN_ID, q)
    
    # 2. Get normalized and meaningful tokens
    raw_tokens = q.lower().split()
    meaningful_tokens = [t for t in raw_tokens if t not in STOPWORDS]
    
    print(f"NORMALIZED QUESTION: {q.lower()}")
    print(f"MEANINGFUL QUERY TOKENS: {meaningful_tokens}")
    
    ambig_result = sem_res.get("ambiguity_result")
    print(f"AMBIGUITY RESULT STATUS: {ambig_result.status.value if ambig_result else 'None'}")
    print(f"DOMINANT MATCH: {ambig_result.dominant_match.value if ambig_result and ambig_result.dominant_match else 'None'}")
    
    print("\nSEMANTIC MATCHES:")
    value_matches = sem_res.get("value_matches", [])
    for idx, c in enumerate(value_matches, 1):
        # Re-run coverage for trace display
        matched_tokens = []
        c_val_tokens = c.get("matched_value_tokens", [])
        c_val_tokens_singular = [SingularPluralMatcher._to_singular(t) for t in c_val_tokens]
        for mt in meaningful_tokens:
            mt_sing = SingularPluralMatcher._to_singular(mt)
            if mt_sing in c_val_tokens_singular:
                matched_tokens.append(mt)
                
        unmatched_tokens = [t for t in meaningful_tokens if t not in matched_tokens]
        coverage_str = f"{len(matched_tokens)}/{len(meaningful_tokens)}"
        
        print(f"  #{idx} value                 : {c.get('value')}")
        print(f"     dimension             : {c.get('business_name')}")
        print(f"     confidence            : {c.get('confidence')}")
        print(f"     match_type            : {c.get('match_type')}")
        print(f"     actual_query_coverage : {coverage_str}")
        print(f"     matched_query_tokens  : {matched_tokens}")
        print(f"     unmatched_query_tokens: {unmatched_tokens}")

    # 3. Trace prompt generation input
    print("\nDOWNSTREAM PIPELINE TRACE:")
    print(f"1. SemanticResolver Output (value_matches):\n   {value_matches}")
    
    resolved_dims = sem_res.get("dimensions", [])
    print(f"2. Resolved Dimensions:\n   {resolved_dims}")
    
    # Filters
    filters_list = []
    for v in value_matches:
        col = v.get("column_name")
        val = v.get("value")
        if col and val:
            filters_list.append(f"{col} = '{val}'")
    print(f"3. Resolved Filters:\n   {filters_list}")
    
    # Try to generate prompt safely
    try:
        builder = PromptBuilder()
        prompt, _, _ = builder.build_sql_prompt(question=q, connection_id=CONN_ID)
        
        # Check if the unmatched tokens appear in the SQL-generation input/context
        # (outside the raw USER QUESTION section)
        unmatched_preservation = {}
        for c in value_matches:
            matched_tokens = []
            c_val_tokens = c.get("matched_value_tokens", [])
            c_val_tokens_singular = [SingularPluralMatcher._to_singular(t) for t in c_val_tokens]
            for mt in meaningful_tokens:
                mt_sing = SingularPluralMatcher._to_singular(mt)
                if mt_sing in c_val_tokens_singular:
                    matched_tokens.append(mt)
            unmatched_tokens = [t for t in meaningful_tokens if t not in matched_tokens]
            
            for ut in unmatched_tokens:
                # Search after "USER QUESTION" in the prompt text
                parts = prompt.split("USER QUESTION")
                post_question = parts[1] if len(parts) > 1 else ""
                preserves = ut.lower() in post_question.lower()
                unmatched_preservation[ut] = preserves
        
        print(f"4. SQL-generation input contains unmatched tokens (outside raw question)?\n   {unmatched_preservation}")
        
        # Check for safety issue
        is_partial = False
        if ambig_result and ambig_result.status == ResolutionStatus.SINGLE_MATCH:
            # Check coverage
            best_c = ambig_result.candidates[0] if ambig_result.candidates else None
            if best_c and best_c.actual_query_coverage < len(meaningful_tokens):
                is_partial = True
                
        if is_partial:
            # Check if any unmatched token is NOT preserved
            any_lost = any(not preserved for preserved in unmatched_preservation.values())
            if any_lost:
                print("\n!!! PARTIAL INTENT DROP — SAFETY ISSUE !!!")
                print(f"  Unmatched tokens: {[k for k, v in unmatched_preservation.items() if not v]} were completely dropped from semantic context.")
            else:
                print("\nPartial match safely preserved.")
    except Exception as e:
        print(f"Prompt Builder invocation failed: {e}")

def main():
    for q in QUERIES:
        trace_query(q)

if __name__ == "__main__":
    main()
