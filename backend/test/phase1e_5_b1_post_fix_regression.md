# Phase 1E.5.B.1 — Post-Fix Semantic Regression Checkpoint Report

## 1. Production Diff Summary
Confirming the changes in `backend/semantic/semantic_resolver.py`:
- **`_get_match_info()` specificity ordering**: Rather than returning early on the first matching rule, `_get_match_info()` now evaluates and collects all match types. All matches are sorted by matched string length descending (prioritizing longer multi-word phrases over shorter sub-phrases) and tie-broken by rule score descending.
- **`_remove_overlaps()` ranking/overlap ordering**: Indentation errors in the function header and signature were fixed. The sorting key was updated to prioritize base scores (integer part of score) and metrics over dimensions when base scores are tied, preventing table-boosted dimensions from discarding the metrics that boosted them.

## 2. Database Metadata Change
- **Target Table**: `semantic_metrics`
- **Target Connection**: `Chatbot` (`F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`)
- **Metric Name**: `due`
- **Synonyms Before Fix**: `'Due, Due Day After Order Given'`
- **Synonyms After Fix**: `'due amount, Due, Due Day After Order Given'`
- **DML SQL Executed**:
  ```sql
  UPDATE semantic_metrics
  SET synonyms = 'due amount, Due, Due Day After Order Given'
  WHERE connection_id = 'F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5' AND metric_name = 'due';
  ```
- **Server Database Update Required**: **YES** (The above DML statement must be executed on the production database server environment before release).

## 3. Due/Amount/Pending/Bill Verification
Targeted queries resolve uniquely and correctly:
- `"Show due"` -> `['due']` (**PASS**)
- `"Show due amount"` -> `['due']` (**PASS**)
- `"Total due amount"` -> `['due']` (**PASS**)
- `"Show amount"` -> `['Amt']` (**PASS**)
- `"Total amount"` -> `['Amt']` (**PASS**)
- `"Show bill amount"` -> `['billamt']` (**PASS**)
- `"Total bill amount"` -> `['billamt']` (**PASS**)
- `"Show pending amount"` -> `['pendamt']` (**PASS**)
- `"Total pending amount"` -> `['pendamt']` (**PASS**)

## 4. Sales Verification
Sales queries resolve correctly and regressions are clean:
- `"Show sales"` -> `['C Y']` (**PASS**)
- `"Show sales for Chennai"` -> `['C Y']` (**PASS**)
- `"Show sales for Chennai city"` -> `['C Y']`, `['City']` (**PASS**)
- `"Current year sales"` -> `['C Y']` (**PASS**)
- `"This year sales"` -> `['C Y']` (**PASS**)

## 5. Quantity Verification
Quantity queries resolve correctly to `Qty`:
- `"Show quantity"` -> `['Qty']` (**PASS**)
- `"Total quantity"` -> `['Qty']` (**PASS**)

## 6. Existing Semantic Regression Suites
All 12 existing semantic unit test suites were executed using `pytest` and passed successfully:
- `test_phase1d_2_b_ambiguity.py` -> **PASS**
- `test_phase1d_2_e_clarification.py` -> **PASS**
- `test_phase1d_2_g_clarification_hardening.py` -> **PASS**
- `test_phase1d_5_b1_explicit_dimension_context.py` -> **PASS**
- `test_phase1d_5_b2_followup_dimension_context.py` -> **PASS**
- `test_phase1d_5_b3_metric_guard_refinement.py` -> **PASS**
- `test_phase1d_5_c_integration_gaps.py` -> **PASS**
- `test_phase1d_6_c_partial_coverage_safety.py` -> **PASS**
- `test_phase1d_6_a_thread_safety.py` -> **PASS**
- `test_phase1d_6_d3_selection_matching.py` -> **PASS**
- `test_phase1d_6_d4_resume_security.py` -> **PASS**
- `test_dimension_value_resolver.py` -> **PASS**

## 7. Temporal Regression
- `test_temporal_resolver_regression.py` -> **PASS**

## 8. Benchmark Smoke Comparison
The benchmark smoke test (`run_retrieval_benchmark.py --smoke`) was run:
- **Baseline Smoke Results**: 3 passed, 2 failed (60% pass rate).
- **Post-Fix Smoke Results**: 3 passed, 2 failed (60% pass rate).
- **Analysis**: No regressions were introduced. E1-190 `"Show sales this year"` successfully resolves the metric `C Y` and dimension `createddate Year` now (an improvement over baseline failure), and E1-154 follow-up metric inheritance expectations match baseline behavior.

## 9. New Regressions
- **New Regressions Found**: **NONE**

## 10. Conclusion
All regression checkpoint checks are **CLEAR**. No new regressions have been detected, and the semantic resolver successfully disambiguates `"due amount"` to the single metric `due` while preserving all other metric resolutions.
