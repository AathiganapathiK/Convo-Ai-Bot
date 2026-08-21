# Phase 1D.6.D.3 — Finalize Clarification Selection Contract + Tests

## 1. Why the Old Test Was Inconsistent With the New Contract
Under the previous selection matching system, substring matching was allowed globally, meaning that querying `"pant"` against `"LINEN PANT"` and `"RAMRAJ PANT"` matched both values and was classified as `AMBIGUOUS`.

However, the new strict selection contract enforces:
1. Exact Option Number
2. Normalized Exact Displayed Value
3. Case-Insensitive Exact Displayed Value
4. Unique Normalized Prefix
5. Otherwise Invalid

Under these rules, `"pant"` has no exact or prefix matches against `"LINEN PANT"` or `"RAMRAJ PANT"`. It is classified as an **invalid selection** (zero matches), rather than an ambiguous one. Therefore, the old test `test_ambiguous_selection_does_not_guess` was expecting the wrong error category (`AMBIGUITY_DETECTED` with "more than one option" instead of invalid selection).

## 2. Exact Test Change
In `backend/test/test_phase1d_2_e_clarification.py`, `test_ambiguous_selection_does_not_guess` was updated to reflect a genuinely ambiguous scenario under the prefix matching rule of the new selection contract:
- **Options**:
  1. `LINEN PANT`
  2. `LINEN SHIRT`
- **User Query**: `"linen"`
- **Result**: Both options share the prefix `"linen"`, which correctly triggers `AMBIGUOUS` matching, resulting in an HTTP 400 response with the ambiguity message and retaining the pending clarification state on the server.

## 3. Final Selection Contract
The selection priority strictly follows:
1. **Exact option number** (e.g., `"1"`, `"option 2"`)
2. **Normalized exact displayed value** (case-insensitive, stripping quotes, conversational fillers, and dimension names)
3. **Case-insensitive exact displayed value**
4. **Unique normalized prefix** (e.g. `"mens pyjama"` -> matches `"MENS PYJAMA PANT"` uniquely)
5. **Otherwise Ambiguous / Invalid** (Multiple matches -> AMBIGUOUS; Zero matches -> INVALID)

No unrestricted substring matching, token-overlap matching, fuzzy semantic retrieval, or global database searches are used.

## 4. Test Results
The combined test run of all four suites executed successfully:

```
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_ambiguous_selection PASSED [  2%]
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_case_insensitive_exact_value_selection PASSED [  5%]
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_exact_value_selection PASSED [  7%]
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_invalid_selection PASSED [ 10%]
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_numeric_selection PASSED [ 12%]
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_option_n_selection PASSED [ 15%]
test/test_phase1d_6_d3_selection_matching.py::TestPhase1D6D3SelectionMatching::test_unique_prefix_selection PASSED [ 17%]
test/test_phase1d_2_e_clarification.py::TestPhase1D2EClarificationOffline::test_ambiguous_selection_does_not_guess PASSED [ 20%]
test/test_phase1d_2_e_clarification.py::TestPhase1D2EClarificationOffline::test_cls_block_on_resume PASSED [ 22%]
...
test/test_phase1d_6_c_partial_coverage_safety.py::TestPhase1D6CUserResponse::test_partial_match_api_response_clarification PASSED [100%]

============================= 40 passed in 3.03s ==============================
```

All regression criteria are met:
- `"MENS PYJAMA PANT"` → exactly one option resolved
- `"'MENS PYJAMA PANT'"` → exactly one option resolved
- `"I meant Prod Grp2 'MENS PYJAMA PANT'"` → exactly one option resolved
- `"mens pyjama"` → unique prefix resolved
- `"ls"` → ambiguous
- `"pant"` → INVALID (not ambiguous)
- `"999"` → INVALID
- `"1"` → option 1 resolved
- `"option 2"` → option 2 resolved

## 5. Confirmation That Production Matching Logic Was NOT Weakened
No changes were made to the production selection matching implementation in `app.py` during this step. The production code remains secure, deterministic, and metadata-leak-free, relying strictly on the designated five priority layers.

## 6. Final Verdict

PASS — D.6.D.3 SELECTION CONTRACT COMPLETE
