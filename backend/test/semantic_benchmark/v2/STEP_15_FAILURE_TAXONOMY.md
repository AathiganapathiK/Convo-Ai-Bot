# Step 15 — Failure Taxonomy

Forensic analysis of the 92 cases Step 16 classified as verdict **A** (genuine
software defect). Read-only: no production code, configuration, database or
Step 16 artifact was modified.

---

## 1. Executive Summary

The 92 failures reduce to **eight shared root causes**. Three of them account for
54 cases (59%).

The dominant finding is that **the resolver has no model of evidence strength**.
Confidence is a constant per matching method, not a measurement, so wherever two
candidates match by the same method the system cannot prefer either — and
wherever a question contains a word the value matcher did not consume, a
43-entry hand-maintained stopword list decides whether the whole answer is
downgraded. Both mechanisms are lexical bookkeeping standing in for a real
scoring model.

The second finding is that **synonym text is trusted as fact**. `C Y` carries the
synonyms `amount`, `revenue`, `sales` and `hand typed`; `Prod Grp4` carries
`category`. Generic words attached to specific columns score identically to
precise ones (9000), so a Sales-table year column wins questions about order
amounts, and a product-variant column attaches itself to every question
containing the word "category".

Two further findings deserve emphasis:

- **No consumer of `NO_MATCH` exists.** `ResolutionStatus.NO_MATCH` is produced
  in `matching/models.py` and read by nothing in `semantic/`, `ai/` or
  `app.py`. All 10 adversarial cases fail for this single reason.
- **5 of the 92 are not defects at all.** Their recorded diagnostic run predates
  the authorised `pendamt → P A M T` correction, and their actual output already
  matches the corrected expectation. They are classified
  `UNRESOLVED — REQUIRES INVESTIGATION` rather than assigned a cause the
  evidence does not support.

---

## 2. Scope and Method

**In scope:** the 92 verdict-A cases only. No B (30), C (0), D (4), E (26) or
VALID (42) case was analysed or reclassified.

**Method.** For each case: read the question, the Step 16 expectation and the
recorded actual result; identify the first divergence in pipeline order; trace
that divergence to a call site in live code; separate the symptom from the
mechanism; then cluster by mechanism rather than by symptom.

**Evidence sources.** Live code under `backend/semantic/` and `backend/ai/`; the
live configuration on connection `F82C2F8D…`; the Step 16 v2 datasets; and
direct read-only execution of the resolver on individual questions to observe
candidate scoring.

**Important scope limit.** `run_retrieval_benchmark.py` calls
`SemanticResolver.resolve()` and nothing else. `SemanticPlanBuilder`,
`prompt_builder`, the SQL guard and `/ask` are **not exercised** by any of these
92 cases. No conclusion about them can be drawn from this evidence, and none is
drawn below.

---

## 3. Current Runtime Pipeline (as exercised by the benchmark)

```
question
  └─ SemanticResolver.resolve()                    semantic_resolver.py:315
       ├─ _fetch_active_metadata()                 :167  metrics + dimensions,
       │                                                 Gate 2 exclusions applied
       ├─ _generate_candidates()                   :233  lexical scoring per row
       │    └─ _get_match_info()                   :65   7 priority tiers
       ├─ _remove_overlaps()                       :286  span-greedy selection
       ├─ SAME_TABLE_BONUS second pass             :333  dimensions only, +0.35
       ├─ snapshot period rebinding                :477  config-driven (Gate 3)
       ├─ DimensionValueResolver.resolve_matches() dimension_value_resolver.py:156
       │    └─ MatchingPipeline: Exact → Normalized → SingularPlural → Fuzzy
       │         └─ AmbiguityClassifier            matching/models.py:240-398
       └─ retrieval status                         :629  count of non-empty buckets
```

Component status, verified by call site rather than by file existence:

| Component | Status |
|---|---|
| `SemanticResolver` | **live** — sole entry point for the benchmark |
| `DimensionValueResolver` | **live** — called from the resolver |
| `AmbiguityClassifier` | **live** — sets the status the benchmark compares |
| `runtime_config_filter` | **live** — Gate 3 P0, exclusions honoured |
| snapshot rebinding | **live** — config-driven since Gate 3 |
| `SemanticPlanBuilder` | live in `/ask`, **not on the benchmark path** |
| `prompt_builder` | live in `/ask`, **not on the benchmark path** |
| SQL guard | live in `/ask` but in **shadow** mode; not on this path |
| `ResolutionStatus.NO_MATCH` | **produced, never consumed** |

