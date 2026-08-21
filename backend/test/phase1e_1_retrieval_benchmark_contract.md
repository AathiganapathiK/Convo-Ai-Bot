# Phase 1E.1 — Retrieval Benchmark Contract & Dataset Design

## 1. Executive Summary
Phase 1E establishes a formal, objective, and reproducible evaluation framework to measure the semantic retrieval accuracy of the current chatbot engine. With Phase 1D (Clarification Pipeline & Selection UX) complete and hardened, Phase 1E evaluates how accurately the semantic retrieval layer understands natural language business queries across varied enterprise domains.

This document defines the **Retrieval Benchmark Contract & Dataset Design**. It specifies:
- The JSON schema for benchmark cases.
- 13 distinct business question categories (A through M).
- Failure classification taxonomy and scoring metrics.
- Dataset composition target (150 test cases).
- Mapping of existing tests to benchmark coverage.
- Datasource isolation and benchmark execution runner specifications.

> [!IMPORTANT]
> **Strict Phase 1E.1 Rule**: This is a **DESIGN ONLY** deliverable. No production semantic retrieval, ranking, threshold, ambiguity, or SQL generation code has been altered. Benchmark failures identified in this specification represent baseline measurement targets to be systematically evaluated in Phase 1E.2 and subsequent phases.

---

## 2. Why Phase 1E Exists
The core question Phase 1E answers is:
> **"How accurately does the current semantic retrieval layer understand real business questions?"**

### Core Principles
1. **Objective Measurement**: Compare `EXPECTED BUSINESS MEANING` against `ACTUAL SEMANTIC RESOLUTION`.
2. **Decoupled Evaluation from Fixing**: A benchmark failure does **not** immediately trigger a production code modification. Every failure is first logged, categorized using a strict failure taxonomy, and prioritized by business severity.
3. **No Guesswork**: Expected outcomes are grounded in verified database schema rules, semantic metadata indices, and domain expert requirements—never in current AI/LLM outputs.

---

## 3. Current Retrieval Output Contract
The benchmark runner interfaces directly with the production retrieval pipeline via `SemanticResolver.resolve()`, `DimensionValueResolver`, and `SemanticGate.evaluate()`.

### Production Output Structure
The existing production retrieval pipeline returns a structured resolution dictionary:

```json
{
  "metrics": ["sales_amount"],
  "dimensions": ["city_name"],
  "metric_objects": [
    {
      "business_name": "Sales",
      "technical_name": "sales_amount",
      "table_name": "fact_sales"
    }
  ],
  "dimension_objects": [
    {
      "business_name": "City",
      "technical_name": "city_name",
      "table_name": "dim_city"
    }
  ],
  "value_matches": [
    {
      "value": "CHENNAI",
      "normalized_value": "chennai",
      "confidence": 0.95,
      "match_type": "EXACT",
      "dimension_id": 101,
      "business_name": "City",
      "table_name": "dim_city",
      "column_name": "city_name"
    }
  ],
  "followup_context": {
    "applied": true,
    "reason": "INHERITED_METRIC_AND_DIMENSION",
    "inherited_metric": "Sales",
    "inherited_dimension": "City"
  },
  "retrieval": {
    "status": "SINGLE_MATCH",
    "reason": "Exact match found",
    "resolved_components": 3,
    "resolved_metric_count": 1,
    "resolved_dimension_count": 1,
    "resolved_value_count": 1,
    "resolved_table_count": 2,
    "confidence": 0.95
  },
  "ambiguity_result": {
    "status": "SINGLE_MATCH",
    "candidates": [...],
    "dominant_match": {...}
  }
}
```

---

## 4. Benchmark Case Schema
Every case in the golden benchmark dataset follows a strict JSON structure:

