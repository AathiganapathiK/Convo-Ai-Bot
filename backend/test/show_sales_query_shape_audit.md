# 1. Executive Verdict

The investigation has confirmed that `CardName` and the associated `GROUP BY` clause are introduced by the **LLM itself** during SQL generation. 

This behavior is caused by a **Query Shape Instruction Gap** in the prompt. Because the prompt builder is completely silent on the expected query shape, the LLM receives no instruction to output a simple scalar query (`SINGLE_VALUE` shape) when no dimensions are resolved. Instead, seeing `CardName` prominently featured in the `DATABASE SCHEMA` columns and highlighted in the `METADATA RULES` section, the LLM infers that it should select and group by `CardName` to provide a breakdown of sales. 

---

# 2. Clean Chat Verification

We ran the query `"Show sales"` on a clean chat session:
* **Session ID:** `144`
* **History Length:** `0` (`history = []`)
* **Memory Source:** Database hydration query returned `[]` (cache miss on session).
* **Semantic Context:** 
  - Metric resolved: `cy` (business name `"C Y"`, table `QB_MDJMD_SALES_5YRS_SUMMARY`, column `CY`, aggregation `SUM`).
  - Dimensions resolved: `[]` (None).
  - Value matches / filters: `[]` (None).
* **Temporal State:** `NONE` (no temporal intent matched).
* **Selected Table:** `QB_MDJMD_SALES_5YRS_SUMMARY`
* **Conclusion:** No historical value/filter or temporal constraints were inherited.

---

# 3. Semantic Output

Before `PromptBuilder` is called, the semantic resolution stage returns:
* **Query Shape:** Conceptually `SINGLE_VALUE` (no dimensions or groupings are resolved).
* **Dimensions:** `[]`
* **Grouping:** `None`
* **CardName:** `None`
* **Ranking / Top-N:** `None`
* **Ordering:** `None`
* **Conclusion:** The semantic engine resolves the query correctly; it does not introduce `CardName` or any grouping column.

---

# 4. QueryExamplesService Results

`QueryExamplesService.retrieve()` was traced for the `"Show sales"` query:
* **Value-Filter Check:** Under the Gate 1B value-filter integrity fix, any stored query example containing specific product/value constraints (like `ProdGrp2 = 'MENS PYJAMA PANT'`) is **excluded** because the current query resolves no filters.
* **Returned Examples:** `[]` (empty list).
* **Conclusion:** **QueryExamplesService did NOT introduce CardName.** No examples containing `CardName` or `GROUP BY CardName` were returned to the prompt builder.

---

# 5. Prompt Analysis

We inspected the final compiled prompt sent to the LLM for the `"Show sales"` query:

* **Semantic Context Section:** Contains only the resolved metric `C Y` on table `QB_MDJMD_SALES_5YRS_SUMMARY`. No dimensions or values.
* **Metadata Rules Section:** Contains the table-specific replacement rule:
  `Use QB_MDJMD_SALES_5YRS_SUMMARY.CardName instead of QB_MDJMD_SALES_5YRS_SUMMARY.CardCode for SELECT, GROUP BY, ORDER BY`
* **Database Schema Section:** Contains the column list for table `QB_MDJMD_SALES_5YRS_SUMMARY` which includes `CardName NVARCHAR(100)`.

#### Table: Presence of CardName and Grouping in Prompt Sections
| Source | Contains CardName? | Contains GROUP BY CardName? |
|--------|---------------------|-----------------------------|
| Semantic Context | No | No |
| Query Examples | No | No |
| Query Shape | No (Section Missing) | No (Section Missing) |
| Relevant Schema | Yes | No |
| SQL Rules / Metadata Rules | Yes | Yes (Metadata Rules mention SELECT, GROUP BY, ORDER BY) |

---

# 6. LLM Output

* **Final Prompt Content:** Injected table schema and metadata rules containing `CardName`, but lacked any query-shape constraints or instructions.
* **Raw LLM SQL Output:**
  ```sql
  SELECT TOP 100
      CardName,
      SUM(CY) AS TotalSales
  FROM
      QB_MDJMD_SALES_5YRS_SUMMARY
  GROUP BY
      CardName
  ORDER BY
      TotalSales DESC;
  ```
* **Verdict:** **The LLM independently introduced CardName.** Because `CardName` was present in the schema and metadata rules, but the prompt lacked a query-shape contract (allowing it to default to a scalar query), the LLM assumed a breakdown of sales by card name was expected.

---

# 7. SQL Post-Processing

* **Raw LLM SQL:** `SELECT TOP 100 CardName, SUM(CY)... GROUP BY CardName`
* **SQL Validation:** Passed (valid SQL Server syntax).
* **SQL Repair:** Skipped (no repair mutations applied).
* **Final Executed SQL:** `SELECT TOP 100 CardName, SUM(CY)... GROUP BY CardName`
* **Conclusion:** Post-processing stages did not introduce or mutate the query shape.