---

## 4. First-Failing-Stage Definition

The earliest stage whose output diverges from the expectation, in pipeline
order: `METRIC → DIMENSION → VALUE → AMBIGUITY → RETRIEVAL_STATUS`. A later
divergence is never counted as primary when an earlier one exists.

For nine cases the recorded `wrong metric` code was discounted first, because it
compared the pre-correction `pendamt` expectation against an actual that already
equals the corrected `P A M T`. Discounting it moves three cases to `AMBIGUITY`,
one to `DIMENSION`, and leaves five with no remaining divergence.

| Stage | Cases |
|---|---:|
| AMBIGUITY | 32 |
| METRIC | 22 |
| DIMENSION | 19 |
| VALUE | 9 |
| RETRIEVAL_STATUS | 5 |
| NONE (stale diagnostic) | 5 |
| **Total** | **92** |

---

## 5. Taxonomy Overview

| ID | Root cause | Cases |
|---|---|---:|
| RC-02 | Ambiguity status overridden by an unmatched-token heuristic | 23 |
| RC-03 | Synonym specificity is not weighted | 21 |
| RC-01 | `NO_MATCH` is produced but never enforced | 10 |
| RC-04 | Name matcher has no morphology | 10 |
| RC-06 | Value matcher accepts weak candidates | 9 |
| RC-07 | No confidence model — dominance rules are inert | 9 |
| RC-05 | Retrieval status is a bucket count | 5 |
| RC-08 | **UNRESOLVED — stale diagnostic evidence** | 5 |
| | **Total** | **92** |

---

## 6. Detailed Root Causes

### RC-01 — `NO_MATCH` is produced but never enforced — 10 cases

**Mechanism.** `ResolutionStatus.NO_MATCH` is returned at
`matching/models.py:242` when no value matched. A repository-wide search finds
**no consumer** of that status in `semantic/`, `ai/` or `app.py`. Nothing gates
the answer on it. So "Show sales for xyzabc" resolves the metric `C Y` from the
word "sales", finds no value for "xyzabc", and reports a metric anyway.

`retrieval_status` does not rescue it either — see RC-05.

**Evidence.** `semantic_resolver.py:629-661`; `matching/models.py:242`; absence
of any read site.

**Why this and not "wrong metric".** The metric resolution is correct in
isolation — the user did say "sales". The defect is that an unresolved *entity*
does not suppress the partial answer.

**Cases (10).** `E1-180 … E1-189` — the entire `NO_MATCH_ADVERSARIAL` category.

**Confidence in diagnosis: HIGH.** Single mechanism, no consumer exists,
whole category affected uniformly.

---

### RC-02 — Ambiguity status overridden by an unmatched-token heuristic — 23 cases

**Mechanism.** After the ambiguity status is decided, `matching/models.py:332-391`
re-examines the question: every query token not consumed by the *value* matcher
is "dangerous" unless it appears in `STOPWORDS` or in the candidate dimension's
own metadata. One dangerous token forces `PARTIAL_MATCH`, discarding a
correctly-computed `WEAK_AMBIGUITY`.

`STOPWORDS` holds **43 entries**. It contains `sales`, `quantity`, `qty`,
`show`, `for`, `in` — but not `total`, `now`, `instead`, `children`, `wear`.

Verified directly:

```
"Show sales for Chennai city"        → WEAK_AMBIGUITY   (passes)
"Total sales for Chennai city"       → PARTIAL_MATCH    ("total" unmatched)
"Now show Qty for Chennai city"      → PARTIAL_MATCH    ("now" unmatched)
"Show sales for Chennai city instead"→ PARTIAL_MATCH    ("instead" unmatched)
```

The classifier has no shared coverage state with metric or dimension resolution,
so it cannot know that "sales" was legitimately consumed elsewhere. A fixed
keyword list is doing the job of token-coverage accounting.

**Evidence.** `matching/models.py:373-391`; `matching/stopwords.py` (43 entries).

