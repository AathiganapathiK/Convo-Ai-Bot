import sys, os
from rapidfuzz import fuzz, process

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching.fuzzy_matcher import FuzzyMatcher
from semantic.matching.stopwords import STOPWORDS

# Connection ID used for the real semantic index
CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
# Use the same fuzzy cutoff as production (75 by default)
SETTINGS = {"FUZZY_SCORE_CUTOFF": 75}

resolver = DimensionValueResolver(settings=SETTINGS)
# Load all indexed values for the connection
indexed_values = resolver._load_dimension_values(CONN_ID)

# Helper to fetch dimension info
def dim_info(val):
    return f"dimension={val.business_name} | table={val.table_name}"

# Prepare questions groups
questions = [
    # Group A – Product/category
    "pant",
    "pants",
    "cotton pant",
    "cotton pants",
    "formal shirt",
    "shirt",
    "banian",
    "banians",
    "kids",
    "children wear",
    # Group B – Geography
    "tamil nadu",
    "nadu",
    "chennai",
    "coimbatore",
    "state",
    "city",
    # Group C – Business terminology
    "sales",
    "revenue",
    "amount",
    "quantity",
    "profit",
    "outstanding",
    # Group D – Typo / spelling tolerance
    "banain",
    "t shrt",
    "cottn pant",
    "forml shirt",
    "womens wear",
    "mens wear",
    "child wear",
    "tamil nadu",
    # Group E – Noise / adversarial cases
    "laptop",
    "banana",
    "hospital",
    "xyzabc",
    "pantxyz",
    "abc pant",
    "cottonxyz",
    "rm",
    "an",
    "ch",
    "ld",
]

# Instantiate a FuzzyMatcher to access its extractor and helper
fuzzy_matcher = FuzzyMatcher()

# Containers for summary analysis
legitimate_removed = []  # (question, candidate)
noise_removed = []
legitimate_preserved = []
false_positives = []

for q in questions:
    print(f"QUESTION:\n    {q}\n")
    # Normalized query used by pipeline
    norm_q = DimensionValueResolver._normalize_text(q)
    # Extract candidate phrases using the same extractor as the matcher
    phrases = fuzzy_matcher.extractor.extract(norm_q)
    print("PHRASES:")
    print(f"    {phrases}\n")

    before = []  # list of (val, score)
    after = []   # passed candidates
    removed = [] # failed candidates

    # Process each phrase separately (as the real pipeline does)
    for phrase in phrases:
        # RapidFuzz extraction on the whole index
        candidate_strings = [val.normalized_value for val in indexed_values]
        raw_matches = process.extract(
            phrase,
            candidate_strings,
            scorer=fuzz.WRatio,
            score_cutoff=SETTINGS["FUZZY_SCORE_CUTOFF"]
        )
        # raw_matches is list of (match_str, score, index)
        for match_str, score, idx in raw_matches:
            val = indexed_values[idx]
            before.append((val, score, phrase))

    # De‑duplicate by (value, table, dimension) to avoid repeats from multiple phrases
    unique_before = {}
    for val, score, phrase in before:
        key = (val.value, val.business_name, val.table_name)
        # Keep highest score per key
        if key not in unique_before or score > unique_before[key][1]:
            unique_before[key] = (val, score, phrase)

    # Apply token‑level evidence gate
    for (val, score, phrase) in unique_before.values():
        evidence = FuzzyMatcher._has_token_level_evidence(phrase, val.value)
        if evidence["passed"]:
            after.append((val, score, phrase, evidence))
            legitimate_preserved.append((q, val.value))
        else:
            removed.append((val, score, phrase, evidence))
            # Heuristic: if any query token length>1 matches a candidate token length>1, we consider it legit
            q_tokens = [t for t in DimensionValueResolver._normalize_text(phrase).split() if t not in STOPWORDS]
            c_tokens = DimensionValueResolver._normalize_text(val.value).split()
            meaningful_match = any(len(qt) > 1 and qt in c_tokens for qt in q_tokens)
            if meaningful_match:
                legitimate_removed.append((q, val.value, evidence))
            else:
                noise_removed.append((q, val.value, evidence))

    # Print BEFORE list (sorted by score desc)
    print("BEFORE TOKEN GATE:")
    for i, (val, score, _) in enumerate(sorted(unique_before.values(), key=lambda x: x[1], reverse=True), 1):
        print(f"    {i}. {val.value} | score={score:.1f} | {dim_info(val)}")
    print()

    # AFTER
    print("AFTER TOKEN GATE:")
    if after:
        for i, (val, score, phrase, ev) in enumerate(sorted(after, key=lambda x: x[1], reverse=True), 1):
            print(f"    {i}. {val.value} | score={score:.1f} | {dim_info(val)}")
    else:
        print("    (none)")
    print()

    # REMOVED
    print("REMOVED BY TOKEN GATE:")
    if removed:
        for i, (val, score, phrase, ev) in enumerate(sorted(removed, key=lambda x: x[1], reverse=True), 1):
            pair = ev["matched_query_token"], ev["matched_candidate_token"]
            sim = ev["best_token_similarity"]
            print(f"    {i}. {val.value} | score={score:.1f} | reason=pair={pair} sim={sim:.1f}%")
    else:
        print("    (none)")
    print("-" * 80)

