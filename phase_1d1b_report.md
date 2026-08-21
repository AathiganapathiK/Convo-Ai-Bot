# Phase 1D.1-B — Singular/Plural Matching Fix: Final Report

**Date:** August 8, 2026
**Scope:** `backend/semantic/matching/singular_plural_matcher.py` only
**Status:** Complete. All tests pass. Real-data verified.

---

## 1. Root Cause

### The failing scenario

| Query | Candidate | Before fix | After fix |
|---|---|---|---|
| `"pant"` | `"LINEN PANT"` | No match | Match |
| `"pants"` | `"LINEN PANT"` | No match | Match |
| `"pants"` | `"RAMRAJ PANT"` | No match | Match |
| `"pant"` | `"pant"` | Match | Match (unchanged) |
| `"pants"` | `"pant"` | Match | Match (unchanged) |
| `"banian"` | `"banian"` | Match | Match (unchanged) |
| `"banians"` | `"banian"` | Match | Match (unchanged) |

### Why it failed

`SingularPluralMatcher.matches_tokens()` had a single code path:

```python
@staticmethod
def matches_tokens(q_singulars: list[str], val_singulars: list[str]) -> bool:
    return SingularPluralMatcher._is_sublist(val_singulars, q_singulars)
```

`_is_sublist(sublist, main_list)` checks whether `sublist` appears as a **contiguous ordered sub-sequence** inside `main_list`.

For `"pants"` → `"LINEN PANT"`:

```
q_singulars  = ["pant"]           # "pants" singularised
val_singulars = ["linen", "pant"]  # "linen pant" tokenised and singularised

_is_sublist(["linen", "pant"], ["pant"])
  → needs a 2-token window in a 1-token list
  → impossible by construction → returns False → NO MATCH
```

For `"pant"` → `"pant"` (single-token value):

```
q_singulars  = ["pant"]
val_singulars = ["pant"]

_is_sublist(["pant"], ["pant"])
  → 1-token window at position 0 → matches → True → MATCH
```

The matcher was **asymmetric by design**: it required the entire candidate value to appear verbatim as a contiguous span in the question. A short query (`"pants"`) can never contain a longer value (`"LINEN PANT"`) as a contiguous span.

The fuzzy fallback did not reliably rescue this because `WRatio("pants", "linen pant")` scores approximately 72–74, below the 85 cutoff.

---

## 2. Exact Code Changed

**File:** `backend/semantic/matching/singular_plural_matcher.py`

**Changes: 2 methods only. No other file was modified.**

---

### Change 1 — `matches_tokens()` (the core fix)

**Before:**

```python
@staticmethod
def matches_tokens(q_singulars: list[str], val_singulars: list[str]) -> bool:
    return SingularPluralMatcher._is_sublist(val_singulars, q_singulars)
```

**After:**

```python
@staticmethod
def matches_tokens(q_singulars: list[str], val_singulars: list[str]) -> bool:
    # Primary check: all candidate tokens form a contiguous sub-sequence
    # inside the question tokens (original behaviour, preserved as-is).
    if SingularPluralMatcher._is_sublist(val_singulars, q_singulars):
        return True

    # Fallback — asymmetric query: the query has FEWER tokens than the
    # candidate value (e.g. query = ["pant"], candidate = ["linen", "pant"]).
    #
    # The guard `len(q_singulars) < len(val_singulars)` is intentional:
    #
    #   • It keeps the original contiguous-sublist requirement for cases
    #     where the query is the same length or longer than the candidate
    #     (e.g. "cotton laptop pant" must NOT match "Cotton Pants" because
    #     "laptop" breaks the contiguous sequence).
    #
    #   • It allows a short query like "pants" (→ ["pant"]) to match
    #     multi-token values like "LINEN PANT" (→ ["linen", "pant"])
    #     through the shared singular token "pant".
    #
    # No fuzzy or partial matching is applied here — only exact singular-
    # form equality is used, which keeps the fallback deterministic.
    if len(q_singulars) < len(val_singulars):
        q_singular_set = set(q_singulars)
        return any(token in q_singular_set for token in val_singulars)

    return False
```

