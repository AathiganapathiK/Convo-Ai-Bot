# Phase 1E.3.B.3-A — Benchmark Result Contract Finalization Report

## 1. Why One Status Was Insufficient
Previously, the benchmark runner conflated value-level ambiguity status (`status`) with overall query resolution success. For metric-only queries (e.g. `"Show Qty"`), metric resolution succeeds, but because no dimension values are present, the value matching engine returns `"NO_MATCH"`. Using this as the overall status resulted in false negatives for successful metric-only queries.

## 2. Status vs. Retrieval Status Definition & Sources

### A. Status (Dimension/Value Ambiguity Status)
*   **Meaning**: Represents the ambiguity classification of resolved dimension values (e.g., whether a value is uniquely matched, weakly ambiguous, or strongly ambiguous).
*   **Production Source**: `ambiguity_result.status.value` (from the production `AmbiguityClassifier`).
*   **Allowed Values**: `NO_MATCH`, `SINGLE_MATCH`, `WEAK_AMBIGUITY`, `STRONG_AMBIGUITY`, `PARTIAL_MATCH`.

### B. Retrieval Status (Overall Semantic Retrieval Status)
*   **Meaning**: Represents the overall status of the semantic context resolution based on which of the three components (metrics, dimensions, values) were successfully parsed.
*   **Production Source**: `semantic_result["retrieval"]["status"]` (from the production `SemanticResolver`).
*   **Allowed Values**: `COMPLETE`, `PARTIAL`, `INSUFFICIENT`.

---

## 3. Query Examples and Contract Isolation

### A. Metric-Only Example
Query: `"Show Qty"`
*   **Expected**: `metrics = ["Qty"]`, `status = "NO_MATCH"`, `retrieval_status = "PARTIAL"` (since only the metric resolves).
*   **Behavior**: Evaluated independently. The query passes because the metric resolved successfully and `retrieval_status` matches `"PARTIAL"`, bypassing status mismatch failures.

### B. Ambiguity Example
Query: `"Show sales for Chennai"`
*   **Expected**: `metrics = ["Sales"]`, `status = "STRONG_AMBIGUITY"`, `retrieval_status = "COMPLETE"` (since both metric and ambiguous value resolve).
*   **Behavior**: Verified that the value resolves as strongly ambiguous.

### C. Follow-up Example
Query: `"for coimbatore"` (Turn 2)
*   **Expected**: `metrics = ["Sales"]`, `status = "SINGLE_MATCH"`, `retrieval_status = "COMPLETE"`, `followup_context_applied = true`.
*   **Behavior**: Because the term `"city"` is absent from Turn 2, `actual.dimensions` remains empty (`[]`), whereas Turn 1 context is inherited. The runner correctly isolates explicitly resolved dimensions from inherited values.

---

## 4. Temporal Handling
*   **Currently Implemented**: Temporal expressions (e.g. `"this year"`) are evaluated against active semantic resolver outputs.
*   **Future Phase**: Expressions like `"same period last year"` bypass current semantic scoring by setting `status = null` and `retrieval_status = null` in the golden dataset.

---

## 5. Changes Made to Benchmark Tooling
1.  **Schema Extension**: Updated `golden_case_schema.json` to make `retrieval_status` required under `expected` and updated field descriptions.
2.  **Validator Strictness**: Modified `validate_golden_schema.py` to enforce that `retrieval_status` is required, belongs to `COMPLETE/PARTIAL/INSUFFICIENT`, and that `status` is null only under `FUTURE_PHASE` cases.
3.  **Runner Accuracy**: Rewrote `evaluate_case` in `run_retrieval_benchmark.py` to capture actual `status` and `retrieval_status` separately, and implemented lowercase failure codes (`wrong metric`, `wrong dimension`, `wrong value`, `wrong ambiguity`, `wrong retrieval status`, `wrong context`).
4.  **Golden Datasets**: Populated all 194 golden cases with expected `retrieval_status` fields derived from the production resolver rules.

---

## 6. Retrieval Status Fallback Safety Fix
Previously, if the `retrieval` key was missing or its value was unspecified in `SemanticResolver` responses, the runner silently fell back to `"NO_MATCH"`. However, `"NO_MATCH"` is not a valid production retrieval status; the valid production states are strictly restricted to `COMPLETE`, `PARTIAL`, and `INSUFFICIENT`.
To prevent silent fallback corruption, the extraction logic has been hardened to raise a `ValueError` if:
- the `retrieval` block is missing or does not contain `status`.
- the retrieved `retrieval_status` value is not one of `{"COMPLETE", "PARTIAL", "INSUFFICIENT"}`.

This guarantees that benchmark scoring fails fast upon encountering any invalid or non-standard resolver outputs.

---

## 7. Audit Declarations
*   **Production Code Changed**: **NO** (Production code remains untouched)
*   **Database Changed**: **NO** (Database schema and records remain untouched)

---
## Final Verdict
**PASS — RETRIEVAL STATUS CONTRACT FINALIZED**
