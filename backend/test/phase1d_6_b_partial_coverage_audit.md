# Phase 1D.6.B — Partial-Coverage / Partial_Match Safety Audit

This audit evaluates whether the current `SINGLE_MATCH` behavior is semantically safe when only part of the user's meaningful query is matched, or if a new `PARTIAL_MATCH` state or coverage guard is required.

---

## 1. Executive Summary

A comprehensive read-only audit of the semantic retrieval and ambiguity classification pipeline was conducted. By running 16 critical test cases against the live index (`Chatbot` database connection), we identified a critical vulnerability: **dangerous partial matches can bypass the ambiguity gate and silently produce wrong SQL queries.**

Specifically, queries like `"children wear"` and `"women wear"` resolve to a `SINGLE_MATCH` with the value `"N--NIGHT WEARS"`. Because `len(choices) == 1`, the classifier immediately returns `SINGLE_MATCH` without verifying the token coverage. The retrieval gate allows this `PARTIAL` status to pass to the LLM, which filters by `"N--NIGHT WEARS"`, dropping the critical demographic constraints (`"children"` or `"women"`) entirely.

**Verdict:** `FAIL — PARTIAL_MATCH / PRODUCTION CHANGE REQUIRED` (A safety guard or status transition is necessary to prevent silent intent loss).

---

## 2. Current Partial-Coverage Model

The current pipeline operates as follows:
1. **Candidate Generation:** Generates value candidates from the `dimension_value_index` table.
2. **Ambiguity Classification:**
   - Calculates `actual_query_coverage` for each candidate by intersecting token singulars.
   - If **exactly 1** candidate matches, it immediately returns `ResolutionStatus.SINGLE_MATCH` regardless of coverage.
3. **Retrieval Status Calculation:**
   - Calculates `resolved_components` (metrics, dimensions, values).
   - If only 1 component (e.g. only values) is resolved, status is set to `PARTIAL`.
4. **Semantic Gate:**
   - Allows both `COMPLETE` and `PARTIAL` retrieval status to proceed to SQL generation.
   - Blocks only `INSUFFICIENT` status or `STRONG_AMBIGUITY` resolution status.
5. **Prompt Builder:** Passes raw question + resolved semantic values to the LLM.
6. **SQL Generation:** The LLM receives the unmatched tokens in the raw question but is heavily coerced to prioritize the structured `SEMANTIC CONTEXT`, leading to silent intent loss.

---

## 3. Token/Coverage Semantics

Based on the current implementation:
* **`meaningful_query_tokens`**: Normalized tokens of the user query that are not in the `STOPWORDS` list (defined in `backend/semantic/matching/stopwords.py`).
* **`matched_query_tokens`**: The subset of `meaningful_query_tokens` that successfully intersect with the candidate's singularized value tokens.
* **`unmatched_query_tokens`**: Meaningful tokens in the query that are not matched by the candidate (`meaningful_query_tokens - matched_query_tokens`).
* **`coverage`**: The ratio of `len(matched_query_tokens) / len(meaningful_query_tokens)`.
* **`candidate coverage`**: Token-level coverage calculated specifically for a single candidate.
* **`partial coverage`**: Occurs when `coverage < 1.0` (i.e. one or more meaningful query tokens are unmatched).

---

## 4. Synthetic Results

In synthetic/mock scenarios (such as `test_phase1d_5_c_integration_gaps.py`):
* A query containing `"cotton blue shirt"` resolving to candidate `"cotton pants"` results in `matched_tokens = ["cotton"]` and `unmatched_tokens = ["blue", "shirt"]`.
* Because `"blue"` and `"shirt"` are not matched, they are left to downstream SQL or LLM processing. If `"cotton pants"` is the only matching candidate, it is treated as a `SINGLE_MATCH` under the current implementation.

---

## 5. Real-Data Results

Verified against the live `Chatbot` connection (`F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`):

