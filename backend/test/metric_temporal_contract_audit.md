# Metric ↔ Temporal Contract Audit

## 1. Executive Summary

This read-only audit investigates the interaction between **Business Metric Meaning** and **Temporal Meaning** across the Text-to-SQL pipeline.

### Core Problem
Currently, the system conflates the business metric `"Sales"` with the specific physical column `CY` (Current Year Sales). Because `"sales"` is registered as a direct synonym for metric `cy` in database table `semantic_metrics`, queries like *"Show sales"* default directly to `CY` without recognizing that the time period is `UNSPECIFIED`. When temporal modifiers like *"last year"* are present, `TemporalPipeline` correctly detects `PREVIOUS_YEAR`, but `SemanticResolver` still resolves metric `cy` (`CY` column), creating severe internal contradictions in the prompt.

---

## 2. Test Questions Trace & First Divergence Matrix

The 6 benchmark questions were traced end-to-end through `TemporalPipeline`, `SemanticResolver`, `DimensionValueResolver`, `QueryExamplesService`, and `PromptBuilder`.

| # | Question | Matched Metric (Resolver) | Temporal Intent (Pipeline) | Value Matches / Exceptions | First Divergence Point |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | *"Show sales"* | `c y` (`CY`) | `None` (`UNSPECIFIED`) | None | **`SemanticResolver`**: Maps `"sales"` synonym to `CY` metric instead of generic `Sales` + `UNSPECIFIED` temporal clarification. |
| **2** | *"Show sales this year"* | `c y` (`CY`) | `CURRENT_YEAR` | None | **`PromptBuilder`**: Double temporal representation (`CY` snapshot metric + `createddate` SQL filter block). |
| **3** | *"Show sales last year"* | `c y` (`CY`) | `PREVIOUS_YEAR` | None | **`SemanticResolver`**: Conflict! Metric resolves to `CY` (Current Year) while Temporal detects `PREVIOUS_YEAR`. Prompt receives contradictory instructions. |
| **4** | *"Show current year sales"* | `c y` (`CY`) | `CURRENT_YEAR` | `Duestatus = 'Current Due (1-7)'` | **`DimensionValueResolver`**: Token `"current"` was fuzzy-matched to dimension value `'Current Due (1-7)'`, raising an `AmbiguityException`. |
| **5** | *"Show previous year sales"* | `p y` (`PY`) | `PREVIOUS_YEAR` | None | **`PromptBuilder`**: Double temporal representation (`PY` snapshot metric + `createddate = 2025` SQL filter block). |
| **6** | *"Compare current year and previous year sales"* | `p y` (`PY`) | `YEAR_COMPARISON` | `State1 = 'AN'` | **`DimensionValueResolver`**: Stop-word `"and"` was fuzzy-matched to state code `'AN'`, AND `SemanticResolver` returned only `PY` instead of both `CY` and `PY`. |

---

## 3. Current vs Desired Behavior

### A. Current Behavior
- `"Show sales"` -> Resolves `cy` (`CY` column). Executes `SUM(CY)` directly.
- `"Show sales this year"` -> Resolves `cy` (`CY` column) + `WHERE YEAR(createddate) = YEAR(GETDATE())`.
- `"Show sales last year"` -> Resolves `cy` (`CY` column) + `WHERE YEAR(createddate) = YEAR(DATEADD(year, -1, GETDATE()))` -> **Conflict between `CY` and `PREVIOUS_YEAR`**.
- `"Show current year sales"` -> Triggers false `AmbiguityException` on `'Current Due (1-7)'`.
- `"Compare current year and previous year sales"` -> Resolves only `PY` + triggers false `AmbiguityException` on `'AN'`.

### B. Desired Contract
- **`"Show sales"`**:
  - `metric` = `Sales`
  - `temporal` = `UNSPECIFIED`
  - **Action**: Intercept in pre-SQL gate and ask user: *"Which year's sales would you like to view?"*
- **`"Show sales this year"`**:
  - `metric` = `Sales`
  - `temporal` = `CURRENT_YEAR`
  - **Action**: Bind `Sales` + `CURRENT_YEAR` to table-specific column (`CY` or date filter).
- **`"Show sales last year"`**:
  - `metric` = `Sales`
  - `temporal` = `PREVIOUS_YEAR`
  - **Action**: Bind `Sales` + `PREVIOUS_YEAR` to table-specific column (`PY` or `createddate = 2025`).
- **`"Compare current year and previous year sales"`**:
  - `metric` = `Sales`
  - `intent` = `YEAR_COMPARISON`
  - **Action**: Bind `Sales` to BOTH `CY` and `PY` snapshot columns (or multi-year date range).

---

## 4. Primary Questions & Findings

### A. Why does "Show sales" currently resolve to CY?
In the database table `semantic_metrics`, the metric `cy` (business_name `"C Y"`, column `CY`) contains `"sales"` in its `synonyms` column string: `"sales, sales amount, total sales, cy sales"`. `SemanticResolver._fetch_active_metadata` loads this, and substring matching maps `"sales"` directly to `cy`.