```json
{
  "case_id": "E1-001",
  "category": "AMBIGUOUS_VALUES",
  "question": "Show sales for Chennai",
  "conversation": [],
  "datasource": "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
  "expected": {
    "metrics": ["Sales"],
    "dimensions": ["City"],
    "values": ["Chennai"],
    "status": "STRONG_AMBIGUITY",
    "followup_context_applied": false,
    "dominant_value": null
  },
  "source": "REAL_BUSINESS",
  "severity": "CRITICAL",
  "notes": "Chennai exists in multiple business dimensions (City vs. District). Clarification card is required."
}
```

### Schema Field Specifications
- `case_id`: Unique identifier formatted as `E1-XXX`.
- `category`: One of the 13 benchmark categories (A–M).
- `question`: The natural language user query.
- `conversation`: Array of prior turn objects for context inheritance testing:
  ```json
  [
    {
      "turn": 1,
      "question": "Show sales for Chennai city",
      "response": {"status": "SINGLE_MATCH"}
    }
  ]
  ```
- `datasource`: Active datasource connection GUID or label.
- `expected`: Ground-truth expected business resolution (`metrics`, `dimensions`, `values`, `status`, `followup_context_applied`, `dominant_value`).
- `source`: Dataset tier: `REAL_BUSINESS`, `REGRESSION`, or `SYNTHETIC_SAFETY`.
- `severity`: Failure severity rating: `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`.
- `notes`: Rationale behind the expected golden definition.

---

## 5. Benchmark Categories
The benchmark suite organizes queries into 13 business categories:

| Code | Category Name | Description | Example Queries |
| :--- | :--- | :--- | :--- |
| **A** | `SIMPLE_METRIC` | Queries requesting a single metric without dimensions or values. | *"Show sales"*, *"Total revenue"*, *"Show quantity"* |
| **B** | `METRIC_DIMENSION_VALUE` | Standard analytics queries combining metric, dimension, and value. | *"Show sales for Chennai"*, *"Net profit in Madurai"* |
| **C** | `EXPLICIT_DIMENSION` | Queries explicitly naming the dimension attribute before or after value. | *"brand Ramraj"*, *"city Coimbatore"*, *"state Tamil Nadu"* |
| **D** | `MULTI_DIMENSION` | Complex queries combining multiple dimension filters. | *"sales for Chennai for Ramraj"*, *"cotton pants in West region"* |
| **E** | `AMBIGUOUS_VALUES` | Values matching multiple entities or business dimensions requiring clarification. | *"pant"*, *"shirt"*, *"Chennai"*, *"Ramraj"* |
| **F** | `PARTIAL_COVERAGE` | Queries containing unmatched or partially matched domain tokens. | *"children wear"*, *"women wear"*, *"cotton shirt"* |
| **G** | `SINGULAR_PLURAL` | Morphological variations across singular and plural nouns. | *"pant"* vs *"pants"*, *"banian"* vs *"banians"* |
| **H** | `TYPO_FUZZY` | Queries with spelling mistakes or fuzzy variations. | *"cottn pant"*, *"banain"*, *"coimbator"* |
| **I** | `FOLLOW_UP` | Multi-turn queries depending on prior conversation context. | Turn 1: *"show sales for Chennai"*, Turn 2: *"for Coimbatore"* |
| **J** | `METRIC_SHIFT` | Multi-turn queries where the metric changes while retaining dimension context. | Turn 1: *"show qty for Chennai"*, Turn 2: *"show amount for Chennai"* |
| **K** | `ENTITY_TOPIC_SHIFT` | Multi-turn queries shifting to a new domain entity (resetting old context). | Turn 1: *"Chennai city"*, Turn 2: *"Ramraj brand"* |
| **L** | `NO_MATCH_ADVERSARIAL` | Out-of-domain, gibberish, or unmapped business queries. | *"xyzabc"*, *"laptop sales"*, *"unknownbusinessterm"* |
| **M** | `TEMPORAL_QUESTIONS` | Queries containing temporal/time-based expressions. Tagged as `CURRENTLY_IMPLEMENTED` or `FUTURE_PHASE`. | *"sales last month"*, *"this year revenue"*, *"same period last year"* |

