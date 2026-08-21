import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Insert backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import engine as real_engine
from sqlalchemy import text
from semantic.matching import MatchType, MatchResult, QuestionContext, MatchingContext, MatchingPipeline, MatchRanker, AmbiguityClassifier, ResolutionStatus
from semantic.dimension_value_resolver import DimensionValueResolver

# Define the Fallback Mock Semantic Index Data
MOCK_INDEX_ROWS = [
    # Pants
    {"semantic_dimension_id": 1, "business_name": "Product Group", "table_name": "Products", "column_name": "ProductGroup", "value": "Pants", "normalized_value": "pants"},
    {"semantic_dimension_id": 2, "business_name": "Product Group", "table_name": "Products", "column_name": "ProductGroup", "value": "Cotton Pants", "normalized_value": "cotton pants"},
    {"semantic_dimension_id": 3, "business_name": "Product Group", "table_name": "Products", "column_name": "ProductGroup", "value": "Formal Pants", "normalized_value": "formal pants"},
    {"semantic_dimension_id": 4, "business_name": "Brand", "table_name": "Products", "column_name": "Brand", "value": "Linen Pant", "normalized_value": "linen pant"},
    {"semantic_dimension_id": 5, "business_name": "Brand", "table_name": "Products", "column_name": "Brand", "value": "Ramraj Pant", "normalized_value": "ramraj pant"},
    {"semantic_dimension_id": 6, "business_name": "Prod Grp2", "table_name": "Products", "column_name": "ProdGrp2", "value": "LS Pant", "normalized_value": "ls pant"},

    # Shirts
    {"semantic_dimension_id": 7, "business_name": "Product Group", "table_name": "Products", "column_name": "ProductGroup", "value": "Shirts", "normalized_value": "shirts"},
    {"semantic_dimension_id": 8, "business_name": "Product Group", "table_name": "Products", "column_name": "ProductGroup", "value": "Formal Shirts", "normalized_value": "formal shirts"},
    {"semantic_dimension_id": 9, "business_name": "Brand", "table_name": "Products", "column_name": "Brand", "value": "Ramraj Shirt", "normalized_value": "ramraj shirt"},
    {"semantic_dimension_id": 10, "business_name": "Brand", "table_name": "Products", "column_name": "Brand", "value": "Red Shirt", "normalized_value": "red shirt"},
    {"semantic_dimension_id": 11, "business_name": "Brand", "table_name": "Products", "column_name": "Brand", "value": "Viveagham Colour Shirt", "normalized_value": "viveagham colour shirt"},
    {"semantic_dimension_id": 12, "business_name": "Product Category", "table_name": "Products", "column_name": "CategoryName", "value": "T-Shirt", "normalized_value": "t-shirt"},

    # Banians
    {"semantic_dimension_id": 13, "business_name": "Category", "table_name": "Products", "column_name": "CategoryName", "value": "Banians", "normalized_value": "banians"},

    # Wears
    {"semantic_dimension_id": 14, "business_name": "Product Category", "table_name": "Products", "column_name": "CategoryName", "value": "Children Wear", "normalized_value": "children wear"},
    {"semantic_dimension_id": 15, "business_name": "Product Category", "table_name": "Products", "column_name": "CategoryName", "value": "Women's Wear", "normalized_value": "women's wear"},
    {"semantic_dimension_id": 16, "business_name": "Product Category", "table_name": "Products", "column_name": "CategoryName", "value": "Men's Wear", "normalized_value": "men's wear"},

    # Socks
    {"semantic_dimension_id": 17, "business_name": "Product Category", "table_name": "Products", "column_name": "CategoryName", "value": "Formal Socks", "normalized_value": "formal socks"},

    # Cotton
    {"semantic_dimension_id": 18, "business_name": "Fabric", "table_name": "Products", "column_name": "FabricType", "value": "Cotton", "normalized_value": "cotton"},
]

