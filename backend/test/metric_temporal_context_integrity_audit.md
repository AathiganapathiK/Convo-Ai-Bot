# Metric, Temporal, Value, Context, Prompt & SQL Integrity Audit

## 1. Executive Summary

This forensic audit investigates two real production/test execution failures (Case A and Case B) to trace how correctness errors enter the Text-to-SQL pipeline.

### Core Findings
1. **CY vs PY Mismatch (Case A)**: `TemporalPipeline` correctly resolved `PREVIOUS_YEAR` for *"Show last year cotton sales"*. However, `SemanticResolver` matched the keyword *"sales"* to the metric `C Y` (column `CY`), while `QueryExamplesService` injected a few-shot example for *"Show cotton sales"* hardcoded with `SUM(CY)`. The LLM obeyed the metric registration and few-shot example over the temporal prompt text, generating `SUM(CY)`.
2. **Value Column Divergence (Case A)**: The user selected `"WHITE SHIRT 100% COTTON"`, which `DimensionValueResolver` mapped to column `ProdGrp2`. `PromptBuilder` rendered `REQUIRED VALUE FILTERS: - ProdGrp2 = 'WHITE SHIRT 100% COTTON'`. However, the LLM diverged during SQL generation and output `WHERE T1.ProdGrp3 = 'WHITE SHIRT 100% COTTON'`.
3. **Context Contamination (Case B)**: In Turn 2 (*"show last year sales"*), `DimensionValueResolver` follow-up context logic automatically inherited `prev_resolved_values` from Turn 1 because no new product value was mentioned. It injected `DHOTI : 3.80MT KL COTTON` into `REQUIRED VALUE FILTERS`, forcing the LLM to append `WHERE T1.ProdGrp3 = 'DHOTI...'` to an independent query.
4. **Unrequested CardName Grouping (Cases A & B)**: Neither `SemanticResolver` nor `MetadataResolver` requested `CardName`. The LLM copied `SELECT CardName ... GROUP BY CardName` directly from the retrieved few-shot example (`"Show cotton sales"`).
5. **Summary Hallucination**: The summarizer prompt receives raw table names like `QB_MDJMD_SALES_5YRS_SUMMARY` without structured temporal plan bounds, causing the LLM to claim the query covers the *"past five years"*.

---

## 2. Case A Forensic Trace

**User Question**: *"Show last year cotton sales"*  
**User Clarification Selection**: `"WHITE SHIRT 100% COTTON"`  
**Observed Generated SQL**:
```sql
SELECT TOP 100
    T1.CardName,
    SUM(T1.CY) AS CottonSales
FROM
    QB_MDJMD_SALES_5YRS_SUMMARY AS T1
WHERE
    T1.ProdGrp3 = 'WHITE SHIRT 100% COTTON'
GROUP BY
    T1.CardName
ORDER BY
    CottonSales DESC;
```

### End-to-End Trace Table