> [!NOTE]
> Temporal cases tagged as `FUTURE_PHASE` are tracked for completeness but excluded from production regression penalty scoring.

---

## 6. Golden Truth Policy
To ensure benchmark validity:
1. **Source of Truth**: Golden expectations are derived exclusively from:
   - Verified physical database schema & data dictionary metadata.
   - Grounded business entity mappings (e.g. `dim_city.city_name`).
   - Domain-expert verified expectations for real enterprise questions.
2. **Strict Rule**: The current output of the chatbot or LLM **MUST NOT** be used as the golden truth. If the chatbot currently returns `PBI_OUTSTANDING_ENES_SUMMARY` for *"Show sales for Chennai city"*, the golden expectation remains `Metric: Sales`, `Dimension: City`, `Value: Chennai` (Table: `fact_sales` / `dim_city`).

---

## 7. Real vs Synthetic Policy
Benchmark cases are classified into three distinct source tiers:

```
Priority Ranking: REAL_BUSINESS > REGRESSION > SYNTHETIC_SAFETY
```

1. `REAL_BUSINESS`: Actual user questions asked in production or business analytics sessions.
2. `REGRESSION`: Previously identified bugs, edge cases, and safety fixes verified during Phase 1A–1D.
3. `SYNTHETIC_SAFETY`: Artificially constructed boundary, fuzz, and adversarial safety tests.

> [!IMPORTANT]
> The final evaluation scorecard reports metrics separately for each tier. Synthetic test pass rates must never obscure real business retrieval performance.

---

## 8. Failure Taxonomy
When actual retrieval results deviate from golden expectations, the failure is categorized under one of 13 standard failure codes:

| Failure Code | Classification | Description |
| :--- | :--- | :--- |
| `CORRECT` | Pass | Actual resolution matches golden expected resolution completely. |
| `WRONG_METRIC` | Production Error | Resolved to incorrect metric (e.g., Outstanding instead of Sales). |
| `WRONG_DIMENSION` | Production Error | Resolved to incorrect dimension or table mapping. |
| `WRONG_VALUE` | Production Error | Resolved to wrong entity value or missed value candidate. |
| `WRONG_AMBIGUITY` | Production Error | Returned `SINGLE_MATCH` when `STRONG_AMBIGUITY` was expected, or vice versa. |
| `PARTIAL_INTENT_LOSS` | Production Error | Valid query tokens were silently dropped during matching. |
| `WRONG_CONTEXT` | Production Error | Multi-turn context inheritance failed or incorrectly polluted turn 2. |
| `WRONG_CANDIDATE` | Production Error | Selected incorrect candidate ranking in multi-match scenario. |
| `MISSED_MATCH` | Production Error | Valid business term rejected by gate or returned `NO_MATCH`. |
| `FALSE_POSITIVE` | Production Error | Non-existent domain term incorrectly matched to a database entity. |
| `FALSE_NEGATIVE` | Production Error | Valid domain query incorrectly blocked by retrieval gate. |
| `UNIMPLEMENTED_FEATURE` | Scope Limitation | Out-of-scope feature (e.g., unhandled temporal macro expression). |
| `BENCHMARK_DEFINITION_ERROR` | Benchmark Defect | The benchmark case expectation was incorrect; does not penalize production. |

---

## 9. Scoring Metrics & Critical Accuracy
The benchmark framework evaluates performance using 9 quantitative metrics:

$$\text{Metric Accuracy (\%)} = \frac{\text{Cases with Correct Metric}}{\text{Total Evaluated Cases}} \times 100$$

$$\text{Dimension Accuracy (\%)} = \frac{\text{Cases with Correct Dimension}}{\text{Total Evaluated Cases}} \times 100$$

$$\text{Value Accuracy (\%)} = \frac{\text{Cases with Correct Value}}{\text{Total Evaluated Cases}} \times 100$$

