# Step 16 correction request — NO_MATCH expectations

Raised by Gate 3 Step 21a. **No expectation has been changed.** This records the
contradiction and specifies the correction; applying it needs approval, as the
P A M T correction did.

## The frozen rule (Step 21a)

> An explicit value reference that does not resolve → `retrieval_status =
> INSUFFICIENT` → the existing `SemanticGate` blocks execution. Resolved metric
> and dimension information is **kept**, so a clarification can say what was
> understood and what was not found.

## The contradiction

The benchmark encodes two incompatible behaviours for the same input shape, and
a third that the frozen rule also contradicts.

```
E1-106  "Show sales for kidswear"   metrics=['C Y']  status=NO_MATCH  retrieval=PARTIAL       verdict=VALID
E1-180  "Show sales for xyzabc"     metrics=[]       status=NO_MATCH  retrieval=INSUFFICIENT  verdict=A
```

Identical shape, identical `NO_MATCH` status, opposite requirements. Nothing in
the input distinguishes "kidswear" from "xyzabc" — both are simply terms absent
from the data. No implementation can satisfy both.

Step 16 validated each expectation against **configuration** but never checked
expectations against **each other**, so this was invisible to that pass.

## Corrections required

### Group 1 — expect `PARTIAL`, must become `INSUFFICIENT` (9 cases)

An explicit value was named and did not resolve, so under the frozen rule
execution must be blocked.

| Case | Question | Now | Correct to |
|---|---|---|---|
| E1-106 | Show sales for kidswear | `PARTIAL` | `INSUFFICIENT` |
| E1-107 | Show quantity for kidswear | `PARTIAL` | `INSUFFICIENT` |
| E1-108 | Show sales for footwear | `PARTIAL` | `INSUFFICIENT` |
| E1-109 | Show pending amount for footwear | `PARTIAL` | `INSUFFICIENT` |
| E1-116 | Show sales for online portal | `PARTIAL` | `INSUFFICIENT` |
| E1-136 | Show sales for cottn | `PARTIAL` | `INSUFFICIENT` |
| E1-148 | Show sales for laptop | `PARTIAL` | `INSUFFICIENT` |
| E1-149 | Show sales for mobile | `PARTIAL` | `INSUFFICIENT` |
| E1-150 | Show sales for computer | `PARTIAL` | `INSUFFICIENT` |

Eight are currently verdict **VALID** and currently **passed**; E1-109 is **A**.
Metrics/dimensions in these expectations are already correct and stay unchanged.

### Group 2 — expect `metrics: []`, must retain the metric (10 cases)

The frozen rule keeps what was understood. These expect it discarded.

| Case | Question | Now | Correct to |
|---|---|---|---|
| E1-180 | Show sales for xyzabc | `metrics=[]` | `metrics=['C Y']` |
| E1-181 | Show sales for smartphone | `metrics=[]` | `metrics=['C Y']` |
| E1-182 | Show sales for mobile phone | `metrics=[]` | `metrics=['C Y']` |
| E1-183 | Show sales for qwert | `metrics=[]` | `metrics=['C Y']` |
| E1-184 | Show sales for asdfgh | `metrics=[]` | `metrics=['C Y']` |
| E1-187 | Show sales for Ramrajj | `metrics=[]` | `metrics=['C Y']` |
| E1-189 | Show sales for Chennaipet | `metrics=[]` | `metrics=['C Y']` |
| E1-185 | Show sales for Bangalore | `metrics=[]` | **hold — see below** |
| E1-186 | Show sales for Mumbai | `metrics=[]` | **hold — see below** |
| E1-188 | Show quantity for Banianist | `metrics=[]` | **hold — see below** |

`retrieval_status = INSUFFICIENT` is already correct on all ten and stays.

### Held back — not corrected here

- **E1-185, E1-186** (Bangalore, Mumbai). These values genuinely **exist** in
  `dimension_value_index` on City and District, so they resolve and `NO_MATCH`
  never fires. The benchmark expects refusal because the business does not trade
  there — a data/business question, deferred by instruction.
- **E1-188** (`Banianist` → `BANIANS`). A weak fuzzy match substitutes a value
  the user did not ask for, so the status is `PARTIAL_MATCH`, not `NO_MATCH`.
  Deferred to **21b** confidence work by instruction.

## Measured effect of leaving these uncorrected

| | Step 14 baseline | After 19a + 21a |
|---|---:|---:|
| Accuracy | 24.74% | **17.89%** |
| VALID passing | 42/42 | 34/42 |

Thirteen cases regressed against the Step 14 baseline and none were fixed. **Not
a software regression** — the resolver now does exactly what was frozen. The
benchmark still encodes the pre-freeze behaviour.

Four of those thirteen (`E1-013, E1-014, E1-086, E1-090`) are unrelated to 21a:
they regressed from the 19a synonym edits, where `Amt`'s synonym `Amount` now
beats `P A M T`'s `Pending Amount` on the span-greedy tie-break. That is RC-03
resurfacing and contradicts the Step 16 P A M T ruling; it needs a configuration
fix, not a benchmark one.

## Recommendation

Apply Groups 1 and 2 (16 cases) as a documented Step 16 v2 correction with
`expectation_changed_in_v2 = true` and a `change_log` citing this file, exactly
as the P A M T correction was handled. Re-baseline afterwards; the corrected
figure is the one to trust.
