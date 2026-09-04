#!/usr/bin/env python
"""
Gate 4 plan-accuracy evaluator.

TWO EVALUATORS, ONE DATASET, ZERO CONFLICTS

evaluate_v2.py scores retrieval - metrics, dimensions, values, ambiguity,
retrieval status. That is Gate 3's measurement and it owns the verdicts in the
golden_dataset_v2_c*.json files, which took a full Step 16 audit pass to
establish.

This scores the Gate 4 fields only: mode, ranking direction, ranking measure,
top_n, benchmark, and the assumptions Gate 4 recorded. It reads the golden files
for two things - case_id and question - and never writes to them. Expectations
live in expected_plan_v2.json, keyed by case_id, so the two evaluators can be
changed independently without either touching the other's file.

WHAT THIS SET CAN AND CANNOT MEASURE

Read the _meta block of expected_plan_v2.json before quoting a number from this
script. Every one of the 194 cases is a descriptive retrieval question of the
form "Show sales for Chennai city". The set contains no ranking, no trend, no
comparison and no diagnostic question, so it cannot demonstrate that mode
detection or ranking extraction is correct.

What it does demonstrate is the other half of the requirement, and the half that
is easier to get wrong at scale: that Gate 4 does not invent structure. A model
asked to extract a ranking from 194 questions that contain no ranking has 194
chances to hallucinate one, and every fabricated top_n or benchmark here would
become a wrong confident answer in production.

The canonical ranking behaviour is covered by test/test_gate4_extraction.py,
which exercises it directly.

RUNNING

    python test/semantic_benchmark/v2/evaluate_plan_v2.py

Offline by default: no model is called, so the run is deterministic and
reproducible, and it measures the deterministic extraction path. Pass --live to
route extraction through the configured provider instead.
"""

import argparse
import collections
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

EXPECTED_FILE = os.path.join(HERE, "expected_plan_v2.json")
GOLDEN_GLOB = os.path.join(HERE, "golden_dataset_v2_c*.json")

# The Gate 4 fields this evaluator scores. Anything outside this tuple belongs
# to another gate and is deliberately not compared.
SCORED_FIELDS = ("mode", "direction", "measure", "top_n", "benchmark")


def load_golden(golden_dir: Optional[str] = None) -> Dict[str, dict]:
    """
    case_id -> case, read from the immutable Gate 3 datasets.

    Only case_id, question and category are ever consulted. The expectation
    blocks in these files are Gate 3's and are not this evaluator's business.
    """
    pattern = (
        os.path.join(golden_dir, "golden_dataset_v2_c*.json")
        if golden_dir else GOLDEN_GLOB
    )
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(
            f"No golden datasets found at {GOLDEN_GLOB}.\n"
            "The Gate 3 Step 16 commit provides them; this branch may not have "
            "it yet. Fetch it before running the plan benchmark."
        )

    cases: Dict[str, dict] = {}
    for path in files:
        with open(path, encoding="utf-8") as handle:
            for case in json.load(handle):
                cases[case["case_id"]] = case
    return cases


