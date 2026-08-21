# Semantic Metric Sales Model Audit Report

## 1. Executive Verdict

An investigation into the database metadata and runtime resolver logic reveals that the conversational chatbot currently utilizes a hybrid/overlapping metric model. 

The physical database representation of sales is pivoted into period-specific columns (`CY`, `PY`, etc.) instead of a single generic column. However, because `"Sales"` is stored directly as a database synonym of the `C Y` (`CY`) metric, queries containing the generic word "sales" (such as `"Show sales"`) resolve to the current year column by default. 

To handle previous year queries, the system relies on a combination of matching separate synonyms (e.g. `"Previous Year Sales"` matching `P Y`) and a hardcoded post-processing override in `SemanticResolver` that programmatically swaps `CY` with `PY` if `PreviousYearIntent` is detected. 

This duplicate routing of temporal logic causes metric collisions (e.g. `"Show PY sales"` resolving to both `P Y` and `C Y`) and prevents a clean separation of business semantics from physical data storage.

---

## 2. Current semantic_metrics records

For connection `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`, the database defines separate semantic metric rows:

| metric_id | metric_name | business_name | column_name | aggregation_type | synonyms |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `96C1224B...` | `cy` | `C Y` | `CY` | `SUM` | `Sales, Current year sales, This year sales, 2026` |
| `4547266B...` | `py` | `P Y` | `PY` | `SUM` | `Previous Year Sales, 1 year ago sales,Last year sales` |
| `72F5251C...` | `ppy` | `P P Y` | `PPY` | `SUM` | `Prior Previous Year Sales, 2 years ago Sales` |
| `4A95DFBD...` | `pppy` | `P P P Y` | `PPPY` | `SUM` | `Prior Prior Previous Year Sales, 3 years ago Sales` |
| `5B2C7B95...` | `ppppy` | `P P P P Y` | `PPPPY` | `SUM` | `Prior Prior Prior Previous Year Sales, 4 years ago Sales` |

---

## 3. Physical Sales Measure Structure

The primary table `QB_MDJMD_SALES_5YRS_SUMMARY` does not have a generic `Sales` column with a raw date field. Instead, sales measures are pre-pivoted into period columns:
- **Current Year**: `CY`
- **Previous Year**: `PY`
- **Prior Previous Year**: `PPY`
- **Prior Prior Previous Year**: `PPPY`
- **Prior Prior Prior Previous Year**: `PPPPY`
And corresponding quantity/quarter column variants (`CYQ`, `PYQ`, etc.).

---

## 4. SemanticResolver Behavior

1. **Candidate Generation**: Matches user question tokens against `business_name`, `metric_name`, and `synonyms` using deterministic scoring.
2. **Overlap Filtering**: Selects candidate matches with the highest score and longest match length.
3. **Temporal Override**: If `PreviousYearIntent` or `YearComparisonIntent` is detected, the resolver programmatically overrides the matches:
   - Re-binds `CY` -> `PY` if `PreviousYearIntent` is active.
   - Appends the missing partner metric if `YearComparisonIntent` is active.

---

## 5. Query-by-Query Resolution Matrix

Based on actual runtime tracing, the queries resolve as follows:

| Query | Normalized | Matched Metric(s) | Business Name(s) | Physical Column(s) | Temporal Intent | Final Semantic Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Show sales** | `show sales` | `cy` | `C Y` | `CY` | `None` | `Metrics=['C Y']` |
| **Show current year sales** | `show this year sales` | `cy` | `C Y` | `CY` | `CurrentYearIntent` | `Metrics=['C Y']` |
| **Show this year's sales** | `show this year sales` | `cy` | `C Y` | `CY` | `CurrentYearIntent` | `Metrics=['C Y'], Dimensions=['createddate Year']` |
| **Show CY sales** | `show cy sales` | `cy` | `C Y` | `CY` | `None` | `Metrics=['C Y']` |
| **Show previous year sales** | `show last year sales` | `py` | `P Y` | `PY` | `PreviousYearIntent` | `Metrics=['P Y']` |
| **Show PY sales** | `show py sales` | `py`, `cy` | `P Y`, `C Y` | `PY`, `CY` | `None` | `Metrics=['P Y', 'C Y']` *(Collision)* |
| **Show sales last year** | `show sales last year` | `py` *(re-bound)* | `P Y` | `PY` | `PreviousYearIntent` | `Metrics=['P Y'], Dimensions=['createddate Year']` |
| **Show current year sales by month** | `show this year sales by month` | `cy`, `docmonth` | `C Y`, `Doc Month` | `CY`, `DocMonth` | `CurrentYearIntent` | `Metrics=['C Y', 'Doc Month']` |