| Stage | Input | Component / File | Output Value / State | Correctness |
| :--- | :--- | :--- | :--- | :--- |
| **1. Temporal Detection** | `"Show last year cotton sales"` | `TemporalDetector` (`detector.py`) | Pattern: `previous_year`, Intent: `PREVIOUS_YEAR`, Confidence: 0.95 | **CORRECT** |
| **2. Temporal Resolution** | Intent `PREVIOUS_YEAR` | `TimeResolver` (`time_resolver.py`) | Strategy: `DATE_COLUMN`, Start: `2025-01-01`, End: `2025-12-31` | **CORRECT** |
| **3. Temporal Formatting** | `TimeContext` | `TemporalPromptFormatter` (`temporal_prompt_formatter.py`) | Rendered Block: `YEAR(createddate) = YEAR(DATEADD(year, -1, GETDATE()))` | **CORRECT** |
| **4. Metric Resolution** | `"Show last year cotton sales"` | `SemanticResolver` (`semantic_resolver.py`) | `metrics: ['C Y']`, `metric_objects: [{metric_name: 'cy', column_name: 'CY'}]` | **INCORRECT** (Conflated "sales" with `CY`) |
| **5. Value Resolution** | `"cotton"` | `DimensionValueResolver` (`dimension_value_resolver.py`) | Matches: `WHITE SHIRT 100% COTTON` (`ProdGrp2`), `DHOTI...` (`ProdGrp3`). Status: `STRONG_AMBIGUITY` | **CORRECT** |
| **6. Clarification Selection** | User choice: `"WHITE SHIRT 100% COTTON"` | `app.py` | `clarified_candidate`: `column_name: 'ProdGrp2'`, `value: 'WHITE SHIRT 100% COTTON'` | **CORRECT** |
| **7. Resumption Resolution** | `clarified_candidate` | `SemanticResolver` (`semantic_resolver.py`) | `value_matches: [{column_name: 'ProdGrp2', value: 'WHITE SHIRT 100% COTTON'}]` | **CORRECT** |
| **8. Table Selection** | Mapped metrics & values | `RelevantTableResolver` (`relevant_table_resolver.py`) | `QB_MDJMD_SALES_5YRS_SUMMARY` (Score: 8), `PBI_ENES_ORDER_PENDING_SUMMARY` (Score: 2) | **CORRECT** |
| **9. Few-Shot Retrieval** | `relevant_tables: ['QB_MDJMD_SALES_5YRS_SUMMARY']` | `QueryExamplesService` (`query_examples_service.py`) | Retreived: `"Show cotton sales" -> SELECT CardName, SUM(CY) ... GROUP BY CardName` | **INCORRECT** (Injected `CY` + `CardName`) |
| **10. Prompt Compilation** | Backend results | `PromptBuilder` (`prompt_builder.py`) | Rendered prompt containing `RELEVANT METRICS: ['C Y']`, `REQUIRED VALUE FILTERS: - ProdGrp2 = 'WHITE SHIRT 100% COTTON'`, and Few-Shot example | **CONTRADICTORY** |
| **11. LLM Generation** | Rendered prompt | `LLMExecutionService` (`ai_service.py`) | Generated SQL using `SUM(CY)`, `ProdGrp3 = 'WHITE SHIRT...'`, and `GROUP BY CardName` | **INCORRECT** (Diverged from prompt filter `ProdGrp2`) |

---

## 3. Case B Forensic Trace

**Conversation Thread**:
- **Turn 1**: *"Show last year cotton sales"* -> User selects `"WHITE SHIRT 100% COTTON"`.
- **Turn 2**: *"show last year sales"*

**Observed Generated SQL (Turn 2)**:
```sql
SELECT TOP 100
    T1.CardName,
    SUM(T1.PY) AS LastYearSales
FROM
    QB_MDJMD_SALES_5YRS_SUMMARY AS T1
WHERE
    YEAR(T1.createddate) = YEAR(GETDATE()) - 1
    AND T1.ProdGrp3 = 'DHOTI : 3.80MT KL COTTON'
GROUP BY
    T1.CardName
ORDER BY
    LastYearSales DESC;
```

### End-to-End Trace Table

| Stage | Input | Component / File | Output Value / State | Correctness |
| :--- | :--- | :--- | :--- | :--- |
| **1. History Loading** | `session_id` | `conversation_memory.py` | Turn 1 context: `resolved_values: [{value: 'DHOTI : 3.80MT KL COTTON', column_name: 'ProdGrp3'}]` | **CORRECT** |
| **2. Turn 2 Value Resolution** | `"show last year sales"` + `prev_context` | `DimensionValueResolver` (`dimension_value_resolver.py`) | `followup_context.applied = True`. Inherited `DHOTI : 3.80MT KL COTTON` into `value_matches` | **INCORRECT** (Inherited product filter on independent topic shift) |
| **3. Turn 2 Metric Resolution** | `"show last year sales"` | `SemanticResolver` (`semantic_resolver.py`) | `metrics: ['P Y']`, `metric_objects: [{metric_name: 'py', column_name: 'PY'}]` | **CORRECT** |
| **4. Turn 2 Temporal Resolution** | `"show last year sales"` | `TemporalPipeline` (`pipeline.py`) | Rendered Block: `YEAR(createddate) = YEAR(DATEADD(year, -1, GETDATE()))` | **CORRECT** |
| **5. Prompt Compilation** | Turn 2 results | `PromptBuilder` (`prompt_builder.py`) | Prompt contains `REQUIRED VALUE FILTERS: - ProdGrp3 = 'DHOTI : 3.80MT KL COTTON'` and Rule 11 forcing filter application | **INCORRECT** (Forced stale filter via Rule 11) |
| **6. LLM Generation** | Rendered prompt | `LLMExecutionService` (`ai_service.py`) | Generated SQL appending `WHERE T1.ProdGrp3 = 'DHOTI...'` and double temporal constraint | **INCORRECT** |