**Cases (23).** `E1-032, E1-033, E1-046, E1-047, E1-048, E1-052, E1-053, E1-054,
E1-110, E1-111, E1-112, E1-137, E1-138, E1-139, E1-140, E1-141, E1-142, E1-153,
E1-165, E1-169, E1-171, E1-174, E1-175`

**Confidence: HIGH.** Reproduced by adding or removing a single word.

---

### RC-03 — Synonym specificity is not weighted — 21 cases

**Mechanism.** Priority 6 of `_get_match_info()` awards a flat **9000** to any
synonym hit, regardless of how generic the synonym is or how specific the column
is. Live configuration then supplies generic words to specific columns:

```
C Y       (QB_MDJMD_SALES_5YRS_SUMMARY.CY)
          synonyms: Current year sales, 2026, hand typed, sales, revenue,
                    amount, current year, CY, C Y
Prod Grp4 (QB_MDJMD_SALES_5YRS_SUMMARY.ProdGrp4)
          synonyms: product group, category, prod grp, group
```

Two distinct manifestations, one cause:

*Under-return.* "Show amount" scores `C Y` and `Amt` **identically** (9000,
match length 6) on the same span. `_remove_overlaps()` is span-greedy, so
exactly one survives; the sort key is identical for both, Python's sort is
stable, and the winner is therefore whichever row the database returned first.
`metric_query` has **no `ORDER BY`** (`semantic_resolver.py:180-192`), so the
outcome is not deterministic across environments.

*Over-return.* "Show sales for category Marketing" matches `Category` on the
span "marketing" and `Prod Grp4` on the span "category". The spans do not
overlap, so **both** are returned where one was expected.

**Evidence.** `semantic_resolver.py:124-130` (flat 9000);
`semantic_resolver.py:286-312` (span-greedy, stable sort);
`semantic_resolver.py:180-192` (no `ORDER BY`); live synonym rows above.

**Cases (21).** `E1-011, E1-012, E1-015, E1-016, E1-017, E1-018, E1-019, E1-034,
E1-035, E1-043, E1-045, E1-059, E1-061, E1-069, E1-070, E1-071, E1-074, E1-084,
E1-164, E1-167, E1-179`

**Confidence: HIGH** for the mechanism. **MEDIUM** for the split between code
and configuration: better synonyms would fix most of these cases without a code
change, but the flat score and unstable tie-break remain latent defects.

---

### RC-04 — Name matcher has no morphology — 10 cases

**Mechanism.** `_find_phrase_spans()` and `_find_whole_word_match_spans()` match
literal tokens. A plural therefore falls out of the exact-phrase tier into the
weakest tier:

```
"Show sales for VT division"   → Division  score 30000  (Business Name, exact phrase)
"Show sales for VT divisions"  → Division  score  8000  (Stem Overlap, last resort)
```

At 8000 the dimension loses to competing candidates or is dropped, so
`dimensions` comes back empty. A `SingularPluralMatcher` **does** exist and is
used for dimension *values* (`dimension_value_resolver.py:93-98`) — the
morphology handling is present on one path and absent on the other.

**Evidence.** `semantic_resolver.py:24-45, 96-122, 132-155`;
`matching/singular_plural_matcher.py` (used only for values).

**Cases (10).** `E1-126 … E1-135` — the entire `SINGULAR_PLURAL` dimension set.

**Confidence: HIGH.** Score difference reproduced directly.

---

### RC-05 — Retrieval status is a bucket count — 5 cases

**Mechanism.** `semantic_resolver.py:629-661` counts how many of
{metric, dimension, value} are non-empty: 0 → `INSUFFICIENT`, 1 → `PARTIAL`,
2+ → `COMPLETE`. Nothing about match quality, coverage or confidence enters.

So "Show sales for ramrj brand" resolves a metric plus a fuzzy value, scores two
non-empty buckets, and reports `COMPLETE` — while the benchmark expects
`PARTIAL` because the brand was never really understood. A weak fuzzy hit counts
exactly as much as an exact one.

**Evidence.** `semantic_resolver.py:629-661`.

**Cases (5).** `E1-117, E1-143, E1-144, E1-151, E1-193`

**Confidence: HIGH.**

---

### RC-06 — Value matcher accepts weak candidates — 9 cases