$$\text{Ambiguity Accuracy (\%)} = \frac{\text{Cases with Correct Ambiguity Status}}{\text{Total Evaluated Cases}} \times 100$$

$$\text{Context Accuracy (\%)} = \frac{\text{Multi-Turn Cases with Correct Context Application}}{\text{Total Multi-Turn Cases}} \times 100$$

$$\text{Partial-Intent Safety (\%)} = \frac{\text{Cases without Unsafe Token Loss}}{\text{Total Evaluated Cases}} \times 100$$

$$\text{False Positive Rate (\%)} = \frac{\text{False Positive Matches}}{\text{Total Non-Matching / Adversarial Cases}} \times 100$$

$$\text{False Negative Rate (\%)} = \frac{\text{False Negative Blocks}}{\text{Total Valid Cases}} \times 100$$

### Critical Case Accuracy
Critical failures are defined as:
- `WRONG_METRIC`
- `WRONG_DIMENSION`
- `WRONG_VALUE`
- `PARTIAL_INTENT_LOSS`
- `WRONG_CONTEXT`

$$\text{Critical Case Accuracy (\%)} = \frac{\text{Evaluated Cases without Critical Failures}}{\text{Total Evaluated Cases}} \times 100$$

---

## 10. Dataset Target & Category Composition
The Phase 1E.2 dataset targets **150 golden test cases** distributed across categories and source tiers:

```
Total Dataset Target: 150 Golden Cases
├── REAL_BUSINESS:    90 Cases (60%)
├── REGRESSION:       40 Cases (27%)
└── SYNTHETIC_SAFETY: 20 Cases (13%)
```

### Proposed Distribution Across Categories (A–M)
1. **A. SIMPLE_METRIC**: 10 cases (6 Real, 3 Reg, 1 Syn)
2. **B. METRIC_DIMENSION_VALUE**: 25 cases (18 Real, 5 Reg, 2 Syn)
3. **C. EXPLICIT_DIMENSION**: 15 cases (10 Real, 4 Reg, 1 Syn)
4. **D. MULTI_DIMENSION**: 15 cases (10 Real, 4 Reg, 1 Syn)
5. **E. AMBIGUOUS_VALUES**: 15 cases (10 Real, 4 Reg, 1 Syn)
6. **F. PARTIAL_COVERAGE**: 12 cases (8 Real, 3 Reg, 1 Syn)
7. **G. SINGULAR_PLURAL**: 10 cases (5 Real, 3 Reg, 2 Syn)
8. **H. TYPO_FUZZY**: 10 cases (5 Real, 3 Reg, 2 Syn)
9. **I. FOLLOW_UP**: 12 cases (8 Real, 3 Reg, 1 Syn)
10. **J. METRIC_SHIFT**: 8 cases (5 Real, 2 Reg, 1 Syn)
11. **K. ENTITY_TOPIC_SHIFT**: 6 cases (4 Real, 1 Reg, 1 Syn)
12. **L. NO_MATCH_ADVERSARIAL**: 6 cases (2 Real, 1 Reg, 3 Syn)
13. **M. TEMPORAL_QUESTIONS**: 6 cases (3 Real, 1 Reg, 2 Syn)

---

## 11. Existing Test Coverage Mapping
Mapping of current test suites to Phase 1E benchmark categories:

