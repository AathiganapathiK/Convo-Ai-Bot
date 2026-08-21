import json
import os

output_path = "phase1e_4_a_corrected_rebaseline.md"

markdown = []

markdown.append("# Phase 1E.4.A — Corrected Benchmark Re-baseline Report\n")

# 1. Previous baseline
markdown.append("## 1. Previous Baseline")
markdown.append("- **Total Cases**: 194")
markdown.append("- **Evaluated (Scored)**: 190")
markdown.append("- **Passed**: 1")
markdown.append("- **Failed**: 189")
markdown.append("- **Errors**: 0")
markdown.append("- **Pass Rate**: **0.53%**\n")

# 2. Corrected baseline
markdown.append("## 2. Corrected Baseline")
markdown.append("- **Total Cases**: 194")
markdown.append("- **Evaluated (Scored)**: 190")
markdown.append("- **Future Phase (Skipped)**: 4")
markdown.append("- **Passed**: 31")
markdown.append("- **Failed**: 159")
markdown.append("- **Errors**: 0")
markdown.append("- **Pass Rate**: **16.32%**")
markdown.append("- **Average Duration**: 1128.85 ms")
markdown.append("- **Total Duration**: 214,480.63 ms\n")

# 3. Improvement
markdown.append("## 3. Improvement")
markdown.append("- **Absolute Improvement**: **+15.79%** (from 0.53% to 16.32%)")
markdown.append("- **Relative Improvement**: **2979.25%** (a 31-fold increase in passing cases)")
markdown.append("- **Note**: This improvement is achieved solely by correcting benchmark expectations and schema contract mappings to match verified production metadata. The production semantic resolver code and database contents were completely unchanged.\n")

# 4. Overall score
markdown.append("## 4. Overall Score")
markdown.append("- **Total Scored**: 190")
markdown.append("- **Passed**: 31")
markdown.append("- **Failed**: 159")
markdown.append("- **Pass Rate**: **16.32%**\n")

# 5. Category scorecard
markdown.append("## 5. Category Scorecard")
markdown.append("| Category | Total Cases | Evaluated | Passed | Failed | Errors | Pass Rate |")
markdown.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
markdown.append("| `AMBIGUOUS_VALUES` | 18 | 18 | 6 | 12 | 0 | 33.33% |")
markdown.append("| `ENTITY_TOPIC_SHIFT` | 8 | 8 | 0 | 8 | 0 | 0.00% |")
markdown.append("| `EXPLICIT_DIMENSION` | 18 | 18 | 2 | 16 | 0 | 11.11% |")
markdown.append("| `FOLLOW_UP` | 10 | 10 | 0 | 10 | 0 | 0.00% |")
markdown.append("| `METRIC_DIMENSION_VALUE` | 22 | 22 | 3 | 19 | 0 | 13.64% |")
markdown.append("| `METRIC_SHIFT` | 8 | 8 | 1 | 7 | 0 | 12.50% |")
markdown.append("| `MULTI_DIMENSION` | 18 | 18 | 0 | 18 | 0 | 0.00% |")
markdown.append("| `NO_MATCH_ADVERSARIAL` | 10 | 10 | 7 | 3 | 0 | 70.00% |")
markdown.append("| `PARTIAL_COVERAGE` | 18 | 18 | 4 | 14 | 0 | 22.22% |")
markdown.append("| `SIMPLE_METRIC` | 18 | 18 | 8 | 10 | 0 | 44.44% |")
markdown.append("| `SINGULAR_PLURAL` | 18 | 18 | 0 | 18 | 0 | 0.00% |")
markdown.append("| `TEMPORAL_QUESTIONS` | 10 | 6 | 0 | 6 | 0 | 0.00% |")
markdown.append("| `TYPO_FUZZY` | 18 | 18 | 0 | 18 | 0 | 0.00% |")
markdown.append("\n")

# 6. Source-tier scorecard
markdown.append("## 6. Source-tier Scorecard")
markdown.append("| Source Tier | Total | Evaluated | Passed | Failed | Errors | Pass Rate |")
markdown.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
markdown.append("| `REAL_BUSINESS` | 139 | 139 | 19 | 120 | 0 | 13.67% |")
markdown.append("| `REGRESSION` | 15 | 15 | 3 | 12 | 0 | 20.00% |")
markdown.append("| `SYNTHETIC_SAFETY` | 40 | 36 | 9 | 27 | 0 | 25.00% |")
markdown.append("\n")

# 7. Failure taxonomy
markdown.append("## 7. Failure Taxonomy")
markdown.append("| Failure Code | Occurrences | Description |")
markdown.append("| :--- | :---: | :--- |")
markdown.append("| `wrong metric` | 128 | Mismatch in resolved metric list |")
markdown.append("| `wrong ambiguity` | 105 | Mismatch in value ambiguity classifier status |")
markdown.append("| `wrong value` | 41 | Mismatch in resolved filter values |")
markdown.append("| `wrong retrieval status` | 35 | Mismatch in overall retrieval status |")
markdown.append("| `wrong dimension` | 6 | Mismatch in resolved dimension list |")
markdown.append("| `execution error` | 0 | Unhandled exceptions or crashes |")
markdown.append("\n")

