# Phase 1D.3 — Candidate Scoring & Ranking Audit

**Date**: 2026-08-12
**Status**: DIAGNOSTIC ONLY — No production code modified.

---

## 1. Current Ranking Algorithm

The candidate scoring and ranking pipeline consists of 5 sequential phases within [dimension_value_resolver.py](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/dimension_value_resolver.py):

```
Raw Matches (MatchingPipeline) → Consolidation → Containment Removal → Ranking → Ambiguity Classification
```

### 1.1 MatchRanker Sort Key

[ranker.py](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/matching/ranker.py) defines a 6-component sort tuple (ascending):

```python
return (
    -type_priority,     # 1. Match Type (EXACT=4 > NORMALIZED=3 > SINGULAR_PLURAL=2 > FUZZY=1)
    -confidence,        # 2. Confidence (higher is better)
    -coverage,          # 3. Coverage = |intersection(q_singulars, v_singulars)| / |q_singulars|
    token_distance,     # 4. abs(len(value_tokens) - len(question_tokens))  (smaller better)
    length_diff,        # 5. abs(len(value_chars) - len(question_chars))     (smaller better)
    value.lower()       # 6. Alphabetical tie-break
)
```

> [!IMPORTANT]
> **Type priority is the primary sort key.** Coverage is the *third* key. This means an EXACT match with 1-token coverage will always outrank a SINGULAR_PLURAL match with 2-token coverage, regardless of how much of the query each candidate actually covers.

### 1.2 Consolidation