| # | Query | Meaningful Tokens | Matched Tokens | Unmatched Tokens | Candidates | Status | Gate Allowed |
|---|---|---|---|---|---|---|---|
| 1 | `"children wear"` | `["children", "wear"]` | `["wear"]` | `["children"]` | 1 (`"N--NIGHT WEARS"`) | `SINGLE_MATCH` | **True** (Dangerous!) |
| 2 | `"women wear"` | `["women", "wear"]` | `["wear"]` | `["women"]` | 1 (`"N--NIGHT WEARS"`) | `SINGLE_MATCH` | **True** (Dangerous!) |
| 3 | `"red shirt"` | `["red", "shirt"]` | `["shirt"]` | `["red"]` | 15 | `STRONG_AMBIGUITY` | False |
| 4 | `"blue shirt"` | `["blue", "shirt"]` | `["shirt"]` | `["blue"]` | 17 | `STRONG_AMBIGUITY` | False |
| 5 | `"formal shirt"` | `["formal", "shirt"]` | `["shirt"]` | `["formal"]` | 15 | `STRONG_AMBIGUITY` | False |
| 6 | `"cotton shirt"` | `["cotton", "shirt"]` | `["cotton", "shirt"]` | `[]` | 1 | `WEAK_AMBIGUITY` | True (Safe, 100% covered) |
| 7 | `"cotton pant"` | `["cotton", "pant"]` | `["cotton"]` | `["pant"]` | 10 | `STRONG_AMBIGUITY` | False |
| 8 | `"shirt in Chennai"` | `["shirt", "chennai"]` | `["chennai"]` | `["shirt"]` | 14 | `STRONG_AMBIGUITY` | False |
| 9 | `"shirt for Ramraj"` | `["shirt", "ramraj"]` | `["shirt", "ramraj"]` | `[]` | 3 | `STRONG_AMBIGUITY` | False |
| 10 | `"show sales for Chennai"` | `["chennai"]` | `["chennai"]` | `[]` | 2 | `STRONG_AMBIGUITY` | False |
| 11 | `"ramraj pant"` | `["ramraj", "pant"]` | `["ramraj", "pant"]` | `[]` | 2 | `STRONG_AMBIGUITY` | False |
| 12 | `"tamil nadu"` | `["tamil", "nadu"]` | `[]` | `["tamil", "nadu"]` | 0 | `NO_MATCH` | False |
| 13 | `"xyzabc"` | `["xyzabc"]` | `[]` | `["xyzabc"]` | 0 | `NO_MATCH` | False |
| 14 | `"laptop"` | `["laptop"]` | `[]` | `["laptop"]` | 0 | `NO_MATCH` | False |
| 15 | `"Chennai hospital"` | `["chennai", "hospital"]` | `["chennai"]` | `["hospital"]` | 2 | `STRONG_AMBIGUITY` | False |
| 16 | `"ramraj coimbatore"` | `["ramraj", "coimbatore"]` | `["coimbatore"]` | `["ramraj"]` | 6 | `STRONG_AMBIGUITY` | False |

---

## 6. Case-by-Case Analysis

### Category A — Harmless Modifiers (`"red shirt"`, `"blue shirt"`, `"formal shirt"`)
* **Finding:** Unmatched tokens (`"red"`, `"blue"`, `"formal"`) are descriptive color or style modifiers that do not correspond to any column in the database schema.
* **Safety:** Safe, because they either trigger `STRONG_AMBIGUITY` due to multiple candidate matches for the main noun, or if they resolve to a single candidate, they do not bypass any database filters.

### Category B — Potentially Meaningful Missing Dimensions (`"shirt in Chennai"`, `"shirt for Ramraj"`)
* **Finding:** Unmatched tokens represent other required dimensions (e.g. `"shirt"` is a Product Category dimension but failed to match a specific value).
* **Safety:** Safe under the current system because they trigger `STRONG_AMBIGUITY` (due to multiple Chennai/Ramraj candidates) or are handled by downstream join validation.

### Category C — One Token Matched, One Token Missed (`"children wear"`, `"women wear"`)
* **Finding:** Matched `"wear"` but missed `"children"`/`"women"`.
* **Safety:** **Unsafe.** Resolves to `SINGLE_MATCH` because only one candidate (`"N--NIGHT WEARS"`) contains the token `"wear"`. The critical modifier is dropped, resulting in a silent wrong-answer.