**Mechanism.** `FuzzyMatcher` admits anything at or above
`MatchSettings.FUZZY_SCORE_CUTOFF = 85` and assigns `confidence = score/100`
(`matching/fuzzy_matcher.py:89`). There is no minimum-evidence rule, no
ambiguity margin, and no check that the matched span is a meaningful share of
the term. Observed results:

```
"Show sales for franchis category" → matched RANCHI   (a city, not a category)
"Show sales for export market"     → matched KR MARKET (expected MONDAY MARKET)
"Show sales for Chennai city …"    → matched ELECTRONIC CITY alongside CHENNAI
```

`RANCHI` is reachable from `franchis` because fuzzy scoring is computed on the
raw token with no requirement that the match respect word boundaries or cover a
minimum fraction of the query term.

**Evidence.** `matching/fuzzy_matcher.py:80-95`; `matching/confidence.py:8`.

**Cases (9).** `E1-020, E1-021, E1-044, E1-062, E1-078, E1-079, E1-115, E1-146,
E1-147`

**Confidence: MEDIUM-HIGH.** Mechanism is clear; for `E1-020/E1-021` the
divergence is a count mismatch on a list of due-slab values whose exact origin
was not traced to a single line.

---

### RC-07 — No confidence model, so dominance rules are inert — 9 cases

**Mechanism.** `MatchConfidence` is a table of constants
(`matching/confidence.py`): `EXACT = 1.00`, `NORMALIZED = 0.98`,
`SINGULAR_PLURAL = 0.95`, `FUZZY = score/100`. It encodes *which matcher fired*,
not how strong the evidence is.

The dominance cascade at `matching/models.py:281-330` is four rules built on
**eight hand-tuned thresholds** (`0.10, 0.08, 0.05, −0.08, 0.10, −0.08, −0.02`),
all comparing that constant. When two candidates match by the same method with
equal token coverage, `conf_gap` is exactly `0.00`, Rule 3 demands `>= 0.05`,
and no rule can ever fire:

```python
elif p1 == p2:
    if len1 == len2:
        if conf_gap >= 0.05:      # two EXACT matches → gap is always 0.00
            dominant = True
```

The result is `STRONG_AMBIGUITY` where the benchmark expects `WEAK_AMBIGUITY`
with a dominant candidate. Nothing else can break the tie — not row counts, not
`is_confirmed`, not table affinity, not the Gate 2 configuration state.

**Evidence.** `matching/confidence.py:1-9`; `matching/models.py:281-330`.

**Cases (9).** `E1-036, E1-037, E1-038, E1-063, E1-101, E1-104, E1-125, E1-145,
E1-170`

**Confidence: HIGH.**

---

### RC-08 — UNRESOLVED, stale diagnostic evidence — 5 cases

**What is missing.** The recorded diagnostic run predates the authorised
`pendamt → P A M T` correction. For these five the only recorded failure was
`wrong metric`, comparing the old `['pendamt']` expectation against an actual of
`['p a m t']` — which *matches* the corrected expectation. No other failure code
is present.

On the available evidence they would now pass, so no software root cause can be
asserted. They are **not** assigned a cause to make the numbers tidy.

**What would resolve it.** Re-running the benchmark against the Step 16 v2
expectations — which is Step 14's job and deliberately out of scope here.

**Cases (5).** `E1-013, E1-014, E1-086, E1-090, E1-109`

**Confidence: HIGH that the evidence is insufficient.**

---

## 7. Root Cause Count Table

| ID | Root cause | Primary | Also appears as secondary |
|---|---|---:|---:|
| RC-01 | `NO_MATCH` not enforced | 10 | 0 |
| RC-02 | Ambiguity overridden by unmatched-token heuristic | 23 | 9 |
| RC-03 | Synonym specificity not weighted | 21 | 0 |
| RC-04 | Name matcher has no morphology | 10 | 0 |
| RC-05 | Retrieval status is a bucket count | 5 | 10 |
| RC-06 | Value matcher accepts weak candidates | 9 | 5 |
| RC-07 | No confidence model | 9 | 9 |
| RC-08 | UNRESOLVED — stale diagnostic | 5 | 0 |
| RC-09 | Span-greedy selection / unstable tie-break | 0 | 19 |
| | **Primary total** | **92** | |

RC-09 never appears as a primary cause: wherever it contributes, an earlier
synonym or morphology defect already determined the outcome. It is recorded
because it is a real latent defect — the unordered `SELECT` makes one class of
outcome environment-dependent.

