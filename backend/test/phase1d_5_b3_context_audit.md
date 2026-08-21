# PHASE 1D.5.B.3 — CONTEXT-AWARE SEMANTIC RESOLUTION AUDIT

## 1. Executive Summary

This audit evaluates the context-aware semantic resolution pipeline under Phase 1D.5.B.3. We trace the execution flow, analyze telemetry outputs from synthetic and real-database test runs, and assess precedence logic, security boundaries, and context leakage risks.

Our main findings are:
* **Precedence and Isolation are Secure:** The system enforces session, employee, and company boundaries correctly. Explicit current dimensions (B.1) override previous context correctly, and historical chains retrieve the latest valid context.
* **Identified Design Gap in Metric Shift Guard:** The current B.2 metric guard blocks inheritance if *any* metric is present in the current query (`CURRENT_METRICS_PRESENT`). This creates an unnecessary clarification prompt (or retrieval failure) when a user restates the *same* metric in their follow-up question (e.g. Turn 1: `"show qty for Coimbatore city"`, Turn 2: `"show qty for Chennai"`).
* **Verdict:** **CONDITIONAL PASS**. Production changes are recommended for B.3 to refine the metric guard to ignore identical/subset metrics and prevent false ambiguity flags.

---

## 2. Current B.1/B.2 Architecture

The system resolves semantic queries in a sequential pipeline:
1. **Explicit Dimension Filtering (B.1):** Scan token context adjacent to resolved values for dimension names (e.g., "city", "brand", "state"). If found, filter candidates to match.
2. **Follow-Up Dimension Inheritance (B.2):** If the query has a single target value, multiple matching candidate dimensions, and no topic shift or explicit label, filter candidates using the previous turn's successfully resolved dimensions.
3. **Ranking and Classification:** Rank remaining candidates using query coverage and confidence, then classify ambiguity status (`SINGLE_MATCH`, `STRONG_AMBIGUITY`, etc.).

---

## 3. Actual Code Trace

1. **`app.py`:** `/ask` endpoint reads conversation history for the current `employee_id` and `session_id`.
2. **`prompt_builder.py`:** Walks back through history in reverse chronological order, identifying the latest turn containing a non-empty `resolved_values` or `dimensions` context.
3. **`SemanticResolver.resolve`:** Loads active metrics/dimensions, generates raw candidates, and passes the current query metrics (`current_metrics`) and previous context down to `DimensionValueResolver`.
4. **`DimensionValueResolver.resolve_matches`:**
   - Evaluates B.1 explicit labels first.
   - Evaluates B.2 follow-up eligibility:
     - Checks if `has_explicit_label` is True -> skips (`EXPLICIT_DIMENSION_LABEL_PRESENT`).
     - Checks if multiple target values are present -> skips (`MULTIPLE_TARGET_VALUES`).
     - Checks if the candidate values belong to only one dimension -> skips (`SINGLE_DIMENSION_VALUE`).
     - Checks if *any* current metric is present -> skips (`CURRENT_METRICS_PRESENT`).
     - Extracts the set of previously resolved dimensions (`prev_dims_set`). If empty -> skips (`NO_PREVIOUS_RESOLVED_DIMENSION`).
     - Filters the current matches against `prev_dims_set`. If the filtered list is empty -> skips (`NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION`).
     - Otherwise, applies the filter and sets `applied = True`.
5. **`MatchRanker.rank`:** Sorts the filtered matches by token coverage, type priority, and confidence.
6. **`AmbiguityClassifier.classify`:** Labels the final candidate set (e.g. `STRONG_AMBIGUITY` if multiple candidates remain).

---

## 4. Real-Data Diagnostic Results

Diagnostic runs against live connection `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5` yielded the following trace logs:

* **No Previous Context:**
  - Query: `"show qty for Coimbatore"`
  - Candidates: `['City', 'District']`
  - Status: `STRONG_AMBIGUITY` (Requires clarification)
* **Turn 1 (Explicit) -> Turn 2 (Follow-Up):**
  - Turn 1: `"city Coimbatore"` -> Resolves to `City` Coimbatore.
  - Turn 2: `"what about Coimbatore?"` -> Inherits `City` context.
  - Status: `SINGLE_MATCH` (`City` Coimbatore).
* **Metric Shift (Qty -> Amt):**
  - Turn 1: `"show qty for Coimbatore city"` -> Resolves to `City` Coimbatore + `Qty`.
  - Turn 2: `"show amt for Coimbatore"` -> Skip inheritance (`CURRENT_METRICS_PRESENT`).
  - Status: `STRONG_AMBIGUITY` (`City` or `District`).

---

## 5. Synthetic Diagnostic Results

Synthetic testing confirmed the logic handles missing database matches safely:
* **Unmatched Follow-Up Value:**
  - Previous: `Brand` context.
  - Current: `"what about Linen?"` (No indexed matches in active DB connection).
  - Status: `NO_MATCH` (Skips inheritance safely with `NO_ELIGIBLE_PREVIOUS_CONTEXT`).

---

## 6. Scenario-by-Scenario Results

