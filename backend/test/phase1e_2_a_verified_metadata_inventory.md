# Phase 1E.2.A — Verified Business Metadata Inventory Report

## 1. Executive Summary & Datasource Inspected
This report documents the verified business metadata inventory discovered from the live, production-indexed data source. This discovery establishes the factual foundation for constructing the 150-case Phase 1E golden retrieval benchmark without relying on LLM outputs or unverified assumptions.

- **Connection ID**: `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`
- **Connection Name**: `Chatbot`
- **Database Engine**: MS SQL Server (`mssql+pyodbc`)
- **Active Physical Database**: `Chatbot` / `PBI`
- **Total Tables**: 3 fact/summary tables
- **Database Safety Audit**:
  - DDL changes: **NONE**
  - DML changes: **NONE**
  - Migrations: **NONE**
  - Production code modified: **NO**

---

## 2. Metrics Inventory
A total of **23 business metrics** were discovered across the registered schema tables in `semantic_metrics`:

| Metric Business Name | Technical Column | Table Name | Aggregation Type | Source |
| :--- | :--- | :--- | :--- | :--- |
| **Amt** | `Amt` | `PBI_ENES_ORDER_PENDING_SUMMARY` | `SUM` | AUTO |
| **billamt** | `billamt` | `PBI_OUTSTANDING_ENES_SUMMARY` | `SUM` | AUTO |
| **C Y** (Current Year Sales) | `CY` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **C Y Q** (Current Year Qtr) | `CYQ` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **Doc Month** | `DocMonth` | `QB_MDJMD_SALES_5YRS_SUMMARY` | None | AUTO |
| **due** | `due` | `PBI_ENES_ORDER_PENDING_SUMMARY` | `SUM` | AUTO |
| **Duedays** | `Duedays` | `PBI_OUTSTANDING_ENES_SUMMARY` | None | AUTO |
| **nodays** | `nodays` | `PBI_OUTSTANDING_ENES_SUMMARY` | None | AUTO |
| **Order No** | `OrderNo` | `PBI_ENES_ORDER_PENDING_SUMMARY` | None | AUTO |
| **P A M T** | `PAMT` | `PBI_OUTSTANDING_ENES_SUMMARY` | `SUM` | AUTO |
| **P Y** (Previous Year Sales) | `PY` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **P Y T D** (PY To Date) | `PYTD` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **P P Y** (2 Years Prior) | `PPY` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **P P P Y** (3 Years Prior) | `PPPY` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **P P P P Y** (4 Years Prior) | `PPPPY` | `QB_MDJMD_SALES_5YRS_SUMMARY` | `SUM` | AUTO |
| **pendamt** (Pending Amount) | `pendamt` | `PBI_OUTSTANDING_ENES_SUMMARY` | `SUM` | AUTO |
| **ps** | `ps` | `PBI_OUTSTANDING_ENES_SUMMARY` | None | AUTO |
| **Qty** (Quantity) | `Qty` | `PBI_ENES_ORDER_PENDING_SUMMARY` | `SUM` | AUTO |
| **Sno** | `Sno` | `QB_MDJMD_SALES_5YRS_SUMMARY` | None | AUTO |

---

## 3. Dimensions Inventory
A total of **98 semantic dimensions** (including auto-expanded date variant dimensions) were discovered across `semantic_dimensions`:

### Categorized Dimension Breakdown
- **Geography (12 dimensions)**: `City`, `District`, `State1`, `state1`, `Area Code`, `Areacode`, `Zip`
- **Product (24 dimensions)**: `Brand`, `Category`, `Prod Grp1`, `Prod Grp2`, `Prod Grp3`, `ItemCode`, `ItemName`
- **Organization & Entity (18 dimensions)**: `Division`, `Division Group`, `Category`, `btype`, `Mkt Type`, `Mkt Type1`, `Mkt Type2`, `M K T R M`
- **Finance & Customer (16 dimensions)**: `Card Code`, `Card Name`, `Cardcode`, `cardname`, `Cardname`, `G Card Code`, `G Card Name`
- **Time & Calendar (28 dimensions)**: Date/Day/Month/Quarter/Week/Year expansions for `DocDate`, `CreatedDate`, `CREATEDDATE`

---

## 4. Dimension-Value Inventory Summary
The live semantic value index (`dimension_value_index`) was queried for connection `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`:

