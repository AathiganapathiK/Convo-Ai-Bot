# Phase 1E.4.A — Corrected Benchmark Re-baseline Report

## 1. Previous Baseline
- **Total Cases**: 194
- **Evaluated (Scored)**: 190
- **Passed**: 1
- **Failed**: 189
- **Errors**: 0
- **Pass Rate**: **0.53%**

## 2. Corrected Baseline
- **Total Cases**: 194
- **Evaluated (Scored)**: 190
- **Future Phase (Skipped)**: 4
- **Passed**: 31
- **Failed**: 159
- **Errors**: 0
- **Pass Rate**: **16.32%**
- **Average Duration**: 1128.85 ms
- **Total Duration**: 214,480.63 ms

## 3. Improvement
- **Absolute Improvement**: **+15.79%** (from 0.53% to 16.32%)
- **Relative Improvement**: **2979.25%** (a 31-fold increase in passing cases)
- **Note**: This improvement is achieved solely by correcting benchmark expectations and schema contract mappings to match verified production metadata. The production semantic resolver code and database contents were completely unchanged.

## 4. Overall Score
- **Total Scored**: 190
- **Passed**: 31
- **Failed**: 159
- **Pass Rate**: **16.32%**

## 5. Category Scorecard
| Category | Total Cases | Evaluated | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `AMBIGUOUS_VALUES` | 18 | 18 | 6 | 12 | 0 | 33.33% |
| `ENTITY_TOPIC_SHIFT` | 8 | 8 | 0 | 8 | 0 | 0.00% |
| `EXPLICIT_DIMENSION` | 18 | 18 | 2 | 16 | 0 | 11.11% |
| `FOLLOW_UP` | 10 | 10 | 0 | 10 | 0 | 0.00% |
| `METRIC_DIMENSION_VALUE` | 22 | 22 | 3 | 19 | 0 | 13.64% |
| `METRIC_SHIFT` | 8 | 8 | 1 | 7 | 0 | 12.50% |
| `MULTI_DIMENSION` | 18 | 18 | 0 | 18 | 0 | 0.00% |
| `NO_MATCH_ADVERSARIAL` | 10 | 10 | 7 | 3 | 0 | 70.00% |
| `PARTIAL_COVERAGE` | 18 | 18 | 4 | 14 | 0 | 22.22% |
| `SIMPLE_METRIC` | 18 | 18 | 8 | 10 | 0 | 44.44% |
| `SINGULAR_PLURAL` | 18 | 18 | 0 | 18 | 0 | 0.00% |
| `TEMPORAL_QUESTIONS` | 10 | 6 | 0 | 6 | 0 | 0.00% |
| `TYPO_FUZZY` | 18 | 18 | 0 | 18 | 0 | 0.00% |


## 6. Source-tier Scorecard
| Source Tier | Total | Evaluated | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `REAL_BUSINESS` | 139 | 139 | 19 | 120 | 0 | 13.67% |
| `REGRESSION` | 15 | 15 | 3 | 12 | 0 | 20.00% |
| `SYNTHETIC_SAFETY` | 40 | 36 | 9 | 27 | 0 | 25.00% |


## 7. Failure Taxonomy
| Failure Code | Occurrences | Description |
| :--- | :---: | :--- |
| `wrong metric` | 128 | Mismatch in resolved metric list |
| `wrong ambiguity` | 105 | Mismatch in value ambiguity classifier status |
| `wrong value` | 41 | Mismatch in resolved filter values |
| `wrong retrieval status` | 35 | Mismatch in overall retrieval status |
| `wrong dimension` | 6 | Mismatch in resolved dimension list |
| `execution error` | 0 | Unhandled exceptions or crashes |


## 8. Top Recurring Failures
1. **Sales Synonym Gap**: The word `'sales'` (present in 128 cases) is not defined as a standalone synonym for the `cy` metric in the database. As a result, the production resolver returns empty metrics `[]` instead of `['C Y']` for general sales queries.
2. **Derivative Ambiguity Mismatches**: When the metric fails to resolve, downstream status predictions (like metric+value ambiguity vs value-only ambiguity) mismatch, leading to 105 `wrong ambiguity` failures.
3. **Bill Amount Correction Gap**: The automated correction script mapped `'bill amount'` to `['Amt']` instead of the more specific production metric `['billamt']` (e.g. E1-015, E1-016), causing false metric mismatches.
4. **Due Amount Double Match**: Wording like `'due amount'` (E1-017) resolves to both `due` and `Amt` because both terms match, but the benchmark expected only `due`.

## 9. Generic Sales / C Y Verification
The database synonyms for `cy` are `'Current year sales, This year sales,2026, Current Year\n'`. Standalone `'Sales'` is not present as a synonym. Therefore:
- Query `'Show sales'` -> actual: `[]` (expected: `['C Y']`).
- Query `'Show sales for Chennai'` -> actual: `[]` (expected: `['C Y']`).
- Query `'Current year sales'` -> actual: `['C Y']` (expected: `['C Y']`).
- Query `'This year sales'` -> actual: `['C Y']` (expected: `['C Y']`).
This confirms an inconsistency where the benchmark expects `'Sales'` to be an alias of `C Y`, but the production metadata lacks the standalone synonym.

## 10. Case E1-154 Analysis
- **Question**: `'for coimbatore'` (follow-up after `'Show sales for Chennai city'`)
- **Expected**: `metrics = ['Sales']`, `status = 'STRONG_AMBIGUITY'`, `followup_context_applied = True`, `retrieval_status = 'COMPLETE'`
- **Actual**: `metrics = []`, `status = 'SINGLE_MATCH'`, `followup_context_applied = True`, `retrieval_status = 'PARTIAL'`
- **Diagnosis**: The resolver successfully inherited the `City` dimension context from Turn 1. Since Coimbatore is a duplicate in the database (matching both City and District), applying the inherited City context filtered out the District candidate, resulting in a single clean candidate (`SINGLE_MATCH`). This indicates context dimension filtering is operating correctly. The expected status of `STRONG_AMBIGUITY` is a mock-era benchmark definition defect that should be corrected to `SINGLE_MATCH` once the sales synonym is added.

## 11. Case E1-190 Analysis
- **Question**: `'Show sales this year'`
- **Expected**: `metrics = ['C Y']`, `dimensions = ['createddate Year']`
- **Actual**: `metrics = []`, `dimensions = ['docdate Year']`
- **Diagnosis**: Because `'sales'` failed to resolve to `C Y`, the resolver lacked the table context of `QB_MDJMD_SALES_5YRS_SUMMARY` to boost its `createddate_year` dimension. Falling back to default scoring across all tables, it selected the outstanding table's `docdate_year` dimension. Once the sales synonym is added to resolve `'sales'` to `cy`, the table context bonus will naturally elevate `createddate_year` to match expectations, showing that the temporal engine does not have an independent selection defect here.

## 12. Database Audit
- **Database Mutations**: **0**
- **Verify**: No SQL mutations (INSERT/UPDATE/DELETE/CREATE/ALTER) were performed. The database remains in its read-only baseline state.

## 13. Production-code Audit
- **Production Code Changes**: **0**
- **Verify**: No changes were made to semantic resolver, rankers, or temporal code.

## 14. Recommended Next Step
Proceed to **Phase 1E.5 — Verified Production Retrieval Defect Fixes**. This will include adding the missing `'Sales'` synonym to `cy` in the database, fixing the minor benchmark definition bugs (like E1-154 ambiguity and E1-015 billamt mappings), and running the final re-baseline validation.