---

## 4. Metric Integrity

- **Metric-Temporal Conflation**: `semantic_metrics` table registers `cy` (Current Year Sales) with synonym `"sales"`. When a user asks *"Show last year sales"*, `SemanticResolver` matches `"sales"` to metric `cy` (`CY` column), ignoring the temporal modifier *"last year"*.
- **Authoritative Aggregation**: Aggregation type is configured in `semantic_metrics` as `SUM`. However, for bare queries without explicit aggregate instructions, the LLM relies on few-shot formatting rather than a compiled pre-SQL plan.
- **Divergence**: `TemporalPipeline` resolved `PREVIOUS_YEAR`, but `SemanticResolver` output `CY`. PromptBuilder included both, creating conflicting instructions.

---

## 5. Temporal Integrity

- `TemporalPipeline` correctly parses `"last year"` as `PREVIOUS_YEAR` (start: `2025-01-01`, end: `2025-12-31`).
- **Double Temporal Filtering**: In Case B, the SQL contains both `SUM(PY)` (which is already Previous Year Sales) AND `WHERE YEAR(createddate) = YEAR(GETDATE()) - 1`. This happens because `TemporalPipeline` outputs the date rule while `SemanticResolver` outputs the `PY` metric column, and the LLM applies both.

---

## 6. Value / Dimension Integrity

- **Selected Column Divergence**:
  - `clarified_candidate` explicit column: `ProdGrp2`
  - Prompt `REQUIRED VALUE FILTERS`: `- ProdGrp2 = 'WHITE SHIRT 100% COTTON'`
  - LLM Generated SQL: `WHERE T1.ProdGrp3 = 'WHITE SHIRT 100% COTTON'`
- **First Divergence Point**: LLM generation stage. The backend resolver and PromptBuilder both specified `ProdGrp2`, but the LLM hallucinated `ProdGrp3` due to column similarity in the schema block.

---

## 7. Context Integrity

- **Stale Filter Inheritance**: `DimensionValueResolver.resolve_matches` checks eligibility for follow-up dimension inheritance. If a question contains no explicit product value tokens, it inherits `prev_resolved_values` from `previous_semantic_context`.
- **Architectural Gap**: The context manager cannot distinguish between:
  1. *Explicit follow-up*: *"show last year sales for it"*
  2. *Context-dependent follow-up*: *"what about last year"*
  3. *New independent question*: *"show last year sales"*
- All queries without value tokens are treated as follow-ups, polluting new questions with old value filters.

---

## 8. Query Shape Integrity

- Both generated queries included `SELECT CardName ... GROUP BY CardName ORDER BY CottonSales DESC` despite the user not asking for a breakdown by customer card name.
- **First Divergence Point**: Few-shot example in `query_examples` (`"Show cotton sales"`).
- **Architectural Gap**: Data shape classification is post-execution only (`DataShapeClassifier.classify`). There is no pre-SQL query shape compiler enforcing `SINGLE_VALUE` (no `GROUP BY`) when the user asks for a simple aggregate.

---

## 9. Table / Join Integrity

- `RelevantTableResolver` correctly scored `QB_MDJMD_SALES_5YRS_SUMMARY` as 8 (metric match on `CY`/`PY`) and `PBI_ENES_ORDER_PENDING_SUMMARY` as 2 (value match on `ProdGrp2`).
- Table selection worked correctly.

---

## 10. Few-Shot Integrity

- Retrieved example:
  `Q: Show cotton sales -> SQL: SELECT TOP 100 CardName, SUM(CY) AS CottonSales FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'LS ZARI COTTON' GROUP BY CardName ORDER BY CottonSales DESC;`
- **Contamination**: This example contains `SUM(CY)` (conflicting with `PY`) and `GROUP BY CardName` (unrequested grouping). The LLM copied its style per Rule 9 (`"Follow the style demonstrated by Previous Successful Queries"`).

---

## 11. Prompt Integrity

### Decision Divergence Table