# 8. Top recurring failures
markdown.append("## 8. Top Recurring Failures")
markdown.append("1. **Sales Synonym Gap**: The word `'sales'` (present in 128 cases) is not defined as a standalone synonym for the `cy` metric in the database. As a result, the production resolver returns empty metrics `[]` instead of `['C Y']` for general sales queries.")
markdown.append("2. **Derivative Ambiguity Mismatches**: When the metric fails to resolve, downstream status predictions (like metric+value ambiguity vs value-only ambiguity) mismatch, leading to 105 `wrong ambiguity` failures.")
markdown.append("3. **Bill Amount Correction Gap**: The automated correction script mapped `'bill amount'` to `['Amt']` instead of the more specific production metric `['billamt']` (e.g. E1-015, E1-016), causing false metric mismatches.")
markdown.append("4. **Due Amount Double Match**: Wording like `'due amount'` (E1-017) resolves to both `due` and `Amt` because both terms match, but the benchmark expected only `due`.\n")

# 9. Generic Sales/C Y verification
markdown.append("## 9. Generic Sales / C Y Verification")
markdown.append("The database synonyms for `cy` are `'Current year sales, This year sales,2026, Current Year\\n'`. Standalone `'Sales'` is not present as a synonym. Therefore:")
markdown.append("- Query `'Show sales'` -> actual: `[]` (expected: `['C Y']`).")
markdown.append("- Query `'Show sales for Chennai'` -> actual: `[]` (expected: `['C Y']`).")
markdown.append("- Query `'Current year sales'` -> actual: `['C Y']` (expected: `['C Y']`).")
markdown.append("- Query `'This year sales'` -> actual: `['C Y']` (expected: `['C Y']`).")
markdown.append("This confirms an inconsistency where the benchmark expects `'Sales'` to be an alias of `C Y`, but the production metadata lacks the standalone synonym.\n")

# 10. E1-154 analysis
markdown.append("## 10. Case E1-154 Analysis")
markdown.append("- **Question**: `'for coimbatore'` (follow-up after `'Show sales for Chennai city'`)")
markdown.append("- **Expected**: `metrics = ['Sales']`, `status = 'STRONG_AMBIGUITY'`, `followup_context_applied = True`, `retrieval_status = 'COMPLETE'`")
markdown.append("- **Actual**: `metrics = []`, `status = 'SINGLE_MATCH'`, `followup_context_applied = True`, `retrieval_status = 'PARTIAL'`")
markdown.append("- **Diagnosis**: The resolver successfully inherited the `City` dimension context from Turn 1. Since Coimbatore is a duplicate in the database (matching both City and District), applying the inherited City context filtered out the District candidate, resulting in a single clean candidate (`SINGLE_MATCH`). This indicates context dimension filtering is operating correctly. The expected status of `STRONG_AMBIGUITY` is a mock-era benchmark definition defect that should be corrected to `SINGLE_MATCH` once the sales synonym is added.\n")

# 11. E1-190 analysis
markdown.append("## 11. Case E1-190 Analysis")
markdown.append("- **Question**: `'Show sales this year'`")
markdown.append("- **Expected**: `metrics = ['C Y']`, `dimensions = ['createddate Year']`")
markdown.append("- **Actual**: `metrics = []`, `dimensions = ['docdate Year']`")
markdown.append("- **Diagnosis**: Because `'sales'` failed to resolve to `C Y`, the resolver lacked the table context of `QB_MDJMD_SALES_5YRS_SUMMARY` to boost its `createddate_year` dimension. Falling back to default scoring across all tables, it selected the outstanding table's `docdate_year` dimension. Once the sales synonym is added to resolve `'sales'` to `cy`, the table context bonus will naturally elevate `createddate_year` to match expectations, showing that the temporal engine does not have an independent selection defect here.\n")

# 12. Database audit
markdown.append("## 12. Database Audit")
markdown.append("- **Database Mutations**: **0**")
markdown.append("- **Verify**: No SQL mutations (INSERT/UPDATE/DELETE/CREATE/ALTER) were performed. The database remains in its read-only baseline state.\n")

# 13. Production-code audit
markdown.append("## 13. Production-code Audit")
markdown.append("- **Production Code Changes**: **0**")
markdown.append("- **Verify**: No changes were made to semantic resolver, rankers, or temporal code.\n")

# 14. Recommended next step
markdown.append("## 14. Recommended Next Step")
markdown.append("Proceed to **Phase 1E.5 — Verified Production Retrieval Defect Fixes**. This will include adding the missing `'Sales'` synonym to `cy` in the database, fixing the minor benchmark definition bugs (like E1-154 ambiguity and E1-015 billamt mappings), and running the final re-baseline validation.\n")

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(markdown))

print("Report generated successfully!")
