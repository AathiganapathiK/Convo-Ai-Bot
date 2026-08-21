# Phase 1D.5.B.5 — New Entity / Topic Shift vs Context Inheritance Audit Report

## 1. Executive Summary

This audit evaluates the behavior of the context-aware semantic resolution pipeline under Phase 1D.5.B.5. We analyze how the engine handles new entities, topic shifts, new dimension values, and how B.2/B.3 guards prevent incorrect inheritance.

Our findings show:
* **The System Correctly Recovers from Topic/Entity Shifts:** If a user shifts to a new value that does not match the previous turn's dimension (e.g., Turn 1: `"show sales for Coimbatore city"`, Turn 2: `"show sales for Ramraj brand"`), the system does not incorrectly force a `City` match.
* **Fallback is Safe:** The candidate filter block detects that no current candidates match the previous dimension, triggers `NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION`, and falls back to normal resolution.
* **Verdict:** **PASS**. No production code changes are required.

---

## 2. Trace and Guard Execution Flow

The sequence of guards is as follows:
1. **Explicit Label (B.1):** If the current query has an explicit label, skip B.2 with `EXPLICIT_DIMENSION_LABEL_PRESENT`.
2. **Metric Shift Guard (B.3):** If a new metric is introduced, skip B.2 with `CURRENT_METRICS_PRESENT`.
3. **Multi-Value Guard:** If multiple values are present, skip B.2 with `MULTIPLE_TARGET_VALUES`.
4. **Candidate Filtering (B.2):** Filter the current candidates against `prev_dims_set`.
   - *Sub-case A:* At least one candidate matches the previous dimension. Filter `matches` to matching candidates only (applied = True).
   - *Sub-case B:* No candidates match the previous dimension. Skip B.2 with `NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION` and keep the original candidate list.

---

## 3. Case Analysis & Diagnostic Results

| Case | Scenario | Expected / Actual Behavior | Status |
|---|---|---|---|
| **Case 1** | Prev City, Current Chennai (City/District) | legitimates inheritance -> `City` selected (`applied = True`) | **PASS** |
| **Case 2** | Prev City, Current Ramraj (Brand only) | skips B.2 -> falls back to normal resolution (`applied = False`, `reason = NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION`) | **PASS** |
| **Case 3** | Prev Brand, Current Coimbatore (City only) | skips B.2 -> falls back to normal resolution (`applied = False`, `reason = NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION`) | **PASS** |
| **Case 4** | Prev City, Current matches City + District | filters out District -> City selected (`applied = True`) | **PASS** |
| **Case 5** | Prev City, Current matches Brand only | skips B.2 -> falls back to normal resolution (`applied = False`) | **PASS** |
| **Case 6** | Prev City, Current explicit "brand Ramraj" | B.1 overrides -> `applied = False`, `reason = EXPLICIT_DIMENSION_LABEL_PRESENT` | **PASS** |
| **Case 7** | Prev Qty + City, Current Amt + Brand | B.3 blocks -> `applied = False`, `reason = CURRENT_METRICS_PRESENT` | **PASS** |
| **Case 8** | Prev Qty + City, Current same Qty + Brand | B.3 allows, B.2 candidate filter skips -> `applied = False`, `reason = NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION` | **PASS** |
| **Case 9** | 3-Turn: City -> Brand -> Coimbatore | Coimbatore matches City/District. Prev turn is Brand. B.2 skips -> falls back to City/District | **PASS** |
| **Case 10**| 3-Turn with metric changes | Metric shift in Turn 2, but Turn 3 matches Turn 2 metric -> B.2 inherits Turn 2 dimension successfully | **PASS** |

---

## 4. Key Design Evaluation

Is B.2's current rule: `"Filter current candidates to previously resolved dimensions"` sufficient?

**Yes, it is both necessary and sufficient.**
- **If the new candidate belongs to a completely different dimension:** The filter set intersection is empty, resulting in `applied = False`. The system successfully falls back to normal resolution without breaking the query.
- **If the new candidate matches both the previous dimension and another dimension:** The system correctly intersects and selects the previous dimension, resolving the ambiguity.
- **If the new candidate matches multiple previous dimensions:** The intersection preserves the ambiguity, forcing clarification instead of guessing.

---

## 5. Security & Isolation Checks
* **No SQL Filters Inherited:** The system does not carry over SQL strings, where-clauses, or parameter values.
* **Session Isolation:** History remains restricted to the active `session_id` and `employee_id`.
* **Ambiguous Turns Restricted:** Clarification turns never populate `semantic_context`, preventing polluted/unresolved states from leaking.

---

## 6. Defects Found
None.

---

## 7. Recommended Production Changes
None.

---

## 8. Final Verdict
**PASS — CURRENT CONTRACT SAFE**
The new entity and topic shift boundaries are completely safe, stable, and operate exactly as intended.