| Decision | Backend Resolver | Prompt Content | LLM Generated SQL | Final Executed SQL | Divergence Layer |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Metric (Case A)** | `C Y` (`CY`) | `RELEVANT METRICS: ['C Y']` | `SUM(T1.CY)` | `SUM(T1.CY)` | `SemanticResolver` metadata synonym |
| **Temporal (Case A)** | `PREVIOUS_YEAR` | `YEAR(createddate) = YEAR(GETDATE()) - 1` | None (used `CY`) | None | LLM (obeyed metric over temporal) |
| **Value Column (Case A)** | `ProdGrp2` | `REQUIRED VALUE FILTERS: ProdGrp2 = '...'` | `ProdGrp3 = '...'` | `ProdGrp3 = '...'` | LLM SQL Generation |
| **Grouping (Case A & B)** | Unspecified | Style from Few-Shot | `GROUP BY CardName` | `GROUP BY CardName` | Few-Shot retrieval + LLM |
| **Filter (Case B)** | Inherited `DHOTI` | `REQUIRED VALUE FILTERS: ProdGrp3 = 'DHOTI...'` | `WHERE ProdGrp3 = 'DHOTI...'` | `WHERE ProdGrp3 = 'DHOTI...'` | `DimensionValueResolver` context manager |

---

## 12. SQL Integrity

- The generated SQL passed AST and syntax validation because `ProdGrp3`, `CY`, `PY`, and `CardName` are valid physical columns in `QB_MDJMD_SALES_5YRS_SUMMARY`.
- Syntactic validity masked severe semantic divergence.

---

## 13. Summary / Insight Integrity

- The summary prompt in `build_summary_prompt` receives raw query text, generated SQL, and result rows.
- The physical table name `QB_MDJMD_SALES_5YRS_SUMMARY` contains `5YRS`.
- Because the summary prompt lacks structured temporal metadata (e.g. `period = '2025'`), the LLM interprets `5YRS_SUMMARY` in the schema context and hallucinates that the data covers the *"past five years"*.

---

## 14. Multiple Sources of Truth

| Decision | Authoritative Owner | Secondary / Inferred Owner | Conflict Risk |
| :--- | :--- | :--- | :--- |
| **Metric Period** | `TemporalPipeline` | `SemanticResolver` (synonyms) & Few-Shots | **HIGH** |
| **Value Filter Column** | `DimensionValueResolver` | LLM Schema reasoning | **HIGH** |
| **Query Shape / Grouping** | `SemanticPlan` (Missing) | Few-Shot examples & LLM guesswork | **HIGH** |
| **Context Retention** | Context Manager | `DimensionValueResolver` fallback | **HIGH** |
| **Summary Bounds** | `TemporalPipeline` | Summary LLM (table name hints) | **MEDIUM** |

---

## 15. Historical Bug Mapping

- **Banian / Banians Mismatch**: Value Resolution (Fixed).
- **Growth / Degrowth**: Intent / Temporal (Unsupported).
- **Chennai Duplicate Ambiguity**: Ambiguity Classifier (Fixed).
- **"for coimbatore" Follow-Up Failure**: Context Manager (Fixed for explicit dimension follow-ups).
- **CY vs PY Mismatch (Case A)**: Metric / Temporal Conflation + Few-Shot Contamination (**UNPROTECTED**).
- **ProdGrp3 Divergence (Case A)**: LLM Obedience Failure (**UNPROTECTED**).
- **Context Contamination (Case B)**: Context Inheritance Defect (**UNPROTECTED**).

---

## 16. Genericity / New-DB Analysis

All 5 core failure modes identified are **SEMANTIC-GENERIC** and **CONTEXT-GENERIC** architecture defects. They are not specific to `QB_MDJMD_SALES_5YRS_SUMMARY` or `cotton` queries.

---

## 17. Root Cause Matrix

| Observed Defect | Primary Root Cause Classification | Secondary Root Cause |
| :--- | :--- | :--- |
| **CY used for "last year"** | **B. Metric/temporal conflation** | **I. Few-shot contamination** |
| **ProdGrp3 instead of ProdGrp2** | **J. LLM obedience failure** | **H. Prompt construction defect** |
| **Case B filter contamination** | **E. Context inheritance defect** | **H. Prompt construction defect (Rule 11 force)** |
| **Unrequested CardName grouping** | **F. Query-shape defect** | **I. Few-shot contamination** |
| **Summary claims "past 5 years"** | **M. Summary grounding defect** | **H. Prompt construction defect** |