**Logic:** Primary path unchanged. Fallback fires only when `len(query) < len(candidate)`. In that case, at least one query singular token must exactly equal at least one candidate singular token.

---

### Change 2 — `matches()` static API (consistency fix)

The standalone string-level API `matches(question, value)` was previously calling `_is_sublist()` directly, diverging from `matches_tokens()`. It now delegates to `matches_tokens()` so both code paths use identical logic.

**Before:**

```python
is_match = SingularPluralMatcher._is_sublist(val_sing, q_sing)
if is_match:
    return MatchResult(
        ...
        reason="Sublist match found after singularization and stopword removal"
    )
return MatchResult(
    ...
    reason="No sublist match found"
)
```

**After:**

```python
is_match = SingularPluralMatcher.matches_tokens(q_sing, val_sing)
if is_match:
    return MatchResult(
        ...
        reason="Morphological singular/plural match"
    )
return MatchResult(
    ...
    reason="No match found"
)
```

---

## 3. Why the Fix Is Safe

### The guard prevents false positives for longer queries

The fallback only fires when `len(q_singulars) < len(val_singulars)`. When the query is the same length as or longer than the candidate, the original sublist check is the only path. This preserves all existing behaviour for multi-word queries.

**Verification table:**

| Query singulars | Val singulars | Guard fires? | Path | Result |
|---|---|---|---|---|
| `["pant"]` | `["pant"]` | No (1 < 1 = False) | Sublist | Match (unchanged) |
| `["pant"]` | `["linen","pant"]` | Yes (1 < 2) | Intersection | Match (new) |
| `["cotton","pant"]` | `["cotton","pant"]` | No (2 < 2 = False) | Sublist | Match (unchanged) |
| `["cotton","laptop","pant"]` | `["cotton","pant"]` | No (3 < 2 = False) | Sublist | No match (unchanged, correct) |
| `["laptop"]` | `["linen","pant"]` | Yes (1 < 2) | Intersection | No match — `{"laptop"} ∩ {"linen","pant"} = {}` |

The critical safety case `"cotton laptop pant"` ↛ `"Cotton Pants"` is preserved: 3 query tokens ≥ 2 value tokens, so the fallback never fires, and the sublist check fails because `["cotton","pant"]` is not a contiguous span of `["cotton","laptop","pant"]`.

### The fallback uses exact singular equality only

No fuzzy matching, no partial matching, no WRatio. The only comparison is `token in q_singular_set` — an exact string equality on singularised tokens. This means a token like `"laptop"` cannot accidentally match `"linen"` or `"pant"`.

### The fix does not touch downstream components

- `_remove_contained_matches()` — unchanged
- `MatchRanker` — unchanged
- `FuzzyMatcher` — unchanged
- `DimensionValueResolver` — unchanged
- `SemanticResolver` — unchanged
- Pipeline orchestration — unchanged

### The fix produces more candidates, not fewer

The new fallback expands the candidate set for short queries. Downstream containment and ranking handle candidate selection. The matcher's contract — return all matching values, let downstream rank — is preserved.

### City-name false-positive safety

Values like `VEPPANTHATTAI`, `IYYAPPANTHANGAL`, and `PANTHEERANKAVU` contain the substring `"pant"` but are stored as single un-tokenized strings in the index. After normalization and tokenization they become single-element token lists (e.g. `["veppanthattai"]`). The singularised form `"veppanthattai"` ≠ `"pant"`, so the intersection check returns False. Confirmed in real-data diagnostic: zero city false positives.

---

## 4. Tests

### New test class: `TestSingularPluralMatcherPhase1B`

Added to `backend/test/test_dimension_value_resolver.py`. 26 new tests across three layers.

