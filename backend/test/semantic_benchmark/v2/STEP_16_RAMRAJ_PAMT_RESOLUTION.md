# Step 16 — RAMRAJ and Pending Amount resolution

Scope: the 26 cases expecting the value `RAMRAJ`, and the 11 expecting the
metric `pendamt`. 37 cases in total. v1 untouched; only v2 updated.

## Rulings applied

1. **`P A M T` is the Pending Amount metric.** `pendamt`
   (`PBI_OUTSTANDING_ENES_SUMMARY.pendamt`, `is_excluded = 1`) stays excluded and
   was not re-enabled. All 11 expectations now name `P A M T`
   (`PBI_OUTSTANDING_ENES_SUMMARY.PAMT`).
2. **`RAMRAJ` is not treated as a database value**, because it is not one.
3. **No prefix semantics were invented.** Nothing was rewritten to
   `starts_with("RAMRAJ")` or `LIKE 'RAMRAJ%'`.
4. **A dimension absent from the metric's table, with no join, is a schema
   limitation (C), not a resolver failure.**

## Finding — `ProdGrp1` was evaluated as the brand dimension and rejected

Required before proposing any replacement. `Prod Grp1`
(`QB_MDJMD_SALES_5YRS_SUMMARY.ProdGrp1`) holds 55 values that mix three
different kinds of thing:

| Kind | Examples |
|---|---|
| Product types | `DHOTI`, `BANIANS`, `TOWEL`, `ACCESSORIES`, `FABRIC`, `SUITING` |
| Standalone brands | `CULTURE CLUB`, `PRIMA CLUB`, `LINEN PARK`, `GENISTAA`, `KOKHILA`, `UNIBRO` |
| Brand-product lines | `RAMRAJ PANT`, `RAMRAJ SHIRT`, `VIVEAGHAM DHOTI`, `VIVEAGA LAGNAA` |
| Non-product entries | `LOT`, `SCRAP ITEM`, `COMBO`, `BTK`, `UB` |

It is a **product-line** dimension, not a brand dimension, and it contains no
value `RAMRAJ`. `Brand` on `PBI_ENES_ORDER_PENDING_SUMMARY` has the same shape
(`RAMRAJ DHOTI`, `RAMRAJ HANKEYS`, `UATHAYAM KIDS SET`, …).

**Neither table represents brand as its own field.** `ProdGrp1` was therefore
*not* substituted for `Brand`, and no expectation was rewritten to point at it.

## Joinability

`schema_relationships` and `semantic_relationships` both hold **0 rows** for
this connection. The three summary tables cannot be joined, so a metric on one
table and a dimension on another is unanswerable by construction.

| Dimension | Exists on |
|---|---|
| `Brand` | Order Pending only |
| `City`, `District` | Outstanding only |
| `Category` | Sales, Order Pending |
| `Division` | all three |
| `Prod Grp1`–`Grp4` | Sales only |

## Verdicts

| Verdict | RAMRAJ | pendamt | Total |
|---|---:|---:|---:|
| **C** — schema limitation, no join | 15 | 3 | **18** |
| **E** — undefined business meaning | 11 | 0 | **11** |
| **B** — corrected expectation | 0 | 8 | **8** |

## Case-by-case — the 26 RAMRAJ cases

`M` = expected metric, `D` = expected dimensions. Expected value is `RAMRAJ` in
every row; the exact value does not exist in any column.

| Case | Question | M | D | Physical reality | Joinable | Verdict |
|---|---|---|---|---|---|---|
| E1-039 | Show sales for brand Ramraj | C Y | Brand | C Y→Sales.CY; Brand→OrderPending.Brand | **No** | **C** |
| E1-040 | sales for Ramraj brand | C Y | Brand | same | **No** | **C** |
| E1-041 | Show quantity for brand Ramraj | Qty | Brand | both on OrderPending | Yes | **E** |
| E1-055 | Show sales for Ramraj brand | C Y | Brand | Brand off-table | **No** | **C** |
| E1-056 | Qty for brand Ramraj | Qty | Brand | both on OrderPending | Yes | **E** |
| E1-057 | Show quantity for Ramraj brand | Qty | Brand | both on OrderPending | Yes | **E** |
| E1-064 | …Chennai city and Ramraj brand | C Y | Brand, City | Brand→OrderPending, City→Outstanding | **No** | **C** |
| E1-065 | Ramraj brand sales in Chennai city | C Y | Brand, City | same | **No** | **C** |
| E1-066 | quantity …Chennai city and Ramraj | Qty | Brand, City | City off-table | **No** | **C** |
| E1-067 | …Coimbatore city and Ramraj brand | C Y | Brand, City | both off-table | **No** | **C** |
| E1-068 | …Madurai city and Ramraj brand | C Y | Brand, City | both off-table | **No** | **C** |
| E1-073 | …Chennai district and Ramraj brand | C Y | Brand, District | both off-table | **No** | **C** |
| E1-075 | …Ramraj brand and Franchise category | C Y | Category, Brand | Brand off-table | **No** | **C** |
| E1-076 | Franchise category sales for Ramraj | C Y | Category, Brand | Brand off-table | **No** | **C** |
| E1-077 | quantity …Ramraj brand and Franchise | Qty | Category, Brand | all on OrderPending | Yes | **E** |
| E1-080 | …Ramraj brand and VT division | C Y | Division, Brand | Brand off-table | **No** | **C** |
| E1-081 | …Chennai city, Ramraj brand, category | C Y | Category, Brand, City | Brand, City off-table | **No** | **C** |
| E1-094 | Show sales for Ramraj | C Y | — | RAMRAJ* only in Sales.ProdGrp1 | Yes | **E** |
| E1-095 | Total sales for Ramraj | C Y | — | same | Yes | **E** |
| E1-096 | Show quantity for Ramraj | Qty | — | RAMRAJ* in OrderPending.Brand | Yes | **E** |
| E1-113 | Show Qty for children wear for Ramraj | Qty | Brand | both on OrderPending | Yes | **E** |
| E1-120 | Show sales for Ramraj brands | C Y | Brand | Brand off-table | **No** | **C** |
| E1-121 | Total sales for Ramraj brand | C Y | Brand | Brand off-table | **No** | **C** |
| E1-166 | Now show quantity for Ramraj brand | Qty | Brand | both on OrderPending | Yes | **E** |
| E1-172 | Ramraj brand | C Y (inherited) | Brand | Brand off-table | Yes¹ | **E** |
| E1-176 | How about Ramraj brand? | C Y (inherited) | Brand | Brand off-table | Yes¹ | **E** |

