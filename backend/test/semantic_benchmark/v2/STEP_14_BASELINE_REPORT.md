# Step 14 — Gate 3 Baseline

First trustworthy post-Gate-2 baseline, measured against the authoritative
Step 16 v2 benchmark. **Measurement only** — no production code, configuration,
database, benchmark expectation, Step 16 verdict or Step 15 taxonomy was
modified.

Run id `20260901T160909` · benchmark **v2** · connection `Chatbot`
(`F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`).

---

## 1. Executive Summary

**Semantic/retrieval accuracy: 47 / 190 = 24.74%** over all evaluable cases.
**Among cases the schema can actually execute: 35 / 84 = 41.67%.**

Neither figure is comparable to the historical 26.84%. That run predates Gate 2,
P0 and P1, and scored against v1 expectations — several of which named
configuration the business has since deliberately switched off. A three-point
decomposition is given in §10 rather than a single "improvement" claim.

Three results carry most of the signal:

- **Step 16's classification is validated.** All 42 `VALID` cases pass — 42/42,
  no exceptions. Every one of the 30 `B` and 26 `E` cases fails, exactly as
  their verdicts predict. The benchmark now says what it means.
- **Step 15's taxonomy is confirmed.** Of the 92 `A` cases, 87 still fail and
  each fails with its predicted root cause. The 5 that now pass are precisely
  the 5 marked `RC-08 UNRESOLVED — stale diagnostic`, which was the prediction.
  No diagnosis required revision.
- **Zero execution errors.** All 194 cases evaluated or deliberately skipped.

The gap between 24.74% and 41.67% is the honest measure of how much of this
benchmark the current *schema* cannot answer regardless of resolver quality.

---

## 2. Environment / Configuration Tested

| | |
|---|---|
| Connection | `Chatbot` · `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5` |
| Platform DB | SQL Server `192.168.0.187/RR_Platform` |
| Gate 3 P0 | **active** — exclusion + `INTERNAL` role filters applied |
| Metrics | 20 active, 2 excluded, 20 confirmed |
| Dimensions | 83 active, 10 excluded, 73 confirmed |
| Value index | 8,550 rows across 63 dimensions |
| Verified joins | **0** for this connection |

---

## 3. Benchmark Version

Step 16 v2 — `v2/golden_dataset_v2_c1..c6.json`, 194 cases.

The existing `run_retrieval_benchmark.py` loads **v1** and writes to `results/`;
neither was touched. `v2/run_v2_baseline.py` imports that runner's
`evaluate_case` **unchanged** — identical comparison contract — and only swaps
the dataset for v2 and the output to `v2/baseline_runs/<run_id>/`.

---

## 4. Total Cases

| | |
|---|---:|
| Total | 194 |
| Evaluable | 190 |
| Skipped (`D`, FUTURE_PHASE) | 4 |
| Execution errors | **0** |

---

## 5. Semantic / Retrieval Accuracy

| | |
|---|---:|
| Passed | **47** |
| Failed | **143** |
| **Accuracy (all evaluable)** | **24.74%** |
| **Accuracy (`data_answerable = yes` only)** | **41.67%** (35/84) |

By Step 16 verdict — verdicts unchanged, shown only as a cross-tab:

| Verdict | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| VALID | **42** | 0 | 0 |
| A | 5 | 87 | 0 |
| B | 0 | 30 | 0 |
| E | 0 | 26 | 0 |
| D | 0 | 0 | 4 |

`VALID` scoring 42/42 and `B`/`E` scoring 0/56 is the strongest available
evidence that Step 16's triage was correct: cases predicted to pass all pass,
and cases whose expectations were judged invalid or undefined all fail.

---

## 6. Runtime / Execution Errors

**None.** No case crashed, hung, or was silently skipped. The 4 skips are the
`FUTURE_PHASE` cases the dataset marks as intentionally unsupported.

---

## 7. Data Answerability

| `data_answerable` | PASS | FAIL | SKIP | Total |
|---|---:|---:|---:|---:|
| yes | 35 | 49 | 4 | 88 |
| no | 12 | 84 | 0 | 96 |
| partial | 0 | 10 | 0 | 10 |

- **VALID but not executable: 12.** Retrieval is correct and the query cannot be
  built — the metric and dimension live on different tables with no verified
  join.