#### Layer 1 — Unit tests on `matches_tokens()` directly

| Test | Query singulars | Value singulars | Expected | Path |
|---|---|---|---|---|
| `test_pant_matches_pant_singulars` | `["pant"]` | `["pant"]` | True | Sublist |
| `test_pants_matches_pant_singulars` | `["pant"]` | `["pant"]` | True | Sublist |
| `test_banian_matches_banian_singulars` | `["banian"]` | `["banian"]` | True | Sublist |
| `test_banians_matches_banian_singulars` | `["banian"]` | `["banian"]` | True | Sublist |
| `test_pants_matches_linen_pant_singulars` | `["pant"]` | `["linen","pant"]` | True | Intersection (new) |
| `test_pants_matches_ramraj_pant_singulars` | `["pant"]` | `["ramraj","pant"]` | True | Intersection (new) |
| `test_unrelated_token_does_not_match_multi_token_value` | `["laptop"]` | `["linen","pant"]` | **False** | Safety guard |
| `test_cotton_laptop_pant_does_not_match_cotton_pants` | `["cotton","laptop","pant"]` | `["cotton","pant"]` | **False** | Length guard |

#### Layer 2 — Static API tests on `matches(question, value)`

| Test | Question | Value | Expected |
|---|---|---|---|
| `test_static_api_pant_matches_pant` | `"pant"` | `"pant"` | matched=True, conf=0.95 |
| `test_static_api_banians_matches_banian` | `"banians"` | `"banian"` | matched=True, conf=0.95 |
| `test_static_api_banian_matches_banian` | `"banian"` | `"banian"` | matched=True, conf=0.95 |
| `test_static_api_pants_matches_linen_pant` | `"pants"` | `"LINEN PANT"` | matched=True, conf=0.95 |
| `test_static_api_pants_matches_ramraj_pant` | `"pants"` | `"RAMRAJ PANT"` | matched=True, conf=0.95 |
| `test_static_api_laptop_does_not_match_linen_pant` | `"laptop"` | `"LINEN PANT"` | matched=False |

#### Layer 3 — Full pipeline integration via `DimensionValueResolver.resolve()`

| Test | Query | Assertion |
|---|---|---|
| `test_integration_pants_resolves_linen_pant` | `"pants"` | `LINEN PANT` in results |
| `test_integration_pants_resolves_ramraj_pant` | `"pants"` | `RAMRAJ PANT` in results |
| `test_integration_pants_all_pant_candidates_returned` | `"pants"` | `LINEN PANT`, `RAMRAJ PANT`, `FORMAL PANTS` all present (ambiguity safety) |
| `test_integration_pant_singular_still_works` | `"pant"` | `LINEN PANT`, `RAMRAJ PANT` in results |
| `test_integration_banian_resolves` | `"banian"` | `Banian` in results |
| `test_integration_banians_resolves` | `"banians"` | `Banians` in results |
| `test_integration_unrelated_token_no_match` | `"laptop"` | `LINEN PANT`, `RAMRAJ PANT` NOT in results |
| `test_integration_match_type_is_singular_plural_for_pants` | `"pants"` | match_type = `SINGULAR_PLURAL`, conf = 0.95 (not FUZZY) |

### Pre-existing test adjustments

Two pre-existing tests required assertion updates because the new fallback correctly expands the candidate set for short queries (more correct behaviour, not a regression):

| Test | Change | Reason |
|---|---|---|
| `test_singular_plural_matching` — positive loop | `assertEqual(len,1)` → `assertIn(expected_value, matched_values)` | `"Shirt"` now correctly also matches `"Formal Shirts"` via intersection; returning more valid candidates is correct |
| `test_focused_regression_phase1b` — Test A | `assertEqual(len,1); assertEqual(value,"Pants")` → `assertIn("Pants", matched_values)` | `"Pant"` now also matches `"Cotton Pants"` via intersection; both are correct |

