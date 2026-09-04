# Gate 3 — authoritative benchmark baseline

**This file, and `authoritative_baseline.json` beside it, are the current Gate 3
measurement.** The v1 artifact under `../results/` is historical and is labelled
as such; do not quote 51/190 as a current figure.

| | |
|---|---|
| Benchmark | v2 (Step 16 authoritative) |
| Comparison contract | identity — `(table_name, column_name)` |
| Runner | `run_v2_baseline.py` (unchanged) |
| Resolver commit | `2b8d98ff1d1f08df4d867b5b2571e86feaeb0e90` |
| Connection | `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5` |

## The number

```
cases loaded    194
scored          190
unsupported       4   (E1-196, E1-197, E1-198, E1-199 — FUTURE_PHASE)
PASS             92
FAIL             98
errors            0

AUTHORITATIVE BASELINE = 92/190 = 48.42%     run 20260903T130444
```

## Read this before quoting the number

**All three runs below were produced by identical resolver code.** Nothing in
`semantic/`, `ai/`, `confidence.py`, `table_affinity`, the Pareto logic, the
semantic configuration, or the benchmark runner changed between them.

| | Run | PASS | Rate | What changed |
|---|---|---:|---:|---|
| Measured software baseline | `20260903T113105` | 66/190 | 34.74% | — |
| After expectation reconciliation | `20260903T122636` | 82/190 | 43.16% | **+16** benchmark expectation reconciliation gain |
| After RC-07 evaluator-contract fix | `20260903T130444` | 92/190 | 48.42% | **+10** evaluator-contract reconciliation gain |

**Neither gain is a software accuracy improvement.** The +16 came from
correcting expectations that asserted behaviour Gate 3 had deliberately
replaced. The +10 came from `evaluate_v2` no longer demanding that the resolver
return every physical copy of a replicated dimension — a demand that
contradicted the ratified RC-07 ruling and made a correct answer
unrepresentable. The honest statement of resolver accuracy over this period is
that **it did not change**; what changed is that the benchmark now measures it.

The 66/190 baseline was verified reproducible — two consecutive runs were
bit-identical across `pass_fail`, `failure_codes` and the `actual` payloads.

## RC-07 — ratified, and what the evaluator now checks

Ruling: when a business dimension is replicated across tables (`Division` is
identical on all three — same name, same synonyms, same GROUPING role,
confirmed, same ten values), the resolver may select one physical copy, and
normally selects the one on the resolved metric's table. Table affinity may
resolve among replicas; it must never resolve between different dimensions,
never override an explicit dimension qualifier, and never collapse genuine
City-vs-District or Division-vs-btype ambiguity.

`evaluate_v2._identity_satisfied()` implements the matching half of that, per
expected business name rather than against a flattened union:

* every actual identity must be an allowed copy of some expected name;
* every expected name must be matched by exactly one actual identity;
* nothing left over on either side.

A single-table expectation therefore behaves exactly as the old equality test.
`Division`-expected / `btype`-actual still fails, `City`-expected /
`District`-actual still fails, and an empty actual set can only satisfy an
empty expectation. Value multiplicity is dropped on both sides, because a
replicated dimension repeats the same string once per copy and two identical
strings are indistinguishable to this comparison; candidate *count* is still
measured by the ambiguity-status check, which is untouched — E1-097 and E1-098
still fail on STRONG vs WEAK, exactly as they should.

Pinned by `backend/test/test_rc07_evaluator_contract.py` (26 tests).

`FAIL → PASS` (16): E1-015, E1-016, E1-034, E1-084, E1-119, E1-126, E1-127,
E1-128, E1-129, E1-130, E1-131, E1-132, E1-133, E1-134, E1-135, E1-145.
`PASS → FAIL`: none.

## What changed in the expectations, and why

26 cases. Every change carries a `change_log` entry in the dataset, and the
original v1 expectation is preserved in `expectation_review.original_expected`.