---

## 8. Case IDs per Root Cause

See §6. Machine-readable in `step15_root_cause_analysis.json`, one record per
case with `primary_root_cause`, `secondary_contributing_factors`,
`first_failing_stage`, expected and actual.

---

## 9. Primary vs Secondary Cause Analysis

| Primary | Secondary | Cases |
|---|---|---:|
| RC-01 | RC-05 — bucket counting lets the partial answer through | 10 |
| RC-03 | RC-09 — span-greedy selection decides which survives | 19 |
| RC-06 | RC-07 — no confidence model to reject the weak candidate | 9 |
| RC-07 | RC-02 — the token heuristic then re-downgrades the status | 9 |
| RC-05 | RC-06 — the weak value that inflated the bucket count | 5 |

RC-02, RC-04 and RC-08 carry no secondary factor: each fully explains its cases.

---

## 10. Production Code Evidence

| File | Lines | Root causes |
|---|---|---|
| `semantic/semantic_resolver.py` | 65-162 (`_get_match_info`) | RC-03, RC-04 |
| | 180-192 (`metric_query`, no `ORDER BY`) | RC-03, RC-09 |
| | 286-312 (`_remove_overlaps`) | RC-03, RC-09 |
| | 629-661 (retrieval status) | RC-05, RC-01 |
| `semantic/matching/models.py` | 242 (`NO_MATCH` produced) | RC-01 |
| | 281-330 (dominance cascade) | RC-07 |
| | 332-391 (unmatched-token override) | RC-02 |
| `semantic/matching/confidence.py` | 1-9 (constants) | RC-07, RC-06 |
| `semantic/matching/stopwords.py` | whole file (43 entries) | RC-02 |
| `semantic/matching/fuzzy_matcher.py` | 80-95 | RC-06 |
| `semantic/dimension_value_resolver.py` | 93-98 (matcher order) | RC-04 (contrast) |

No file was modified.

---

## 11. Existing Gate 2 / Gate 3 Coverage

| Root cause | Already addressed? |
|---|---|
| RC-01 | No. Audit priority 🔴1; owned by Step 21 |
| RC-02 | No |
| RC-03 | **Partly.** Gate 3 P0 made exclusions effective, which removes excluded rows from the candidate pool. It does not weight synonyms. The `C Y`/`Prod Grp4` synonyms are live configuration and remain |
| RC-04 | No |
| RC-05 | No |
| RC-06 | No |
| RC-07 | No. `is_confirmed` was deliberately left unused by P0 precisely so it could feed a confidence model later |
| RC-08 | Resolved by Step 16's correction; needs Step 14 to re-measure |

Gate 3 P0/P1 fixed configuration *enforcement*. None of the eight causes is a
regression from that work.

---

## 12. Recommended Future Owner

| Root cause | Owner | Note |
|---|---|---|
| RC-01 | **Step 21** | No-match protection |
| RC-02 | **Step 21**, with Step 17 | Needs shared token-coverage state across metric, dimension and value resolution |
| RC-03 | **Step 19**, plus a Gate 2 configuration task | Code fix is scoring; the generic synonyms are an admin correction |
| RC-04 | **Step 19** | Linguistic variation |
| RC-05 | **Step 21** | Status must derive from coverage and confidence |
| RC-06 | **Step 21**, with Step 19 | Thresholds, margins, minimum evidence |
| RC-07 | **Step 21** | The confidence model everything else depends on |
| RC-08 | **Step 14** | Re-measure |
| RC-09 | **Step 17** | Slot-aware selection replaces span-greedy |

**RC-03 needs an owner that does not exist.** Its configuration half — auditing
synonyms for over-generic terms — is neither a resolver change nor a benchmark
change. It belongs to the Gate 2 admin track and should be scheduled explicitly
rather than folded into Step 19.

**Dependency worth stating:** RC-02, RC-05 and RC-06 all consume a confidence
signal that does not exist. **RC-07 should be built first**, or the other three
will be rebuilt afterwards.

---

## 13. Unresolved Cases

`E1-013, E1-014, E1-086, E1-090, E1-109` — RC-08. Diagnostic evidence predates
the P A M T correction; their recorded failure is an artefact. Resolution
requires a Step 14 re-run against v2 expectations.