All negative assertions (`assertNotIn`) remain strictly unchanged.

### Full test run result

```
57 passed in 1.14s
  - test_matching_pipeline_phase1a.py:  5/5  passed  (no changes)
  - test_dimension_value_resolver.py:  52/52 passed  (26 pre-existing + 26 new)
```

---

## 5. Real-Data Results

**Connection:** `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`
**Index size (pant/banian values):** 23 rows

### "pant" (was: working for single-token values only)

```
CANDIDATES BEFORE CONTAINMENT (11 pant-related):
  [SINGULAR_PLURAL] 'B--PANT'             conf=0.95  v_sing=['b', 'pant']
  [SINGULAR_PLURAL] 'DHOTI PANT'          conf=0.95  v_sing=['dhoti', 'pant']
  [SINGULAR_PLURAL] 'LINEN PANT'          conf=0.95  v_sing=['linen', 'pant']
  [SINGULAR_PLURAL] 'LINEN PANT'          conf=0.95  v_sing=['linen', 'pant']   ← (2 dimensions)
  [SINGULAR_PLURAL] 'LS PANT'             conf=0.95  v_sing=['ls', 'pant']
  [SINGULAR_PLURAL] 'MENS PYJAMA PANT'    conf=0.95  v_sing=['man', 'pyjama', 'pant']
  [SINGULAR_PLURAL] 'RAMRAJ PANT'         conf=0.95  v_sing=['ramraj', 'pant']
  [SINGULAR_PLURAL] 'RAMRAJ PANT'         conf=0.95  v_sing=['ramraj', 'pant']  ← (2 dimensions)
  [SINGULAR_PLURAL] 'UNIBRO JOGGER PANT'  conf=0.95
  [SINGULAR_PLURAL] 'UNIBRO JOGGER PANT V2' conf=0.95
  [SINGULAR_PLURAL] 'UNIBRO TRACK PANT'   conf=0.95

FINAL CANDIDATES (11):  All 11 survive containment unchanged.
```

### "pants" (was: 0 pant candidates returned — the bug)

```
CANDIDATES BEFORE CONTAINMENT (11 pant-related):
  Identical to "pant" above — "pants" singularises to "pant", same path.

FINAL CANDIDATES (11):  All 11 survive.
```

**Before this fix: "pants" returned 0 pant candidates.**

### "banian" (was: working for single-token BANIANS only)

```
CANDIDATES BEFORE CONTAINMENT (7 banian-related):
  [SINGULAR_PLURAL] '1 BANIAN'              conf=0.95  (intersection: "banian")
  [SINGULAR_PLURAL] 'ADVERTISEMENT BANIAN'  conf=0.95  (intersection: "banian")
  [SINGULAR_PLURAL] 'BANIANS'               conf=0.95  (sublist: ["banian"])
  [SINGULAR_PLURAL] 'SECONDS_ RN BANIAN'    conf=0.95  (intersection: "banian")
  [SINGULAR_PLURAL] 'SECONDS_ RNBS BANIAN'  conf=0.95  (intersection: "banian")
  [SINGULAR_PLURAL] 'SECONDS_ RNS BANIAN'   conf=0.95  (intersection: "banian")
  [SINGULAR_PLURAL] 'SECONDS_KIDS BANIAN'   conf=0.95  (intersection: "banian")

FINAL CANDIDATES (7):  All 7 survive.
```

### "banians" (was: only BANIANS matched via exact)

```
CANDIDATES BEFORE CONTAINMENT (7 banian-related):
  [EXACT]           'BANIANS'               conf=1.00
  [SINGULAR_PLURAL] '1 BANIAN'              conf=0.95
  [SINGULAR_PLURAL] 'ADVERTISEMENT BANIAN'  conf=0.95
  [SINGULAR_PLURAL] 'SECONDS_ RN BANIAN'    conf=0.95
  [SINGULAR_PLURAL] 'SECONDS_ RNBS BANIAN'  conf=0.95
  [SINGULAR_PLURAL] 'SECONDS_ RNS BANIAN'   conf=0.95
  [SINGULAR_PLURAL] 'SECONDS_KIDS BANIAN'   conf=0.95

FINAL CANDIDATES (7):  All 7 survive. BANIANS ranked first at conf=1.00.
```

