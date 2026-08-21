# Phase 1E.5.B — Due Amount Metric Disambiguation Audit & Fix Report

## 1. Original Behavior
Queries containing `"due amount"` (e.g. `"Show due amount"`, `"Total due amount"`) resolved to two metrics:
- `due` (Due Days/Amount)
- `Amt` (Amount)

This caused a semantic ambiguity block where the system returned multiple metric choices instead of uniquely resolving to the intended single `due` metric.

## 2. Root Cause
1. **Metadata Gap**: Standalone `"due amount"` was absent from the database synonyms for the `due` metric. The original synonyms for `due` were only `'Due, Due Day After Order Given'`.
2. **Business Name Priority Conflict**: The `due` metric has `business_name = 'due'` (a real lowercase English word). During matching for `"Show due amount"`, the word `"due"` matched via **Priority 3: Exact business phrase contained in the question** (Score: 30000) returning a span of `[(5, 8)]` (covering `"due"`).
3. **No Overlap Discarding**: Because `"due"` matched via Business Name phrase (Score 30000, span `[(5, 8)]`), and `"amount"` matched `amt` via Synonym (Score 9000, span `[(9, 15)]`), the two spans did not overlap. Consequently, overlap resolution did not discard `amt`, resulting in both metrics resolving.
4. **Synonym Matching Fallthrough Limitation**: Even when `"due amount"` was added as a synonym for `due`, the resolver's `_get_match_info` function evaluated candidate rules sequentially and returned early on the first match. Since the Business Name phrase match (`"due"`, Score 30000) was checked before the Database Synonym match (`"due amount"`, Score 9000), it returned early with the shorter match, completely ignoring the more specific `"due amount"` synonym!

## 3. Metadata Evidence
Prior to the change, the metadata for `due` and `amt` under connection `Chatbot` (`F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`) was:
- **Metric `amt`**: Business Name: `Amt`, Synonyms: `'Amount'`, Table: `PBI_ENES_ORDER_PENDING_SUMMARY`, Column: `Amt`
- **Metric `due`**: Business Name: `due`, Synonyms: `'Due, Due Day After Order Given'`, Table: `PBI_ENES_ORDER_PENDING_SUMMARY`, Column: `due`

## 4. Fix Selected
We applied a combined two-part fix:
1. **Metadata Synonym Update**: Added `"due amount"` to the database synonyms for the `due` metric. By placing `"due amount"` first, it is evaluated first during synonym matching.
2. **Matcher/Ranking Specificity Correction**: Refactored the `_get_match_info` helper inside `backend/semantic/semantic_resolver.py`. Instead of returning early on the first matching rule, `_get_match_info` now gathers all valid matches, sorts them by matched substring length descending (prioritizing more specific multi-word phrase matches like `"due amount"` over shorter matches like `"due"`), and breaks ties on the rule score. This ensures that the resolver successfully picks up the `"due amount"` synonym match over the `"due"` business name match.

Additionally, to prevent a table-boosted dimension (like `createddate_year` receiving `+0.35` bonus) from sorting before and discarding the very metric (like `cy`) that boosted it, we updated the final overlap removal sorting key in `_remove_overlaps` to sort by:
1. Base score (integer part of score) descending.
2. Type is metric descending (metrics first).
3. Full score descending (tie-breaker for table-boosted dimensions).
4. Matched length descending.

## 5. Exact Changes

### Database Changes
- **Target Table**: `semantic_metrics`
- **Target Connection**: `Chatbot` (`F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`)
- **Before Value**: `'Due, Due Day After Order Given'`
- **After Value**: `'due amount, Due, Due Day After Order Given'`
- **SQL Executed**:
  ```sql
  UPDATE semantic_metrics
  SET synonyms = 'due amount, Due, Due Day After Order Given'
  WHERE connection_id = 'F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5' AND metric_name = 'due';
  ```

### Code Changes
Modified `backend/semantic/semantic_resolver.py`:
- In `_get_match_info`: Revised logic to collect all matches and return the one with the maximum matched substring length, tie-breaking on score.
- In `_remove_overlaps`: Indented the function body and signature correctly, and updated the sort key to prioritize base scores and metrics over table-boosted dimensions.

## 6. Before/After Test Results

| Question | Before Metrics | After Metrics | Status |
| :--- | :--- | :--- | :---: |
| **Show due** | `['due']` | `['due']` | **PASS** |
| **Show due amount** | `['due', 'Amt']` | `['due']` | **PASS** |
| **Total due amount** | `['due', 'Amt']` | `['due']` | **PASS** |
| **Show amount** | `['Amt']` | `['Amt']` | **PASS** |
| **Total amount** | `['Amt']` | `['Amt']` | **PASS** |
| **Show bill amount** | `['billamt']` | `['billamt']` | **PASS** |
| **Total bill amount** | `['billamt']` | `['billamt']` | **PASS** |
| **Show pending amount**| `['pendamt']` | `['pendamt']` | **PASS** |
| **Total pending amount**| `['pendamt']` | `['pendamt']` | **PASS** |

## 7. Regression Checks
All regression checks passed successfully:
- **Sales → C Y**: `"Show sales"`, `"Show sales for Chennai"`, `"Show sales for Chennai city"`, `"Current year sales"`, and `"This year sales"` all correctly resolve to `['C Y']`.
- **Quantity → Qty**: `"Show quantity"` correctly resolves to `['Qty']`.
- **Chennai city behavior**: Duplicate and explicit location matches resolve correctly.

## 8. Database Impact
- **DATABASE CHANGE**: **YES** (DML row update to `semantic_metrics` table synonyms column, no schema changes).

## 9. Server Deployment Requirement
- **SERVER DATABASE UPDATE REQUIRED**: **YES**
- The exact DML update to run on the server's database is:
  ```sql
  UPDATE semantic_metrics
  SET synonyms = 'due amount, Due, Due Day After Order Given'
  WHERE connection_id = 'F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5' AND metric_name = 'due';
  ```

## 10. Production-Code Impact
- **Production Code Changed**: **YES**
- The file [`backend/semantic/semantic_resolver.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/semantic_resolver.py) was modified to implement specificity-based match sorting inside `_get_match_info` and base score prioritization inside `_remove_overlaps`.