### Category D — Multi-Token Candidate / Partial Candidate (`"cotton shirt"` resolving to `"Cotton Pants"`)
* **Finding:** When a query overlaps in tokens but has distinct unmatched tokens.
* **Safety:** **Unsafe.** If `"Cotton Pants"` is the only cotton candidate, `"cotton shirt"` would resolve to it with `SINGLE_MATCH`, leading to a false semantic filter.

### Category E & F — Full Coverage & No Coverage
* **Finding:** Correctly handled. Full matches remain `SINGLE_MATCH` or `WEAK_AMBIGUITY`, while non-matching queries correctly return `NO_MATCH`.

---

## 7. Silent Wrong-Answer Risk

The silent wrong-answer risk occurs when:
1. Query: `"X Y"`
2. Candidate value: `"X"` (or a value matching only token `"X"`)
3. Database contains no other candidate matching `"X"` or `"Y"`.
4. The system outputs `SINGLE_MATCH` for `"X"`.
5. The `SemanticGate` allows the pipeline to continue.
6. The LLM ignores `"Y"` in the raw question and filters only by `"X"`.

This results in a completely incorrect SQL filter (e.g. retrieving all Night Wears instead of Children's Wears) without notifying the user or requesting clarification.

---

## 8. Downstream SQL Safety Analysis

* **Do downstream steps catch this?** No. The LLM is heavily coerced by the prompt to follow `SEMANTIC CONTEXT` and `SEMANTIC RUNTIME` rules, making it extremely likely to ignore unmatched tokens in the raw question.
* **Does it bypass RBAC/RLS/CLS?** No. Row-level security is enforced at the database/session layer, so a partial match cannot leak unauthorized data, but it still returns the wrong business results.
* **Can unmatched tokens cause arbitrary SQL filters?** No, the LLM will not invent filters unless instructed by the semantic metadata.

---

## 9. PARTIAL_MATCH Decision

**Decision: OPTION C / B (Current behavior is unsafe; a coverage guard or a new status is required).**

Specifically, we should introduce a **Coverage Guard** in `AmbiguityClassifier.classify`. If the coverage of the dominant candidate is below a safety threshold (e.g. `< 100%` or `< 50%` of meaningful query tokens), or if there are unmatched meaningful tokens, the status should be downgraded to prevent it from bypassing the `SemanticGate` as a trusted `SINGLE_MATCH`.

---

## 10. Required Fix, if any

The proposed fix involves:
1. In `AmbiguityClassifier.classify`:
   - If `len(choices) == 1`, verify that the match covers all meaningful question tokens (excluding stopwords).
   - If `actual_query_coverage < len(q_tokens)`:
     - Downgrade the status from `SINGLE_MATCH` to a new status `PARTIAL_MATCH` (or handle it as `STRONG_AMBIGUITY` / `WEAK_AMBIGUITY`).
2. In `SemanticGate.evaluate`:
   - Block `PARTIAL_MATCH` from SQL generation, or route it to clarification.

---

## 11. Required Tests

A new test suite `test_phase1d_6_b_partial_coverage_guard.py` should verify:
* **Full Coverage Match:** `"cotton shirt"` -> `SINGLE_MATCH` / `WEAK_AMBIGUITY` (Allowed)
* **Partial Match (Demographic constraint missing):** `"children wear"` -> `PARTIAL_MATCH` (Blocked)
* **Partial Match (Modifier-only):** `"Chennai hospital"` -> Blocked
* **No Match:** `"laptop"` -> `NO_MATCH` (Blocked)

---

## 12. Regression Impact

This change will strictly increase safety and will not affect fully-resolved B.1–B.6 queries. It will correctly intercept partially matched queries that would have previously generated incorrect SQL.

---

## 13. Final Verdict

**FINAL VERDICT: FAIL — PARTIAL_MATCH / PRODUCTION CHANGE REQUIRED**