# Attempt to load from real DB, otherwise use mock rows
def load_index_data():
    try:
        # Check connection quickly
        with real_engine.connect() as conn:
            query = text("""
                SELECT
                    dvi.semantic_dimension_id,
                    sd.business_name,
                    sd.table_name,
                    sd.column_name,
                    dvi.value,
                    dvi.normalized_value
                FROM dimension_value_index dvi
                INNER JOIN semantic_dimensions sd 
                    ON sd.dimension_id = dvi.semantic_dimension_id
                WHERE sd.is_active = 1
                ORDER BY sd.business_name, dvi.value
            """)
            result = conn.execute(query)
            rows = [dict(row._mapping) for row in result.fetchall()]
            if rows:
                print(">>> Successfully loaded semantic index from the live database.", flush=True)
                return rows
    except Exception as e:
        print(f">>> Live database connection unavailable: {e}. Falling back to rich mock semantic index.", flush=True)
    return MOCK_INDEX_ROWS

def print_candidate(c, rank_idx=None):
    r_val = c.value
    norm_val = c.normalized_value
    mt = c.match_type.value if hasattr(c.match_type, "value") else str(c.match_type)
    
    # Calculate coverage
    q_toks = c.matched_question_tokens or []
    v_toks = c.matched_value_tokens or []
    
    q_cov = f"{len(q_toks)} tokens"
    v_cov = f"{len(v_toks)} tokens"
    
    prefix = f"  [{rank_idx}] " if rank_idx is not None else "  - "
    score_details = ""
    
    # Match ranker scoring details
    type_priority = 0
    if c.match_type == MatchType.EXACT:
        type_priority = 4
    elif c.match_type == MatchType.NORMALIZED:
        type_priority = 3
    elif c.match_type == MatchType.SINGULAR_PLURAL:
        type_priority = 2
    elif c.match_type == MatchType.FUZZY:
        type_priority = 1
        
    score_details = f"TypePriority={type_priority}, Conf={c.confidence:.3f}"
    
    print(f"{prefix}Value: '{r_val}' (Normalized: '{norm_val}') | MatchType: {mt} | Conf: {c.confidence:.3f}")
    print(f"      DimensionID: {c.dimension_id} | BusinessName: '{c.business_name}' | Table: '{c.table_name}' | Column: '{c.column_name}'")
    print(f"      Matched Question Tokens: {q_toks} | Matched Value Tokens: {v_toks}")
    print(f"      Score Components: {score_details}")

def run_forensic_trace(question_text: str, resolver: DimensionValueResolver):
    print("\n" + "="*80)
    print(f"FORENSIC RANKING TRACE FOR QUESTION: '{question_text}'")
    print("="*80)
    
    sanitized = DimensionValueResolver._normalize_text(question_text)
    from semantic.matching.stopwords import STOPWORDS
    q_tokens = [t for t in sanitized.split() if t not in STOPWORDS]
    
    # Get Cached values
    indexed_values = resolver._load_dimension_values("conn-1")
    
    # Run through the pipeline phases manually to trace them
    question_context = QuestionContext(
        raw_question=question_text,
        normalized_question=sanitized,
        q_tokens=q_tokens,
        q_singulars=[SingularPluralMatcher._to_singular(t) for t in q_tokens]
    )
    
    matching_context = MatchingContext(
        question_context=question_context,
        connection_id="conn-1",
        indexed_values=indexed_values,
        settings=resolver.settings
    )
    
    # 1. Raw Matches
    raw_matches, stats = resolver.pipeline.execute(matching_context)
    print(f"\n[PHASE 1] RAW MATCHES (Count: {len(raw_matches)}):")
    if not raw_matches:
        print("  None")
    for idx, c in enumerate(raw_matches):
        print_candidate(c, idx + 1)
        
    # 2. Consolidated Matches
    consolidated = resolver._consolidate_duplicate_matches(raw_matches)
    print(f"\n[PHASE 2] CONSOLIDATED MATCHES (Count: {len(consolidated)}):")
    if not consolidated:
        print("  None")
    for idx, c in enumerate(consolidated):
        print_candidate(c, idx + 1)
        
    # 3. Containment-Surviving Matches
    containment_surviving = resolver._remove_contained_matches(consolidated, q_tokens)
    print(f"\n[PHASE 3] CONTAINMENT-SURVIVING MATCHES (Count: {len(containment_surviving)}):")
    if not containment_surviving:
        print("  None")
    for idx, c in enumerate(containment_surviving):
        print_candidate(c, idx + 1)
        
    # 4. Final Ranked Matches
    final_ranked = MatchRanker.rank(containment_surviving, q_tokens)
    print(f"\n[PHASE 4] FINAL RANKED MATCHES (Count: {len(final_ranked)}):")
    if not final_ranked:
        print("  None")
    for idx, c in enumerate(final_ranked):
        print_candidate(c, idx + 1)
        
    # 5. Ambiguity Classifier Input & Classification Output
    ambig_res = AmbiguityClassifier.classify(final_ranked, q_tokens)
    print(f"\n[PHASE 5] AMBIGUITY CLASSIFIER OUTPUT:")
    print(f"  Status: {ambig_res.status.name}")
    if ambig_res.dominant_match:
        print(f"  Dominant Match: '{ambig_res.dominant_match.value}'")
    else:
        print("  Dominant Match: None")
    
    print("\n  Candidates entering classification:")
    for idx, choice in enumerate(ambig_res.candidates):
        print(f"  [{idx + 1}] Choice Value: '{choice.value}' | Coverage: {choice.actual_query_coverage} | Covered query tokens: {choice.matched_query_tokens}")
        print_candidate(choice.result)