---

# 8. First Appearance of CardName

* **First Divergence Point:** The first appearance of `CardName` within the query-specific resolved variables is the **LLM output** itself.
* **Prompt Source:** `CardName` was visible to the LLM only as part of the static schema definition and metadata replacement rules, not as a requested semantic parameter.

---

# 9. Query Shape Architecture

* **Codebase Search:** The codebase defines query shapes in [`backend/semantic/models/semantic_plan.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/models/semantic_plan.py#L24-L35):
  ```python
  class SemanticQueryShape(str, Enum):
      SINGLE_VALUE = "SINGLE_VALUE"
      COMPARISON = "COMPARISON"
      TREND = "TREND"
      RANKED_LIST = "RANKED_LIST"
      LARGE_SUMMARY = "LARGE_SUMMARY"
      DETAIL = "DETAIL"
      DISTRIBUTION = "DISTRIBUTION"
  ```
* **Usage in Pipeline:** The `SemanticPlan` model defines `query_shape: Optional[SemanticQueryShape] = None`, but this model is **not instantiated or utilized** in the active SQL prompt generation pipeline (`app.py` or `PromptBuilder`).
* **Verdict:** The pre-SQL query-shape contract is **missing** from the runtime pipeline.

---

# 10. Root Cause

1. **Missing Pre-SQL Query-Shape Contract:** The prompt builder does not compile or pass the target `SemanticQueryShape` (e.g. `SINGLE_VALUE` vs. `GROUPED`) to the LLM.
2. **LLM Guesswork from Metadata Rules:** In the absence of a query-shape constraint, the LLM is misled by the table's `METADATA RULES` (which mention `CardName` for `SELECT, GROUP BY, ORDER BY`) and assumes it should apply them.

---

# 11. Correct Architectural Owner

* **Owner:** **`PromptBuilder`**
* **Responsibility:** The prompt builder should analyze the resolved semantic objects (if `dimensions` list is empty, shape is `SINGLE_VALUE`) and inject a strict query-shape instruction block to guide the LLM's query structure.

---

# 12. Minimal Fix

1. **Define Query Shape in Prompt Builder:**
   In [`backend/ai/prompt_builder.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/ai/prompt_builder.py), determine the expected query shape based on semantic resolver outputs. If `dimension_objects` is empty, set shape to `SINGLE_VALUE`.
2. **Inject Query Shape Instructions:**
   Add a `QUERY SHAPE CONSTRAINTS` section to the prompt template:
   ```
   ===========================================================
   QUERY SHAPE CONSTRAINTS
   ===========================================================
   Expected Query Shape: SINGLE_VALUE
   
   Strict Instructions:
   - This query must compute a single aggregated scalar value (e.g., SELECT SUM(...)).
   - Do NOT include any GROUP BY clauses.
   - Do NOT select any non-aggregated grouping columns (such as CardName, ProdGrp2, etc.).
   ```
3. **Filter Examples by Query Shape:**
   Update `QueryExamplesService.retrieve()` to reject query examples whose query shape does not match the current query's shape (preventing `GROUP BY` examples from being matched for `SINGLE_VALUE` queries).

---

# 13. Regression Matrix

When query-shape logic is implemented, the expected behaviors are:

1. **"Show sales"**
   - Expected Shape: `SINGLE_VALUE`
   - SQL: `SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY`
2. **"Show sales this year"**
   - Expected Shape: `SINGLE_VALUE`
   - SQL: `SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY` (with year filters)
3. **"Show sales last year"**
   - Expected Shape: `SINGLE_VALUE`
   - SQL: `SELECT SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY` (with year filters)
4. **"Show sales by card"**
   - Expected Shape: `GROUPED` / `DETAIL`
   - SQL: `SELECT CardName, SUM(CY) FROM QB_MDJMD_SALES_5YRS_SUMMARY GROUP BY CardName`
5. **"Show sales by city"**
   - Expected Shape: `GROUPED` / `DETAIL`
   - SQL: `SELECT City, SUM(CY) FROM ... GROUP BY City`
6. **"Show top 10 cards by sales"**
   - Expected Shape: `RANKED_LIST`
   - SQL: `SELECT TOP 10 CardName, SUM(CY) FROM ... GROUP BY CardName ORDER BY SUM(CY) DESC`
7. **"Show sales trend"**
   - Expected Shape: `TREND`
   - SQL: `SELECT DocMonth, SUM(CY) FROM ... GROUP BY DocMonth`
8. **"Compare current year and previous year sales"**
   - Expected Shape: `COMPARISON`
   - SQL: `SELECT SUM(CY), SUM(PY) FROM ...`

---

# 14. Final Recommendation

Create a **Pre-SQL Query-Shape Classifier** inside the `PromptBuilder` that inspects resolved dimensions and temporal intents to map the current request to a `SemanticQueryShape`, and enforce this shape using explicit constraints in the prompt instructions.
