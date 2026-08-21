#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
from typing import List, Dict, Any, Optional

# Add backend directory to path to locate dependencies
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    from database import engine
    from semantic.semantic_resolver import SemanticResolver
    from services.connection_service import ConnectionService
    from semantic.matching.models import ResolutionStatus
except ImportError as e:
    print(f"Error importing production modules: {e}")
    sys.exit(1)

# List of golden dataset files
DATASET_FILES = [
    "backend/test/semantic_benchmark/golden_dataset_1e_2_c1.json",
    "backend/test/semantic_benchmark/golden_dataset_1e_2_c2.json",
    "backend/test/semantic_benchmark/golden_dataset_1e_2_c3.json",
    "backend/test/semantic_benchmark/golden_dataset_1e_2_c4.json",
    "backend/test/semantic_benchmark/golden_dataset_1e_2_c5.json",
    "backend/test/semantic_benchmark/golden_dataset_1e_2_c6.json"
]

SMOKE_CASE_IDS = {"E1-006", "E1-024", "E1-082", "E1-154", "E1-190", "E1-196"}

def resolve_logical_connection() -> str:
    """
    Resolves the logical connection 'Chatbot' to its physical connection UUID.
    """
    ref_name = os.getenv("BENCHMARK_DATASOURCE_REF", "Chatbot")
    try:
        connections = ConnectionService.get_connections()
        for conn in connections:
            if conn.get("connection_name") == ref_name:
                conn_id = conn.get("connection_id")
                if conn_id:
                    print(f"Resolved logical connection '{ref_name}' to ID: {conn_id}")
                    return str(conn_id)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch connections from database during logical connection resolution: {e}")
    
    raise ValueError(f"Error: Could not resolve logical connection '{ref_name}'. No matching connection found in database.")

def validate_and_load_cases() -> List[Dict[str, Any]]:
    """
    Loads, merges, and validates all benchmark cases from files.
    """
    cases = []
    seen_ids = set()
    seen_questions = set()
    
    for filename in DATASET_FILES:
        filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", filename))
        if not os.path.exists(filepath):
            print(f"Error: Dataset file not found: {filepath}")
            sys.exit(1)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for case in data:
                case_id = case.get("case_id")
                # 1. Structural checks
                required = {"case_id", "category", "source", "severity", "question", "expected"}
                missing = required - set(case.keys())
                if missing:
                    raise ValueError(f"Case {case_id} missing required fields: {missing}")
                
                # 2. Check for duplicate IDs
                if case_id in seen_ids:
                    raise ValueError(f"Duplicate case_id found: {case_id}")
                seen_ids.add(case_id)
                
                # 3. Check for duplicate questions (normalized)
                q_norm = " ".join(case["question"].lower().split())
                if q_norm in seen_questions:
                    raise ValueError(f"Duplicate normalized question found: '{case['question']}'")
                seen_questions.add(q_norm)
                
                cases.append(case)
                
    # Sort merged cases by case_id
    cases.sort(key=lambda c: int(c["case_id"].split("-")[1]))
    return cases

def normalize_list(lst: Optional[List[Any]]) -> List[str]:
    """
    Helper to normalize lists (metrics, dimensions, values) for comparison.
    """
    if not lst:
        return []
    return sorted([str(x).strip().lower() for x in lst if x is not None])