---

## 14. Cross-cutting Root Causes

**Absence of an evidence model** underlies RC-02, RC-05, RC-06 and RC-07 —
54 cases, 59%. Each substitutes a different proxy: a stopword list, a bucket
count, a fixed fuzzy cutoff, a table of per-matcher constants. Fixing them
independently would produce four more proxies.

**Lexical text trusted as fact** underlies RC-03 and RC-04 — 31 cases. Synonyms
are matched as literal strings at a flat score, and names are matched without
morphology.

Together these two account for **85 of 92**.

---

## 15. Hardcoded Assumption Findings

The Gate 3 audit recorded remaining hardcoded assumptions. Their status against
these 92 cases:

| Location | On the failing path? | Explains any A case? |
|---|---|---|
| `prompt_builder.py:339` — hardcoded snapshot column set | **No** — not called by the benchmark | No |
| `prompt_builder.py:234/241` — `"CY"`/`"PY"` fallbacks | **No** | No |
| `prompt_builder.py:673/968`, `semantic_plan_builder.py:281` — `business_name == "Sales"` | **No** | No |
| `semantic_resolver.py:477-560` — snapshot rebinding | **Yes**, on the path | **No** — made config-driven in Gate 3; only one `TEMPORAL_QUESTIONS` case is in the A set and it fails at retrieval status (RC-05) |

**No A case is explained by a hardcoded business assumption.** They are real
technical debt, but the benchmark does not exercise them, because it calls only
`SemanticResolver.resolve()`. This is a **gap in benchmark coverage**, not
evidence of correctness. `prompt_builder` and `SemanticPlanBuilder` are
currently unmeasured.

---

## 16. Multi-user / State Findings

**No evidence of a state defect in these 92 cases, and none is claimed.**

The runner replays multi-turn cases in-process, constructing
`previous_semantic_context` explicitly and passing it as an argument
(`run_retrieval_benchmark.py:130-170`). No session id, user id, company id or
cached conversation state participates. Cross-user leakage, stale clarification
state and connection leakage are therefore **not represented in this benchmark**
and cannot be assessed from it.

The follow-up and topic-shift cases that do fail (`E1-165, E1-169, E1-171,
E1-174, E1-175, E1-179`) fail for RC-02 and RC-03 — the extra word "now" or
"instead" trips the token heuristic — not for context handling. Their inherited
context was applied correctly.

The audit's separate finding that live follow-up context takes the most recent
turn with values and has no topic-shift detection still stands; it is simply not
evidenced here.

---

## 17. Final Reconciliation of All 92 A Cases

| Root cause | Cases |
|---|---:|
| RC-02 | 23 |
| RC-03 | 21 |
| RC-01 | 10 |
| RC-04 | 10 |
| RC-06 | 9 |
| RC-07 | 9 |
| RC-05 | 5 |
| RC-08 (unresolved) | 5 |
| **Total** | **92** |

Verified programmatically: 92 unique case ids, each with exactly one primary
root cause, summing to 92. No B, C, D, E or VALID case is included.

---

## 18. Conclusions

1. **Eight root causes explain 92 failures**, and three explain 54 of them.
2. **The highest-leverage fix is a real confidence model (RC-07).** Four causes
   depend on a signal that does not exist; building them in any other order
   means building them twice.
3. **`NO_MATCH` needs a consumer, not an implementation.** The status already
   exists and is correctly produced; nothing reads it.
4. **Some of this is configuration, not code.** `C Y` claiming `amount`,
   `revenue`, `sales` and `hand typed`, and `Prod Grp4` claiming `category`,
   drive a large share of RC-03. That work belongs to the Gate 2 admin track and
   has no owner in the current plan.
5. **One outcome is environment-dependent.** With no `ORDER BY` on the metric
   query and a stable sort over identical keys, which of two tied metrics
   survives depends on database row order.
6. **The benchmark measures one component.** `SemanticPlanBuilder`,
   `prompt_builder` and the SQL guard are not exercised, so the hardcoded
   assumptions there are unmeasured — a coverage gap Step 14 should state
   openly rather than a clean bill of health.
7. **Five cases are not defects.** Recording them as `UNRESOLVED` keeps the
   taxonomy honest at the cost of a tidy total.
