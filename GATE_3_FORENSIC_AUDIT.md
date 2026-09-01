# GATE 3 — FORENSIC AUDIT AND FINAL ARCHITECTURE DESIGN

**Scope:** Steps 14–21. Audit and design only. No production code was modified.
**Method:** End-to-end runtime trace, read-only reproduction of matcher behaviour, and
inspection of the committed benchmark results. Every claim below cites a file and line.
**Date of audit:** 2026-08-31. Audited commit: `da829bf` (Gate 2 complete, working tree clean).

---

## 1. EXECUTIVE VERDICT

The system works by a route that is different from the one the architecture documents
describe. Three findings dominate everything else.

**Finding A — Gate 2's configuration is not read at query time.**
Gate 2 built an admin semantic layer that records which columns are excluded, which are
confirmed, and which dimensions are legitimate groupings. The runtime read path never
consults any of it. `is_excluded`, `is_confirmed`, and `dimension_role` appear **zero
times** in `semantic_resolver.py`, `dimension_value_resolver.py`, `semantic_service.py`,
and `dimension_value_index_builder.py`. All three read paths filter on `is_active = 1`
only ([semantic_resolver.py:182,195](backend/semantic/semantic_resolver.py#L182),
[dimension_value_resolver.py:553](backend/semantic/dimension_value_resolver.py#L553),
[dimension_value_index_builder.py:52](backend/semantic/dimension_value_index_builder.py#L52)).

An administrator who excludes a column in the Semantic Control Center changes nothing
about what the chatbot does. Gate 2 Step 13 set `dimension_role = GROUPING` on Party and
Regional Manager ([seed_semantic_config.py:205](backend/tools/seed_semantic_config.py#L205));
that field is never read. This is the single highest-value defect in the system, and it is
cheap to fix.

**Finding B — the SemanticPlan is advisory, not authoritative.**
SQL is written by an LLM from a text prompt
([ai_service.py:96](backend/ai/ai_service.py#L96)). The `SemanticPlan` is built
*after* the prompt context is assembled, is serialised into that same prompt, and is
otherwise used only by the Gate 5 SQL Guard, which defaults to shadow mode
([app.py:838](backend/app.py#L838)). Nothing forces the generated SQL to use the columns
the plan resolved. The plan is a suggestion the model may ignore.

**Finding C — "confidence" is not a measure of correctness.**
`retrieval.confidence` is a count of which *slot types* got filled — 0.35 for any metric,
0.25 for any dimension, 0.20 for any value, 0.20 for any table
([semantic_resolver.py:593-618](backend/semantic/semantic_resolver.py#L593)). It is
completely independent of match quality. A perfect exact match and a marginal fuzzy match
on a typo produce the identical number. Worse, `SemanticGate.evaluate` reads `confidence`
into a variable and **never compares it to any threshold**
([semantic_gate.py:19](backend/semantic/semantic_gate.py#L19)) — the decision is made
purely on the string `status`. There is no confidence gate anywhere in the system, despite
the field being logged as if there were.

**Benchmark reality (committed results, 190 scored cases, 26.84% pass):**

| Category | Pass rate | Gate 3 step |
|---|---|---|
| MULTI_DIMENSION | **0.0%** (0/18) | Step 17 |
| FOLLOW_UP | **0.0%** (0/10) | Step 18 |
| ENTITY_TOPIC_SHIFT | **0.0%** (0/8) | Step 18 |
| NO_MATCH_ADVERSARIAL | **0.0%** (0/10) | Step 21 |
| TEMPORAL_QUESTIONS | **0.0%** (0/10) | Step 14/16 |
| SINGULAR_PLURAL | 5.6% (1/18) | Step 19 |
| METRIC_SHIFT | 12.5% (1/8) | Step 18 |
| EXPLICIT_DIMENSION | 16.7% (3/18) | Step 17 |
| TYPO_FUZZY | 27.8% (5/18) | Step 19 |
| METRIC_DIMENSION_VALUE | 36.4% (8/22) | Step 17 |
| SIMPLE_METRIC | 50.0% (9/18) | Step 14 |
| PARTIAL_COVERAGE | 55.6% (10/18) | Step 21 |
| AMBIGUOUS_VALUES | 77.8% (14/18) | Step 21 |

**The 26.84% number is not trustworthy as a measure of the software.** 116 of the ~194
cases expect the metric literally named `"C Y"` — a pre-Gate-2 auto-discovered name. Gate 2
renamed these. The runner compares metric business names as sorted lists and fails the
whole case on any mismatch ([run_retrieval_benchmark.py:243](backend/test/semantic_benchmark/run_retrieval_benchmark.py#L243)).
A single stale expectation therefore fails cases in *every* category simultaneously. **Step 16
must run before Step 14**, or the re-baseline measures the benchmark rather than the system.

**Recommended architecture:** Option C — deterministic-first with a narrow, validated LLM
escalation tier. Not LLM-first. Reasons in §19. The single most important structural change
is to make the SemanticPlan **authoritative** (compile SQL from it, or enforce the guard),
because no amount of resolver accuracy matters while the model may disregard the plan.

---

## 2. CURRENT RUNTIME ARCHITECTURE

Traced from the frontend call to SQL execution. The entry point is **`GET /ask`** —
not a POST, and not the `chat_router` (which is session CRUD only).

```
frontend ChatPage.jsx:968  fetch(`${API}/ask?question=...&session_id=...`)
  │
  ▼
app.py:360  ask_question()
  ├─ session ownership + company_id check           app.py:408   (multi-tenant boundary)
  ├─ division RBAC check                            app.py:411
  ├─ persist USER message                           app.py:423
  │
  ├─ PENDING CLARIFICATION BRANCH                   app.py:439-636
  │    get_pending_clarification(employee_id, session_id)
  │    ├─ regex option-number parse ("1", "first")  app.py:472
  │    ├─ quoted-text / prefix match on option      app.py:482-519
  │    ├─ 1 match  → resume with original question  app.py:544
  │    ├─ >1 match → re-ask (AmbiguityException)    app.py:567
  │    └─ 0 match  → SemanticResolver.resolve() probe for "intent shift"
  │                   app.py:592  ─ if any slot resolves, DISCARD pending state
  │
  ├─ classify_intent()                              intent_classifier.py:129
  │    Stage 1 hardcoded AdventureWorks keyword list (_ANALYTICS_KEYWORDS:69)
  │    Stage 2 LLM fallback (purpose="intent")
  │    └─ GENERAL → generate_general_response(), return
  │
  ├─ get_history(employee_id, session_id)           conversation_memory.py:92
  │
  ▼
ai_service.py:72  generate_sql_query()
  │
  ▼
prompt_builder.py:139  build_sql_prompt()
  ├─ history_text = last 2 turns, RAW question + RAW SQL concatenated   :151-158
  ├─ TemporalPipeline.build()                        :209
  ├─ clarified temporal override (hardcoded CY/PY/PPY strings)          :217-276
  ├─ previous_semantic_context ← scan history for resolved_values       :286-293
  ├─ SemanticResolver.resolve(conn_id, question, ...)                   :296
  ├─ has_snapshot_metric: HARDCODED {"CY","PY","PPY","PPPY","PPPPY","CYQ","PYQ"}  :339
  ├─ SemanticGate.evaluate(semantic_result)          :442
  │    └─ BLOCK → PARTIAL_MATCH / STRONG_AMBIGUITY → AmbiguityException :463-563
  ├─ RelevantTableResolver.resolve()                 :566
  ├─ RelationshipExpander.expand()                   :573
  ├─ MetadataResolver.resolve()                      :598
  ├─ RuntimeContextBuilder.build()                   :608
  ├─ SemanticPlanBuilder.build()   ← PLAN BUILT HERE, AFTER context     :633
  ├─ hardcoded check: business_name=="Sales" and column=="None"         :673
  └─ returns (prompt_text, semantic_result, runtime_context)
  │
  ▼
ai_service.py:96  LLMExecutionService.execute(purpose="sql_generation")
  └─ LLM WRITES THE SQL FROM TEXT                    ← plan is advisory only
  │
  ▼
app.py:783-859
  ├─ validate_cls()            (column-level security)
  ├─ validate_sql_query()      (blocked keywords; "Schema Validation: NOT IMPLEMENTED":803)
  ├─ guard_sql(plan=..., sql=...)   Gate 5 conformance — SHADOW MODE by default  :838
  ├─ enforce_row_limit()
  ├─ apply_rls() + DivisionRLSEngine
  └─ execute against source connection
```

### Live / dead / partially integrated

**Live and on the hot path:**
`app.py:/ask`, `intent_classifier`, `conversation_memory`, `prompt_builder`,
`SemanticResolver`, `DimensionValueResolver` + `matching/*` pipeline, `SemanticGate`,
`TemporalPipeline` + `temporal/*`, `RelevantTableResolver`, `RelationshipExpander`,
`MetadataResolver`, `RuntimeContextBuilder`, `SemanticPlanBuilder`, `ai_service`,
`sql_validator`, Gate 5 `guard_sql`, RLS/CLS engines.

**Live but ineffective (built, wired, ignored by consumers):**
- `SemanticPlan` — built and passed to the guard, but the guard is in shadow mode, so it
  changes nothing. Effectively documentation.
- `retrieval.confidence` — computed, logged, threaded through, **never gated on**.
- `SnapshotConfig` / `snapshot_config.py` (Gate 2 Step 11a) — correctly consumed by
  `SemanticPlanBuilder`, but `prompt_builder.py:339` still carries a hardcoded duplicate of
  the same column set, so the two disagree the moment configuration changes.
- `assumptions_made` on the plan — populated by the builder, never surfaced to the user.

**Configuration written but never read (the Finding A set):**
`is_excluded`, `is_confirmed`, `dimension_role`, `semantic_table_config.domain_id`.

**Dead / vestigial:**
- `semantic/matching.zip`, `semantic/temporal.zip` — stale archives beside live packages.
- `semantic/singular_plural_matcher.py` — duplicate of the live
  `semantic/matching/singular_plural_matcher.py`. Two files, same class name, one used.
- `_ANALYTICS_KEYWORDS` — an AdventureWorks list (`reseller`, `salesperson`,
  `subcategory`) in a Ramraj textiles product. Contains none of `banian`, `dhoti`,
  `party`, `pending`, `receivable`. Ramraj questions reach analytics **via the Stage-2 LLM
  fallback**, i.e. by accident, at the cost of an extra LLM call on the common path.
- `semantic/test_metrics.py` imported at the top of `semantic_resolver.py:1` but unused.

**Conflicting sources of truth (detail in §14):** snapshot column names exist in
`semantic_snapshot_mapping` (authoritative), `DEFAULT_BINDINGS`
([snapshot_config.py](backend/semantic/temporal/snapshot_config.py)), and a hardcoded set
at `prompt_builder.py:339`. Three copies.

---

## 3. LIVE / DEAD / PARTIAL COMPONENT TABLE

| Component | State | Evidence |
|---|---|---|
| `app.py /ask` | LIVE — sole entry point | ChatPage.jsx:968 |
| `chat/chat_sessions.py` | LIVE — CRUD only, not the ask path | chat_sessions.py:18-242 |
| `intent_classifier` Stage 1 | LIVE but domain-mismatched | intent_classifier.py:69 |
| `intent_classifier` Stage 2 (LLM) | LIVE — carries the real load | intent_classifier.py:159 |
| `SemanticResolver` | LIVE — core resolver | prompt_builder.py:296 |
| `DimensionValueResolver` + `matching/` | LIVE | dimension_value_resolver.py:126 |
| `SemanticGate` | LIVE but confidence-blind | semantic_gate.py:19 |
| `TemporalPipeline` | LIVE | prompt_builder.py:209 |
| `SemanticPlanBuilder` | LIVE, output advisory | prompt_builder.py:633 |
| `SnapshotConfig` (Gate 2 11a) | LIVE in builder; duplicated in prompt_builder | prompt_builder.py:339 |
| Gate 5 `guard_sql` | LIVE, **shadow mode** | app.py:838 |
| `is_excluded` / `is_confirmed` / `dimension_role` | **WRITTEN, NEVER READ** | grep: 0 hits in read path |
| `retrieval.confidence` | Computed, never gated | semantic_gate.py:19 |
| `semantic/singular_plural_matcher.py` (root) | DEAD duplicate | vs `matching/` version |
| `matching.zip`, `temporal.zip` | DEAD archives | filesystem |
| `_ANALYTICS_KEYWORDS` | VESTIGIAL (AdventureWorks) | intent_classifier.py:69 |

---

## 4. EXISTING RESOLVER AUDIT

### 4.1 `SemanticResolver` — metric/dimension name resolution

**Input:** `connection_id`, raw question, optional `clarified_candidate`,
optional `previous_semantic_context`.
**Processing:** loads all active metrics + dimensions
([:172-196](backend/semantic/semantic_resolver.py#L172)), scores every row against the
question with a 7-tier priority ladder in `_get_match_info` ([:64-161](backend/semantic/semantic_resolver.py#L64)):
exact technical (50000) → exact business (40000) → business phrase (30000) → technical
whole-word (20000) → business core-word (15000) → business whole-word (10000) → synonym
(9000) → stem overlap ≥0.5 (≤8000). Then a `SAME_TABLE_BONUS = 0.35` re-rank
([:318](backend/semantic/semantic_resolver.py#L318)) and greedy span-overlap removal
([:271-297](backend/semantic/semantic_resolver.py#L271)).
**Output:** metrics, dimensions, objects, `retrieval{status, confidence, counts}`.

| Aspect | Finding |
|---|---|
| Confidence | Slot-count only; not match quality. §1 Finding C. |
| Ambiguity | None at this layer. Greedy overlap silently drops the loser with no record. |
| No-match | Score 0 → candidate omitted; contributes to INSUFFICIENT only via count. |
| Fuzzy | **None.** Typos never resolve a metric/dimension name; only *values* are fuzzy-matched. |
| Context | `previous_semantic_context` accepted; only reaches value resolution, not name resolution. |
| Scoping | connection_id only. **No `is_excluded`/`is_confirmed`/domain filter.** |
| Multi-dimensional | Returns a flat list. No filter-vs-grouping role. §8. |
| Determinism | Deterministic. |
| False positives | `SAME_TABLE_BONUS` (0.35) is added to scores in the 9000–50000 range — it is **arithmetically incapable of changing any ranking**. The "context ranking" logged at :320-341 is theatre. |
| Reusable | Yes, mechanism is domain-neutral. |

The `SAME_TABLE_BONUS` defect is worth stating plainly: adding 0.35 to a score of 15000
cannot reorder it against 20000. The feature is inert.

### 4.2 `DimensionValueResolver` + `matching/` pipeline — value resolution

**Input:** connection_id, question, dimension context, previous context.
**Processing:** cached `dimension_value_index` load ([:531](backend/semantic/dimension_value_resolver.py#L531))
→ Exact → Normalized → SingularPlural → Fuzzy matchers → rank → dedupe → ambiguity classify.
**Confidence:** *static per match type* — EXACT 1.00, NORMALIZED 0.98, SINGULAR_PLURAL 0.95,
FUZZY 0.90 ([confidence.py](backend/semantic/matching/confidence.py)). The fuzzy matcher
overrides with `score/100` ([fuzzy_matcher.py](backend/semantic/matching/fuzzy_matcher.py)).

| Aspect | Finding |
|---|---|
| Fuzzy | `rapidfuzz.WRatio`, cutoff 85, plus a token-evidence guard at ratio ≥75. |
| Ambiguity | Real: `AmbiguityClassifier` → STRONG_AMBIGUITY / PARTIAL_MATCH / dominant. Best subsystem in the codebase. |
| No-match | Returns empty; gate converts to INSUFFICIENT. |
| Scoping | `is_active` only. **Excluded dimensions still supply values.** |
| False positives | Layered defence genuinely works on the brief's examples — see reproduction §12. |
| Determinism | Deterministic. |

**Read-only reproduction (rapidfuzz, matching live settings):**

```
phrase      WRatio hits (cutoff 85)        token-evidence ratio (cutoff 75)
laptop   →  [('top', 90)]      PASSES      laptop vs top  = 66.7  → BLOCKED ✅
stopped  →  [('top', 90)]      PASSES      stopped vs top = 60.0  → BLOCKED ✅
banain   →  [('banians', 85)]  PASSES      banain vs banians = 76.9 → allowed ✅ (correct)
mars     →  []                             → no match ✅
xyzzy    →  []                             → no match ✅
pant     →  [('pants', 88)]                pant vs pants = 88.9 → allowed ✅
```

**This corrects a hypothesis I held going in.** The `laptop → top` and `stopped → top`
false positives named in the brief are *already blocked* by the token-evidence guard. The
two-stage design (WRatio gate, then token-ratio gate) is sound and should be **kept**. The
adversarial 0/10 failure has a different cause — see §12.

### 4.3 `SemanticGate`

Pure function of `status` and `ambiguity_result`. `confidence` is read and discarded
([semantic_gate.py:19](backend/semantic/semantic_gate.py#L19)). `status == PARTIAL`
(exactly one slot type resolved) is **allowed through to SQL generation**
([:60-69](backend/semantic/semantic_gate.py#L60)). So "sales in Mars" — metric resolves,
value does not — yields PARTIAL and produces SQL for total sales, silently ignoring the
unresolvable filter. This is the mechanism behind NO_MATCH_ADVERSARIAL 0/10.

### 4.4 `SemanticPlanBuilder`

Builds `dimensions` from `dimension_objects` and `filters` from `value_matches`
([:290-332](backend/semantic/semantic_plan_builder.py#L290)). **No deduplication between
the two.** Query shape from three regexes ([:93-101](backend/semantic/semantic_plan_builder.py#L93)) —
these are correctly word-boundary-anchored and do *not* misfire on "topic"/"laptop"
(verified). Hardcoded `business_name == "Sales"` special case at
[prompt_builder.py:673](backend/ai/prompt_builder.py#L673).

### 4.5 `TemporalPipeline`

The most mature subsystem. Thread-local state, proper intent taxonomy, Gate 2's
scope-aware `SnapshotConfig` correctly integrated. **Keep.** Its only defects are external:
the hardcoded duplicates at `prompt_builder.py:234-268` and `:339`.

### 4.6 `intent_classifier`

Two-stage keyword→LLM. Keyword list is for the wrong database (§2). Consequence: an extra
LLM round-trip on most real questions, and a latent misclassification risk.

---

## 5. STEP 14 — BENCHMARK RE-BASELINE FINDINGS

**Existing asset:** 194 cases across 8 JSON files, 190 scored, 4 marked FUTURE_PHASE.
13 categories. Runner: `run_retrieval_benchmark.py`.

**What it measures:** `SemanticResolver.resolve()` output only — metrics, dimensions,
values, ambiguity status, retrieval status, followup flag. It asserts on **business-name
strings** ([:243-285](backend/test/semantic_benchmark/run_retrieval_benchmark.py#L243)),
sorted and lowercased.

| Question | Answer |
|---|---|
| Retrieval only, or full interpretation? | **Retrieval only.** No SQL, no plan, no execution, no answer correctness. |
| Are expectations authoritative? | **No.** 116/194 expect metric `"C Y"`; 37 `"Qty"`; only 17 `"Sales"`. Pre-Gate-2 names. |
| Multi-dimensional coverage? | Yes — MULTI_DIMENSION (18) + METRIC_DIMENSION_VALUE (22). |
| Ambiguity coverage? | Yes — AMBIGUOUS_VALUES (18), best-performing at 77.8%. |
| No-match coverage? | Yes — NO_MATCH_ADVERSARIAL (10). 0% pass. |
| Follow-up coverage? | Yes — FOLLOW_UP (10), METRIC_SHIFT (8), ENTITY_TOPIC_SHIFT (8). All ≤12.5%. |
| Ranking/trend/comparison? | **No.** No category asserts `query_shape`, ranking, or output mode. |
| Outdated expectations? | **Yes, pervasively.** See §6. |

**Structural defect — cascading failures.** 66 of 139 failures are multi-code. One root
cause (a renamed metric) emits `wrong metric` + `wrong ambiguity` + `wrong retrieval
status` on the same case, because status is derived from slot counts which depend on the
metric matching. This directly violates the Step 15 goal of one-failure-one-cause, and it
inflates `failure_breakdown` (`wrong ambiguity` = 105 is largely an artefact).

**Proposed Gate 3 evaluation structure (do not build yet):**

1. **Two-layer scoring.** Layer 1 = *slot resolution* (current assertions). Layer 2 = *plan
   conformance* — assert on the `SemanticPlan`: `filters[]` vs `dimensions[]` separately,
   `query_shape`, `temporal.snapshot_columns`, `NO_MATCH`. Layer 2 is what Steps 17/18/21
   actually need and cannot be expressed today.
2. **Assert on identity, not display name.** Expect `(table_name, column_name)` pairs, not
   `business_name` strings. Immunises the benchmark against admin renames — the exact
   fragility that makes today's 26.84% meaningless.
3. **Primary-cause tagging.** Each case declares the *one* slot under test; secondary
   mismatches are recorded but do not multiply the failure count.
4. **New categories:** `NO_MATCH_STRICT`, `MULTI_SLOT_ROLE` (filter vs grouping),
   `TOPIC_SHIFT_STRICT`, `RANKING_SHAPE`, `COMPARISON_SHAPE`, `CROSS_DOMAIN`.
5. **Freeze a v2 dataset**; keep v1 immutable for historical comparison.

**Order:** Step 16 (expectation validity) must complete before Step 14 re-baseline runs.
Re-baselining against stale expectations measures nothing.

---

## 6. STEP 15 — FAILURE TAXONOMY

Current codes are 6, flat, and cascade. Proposed taxonomy — **hierarchical, single primary
cause, mapped to the owning stage**:

| Code | Stage | Definition | Diagnosed by |
|---|---|---|---|
| `MET_MISSING` | Metric res. | Expected metric not resolved | expected ∉ actual metrics |
| `MET_WRONG` | Metric res. | Different metric resolved | actual ≠ ∅ and ≠ expected |
| `MET_EXTRA` | Metric res. | Spurious extra metric | actual ⊃ expected |
| `DIM_MISSING` / `DIM_WRONG` / `DIM_EXTRA` | Dimension res. | as above for grouping dims | plan.dimensions |
| `DIM_ROLE_CONFUSED` | Slot assign. | Right dimension, wrong role (filter↔grouping) | in plan.filters, expected in plan.dimensions |
| `VAL_MISSING` / `VAL_WRONG` | Value res. | value slot | plan.filters[].values |
| `VAL_HALLUCINATED` | Value res. | value returned for a term absent from the index | actual value with no index entry for the question span |
| `TBL_WRONG` / `DOMAIN_WRONG` | Scope | wrong table/domain chosen | plan.primary_table |
| `TMP_INTENT_WRONG` | Temporal | wrong intent (PY vs PYTD) | time_ctx.intent |
| `TMP_MAPPING_WRONG` | Temporal | right intent, wrong column | time_ctx.snapshot_columns |
| `AMB_SHOULD_CLARIFY` | Gate | answered confidently where clarification was required | status ≠ STRONG_AMBIGUITY |
| `AMB_OVER_CLARIFY` | Gate | clarified where a dominant match existed | false positive clarification |
| `NOMATCH_MISSED` | Gate | **proceeded when nothing matched** | the adversarial failure |
| `CTX_LEAK` | Conversation | prior turn's filter wrongly retained | filter present, absent from turn |
| `CTX_LOST` | Conversation | prior filter wrongly dropped | filter absent, expected retained |
| `TOPIC_LEAK` | Conversation | old domain retained after topic change | primary_table unchanged across shift |
| `SHAPE_WRONG` | Plan | ranking/trend/comparison misclassified | plan.query_shape |
| `UNSUPPORTED` | — | capability intentionally absent | declared in case |

**Diagnosis rule (one failure → one cause):** evaluate stages in pipeline order —
scope → metric → dimension → value → temporal → slot-role → shape → gate → context. The
**first** stage that mismatches is the primary cause; all later mismatches are recorded as
`downstream` and excluded from the headline count. This is what makes the taxonomy
actionable, and it is the fix for the 66 multi-code cases.

---

## 7. STEP 16 — BENCHMARK EXPECTATION VALIDITY

**Mandatory classification before any expectation is edited:**

- **A — software defect:** DB supports it, config is correct, code gets it wrong. → fix code.
- **B — benchmark defect:** expectation contradicts current authoritative config. → fix expectation, log rationale + before/after.
- **C — data limitation:** DB cannot answer. → mark `UNSUPPORTED_BY_DATA`, assert graceful decline.
- **D — intentionally unsupported:** out of scope. → `FUTURE_PHASE`.
- **E — ambiguity:** genuinely under-specified. → expect clarification, not an answer.

**Every reclassification must record:** case_id, original expectation, evidence
(config row or query), verdict A–E, new expectation, author, date. No silent edits.

**Findings on the current dataset:**

| Issue | Cases | Verdict | Recommended |
|---|---|---|---|
| Metric expected as `"C Y"` | 116 | **B** — Gate 2 renamed these; expectation names a display string that no longer exists | Re-express as `(table, column)` identity, e.g. `SALES.CY` |
| Metric `"Qty"` / `"Amt"` / `"due"` / `"pendamt"` | 63 | **B** — same class, raw discovered names | Same |
| `"Show sales for Banian"` expects metric `CY` | many | **E** — question names no period; binding to current-year is an unstated assumption | Expect `assumptions_made` to record the default, or expect temporal clarification |
| TEMPORAL_QUESTIONS 0/10 | 10 | **A + B mixed** — must be re-triaged individually after B-class renames are fixed | Re-run, then classify |
| NO_MATCH_ADVERSARIAL 0/10 | 10 | **A** — genuine defect, gate allows PARTIAL through | Fix code (§12), keep expectations |
| MULTI_DIMENSION 0/18 | 18 | **A** — plan cannot express filter-vs-grouping roles | Fix code (§8), keep expectations |
| FOLLOW_UP / TOPIC_SHIFT 0% | 26 | **A** — no conversation state machine | Fix code (§9), keep expectations |

**Conclusion:** roughly 60% of current failures are B-class (stale names) and ~40% are
genuine A-class defects concentrated in Steps 17, 18, 21. The true software pass rate is
unknown until B-class is corrected — which is precisely why Step 16 precedes Step 14.

---

## 8. STEP 17 — MULTIPLE DIMENSIONS / MULTIPLE SLOTS

Target: *"Show BANIANS sales in Tamil Nadu by party last year."*
Required slots: metric=Sales; filter Product=BANIANS; filter State=TN; grouping=Party;
time=PY(full).

**Where information is lost — three distinct defects:**

**(1) The word "by" is never parsed.** `grep` for grouping cues across
`semantic_plan_builder.py` and `semantic_resolver.py` returns only a comment and a
temporal-breakdown check. The primary English grouping signal is not a feature of the
system. Grouping vs filtering is inferred solely from *"did a value match this dimension?"*
— dimension-with-value ⇒ filter, dimension-without-value ⇒ grouping. That heuristic
breaks on exactly the target sentence: "in Tamil Nadu" is a filter, "by party" is a
grouping, and both are dimensions.

**(2) A filtered dimension is emitted twice.** `plan.dimensions` is built from *all*
`dimension_objects` and `plan.filters` from *all* `value_matches`, with **no dedup**
([semantic_plan_builder.py:290-332](backend/semantic/semantic_plan_builder.py#L290)). State
appears as a grouping *and* a filter ⇒ SQL groups by State when the user asked to group by
Party. This alone can explain MULTI_DIMENSION 0/18.

**(3) Greedy overlap removal discards competing slots silently.**
`_remove_overlaps` keeps the highest-scoring candidate per text span and drops the rest
with no record ([semantic_resolver.py:271](backend/semantic/semantic_resolver.py#L271)).
With `SAME_TABLE_BONUS` inert (§4.1), there is no domain-coherence pressure on which
survives.

**Proposed representation — role-tagged slots, no positional assumptions:**

```
SemanticSlot {
  role:        FILTER | GROUPING | METRIC | TIME | ORDER_BY
  dimension:   {table, column, business_name, dimension_role}
  values:      [resolved values]        # FILTER only
  operator:    = | IN | BETWEEN | >= ...
  source_span: (start, end)             # provenance in the question
  evidence:    {match_type, score, why}
  confidence:  computed (§13)
}
```

Role assignment rules, in precedence order (all deterministic, all configuration-driven):
1. `dimension_role` from Gate 2 config — a `GROUPING`-roled dimension is never silently a filter.
2. Syntactic cue — `by|per|across|split by|grouped by` + dimension ⇒ GROUPING.
3. Cue — `in|for|of|where|with` + dimension-with-value ⇒ FILTER.
4. A dimension with a resolved value and no grouping cue ⇒ FILTER.
5. A dimension with no value and no cue ⇒ GROUPING (current default; keep as fallback).
6. **A dimension may hold at most one role per query.** If both fire, prefer the cue-backed
   one and record the conflict in `assumptions_made`.

This is order-independent and works for "by party show banians sales" as well as the
canonical order.

---

## 9. STEP 18 — MULTI-TURN CONVERSATION

**Current mechanism.** `history` = last N exchanges of `{question, sql_query,
semantic_context}` ([conversation_memory.py:132](backend/services/conversation_memory.py#L132)).
`prompt_builder` injects the **last 2 turns as raw text — the previous question and the
previous SQL verbatim** ([:151-158](backend/ai/prompt_builder.py#L151)). Separately,
`previous_semantic_context` is scanned out of history and passed to the resolver
([:286-293](backend/ai/prompt_builder.py#L286)).

**This is the "blindly concatenating previous messages" anti-pattern the brief forbids,
and it is what the system does today.** There is no state machine, no slot carry-over
policy, no topic-change detection, and no expiry. Prior SQL in the prompt is the strongest
signal the model sees, so it tends to copy it — which is exactly `CTX_LEAK`.

Topic-change detection exists in exactly one place and only inside a pending
clarification: `app.py:592` probes `SemanticResolver.resolve()` and treats *any* resolved
slot as an intent shift. Outside clarification, there is none.

**Trace of the required behaviours:**

| Turn | Required | Today |
|---|---|---|
| T1 "Show BANIANS sales" | filter Product=BANIANS, metric Sales | works |
| T2 "Last year" | **carry** filter, **replace** time | no slot state; prior SQL text is pasted and the model guesses |
| T3 "by party" | **carry** filter+time, **add** grouping | "by" unparsed (§8) ⇒ fails |
| T2′ "Now show order pendings" | **reset** — new domain | no topic detection ⇒ BANIANS leaks into a different table |

**Proposed conversation state — explicit, typed, per (user, session, connection):**

```
ConversationState {
  connection_id, employee_id, session_id     # full scoping key
  active_domain            # from Gate 2 semantic_domain
  active_table
  slots: {METRIC[], FILTER[], GROUPING[], TIME}
  turn_index, updated_at
}
```

**Merge rules (deterministic, evaluated per turn):**

1. **Classify the turn** against the current state:
   - `NEW_QUESTION` — resolves a metric **and** a domain different from `active_domain` ⇒ **RESET all slots**.
   - `REFINEMENT` — resolves no metric, but resolves time/dimension/value ⇒ **MERGE**.
   - `REPLACEMENT` — resolves a metric in the **same** domain ⇒ replace metric, **keep** filters unless contradicted.
   - `CLARIFICATION_REPLY` — pending clarification exists and the turn matches an option ⇒ resume (current behaviour, keep).
2. **Slot-type replacement:** a new value for an existing slot *type* replaces it
   ("last year" replaces TIME). A new value for a *different* dimension adds a slot.
3. **Contradiction:** a new filter on the same dimension replaces the old one
   ("BANIANS" → "DHOTI" replaces, never ANDs).
4. **Expiry:** slots expire after N turns (propose 5) or on domain change. Pending
   clarification already expires at 300s — keep, and align.
5. **Never inject prior SQL into the prompt.** Carry *resolved slots*, not text. This is
   the single change that kills `CTX_LEAK`.
6. **Always surface carried slots** in `assumptions_made` so the answer can say "for
   BANIANS, last year" — an accuracy *and* trust win.

---

## 10. STEP 19 — LINGUISTIC VARIATION

**Current handling.** Normalisation (`lower`, strip `'`, `[-_/.]`→space, collapse
whitespace) ([singular_plural_matcher.py:30](backend/semantic/matching/singular_plural_matcher.py#L30));
singular/plural with a protected-word list and 7 irregulars; fuzzy `WRatio`≥85 + token
evidence ≥75. Applied to **values only** — metric and dimension *names* get a crude
inline `_stem_word` ([semantic_resolver.py:51](backend/semantic/semantic_resolver.py#L51))
and no fuzzy matching at all.

**Verified behaviour (read-only):**

| Input | Result | Verdict |
|---|---|---|
| banian → banians | 76.9 token ratio, allowed | ✅ works |
| pant → pants | 88.9, allowed | ✅ |
| vests → vest | 88.9, allowed | ✅ |
| shirt → shirts | 90 WRatio, allowed | ✅ |
| laptop → top | blocked at token stage | ✅ correctly rejected |
| stopped → top | blocked at token stage | ✅ correctly rejected |
| mars, xyzzy | no candidates | ✅ |

**So why is SINGULAR_PLURAL only 5.6%?** Not because singular/plural matching is broken —
it demonstrably works. Because **every case also asserts the metric**, and the metric
expectation is the stale `"C Y"` (§7 B-class). The category is failing on the metric
assertion, not the linguistic one. This is the clearest single illustration of why Step 16
gates Step 14.

**Gaps that are real:**
- Metric/dimension *names* have no fuzzy tier — "revenu", "quantiy" resolve nothing.
- Abbreviations (`qty`→quantity, `RM`→Regional Manager) depend entirely on the admin
  filling `synonyms`. Gate 2 seeded some. This is the right mechanism — configuration, not code.
- "3 years ago" vs "three years ago" — word-number normalisation exists **only** inside the
  clarification branch ([app.py:459-467](backend/app.py#L459)), not in temporal parsing.
- Mixed Tamil-English: no support. Recommend explicitly out of scope for Gate 3 (D-class)
  unless the golden set shows real traffic.

**Technique allocation (this is a design decision, not a default):**

| Concern | Technique | Why not the alternatives |
|---|---|---|
| case, punctuation, whitespace | normalisation | Free, deterministic, zero risk. |
| singular/plural | rule matcher (existing) | Deterministic, explainable, already correct. |
| typos in **values** | fuzzy + token evidence (existing) | Proven above. Embeddings add cost and *reduce* explainability for no accuracy gain on short product codes. |
| typos in **names** | **add** the same fuzzy tier, higher cutoff (≥90) | Names are a small closed set; fuzzy is sufficient and cheap. |
| abbreviations, business synonyms | **admin `synonyms` config** | Authoritative, auditable, no inference. The correct home. |
| word-numbers, ordinals | normalisation, moved out of the clarification branch | Deterministic. |
| genuinely novel phrasing | **LLM escalation (§11)** | Only after all the above miss. |

**Explicit recommendation against embeddings for Gate 3.** Values here are short product
and place codes (BANIAN, TN, DHOTI). Embedding similarity on 2–8 character tokens is
noisy, needs an index to build and invalidate, adds latency, and — decisively — is
*less explainable* than "token ratio 76.9 ≥ 75". The current lexical stack outperforms it
on this data shape. Revisit only if a future domain introduces long free-text values.

---

## 11. STEP 20 — LLM RESOLUTION TIER

**Existing infrastructure** — `LLMExecutionService.execute(purpose=...)` with
per-purpose model routing and DB-configured fallbacks. Purposes live today: `intent`,
`sql_generation`, `insight`, `assistants`. A new purpose costs no new infrastructure.

**Option evaluation for *this* project:**

| | Accuracy | Latency | Explainable | Cost | Determinism | FP risk |
|---|---|---|---|---|---|---|
| **A** rules/fuzzy only | ceiling ~70% | best | total | zero | full | low |
| **B** + embeddings | +small on short codes | +index, +ms | poor | index build | high | **raises** FP |
| **C** rules/fuzzy + LLM escalation | highest practical | best common path | good (tier logged) | only on miss | high | low if validated |
| **D** LLM-first + validation | high | **worst** — LLM on every query | moderate | highest | low | moderate |

**Recommendation: Option C.**

Rationale specific to this codebase: the deterministic stack already handles the common
path correctly (§10 reproduction). Its measured failures are concentrated in *structure*
(roles, conversation, no-match) — problems that Steps 17, 18 and 21 fix deterministically,
not problems an LLM is needed for. Option D would pay an LLM call on every query to solve
problems that a `by`-parser solves for free, and it would make the plan non-reproducible,
which breaks the benchmark. Option B buys little on 2–8 character codes and costs
explainability.

**Escalation policy — when the LLM tier is invoked.** Only when *all* hold:
1. Deterministic resolution left a **required** slot unresolved, or produced
   `STRONG_AMBIGUITY` with no dominant candidate;
2. the question is not a clarification reply;
3. the escalation budget for the turn is unspent (max **1** call).

**What it receives (never the database, never free schema):**
- the question, and the resolved slots so far;
- **the candidate shortlist only** — business names + synonyms of metrics/dimensions that
  are `is_active AND NOT is_excluded`, plus the top-K candidate *values* already retrieved
  from the index (K≤25);
- the conversation slot state (not raw history);
- an explicit "NO_MATCH is a valid and expected answer" instruction.

**Required structured output** (JSON, schema-validated):

```json
{"slots":[{"role":"FILTER|GROUPING|METRIC|TIME",
           "candidate_id":"<id from the supplied shortlist>",
           "confidence":0.0-1.0,
           "reasoning":"short"}],
 "unresolved":["..."],
 "no_match":false}
```

**Validation after output — the LLM is a proposer, never an authority:**
1. Every `candidate_id` **must** be one supplied in the shortlist. Anything else ⇒ discard
   the whole response and treat as NO_MATCH. This is the anti-hallucination guarantee: the
   model physically cannot name a column or value that was not offered to it.
2. The referenced row is re-read from configuration; `is_excluded` re-checked.
3. Values are re-verified against `dimension_value_index`.
4. Temporal mappings are **never** LLM-assigned — `SnapshotConfig` owns them absolutely.
5. LLM confidence is recorded but **capped** below any deterministic match
   (propose ≤0.80), so an exact match always outranks a model opinion.

**Retry / timeout / failure:** max attempts **1** (one retry only on malformed JSON, not on
a disliked answer). Timeout 5s. On timeout, malformed output, or failed validation ⇒
`NO_MATCH` ⇒ clarification. **Never** fall through to a guess.

**Auditability:** persist `{question, shortlist_ids, raw_response, validated_slots,
rejected_ids, latency, model}` per escalation. Required to defend the tier and to build
regression cases.

**Absolute prohibitions.** The LLM must never choose physical columns, tables, values, or
temporal mappings directly, and never bypass `is_excluded`. Those come from configuration
and the value index. This is enforced structurally by rule 1, not by prompt instruction.

---

## 12. STEP 21 — FALSE-POSITIVE / NO-MATCH PROTECTION

**The real cause of NO_MATCH_ADVERSARIAL 0/10 is not fuzzy matching** — §4.2 proves the
fuzzy guard rejects `laptop→top` and `stopped→top`. The cause is the **gate**:

`status == PARTIAL` (one slot type resolved) is **allowed**
([semantic_gate.py:60](backend/semantic/semantic_gate.py#L60)). For "show sales in Mars":
metric resolves, value does not ⇒ 1 component ⇒ PARTIAL ⇒ **allowed** ⇒ SQL for *total
sales*, with Mars silently dropped. The user receives a confident, wrong, unqualified
number. There is no `NO_MATCH` state in the system at all.

**Defined protections:**

**Confidence — actually computed, replacing the slot-count score:**
```
slot_confidence = base(match_type) × span_coverage × domain_coherence
   base:            EXACT 1.00 | NORMALIZED 0.95 | SINGULAR_PLURAL 0.90
                    | FUZZY (token_ratio/100, cap 0.85) | LLM (cap 0.80)
   span_coverage  = matched_chars / candidate_chars     (penalises "top" ⊂ "laptop")
   domain_coherence = 1.0 same table as metric | 0.85 same domain | 0.6 cross-domain
plan_confidence = min(required slot confidences)        # weakest link, not a sum
```
This is a genuine quality measure, unlike today's count.

**Thresholds (initial, to be tuned against the v2 benchmark — these are starting values,
not proven constants):**
- accept ≥ **0.85**
- clarify **0.60–0.85**
- `NO_MATCH` < **0.60**
- **ambiguity margin:** if top₁ − top₂ < **0.10** ⇒ clarify regardless of absolute score.
- **exact-match precedence:** any EXACT match suppresses all fuzzy candidates on the same
  span (already implemented in `_remove_contained_matches` — keep).
- **evidence floor:** fuzzy requires token ratio ≥75 **and** span coverage ≥0.6. The second
  clause is new and is what would stop a short-substring match on longer values.
- **domain constraint:** candidates outside the resolved metric's domain are demoted, not
  merely tie-broken. This is `SAME_TABLE_BONUS` done correctly (§4.1 shows the current one
  is arithmetically inert).

**The mandatory new rule — explicit `NO_MATCH`:**
> If the question contains a noun phrase that the system attempted to resolve as a value
> and **failed**, the request must **not** proceed to SQL. It must return `NO_MATCH` naming
> the unresolved term.

"Show sales in Mars" ⇒ *"I could not find 'Mars' in any configured business dimension."*
Never a total-sales answer. This single rule converts the 0/10 adversarial category into a
passing one and is the highest-value change in Step 21.

**"UT resolves to the wrong State column" — correct diagnosis.** Not a fuzzy problem (§4.2
shows short codes match only exactly). It is a **duplicate-column** problem: Gate 2's
`report_duplicate_columns.py` flagged `State1/State2/State3/StateCode` holding overlapping
values. "UT" legitimately exists in several, so it is a genuine `CROSS_DIMENSION`
ambiguity. Correct handling: **clarify**, and let the admin exclude the redundant columns —
which requires Finding A to be fixed first, because exclusion currently does nothing.

---

## 13. CURRENT DEFECTS (consolidated, severity-ordered)

| # | Defect | Location | Severity | Effect |
|---|---|---|---|---|
| D1 | `is_excluded` / `is_confirmed` / `dimension_role` never read | all 3 read paths | **Critical** | Gate 2 config inert |
| D2 | No `NO_MATCH`; PARTIAL proceeds to SQL | semantic_gate.py:60 | **Critical** | Confident wrong answers |
| D3 | SemanticPlan advisory; guard in shadow mode | app.py:838 | **Critical** | SQL may ignore the plan |
| D4 | `confidence` never gated | semantic_gate.py:19 | **Critical** | No quality floor |
| D5 | Grouping cue "by" unparsed | plan_builder | **High** | MULTI_DIMENSION 0% |
| D6 | dimensions/filters not deduped | plan_builder:290-332 | **High** | Wrong GROUP BY |
| D7 | Raw prior SQL injected into prompt | prompt_builder:151 | **High** | CTX_LEAK; topic bleed |
| D8 | No conversation state machine / topic detection | — | **High** | FOLLOW_UP 0% |
| D9 | `confidence` is a slot count | semantic_resolver:593 | **High** | Meaningless metric |
| D10 | Hardcoded snapshot columns duplicating config | prompt_builder:339, 234-268 | **High** | Diverges from Gate 2 |
| D11 | `SAME_TABLE_BONUS` arithmetically inert | semantic_resolver:318 | Medium | Dead feature, false logs |
| D12 | Hardcoded `business_name == "Sales"` | prompt_builder:673 | Medium | Sales-only branch |
| D13 | AdventureWorks keyword list | intent_classifier:69 | Medium | Extra LLM call; misroute risk |
| D14 | Benchmark asserts display names | runner:243 | Medium | Breaks on admin rename |
| D15 | Cascading multi-code failures | runner | Medium | Obscures root cause |
| D16 | No fuzzy tier for metric/dimension names | semantic_resolver | Medium | Name typos fail |
| D17 | Word-number normalisation only in clarification | app.py:459 | Low | "three years ago" fails |
| D18 | Dead duplicates: `singular_plural_matcher.py`, `*.zip` | — | Low | Confusion |
| D19 | Value cache unbounded, not invalidated by config writes | dimension_cache.py | Medium | Stale after admin edit |

---

## 14. SOURCE-OF-TRUTH VIOLATIONS

Required authority model, and where the code violates it:

| Fact | Authority | Violations |
|---|---|---|
| Business meaning | Admin semantic config | **D1** — exclusion/confirmation/role ignored |
| Physical column | Config / schema | `prompt_builder:339` hardcodes CY/PY/PPY/PPPY/PPPPY/CYQ/PYQ; `:234-268` hardcodes CY/PY fallbacks; `:673` hardcodes `"Sales"` |
| Table / domain | Admin config | `semantic_table_config.domain_id` never read at query time; `_ANALYTICS_KEYWORDS` encodes a different DB's entities |
| Temporal strategy | `semantic_table_config` + `semantic_snapshot_mapping` | Three competing copies: DB table (authoritative), `DEFAULT_BINDINGS` (fallback), `prompt_builder:339` (hardcoded). |
| Valid dimension value | `dimension_value_index` / live DB | Respected ✅ — the one clean case |
| User intent | Extracted request | Partly violated — prior **SQL text** in the prompt competes with the current question (D7) |
| Conversation context | Explicit session state | Violated — no state object exists; raw text stands in (D8) |
| LLM interpretation | Proposal only | Violated at the largest scale: the LLM *writes the SQL* (D3), so it is the final authority on columns and joins |

**D3 is the deepest violation.** Every other item is a bounded fix. D3 is architectural: as
long as an LLM emits SQL from prose, the system's correctness ceiling is the model's
compliance, not the resolver's accuracy.

---

## 15. MULTI-USER / CONCURRENCY RISKS

| Risk | Assessment | Evidence |
|---|---|---|
| Cross-user session leakage | **Low** — `/ask` verifies `session.company_id == user.company_id` and division scope | app.py:408-419 |
| `conversation_store` keying | **Medium** — `defaultdict[employee_id][conversation_id]`, **no `connection_id`, no `company_id`** | conversation_memory.py:5,147 |
| Cross-connection history | **Medium-High** — if the active connection changes mid-session, history carries prior SQL written against a *different database*, and it is injected verbatim into the prompt | conversation_memory.py + prompt_builder.py:151 |
| Unbounded memory growth | **Medium** — `conversation_store` and `pending_clarification_store` are process-global dicts with **no eviction**; only clarification entries expire (300 s) | conversation_memory.py:5,183 |
| Value cache | **Low-Medium** — correctly keyed `(connection_id, version)`, but **unbounded**, and not invalidated when Gate 2 config changes | cache/dimension_cache.py |
| Thread-local `last_*` state | **Low, fragile** — `DimensionValueResolver` and `TemporalPipeline` use `threading.local()` correctly for sync workers, **but would break under async/await or a thread pool that reuses threads across requests** | dimension_value_resolver.py:53, temporal/pipeline.py:21 |
| Multi-worker consistency | **Medium** — all state is per-process; with >1 uvicorn worker, a user's clarification can land on a worker that lacks it, silently degrading to "invalid selection" | in-memory stores |

**Recommendations:**
1. Key conversation state on **`(company_id, employee_id, session_id, connection_id)`** and
   invalidate on connection change. Prevents cross-database context bleed.
2. Bound both stores (LRU + TTL).
3. Move `pending_clarification_store` to the database or a shared cache before running
   more than one worker. This is a correctness bug under horizontal scaling, not a nicety.
4. Add `connection_id` to the ConversationState key (§9) by construction.
5. Treat `threading.local()` as a constraint on the deployment model — document that the
   ask path must remain synchronous, or migrate to explicit context passing.

---

## 16. PERFORMANCE

Current measured path: intent LLM (frequently, due to D13) + SQL-generation LLM (always).

| Operation | Frequency | Est. latency | Cache | Sync? | Notes |
|---|---|---|---|---|---|
| metadata load (metrics+dims) | every query | 10–40 ms | **should cache** | yes | Currently uncached; two queries per ask |
| value index load | every query | 20–100 ms cold, ~0 warm | cached ✅ | yes | Unbounded — bound it |
| deterministic matching | every query | 5–30 ms | n/a | yes | Fast; keep on common path |
| temporal pipeline | every query | 5–15 ms | capability cached ✅ | yes | Fine |
| intent LLM (Stage 2) | **most queries** (D13) | 300–800 ms | keyword fix removes it | yes | Fix the keyword list ⇒ large win |
| **LLM escalation (new)** | **≤10% target** | 500–1500 ms | cache by (conn, normalised question) | yes | Budget: max 1/turn |
| SQL generation LLM | every query | 1–3 s | no | yes | Dominant cost |

**Targets:** common path unchanged or faster (fixing D13 removes an LLM call);
escalation ≤10% of queries; **hard budget of one escalation per turn**.

Two cheap wins available before any Gate 3 feature work: fix the keyword list (removes an
LLM round-trip from most queries) and cache the metadata load. Neither is on the Gate 3
critical path but both improve every query.

**Explicit constraint:** accuracy must not be bought with per-query LLM calls. Steps 17,
18, 19 and 21 are all solved deterministically in this design; the LLM tier exists only for
residual novelty.

---

## 17. FINAL PROPOSED ARCHITECTURE

The brief's suggested order needs **two changes**, both justified by the audit:
**scope resolution must precede metric/dimension resolution** (it is what makes domain
coherence computable and kills cross-domain false positives), and **conversation state must
be applied before resolution**, not after (otherwise follow-ups have nothing to resolve
against).

```
USER MESSAGE
  ↓
[0] REQUEST NORMALISATION          det.  case/punct/word-numbers/whitespace
  ↓
[1] CONVERSATION STATE RESOLUTION  det.  classify turn: NEW|REFINE|REPLACE|CLARIFY_REPLY
  │                                      load/merge/reset slots  (§9)
  ↓
[2] DOMAIN / TABLE SCOPE           det.  from carried state + config (semantic_domain,
  │                                      semantic_table_config). Narrows every later stage.
  ↓
[3] CANDIDATE EXTRACTION           det.  n-grams, spans, cue detection (by|in|for|per)
  ↓
[4] METRIC RESOLUTION              det.  exact→normalised→synonym→fuzzy(≥90)
  │                                      **filters is_excluded**
  ↓
[5] DIMENSION RESOLUTION           det.  same ladder + dimension_role from config
  ↓
[6] VALUE RESOLUTION               det.  existing matching pipeline (keep — it works)
  ↓
[7] SLOT ROLE ASSIGNMENT           det.  FILTER vs GROUPING (§8 rules) + dedup
  ↓
[8] TEMPORAL RESOLUTION            det.  TemporalPipeline + SnapshotConfig (authoritative)
  ↓
[9] CONFIDENCE + AMBIGUITY + NO-MATCH GATE   det.  §12 thresholds & margin
  │      ├─ accept       → [11]
  │      ├─ clarify      → clarification (existing machinery)
  │      └─ unresolved   → [10]
  ↓
[10] LLM ESCALATION TIER           LLM   shortlist-constrained, ≤1 call, schema-validated
  │      └─ validate against config+index → re-enter [9]; failure ⇒ NO_MATCH
  ↓
[11] SEMANTIC PLAN ASSEMBLY        det.  role-tagged slots, assumptions_made
  ↓
[12] PLAN VALIDATION               det.  every column exists, not excluded, in scope,
  │                                      temporal mapping ∈ SnapshotConfig
  ↓
VALIDATED PLAN → (SQL compile / guarded generation)
```

**Per stage:**

| # | Responsibility | In | Out | Type | Failure | Tests |
|---|---|---|---|---|---|---|
| 0 | normalise | raw text | normalised | det. | n/a | unit |
| 1 | turn class + slot merge | text, state | merged slots | det. | treat as NEW | unit + component |
| 2 | scope | slots, config | domain, tables | det. | all in-scope tables | unit |
| 3 | candidates | text | spans, cues | det. | empty ⇒ NO_MATCH | unit |
| 4 | metric | spans, config | metrics + conf | det. | unresolved slot | unit |
| 5 | dimension | spans, config | dims + role | det. | unresolved slot | unit |
| 6 | value | spans, index | values + conf | det. | unresolved slot | unit |
| 7 | roles | dims, values, cues | FILTER/GROUPING | det. | default + assumption | unit |
| 8 | temporal | text, table config | TimeContext | det. | default + assumption | unit (exists) |
| 9 | gate | all slots | ACCEPT/CLARIFY/NO_MATCH | det. | — | component |
| 10 | escalation | shortlist | proposals | **LLM** | NO_MATCH | integration + mocked |
| 11 | assemble | slots | SemanticPlan | det. | — | component |
| 12 | validate | plan, config | validated plan | det. | **reject, never repair** | integration |

**The decisive change:** stage 12 must be able to *reject*. Today nothing can stop a plan
from reaching SQL generation.

---

## 18. FINAL STRUCTURED DATA CONTRACT

Must express all seven brief examples without later stages re-reading the question.

```
SemanticRequest {
  request_id, connection_id, company_id, employee_id, session_id, turn_index
  raw_question, normalised_question
  turn_type: NEW_QUESTION | REFINEMENT | REPLACEMENT | CLARIFICATION_REPLY
  domain, primary_table, tables[]

  intent:      DESCRIPTIVE | COMPARATIVE | TREND | RANKING | DIAGNOSTIC | PRESCRIPTIVE
  query_shape: SINGLE_VALUE | DETAIL | RANKED_LIST | TREND | COMPARISON

  metrics[]   { table, column, business_name, aggregation, unit, confidence, evidence, source_span }
  filters[]   { table, column, business_name, operator, values[], confidence, evidence, source_span }
  groupings[] { table, column, business_name, dimension_role, confidence, evidence, source_span }

  temporal {
    intent, strategy: SNAPSHOT|DATE_COLUMN|NONE,
    period_scope: FULL|TO_DATE,
    snapshot_columns[], date_column, start_date, end_date, grain,
    comparison { baseline_offset, target_offset, scope_rule }   # CY vs PYTD
  }

  ranking    { top_n, direction, measure }
  comparison { left, right, mode }          # example 7
  diagnostic { target_metric, observed_change, candidate_dimensions[] }   # example 6

  resolution_status: RESOLVED | NEEDS_CLARIFICATION | NO_MATCH
  unresolved_terms[]                         # drives the NO_MATCH message
  clarification { type, options[] }
  confidence { plan, per_slot{}, method }
  assumptions_made[]                         # every default taken on the user's behalf
  provenance[] { stage, decision, source: CONFIG|INDEX|LLM|DEFAULT, evidence }
  carried_slots[]                            # which slots came from prior turns
}
```

**Coverage check against the brief's seven examples:**

| # | Example | Fields exercised |
|---|---|---|
| 1 | sales this year | metrics, temporal(CY, TO_DATE) |
| 2 | BANIANS sales last year | + filters[Product=BANIANS], temporal(PY, FULL) |
| 3 | BANIANS in TN by party last year | + filters[State=TN], **groupings[Party]** ← impossible today |
| 4 | monthly trend, Dhoti, last year | + query_shape=TREND, temporal.grain=MONTH |
| 5 | top 5 declining products last quarter | + ranking{5,DESC}, intent=RANKING, comparison |
| 6 | why did BANIANS sales fall | + intent=DIAGNOSTIC, diagnostic{} |
| 7 | BANIANS this year vs last year | + query_shape=COMPARISON, temporal.comparison{CY,PYTD} |

Example 3 is the one the current `SemanticPlan` structurally cannot represent, because
`dimensions` conflates filtering and grouping (§8). Example 7 depends on
`temporal.comparison.scope_rule` — Gate 2 Step 11b already computes this correctly; the
contract must carry it so it is not recomputed or lost.

---

## 19. LLM ROLE AND ESCALATION POLICY

**Recommended: Option C.** Full policy in §11. Summary of the guarantees:

1. **Deterministic first.** The LLM never runs while deterministic resolution succeeds.
2. **Shortlist-constrained.** The model chooses only from candidate IDs supplied to it. It
   cannot name a column, table, or value that was not offered. This is enforced by
   validation, not by prompt wording — the structural anti-hallucination guarantee.
3. **Validated after.** Every proposal is re-checked against configuration (`is_excluded`)
   and the live value index before entering the plan.
4. **Never authoritative** over physical columns, tables, values, temporal mappings, or SQL
   semantics.
5. **Confidence-capped** below any deterministic match (≤0.80).
6. **Budgeted:** ≤1 call/turn, 5 s timeout, 1 retry on malformed JSON only.
7. **Fails to NO_MATCH**, never to a guess.
8. **Fully audited** for regression harvesting.

**Note on the existing LLM usage.** The largest LLM authority in the system today is not
the proposed tier — it is `sql_generation`, which writes SQL directly (D3). Option C
constrains the *resolution* tier tightly while leaving that unaddressed. Closing D3
(compiling SQL from the validated plan, or moving the Gate 5 guard to enforce) is the
larger prize and should be sequenced deliberately (§23).

---

## 20. NO-MATCH / AMBIGUITY STRATEGY

Full definitions in §12. The three rules that matter most:

1. **An unresolved noun phrase blocks SQL.** No silent dropping. `NO_MATCH` names the term.
2. **Ambiguity margin < 0.10 ⇒ clarify**, even at high absolute confidence. Two plausible
   candidates is a question for the user, not a coin toss.
3. **Exact beats fuzzy, always**; fuzzy requires token ratio ≥75 **and** span coverage ≥0.6.

State machine: `RESOLVED` → proceed; `NEEDS_CLARIFICATION` → existing clarification
machinery (which is genuinely good — keep it); `NO_MATCH` → decline, naming the term, and
offer the nearest *configured* dimensions as a hint **without pre-selecting one**.

---

## 21. TEST ARCHITECTURE

**L1 Unit** (fast, no DB): normalisation; singular/plural; fuzzy thresholds; **role
assignment** (`by`/`in` cues); confidence formula; turn classification; `NO_MATCH`
triggering; the `laptop→top` / `stopped→top` rejections as permanent regressions.

**L2 Component** (fixture config, no live DB): resolver stages in isolation; exclusion
honoured; ambiguity margin; clarification generation; slot merge/reset across turns.

**L3 Integration** (fixture DB, mocked LLM): full pipeline to a validated plan; escalation
invoked only on deterministic miss; **LLM proposing an off-shortlist ID is rejected**;
plan validation rejects an excluded column.

**L4 Real-database benchmark:** golden v2, `(table, column)` identity assertions, primary-
cause tagging, two-layer scoring (§5).

**Adversarial suite — required assertions:**

| Input | Required output |
|---|---|
| `laptop sales` | `NO_MATCH` on "laptop"; **never** filter Product=TOP |
| `stopped orders` | not RANKED_LIST; `NO_MATCH` or clarify on "stopped" |
| `top sales` | RANKED_LIST; no value filter |
| `unknown product` | `NO_MATCH`, term named |
| `show sales in Mars` | `NO_MATCH` on "Mars" — **not** a total-sales answer (today's D2 failure) |
| `show sales by random_column` | `NO_MATCH` on grouping; no invented GROUP BY |
| `show BANIANS PY sales` | filter=BANIANS, temporal=PY **FULL** |
| `show BANIANS sales by party and state` | filter=BANIANS, groupings=[Party,State] — both, neither duplicated into filters |
| `show BANIANS sales in TN by party` | filter=[Product=BANIANS, State=TN], grouping=[Party] — **State not in groupings** |
| T1 BANIANS sales / T2 "now show order pendings" | domain resets; BANIANS **not** carried |
| T1 BANIANS sales / T2 "last year" / T3 "by party" | filter carried, time replaced, grouping added |

---

## 22. FILE OWNERSHIP MAP

| File | Current | Proposed | Action | Risk |
|---|---|---|---|---|
| `app.py` `/ask` (360-1000) | entry + clarification + orchestration, ~640 lines | thin orchestration | **Refactor** — extract clarification to a service | **Shared-risk**: RLS/CLS/audit live here |
| `ai/prompt_builder.py` | 1212 lines: orchestration + resolution + gating + prompt | prompt rendering only | **Refactor/split** | **Highest-risk file.** D7, D10, D12 all live here |
| `semantic/semantic_resolver.py` | name matching + confidence | name matching only; add exclusion filter + fuzzy tier | **Refactor** | Benchmark depends on output shape |
| `semantic/dimension_value_resolver.py` | value resolution | unchanged + exclusion filter | **Keep** | Works well |
| `semantic/matching/*` | matcher pipeline | unchanged | **Keep** | Proven (§4.2) |
| `semantic/semantic_gate.py` | status-only gate | confidence + margin + NO_MATCH | **Replace** | Small file, large effect |
| `semantic/semantic_plan_builder.py` | plan assembly | + role assignment, dedup | **Refactor** | Core of Step 17 |
| `semantic/models/semantic_plan.py` | plan schema | + groupings/filters split, provenance, NO_MATCH | **Refactor (additive)** | Gate 5 guard reads this |
| `semantic/temporal/*` | temporal | unchanged | **Keep** | Most mature subsystem |
| `semantic/temporal/snapshot_config.py` | Gate 2 11a/11b | sole authority | **Keep** | Remove `DEFAULT_BINDINGS` once tests inject config |
| `services/conversation_memory.py` | dict history + prior SQL | typed ConversationState | **Replace** | Steps 18 + §15 |
| `ai/intent_classifier.py` | AdventureWorks keywords + LLM | config-derived vocabulary | **Refactor** | Cheap perf win |
| `semantic/config_service.py` etc. | Gate 2 admin | unchanged | **Keep** | **Conflict risk — see below** |
| `test/semantic_benchmark/*` | v1 | v2 alongside | **Extend** | Keep v1 immutable |
| `semantic/singular_plural_matcher.py` (root) | dead duplicate | — | **Delete** | Verify no importer first |
| `semantic/matching.zip`, `temporal.zip` | archives | — | **Delete** | None |
| `semantic/diagnostic_trace.py` | `TEMP_..._REMOVE_LATER` | promote or remove | **Decide** | Currently useful |

**Conflicts with active Gate 2 work:**
- `semantic_plan.py` is read by the Gate 5 guard — additive changes only, or the guard breaks.
- `snapshot_config.py` has an open Gate 2 item (delete `DEFAULT_BINDINGS` once tests inject
  config). Gate 3 should not touch it until that lands.
- The Gate 2 UI exposes `is_excluded`/`dimension_role`. Fixing D1 makes those controls
  *actually take effect* — which will visibly change chatbot behaviour the moment it ships.
  Sequence it deliberately and tell the admin.
- Two Gate 2 items remain open and affect Gate 3 inputs: suggestions have not been
  regenerated for Order Pending and Receivables, and the duplicate `State*` columns are
  undecided. **Both should close before the Step 14 re-baseline**, or the benchmark
  measures a half-configured system.

---

## 23. IMPLEMENTATION SEQUENCE

Ordered to minimise rework. **Two prerequisites precede Step 14.**

**P0 — Fix D1 (exclusion/confirmation/role honoured).** *Not formally a Gate 3 step, but
everything downstream is measured against a system that ignores its own configuration.*
Files: `semantic_resolver.py`, `dimension_value_resolver.py`,
`dimension_value_index_builder.py`. Tests: L2 exclusion honoured. DB: none. UI: none.
Rollback: low (additive WHERE clauses). **Acceptance:** an excluded column never appears in
any resolution result.

**P1 — Close Gate 2 open items.** Regenerate suggestions for Order Pending + Receivables;
decide the `State*` duplicates. Requires office network. **Acceptance:** all three tables
fully configured.

**Step 16 — Expectation validity.** *Before* re-baselining. Triage all 194 cases A–E;
re-express metric expectations as `(table, column)`. Files: benchmark JSON + runner.
Rollback: none (v1 kept immutable). **Acceptance:** every case has a recorded verdict and
rationale.

**Step 15 — Failure taxonomy + primary-cause diagnosis.** Files: runner only.
**Acceptance:** every failure carries exactly one primary code; multi-code cases → 0.

**Step 14 — Re-baseline.** Now meaningful. Files: runner, results. **Acceptance:** a
trustworthy pass rate per category, with A-class defects isolated from B-class noise.

**Step 21 — NO_MATCH + confidence gate.** Do this *before* 17/18: it is the largest
correctness win and the safety net every later step relies on. Files: `semantic_gate.py`
(replace), `semantic_resolver.py` (real confidence), plan schema (NO_MATCH state).
Tests: adversarial suite. **Rollback: medium — this makes the system decline questions it
previously answered.** Ship behind a flag; compare decline rate against the golden set.
**Acceptance:** NO_MATCH_ADVERSARIAL ≥90%; no regression elsewhere.

**Step 17 — Multi-slot roles.** Files: `semantic_plan_builder.py`, `semantic_plan.py`
(additive), candidate extraction. **Acceptance:** MULTI_DIMENSION ≥80%; "in TN by party"
yields State∈filters, Party∈groupings, State∉groupings.

**Step 19 — Linguistic variation.** Small after 17/21: add the name-level fuzzy tier, move
word-number normalisation out of the clarification branch, rely on admin `synonyms`.
**Acceptance:** SINGULAR_PLURAL and TYPO_FUZZY ≥85% (they should jump on Step 16 alone —
measure the delta to confirm the §10 diagnosis).

**Step 18 — Conversation state.** Largest behavioural change; do it after slots are
role-tagged, since it carries slots. Files: `conversation_memory.py` (replace),
`prompt_builder.py` (stop injecting raw SQL — D7), `app.py`. **DB: likely yes** if
clarification state moves out of process (§15). **Rollback: high.** **Acceptance:**
FOLLOW_UP + ENTITY_TOPIC_SHIFT ≥80%; no cross-domain leakage.

**Step 20 — LLM escalation tier.** Last, because it is only worth building once the
deterministic floor is known — the escalation rate *is* the measure of residual failure.
Files: new resolver tier + `LLMExecutionService` purpose. **Acceptance:** escalation ≤10%
of queries; off-shortlist proposals always rejected; net accuracy gain demonstrated.

**Deliberately deferred: D3 (plan authority).** Compiling SQL from the validated plan, or
moving the Gate 5 guard to enforce, is the highest-value remaining change but is a
separate architectural commitment with its own risk profile. Steps 14–21 are all
prerequisites for it: an authoritative plan is only safe once the plan is correct.
**Recommend scheduling it immediately after Gate 3, not within it.**

---

## 24. ACCEPTANCE CRITERIA

| Step | Criterion |
|---|---|
| P0 | Excluded columns absent from all resolution output; `dimension_role` honoured |
| P1 | All three tables configured; duplicate columns decided |
| 16 | 100% of cases carry a verdict A–E with rationale; no silent edits |
| 15 | Every failure = exactly one primary code; cascading count 0 |
| 14 | Trustworthy per-category baseline published |
| 21 | Adversarial ≥90%; unresolved term never silently dropped; every threshold documented |
| 17 | MULTI_DIMENSION ≥80%; no dimension in both filters and groupings |
| 19 | SINGULAR_PLURAL + TYPO_FUZZY ≥85% |
| 18 | FOLLOW_UP + TOPIC_SHIFT ≥80%; zero cross-domain leakage; no raw SQL in prompt |
| 20 | Escalation ≤10%; off-shortlist rejection 100%; measurable net gain |
| All | Common-path latency not worse than today; every plan carries `provenance` and `assumptions_made` |

---

## 25. RISKS AND TRADE-OFFS

| Risk | Severity | Mitigation |
|---|---|---|
| **Step 21 makes the system decline more** — previously "answered" questions now say NO_MATCH | High | This is *correct* (they were wrong answers), but will read as regression. Flag it; measure decline rate; communicate before shipping. |
| `prompt_builder.py` is 1212 lines and central | High | Incremental extraction; keep its public signature; L3 integration tests before each move |
| Step 18 changes conversation behaviour broadly | High | Flag; shadow-compare slot decisions before enforcing |
| Fixing D1 visibly changes chatbot behaviour | Medium | Expected and desired — but tell the admin, since their exclusions suddenly take effect |
| Benchmark v2 not comparable to v1 | Medium | Keep v1 immutable; report both during transition |
| Thresholds in §12 are starting values, not proven | Medium | Tune against v2; record every change with its effect |
| Multi-worker deployment breaks in-memory clarification | Medium | Must be fixed before scaling out (§15) |
| LLM tier becomes a crutch | Medium | Hard budget; escalation rate is a tracked metric, not an accepted cost |
| D3 left open through Gate 3 | **Accepted** | Deliberate; scheduled immediately after |

**Principal trade-off:** this design chooses determinism over coverage. It will decline
questions an LLM-first design would attempt. For a financial analytics product where a
confidently wrong number is worse than "I don't know", that is the right trade — and it is
the direct consequence of the stated goal that accurate retrieval matters "very very much".

---

## 26. DECISIONS TO FREEZE BEFORE CODING

1. **Plan authority (D3).** Confirm: Gate 3 leaves SQL generation LLM-driven, and plan
   authority is tackled immediately after. *If this is wrong, the whole sequence changes.*
2. **Option C** (deterministic-first + validated escalation) is the chosen architecture.
3. **No embeddings in Gate 3** (§10 rationale).
4. **Step order: 16 → 15 → 14 → 21 → 17 → 19 → 18 → 20**, with P0/P1 first.
5. **P0 (fix D1) is in scope** and ships before the re-baseline.
6. **Benchmark asserts `(table, column)` identity**, not display names.
7. **Thresholds:** accept 0.85 / clarify 0.60 / margin 0.10 / fuzzy token 75 + span 0.6 —
   adopted as *starting* values, tuned against v2, every change logged.
8. **NO_MATCH blocks SQL.** No silent term-dropping. Accept the higher decline rate.
9. **Escalation budget: 1 LLM call/turn, 5 s, ≤10% of queries.**
10. **Conversation state keyed on `(company_id, employee_id, session_id, connection_id)`**;
    raw prior SQL is never injected into the prompt again.
11. **Clarification state must leave process memory** before multi-worker deployment.
12. **Gate 2 items P1 close first** — otherwise the baseline measures a half-configured system.
13. **Tamil-English mixed language: explicitly out of scope** for Gate 3 unless traffic shows otherwise.
14. **`SemanticPlan` changes are additive only** while the Gate 5 guard reads it.

---

### Audit method note

Findings are grounded in file:line references from the audited commit and, where behaviour
was in question, in read-only reproduction (rapidfuzz matcher behaviour, ranking-cue
regexes) and the committed benchmark results. Two hypotheses I held at the outset were
**disproved by that testing** and are corrected in the body: the `laptop→top` /
`stopped→top` false positives are already blocked by the token-evidence guard (§4.2), and
SINGULAR_PLURAL's 5.6% is caused by stale metric expectations rather than by the
singular/plural matcher (§10). No production code, migration, data, or frontend file was
modified in the course of this audit.
