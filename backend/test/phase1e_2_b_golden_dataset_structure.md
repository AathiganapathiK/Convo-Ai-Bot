# Phase 1E.2.B — Golden Dataset Structure & Contract Specification

## 1. Purpose
This document defines the canonical, machine-readable JSON structure for the Phase 1E Golden Retrieval Benchmark dataset. The dataset contract provides a standardized, repeatable data format to store natural language business queries, conversation history, logical datasource references, and ground-truth business semantic expectations.

> [!IMPORTANT]
> **Strict Data Contract Principle**: The golden dataset specifies **BUSINESS MEANING** (`metrics`, `dimensions`, `values`, `status`), not generated SQL queries or physical database IDs. SQL correctness is decoupled from semantic retrieval evaluation.

---

## 2. JSON Case Schema & Field Definitions

Each benchmark case is stored as a JSON object adhering to `golden_case_schema.json`.

```json
{
  "case_id": "E1-003",
  "category": "METRIC_DIMENSION_VALUE",
  "source": "REAL_BUSINESS",
  "severity": "CRITICAL",
  "question": "Show sales for Chennai city",
  "conversation": [],
  "datasource_ref": "Chatbot",
  "expected": {
    "metrics": ["Sales"],
    "dimensions": ["City"],
    "values": ["CHENNAI"],
    "status": "SINGLE_MATCH",
    "followup_context_applied": false,
    "dominant_candidate": null
  },
  "allowed_variations": ["Sales for Chennai city", "Show sales in Chennai city"],
  "must_not": ["District"],
  "notes": "Explicit dimension qualifier 'city' disambiguates Chennai to City dimension."
}
```

---

## 3. Required vs. Optional Fields