| Category | Test Suite / File | Existing Coverage Status | Benchmark Gap / Action Needed |
| :--- | :--- | :--- | :--- |
| **A. SIMPLE METRIC** | `test_phase1d_2_e_clarification.py` | Partially covered (mock metrics) | Needs real database connection cases |
| **B. METRIC + DIM + VAL** | `test_phase1d_6_c_partial_coverage_safety.py` | Covered for safety | Needs multi-dimension business queries |
| **C. EXPLICIT DIMENSION** | `test_phase1d_5_b1_explicit_dimension_context.py` | Covered for context | Needs standalone explicit dimension tests |
| **D. MULTI-DIMENSION** | `test_phase1d_5_c_integration_gaps.py` | Basic coverage | Needs complex multi-filter real cases |
| **E. AMBIGUOUS VALUES** | `test_phase1d_6_d3_selection_matching.py` | Fully covered for selection | Needs duplicate display value cases |
| **F. PARTIAL COVERAGE** | `test_phase1d_6_c_partial_coverage_safety.py` | Fully covered for safety | Needs intent-loss tracking benchmarks |
| **G. SINGULAR / PLURAL** | `test_phase1c_fuzzy_matching.py` | Covered | Add real business product plurals |
| **H. TYPO / FUZZY** | `test_phase1c_fuzzy_matching.py` | Covered | Add real customer typo cases |
| **I. FOLLOW-UP** | `test_phase1d_5_b2_followup_dimension_context.py` | Covered for context inheritance | Add multi-turn context loss benchmarks |
| **J. METRIC SHIFT** | `test_phase1d_5_b3_metric_guard_refinement.py` | Covered | Add metric override benchmark cases |
| **K. TOPIC SHIFT** | `test_phase1d_5_b6_context_staleness_reset_audit.md` | Covered conceptually | Add explicit topic shift benchmark cases |
| **L. ADVERSARIAL** | `test_phase1d_6_a_thread_safety.py` | Covered for isolation | Add unmapped domain vocabulary tests |
| **M. TEMPORAL** | `test_temporal_mapper.py` | Covered | Tag as `CURRENTLY_IMPLEMENTED` vs `FUTURE` |

---

## 12. Datasource Handling
Benchmark evaluation must be strictly datasource-aware:
- Active live business connection ID: `F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5`.
- Evaluation runner initializes `MatchingContext` and `SemanticResolver` with the specified `connection_id`.
- Business rules and values are dynamically checked against the active database index.
- **Rule**: Hardcoding business entity IDs or table strings inside benchmark runner logic is strictly prohibited.

---

## 13. Benchmark Runner Design
The benchmark runner (`backend/test/run_retrieval_benchmark.py`) will execute each golden case against the live retrieval engine and format the output:

```json
{
  "case_id": "E1-001",
  "question": "Show sales for Chennai",
  "expected": {
    "metrics": ["Sales"],
    "dimensions": ["City"],
    "values": ["Chennai"],
    "status": "STRONG_AMBIGUITY"
  },
  "actual": {
    "metrics": ["Sales"],
    "dimensions": ["City", "District"],
    "values": ["CHENNAI"],
    "status": "STRONG_AMBIGUITY"
  },
  "result": "PASS",
  "failure_category": null,
  "severity": "CRITICAL",
  "execution_time_ms": 42.5
}
```

---

## 14. Scorecard Design
The final execution summary report (`backend/test/phase1e_scorecard.json` and Markdown summary) will present aggregated metrics:

```json
{
  "total_cases": 150,
  "passed": 128,
  "failed": 22,
  "overall_accuracy_pct": 85.33,
  "metrics": {
    "metric_accuracy_pct": 91.20,
    "dimension_accuracy_pct": 88.00,
    "value_accuracy_pct": 89.33,
    "ambiguity_accuracy_pct": 92.00,
    "context_accuracy_pct": 84.00,
    "partial_safety_pct": 95.00,
    "critical_accuracy_pct": 86.67,
    "false_positive_rate_pct": 3.20,
    "false_negative_rate_pct": 2.10
  },
  "by_source_tier": {
    "REAL_BUSINESS": {"total": 90, "passed": 74, "accuracy_pct": 82.22},
    "REGRESSION": {"total": 40, "passed": 36, "accuracy_pct": 90.00},
    "SYNTHETIC_SAFETY": {"total": 20, "passed": 18, "accuracy_pct": 90.00}
  }
}
```

---

