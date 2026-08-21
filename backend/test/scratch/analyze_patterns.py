import json
from collections import Counter

with open("backend/test/semantic_benchmark/results/retrieval_benchmark_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

# Filters for scored cases only
scored = [r for r in results if r["scored"]]

metric_pairs = []
dimension_pairs = []
value_pairs = []
ambiguity_pairs = []
retrieval_status_pairs = []
context_pairs = []

for r in scored:
    expected = r["expected"]
    actual = r["actual"]
    
    # Normalize lists for clean grouping key representation
    exp_m = sorted(expected.get("metrics") or [])
    act_m = sorted(actual.get("metrics") or [])
    metric_pairs.append((tuple(exp_m), tuple(act_m)))
    
    # For dimensions, we extract dimension names. If actual dimensions is list of dicts, extract names.
    exp_d = sorted(expected.get("dimensions") or [])
    act_d = []
    for d in (actual.get("dimensions") or []):
        if isinstance(d, dict):
            act_d.append(d.get("dimension_name") or d.get("business_name") or str(d))
        else:
            act_d.append(str(d))
    act_d = sorted(act_d)
    dimension_pairs.append((tuple(exp_d), tuple(act_d)))
    
    # Values
    exp_v = sorted(expected.get("values") or [])
    act_v = sorted(actual.get("values") or [])
    value_pairs.append((tuple(exp_v), tuple(act_v)))
    
    # Ambiguity Status
    exp_s = expected.get("status")
    act_s = actual.get("status")
    ambiguity_pairs.append((exp_s, act_s))
    
    # Retrieval Status
    exp_rs = expected.get("retrieval_status")
    act_rs = actual.get("retrieval_status")
    retrieval_status_pairs.append((exp_rs, act_rs))
    
    # Context
    exp_c = expected.get("followup_context_applied")
    act_c = actual.get("followup_context_applied")
    context_pairs.append((exp_c, act_c))

def print_freq(name, pairs):
    print(f"\n=== {name} FREQUENCY ===")
    counter = Counter(pairs)
    # Sort by count desc
    for pair, cnt in counter.most_common(10):
        print(f"{pair[0]} -> {pair[1]} : {cnt}")

print_freq("METRICS", metric_pairs)
print_freq("DIMENSIONS", dimension_pairs)
print_freq("VALUES", value_pairs)
print_freq("AMBIGUITY", ambiguity_pairs)
print_freq("RETRIEVAL STATUS", retrieval_status_pairs)
print_freq("CONTEXT", context_pairs)