### City false-positive check (safety)

`VEPPANTHATTAI`, `IYYAPPANTHANGAL`, `PANTHEERANKAVU` — all contain the substring `"pant"` in their raw string — do **not** appear in any of the four query results. They tokenise as single-element lists (`["veppanthattai"]` etc.), and the intersection check on exact singular equality returns False.

---

## 6. Remaining Risks

### Risk 1 — Increased candidate volume for short queries (by design, but needs downstream awareness)

The new fallback deliberately returns more candidates for single-token queries. For a query like `"pant"`, all 11 pant-containing product values are now candidates. This is correct semantically, but it places more responsibility on the downstream `MatchRanker` and `_remove_contained_matches()` to select the most relevant candidate when context is limited.

**Mitigation:** Both components were already designed to handle multiple candidates. The pipeline architecture explicitly separates matching (return all valid candidates) from ranking (select the best). No additional risk introduced.

### Risk 2 — Very common single-character or two-character tokens

If a single-character token like `"s"` or `"a"` appears in the question, the intersection fallback would match any multi-token value containing `"s"` or `"a"` as a standalone token after singularisation. In practice this is unlikely because: (a) single-character tokens are typically stopwords or noise; (b) real product/dimension values rarely contain standalone single-character meaningful tokens except for known abbreviations like `"v2"`.

**Mitigation:** The stopword list already removes common short tokens. If this becomes an issue in practice, a `len(token) >= 2` guard can be added to the intersection check inside `matches_tokens()` without changing any other behaviour.

### Risk 3 — `matches()` static API now returns more matches (consistent with `matches_tokens()`)

The standalone `SingularPluralMatcher.matches(question, value)` string API previously used `_is_sublist()` directly. It now delegates to `matches_tokens()`. Any caller using this API for "does this specific question match this specific value?" will now receive `matched=True` for cases that previously returned `matched=False`. This is correct behaviour, but callers that used the old return value as a hard gate should be reviewed.

**Current callers:** Only `test_typed_match_result` in the test suite calls `matches()` directly — confirmed passing. No production code outside the test suite calls `matches()` directly (all production paths go through `match(context)` on the pipeline).

### Risk 4 — `BAHAMA LONG PANT(W)` not matched

The value `BAHAMA LONG PANT(W)` contains parentheses. The normaliser converts `(` and `)` to spaces (via the delimiter regex `[-_/.]`... wait — parentheses are NOT in the delimiter regex). The normalized form is `"bahama long pant(w)"`. After tokenisation: `["bahama", "long", "pant(w)"]`. The token `"pant(w)"` after `_to_singular()` → `"pant(w)"` (ends in `")"`, not `"s"`). So `"pant(w)" ≠ "pant"` — this value is unreachable by the current normaliser for any `"pant"` query.

This is a pre-existing issue unrelated to Phase 1D.1-B and is not introduced by this fix. It would require extending the normaliser to strip trailing punctuation from tokens, which is a separate change.

---

## Files Modified

| File | Change |
|---|---|
| `backend/semantic/matching/singular_plural_matcher.py` | `matches_tokens()`: added asymmetric-query intersection fallback. `matches()`: delegate to `matches_tokens()` for consistency. |
| `backend/test/test_dimension_value_resolver.py` | Added `TestSingularPluralMatcherPhase1B` (26 tests). Updated 2 pre-existing test assertions to `assertIn` (correct expansion of behaviour). Added `setUp`/`tearDown` cache clearing. |

No other production files were modified.
