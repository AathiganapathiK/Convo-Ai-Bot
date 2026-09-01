# Gate 3 Step 16 — Benchmark Expectation Validity

Purpose: decide, for every case, whether the benchmark's expectation is still
correct **before** Step 14 uses the benchmark to measure accuracy. A score
produced against wrong expectations measures the benchmark, not the software.

- Cases reviewed: **194** (the six datasets the runner loads)
- v1 datasets, v1 schema and the runner: **unchanged** (MD5-verified)
- No expectation was rewritten. Verdicts and recommendations are recorded; the
  `expected` block of every v2 case is byte-identical to v1.
- No production, resolver, SQL, prompt, UI or database change.

## Verdicts

| Verdict | Meaning | Cases |
|---|---|---:|
| **A** | Software defect — the expectation is achievable under current configuration, the system does not meet it | **83** |
| **B** | Outdated or incorrect benchmark expectation | **39** |
| **C** | Database / data limitation | **0** |
| **D** | Intentionally unsupported capability | **4** |
| **E** | Genuine ambiguity — needs a business decision | **26** |
| **VALID** | Expectation verified against live configuration and currently met | **42** |
| | **Total** | **194** |

`VALID` is a sixth outcome, not one of A–E. A case that passes with a verified
expectation is neither a software defect nor a benchmark defect, and forcing it
into one of those letters would be false. Every case carries exactly one
outcome and `validate_v2.py` asserts it.

**C is zero, and that is a finding rather than an omission.** Every
unmeetable expectation traced to a name that does not exist in configuration or
a value spelled differently from the data — not to data that cannot answer the
question. No case was filed under C to make the table look complete.

## How each verdict was reached

Rules are ordered; the first match wins, so no case can hold two verdicts.

1. `implementation_status == FUTURE_PHASE` → **D**
2. Any expected metric, dimension or value missing from live configuration, or
   switched off by an administrator → **B**, unless:
   - the missing value has no near-identical real counterpart but does have a
     family of plausible ones → **E** (a business decision, not a correction)
   - nothing similar exists at all → **C**
3. All expectations verified present and usable, but the case fails → **A**
4. Otherwise → **VALID**

Evidence comes from the live connection: `semantic_metrics`,
`semantic_dimensions`, `dimension_value_index`, plus one diagnostic execution
of each case. **The diagnostic run is not the Step 14 baseline** and must not be
quoted as an accuracy figure.

## B — what is actually wrong, by root cause

| Root cause | Cases | Evidence | Recommended |
|---|---:|---|---|
| Expects metric `Sales` | 12 | No metric named `Sales` exists. The benchmark's own first-turn cases for the identical question (`E1-024` "Show sales for Chennai city") expect `C Y` — these are follow-up turns the 1E.4 correction pass missed, so the dataset contradicts itself | `C Y` |
| Expects metric `pendamt` | 11 | Exists on `PBI_OUTSTANDING_ENES_SUMMARY.pendamt` but `is_excluded = 1`; after Gate 3 P0 the resolver can never return it | Re-include the metric, or drop it from the expectation — a config decision |
| Expects value `FRANCHISEE` | 7 | Absent from the index. The real value is `Franchise` (on `Mkt Type`). 1E.4 changed `FRANCHISE`→`FRANCHISEE` believing it matched the database; it does not | `Franchise` |
| Expects `createddate Year` / `createddate Month` | 7 | Gate 2 Step 12 stopped registering `createddate` (1 distinct value over 2,238,958 rows — a load stamp), and P1 excluded it. 1E.4 had deliberately corrected these *to* createddate; Gate 2 then removed it | Sales is `SNAPSHOT`: the year is the metric column (`C Y`/`P Y`), so expect no year dimension. For month use `Inv Month` (`InvMonth`), the table's configured `month_column` |
| Expects value `VIVEAGHAM` | 3 | Absent; real values are `VIVEAGHAM DHOTI`, `VIVEAGHAM HOSIERY`, … | See E — needs a decision |
| Expects `Key Line` values (`AKG-Marketing-AP`, …) | 2 | Values exist only on the `Key Line` dimension, which the administrator excluded | Drop, or re-include `Key Line` |
| Expects value `BANIAN` | 1 | Absent; `BANIANS` exists on `Prod Grp1` (similarity 0.92) | `BANIANS` |

