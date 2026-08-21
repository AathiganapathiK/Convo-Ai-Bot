import json

results_path = "semantic_benchmark/results/retrieval_benchmark_results.json"
summary_path = "semantic_benchmark/results/retrieval_benchmark_summary.json"

with open(results_path, "r", encoding="utf-8") as f:
    results = json.load(f)

with open(summary_path, "r", encoding="utf-8") as f:
    summary = json.load(f)

print("Pass Rate:", summary["pass_rate"])
print("Passed:", summary["passed"])
print("Failed:", summary["failed"])
print("Errors:", summary["errors"])

# Category breakdown
print("\nCategory breakdown:")
for cat, stats in sorted(summary["category_breakdown"].items()):
    cat_eval = len([r for r in results if r["category"] == cat and r["scored"]])
    rate = round((stats["passed"] / cat_eval) * 100, 2) if cat_eval else 0.0
    print(f"{cat}: {stats['passed']}/{cat_eval} ({rate}%)")

# Source breakdown
print("\nSource breakdown:")
for src, stats in sorted(summary["source_breakdown"].items()):
    src_eval = len([r for r in results if r["source"] == src and r["scored"]])
    rate = round((stats["passed"] / src_eval) * 100, 2) if src_eval else 0.0
    print(f"{src}: {stats['passed']}/{src_eval} ({rate}%)")

# Failures
print("\nFailure breakdown:", summary["failure_breakdown"])
print("Cases with multiple failures:", summary["cases_with_multiple_failures"])
print("Avg duration:", summary["average_duration_ms"])
print("Total duration:", summary["total_duration_ms"])