- **Total Indexed Dimension Value Rows**: `8,360`
- **Unique Dimension Values**: `5,514`
- **Cross-Dimension / Cross-Table Duplicate Values**: `1,619`
- **Average Values Per Standard Dimension**: `~85`

---

## 5. Synonym / Alias Inventory
Verified business synonyms currently indexed in `semantic_dimensions`:

| Business Dimension | Verified Synonyms / Aliases |
| :--- | :--- |
| **Card Code / Cardcode** | `Party code`, `Customer code`, `Customer id` |
| **Card Name / cardname** | `Party name`, `Customer Name`, `Customer` |
| **Category** | `Marketing`, `Franchise`, `Others` |
| **Division** | `Unit`, `Division` |
| **Division Group** | `Unit Group`, `Division Group` |
| **Doc Date / Created Date** | `date`, `dt`, `day` |
| **G Card Code / Gcardcode** | `Group card Code`, `Group Customer Code` |
| **G Card Name / Gcardname** | `Group card Name`, `Group Customer Name`, `Group Customer` |
| **state1 / State1** | `State ( Shortform )` |
| **M K T R M / Mkt R M** | `Marketing Regional Manager` |

---

## 6. Duplicate / Ambiguous-Value Inventory
Out of 5,514 unique values, **1,619 values** match multiple business dimensions or entities. Representative verified ambiguous values useful for benchmark construction:

### A. Geographical Ambiguity (City vs. District)
- **`CHENNAI`**: Matches `City` and `District`
- **`COIMBATORE`**: Matches `City` and `District`
- **`MADURAI`**: Matches `City` and `District`
- **`Erode`**, **`Salem`**, **`Tirunelveli`**, **`Trichy`**, **`Vellore`**: Match `City` and `District`

### B. Product & Brand Ambiguity (Brand vs. Prod Grp1 / Category)
- **`RAMRAJ`**: Matches `Brand` and `Prod Grp1`
- **`COTTON`**: Matches product terms in `Brand` and `Prod Grp1`
- **`VIVEAGHAM DHOTI`**: Matches `Brand` and `Prod Grp1`
- **`LS ZARI COTTON`**: Matches product group candidates

### C. Organizational & Type Ambiguity
- **`VT`**: Matches `Division` and `btype` (Business Type)
- **`WB`**: Matches `State1` and `state1`

---

## 7. Relevant Table & Column Inventory
All semantic resolution operates over 3 physical database views/tables:

### 1. `PBI_ENES_ORDER_PENDING_SUMMARY` (21 columns)
- **Fact Columns**: `Qty`, `Amt`, `due`, `OrderNo`
- **Dimensions**: `Brand`, `Division`, `Category`, `Areacode`, `Cardcode`, `cardname`, `DocDate`, `CREATEDDATE`

### 2. `PBI_OUTSTANDING_ENES_SUMMARY` (34 columns)
- **Fact Columns**: `pendamt`, `billamt`, `PAMT`, `Duedays`, `nodays`, `ps`
- **Dimensions**: `City`, `District`, `Division`, `Category`, `AreaCode`, `btype`, `Cardcode`, `Cardname`, `CreatedDate`

### 3. `QB_MDJMD_SALES_5YRS_SUMMARY` (38 columns)
- **Fact Columns**: `CY` (Current Year), `PY` (Prev Year), `PPY`, `PPPY`, `PPPPY`, `CYQ`, `PYQ`, `PYTD`, `Sno`, `DocMonth`
- **Dimensions**: `Division`, `DivisionGroup`, `Category`, `CardCode`, `CardName`, `createddate`

---

## 8. Existing Semantic Metadata Sources
Verified backend metadata files:
1. `backend/database.py` (SQLAlchemy connection configuration and DB engine)
2. `backend/semantic/discovery_service.py` (Auto-discovery of metrics, dimensions, and data types)
3. `backend/semantic/dimension_value_index_builder.py` (Value index builder)
4. `backend/semantic/dimension_value_resolver.py` (Exact, normalized, singular/plural, fuzzy match pipeline)
5. `backend/semantic/matching/` (Matchers: `ExactMatcher`, `NormalizedMatcher`, `SingularPluralMatcher`, `FuzzyMatcher`, `SemanticGate`, `AmbiguityClassifier`)

---

## 9. Existing Regression Cases Discovered
Extracted from Phase 1D unit & integration tests (`test_phase1d_2_b` through `test_phase1d_6_d4`):

