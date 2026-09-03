# Gate 3 — authoritative benchmark baseline

**This file, and `authoritative_baseline.json` beside it, are the current Gate 3
measurement.** The v1 artifact under `../results/` is historical and is labelled
as such; do not quote 51/190 as a current figure.

| | |
|---|---|
| Benchmark | v2 (Step 16 authoritative) |
| Comparison contract | identity — `(table_name, column_name)` |
| Runner | `run_v2_baseline.py` (unchanged) |
| Commit | `2b8d98ff1d1f08df4d867b5b2571e86feaeb0e90` |
| Connection | `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5` |

## The number

```
cases loaded    194
scored          190
unsupported       4   (E1-196, E1-197, E1-198, E1-199 — FUTURE_PHASE)
PASS             82
FAIL            108
errors            0

AUTHORITATIVE BASELINE = 82/190 = 43.16%
```

## Read this before quoting the number

The two runs below were produced by **identical resolver code**. Nothing in
`semantic/`, `ai/`, the semantic configuration, or the benchmark runner changed
between them. Only benchmark expectations changed.

| | Run | PASS | Rate |
|---|---|---:|---:|
| Pre-reconciliation — the measured software baseline | `20260903T113105` | 66/190 | 34.74% |
| Post-reconciliation — this artifact | `20260903T122636` | 82/190 | 43.16% |
| Delta | | **+16** | **+8.42 pts** |

**The +16 is a benchmark expectation reconciliation gain, not a software
accuracy improvement.** Every one of the sixteen cases was already behaving
correctly; the benchmark was asserting the behaviour Gate 3 had deliberately
replaced. The pre-reconciliation 66/190 was verified reproducible — two
consecutive runs were bit-identical across `pass_fail`, `failure_codes` and the
`actual` payloads.

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
| PENDING EVALUATOR CONTRACT FIX | systemic — see below |

## Where the remaining 108 failures sit

| Category | Pass | | Category | Pass |
|---|---|---|---|---|
| AMBIGUOUS_VALUES | 13/18 | | METRIC_SHIFT | 4/8 |
| SIMPLE_METRIC | 11/18 | | ENTITY_TOPIC_SHIFT | 2/8 |
| METRIC_DIMENSION_VALUE | 11/22 | | **FOLLOW_UP** | **0/10** |
| PARTIAL_COVERAGE | 11/18 | | **MULTI_DIMENSION** | **0/18** |
| SINGULAR_PLURAL | 11/18 | | **TEMPORAL_QUESTIONS** | **0/6** |
| NO_MATCH_ADVERSARIAL | 7/10 | | | |
| EXPLICIT_DIMENSION | 6/18 | | | |
| TYPO_FUZZY | 6/18 | | | |

Failure codes: `wrong value` 77 · `wrong ambiguity` 75 · `wrong dimension` 44 ·
`wrong metric` 22 · `wrong retrieval status` 18.

**`wrong dimension` remains inflated.** `evaluate_v2._identity_set` unions every
physical table carrying an expected dimension name, so a case whose dimension
exists on several tables can only pass if the resolver returns all of them —
the opposite of the single-table selection 17a and RC-07 exist to perform.
E1-126 and E1-145 were corrected individually here; the general contract was
deliberately **not** changed, because that is an evaluator-design decision and
does not belong in an expectation reconciliation. 44 of the 108 remaining
failures still carry the code.

## Reproducing

```bash
python backend/test/semantic_benchmark/v2/validate_v2.py
python backend/test/semantic_benchmark/v2/run_v2_baseline.py
```

The runner writes a new timestamped directory under `baseline_runs/` and
overwrites nothing.
