# Step 16 — final consistency pass: verdict vs data_answerable

This pass separates two things that had become entangled and applies the
joinability rule uniformly to all 194 cases. It supersedes the verdict counts in
`STEP_16_EXPECTATION_VALIDITY_REPORT.md` and
`STEP_16_RAMRAJ_PAMT_RESOLUTION.md`; the evidence and reasoning in those files
still stand.

## The rule applied

**`verdict`** — is the benchmark's semantic/retrieval expectation valid, and did
the resolver meet it? Values `A / B / C / D / E / VALID`.

**`data_answerable`** — can the current physical schema execute the requested
answer? Values `yes / no / partial`.

They are computed independently. Answerability is never consulted when deciding
a verdict, and a verdict never sets answerability.

Joinability rule, applied to every case: if the expected metric is on table T1
and an expected dimension is on a different table T2 with no verified join
between them, that is recorded in `data_answerable` and `missing_data`. **It
does not make the case a software defect, and it does not change the verdict.**

`schema_relationships` holds 97 rows overall but **0 for this connection**, and
`semantic_relationships` holds 0. No join was invented or inferred.

### Why the previous pass was wrong

The RAMRAJ resolution let joinability decide the verdict, producing 18 `C`s. But
12 cross-table cases *pass* retrieval, which proves joinability does not prevent
retrieval succeeding — the resolver correctly names metric and dimension; only
the SQL is impossible. Worse, 44 cases with the identical fault were still
sitting on `A`, so the same defect was classified two different ways depending
on whether the case mentioned RAMRAJ.

## Before and after

| Verdict | Before | After | Δ |
|---|---:|---:|---:|
| VALID | 42 | 42 | — |
| A | 83 | **92** | +9 |
| B | 36 | **30** | −6 |
| C | 18 | **0** | −18 |
| E | 11 | **26** | +15 |
| D | 4 | 4 | — |
| **Total** | 194 | **194** | |

`C` falls to zero, and that is the point: every case previously filed there was
blocked by a *join*, not by absent data, so the blocker belongs in
`data_answerable`. `C` remains available for a genuine data limitation — an
expected value that exists nowhere and resembles nothing — and no case currently
meets that bar.

| data_answerable | Cases |
|---|---:|
| yes | **88** |
| no | **96** |
| partial | **10** |

**96 of 194 cases (49%) cannot be executed against the current schema**, and 10
more only partially. This is independent of resolver quality.

## The two axes, crossed

| verdict | yes | no | partial |
|---|---:|---:|---:|
| VALID | 30 | **12** | 0 |
| A | 47 | **45** | 0 |
| B | 7 | 23 | 0 |
| E | 0 | 16 | 10 |
| D | 4 | 0 | 0 |

### VALID + `data_answerable = no` — 12 cases

Retrieval is correct; the query cannot be built.

```
E1-024  Show sales for Chennai city
        C Y → QB_MDJMD_SALES_5YRS_SUMMARY.CY
        City → PBI_OUTSTANDING_ENES_SUMMARY.City
        missing_data: City on QB_MDJMD_SALES_5YRS_SUMMARY, or a verified
                      join path from QB_MDJMD_SALES_5YRS_SUMMARY to
                      PBI_OUTSTANDING_ENES_SUMMARY
```
Also `E1-025` (Qty in Coimbatore city), `E1-026`, `E1-027`, `E1-028`, `E1-029`.

### A + `data_answerable = no` — 45 cases

The expectation is achievable by retrieval and the resolver missed it, *and*
separately the schema could not execute it.

```
E1-034  Show bill amount for Coimbatore city
        Amt  → PBI_ENES_ORDER_PENDING_SUMMARY.Amt
        City → PBI_OUTSTANDING_ENES_SUMMARY.City
E1-036  Show sales for Chennai district
        C Y      → QB_MDJMD_SALES_5YRS_SUMMARY.CY
        District → PBI_OUTSTANDING_ENES_SUMMARY.District
```

## Verdict changes — all 26, with reasons

| From → To | Cases | Reason |
|---|---:|---|
| **C → E** | 15 | RAMRAJ cases. Joinability moved to `data_answerable`; the retrieval problem is that `RAMRAJ` is not a stored value and the column holds brand-product lines, so its meaning is undefined. `data_answerable = no` still records the join limitation. `E1-039, E1-040, E1-055, E1-064–E1-068, E1-073, E1-075, E1-076, E1-080, E1-081, E1-120, E1-121` |
| **B → A** | 8 | Pending Amount cases. With the authorised `pendamt → P A M T` correction their expectation is valid, so any remaining failure is the resolver's. `data_answerable = yes` — `P A M T` and `City` are both on Outstanding. `E1-013, E1-014, E1-032, E1-033, E1-086, E1-090, E1-109, E1-169` |
| **C → B** | 2 | `E1-060`, `E1-072`. Previously C for joinability; the retrieval fault is `FRANCHISEE`, which has a confident replacement (`Franchise`). `data_answerable = no` because `Category` is not on Outstanding. |
| **C → A** | 1 | `E1-179`. Expectation valid after the P A M T correction; the run failed. `data_answerable = no` for `Category`. |

Every change is recorded per case in `expectation_review.verdict_history` with
the old verdict, new verdict, evidence and rationale.

## Business decisions preserved

- `C Y` remains the configured metric — untouched
- `pendamt` remains excluded — not re-enabled
- `P A M T` remains the corrected expectation on all 11 authorised cases
- `ProdGrp1` is **not** treated as a Brand field
- No RAMRAJ prefix rule invented
- No expectation changed in this pass; the only expectation edits remain the 11
  authorised P A M T corrections from the previous step

## Human review — 26 cases

All `E`, all turning on one question: against a column of brand-product lines
(`RAMRAJ DHOTI`, `RAMRAJ PANT`, …), what should "Ramraj brand" resolve to?

`E1-039, E1-040, E1-041, E1-055, E1-056, E1-057, E1-064, E1-065, E1-066,
E1-067, E1-068, E1-073, E1-075, E1-076, E1-077, E1-080, E1-081, E1-094, E1-095,
E1-096, E1-113, E1-120, E1-121, E1-166, E1-172, E1-176`

16 of them are also `data_answerable = no` — even with the meaning settled, the
join is still missing.

## Files changed

Only inside `backend/test/semantic_benchmark/v2/`:

- `golden_dataset_v2_c1.json` … `c6.json` — verdicts, `verdict_history`,
  `answerability` evidence, `data_answerable`, `missing_data`
- `validate_v2.py` — extended with the two-axis checks
- `STEP_16_CONSISTENCY_PASS.md` — this file

No production code, no database writes, no Gate 2 configuration change, no v1
file touched.

## Validation

`validate_v2.py` — **all checks passed**:

- 194 cases, exactly one verdict each, sum 194
- verdicts only `A/B/C/D/E/VALID`; `data_answerable` only `yes/no/partial`
- `missing_data` populated for every `no`/`partial`, empty for every `yes`
- `original_expected` matches the v1 file for all 194
- `expected` differs from v1 only where `expectation_changed_in_v2` is true and
  a `change_log` explains it (the 11 P A M T cases)
- verdict `A` never carries a configuration problem; verdict `E` always flagged
  for human review

v1 MD5 (6 datasets + `golden_case_schema.json` + `run_retrieval_benchmark.py`):
**unchanged**.