| Group | Cases | Change | Basis |
|---|---|---|---|
| RC-03a | E1-015, E1-016, E1-034 | metric → `PBI_OUTSTANDING_ENES_SUMMARY.billamt` | Approved ruling: "bill amount" → `billamt` |
| RC-03a | E1-084 | metric → `QB_MDJMD_SALES_5YRS_SUMMARY.CY` | Approved ruling: "sales amount" → `C Y` |
| RC-03a | E1-019 | metric → `PBI_OUTSTANDING_ENES_SUMMARY.PAMT` (status untouched) | Approved ruling: "payment amount" → Pending Amount |
| RC-03b | E1-017, E1-018, E1-035 | metric → `PBI_OUTSTANDING_ENES_SUMMARY.PAMT` | Approved ruling: "due amount" → Pending Amount. **Expected to fail until RC-03b is implemented** |
| 21d | E1-119 | status `PARTIAL_MATCH` → `WEAK_AMBIGUITY` | `total` became a verified filler word in 21d, so it is no longer a dangerous unmatched token. Closes the open action in `STEP_21D_E1119_CONFLICT.md` |
| 19b | E1-127 – E1-135 | duplicate value removed; status → `SINGLE_MATCH` | The duplicate was the same value on the other geographic dimension, which the plural qualifier correctly drops |
| 19b / 17a | E1-126 | values → `["VT"]`; dimension identity → `QB_MDJMD_SALES_5YRS_SUMMARY.Division` | The fourth `VT` was `btype`, a different dimension; the rest was one dimension across three tables |
| 17a | E1-145 | values → `["MARKETING"]`; dimension identity → `QB_MDJMD_SALES_5YRS_SUMMARY.Category` | Two of the five values belonged to `MktType`/`Mkt_Type2`. `Category` holds only `MARKETING` and `OTHERS` |
| 21f | E1-137 – E1-142 | value → the city the user actually named; status → `SINGLE_MATCH` | The old expectation demanded `ELECTRONIC CITY` *instead of* the named city. **Expected to fail until the qualifier-token / fuzzy-value defect is fixed** |

### Deliberately left unchanged

| Marker | Cases |
|---|---|
| PENDING QUALIFIER-REFUSAL RULING | E1-042, E1-060, E1-114, E1-146, E1-168, E1-173 |
| PENDING RAMRAJ BUSINESS RULING | 26 cases, all verdict `E` |
| PENDING AMBIGUITY-STATUS RULING | E1-019 (now isolated: it fails on status alone) |
| RE-AUTHOR / RE-CATEGORIZE REQUIRED | E1-185, E1-186 |
| PENDING TEMPORAL/DIMENSION REVIEW | E1-020, E1-021 |
| ~~PENDING EVALUATOR CONTRACT FIX~~ | **resolved** — see the RC-07 section above |

## Where the remaining 98 failures sit

| Category | Pass | | Category | Pass |
|---|---|---|---|---|
| METRIC_DIMENSION_VALUE | 14/22 | | NO_MATCH_ADVERSARIAL | 7/10 |
| AMBIGUOUS_VALUES | 13/18 | | TYPO_FUZZY | 7/18 |
| SIMPLE_METRIC | 11/18 | | ENTITY_TOPIC_SHIFT | 2/8 |
| PARTIAL_COVERAGE | 11/18 | | **FOLLOW_UP** | **0/10** |
| SINGULAR_PLURAL | 11/18 | | **MULTI_DIMENSION** | **0/18** |
| EXPLICIT_DIMENSION | 10/18 | | **TEMPORAL_QUESTIONS** | **0/6** |
| METRIC_SHIFT | 6/8 | | | |

Failure codes: `wrong value` 64 · `wrong ambiguity` 75 · `wrong dimension` 11 ·
`wrong metric` 22 · `wrong retrieval status` 18.

**`wrong dimension` fell 44 → 11, and all 11 are genuine:** the `createddate`
temporal expectations (E1-022, E1-023, E1-190, E1-191, E1-192, E1-194, E1-195),
the `docdate` leak on E1-020/E1-021, and E1-060/E1-072, where the resolver
selected a replica that is **not** in the expected set — proof the contract is
still strict about which copies are allowed.

The three largest remaining clusters are untouched by any of this work:
follow-up metric carry-over (0/10), MULTI_DIMENSION (0/18) and the per-table
temporal capability (0/6).

## Reproducing

```bash
python backend/test/semantic_benchmark/v2/validate_v2.py
python backend/test/semantic_benchmark/v2/run_v2_baseline.py
```

The runner writes a new timestamped directory under `baseline_runs/` and
overwrites nothing.