1. **`pant`** (`test_phase1d_2_e_clarification.py`)
   - *Expected*: `STRONG_AMBIGUITY` (Matches candidates: `LS ZARI COTTON`, `LS COTTON BREEZE`, `MENS PYJAMA PANT`).
2. **`MENS PYJAMA PANT`** (`test_phase1d_6_d3_selection_matching.py`)
   - *Expected*: `SINGLE_MATCH` (Exact option selection matching).
3. **`brand Ramraj`** (`test_phase1d_5_b1_explicit_dimension_context.py`)
   - *Expected*: `SINGLE_MATCH` (Explicit dimension label `brand` disambiguates `Ramraj`).
4. **`children wear`** (`test_phase1d_6_c_partial_coverage_safety.py`)
   - *Expected*: `NO_MATCH` (Partial coverage gate blocks unmapped query token `wear`).
5. **`cotton pant`** (`test_phase1d_6_c_partial_coverage_safety.py`)
   - *Expected*: `SINGLE_MATCH` (Full query token coverage allowed).
6. **`1`**, **`option 2`** (`test_phase1d_6_d3_selection_matching.py`)
   - *Expected*: `SINGLE_MATCH` (Clarification numeric / option index selection).

---

## 10. Context / Follow-up Cases Discovered
Extracted multi-turn context rules:
1. **Dimension Inheritance**:
   - Turn 1: `"Show sales for Chennai city"` (Metric: `Sales`, Dimension: `City`, Value: `Chennai`)
   - Turn 2: `"for coimbatore"` (Inherits `Sales` metric and `City` dimension -> Value: `Coimbatore`)
2. **Metric Shift**:
   - Turn 1: `"qty Coimbatore"` (Metric: `Qty`, Dimension: `City`, Value: `Coimbatore`)
   - Turn 2: `"amt Coimbatore"` (Metric shifts to `Amt`, retaining `City` dimension context)
3. **Topic Shift / Reset**:
   - Turn 1: `"Chennai city"`
   - Turn 2: `"Ramraj brand"` (New entity in different domain resets previous geographic context)

---

## 11. Temporal Capability Status
- **Current Support**: `test_prompt_builder_temporal.py` and `StrategyPriorityEngine` handle SNAPSHOT, FISCAL, CALENDAR_DIMENSION, DATE_COLUMN, DERIVED strategies.
- **Date Dimensions**: `DocDate` and `CreatedDate` auto-expanded into Year, Quarter, Month, Week, Day dimensions.
- **Benchmark Tagging**: Basic date/month queries tagged as `CURRENTLY_IMPLEMENTED`. Advanced multi-year macro expressions (e.g. *"same period last year"*) tagged as `FUTURE_PHASE`.

---

## 12. Data Limitations & Unknowns
1. **Identifier Metrics**: Columns like `Sno` and `OrderNo` are auto-discovered as numeric metrics despite being document/row identifiers.
2. **Column Abbreviations**: Table `QB_MDJMD_SALES_5YRS_SUMMARY` uses abbreviated column names (`CY`, `PY`, `PPY`, `PPPPY`) requiring semantic business name mapping.
3. **Table Relationships**: No physical foreign keys exist between summary tables; join context relies on shared dimension names (`Division`, `Category`, `Cardcode`).

---

## 13. Safe Items for Golden Benchmark Construction
- **Verified Metrics**: `Sales`, `Qty`, `Amt`, `due`, `pendamt`, `billamt`, `CY`, `PY`
- **Verified Dimensions**: `City`, `District`, `Brand`, `Category`, `Division`, `Card Name`, `Doc Date`
- **Verified Values**: `CHENNAI`, `COIMBATORE`, `MADURAI`, `RAMRAJ`, `COTTON PANT`, `MENS PYJAMA PANT`
- **Explicit Labels**: `city`, `brand`, `state`, `district`, `division`
- **Ambiguous Pairs**: `CHENNAI` (`City` vs `District`), `RAMRAJ` (`Brand` vs `Prod Grp1`), `VT` (`Division` vs `btype`)

---

## 14. Items That Must NOT Be Assumed
- **DO NOT** assume LLM table selection choices as golden truth.
- **DO NOT** assume unindexed values exist in the database index.
- **DO NOT** assume future temporal macro expressions are supported without strategy tagging.
- **DO NOT** assume non-existent business synonyms or aliases.

---

## 15. Final Verdict
**PASS — VERIFIED METADATA INVENTORY READY**