## 15. Initial Real-World Cases (Baseline Registration)
The following 3 known real-world observations are formally registered as golden baseline cases:

### Case 1: `E1-001` (Duplicate Display Values)
- **Question**: `"Show sales for Chennai"`
- **Observed Behavior**: Chennai produced candidates with duplicate display strings (`CHENNAI` vs `CHENNAI`).
- **Golden Expectation**:
  ```json
  {
    "case_id": "E1-001",
    "category": "AMBIGUOUS_VALUES",
    "question": "Show sales for Chennai",
    "conversation": [],
    "datasource": "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
    "expected": {
      "metrics": ["Sales"],
      "dimensions": ["City"],
      "values": ["Chennai"],
      "status": "STRONG_AMBIGUITY"
    },
    "source": "REAL_BUSINESS",
    "severity": "CRITICAL",
    "notes": "Clarification required; display labels must differentiate City vs. District."
  }
  ```

### Case 2: `E1-002` (Wrong Metric / Outstanding Summary Table Misinterpretation)
- **Question**: `"Show sales for Chennai city"`
- **Observed Behavior**: SQL generated used `SUM(pendamt) AS Sales` from `PBI_OUTSTANDING_ENES_SUMMARY` instead of sales transaction table.
- **Golden Expectation**:
  ```json
  {
    "case_id": "E1-002",
    "category": "METRIC_DIMENSION_VALUE",
    "question": "Show sales for Chennai city",
    "conversation": [],
    "datasource": "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
    "expected": {
      "metrics": ["Sales"],
      "dimensions": ["City"],
      "values": ["Chennai"],
      "status": "SINGLE_MATCH"
    },
    "source": "REAL_BUSINESS",
    "severity": "CRITICAL",
    "notes": "Must map to Sales metric and City dimension, not Outstanding/pendamt table."
  }
  ```

### Case 3: `E1-003` (Follow-up Context Loss for "for coimbatore")
- **Question**:
  - Turn 1: `"Show sales for Chennai city"`
  - Turn 2: `"for coimbatore"`
- **Observed Behavior**: Turn 2 did not inherit the `Sales` metric and `City` dimension context from Turn 1.
- **Golden Expectation**:
  ```json
  {
    "case_id": "E1-003",
    "category": "FOLLOW_UP",
    "question": "for coimbatore",
    "conversation": [
      {
        "turn": 1,
        "question": "Show sales for Chennai city",
        "response": {"status": "SINGLE_MATCH", "metric": "Sales", "dimension": "City", "value": "Chennai"}
      }
    ],
    "datasource": "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5",
    "expected": {
      "metrics": ["Sales"],
      "dimensions": ["City"],
      "values": ["Coimbatore"],
      "status": "SINGLE_MATCH",
      "followup_context_applied": true
    },
    "source": "REAL_BUSINESS",
    "severity": "CRITICAL",
    "notes": "Turn 2 must inherit Sales metric and City dimension context from Turn 1."
  }
  ```

---

## 16. Phase 1E Completion Criteria
Phase 1E will be complete when:
1. **1E.1**: Retrieval Benchmark Contract & Dataset Design specification is complete and verified (**Current Step**).
2. **1E.2**: 150-case golden benchmark dataset file (`backend/test/golden_retrieval_benchmark.json`) is populated.
3. **1E.3**: Benchmark execution runner script (`backend/test/run_retrieval_benchmark.py`) is implemented and executed against the live dataset.
4. **1E.4**: Initial baseline scorecard (`backend/test/phase1e_baseline_scorecard.md`) is published detailing baseline accuracy across categories A–M and failure classifications.

---

## 17. Recommended Next Step
Proceed to **PHASE 1E.2 — GOLDEN BUSINESS-QUESTION DATASET**, creating `backend/test/golden_retrieval_benchmark.json` containing the initial target of 150 structured golden cases.

---

## 18. Final Verdict
**PASS — PHASE 1E.1 BENCHMARK CONTRACT READY**