¹ These two are follow-up turns whose v1 expectation names metric `Sales`,
which does not resolve, so no metric table is established and the joinability
test cannot fire. They are **E** on the value question alone. Their metric
expectation remains a separate **B**-class problem recorded in the main Step 16
report.

**Matching values available:** 9 `RAMRAJ*` values in `Sales.ProdGrp1`
(`RAMRAJ PANT`, `RAMRAJ SHIRT`, `RAMRAJ MASK`, `RAMRAJ MUHURTH`,
`RAMRAJ KALYAAN`, `RAMRAJ LAGNAA`, `RAMRAJ LITTLESTARS`,
`RAMRAJ VAIBHAV SET`, `RAMRAJ WEDDING SET`); 12 in `OrderPending.Brand`.

### Why the 11 E cases are E and not C

Metric and dimension sit on the same table, so the question is structurally
answerable. What blocks it is that the column holds brand-**product lines**, so
"Ramraj brand" has no defined referent: one line, all of them, or a brand field
that does not exist yet. That is an undefined business meaning, which is exactly
the E criterion. `data_answerable` is `partial` and `missing_data` records the
requirement.

### Why the 15 C cases are C and not A

No resolver behaviour can satisfy them. The dimension is not a column of the
metric's table and there is no relationship to join through, so the expectation
is unmeetable for a schema reason. Per the ruling, these are **not** resolver
failures. `data_answerable` is `no` and `missing_data` names the field or key
required.

## Case-by-case — the 11 Pending Amount cases

Every one now expects `P A M T` → `PBI_OUTSTANDING_ENES_SUMMARY.PAMT`.
`original_expected` still records `pendamt`.

| Case | Question | Was | Now | Verdict | Why not B |
|---|---|---|---|---|---|
| E1-013 | Show pending amount | pendamt | P A M T | **B** | — |
| E1-014 | Total pending amount | pendamt | P A M T | **B** | — |
| E1-032 | Show pending amount for Chennai city | pendamt | P A M T | **B** | City is on Outstanding, same table as PAMT |
| E1-033 | Pending amount in Madurai city | pendamt | P A M T | **B** | same |
| E1-060 | Pending amount for Franchise category | pendamt | P A M T | **C** | `Category` is not on Outstanding; no join |
| E1-072 | …Chennai city and Franchise category | pendamt | P A M T | **C** | `Category` off-table |
| E1-086 | Show pending amount for Chennai | pendamt | P A M T | **B** | — |
| E1-090 | Show pending amount for Coimbatore | pendamt | P A M T | **B** | — |
| E1-109 | Show pending amount for footwear | pendamt | P A M T | **B** | — |
| E1-169 | Show pending amount for Erode city | pendamt | P A M T | **B** | — |
| E1-179 | Marketing category instead | pendamt | P A M T | **C** | `Category` off-table |

The metric correction was applied to all 11, including the three whose verdict
is C. Joinability and metric identity are independent faults; leaving the
excluded metric in place would have kept a second reason the expectation can
never be met.

**Note for later:** `P A M T` currently carries the synonyms
`payment, paid amount, pamt, Pending Amount, Remaining Amount, Pendamt`. With
`pendamt` excluded there is no longer a collision, but "paid amount" and
"Pending Amount" on one metric are opposite meanings and will mis-resolve
questions about payments. That is a configuration matter, outside Step 16.

## What changed in v2

- 8 cases: `expected.metrics` `pendamt` → `P A M T`, with
  `expectation_changed_in_v2 = true` and a `change_log`
- 3 cases: same metric correction, verdict `C` for the joinability blocker
- 26 RAMRAJ cases: verdict, evidence, joinability, `data_answerable`,
  `missing_data`. **No expectation rewritten** — no invented prefix rule, no
  substituted dimension
- All 37: `expected_identity` refreshed to the corrected physical identity

`validate_v2.py` was tightened rather than relaxed: `original_expected` must
always match the v1 file, and `expected` may differ only when
`expectation_changed_in_v2` is true **and** a `change_log` says why.

## Verification

- `validate_v2.py`: 194 cases, one verdict each, sum 194 — **passed**
- Final distribution: VALID 42, A 83, B 36, C 18, E 11, D 4
- All 11 pendamt cases confirmed corrected, `original_expected` intact
- v1 MD5 (6 datasets + schema + runner): **unchanged**
- `git status`: only `backend/test/semantic_benchmark/v2/` is new

## Open for you — the 11 E cases

`E1-041, E1-056, E1-057, E1-077, E1-094, E1-095, E1-096, E1-113, E1-166,
E1-172, E1-176`

One question decides all of them: **against a column of brand-product lines,
what should "Ramraj brand" mean?**

1. the whole family — needs a rule this step was told not to invent, or a real
   brand field;
2. ask the user which line — makes these Step 21 clarification cases;
3. add a brand field to the source tables — a data change that also fixes the
   15 C cases for Sales.
