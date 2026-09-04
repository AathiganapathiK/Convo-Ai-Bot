# Step 21d — documented conflict: E1-119 vs. the `total` filler-word rule

**Status: recorded, not resolved. No benchmark expectation was changed.**

## The conflict

`E1-119` — "Total sales for Banians" — expects `PARTIAL_MATCH`. Its only
previously-unmatched, non-stopword, non-dimension-word token was `total`.
Before Step 21d, that token was treated as dangerous, which is what produced
the expected `PARTIAL_MATCH`. After 21d, `total` is exempted (it is generic
filler — it explains nothing about which value or dimension is meant, and
this was independently verified across ten other cases before being added),
so this case now resolves `WEAK_AMBIGUITY` instead.

## Why this was not "fixed" case-specifically

- `total` is correctly treated as generic filler by the general RC-02 rule.
  The rule was derived from, and validated against, cases that do not
  include E1-119: E1-046/047/048 ("Total sales for `<city>`"), E1-098 ("Total
  sales for VT"), and the live-DB regression check added in this step.
- The existing E1-119 expectation is the one case in the benchmark whose
  correctness *depends on* `total` staying unmatched-and-dangerous. No other
  case needs that.
- Carving out an exception for "total, except when the value is Banians" (or
  any other per-case condition) would be exactly the case-specific rule this
  session's standing instructions prohibit, and would not generalize to any
  future question phrased with "total."

## What 21d actually delivered

- FAIL → PASS: 10 cases (E1-032, E1-033, E1-046, E1-047, E1-048, E1-165,
  E1-169, E1-171, E1-174, E1-175).
- PASS → FAIL: 1 case (E1-119, this conflict).
- Net: **+9**, benchmark **59/190 (31.05%) → 68/190 (35.79%)**.

A net +9 improvement is not, by itself, sufficient justification to weaken
the general rule for one case. The decision recorded here is to keep the
rule and accept E1-119 as failing, explicitly, rather than to special-case it
or silently absorb the regression.

## Open action

E1-119's expectation itself has not been reviewed under the Step 16 process
(verdict / rationale / evidence / recommended expectation). It remains
`PARTIAL_MATCH` in `golden_dataset_v2_c3.json` (or wherever the case lives),
unmodified. Whether `WEAK_AMBIGUITY` is actually the more defensible
expectation for "Total sales for Banians" — given that `total` carries no
information and the value itself is unambiguous — is a question for a future
Step-16-style expectation review, not for 21d. No such review has been
performed as part of this document; this file only records the conflict.