def evaluate_case(case: Dict[str, Any], connection_id: str) -> Dict[str, Any]:
    """
    Executes and scores a single benchmark case.
    """
    case_id = case["case_id"]
    question = case["question"]
    expected = case["expected"]
    impl_status = expected.get("implementation_status", "CURRENTLY_IMPLEMENTED")
    
    result_record = {
        "case_id": case_id,
        "question": question,
        "category": case["category"],
        "source": case["source"],
        "implementation_status": impl_status,
        "scored": False,
        "pass_fail": "SKIPPED",
        "failure_codes": [],
        "failure_details": {},
        "reason": None,
        "duration_ms": 0.0,
        "expected": expected,
        "actual": None
    }
    
    if impl_status == "FUTURE_PHASE":
        result_record["reason"] = "future capability"
        return result_record
        
    start_time = time.perf_counter()
    try:
        # Replay conversation history for multi-turn cases
        prev_context = None
        for turn in case.get("conversation", []):
            turn_q = turn["question"]
            res = SemanticResolver.resolve(
                connection_id=connection_id,
                question=turn_q,
                previous_semantic_context=prev_context
            )
            # Reconstruct previous turn context structure
            prev_context = {
                "metrics": [
                    {
                        "metric_name": m.get("metric_name"),
                        "business_name": m.get("business_name"),
                        "table_name": m.get("table_name"),
                        "column_name": m.get("column_name")
                    } for m in res.get("metric_objects", [])
                ],
                "dimensions": [
                    {
                        "dimension_name": d.get("dimension_name"),
                        "business_name": d.get("business_name"),
                        "table_name": d.get("table_name"),
                        "column_name": d.get("column_name")
                    } for d in res.get("dimension_objects", [])
                ],
                "resolved_values": [
                    {
                        "dimension_id": v.get("dimension_id"),
                        "business_name": v.get("business_name"),
                        "table_name": v.get("table_name"),
                        "column_name": v.get("column_name"),
                        "value": v.get("value"),
                        "normalized_value": v.get("normalized_value", v.get("value").lower() if v.get("value") else "")
                    } for v in res.get("value_matches", [])
                ]
            }
            
        # Execute final turn
        final_res = SemanticResolver.resolve(
            connection_id=connection_id,
            question=question,
            previous_semantic_context=prev_context
        )
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        result_record["duration_ms"] = duration_ms
        result_record["scored"] = True
        
        # Extract and normalize actual results according to precise result contract
        actual_metrics = [m.get("business_name") for m in final_res.get("metric_objects", [])]
        actual_dimensions = [
            {
                "dimension_name": d.get("dimension_name"),
                "business_name": d.get("business_name"),
                "table_name": d.get("table_name"),
                "column_name": d.get("column_name")
            } for d in final_res.get("dimension_objects", [])
        ]
        actual_values = [v.get("value") for v in final_res.get("value_matches", [])]
        
        # Ambiguity resolution status
        ambig_res = final_res.get("ambiguity_result")
        actual_val_status = ambig_res.status.value if ambig_res and hasattr(ambig_res.status, "value") else "NO_MATCH"
        
        # Retrieval status
        retrieval_block = final_res.get("retrieval")
        if not retrieval_block or "status" not in retrieval_block:
            raise ValueError("SemanticResolver result missing retrieval.status")
        retrieval_status = retrieval_block["status"]
        if retrieval_status not in {"COMPLETE", "PARTIAL", "INSUFFICIENT"}:
            raise ValueError(
                f"Invalid production retrieval.status: {retrieval_status}"
            )
        
        # Follow-up context
        actual_followup = final_res.get("followup_context", {}).get("applied", False)
        actual_dominant = ambig_res.dominant_match.value if ambig_res and ambig_res.dominant_match else None
        
        actual_record = {
            "metrics": actual_metrics,
            "dimensions": actual_dimensions,
            "values": actual_values,
            "status": actual_val_status,
            "retrieval_status": retrieval_status,
            "followup_context_applied": actual_followup,
            "dominant_candidate": actual_dominant
        }
        result_record["actual"] = actual_record
        
        # Perform comparison contract assertions
        exp_metrics = normalize_list(expected.get("metrics"))
        act_metrics = normalize_list(actual_metrics)
        
        exp_dims = normalize_list(expected.get("dimensions"))
        act_dims = normalize_list([d.get("business_name") for d in actual_dimensions])
        
        exp_vals = normalize_list(expected.get("values"))
        act_vals = normalize_list(actual_values)
        
        exp_status = expected.get("status")
        act_status = actual_val_status
        
        exp_ret_status = expected.get("retrieval_status")
        act_ret_status = retrieval_status
        
        exp_followup = expected.get("followup_context_applied", False)
        act_followup = actual_followup
        
        failure_codes = []
        failure_details = {}
        
        # 1. Metrics Comparison
        if act_metrics != exp_metrics:
            failure_codes.append("wrong metric")
            failure_details["metrics"] = {
                "expected": exp_metrics,
                "actual": act_metrics
            }
            
        # 2. Dimensions Comparison
        if act_dims != exp_dims:
            failure_codes.append("wrong dimension")
            failure_details["dimensions"] = {
                "expected": exp_dims,
                "actual": act_dims
            }
            
        # 3. Values Comparison
        if act_vals != exp_vals:
            failure_codes.append("wrong value")
            failure_details["values"] = {
                "expected": exp_vals,
                "actual": act_vals
            }
            
        # 4. Status Comparison (Only checked for cases with expected values or non-SIMPLE_METRIC cases)
        if exp_status is not None and act_status != exp_status:
            if expected.get("values") or case["category"] != "SIMPLE_METRIC":
                failure_codes.append("wrong ambiguity")
                failure_details["status"] = {
                    "expected": exp_status,
                    "actual": act_status
                }
            
        # 5. Retrieval Status Comparison
        if exp_ret_status is not None and act_ret_status != exp_ret_status:
            failure_codes.append("wrong retrieval status")
            failure_details["retrieval_status"] = {
                "expected": exp_ret_status,
                "actual": act_ret_status
            }
            
        # 6. Context Comparison
        if act_followup != exp_followup:
            failure_codes.append("wrong context")
            failure_details["followup_context_applied"] = {
                "expected": exp_followup,
                "actual": act_followup
            }
            
        result_record["failure_codes"] = failure_codes
        result_record["failure_details"] = failure_details
        
        if failure_codes:
            result_record["pass_fail"] = "FAIL"
            result_record["reason"] = f"mismatches detected: {', '.join(failure_codes)}"
        else:
            result_record["pass_fail"] = "PASS"
            
    except Exception as e:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        result_record["duration_ms"] = duration_ms
        result_record["pass_fail"] = "ERROR"
        result_record["failure_codes"] = ["execution error"]
        result_record["failure_details"] = {"error": str(e)}
        result_record["reason"] = str(e)
        
    return result_record