---

## 6. Metric/Synonym Collisions

- **Double Match on PY sales**: The phrase `"py sales"` matches `"py"` directly (scoring `P Y`) and `"sales"` directly (scoring `C Y`). Because the two spans do not overlap, both metrics are returned in the final prompt, causing duplicate metric selection.
- **Dueling Paths for "last year"**: `"Show sales last year"` matches `"sales"` -> `cy`, then is re-bound to `py` via code override. However, `"Show previous year sales"` matches `"previous year sales"` -> `py` via database synonym directly. 

---

## 7. Temporal Interaction

The period-specific synonyms (`"Previous Year Sales"`, `"Current year sales"`) duplicate the logic of the temporal pipeline. If the temporal pipeline resolves an intent as `PREVIOUS_YEAR`, matching a synonym that already binds to `PY` is redundant.

---

## 8. Current SemanticPlan Representation

Under the current implementation, the `SemanticPlan` records the matched physical mapping directly:
- `Metrics`: `C Y (QB_MDJMD_SALES_5YRS_SUMMARY.CY as SUM)`
- `Query Shape`: `SINGLE_VALUE`

---

## 9. Root Cause of "C Y" appearing as metric

Because `"Sales"` is registered as a synonym of `"C Y"`, the resolver returns `"C Y"` as the resolved semantic metric, rather than identifying it as the generic concept `Sales` mapped to a period column.

---

## 10. Recommended Canonical Model

We recommend **Model C (Hybrid Model with Separation of Concerns)**:

1. **Canonical Metric**: Define a single canonical business metric: **`Sales`** (synonyms: `Sales, Revenue, Turnover`).
2. **Temporal Strategy Binding**:
   - The semantic resolver maps generic terms to the canonical `Sales` metric.
   - The `SemanticPlanBuilder` looks at the resolved `TimeContext` and dynamically binds `Sales` to the physical column:
     - If strategy is `SNAPSHOT`:
       - `CURRENT_YEAR` -> bind `Sales` to `CY`
       - `PREVIOUS_YEAR` -> bind `Sales` to `PY`
       - `PPY` -> bind `Sales` to `PPY`
     - If strategy is `DATE_COLUMN`:
       - Bind to date-filtered column (e.g. `Amt` or `SalesAmount`) and apply time range constraints.
3. **Rationale**: This eliminates duplicate metric matching, removes hardcoded post-processing overrides, and cleanly decouples business definitions from database storage optimizations.

---

## 11. Synonym Cleanups

1. **Remove** `"Sales"` from `cy`'s database synonyms list.
2. **Remove** `"Previous Year Sales"` and `"Last year sales"` from `py`'s synonyms list (let the temporal pipeline map generic `"Sales"` to `py` during the binding phase).
3. **Keep** direct acronyms like `"CY"` and `"PY"` as direct synonyms for users specifically requesting them.

---

## 12. Modifiable Components

- **Database Table**: `semantic_metrics` (Clean up synonyms).
- **Resolver**: [`backend/semantic/semantic_resolver.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/semantic_resolver.py) (Remove lines 445–486).
- **Builder**: [`backend/semantic/semantic_plan_builder.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/semantic_plan_builder.py) (Add dynamic binding translation).

---

## 13. Regression Risks

- Queries mentioning specific column acronyms (e.g. `"Show CY"`) could fail if acronyms are completely stripped. Thus, acronyms must be preserved as secondary names.

---

## 14. Required Implementation Order

1. **Step 1**: Update database records to establish a generic canonical `Sales` metric and clean up overlapping period synonyms.
2. **Step 2**: Implement physical binding selection in `SemanticPlanBuilder` using the temporal strategy.
3. **Step 3**: Remove the hardcoded override logic in `SemanticResolver`.