def load_expected() -> dict:
    with open(EXPECTED_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def _enum_value(value: Any) -> Optional[str]:
    """Enum member, plain string or None, rendered as a comparable string."""
    if value is None:
        return None
    return getattr(value, "value", value)


def build_actual(question: str, live: bool) -> dict:
    """
    Run the Gate 4 pipeline for one question and report its plan fields.

    The plan is built with an empty semantic_result. That is deliberate: the
    resolver's output feeds the metrics and dimensions Gate 3 measures, and
    including it here would make this score depend on Gate 3's current state and
    move whenever their branch moves. The Gate 4 fields are derived from the
    question and the extraction, so an empty resolution isolates exactly what
    this evaluator is responsible for.
    """
    from ai import assumptions as gate4_assumptions
    from ai.extraction.slot_extractor import extract_intent
    from semantic.semantic_plan_builder import SemanticPlanBuilder

    invoke = None if live else (lambda purpose, prompt: None)

    intent = extract_intent(question=question, vocabulary=None, invoke=invoke)
    outcome = gate4_assumptions.resolve(intent)
    intent.assumptions_made = gate4_assumptions.merge_into(
        intent.assumptions_made, outcome.assumptions
    )

    plan = SemanticPlanBuilder.build(
        question=question, semantic_result={}, extracted=intent
    )

    ranking = plan.ranking
    return {
        "mode": _enum_value(plan.mode),
        "direction": _enum_value(ranking.direction) if ranking else None,
        "measure": _enum_value(ranking.measure) if ranking else None,
        "top_n": ranking.top_n if ranking else None,
        "benchmark": _enum_value(plan.benchmark.benchmark_type) if plan.benchmark else None,
        # Only Gate 4's own disclosures. plan.assumptions_made also carries the
        # snapshot-configuration note the builder writes before Gate 4 runs, and
        # scoring that would be scoring somebody else's work.
        "assumptions": list(intent.assumptions_made),
        "escalation_tier": intent.escalation_tier.value,
        "clarification": intent.clarification.slot if intent.clarification else None,
        "unsupported": list(intent.unsupported),
    }


def compare(expected: dict, actual: dict) -> List[str]:
    """Field-level mismatches for one case."""
    problems = []

    for field in SCORED_FIELDS:
        want = expected.get(field)
        got = actual.get(field)
        if want != got:
            problems.append(f"{field}: expected {want!r}, got {got!r}")

    want_assumptions = expected.get("assumptions") or []
    got_assumptions = actual.get("assumptions") or []
    if len(want_assumptions) != len(got_assumptions):
        problems.append(
            f"assumptions: expected {len(want_assumptions)}, "
            f"got {len(got_assumptions)} ({got_assumptions})"
        )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate 4 plan accuracy.")
    parser.add_argument(
        "--live", action="store_true",
        help="Call the configured model instead of the deterministic path.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print every failing case."
    )
    parser.add_argument(
        "--golden-dir",
        help=(
            "Directory holding golden_dataset_v2_c*.json. Defaults to this "
            "one. Useful while the Gate 3 Step 16 commit is not yet on the "
            "current branch."
        ),
    )
    args = parser.parse_args()

    golden = load_golden(args.golden_dir)
    document = load_expected()
    expectations = document["cases"]

    missing = sorted(set(expectations) - set(golden))
    unexpected = sorted(set(golden) - set(expectations))

    results = []
    by_category = collections.defaultdict(lambda: {"total": 0, "passed": 0})
    failure_fields = collections.Counter()

    for case_id in sorted(set(golden) & set(expectations)):
        case = golden[case_id]
        expected = expectations[case_id]
        category = case.get("category", "UNKNOWN")

        try:
            actual = build_actual(case["question"], live=args.live)
            problems = compare(expected, actual)
            error = None
        except Exception as exc:                      # noqa: BLE001
            actual, problems, error = {}, [f"error: {exc}"], str(exc)

        passed = not problems
        by_category[category]["total"] += 1
        if passed:
            by_category[category]["passed"] += 1
        else:
            for problem in problems:
                failure_fields[problem.split(":")[0]] += 1

        results.append({
            "case_id": case_id,
            "category": category,
            "question": case["question"],
            "passed": passed,
            "problems": problems,
            "actual": actual,
            "error": error,
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = (passed / total * 100) if total else 0.0

    print()
    print("=" * 68)
    print("GATE 4 PLAN ACCURACY")
    print("=" * 68)
    print(f"Mode              : {'live model' if args.live else 'deterministic (no model)'}")
    print(f"Cases evaluated   : {total}")
    print(f"Passed            : {passed}")
    print(f"Failed            : {total - passed}")
    print(f"Plan accuracy     : {accuracy:.2f}%")
    if missing:
        print(f"Expected-but-absent from the golden set : {missing}")
    if unexpected:
        print(f"Golden cases with no expectation        : {unexpected}")
    print()

    print("BY CATEGORY")
    for category in sorted(by_category):
        stats = by_category[category]
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0.0
        print(f"  {category:24} {stats['passed']:3}/{stats['total']:<3}  {rate:6.2f}%")
    print()

    if failure_fields:
        print("FAILURES BY FIELD")
        for field, count in failure_fields.most_common():
            print(f"  {field:24} {count}")
        print()

    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"FAILING CASES ({len(failures)})")
        for result in failures if args.verbose else failures[:20]:
            print(f"  {result['case_id']} [{result['category']}] {result['question']!r}")
            for problem in result["problems"]:
                print(f"      {problem}")
        if not args.verbose and len(failures) > 20:
            print(f"  ... {len(failures) - 20} more; rerun with --verbose")
        print()

    print("SCOPE NOTE")
    print("  " + document["_meta"]["finding"].replace(". ", ".\n  "))
    print()

    output = os.path.join(HERE, "plan_accuracy_v2.json")
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "mode": "live" if args.live else "deterministic",
                "total": total,
                "passed": passed,
                "accuracy": round(accuracy, 2),
                "by_category": {k: dict(v) for k, v in by_category.items()},
                "failures": [r for r in results if not r["passed"]],
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Detail written to {output}")

    # A non-zero exit below the target makes this usable as a gate in CI.
    return 0 if accuracy >= 90.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