# SingularPluralMatcher to resolve imports in trace
from semantic.matching.singular_plural_matcher import SingularPluralMatcher

def run_synthetic_cases():
    print("\n" + "="*80)
    print("RUNNING DETERMINISTIC SYNTHETIC RANKING CASES")
    print("="*80)
    
    # Case A: EXACT 1.00 vs FUZZY 0.90
    m_exact = MatchResult(
        matched=True, value="Linen Pant", normalized_value="linen pant", confidence=1.00,
        match_type=MatchType.EXACT, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
        reason="exact", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    m_fuzzy = MatchResult(
        matched=True, value="Ramraj Pant", normalized_value="ramraj pant", confidence=0.90,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["ramraj", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    ranked = MatchRanker.rank([m_fuzzy, m_exact], ["pant"])
    print(f"\nCase A (EXACT 1.00 vs FUZZY 0.90): First ranked = '{ranked[0].value}' (Match Type: {ranked[0].match_type.value})")
    
    # Case B: NORMALIZED 1.00 vs SINGULAR_PLURAL 0.95
    m_norm = MatchResult(
        matched=True, value="Linen Pant", normalized_value="linen pant", confidence=1.00,
        match_type=MatchType.NORMALIZED, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
        reason="normalized", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    m_sing = MatchResult(
        matched=True, value="Pants", normalized_value="pants", confidence=0.95,
        match_type=MatchType.SINGULAR_PLURAL, matched_question_tokens=["pant"], matched_value_tokens=["pants"],
        reason="singular_plural", dimension_id=1, business_name="Product Group", table_name="Products", column_name="ProductGroup"
    )
    ranked = MatchRanker.rank([m_sing, m_norm], ["pant"])
    print(f"Case B (NORMALIZED 1.00 vs SINGULAR_PLURAL 0.95): First ranked = '{ranked[0].value}' (Match Type: {ranked[0].match_type.value})")
    
    # Case C: SINGULAR_PLURAL 0.95 vs FUZZY 0.90
    m_sing = MatchResult(
        matched=True, value="Pants", normalized_value="pants", confidence=0.95,
        match_type=MatchType.SINGULAR_PLURAL, matched_question_tokens=["pant"], matched_value_tokens=["pants"],
        reason="singular_plural", dimension_id=1, business_name="Product Group", table_name="Products", column_name="ProductGroup"
    )
    m_fuzzy = MatchResult(
        matched=True, value="Linen Pant", normalized_value="linen pant", confidence=0.90,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    ranked = MatchRanker.rank([m_fuzzy, m_sing], ["pant"])
    print(f"Case C (SINGULAR_PLURAL 0.95 vs FUZZY 0.90): First ranked = '{ranked[0].value}' (Match Type: {ranked[0].match_type.value})")

    # Case D: FUZZY 0.92 vs FUZZY 0.86 (same coverage)
    m_fuzzy_hi = MatchResult(
        matched=True, value="Linen Pant", normalized_value="linen pant", confidence=0.92,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    m_fuzzy_lo = MatchResult(
        matched=True, value="Ramraj Pant", normalized_value="ramraj pant", confidence=0.86,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["ramraj", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    ranked = MatchRanker.rank([m_fuzzy_lo, m_fuzzy_hi], ["pant"])
    print(f"Case D (FUZZY 0.92 vs FUZZY 0.86 same coverage): First ranked = '{ranked[0].value}' (Confidence: {ranked[0].confidence:.2f})")

    # Case E: FUZZY 0.90 coverage 2/2 vs FUZZY 0.95 coverage 1/2
    m_cov2 = MatchResult(
        matched=True, value="Cotton Pant", normalized_value="cotton pant", confidence=0.90,
        match_type=MatchType.FUZZY, matched_question_tokens=["cotton", "pant"], matched_value_tokens=["cotton", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Product Group", table_name="Products", column_name="ProductGroup"
    )
    m_cov1 = MatchResult(
        matched=True, value="Ramraj Pant", normalized_value="ramraj pant", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["cotton", "pant"], matched_value_tokens=["ramraj", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    ranked = MatchRanker.rank([m_cov1, m_cov2], ["cotton", "pant"])
    print(f"Case E (FUZZY 0.90 cov 2/2 vs FUZZY 0.95 cov 1/2): First ranked = '{ranked[0].value}' (Coverage logic checked)")

    # Case F: Same dimension, equal confidence options (LINEN PANT vs RAMRAJ PANT)
    m_linen = MatchResult(
        matched=True, value="Linen Pant", normalized_value="linen pant", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["linen", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    m_ramraj = MatchResult(
        matched=True, value="Ramraj Pant", normalized_value="ramraj pant", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["ramraj", "pant"],
        reason="fuzzy", dimension_id=1, business_name="Brand", table_name="Products", column_name="Brand"
    )
    # Check if both remain as options in the ambiguity classifier
    ambig_res = AmbiguityClassifier.classify([m_linen, m_ramraj], ["pant"])
    print(f"Case F (Same Dimension alternatives equal confidence): Status = {ambig_res.status.name}, candidates = {[c.value for c in ambig_res.candidates]}")

    # Case G: Cross dimension (LS PANT -> Prod Grp2 vs RAMRAJ PANT -> Brand)
    m_ls = MatchResult(
        matched=True, value="LS Pant", normalized_value="ls pant", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["ls", "pant"],
        reason="fuzzy", dimension_id=5, business_name="Prod Grp2", table_name="Products", column_name="ProdGrp2"
    )
    m_ramraj_b = MatchResult(
        matched=True, value="Ramraj Pant", normalized_value="ramraj pant", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["pant"], matched_value_tokens=["ramraj", "pant"],
        reason="fuzzy", dimension_id=4, business_name="Brand", table_name="Products", column_name="Brand"
    )
    ambig_res_g = AmbiguityClassifier.classify([m_ls, m_ramraj_b], ["pant"])
    print(f"Case G (Cross Dimension): Status = {ambig_res_g.status.name}, dimensions = {[c.business_name for c in ambig_res_g.candidates]}")

    # Case H: Exact duplicate values in same dimension
    # (Duplicate test helper)
    m_dup1 = MatchResult(
        matched=True, value="Pants", normalized_value="pants", confidence=1.00,
        match_type=MatchType.EXACT, matched_question_tokens=["pants"], matched_value_tokens=["pants"],
        reason="exact", dimension_id=1, business_name="Product Group", table_name="Products", column_name="ProductGroup"
    )
    m_dup2 = MatchResult(
        matched=True, value="Pants", normalized_value="pants", confidence=0.98,
        match_type=MatchType.NORMALIZED, matched_question_tokens=["pants"], matched_value_tokens=["pants"],
        reason="normalized", dimension_id=1, business_name="Product Group", table_name="Products", column_name="ProductGroup"
    )
    consolidated = DimensionValueResolver._consolidate_duplicate_matches([m_dup1, m_dup2])
    print(f"Case H (Duplicate same value same dimension): Consolidated count = {len(consolidated)} (Value: '{consolidated[0].value}')")

    # Case I: Same value in different dimensions
    m_diff1 = MatchResult(
        matched=True, value="CommonVal", normalized_value="commonval", confidence=1.00,
        match_type=MatchType.EXACT, matched_question_tokens=["commonval"], matched_value_tokens=["commonval"],
        reason="exact", dimension_id=10, business_name="Category1", table_name="T1", column_name="C1"
    )
    m_diff2 = MatchResult(
        matched=True, value="CommonVal", normalized_value="commonval", confidence=1.00,
        match_type=MatchType.EXACT, matched_question_tokens=["commonval"], matched_value_tokens=["commonval"],
        reason="exact", dimension_id=11, business_name="Category2", table_name="T2", column_name="C2"
    )
    consolidated_i = DimensionValueResolver._consolidate_duplicate_matches([m_diff1, m_diff2])
    print(f"Case I (Same value different dimensions): Consolidated count = {len(consolidated_i)} (Dimensions: {[c.business_name for c in consolidated_i]})")

    # Case J: Partial candidates on disjoint query spans ("formal shirt")
    # formal -> one candidate, shirt -> another
    m_formal = MatchResult(
        matched=True, value="Formal Socks", normalized_value="formal socks", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["formal"], matched_value_tokens=["formal", "socks"],
        reason="fuzzy", dimension_id=17, business_name="Product Category", table_name="Products", column_name="CategoryName"
    )
    m_shirt = MatchResult(
        matched=True, value="Viveagham Colour Shirt", normalized_value="viveagham colour shirt", confidence=0.95,
        match_type=MatchType.FUZZY, matched_question_tokens=["shirt"], matched_value_tokens=["viveagham", "colour", "shirt"],
        reason="fuzzy", dimension_id=11, business_name="Brand", table_name="Products", column_name="Brand"
    )
    ranked = MatchRanker.rank([m_formal, m_shirt], ["formal", "shirt"])
    print(f"Case J (Disjoint partial matches): Ranked order = {[c.value for c in ranked]}")


def main():
    # Setup dimension value resolver
    rows = load_index_data()
    
    # We patch the database load function to return our rows instead of querying DB
    with patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=[
        # Convert index rows to CachedDimensionValue objects
        from_dict_to_cached(r) for r in rows
    ]):
        resolver = DimensionValueResolver()
        
        # Run real business queries
        queries = [
            "pant",
            "shirt",
            "cotton pant",
            "formal shirt",
            "banian",
            "banians",
            "children wear",
            "women wear",
            "mens wear",
            "t shirt",
            "red shirt",
            "cotton",
            "sales",
            "show sales",
            "total sales"
        ]
        
        for q in queries:
            run_forensic_trace(q, resolver)
            
        run_synthetic_cases()

def from_dict_to_cached(row):
    from semantic.matching.models import CachedDimensionValue
    from semantic.matching.singular_plural_matcher import SingularPluralMatcher
    from semantic.matching.stopwords import STOPWORDS
    
    raw_value = row["value"]
    stored_normalized = row["normalized_value"]
    norm_val_raw = DimensionValueResolver._normalize_text(raw_value)
    val_tokens = [t for t in norm_val_raw.split() if t not in STOPWORDS]
    val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]

    norm_val_stored = DimensionValueResolver._normalize_text(stored_normalized) if stored_normalized else ""
    stored_tokens = [t for t in norm_val_stored.split() if t not in STOPWORDS]
    stored_singulars = [SingularPluralMatcher._to_singular(t) for t in stored_tokens]

    return CachedDimensionValue(
        semantic_dimension_id=row["semantic_dimension_id"],
        business_name=row["business_name"],
        table_name=row["table_name"],
        column_name=row["column_name"],
        value=raw_value,
        normalized_value=stored_normalized if stored_normalized else "",
        runtime_stored_norm=norm_val_stored,
        runtime_stored_tokens=stored_tokens,
        runtime_stored_singulars=stored_singulars,
        runtime_raw_norm=norm_val_raw,
        runtime_raw_tokens=val_tokens,
        runtime_raw_singulars=val_singulars
    )

if __name__ == "__main__":
    main()