### Required Fields
- `case_id`: Unique string matching `^E1-[0-9]{3,}$` (e.g. `E1-001`, `E1-042`).
- `category`: Exactly one of the 13 benchmark category codes.
- `source`: Exactly one of `REAL_BUSINESS`, `REGRESSION`, `SYNTHETIC_SAFETY`.
- `severity`: Exactly one of `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
- `question`: Non-empty natural language query string being evaluated.
- `conversation`: Array of prior turn objects `[{"turn": 1, "question": "..."}]` (empty `[]` for single turn).
- `datasource_ref`: Logical dataset name (e.g. `"Chatbot"`).
- `expected`: Object containing `metrics`, `dimensions`, `values`, `status`, `followup_context_applied`.
- `notes`: Human-readable explanation of why this golden expectation is correct.

### Optional Fields
- `allowed_variations`: List of acceptable question phrase variants.
- `must_not`: List of terms or entity mappings forbidden in resolution.
- `expected.dominant_candidate`: Optional string candidate name when ambiguity is present.

---

## 4. Category Contract (13 Business Categories)
Every case must be categorized under one of 13 codes:

| Code | Category Name | Description |
| :--- | :--- | :--- |
| `SIMPLE_METRIC` | Simple Metric | Single metric request without filters or values |
| `METRIC_DIMENSION_VALUE` | Standard Analytics | Metric + Dimension + Value query |
| `EXPLICIT_DIMENSION` | Explicit Attribute | Named dimension attribute (e.g. `"brand Ramraj"`) |
| `MULTI_DIMENSION` | Multi-Dimension | Multiple dimension filters in one query |
| `AMBIGUOUS_VALUES` | Ambiguous Value | Value matching multiple dimensions or entities |
| `PARTIAL_COVERAGE` | Partial Coverage | Queries with unmapped domain tokens |
| `SINGULAR_PLURAL` | Morphology | Singular/plural noun variations |
| `TYPO_FUZZY` | Fuzzy & Typos | Spelling errors or fuzzy variations |
| `FOLLOW_UP` | Context Follow-up | Multi-turn query depending on prior turn context |
| `METRIC_SHIFT` | Metric Shift | Multi-turn query changing metric while keeping context |
| `ENTITY_TOPIC_SHIFT` | Topic Shift | Multi-turn query shifting to new domain entity |
| `NO_MATCH_ADVERSARIAL` | Adversarial / Out-of-Domain | Unmapped or gibberish business queries |
| `TEMPORAL_QUESTIONS` | Temporal | Time-based queries (tagged for current/future capabilities) |

---

## 5. Source & Severity Contracts

### Source Tiers
- `REAL_BUSINESS`: Authentic user queries from real production/analytics sessions (Highest Priority).
- `REGRESSION`: Verified edge cases and bug fixes from Phase 1A–1D.
- `SYNTHETIC_SAFETY`: Boundary, fuzz, and adversarial safety tests.

### Severity Ratings
- `CRITICAL`: Severe business misinterpretation (wrong metric, wrong entity value, silent token loss).
- `HIGH`: Major retrieval inaccuracy (missed dimension mapping, failure to clarify).
- `MEDIUM`: Minor ambiguity or fuzzy resolution edge cases.
- `LOW`: Cosmetic or variation discrepancies.

---

## 6. Expected Semantic-Result Contract (`ResolutionStatus`)
The `expected.status` field must strictly match the project's production `ResolutionStatus` contract (`backend/semantic/matching/models.py`):

1. `NO_MATCH`: No valid business candidates resolved or gate blocked execution.
2. `SINGLE_MATCH`: Unambiguous resolution to exactly one business entity/metric combination.
3. `WEAK_AMBIGUITY`: Minor candidate score gap, dominant match present.
4. `STRONG_AMBIGUITY`: Close score gap requiring user clarification card.
5. `PARTIAL_MATCH`: Resolved subset of query tokens safely.

---

## 7. Multi-Turn & Conversation Representation
Conversation history preserves turn order explicitly:

### Single-Turn Query
```json
"conversation": []
"question": "Show sales for Chennai city"
```

### Multi-Turn Context Follow-Up
```json
"conversation": [
  {
    "turn": 1,
    "question": "Show sales for Chennai city"
  }
],
"question": "for coimbatore"
```

---

## 8. Datasource & Safety Rules
1. **Logical References**: `datasource_ref` uses `"Chatbot"`.
2. **No Physical Identifiers**: No hardcoded connection GUIDs (`F82C2F8D-...`), credentials, passwords, or physical table names (`PBI_OUTSTANDING_ENES_SUMMARY`) inside individual benchmark case files.
3. **Decoupled SQL**: No SQL `SELECT` statements required in golden expectations.

---

## 9. Schema Validation Script (`validate_golden_schema.py`)
Dataset integrity is strictly enforced by `backend/test/semantic_benchmark/validate_golden_schema.py`:
- Validates case ID uniqueness (`^E1-[0-9]{3,}$`).
- Enforces enum values for category, source, severity, status.
- Verifies array and boolean data types in `expected`.
- Rejects unexpected extra fields or missing required fields.
- Rejects embedded SQL or connection credentials.

---

## 10. Representative 5-Case Example Suite (`golden_dataset_examples.json`)
The five representative cases verified in Phase 1E.2.A are stored in `backend/test/semantic_benchmark/golden_dataset_examples.json`:

1. `E1-001` (`SIMPLE_METRIC`): `"Show sales"` -> `SINGLE_MATCH`
2. `E1-002` (`AMBIGUOUS_VALUES`): `"Show sales for Chennai"` -> `STRONG_AMBIGUITY`
3. `E1-003` (`METRIC_DIMENSION_VALUE`): `"Show sales for Chennai city"` -> `SINGLE_MATCH`
4. `E1-004` (`FOLLOW_UP`): Turn 1: `"Show sales for Chennai city"`, Turn 2: `"for coimbatore"` -> `SINGLE_MATCH`, `followup_context_applied`: `true`
5. `E1-005` (`METRIC_SHIFT`): Turn 1: `"qty Coimbatore"`, Turn 2: `"amt Coimbatore"` -> `SINGLE_MATCH`, `followup_context_applied`: `true`

---

## 11. Verification Audits

```
DATABASE CHANGES: NONE
PRODUCTION SEMANTIC CODE CHANGED: NO
SCHEMA VALIDATION STATUS: PASS (5/5 Example Cases Validated)
```

---

## 12. Final Verdict
**PASS — GOLDEN DATASET STRUCTURE & SCHEMA READY**