| Case | Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|
| 1 | Prev City + Coimbatore | Inherits City; resolves Coimbatore to City | Inherited City; SINGLE_MATCH | **PASS** |
| 2 | Prev Brand + Linen | Inherits Brand context if candidates exist | Safely resolved to NO_MATCH (no index match) | **PASS** |
| 3 | Explicit overrides previous | District label wins over City | District selected; EXPLICIT_LABEL_PRESENT | **PASS** |
| 4 | Current metric shift | Qty -> Amt skips inheritance | Skipped; CURRENT_METRICS_PRESENT | **PASS** |
| 5 | New topic / intent shift | Skip inheritance | Skipped; NO_ELIGIBLE_PREVIOUS_CONTEXT | **PASS** |
| 6 | Ambiguous current value | Coimbatore resolved to City | Inherited City; SINGLE_MATCH | **PASS** |
| 7 | Multiple current values | Coimbatore and Chennai skips inheritance | Skipped; MULTIPLE_TARGET_VALUES | **PASS** |
| 8 | Label + prev context conflict | City Ramraj overrides Brand context | City selected; EXPLICIT_LABEL_PRESENT | **PASS** |
| 9 | Prev strong ambiguity | Skip inheritance | Skipped; NO_PREVIOUS_RESOLVED_DIMENSION | **PASS** |
| 10| Session isolation | Session A does not affect Session B | Session B has no history; isolated | **PASS** |
| 11| User/company isolation | User 1 does not affect User 2 | User 2 has no history; isolated | **PASS** |
| 12| Context chain | T1 (City) -> T2 (Chennai) -> T3 (Coimbatore) | Coimbatore inherits City from T2 | **PASS** |
| 13| Same metric + follow-up | Inherits City (no shift) | Skipped; CURRENT_METRICS_PRESENT | **FAIL** (Design Gap) |
| 14| No previous context | Normal ambiguity | Skipped; NO_ELIGIBLE_PREVIOUS_CONTEXT | **PASS** |

---

## 7. Context Precedence Findings

The actual implementation strictly respects the required precedence:
1. **Explicit current dimension (B.1)**: Processes early, overriding previous context.
2. **Explicit/current metric and topic**: Blocks B.2 if current metrics are present (needs refinement).
3. **Current query token evidence**: Dictates match spans and consolidations.
4. **Previous valid semantic context (B.2)**: Evaluated next.
5. **Candidate ranking / Ambiguity classification / Clarification**: Succeeds the filtering stages.

---

## 8. Context Leakage / Safety Findings

* **Stale previous dimension overriding current intent:** **SAFE**. Blocked by B.1 explicit label checks and metric shifts.
* **Previous metric leaking into current query:** **SAFE**. Memory only acts as a query resolver filter, not as an SQL construct generator.
* **Previous value being reused incorrectly:** **SAFE**. Only the dimension is inherited; value matching is fresh.
* **Previous ambiguous state becoming a false certainty:** **SAFE**. Lacks dimensions/resolved values in `semantic_context`, blocking B.2.
* **Context crossing sessions/users/companies:** **SAFE**. Hard-locked by `employee_id` and `conversation_id` in SQL queries.

---

## 9. Remaining Defects

None.

---

## 10. Remaining Design Gaps

* **Overly Strict Metric Guard (CASE 13):** The B.2 engine rejects inheritance when the current query contains *any* metrics. If the user repeats the *same* metric (e.g. `"show qty for Coimbatore"` after `"show qty for Chennai city"`), the system fails to inherit the dimension, resulting in a false `STRONG_AMBIGUITY` classification.

---

## 11. B.3 Proposed Contract

### A. Responsibility
Refine follow-up context resolution to ignore current query metrics that match (or are a subset of) the previous turn's successfully resolved metrics, preventing false ambiguity blocks on repeated-metric follow-ups.

### B. Eligibility Rules
1. Previous context contains resolved dimensions.
2. Current query has a single target search value.
3. No explicit B.1 dimension label is present.
4. Current query contains no *new* metrics (i.e., any current metrics must be a subset of the previous turn's metrics).

### C. Skip Conditions
* Current query contains a metric not present in the previous turn's metrics (Topic Shift).
* Explicit dimension label is present.
* Multiple target values present.

---

## 12. Required Production Changes

In `backend/semantic/dimension_value_resolver.py`:
- Modify the `CURRENT_METRICS_PRESENT` guard:
  ```python
  # Instead of:
  # elif current_metrics and len(current_metrics) > 0:
  
  # Implement:
  # prev_metrics_set = {m.get("business_name").lower() for m in previous_semantic_context.get("metrics", [])}
  # current_metrics_set = {m.get("business_name").lower() for m in current_metrics}
  # if not current_metrics_set.issubset(prev_metrics_set):
  #     self.followup_context = {"applied": False, "reason": "CURRENT_METRICS_PRESENT"}
  ```

---

## 13. Required Tests

### Unit Tests
* `test_same_metric_inheritance`: Previous Qty + City -> Current Qty + Coimbatore inherits City.
* `test_different_metric_shift`: Previous Qty + City -> Current Amt + Coimbatore skips inheritance.

---

## 14. Regression Impact

Low. Only queries that restated the same metric in an elliptical query (which previously failed to inherit context and triggered clarification) will now resolve successfully. All other guards remain active.

---

## 15. PASS / FAIL / CONDITIONAL PASS

**CONDITIONAL PASS** (Refinement to the metric shift guard is needed to prevent false-ambiguity regressions on repeated metrics).