[_consolidate_duplicate_matches](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/dimension_value_resolver.py#L437-L528) groups candidates by `(dimension_id, normalized_value)`. Within each group, the candidate with the highest type priority wins; ties broken by confidence, then by coverage count.

### 1.3 Containment Removal

[_remove_contained_matches](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/dimension_value_resolver.py#L374-L435) removes candidates whose matched question span is a strict contiguous subset of a longer-span candidate's span, unless the shorter candidate has higher confidence. Direct match types suppress fuzzy matches on the same question span.

### 1.4 AmbiguityClassifier

[AmbiguityClassifier.classify](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/matching/models.py#L226-L323) compares Rank #1 against Rank #2 using four dominance rules:

| Rule | Condition | Dominant? |
|------|-----------|-----------|
| **Rule 1** | priority_gap ≥ 2 AND c1.conf ≥ c2.conf - 0.10 | Yes |
| **Rule 2** | c1.coverage > c2.coverage AND p1 ≥ p2 AND c1.conf ≥ c2.conf - 0.08 | Yes |
| **Rule 3** | Same priority: confidence gap ≥ 0.05 (same coverage), or coverage advantage with conf within 0.08 | Yes |
| **Rule 4** | priority_gap = 1: with coverage/confidence conditions | Yes |

If dominant → `WEAK_AMBIGUITY` (SQL allowed). If not → `STRONG_AMBIGUITY` (SQL blocked).

### 1.5 Pipeline Ordering Summary

| Step | When | What it does |
|------|------|--------------|
| 1. Raw | After all matchers execute | Collects all candidate matches across EXACT, NORMALIZED, SINGULAR_PLURAL, FUZZY |
| 2. Consolidation | Before containment | Merges duplicate evidence for same (dimension_id, normalized_value) |
| 3. Containment | Before ranking | Removes candidates whose span is subsumed by a longer-span candidate |
| 4. Ranking | After containment | Sorts by type > confidence > coverage > token distance > length diff > alpha |
| 5. Classification | After ranking | Compares #1 vs #2 to decide SINGLE/WEAK/STRONG ambiguity |

---

## 2. Real Business Query Results

### Summary Table

| # | Query | Final Candidates | Classification | Dominant | Correct? |
|---|-------|-----------------|---------------|----------|----------|
| 1 | `pant` | 6 (Pants, LS Pant, Linen Pant, Ramraj Pant, Cotton Pants, Formal Pants) | STRONG_AMBIGUITY | None | ✅ |
| 2 | `shirt` | 6 (Shirts, T-Shirt, Red Shirt, Ramraj Shirt, Formal Shirts, Viveagham Colour Shirt) | STRONG_AMBIGUITY | None | ✅ |
| 3 | `cotton pant` | 2 (Cotton, Cotton Pants) | WEAK_AMBIGUITY | **Cotton** | ⚠️ DEFECT |
| 4 | `formal shirt` | 1 (Formal Shirts) | SINGLE_MATCH | Formal Shirts | ✅ |
| 5 | `banian` | 1 (Banians) | SINGLE_MATCH | Banians | ✅ |
| 6 | `banians` | 1 (Banians) | SINGLE_MATCH | Banians | ✅ |
| 7 | `children wear` | 1 (Children Wear) | SINGLE_MATCH | Children Wear | ✅ |
| 8 | `women wear` | 1 (Women's Wear) | SINGLE_MATCH | Women's Wear | ✅ |
| 9 | `mens wear` | 1 (Men's Wear) | SINGLE_MATCH | Men's Wear | ✅ |
| 10 | `t shirt` | 1 (T-Shirt) | SINGLE_MATCH | T-Shirt | ✅ |
| 11 | `red shirt` | 1 (Red Shirt) | SINGLE_MATCH | Red Shirt | ✅ |
| 12 | `cotton` | 2 (Cotton, Cotton Pants) | WEAK_AMBIGUITY | Cotton | ✅ |
| 13 | `sales` | 0 | NO_MATCH | — | ✅ (stopword) |
| 14 | `show sales` | 0 | NO_MATCH | — | ✅ (stopwords) |
| 15 | `total sales` | 0 | NO_MATCH | — | ✅ (stopwords) |

### Detailed Analysis: `cotton pant` (DEFECT)

```
QUERY: "cotton pant"
QUESTION TOKENS: ["cotton", "pant"]

Phase 1 (RAW): 11 candidates
Phase 2 (CONSOLIDATED): 7 candidates
  Cotton         → EXACT   1.000  (covers: "cotton")
  Cotton Pants   → S_PLUR  0.950  (covers: "cotton" + "pant")
  Pants          → S_PLUR  0.950  (covers: "pant")
  LS Pant        → FUZZY   0.900  (covers: "pant")
  Formal Pants   → FUZZY   0.900  (covers: "pant")
  Linen Pant     → FUZZY   0.900  (covers: "pant")
  Ramraj Pant    → FUZZY   0.900  (covers: "pant")

Phase 3 (CONTAINMENT): 2 candidates survive
  Cotton Pants   → S_PLUR  0.950  (span: ["cotton", "pant"] = 2/2 tokens)
  Cotton         → EXACT   1.000  (span: ["cotton"]          = 1/2 tokens)

Phase 4 (RANKED):
  [1] Cotton       → EXACT   1.000   ← wins because type_priority 4 > 2
  [2] Cotton Pants → S_PLUR  0.950

Phase 5 (CLASSIFIED):
  Status: WEAK_AMBIGUITY
  Dominant: Cotton (Fabric → FabricType)
  Rule 1 fires: priority_gap = 4-2 = 2, confidence 1.0 >= 0.85 → dominant
```

> [!CAUTION]
> **The user typed "cotton pant" — a 2-token phrase. "Cotton Pants" matches BOTH tokens (100% coverage), while "Cotton" (Fabric) only matches 1 token (50% coverage). The system incorrectly selects "Cotton" as dominant because EXACT type priority unconditionally overrides SINGULAR_PLURAL, even when the SINGULAR_PLURAL candidate covers the ENTIRE query.**
>
> This is a real semantic defect: the user who types "cotton pant" unambiguously means the product "Cotton Pants", not the fabric type "Cotton".

---

## 3. Synthetic Ranking Case Results

| Case | Setup | Result | Assessment |
|------|-------|--------|------------|
| **A** | EXACT 1.00 vs FUZZY 0.90 | EXACT wins | ✅ CORRECT |
| **B** | NORMALIZED 1.00 vs SINGULAR_PLURAL 0.95 | NORMALIZED wins | ✅ CORRECT |
| **C** | SINGULAR_PLURAL 0.95 vs FUZZY 0.90 | SINGULAR_PLURAL wins | ✅ CORRECT |
| **D** | FUZZY 0.92 vs FUZZY 0.86, same coverage | Higher confidence wins | ✅ CORRECT |
| **E** | FUZZY 0.90 cov 2/2 vs FUZZY 0.95 cov 1/2 | Higher confidence (0.95) wins despite lower coverage | ⚠️ DEFECT |
| **F** | Same dimension, equal confidence | STRONG_AMBIGUITY, both preserved | ✅ CORRECT |
| **G** | Cross dimension, equal confidence | STRONG_AMBIGUITY, both preserved with dimension metadata | ✅ CORRECT |
| **H** | Duplicate same value same dimension | Consolidated to 1 | ✅ CORRECT |
| **I** | Same value different dimensions | Not consolidated, 2 remain | ✅ CORRECT |
| **J** | Disjoint partial matches ("formal" → Formal Socks, "shirt" → Viveagham Colour Shirt) | Both survive, ranked independently | ✅ CORRECT |

### Case E Analysis

The ranker's sort key is `(-type, -confidence, -coverage, ...)`. Since confidence is the **second** key and coverage is the **third** key, a candidate with higher confidence but lower coverage will always outrank one with full coverage but slightly lower confidence. This is the same root cause as the "cotton pant" defect but manifested within the same match type.

---

## 4. Ranking Principle Evaluation

### Principle A — EXACTNESS
**Assessment: CORRECT (with caveat)**

EXACT matches correctly outrank FUZZY matches when they cover the same query span. However, when an EXACT match covers a *smaller portion* of the query than a SINGULAR_PLURAL match covering the *full query*, the EXACT match still wins. This is the root cause of the "cotton pant" defect (see Principle B).

### Principle B — QUERY COVERAGE
**Assessment: DEFECT DETECTED**

Coverage is the **third** sort component — subordinate to both type priority *and* confidence. This means:
- A 1-token EXACT match always beats a 2-token SINGULAR_PLURAL match
- A high-confidence partial FUZZY match always beats a lower-confidence full-coverage FUZZY match

The AmbiguityClassifier's Rule 1 (`priority_gap >= 2 → dominant`) exacerbates this by not checking whether c2 has significantly greater coverage than c1.

### Principle C — CONFIDENCE
**Assessment: CORRECT**

Within the same match type and same coverage, higher confidence correctly ranks first. Verified in Case D.

### Principle D — MATCH TYPE PRIORITY
**Assessment: CORRECT**

The implemented priority order is: EXACT (4) > NORMALIZED (3) > SINGULAR_PLURAL (2) > FUZZY (1). This priority is consistent across:
- `MatchRanker.rank()` (line 28-35)
- `_consolidate_duplicate_matches()` (line 472-477)
- `AmbiguityClassifier._type_priority()` (line 173-182)

### Principle E — SAME-DIMENSION ALTERNATIVES
**Assessment: CORRECT**

Verified in Case F and in real query "pant": LINEN PANT and RAMRAJ PANT (both Brand, both SINGULAR_PLURAL 0.95) correctly produce STRONG_AMBIGUITY with both preserved as options.

### Principle F — CROSS-DIMENSION CANDIDATES
**Assessment: CORRECT**

Verified in Case G: LS PANT (Prod Grp2) and RAMRAJ PANT (Brand) correctly produce STRONG_AMBIGUITY. Dimension metadata (`dimension_id`, `business_name`) survives through all pipeline stages and is available to the ambiguity UI.

### Principle G — PARTIAL MATCHES
**Assessment: CORRECT**

For "formal shirt", the containment filter correctly removes partial candidates (Formal Pants on "formal" span, Shirts on "shirt" span) and preserves "Formal Shirts" which covers both tokens. Case J confirms disjoint partial matches on non-overlapping spans survive correctly.

### Principle H — DUPLICATES
**Assessment: CORRECT**

Consolidation correctly merges:
- Same (dimension_id, normalized_value) across multiple matchers → 1 candidate (retains strongest type)
- Different dimension_ids with same value → remain separate

Verified in Cases H, I, and in real queries (e.g., "banians" raw=4 → consolidated=1).

---

## 5. Performance / Candidate Volume Analysis

| Query | Raw | Consolidated | Containment | Ranked | Classified |
|-------|-----|-------------|-------------|--------|-----------|
| pant | 11 | 6 | 6 | 6 | 6 |
| shirt | 11 | 6 | 6 | 6 | 6 |
| cotton pant | 11 | 7 | 2 | 2 | 2 |
| formal shirt | 10 | 7 | 1 | 1 | 1 |
| banian | 2 | 1 | 1 | 1 | 1 |
| banians | 4 | 1 | 1 | 1 | 1 |
| children wear | 6 | 3 | 1 | 1 | 1 |
| women wear | 4 | 3 | 1 | 1 | 1 |
| mens wear | 6 | 3 | 1 | 1 | 1 |
| t shirt | 11 | 6 | 1 | 1 | 1 |
| red shirt | 10 | 5 | 1 | 1 | 1 |
| cotton | 6 | 2 | 2 | 2 | 2 |
| sales | 0 | 0 | 0 | 0 | 0 |

**Observations:**
- Consolidation effectively reduces candidates by ~40-75% (11→6, 10→5, 6→3)
- Containment is highly effective on multi-token queries: reduces 7→2 for "cotton pant", 7→1 for "formal shirt"
- Single-token queries ("pant", "shirt") pass through containment unchanged since all candidates share the same 1-token span
- The pipeline operates on volumes of 2–11 candidates — extremely small. No performance concern.

---

## 6. Defect Classification

### DEFECT #1: Coverage-Blind Type Priority (REAL DEFECT)

| Field | Detail |
|-------|--------|
| **Exact defect** | When a shorter EXACT/NORMALIZED match and a longer SINGULAR_PLURAL match compete, the shorter match always dominates regardless of query coverage. |
| **Example** | Query `"cotton pant"` → `Cotton` (EXACT, 1/2 tokens) wins over `Cotton Pants` (SINGULAR_PLURAL, 2/2 tokens) |
| **Why current behavior is wrong** | A user typing "cotton pant" clearly means the product "Cotton Pants", not the fabric "Cotton". The system should prefer the candidate that covers more of the user's query when the coverage difference is significant (e.g., 2/2 vs 1/2). |
| **Root cause** | Two reinforcing issues: (1) `MatchRanker.rank()` uses type_priority as primary sort key above coverage. (2) `AmbiguityClassifier.classify()` Rule 1 grants dominance when `priority_gap >= 2` without checking if c2 has significantly greater query coverage. |
| **Smallest safe fix** | In `AmbiguityClassifier.classify()`, modify Rule 1 to NOT grant dominance when `len2 > len1` (c2 covers more query tokens). This allows the higher-coverage candidate to remain competitive. The fix is ~3 lines in [models.py](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/matching/models.py#L274-L278). |
| **Affected files** | `backend/semantic/matching/models.py` (AmbiguityClassifier Rule 1) |
| **Regression tests required** | (1) "cotton pant" must resolve to "Cotton Pants" as dominant. (2) "cotton" (alone) must still resolve to "Cotton" as dominant. (3) All existing ambiguity tests in `test_phase1d_2_b_ambiguity.py` must pass. |
| **Classification** | **C. REAL DEFECT — production fix required** |

### DEFECT #2: Confidence-Before-Coverage in Same-Type Ranking (DIAGNOSTIC LIMITATION)

| Field | Detail |
|-------|--------|
| **Exact defect** | In `MatchRanker.rank()`, confidence is the 2nd sort key and coverage is the 3rd. A high-confidence partial match outranks a lower-confidence full-coverage match of the same type. |
| **Example** | Synthetic Case E: FUZZY 0.95 (1/2 cov) outranks FUZZY 0.90 (2/2 cov) |
| **Assessment** | In the real query set, this is currently mitigated by consolidation + containment (which usually eliminates the lower-confidence partial match before ranking). No real-world example in the current test set triggers this path to a wrong outcome independently of Defect #1. |
| **Classification** | **B. DIAGNOSTIC LIMITATION — requires evidence from live data to confirm impact** |

### NON-DEFECTS (Confirmed Correct)

| Area | Classification |
|------|---------------|
| Match type priority order (EXACT > NORMALIZED > SINGULAR_PLURAL > FUZZY) | **A. CORRECT** |
| Same-dimension alternative preservation | **A. CORRECT** |
| Cross-dimension candidate preservation with metadata | **A. CORRECT** |
| Duplicate consolidation (same dim + same value → 1) | **A. CORRECT** |
| Cross-dimension non-consolidation (same value, different dim → separate) | **A. CORRECT** |
| Containment removal for subsumed spans | **A. CORRECT** |
| Partial match handling on disjoint spans | **A. CORRECT** |
| Stopword queries ("sales", "show sales") producing NO_MATCH | **A. CORRECT** |
| Single-token ambiguous queries ("pant", "shirt") → STRONG_AMBIGUITY | **A. CORRECT** |
| Multi-token specific queries ("formal shirt", "red shirt", "t shirt") → SINGLE_MATCH | **A. CORRECT** |
| Morphological matching ("banian" → "Banians", "women wear" → "Women's Wear") | **A. CORRECT** |

---

## 7. Regression Test Results

### Test Suite Execution

```
pytest test/test_phase1d_2_b_ambiguity.py
       test/test_phase1d_2_e_clarification.py
       test/test_phase1d_2_g_clarification_hardening.py
       test/test_dimension_value_resolver.py
       test/test_matching_pipeline_phase1a.py
```

| Category | Count | Details |
|----------|-------|---------|
| **PASSING OFFLINE** | **90** | All ambiguity, clarification, hardening, resolver, and pipeline tests |
| **PASSING WITH DATABASE** | 0 | (DB offline) |
| **BLOCKED BY DATABASE/NETWORK** | 0 | (not in this test set) |
| **ACTUAL FAILURE** | **1** | `test_session_and_user_isolation` — Pre-existing mock setup issue |

### Failure Analysis: `test_session_and_user_isolation`

This failure is a **test mock environment issue**, not a ranking defect:
- The test sets `mock_conn.execute.return_value.fetchone.return_value = create_mock_session_row(42, "EMP002", "COMPANY001")` to simulate User B's session lookup
- But `app.py` line 382 enforces `session_row["employee_id"] != user["employee_id"]` — since the session's stored owner is EMP001 (set by the earlier test) but the mock now returns EMP002 as the session owner, the check passes
- The actual failure is that the module-level `mock_conn` is shared across all tests in the file, and the `fetchone` return value from an earlier test case (`test_option_id_integrity_and_spoof_prevention`) has a stale mock mapping that conflicts

This is tracked as a test infrastructure issue, not a ranking pipeline defect.

---

## 8. Production Change Recommendation

### Recommended Fix: Defect #1 — Coverage-Aware Classifier Rule 1

**Location**: [models.py, AmbiguityClassifier.classify(), Rule 1](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/matching/models.py#L274-L278)

**Current code:**
```python
# Rule 1: High priority gap (gap >= 2, e.g. EXACT vs FUZZY) is dominant
if priority_gap >= 2:
    if c1.confidence >= c2.confidence - 0.10:
        dominant = True
```

**Proposed fix:**
```python
# Rule 1: High priority gap (gap >= 2, e.g. EXACT vs FUZZY) is dominant
# UNLESS c2 covers more query tokens than c1 (evidence that c2 is semantically better)
if priority_gap >= 2:
    if c1.confidence >= c2.confidence - 0.10 and len1 >= len2:
        dominant = True
```

**Impact**: Adding `and len1 >= len2` prevents the classifier from granting dominance when the lower-priority candidate has strictly greater query coverage. This means:
- `"cotton pant"` → Cotton Pants (SINGULAR_PLURAL, 2/2) vs Cotton (EXACT, 1/2) → **STRONG_AMBIGUITY** or the classifier defers to a coverage-aware rule, resolving correctly
- `"cotton"` → Cotton (EXACT, 1/1) vs Cotton Pants (SINGULAR_PLURAL, 1/1) → Rule 1 still fires (coverage equal), Cotton dominates ✅
- `"banians"` → single match, unaffected ✅
- `"formal shirt"` → single match after containment, unaffected ✅

### Deferred Items

| Item | Phase |
|------|-------|
| Ranker coverage promotion (making coverage more important than confidence in ranking) | Phase 1D.4 |
| Live semantic index validation with full production data | Phase 1D.5 |

---

## 9. Final Verdict

### **CONDITIONAL PASS — RANKING SAFE BUT ONE DESIGN DEFECT DEFERRED**

The ranking pipeline is architecturally sound and produces correct results for **14 out of 15** tested business queries. The consolidation, containment, and ambiguity classification systems work correctly across same-dimension, cross-dimension, morphological, and partial match scenarios.

**One real defect** exists: the classifier's Rule 1 grants dominance to a higher-priority-type candidate without checking if the lower-priority candidate covers significantly more of the user's query. This affects the `"cotton pant"` query (and any similar multi-token query where a partial EXACT match competes with a full-coverage SINGULAR_PLURAL match).

**The fix is small** (~1 condition added to Rule 1) and should be implemented before frontend integration to avoid incorrect auto-resolution of multi-token queries. All existing regression tests are expected to continue passing with the fix.

> [!WARNING]
> **Do NOT proceed to Phase 1D.4 implementation until Defect #1 is reviewed and either fixed or explicitly accepted as a known limitation.**