A recommendation is recorded only where a single real value is near-identical
in spelling. Where several real values could be meant, the case is **E** and
left for a human.

## E — 26 cases needing a business decision

All 26 expect the value `RAMRAJ`, which does not exist. Fifteen real values
begin with it (`RAMRAJ DHOTI`, `RAMRAJ PANT`, `RAMRAJ HANKEYS`, …), and none is
a near-spelling match (best similarity 0.67). "Show sales for Ramraj brand" is
therefore genuinely under-specified against this data.

The decision needed is what the benchmark should require:

1. resolve to every `RAMRAJ*` value (a brand-family filter), or
2. return an ambiguity status and ask the user which product line, or
3. treat `RAMRAJ` as a brand attribute that should exist as its own dimension
   value — a data/configuration change rather than a benchmark one.

This is exactly the class of question Step 21 (ambiguity and no-match
protection) exists to answer, so these expectations should be settled with that
design rather than guessed now.

## A — 83 cases where the expectation is sound

Every metric, dimension and value these cases name exists and is usable, so the
gap is in the software. They are the honest input to Step 15's taxonomy work.
The largest clusters:

- Metric resolution on non-Sales tables (`Show amount`, `Show bill amount`,
  `Show due amount`) — `wrong metric`
- The 10 `NO_MATCH_ADVERSARIAL` cases (`Show sales for xyzabc`,
  `Show sales for Bangalore`) expect `metrics: []` and `INSUFFICIENT`; the
  resolver still resolves "sales" and answers. This is the Step 21 gap the
  Gate 3 audit ranked first
- Ambiguity-status mismatches — `wrong ambiguity` appears in 105 of the
  diagnostic failures, which Step 15 must decompose before it means anything

**One open question inside this group**, flagged rather than decided: for the
adversarial cases, is `metrics: []` the right expectation, or should the system
return the metric it understood and mark retrieval `INSUFFICIENT` because the
entity is unknown? The second is arguably more useful. Settle it in Step 21.

## D — 4 cases

`E1-196` … `E1-199` — same-period-last-year, last-two-quarters, fiscal-year
2024, next-month. Marked `FUTURE_PHASE` in v1 and skipped by the runner.
Retained unchanged.

## Physical identity

Every v2 case gains `expected_identity`, resolving each expected metric and
dimension to `(table_name, column_name)` from live configuration, with flags for
unresolved names and for names configured on more than one table.

Identity is recorded **alongside** the business names, not instead of them, so
v1 and v2 stay directly comparable. Business names are display strings an
administrator can rename at any moment — which is precisely how the `Sales` and
`createddate` expectations rotted. Step 14 should compare on identity.

## Files

Added (all new):

- `v2/golden_dataset_v2_c1.json` … `c6.json` — 194 cases with review + identity
- `v2/golden_case_v2_schema.json` — v2 schema
- `v2/validate_v2.py` — integrity checks
- `v2/STEP_16_EXPECTATION_VALIDITY_REPORT.md` — this report

Unchanged and MD5-verified: the six v1 datasets, `golden_case_schema.json`,
`run_retrieval_benchmark.py`, and `results/`.

The runner still reads v1 only. Step 14 will need a small change to load v2 and
compare on identity; that change is deliberately not made here.

## Checks performed

- `validate_v2.py` — 194 cases, exactly one verdict each, verdict sum 194,
  every `expected` byte-identical to v1, every A verdict free of configuration
  problems, every B verdict carrying a recorded problem — **passed**
- Structural conformance of all 194 cases to the v2 schema — **0 violations**
- MD5 of all eight v1 artifacts before and after — **identical**
- `git status` — only the new `v2/` directory appears