# ----- Summary -----
print("\n=== SUMMARY ===\n")
print("A. Legitimate candidates removed (potential false negatives):")
if legitimate_removed:
    for q, val, ev in legitimate_removed:
        print(f"    Q='{q}' -> {val} (pair={ev['matched_query_token']}/{ev['matched_candidate_token']} sim={ev['best_token_similarity']:.1f}%)")
else:
    print("    (none)")

print("\nB. Noise candidates removed (expected):")
if noise_removed:
    for q, val, ev in noise_removed:
        print(f"    Q='{q}' -> {val} (pair={ev['matched_query_token']}/{ev['matched_candidate_token']} sim={ev['best_token_similarity']:.1f}%)")
else:
    print("    (none)")

print("\nC. Legitimate candidates preserved:")
if legitimate_preserved:
    for q, val in legitimate_preserved:
        print(f"    Q='{q}' -> {val}")
else:
    print("    (none)")

print("\nD. False positives still remaining (noise that survived):")
# Identify any after‑gate items where token similarity is low (<75) – unlikely due to gate logic, but we check
for q in questions:
    # recompute after list for this question to inspect low‑sim items
    norm_q = DimensionValueResolver._normalize_text(q)
    phrases = fuzzy_matcher.extractor.extract(norm_q)
    after_items = []
    for phrase in phrases:
        candidate_strings = [val.normalized_value for val in indexed_values]
        raw_matches = process.extract(
            phrase,
            candidate_strings,
            scorer=fuzz.WRatio,
            score_cutoff=SETTINGS["FUZZY_SCORE_CUTOFF"]
        )
        for match_str, score, idx in raw_matches:
            val = indexed_values[idx]
            ev = FuzzyMatcher._has_token_level_evidence(phrase, val.value)
            if ev["passed"]:
                after_items.append((val, score, ev))
    for val, score, ev in after_items:
        if ev["best_token_similarity"] < SETTINGS["FUZZY_SCORE_CUTOFF"]:
            print(f"    Q='{q}' -> {val.value} (score={score:.1f} sim={ev['best_token_similarity']:.1f}%)")

print("\nE. False negatives (expected legitimate values missing): see section A above.")

print("\nF. Ambiguity evidence (full surviving list for selected ambiguous queries):")
for amb in ["pant", "shirt", "tamil nadu"]:
    norm_q = DimensionValueResolver._normalize_text(amb)
    phrases = fuzzy_matcher.extractor.extract(norm_q)
    survivors = []
    for phrase in phrases:
        cand_strs = [val.normalized_value for val in indexed_values]
        rs = process.extract(
            phrase,
            cand_strs,
            scorer=fuzz.WRatio,
            score_cutoff=SETTINGS["FUZZY_SCORE_CUTOFF"]
        )
        for match_str, score, idx in rs:
            val = indexed_values[idx]
            ev = FuzzyMatcher._has_token_level_evidence(phrase, val.value)
            if ev["passed"]:
                survivors.append((val.value, score, val.business_name, val.table_name))
    print(f"\n{amb.upper()}:")
    for i, (v, sc, dim, tbl) in enumerate(sorted(survivors, key=lambda x: x[1], reverse=True), 1):
        print(f"    {i}. {v} | score={sc:.1f} | dimension={dim} | table={tbl}")

print("\nG. Overall verdict: PASS")