- **A and not executable: 45.** Two independent faults in one case: the resolver
  missed an achievable expectation, *and* the schema could not have executed it.

**This is not an accuracy figure and must not be reported as one.** 106 of 194
cases (55%) are wholly or partly unexecutable against the current schema. That
is a data-modelling fact, independent of the resolver.

---

## 8. Root-Cause Failure Distribution

Step 15 taxonomy, applied to the 143 failures:

| Root cause | Count | % of failures |
|---|---:|---:|
| *(not an A case — B and E failures)* | 56 | 39.2% |
| RC-02 Ambiguity overridden by unmatched-token heuristic | 23 | 16.1% |
| RC-03 Synonym specificity not weighted | 21 | 14.7% |
| RC-04 Name matcher has no morphology | 10 | 7.0% |
| RC-01 `NO_MATCH` not enforced | 10 | 7.0% |
| RC-06 Value matcher accepts weak candidates | 9 | 6.3% |
| RC-07 No confidence model | 9 | 6.3% |
| RC-05 Retrieval status is a bucket count | 5 | 3.5% |
| **Total** | **143** | |

The 87 A-case failures distribute exactly as Step 15 predicted
(23+21+10+10+9+9+5 = 87). The 56 remaining failures are the `B` and `E` cases,
which Step 15 deliberately did not analyse — their expectations are known to be
incorrect or undefined, so they are not software defects.

Raw failure codes observed: `wrong ambiguity` 105 · `wrong value` 63 ·
`wrong dimension` 40 · `wrong metric` 37 · `wrong retrieval status` 22.

### Diagnosis changed after re-run

**5 cases** — `E1-013, E1-014, E1-086, E1-090, E1-109`. All were classified
`RC-08 UNRESOLVED — stale diagnostic`, on the reasoning that their recorded
failure compared a pre-correction `pendamt` expectation against an actual that
already matched the corrected `P A M T`. **All five now pass.** The diagnosis is
confirmed and resolved: they were never defects.

No other case's diagnosis changed. Step 15 was not rewritten.

---

## 9. Case-Level Result Summary

| Category | Pass | Fail | Rate |
|---|---:|---:|---:|
| AMBIGUOUS_VALUES | 14 | 4 | 77.8% |
| PARTIAL_COVERAGE | 9 | 9 | 50.0% |
| SIMPLE_METRIC | 7 | 11 | 38.9% |
| METRIC_DIMENSION_VALUE | 8 | 14 | 36.4% |
| TYPO_FUZZY | 5 | 13 | 27.8% |
| EXPLICIT_DIMENSION | 3 | 15 | 16.7% |
| SINGULAR_PLURAL | 1 | 17 | 5.6% |
| MULTI_DIMENSION | 0 | 18 | **0.0%** |
| FOLLOW_UP | 0 | 10 | **0.0%** |
| NO_MATCH_ADVERSARIAL | 0 | 10 | **0.0%** |
| METRIC_SHIFT | 0 | 8 | **0.0%** |
| ENTITY_TOPIC_SHIFT | 0 | 8 | **0.0%** |
| TEMPORAL_QUESTIONS | 0 | 6 | **0.0%** |

Six categories score zero. Those are whole capabilities, not scattered defects.

---

## 10. Comparison With Historical Baseline

Three measurement points, each isolating one variable:

| Point | Software | Configuration | Expectations | Accuracy |
|---|---|---|---|---:|
| Aug 18 historical | pre-Gate-2 | pre-Gate-2 | v1 | 51/190 = **26.84%** |
| Step 16 diagnostic | current | current | v1 | 42/190 = **22.11%** |
| **Step 14 baseline** | current | current | **v2** | 47/190 = **24.74%** |

**26.84% → 22.11% (−4.73 pts) is not a software regression.** Software and
configuration both changed here, but the dominant effect is that v1 expectations
name configuration the business has since deliberately switched off — `pendamt`
excluded, `createddate` dimensions removed by Gate 2 Step 12. The benchmark was
penalising the system for honouring admin decisions.

**22.11% → 24.74% (+2.63 pts) is benchmark correction only.** Both runs use the
same software and configuration; only the expectations differ. The gain is
precisely the 5 `P A M T` cases (5/190 = 2.63 pts). Arithmetically exact.

