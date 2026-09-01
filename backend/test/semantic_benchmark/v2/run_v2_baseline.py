"""
Gate 3 Step 14 - baseline run against the authoritative Step 16 v2 benchmark.

The existing runner (run_retrieval_benchmark.py) loads v1 and writes to
results/. Neither is touched. This script imports that runner's `evaluate_case`
**unchanged**, so the comparison contract is identical, and only swaps the
dataset for v2 and the output for a new versioned directory.

Measurement only. Nothing here modifies expectations, verdicts, configuration
or production code.

    python backend/test/semantic_benchmark/v2/run_v2_baseline.py
"""

import datetime
import importlib.util
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
BACKEND = os.path.dirname(os.path.dirname(BENCH))
REPO = os.path.dirname(BACKEND)

sys.path.insert(0, BACKEND)
os.chdir(REPO)

# Import the v1 runner as a module purely to reuse evaluate_case().
_spec = importlib.util.spec_from_file_location(
    "v1_runner", os.path.join(BENCH, "run_retrieval_benchmark.py")
)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

# The v2 comparison contract: metrics and dimensions are matched on
# (table_name, column_name) rather than on a business name an administrator can
# rename. See evaluate_v2.py.
sys.path.insert(0, HERE)
from evaluate_v2 import evaluate_case_v2  # noqa: E402

V2_FILES = [os.path.join(HERE, "golden_dataset_v2_c%d.json" % i) for i in range(1, 7)]

RUN_ID = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
OUT_DIR = os.path.join(HERE, "baseline_runs", RUN_ID)


def main():
    cases = []
    for path in V2_FILES:
        with open(path, encoding="utf-8") as fh:
            cases.extend(json.load(fh))

    if len(cases) != 194:
        sys.exit("Expected 194 v2 cases, found %d - refusing to run." % len(cases))

    connection_id = runner.resolve_logical_connection()

    print("Step 14 baseline - benchmark v2, %d cases, connection %s"
          % (len(cases), connection_id))

    results = []
    for i, case in enumerate(cases, 1):
        rec = {
            "case_id": case["case_id"],
            "question": case["question"],
            "category": case["category"],
            "benchmark_verdict": case["expectation_review"]["verdict"],
            "data_answerable": case.get("data_answerable"),
            "step15_primary_root_cause": None,
            "execution_error": None,
        }
        try:
            res = evaluate_case_v2(
                case,
                connection_id,
                resolver=runner.SemanticResolver,
                normalize_list=runner.normalize_list,
            )
            rec["comparison_mode"] = res.get("comparison_mode")
            rec.update({
                "scored": res["scored"],
                "pass_fail": res["pass_fail"],
                "failure_codes": res["failure_codes"],
                "failure_details": res.get("failure_details"),
                "expected": res["expected"],
                "actual": res.get("actual"),
                "duration_ms": res.get("duration_ms"),
                "reason": res.get("reason"),
            })
        except Exception as exc:
            # An infrastructure failure is recorded as EXECUTION_ERROR. It is
            # never counted as a semantic pass, and never as a semantic failure
            # without evidence of a semantic divergence.
            rec.update({
                "scored": False,
                "pass_fail": "EXECUTION_ERROR",
                "failure_codes": [],
                "failure_details": None,
                "expected": case["expected"],
                "actual": None,
                "duration_ms": None,
                "reason": str(exc)[:300],
            })
            rec["execution_error"] = traceback.format_exc()[-1500:]

        results.append(rec)
        if i % 25 == 0:
            print("  ...%d/%d" % (i, len(cases)), file=sys.stderr)

    # attach the Step 15 diagnosis, read-only, for confirm/revise analysis
    s15_path = os.path.join(HERE, "step15_root_cause_analysis.json")
    if os.path.exists(s15_path):
        s15 = {c["case_id"]: c for c in
               json.load(open(s15_path, encoding="utf-8"))["cases"]}
        for r in results:
            if r["case_id"] in s15:
                r["step15_primary_root_cause"] = s15[r["case_id"]]["primary_root_cause"]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "results.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "run_id": RUN_ID,
            "benchmark_version": "v2 (Step 16 authoritative)",
            "connection_id": connection_id,
            "case_count": len(results),
            "results": results,
        }, fh, indent=1)

    import collections
    pf = collections.Counter(r["pass_fail"] for r in results)
    print("\n%s" % ("=" * 60))
    print("cases        : %d" % len(results))
    print("pass_fail    : %s" % dict(pf))
    print("written to   : %s" % os.path.relpath(os.path.join(OUT_DIR, "results.json"), REPO))
    print("=" * 60)


if __name__ == "__main__":
    main()