def generate_reports(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes statistical aggregates and outputs results/reports.
    """
    total_cases = len(results)
    evaluated = [r for r in results if r["scored"]]
    future_phase = [r for r in results if r["implementation_status"] == "FUTURE_PHASE"]
    
    passed = len([r for r in evaluated if r["pass_fail"] == "PASS"])
    failed = len([r for r in evaluated if r["pass_fail"] == "FAIL"])
    errors = len([r for r in results if r["pass_fail"] == "ERROR"])
    
    pass_rate = round((passed / len(evaluated)) * 100, 2) if evaluated else 0.0
    
    durations = [r["duration_ms"] for r in evaluated if r["duration_ms"] > 0]
    total_duration = round(sum(durations), 2)
    avg_duration = round(total_duration / len(durations), 2) if durations else 0.0
    
    # Categorized breakdowns
    categories = {}
    sources = {}
    failures = {}
    cases_with_multiple_failures = 0
    
    for r in results:
        cat = r["category"]
        src = r["source"]
        categories.setdefault(cat, {"total": 0, "passed": 0, "failed": 0, "errors": 0})
        sources.setdefault(src, {"total": 0, "passed": 0, "failed": 0, "errors": 0})
        
        # Overall totals
        categories[cat]["total"] += 1
        sources[src]["total"] += 1
        
        if r["scored"]:
            pf = r["pass_fail"]
            if pf == "PASS":
                categories[cat]["passed"] += 1
                sources[src]["passed"] += 1
            elif pf == "FAIL":
                categories[cat]["failed"] += 1
                sources[src]["failed"] += 1
                codes = r.get("failure_codes", [])
                if not codes:
                    codes = ["UNKNOWN"]
                for fc in codes:
                    failures[fc] = failures.get(fc, 0) + 1
                if len(codes) > 1:
                    cases_with_multiple_failures += 1
            elif pf == "ERROR":
                categories[cat]["errors"] += 1
                sources[src]["errors"] += 1
                codes = r.get("failure_codes", ["execution error"])
                for fc in codes:
                    failures[fc] = failures.get(fc, 0) + 1
                
    summary = {
        "total_cases": total_cases,
        "evaluated_cases": len(evaluated),
        "future_phase_cases": len(future_phase),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate": pass_rate,
        "failure_breakdown": failures,
        "cases_with_multiple_failures": cases_with_multiple_failures,
        "category_breakdown": categories,
        "source_breakdown": sources,
        "average_duration_ms": avg_duration,
        "total_duration_ms": total_duration
    }
    
    # Create output directory
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "results"))
    os.makedirs(out_dir, exist_ok=True)
    
    # Write machine-readable files
    with open(os.path.join(out_dir, "retrieval_benchmark_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
        
    with open(os.path.join(out_dir, "retrieval_benchmark_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    # Write markdown report
    markdown_path = os.path.join(out_dir, "retrieval_benchmark_report.md")
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write("# Phase 1E Golden Retrieval Benchmark Report\n\n")
        f.write("## 1. Performance Executive Summary\n\n")
        f.write(f"- **Total Cases Merged**: {total_cases}\n")
        f.write(f"- **Evaluated (Currently Implemented)**: {len(evaluated)}\n")
        f.write(f"- **Excluded (Future Roadmap)**: {len(future_phase)}\n")
        f.write(f"- **Passed Cases**: {passed}\n")
        f.write(f"- **Failed Cases**: {failed}\n")
        f.write(f"- **Cases with Multiple Mismatches**: {cases_with_multiple_failures}\n")
        f.write(f"- **Execution Errors**: {errors}\n")
        f.write(f"- **Retrieval Pass Rate**: **{pass_rate}%**\n")
        f.write(f"- **Average Resolving Time**: {avg_duration} ms\n")
        f.write(f"- **Total Resolving Time**: {total_duration} ms\n\n")
        
        f.write("## 2. Category Accuracy Grid\n\n")
        f.write("| Category | Total Cases | Evaluated | Passed | Failed | Errors | Pass Rate |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for cat, stat in sorted(categories.items()):
            tot = stat["total"]
            cat_eval = len([r for r in evaluated if r["category"] == cat])
            c_rate = round((stat["passed"] / cat_eval) * 100, 2) if cat_eval else 0.0
            f.write(f"| {cat} | {tot} | {cat_eval} | {stat['passed']} | {stat['failed']} | {stat['errors']} | {c_rate}% |\n")
            
        f.write("\n## 3. Source-Tier Accuracy Breakdown\n\n")
        f.write("| Source Tier | Total | Evaluated | Passed | Failed | Errors | Pass Rate |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for src, stat in sorted(sources.items()):
            src_eval = len([r for r in evaluated if r["source"] == src])
            s_rate = round((stat["passed"] / src_eval) * 100, 2) if src_eval else 0.0
            f.write(f"| {src} | {stat['total']} | {src_eval} | {stat['passed']} | {stat['failed']} | {stat['errors']} | {s_rate}% |\n")
            
        f.write("\n## 4. Failure Taxonomy & Breakdown\n\n")
        if failures:
            f.write("| Failure Code | Count | Description |\n")
            f.write("| :--- | :---: | :--- |\n")
            for fc, cnt in sorted(failures.items()):
                f.write(f"| {fc} | {cnt} | Mismatch or exception in benchmark run |\n")
        else:
            f.write("*Zero failures detected. All evaluated cases passed perfectly!*\n")
            
        f.write("\n## 5. Representative Mismatches / Failed Cases\n\n")
        failed_cases = [r for r in evaluated if r["pass_fail"] == "FAIL"]
        if failed_cases:
            for idx, fc in enumerate(failed_cases[:10]):
                f.write(f"### {idx+1}. Case {fc['case_id']} ({fc['category']})\n")
                f.write(f"- **Question**: \"{fc['question']}\"\n")
                f.write(f"- **Failure Codes**: `{json.dumps(fc['failure_codes'])}`\n")
                f.write(f"- **Failure Details**: {json.dumps(fc['failure_details'])}\n")
                f.write(f"- **Expected**: {json.dumps(fc['expected'])}\n")
                f.write(f"- **Actual**: {json.dumps(fc['actual'])}\n\n")
        else:
            f.write("*No failed cases to display.*\n")
            
    print(f"Benchmark reports compiled successfully under: {out_dir}")
    return summary

def main():
    parser = argparse.ArgumentParser(description="Phase 1E Golden Retrieval Benchmark Runner")
    parser.add_argument("--smoke", action="store_true", help="Run only the smoke test suite (6 cases)")
    parser.add_argument("--all", action="store_true", help="Run all 194 cases in the dataset")
    parser.add_argument("--category", type=str, help="Filter cases by category name")
    args = parser.parse_args()
    
    # Force smoke test if no option selected for safety first
    is_smoke = args.smoke or (not args.all and not args.category)
    
    print("======================================================================")
    print("       Retail AI Analytics Platform — Golden Retrieval Benchmark      ")
    print("======================================================================")
    
    # 1. Load and validate cases
    cases = validate_and_load_cases()
    print(f"Successfully loaded and validated {len(cases)} cases.")
    
    # 2. Resolve database connection
    connection_id = resolve_logical_connection()
    
    # 3. Filter cases
    run_cases = []
    for case in cases:
        if is_smoke:
            if case["case_id"] in SMOKE_CASE_IDS:
                run_cases.append(case)
        elif args.category:
            if case["category"].lower() == args.category.lower():
                run_cases.append(case)
        else:
            run_cases.append(case)
            
    print(f"Running {len(run_cases)} selected cases (Smoke mode: {is_smoke})")
    
    # 4. Execute cases
    results = []
    for case in run_cases:
        print(f" -> Executing {case['case_id']}: {case['question']} ({case['expected'].get('implementation_status', 'CURRENTLY_IMPLEMENTED')})")
        res = evaluate_case(case, connection_id)
        results.append(res)
        if res["scored"]:
            print(f"    Result: {res['pass_fail']} (Duration: {res['duration_ms']} ms)")
        else:
            print(f"    Result: {res['pass_fail']} ({res['reason']})")
            
    # 5. Generate reports
    summary = generate_reports(results)
    
    # Print console summary
    print("\n========================= EXECUTION SUMMARY =========================")
    print(f"Total Cases Checked   : {summary['total_cases']}")
    print(f"Evaluated (Scored)    : {summary['evaluated_cases']}")
    print(f"Future Phase (Skipped): {summary['future_phase_cases']}")
    print(f"Passed                : {summary['passed']}")
    print(f"Failed                : {summary['failed']}")
    print(f"Errors                : {summary['errors']}")
    print(f"Pass Rate             : {summary['pass_rate']}%")
    print(f"Avg Duration          : {summary['average_duration_ms']} ms")
    print("======================================================================")
    
    # Return exit code based on failures
    if summary["failed"] > 0 or summary["errors"] > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