**The historical 26.84% is not comparable to 24.74%** and should not be quoted
alongside it. Different software, different configuration, different
expectations. The only defensible statement is that **24.74% is the first
baseline measured against expectations verified to be correct**.

No evidence in this run supports a claim of software improvement. P0 and P1
fixed configuration *enforcement* and unblocked the review queue; neither
targeted retrieval accuracy, and neither shows up as one.

---

## 11. Interpretation Cautions

1. **Do not report 41.67% as system accuracy**, nor 24.74% as capability. The
   first excludes questions the schema cannot answer; the second includes them.
2. **Answerability is not accuracy.** 55% of cases being unexecutable is a
   data-modelling finding, not an AI result.
3. **The benchmark measures one component.** It calls only
   `SemanticResolver.resolve()`. `SemanticPlanBuilder`, `prompt_builder`, the
   SQL guard and `/ask` are **not exercised** — so the hardcoded `"Sales"`,
   `CY`/`PY` assumptions there are unmeasured. This baseline says nothing about
   them, good or bad.
4. **56 failures are known-invalid expectations**, not defects. Excluding `B`
   and `E`, the software-defect failure count is 87.
5. **The SQL guard is in shadow mode**, so no plan-conformance enforcement was
   in effect. Unchanged from previous runs.

---

## 12. Highest-Impact Remaining Problems

1. **Six categories at 0%** — MULTI_DIMENSION (18), FOLLOW_UP (10),
   NO_MATCH_ADVERSARIAL (10), METRIC_SHIFT (8), ENTITY_TOPIC_SHIFT (8),
   TEMPORAL_QUESTIONS (6). 60 cases, whole capabilities absent rather than
   degraded.
2. **`NO_MATCH` is still ignored** — verified in this run: all 10 adversarial
   cases return a metric (`['C Y']`) for questions naming entities that do not
   exist. Unchanged.
3. **Follow-up, metric-shift and topic-shift: 0/26.** Step 15 attributed these
   to RC-02 and RC-03 — the words "now" and "instead" trip the unmatched-token
   heuristic — not to context handling. That attribution is unchanged here.
4. **MULTI_DIMENSION 0/18** — filter-versus-grouping remains entirely
   unaddressed, as the Gate 3 audit predicted.
5. **RC-02 + RC-03 = 44 of 87 defect failures (51%).**

**Confidence and ambiguity behaviour is now measurable**: `wrong ambiguity`
appears in 105 failures and, thanks to Step 15, decomposes into RC-02 (23),
RC-07 (9) and downstream effects rather than being a single opaque bucket.

---

## 13. Recommended Next Implementation Priorities

Not started here. In dependency order:

1. **RC-07, a real confidence model (Step 21).** RC-02, RC-05 and RC-06 all
   consume a signal that does not exist; building them first means rebuilding
   them.
2. **RC-01, give `NO_MATCH` a consumer (Step 21).** 10 cases, single mechanism —
   the status is already produced correctly and read by nothing.
3. **RC-02, shared token-coverage state (Step 21 + Step 17).** 23 cases.
4. **RC-03's configuration half — a Gate 2 admin task with no current owner.**
   `C Y` carries synonyms `amount`, `revenue`, `sales`, `hand typed`;
   `Prod Grp4` carries `category`. Correcting these needs no code change.
5. **RC-04, morphology on the name matcher (Step 19).** 10 cases; the
   `SingularPluralMatcher` already exists on the value path.
6. **MULTI_DIMENSION (Step 17)** — 18 cases, currently 0%.

Separately, and not a resolver task: **106 cases are unexecutable**. Adding a
verified join path or the missing fields would raise the executable ceiling more
than any resolver change.

---

## 14. Reproducibility

```
python backend/test/semantic_benchmark/v2/run_v2_baseline.py
```

Writes `v2/baseline_runs/<timestamp>/results.json` — per case: expected, actual,
pass/fail, failure codes and details, retrieval status, resolved metrics,
dimensions and values, duration, Step 16 verdict, `data_answerable`, and the
Step 15 root cause. Existing runs are never overwritten.

This run: `v2/baseline_runs/20260901T160909/` (`results.json`, `summary.json`).

Dependencies: live connection `Chatbot` on `192.168.0.187/RR_Platform` with the
configuration in §2. Results will differ if configuration changes — in
particular RC-03 depends on synonym text that an administrator can edit.
