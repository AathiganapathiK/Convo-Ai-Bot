# Phase 1E.2.C.5 — Verified Golden Question Creation (FOLLOW_UP + METRIC_SHIFT + ENTITY/TOPIC SHIFT)

## 1. Executive Summary
This document records the creation and subsequent expectation consistency audit of the fifth controlled subset of the Phase 1E Golden Retrieval Benchmark dataset. All cases were constructed strictly from verified database metadata (`verified_metadata_inventory.json` and `phase1e_2_a_verified_metadata_inventory.md`) and pre-existing Phase 1D regression context tests. No business terms were invented, no physical credentials/GUIDs were embedded, and no SQL was stored.

- **Target Categories**: `FOLLOW_UP`, `METRIC_SHIFT`, and `ENTITY_TOPIC_SHIFT`
- **Dataset File**: `backend/test/semantic_benchmark/golden_dataset_1e_2_c5.json`
- **Case ID Range**: `E1-154` to `E1-179` (26 new cases)
- **Schema Validator**: `backend/test/semantic_benchmark/validate_golden_schema.py`
- **Database Safety Audit**: **NONE** (DDL: NONE, DML: NONE, Migrations: NONE)
- **Production Code Safety Audit**: **NO** (Production code unchanged)

---

## 2. Dataset Case Distribution Summary

| Category | Target Range | Actual Created Cases | Case ID Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`FOLLOW_UP`** | 10 | **10 cases** | `E1-154` to `E1-163` | Context inheritance cases (inheriting metrics/dimensions, replacing value). |
| **`METRIC_SHIFT`** | 8 | **8 cases** | `E1-164` to `E1-171` | Metric replacement cases (changing metrics while retaining dimensional context). |
| **`ENTITY_TOPIC_SHIFT`** | 8 | **8 cases** | `E1-172` to `E1-179` | Topic reset cases (changing dimension/value while inheriting or resetting metrics). |
| **TOTAL** | 26 | **26 cases** | `E1-154` to `E1-179` | New dataset subset size. |

---

## 3. Context Mappings & Verified Behaviors

### A. Context Inheritance Cases (`FOLLOW_UP`)
These cases verify the semantic resolver's ability to retain the query's business focus (metric and dimension) while resolving a new value in a follow-up turn.
- `E1-154` through `E1-163` demonstrate inheriting metrics (Sales, Qty, pendamt) and dimensions (City, Brand, Category, District) and replacing values.

### B. Metric Replacement Cases (`METRIC_SHIFT`)
These cases verify the resolver's ability to change metrics when a user explicitly requests a metric shift, while preserving the active dimension and value.
- `E1-164` (Qty $\to$ Amt)
- `E1-165` (Qty $\to$ Sales)
- `E1-166` (Sales $\to$ Qty)
- `E1-167` (Qty $\to$ Sales)
- `E1-168` (Sales $\to$ Qty)
- `E1-169` (Sales $\to$ pendamt)
- `E1-170` (Qty $\to$ Sales)
- `E1-171` (pendamt $\to$ Qty)

### C. Topic Reset Cases (`ENTITY_TOPIC_SHIFT`)
These cases verify the resolver's ability to update or reset the dimensional context when a new category, brand, or division is introduced, preventing stale dimension inheritance.
- `E1-172` (City $\to$ Brand, inheriting Sales)
- `E1-173` (City $\to$ Category, resetting context via explicit query)
- `E1-174` (Brand $\to$ City, resetting context via explicit query)
- `E1-175` (Category $\to$ City, resetting context via explicit query)
- `E1-176` (Division $\to$ Brand, inheriting Qty)
- `E1-177` (Category $\to$ City, inheriting Sales)
- `E1-178` (Category $\to$ City, inheriting Sales)
- `E1-179` (City $\to$ Category, inheriting pendamt)

---

## 4. Known Real-World Failure Integration
- **Case `E1-154`**: Triggers a known follow-up parsing issue where the lowercase query `"for coimbatore"` is processed.
  - **Turn 1**: `"Show sales for Chennai city"`
  - **Turn 2**: `"for coimbatore"`
  - **Expected Current Turn**: Sales, City, Coimbatore (`SINGLE_MATCH`, `followup_context_applied = true`).
  - **Status in Benchmark**: Present to objectively evaluate context resolution quality without changing production code.

---

## 5. Golden Expectation Audit (Phase 1E.2.C.5-A)

A forensic consistency audit was conducted on the `expected.followup_context_applied` values in the dataset using the Phase 1D contract rules:
- **Rule B.1**: Explicit Dimension takes precedence over B.2 follow-up inheritance. If the current turn explicitly contains a dimension label (`city`, `district`, `brand`, `category`, `division`), `followup_context_applied` must be set to `false`.

### Audit Details:
- **Cases Audited**: `E1-154` through `E1-179` (26 cases)
- **Cases Changed**: 23 cases (`E1-155` through `E1-171`, `E1-172`, and `E1-176` through `E1-179`)
- **Old Value**: `true` for `followup_context_applied`
- **New Value**: `false` for `followup_context_applied`
- **Reason**: The current turn explicitly names a dimension qualifier (e.g. `city`, `brand`, `category`, `division`, `district`). Under Rule B.1, explicit resolution takes precedence, and B.2 dimension inheritance is not applied.
- **Unchanged Cases**:
  - `E1-154` ("for coimbatore" - genuinely elliptical query, remains `true`).
  - `E1-173`, `E1-174`, `E1-175` (previously `false` and remain `false` because they are explicit standalone queries with no inheritance).

---

## 6. Source Classification & Severity
- **`REGRESSION`**: Assigned to `E1-154` (known failure case) and `E1-164`/`E1-172` (derived directly from verified context unit tests in Phase 1D).
- **`REAL_BUSINESS`**: Assigned to all remaining 23 cases.
- **Severity Ratings**: Rated `CRITICAL` for core city and locations and `HIGH` for remaining category shifts.

---

## 7. Duplicate & Schema Validation Audit
1. **Case ID Uniqueness**: **PASS** (174 unique IDs `E1-006` to `E1-179` across files C.1 to C.5).
2. **Question Uniqueness**: **PASS** (174/174 unique questions normalized before comparison).
3. **Schema Compliance**: **PASS** (Validated against `golden_case_schema.json` using `validate_golden_schema.py`).
4. **No Credentials / GUIDs**: **PASS** (Logical label `"Chatbot"` used).
5. **No Embedded SQL**: **PASS** (Only business semantic expectations are validated).

---

## 8. Audit Verdicts

```
DATABASE CHANGES: NONE
PRODUCTION SEMANTIC CODE CHANGED: NO
SCHEMA VALIDATION RESULT: PASS (26/26 Cases Validated)
METADATA VERIFICATION RESULT: PASS
DUPLICATE CHECK RESULT: PASS
TOTAL PRODUCTION BENCHMARK CASES: 174
```

---

## 9. Final Verdict
**PASS — C5 GOLDEN EXPECTATIONS CONSISTENT**
