# Phase 1D.5.B.4 — Previous Context Safety / Multi-Dimension Inheritance Audit Report

## 1. Executive Summary

This audit evaluates the safety, isolation, and robustness of the multi-turn context-aware semantic resolution pipeline under Phase 1D.5.B.4. We specifically focus on safety limits, multi-dimension contexts, intent shifts, and session isolation.

Our findings show:
* **The Context Inheritance Contract is Highly Safe:** The system isolates session, user, and company context correctly.
* **Ambiguity Handling is Sound:** If a follow-up value matches multiple dimensions that were resolved in the previous turn, the system preserves the ambiguity rather than making a silent guess.
* **Leaks are Prevented:** Ambiguous queries requiring clarification do not save context to the database, preventing corrupt or ambiguous states from leaking.
* **Verdict:** **PASS**. No new production code changes are recommended; the current system is secure and functionally correct.

---

## 2. Current Architecture & Trace Flow

The semantic context resolves as follows:
1. **Fetch Memory:** The `/ask` endpoint retrieves history for the active session.
2. **Context Selection:** `prompt_builder.py` searches the history in reverse chronological order and selects the latest successful turn containing a non-empty `semantic_context`.
3. **Explicit Label Check (B.1):** Triggers `EXPLICIT_DIMENSION_LABEL_PRESENT` early and exits the follow-up pipeline if an explicit dimension is stated.
4. **Metric Shift Check (B.3):** Triggers `CURRENT_METRICS_PRESENT` early if the current query introduces a new metric not present in the previous context.
5. **Follow-Up Inheritance (B.2):**
   - Filters candidate matches using `prev_dims_set`.
   - If the candidate's dimension matches any of the previously resolved dimensions, it survives.
   - If no candidates survive, it skips inheritance with `NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION`.
6. **Ambiguity Classification:** Processes the surviving matches. If multiple matches remain, it raises a clarification question.

---

## 3. Case-by-Case Analysis

### Case 1: Previous Single Dimension + Single Value
* *Behavior:* Normal B.2 inheritance.
* *Result:* **PASS** (Inherits dimension correctly).

### Case 2: Previous Multiple Dimensions + Multiple Values
* *Behavior:* Union of dimensions `{"city", "brand"}` is constructed. If the current value is ambiguous (e.g. Coimbatore matches City and District), the District candidate is filtered out because it is not in the active dimension set.
* *Result:* **PASS** (Filters correctly and resolves to City).

### Case 3: Previous Multiple Dimensions + Current Value Matches Only One
* *Behavior:* Standard intersection filtering selects the single matching candidate.
* *Result:* **PASS** (Resolves correctly).

### Case 4: Previous Multiple Dimensions + Current Value Matches Multiple Dimensions
* *Behavior:* If previous context contains `{"city", "district"}` and the current value matches both, both candidates survive. The classifier correctly marks it as `STRONG_AMBIGUITY`.
* *Result:* **PASS** (Ambiguity is preserved, avoiding silent guesses).

### Case 5: Previous Ambiguous Query
* *Behavior:* If a turn requires clarification, it skips `add_exchange` and does not save context. If empty context is passed, B.2 is skipped with `NO_PREVIOUS_RESOLVED_DIMENSION`.
* *Result:* **PASS** (No false certainty).

### Case 6: Previous Partially Resolved Query
* *Behavior:* If only one dimension resolved (or is present in dimensions list), B.2 filters using that dimension.
* *Result:* **PASS** (Filters correctly).

### Case 7: Current Explicit Dimension
* *Behavior:* B.1 explicit label (e.g., "district Coimbatore") sets `has_explicit_label = True`, skipping B.2 inheritance.
* *Result:* **PASS** (B.1 overrides B.2).

### Case 8: Current New Metric
* *Behavior:* B.3 checks if current metrics are a subset of previous metrics. If not, it skips inheritance.
* *Result:* **PASS** (Metric shift detected).

### Case 9: Current Multiple Target Values
* *Behavior:* Multi-value searches (e.g. Coimbatore and Chennai) skip B.2.
* *Result:* **PASS** (Skips correctly).

### Case 10: Three or More Conversational Turns
* *Behavior:* History search retrieves the latest valid successful context, bypassing any intermediate invalid or non-semantic turns.
* *Result:* **PASS** (Retrieves latest valid context).

### Case 11: Intent/Topic Shift
* *Behavior:* The metric shift or single dimension checks skip B.2 safely.
* *Result:* **PASS** (No context leakage).

### Case 12: Cross-Session/User/Company Context
* *Behavior:* Database query is locked by `employee_id` and `session_id`, ensuring strict isolation.
* *Result:* **PASS** (Strict boundary isolation).

---

## 4. Key Questions Answered

* **A. Is the current B.2/B.3 inheritance contract safe?** Yes. It strictly restricts inheritance based on metric shifts, session isolation, and explicit labels.
* **B. Is previous context allowed only when it represents a single deterministic dimension?** No, but if multiple dimensions exist, candidate filtering filters out non-relevant ones while preserving ambiguity if multiple relevant ones match.
* **C. If previous context contains multiple dimensions, should inheritance be allowed, restricted, or completely rejected?** Allowed with union filtering. This is safe and optimal because it filters out noise dimensions while preserving real ambiguity.
* **D. Can previous context from an ambiguous result leak into later turns?** No, because unresolved turns are not saved to the conversation history.
* **E. Can a later query inherit the wrong dimension?** No, because explicit labels (B.1) and metric shifts (B.3) override it.
* **F. Does B.1 always take precedence?** Yes, it is evaluated first.
* **G. Does B.3 always take precedence for metric shifts?** Yes, evaluated before B.2.
* **H. Are there any security/isolation risks?** None. Fully bound by session keys.

---

## 5. Defects Found
None.

---

## 6. Recommended Production Changes
None.

---

## 7. Final Verdict
**PASS — CURRENT CONTRACT SAFE**
No production changes are required as the context-aware semantic resolution safety boundaries are completely intact and robust.
