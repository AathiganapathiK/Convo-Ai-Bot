# Phase 1E.5.A — Production Metadata Fix Audit Report: Sales → C Y

## 1. Problem
During the Phase 1E.4.A retrieval benchmark, an inconsistency was identified where general sales queries (e.g., "Show sales") failed to resolve to the `C Y` (Current Year Sales) metric. The business requirement dictates that `"Sales"` is a valid standalone alias for the `C Y` metric. Prior to this fix, the standalone term `"Sales"` was absent from the database synonyms for the `C Y` metric.

## 2. Original C Y Synonyms
- **Connection**: `Chatbot` (Connection ID: `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`)
- **Metric Name**: `cy`
- **Business Name**: `C Y`
- **Table Name**: `QB_MDJMD_SALES_5YRS_SUMMARY`
- **Column Name**: `CY`
- **Original Synonym Value**: `'Current year sales, This year sales,2026\n'` (the standalone `"Sales"` was absent)

## 3. Updated C Y Synonyms
- **Updated Synonym Value**: `'Sales, Current year sales, This year sales,2026'`
- **Note on Synonym Ordering**: To resolve a subtle overlap issue where the dimension `createddate Year` (matching on the synonym `"year"`) would conflict with the longer metric synonyms `"Current year sales"` or `"This year sales"`, the standalone synonym `"Sales"` was placed **first** in the comma-separated list. This forces the deterministic resolver to match on `"Sales"` (span: `[(13, 18)]`) first rather than the full phrase (span: `[(0, 18)]`), preventing overlap conflicts with `"year"` (span: `[(8, 12)]`) and allowing both elements to resolve successfully.

## 4. Exact Database Change
- **Type**: DML Metadata Update (DML update to metadata table, no schema DDL change)
- **Target Table**: `semantic_metrics`
- **Target Connection**: `Chatbot` (`F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`)
- **SQL Executed**:
  ```sql
  UPDATE semantic_metrics
  SET synonyms = 'Sales, Current year sales, This year sales,2026'
  WHERE connection_id = 'F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5' AND metric_name = 'cy';
  ```
- **Rows Affected**: Exactly `1` row updated.

## 5. Verification Queries/Results
The semantic resolver was evaluated against the five targeted verification queries:
1. **Show sales**
   - **Resolved Metrics**: `['C Y']`
   - **Resolved Dimensions**: `[]`
   - **Status**: **PASS**
2. **Show sales for Chennai**
   - **Resolved Metrics**: `['C Y']`
   - **Resolved Dimensions**: `[]`
   - **Status**: **PASS**
3. **Show sales for Chennai city**
   - **Resolved Metrics**: `['C Y']`
   - **Resolved Dimensions**: `['City']`
   - **Status**: **PASS**
4. **Current year sales**
   - **Resolved Metrics**: `['C Y']`
   - **Resolved Dimensions**: `['createddate Year']`
   - **Status**: **PASS**
5. **This year sales**
   - **Resolved Metrics**: `['C Y']`
   - **Resolved Dimensions**: `['createddate Year']`
   - **Status**: **PASS**

## 6. Regression Checks
Unrelated metrics were verified to ensure they were not impacted by the change:
1. **Show quantity** -> Resolves to `['Qty']` (**PASS**)
2. **Show amount** -> Resolves to `['Amt']` (**PASS**)
3. **Show pending amount** -> Resolves to `['pendamt']` (**PASS**)
4. **Show bill amount** -> Resolves to `['billamt']` (**PASS**)
5. **Show due** -> Resolves to `['due']` (**PASS**)

## 7. Production-Code Changes
- **Production Code Changed**: **NO**

## 8. Database Changes
- **Database Changed**: **YES** (DML metadata row update)

## 9. Server Deployment Requirement
- **Local Database**: **UPDATED**
- **Server Database**: **REQUIRED BEFORE PRODUCTION DEPLOYMENT** (The DML update must be run against the production database server environment before releasing).
