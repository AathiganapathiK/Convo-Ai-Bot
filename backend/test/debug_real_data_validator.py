import os
import json
import sys

# Ensure backend root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.semantic_resolver import SemanticResolver
from semantic.dimension_value_resolver import DimensionValueResolver

queries = [
    "brand ramraj pant",
    "ramraj pant brand",
    "city coimbatore",
    "coimbatore city",
    "state tamil nadu",
    "tamil nadu state",
    "brand ramraj",
    "show sales for pant",
    "show sales for coimbatore",
    "show brand sales for coimbatore"
]

CONN_ID = "test-conn" # Or check local active connection ID from database.
# Let's dynamically load the active connection ID
from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    row = conn.execute(text("SELECT DISTINCT connection_id FROM semantic_dimensions WHERE connection_id = 'F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5'")).fetchone()
    if row:
        CONN_ID = row[0]
        print(f"Using active connection ID: {CONN_ID}")
    else:
        # fallback to fetchone()
        row = conn.execute(text("SELECT DISTINCT connection_id FROM semantic_dimensions")).fetchone()
        if row:
            CONN_ID = row[0]
            print(f"Using active connection ID: {CONN_ID}")
        else:
            print("No connection_id found in semantic_dimensions, using 'test-conn'.")

print("==================================================")
print("REAL-DATA VALIDATION RESULTS")
print("==================================================")

for q in queries:
    print(f"\nQUERY: '{q}'")
    # Resolve using SemanticResolver
    res = SemanticResolver.resolve(CONN_ID, q)
    
    # Let's inspect what happens inside DimensionValueResolver by manually running parts of it for logging
    # 1) Generate dimension context from query
    metric_rows, dimension_rows = SemanticResolver._fetch_active_metadata(CONN_ID)
    candidates = SemanticResolver._generate_candidates(metric_rows, dimension_rows, q)
    dim_context = [
        {
            "dimension_name": cand.get("dimension_name"),
            "business_name": cand.get("business_name"),
            "table_name": cand.get("table_name"),
            "column_name": cand.get("column_name"),
            "matched_text": cand.get("matched_text"),
            "spans": cand.get("spans")
        }
        for cand in candidates
        if cand.get("type") == "dimension"
    ]
    
    # 2) Run matcher pipeline to get candidates before filtering
    resolver = DimensionValueResolver()
    question = resolver._normalize_text(q)
    q_tokens = [t for t in question.split() if t not in resolver.pipeline.matchers[0].match_type.__class__.__module__] # dummy import check
    # Let's run matching context
    from semantic.matching.models import QuestionContext, MatchingContext
    from semantic.matching.stopwords import STOPWORDS
    from semantic.matching.singular_plural_matcher import SingularPluralMatcher
    
    q_tokens = [t for t in question.split() if t not in STOPWORDS]
    q_singulars = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
    question_context = QuestionContext(
        raw_question=q,
        normalized_question=question,
        q_tokens=q_tokens,
        q_singulars=q_singulars
    )
    indexed_values = resolver._load_dimension_values(CONN_ID)
    matching_context = MatchingContext(
        question_context=question_context,
        connection_id=CONN_ID,
        indexed_values=indexed_values,
        settings=resolver.settings
    )
    
    raw_matches, _ = resolver.pipeline.execute(matching_context)
    raw_matches = resolver._consolidate_duplicate_matches(raw_matches)
    raw_matches = resolver._remove_contained_matches(raw_matches, q_tokens)
    
    # Let's check explicit dimension detected
    detected_dims = []
    q_words = question.split()
    for m in raw_matches:
        val_norm = m.normalized_value or m.value.lower()
        indices = resolver._find_match_span_indices(q_words, val_norm)
        if indices:
            min_idx = min(indices)
            max_idx = max(indices)
            adjacent_words = []
            if min_idx > 0:
                adjacent_words.append(q_words[min_idx - 1])
            if max_idx < len(q_words) - 1:
                adjacent_words.append(q_words[max_idx + 1])
            for word in adjacent_words:
                matched_dim_name = resolver._find_matching_dimension(word, dim_context)
                if matched_dim_name:
                    detected_dims.append(matched_dim_name)
                    
    detected_dims = sorted(list(set(detected_dims)))
    
    # Candidates before contextual filtering
    before_strs = [f"{m.value} ({m.business_name})" for m in raw_matches]
    
    # Candidates after contextual filtering (value_matches from result)
    after_strs = []
    val_matches = res.get("value_matches", [])
    for vm in val_matches:
        after_strs.append(f"{vm['value']} ({vm['business_name']})")
        
    ambig_res = res.get("ambiguity_result")
    ambig_status = ambig_res.status.value if ambig_res else "NO_MATCH"
    
    selected_val = None
    if ambig_res and ambig_res.dominant_match:
        selected_val = f"{ambig_res.dominant_match.result.value} ({ambig_res.dominant_match.result.business_name})"
        
    print(f"  - Explicit Dimension Detected: {detected_dims if detected_dims else 'None'}")
    print(f"  - Selected Dimension: {detected_dims if len(detected_dims) == 1 else 'None'}")
    print(f"  - Candidates Before Contextual Filtering: {before_strs}")
    print(f"  - Candidates After Contextual Filtering: {after_strs}")
    print(f"  - Final Ambiguity Status: {ambig_status}")
    print(f"  - Final Selected Value: {selected_val}")
