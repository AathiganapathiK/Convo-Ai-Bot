# Phase 1E.3.B.3-B — Multi-Mismatch Benchmark Failure Reporting

## 1. Why First-Failure Reporting Was Insufficient
In previous iterations, the benchmark runner used a sequential `if/elif` block to evaluate semantic mismatches. This approach halted verification at the first mismatch encountered. 
For example, if a query resolved the wrong metric, the runner flagged the case as `wrong metric` and immediately skipped checks for dimensions, values, context, and retrieval status. This hid secondary, independent mismatches (such as a concurrent `wrong retrieval status` or `wrong ambiguity`), obscuring the true state of semantic alignment and preventing comprehensive forensic audits.

## 2. New Multi-Failure Contract
The benchmark runner now evaluates all six semantic components independently:
1.  `metrics`
2.  `dimensions`
3.  `values`
4.  `status` (value ambiguity status)
5.  `retrieval_status` (overall retrieval status)
6.  `followup_context_applied`

Rather than stopping at the first discrepancy, the runner:
*   Collects all mismatches in a `failure_codes` list (which remains empty `[]` for passing cases).
*   Enforces `pass_fail = "PASS"` only if `failure_codes` is empty; otherwise `pass_fail = "FAIL"`.
*   Populates a structured `failure_details` dictionary containing the `expected` and `actual` states of only the components that mismatched.

---

## 3. Example E1-082
*   **Question**: `"Show sales for Chennai"`
*   **Expected**: `metrics = ["Sales"]`, `retrieval_status = "COMPLETE"`
*   **Actual**: `metrics = []`, `retrieval_status = "PARTIAL"`
*   **Result**: 
    *   `failure_codes`: `["wrong metric", "wrong retrieval status"]`
    *   `failure_details`: 
        ```json
        {
          "metrics": {"expected": ["sales"], "actual": []},
          "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}
        }
        ```

---

## 4. Example E1-024
*   **Question**: `"Show sales for Chennai city"`
*   **Expected**: `metrics = ["Sales"]`, `status = "SINGLE_MATCH"`
*   **Actual**: `metrics = []`, `status = "WEAK_AMBIGUITY"`
*   **Result**: 
    *   `failure_codes`: `["wrong metric", "wrong ambiguity"]`
    *   `failure_details`: 
        ```json
        {
          "metrics": {"expected": ["sales"], "actual": []},
          "status": {"expected": "SINGLE_MATCH", "actual": "WEAK_AMBIGUITY"}
        }
        ```

---

## 5. Example E1-154 (Follow-up Turn 2)
*   **Question**: `"for coimbatore"`
*   **Expected**: `metrics = ["Sales"]`, `retrieval_status = "COMPLETE"`
*   **Actual**: `metrics = []`, `retrieval_status = "PARTIAL"`
*   **Result**: 
    *   `failure_codes`: `["wrong metric", "wrong retrieval status"]`
    *   `failure_details`: 
        ```json
        {
          "metrics": {"expected": ["sales"], "actual": []},
          "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}
        }
        ```

---

## 6. Result-File Changes (`retrieval_benchmark_results.json`)
Every case in the machine-readable results contains the following keys:
*   `case_id`, `question`, `category`, `expected`, `actual`, `pass_fail`, `failure_codes`, `failure_details`, `implementation_status`, `scored`, `reason`, `duration_ms`.

---

## 7. Summary-File Changes (`retrieval_benchmark_summary.json`)
The failure breakdowns in the summary report are now aggregated across all failure codes of all failing cases (a single case can contribute to multiple counts). Additionally, a new metric has been added:
*   `cases_with_multiple_failures`: The count of scored cases that returned more than one failure code.

---

## 8. Smoke Verification
Running the smoke suite against the 6 smoke-test cases (`E1-006`, `E1-024`, `E1-082`, `E1-154`, `E1-190`, `E1-196`) successfully verified:
*   **E1-196**: Correctly skipped (`FUTURE_PHASE`).
*   **E1-006**: Returned `["wrong metric", "wrong retrieval status"]`.
*   **E1-024**: Returned `["wrong metric", "wrong ambiguity"]`.
*   **E1-082**: Returned `["wrong metric", "wrong retrieval status"]`.
*   **E1-154**: Returned `["wrong metric", "wrong retrieval status"]`.
*   **E1-190**: Returned `["wrong metric", "wrong dimension", "wrong ambiguity", "wrong retrieval status"]`.

This indicates that multi-failure reporting is fully active and functioning correctly.

---

## 9. Production-Code Audit
The production codebase remains completely untouched. The semantic parsing layers, disambiguation logic, and SQL engine were not altered. The changes are strictly isolated to the test and benchmark tooling.

---

## 10. Database Audit
No writes, updates, or deletes were performed on the database. Active metadata counts (23 metrics, 98 dimensions) were verified as read-only inputs during the benchmark run.

---
## Final Verdict
**PASS — MULTI-MISMATCH REPORTING READY**