---

## 18. Correct Architectural Owner

- **Metric vs Temporal Period**: `SemanticPlan` compiler + `TemporalPipeline`. (Temporal engine must override metric period columns when explicit time bounds are present).
- **Value Filter Column**: `SemanticPlan` compiler + strict prompt constraint/AST validator.
- **Context Contamination**: Context Manager (`conversation_memory.py` / `DimensionValueResolver`). (Must classify query topic shift before inheriting values).
- **Grouping / Query Shape**: Pre-SQL `SemanticPlan` Query-Shape Classifier.
- **Summary Grounding**: Summary Layer (must receive structured `TimeContext`).

---

## 19. Required Regression Matrix

### Metric / Temporal
1. `Show sales` -> Metric: `Sales`, Temporal: `UNSPECIFIED` -> **Request Year Clarification**.
2. `Show sales this year` -> Metric: `Sales`, Temporal: `CURRENT_YEAR` -> `SUM(CY)`.
3. `Show sales last year` -> Metric: `Sales`, Temporal: `PREVIOUS_YEAR` -> `SUM(PY)` or `WHERE YEAR(date) = 2025`.
4. `Compare current year and previous year sales` -> Intent: `COMPARISON`, `SUM(CY)` vs `SUM(PY)`.

### Value + Temporal
5. `Show last year cotton sales` -> `Sales` + `PREVIOUS_YEAR` + `ProdGrp2 = 'WHITE SHIRT...'` -> `SUM(PY)` on `ProdGrp2`.

### Context
6. Turn 1: `Show cotton sales` -> Select `WHITE SHIRT...`  
   Turn 2: `show last year sales` -> **RESET product filter**, execute `Sales` + `PREVIOUS_YEAR`.
7. Turn 1: `Show sales for Chennai`  
   Turn 2: `for Coimbatore` -> **INHERIT City dimension**, filter `City = 'Coimbatore'`.

### Query Shape
8. `Show last year sales` -> `SINGLE_VALUE` aggregate (No `GROUP BY CardName`).
9. `Show sales by card` -> `RANKED_LIST` (`SELECT CardName, SUM(...) GROUP BY CardName`).

---

## 20. Recommended Minimal Fix Order

1. **Fix 1: Metric/Temporal Conflation Guard**: Decouple generic metric `"Sales"` from `CY` in `SemanticResolver` when a temporal intent (`PREVIOUS_YEAR`) is active.
2. **Fix 2: Topic Shift / Context Reset Guard**: Update `DimensionValueResolver` context inheritance to reset `prev_resolved_values` when a new query is an independent topic (e.g. `"show last year sales"`).
3. **Fix 3: Few-Shot Curation & Compatibility**: Remove or update hardcoded `CardName` grouping in general query examples.
4. **Fix 4: Pre-SQL Query Shape Integration**: Enforce `SINGLE_VALUE` shape when no `by <dimension>` is requested, blocking unrequested `GROUP BY` clauses.
5. **Fix 5: SemanticPlan Compiler (Milestone 1A Step 2)**: Unify resolver outputs into an authoritative pre-SQL `SemanticPlan`.

---

## 21. Unknowns / Risks

- **LLM Non-Determinism**: Even with strict prompts, LLMs may occasionally hallucinate column indices (`ProdGrp3` vs `ProdGrp2`) unless enforced by AST repair or rigid plan compilation.

---

## 22. Final Verdict

**CONFIRMED ARCHITECTURAL GAPS AND MULTIPLE SOURCES OF TRUTH IDENTIFIED.**

The failures in Case A and Case B are directly caused by:
1. Conflation of time periods between `TemporalPipeline` and `SemanticResolver` metric synonyms.
2. Unchecked follow-up context inheritance in `DimensionValueResolver`.
3. Lack of pre-SQL query shape enforcement, allowing few-shot style leakage (`CardName` grouping).
4. Prompt serialization rendering conflicting instructions to the LLM.

Implementing the **Semantic Plan Foundation** (Milestone 1A) will centralize these decisions into one authoritative contract, eliminating these root causes.
