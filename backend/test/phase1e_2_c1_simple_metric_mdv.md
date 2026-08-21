# Phase 1E.2.C.1 — Verified Golden Question Creation (SIMPLE_METRIC + METRIC_DIMENSION_VALUE)

## 1. Executive Summary
This document records the creation of the first controlled subset of the Phase 1E Golden Retrieval Benchmark dataset. All cases were constructed strictly from verified database metadata (`verified_metadata_inventory.json` and `phase1e_2_a_verified_metadata_inventory.md`) without inventing business terms, hardcoding physical credentials/GUIDs, or embedding SQL queries.

- **Target Categories**: `SIMPLE_METRIC` and `METRIC_DIMENSION_VALUE`
- **Dataset File**: `backend/test/semantic_benchmark/golden_dataset_1e_2_c1.json`
- **Schema Validator**: `backend/test/semantic_benchmark/validate_golden_schema.py`
- **Database Safety Audit**: **NONE** (DDL: NONE, DML: NONE, Migrations: NONE)
- **Production Code Safety Audit**: **NO** (Production code unchanged)

---

## 2. Dataset Case Distribution Summary

| Category | Target Range | Actual Created Cases | Case ID Range |
| :--- | :--- | :--- | :--- |
| **`SIMPLE_METRIC`** | 15–20 | **18 cases** | `E1-006` to `E1-023` |
| **`METRIC_DIMENSION_VALUE`** | 20–25 | **22 cases** | `E1-024` to `E1-045` |
| **TOTAL** | 35–45 | **40 cases** | `E1-006` to `E1-045` |

---

## 3. Business Metadata Verification

### A. Verified Metrics Used (10 metrics)
1. `Sales` (Mapped from `CY` / `PY`)
2. `Qty` (Order quantity metric)
3. `Amt` (Order amount metric)
4. `pendamt` (Outstanding pending amount)
5. `billamt` (Outstanding bill amount)
6. `due` (Order due amount)
7. `PAMT` (Payment amount)
8. `Duedays` (Outstanding due days)
9. `CY` (Current Year sales metric)
10. `PY` (Previous Year sales metric)

### B. Verified Dimensions Used (4 dimensions)
1. `City` (Geography)
2. `District` (Geography)
3. `Brand` (Product)
4. `Category` (Organization/Product)

### C. Verified Ground-Truth Values Used (10 values)
- Geography: `CHENNAI`, `COIMBATORE`, `MADURAI`, `ERODE`, `SALEM`, `TIRUNELVELI`
- Brand: `RAMRAJ`
- Category: `MARKETING`, `FRANCHISE`, `OTHERS`

---

## 4. Ambiguity Safety & Exclusions

1. **Unqualified Multi-Dimension Values**:
   - Query: `"Show sales for Chennai"`
   - *Reason for Exclusion from MDV*: `"Chennai"` exists in both `City` and `District` dimensions without an explicit attribute qualifier. The expected status is `STRONG_AMBIGUITY`. This case belongs to the `AMBIGUOUS_VALUES` category and is reserved for Phase 1E.2.C.3.
2. **Explicit Disambiguation Qualifiers**:
   - Query: `"Show sales for Chennai city"` -> `SINGLE_MATCH` (Qualifies `City` dimension).
   - Query: `"Show sales for Chennai district"` -> `SINGLE_MATCH` (Qualifies `District` dimension).
   - Query: `"Show sales for brand Ramraj"` -> `SINGLE_MATCH` (Qualifies `Brand` dimension).
3. **Unverified Terms Excluded**:
   - Terms like *"profit"*, *"revenue"*, *"margin"*, *"customer churn"* were **EXCLUDED** because they are not present in the indexed metadata inventory.

---

## 5. Duplicate & Schema Validation Audit

1. **Case ID Uniqueness**: **PASS** (40 unique IDs from `E1-006` to `E1-045`).
2. **Question Uniqueness**: **PASS** (40 unique natural language questions).
3. **Meaning Uniqueness**: **PASS** (No trivial politeness wrappers or duplicate semantic intent).
4. **Schema Compliance**: **PASS** (Validated by `validate_golden_schema.py`).
5. **No Credential / GUID Leakage**: **PASS** (Logical label `"Chatbot"` used; no connection GUIDs).
6. **No Embedded SQL**: **PASS** (Expected results specify business semantic contract only).

---

## 6. Audit Verdicts

```
DATABASE CHANGES: NONE
PRODUCTION SEMANTIC CODE CHANGED: NO
SCHEMA VALIDATION RESULT: PASS (40/40 Cases Validated)
METADATA VERIFICATION RESULT: PASS
DUPLICATE CHECK RESULT: PASS
```

---

## 7. Final Verdict
**PASS — PHASE 1E.2.C.1 COMPLETE**