### B. Can the system represent Sales independently from time?
**NO.** Currently, there is no generic `Sales` metric entry. `Sales` is conflated with `CY` (Current Year), `PY` (Previous Year), or `PPY` (Two Years Prior).

### C. Does "last year sales" resolve Sales + PY correctly?
**NO.** `TemporalPipeline` resolves `PREVIOUS_YEAR`, but `SemanticResolver` matches `"sales"` to `cy` (`CY` column). The resulting prompt instructs the LLM to use metric `CY` while enforcing temporal filter `YEAR(createddate) = 2025`.

### D. Do few-shot examples introduce CY/PY conflicts?
**YES.** Few-shot examples in `query_examples` hardcode `SUM(CY)` or `SUM(PY)` for questions like `"Show cotton sales"`, which forces the LLM to copy `CY` even when `PREVIOUS_YEAR` is requested.

---

## 5. Table-Specific Temporal Binding

The architecture contains two different types of tables with distinct temporal mechanics:
1. **Snapshot Tables** (e.g. `QB_MDJMD_SALES_5YRS_SUMMARY`):
   - Time periods are pre-aggregated into physical columns: `CY`, `PY`, `PPY`, `PPPY`, `PPPPY`.
   - Correct handling: `Sales` + `PREVIOUS_YEAR` must bind to physical column `PY` (no `createddate` filter).
2. **Date-Column Tables** (e.g. `PBI_ENES_ORDER_PENDING_SUMMARY`, `PBI_OUTSTANDING_ENES_SUMMARY`):
   - Time periods are dynamic date columns: `CREATEDDATE`, `DocDate`, `DueDate`.
   - Correct handling: `Sales` + `PREVIOUS_YEAR` must bind to physical metric column `Amt` + filter `WHERE YEAR(DocDate) = YEAR(GETDATE()) - 1`.

Currently, `TemporalPipeline` applies date-column rules (`WHERE YEAR(createddate) = ...`) even on snapshot tables that already have `CY`/`PY` columns, leading to **double temporal representation**.

---

## 6. Files & Functions Involved

- `backend/semantic/semantic_resolver.py`: `SemanticResolver.resolve()` and `_fetch_active_metadata()` (Maps `synonyms` to `metric_objects`).
- `backend/semantic/dimension_value_resolver.py`: `DimensionValueResolver.resolve_matches()` (Fuzzy-matches temporal stop-words like `"current"` and `"and"` to dimension values).
- `backend/semantic/temporal/pipeline.py`: `TemporalPipeline.build()` and `TimeResolver.resolve()` (Detects intents and computes time strategy).
- `backend/semantic/temporal/temporal_prompt_formatter.py`: `TemporalPromptFormatter._get_sql_rule()` (Renders raw SQL `WHERE` clauses).
- `backend/ai/prompt_builder.py`: `PromptBuilder.build_sql_prompt()` (Combines metric objects and temporal blocks into prompt string).

---

## 7. Regression Risks

Decoupling `"sales"` from `cy` introduces regression risks in the following components:
1. **`test_semantic_aggregation.py`**: Tests like `test_cy_resolves_with_sum_aggregation` expect `"Show sales"` to resolve directly to `cy`.
2. **`test_temporal_pipeline.py`**: Expects `TemporalPipeline` to output specific `WHERE` blocks.
3. **`test_phase1d_2_b_ambiguity.py`**: Expects ambiguity flow behavior on value matches.
4. **`QueryExamplesService`**: Few-shot matching score relies on metric object identity matching (`cy` vs `Sales`).

---

## 8. Smallest Safe Implementation Change

1. **Semantic Metadata Entry**: Register a generic `sales` metric entry in `semantic_metrics` with `table_name = QB_MDJMD_SALES_5YRS_SUMMARY`, `column_name = CY` (default), but flag it as time-decoupled.
2. **Temporal Stop-Word Exclusions**: Add `"current"`, `"previous"`, and `"and"` to `STOPWORDS` in `semantic/matching/stopwords.py` to prevent false value matches against `'Current Due (1-7)'` and `'AN'`.
3. **SemanticPlan Compiler (Milestone 1A Step 2)**:
   - When `temporal` is `UNSPECIFIED` and metric is `Sales`, set `plan.ambiguity_state` to request year clarification.
   - When `temporal` is `PREVIOUS_YEAR` and table is snapshot-based, bind `Sales` to `PY` column and suppress redundant `createddate` `WHERE` clauses.

---

## 9. Tests That Must Pass After Implementation

- `backend/test/test_semantic_plan.py` (New 12 unit tests)
- `backend/test/test_semantic_aggregation.py`
- `backend/test/test_temporal_pipeline.py`
- `backend/test/test_phase1d_2_b_ambiguity.py`
- `backend/test/test_query_examples_service.py`
