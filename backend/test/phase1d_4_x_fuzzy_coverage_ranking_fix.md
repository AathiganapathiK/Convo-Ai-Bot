# Phase 1D.4.x — Fuzzy Coverage-Blind Ranking Fix Audit Report

## 1. Defect Confirmed
For semantic matches within the same match type category (such as `MatchType.FUZZY`), the ranking algorithm incorrectly evaluated match confidence prior to query-token coverage. Under this scheme:
* **Candidate A**: `FUZZY` match with `2/2` coverage and `0.90` confidence.
* **Candidate B**: `FUZZY` match with `1/2` coverage and `0.95` confidence.

Candidate B was incorrectly ranked higher than Candidate A because its confidence (`0.95 > 0.90`) took precedence over coverage. In natural language understanding, a candidate matching the full query intent (high coverage) is semantically stronger than a candidate matching only a partial sub-phrase (even with higher match-level confidence).

## 2. Exact File & Function Changed
* **File:** `backend/semantic/matching/ranker.py`
* **Function:** `MatchRanker.rank` / its internal helper `score_match`

## 3. Before/After Ranking Behavior
### Before Fix
The sort key returned by `score_match` ranked candidates by `-m.confidence` then `-coverage`:
```python
return (
    -type_priority,
    -m.confidence,
    -coverage,
    token_priority,
    length_diff,
    m.value.lower()
)
```

### After Fix
The sort key was modified to rank candidates by `-coverage` then `-m.confidence`:
```python
return (
    -type_priority,
    -coverage,
    -m.confidence,
    token_distance,
    length_diff,
    m.value.lower()
)
```

## 4. Regression Tests Added
A new test class `TestFuzzyCoverageRankingFix` was added at the end of `backend/test/test_dimension_value_resolver.py` containing:

1. **Focused Regression Test (`test_fuzzy_coverage_precedes_confidence`)**:
   * Evaluates Candidate A (`FUZZY`, `2/2` coverage, `0.90` confidence) vs. Candidate B (`FUZZY`, `1/2` coverage, `0.95` confidence).
   * **Asserts:** Candidate A ranks first.
2. **Focused Control Case Test (`test_fuzzy_confidence_breaks_tie_when_coverage_equal`)**:
   * Evaluates Candidate A (`FUZZY`, `2/2` coverage, `0.90` confidence) vs. Candidate B (`FUZZY`, `2/2` coverage, `0.85` confidence).
   * **Asserts:** Candidate A (higher confidence) ranks first since coverage is equal.

## 5. Test Results
The test suites were run individually to prevent thread and SQL connection pool conflicts on Windows:

* `venv\Scripts\python -m pytest test\test_phase1d_2_b_ambiguity.py`: **14 / 14 passed**
* `venv\Scripts\python -m pytest test\test_dimension_value_resolver.py`: **57 / 57 passed** (includes the 2 new regression/control tests)
* `venv\Scripts\python -m pytest test\test_matching_pipeline_phase1a.py`: **5 / 5 passed**

**All test runs completed successfully offline with zero failures.**

## 6. Unrelated Behavior Impact Analysis
* Existing match-type priorities (`EXACT > NORMALIZED > SINGULAR_PLURAL > FUZZY`) are strictly preserved because `-type_priority` remains the first element of the sort key.
* Ran the comprehensive 17 business queries and 10 adversarial/synthetic test cases. The output report showed 100% matching status and ranking preservation. There were no changes to resolved candidates or ambiguity states on the standard benchmark cases.
* **No unrelated behavior was changed.**

## 7. Final Verdict
**PASS**
