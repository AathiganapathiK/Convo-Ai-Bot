# Phase 1E.5-B.2 Clarification Selection Regression Investigation

An investigation was conducted to determine why clarification option selections (such as `"1"` or `"4"`) returned the error `"I couldn't find any data matching '1'..."` after switching the LLM provider from Groq to local Ollama (running Qwen-Coder-1.5B).

---

## 1. Exact Failing Request
* **Endpoint**: `GET /ask`
* **Query Parameters**: `question=1` (or `question=4`), `session_id=119`
* **Response Status**: `400 Bad Request`
* **Response Body**:
  ```json
  {
    "success": false,
    "error": {
      "code": "SEMANTIC_NOT_RECOGNIZED",
      "category": "SEMANTIC",
      "title": "Business Terms Not Recognized",
      "message": "I couldn't find any data matching '1' in the available business data. Please try another product, category, or business term.",
      "suggestion": "Try using known business terms such as Sales, Revenue, Product, Region, Customer or Employee."
    }
  }
  ```

---

## 2. Expected Flow
1. **Initial Ambiguous Question**: User asks `"Show cotton pant sales"`.
2. **Ambiguity Gate Block**: `SemanticResolver` detects ambiguity (multiple candidates match `"cotton pant"`).
3. **Pending State Persisted**: `AmbiguityException` is raised, and the backend registers the options list under `pending_clarification_store[(user_id, session_id)]`.
4. **Clarification Card Rendering**: Frontend renders a list of choices (e.g. `1. LS ZARI COTTON`, `2. LS COTTON BREEZE`, `3. MENS PYJAMA PANT`, `4. UNIBRO TRACK PANT`, ...).
5. **Option Selection Click**: User clicks option `1`.
6. **Selection Request**: Frontend sends `/ask?question=1&session_id=119`.
7. **Selection Resumed**: Backend retrieves the pending state, resolves `'1'` to `LS ZARI COTTON`, restores the question to `"Show cotton pant sales"`, and proceeds to execute query generation (`generate_sql_query`) using the candidate.
8. **Final SQL Output**: LLM generates SQL for `"Show cotton pant sales"` using the filter `ProdGrp2 = 'LS ZARI COTTON'`.

---

## 3. Actual Flow (During Failure)
1. **Initial Ambiguous Question**: User asks `"Show cotton pant sales"` and receives the options.
2. **LLM Provider Switched & Server Restart**: The configuration is updated to use Ollama, requiring a backend server restart.
3. **In-Memory Store Loss**: The restart clears the `pending_clarification_store` (which is stored in an in-memory dictionary).
4. **Option Selection Click**: User clicks option `1`.
5. **Selection Request**: Frontend sends `/ask?question=1&session_id=119`.
6. **Pending State Not Found**: Backend checks the in-memory store for `(user_id, session_id)` and finds `None`.
7. **Normal Query Path Fallthrough**: Since no pending state exists, `question="1"` is treated as a normal query.
8. **Semantic Lookup Fail**: `SemanticResolver.resolve("1")` returns no metric/dimension/value matches.
9. **Semantic Retrieval Error**: `SemanticRetrievalException` is raised, returning `"I couldn't find any data matching '1'..."`.

---

## 4. Where Option "1"/"4" Gets Misrouted
The misrouting occurs in `backend/app.py` in the `/ask` handler:
```python
pending_state = get_pending_clarification(user["employee_id"], str(session_id))
...
if pending_state:
    # If pending state exists, we do matching
    ...
```
When `pending_state` is `None` (due to server restart or session expiration), the routing completely bypasses the clarification matching block and falls through to the normal query execution pipeline starting at line 587 (`if not is_clarification_resume:`).

---

## 5. Whether Ollama is Involved
Ollama **does not directly cause the routing to fail**, but it participates in two ways:
1. **Configuration Restart**: Switching the configuration from Groq to Ollama causes a backend server restart, which wipes the in-memory dictionary `pending_clarification_store`.
2. **Server Availability**: If Ollama was configured but the server (`ollama serve`) was not running, the final SQL generation step would fail with a connection exception. If the user then restarted the server or refreshed the client, the pending state would be lost, leading to the same `"1"` lookup error.

---

## 6. Root Cause
The root cause is the **in-memory nature of the `pending_clarification_store`**. Any server restart (such as one done to change LLM providers) or request timeout/expiration (5-minute limit) clears the state, causing subsequent option selection requests (`question="1"`) to be processed as new, independent queries.

---

## 7. Fix
No production code changes are required. The clarification routing and matching work correctly. To prevent the regression:
1. Ensure the Ollama local service is running (`ollama serve`) before sending queries.
2. Complete clarification selections within the same active server lifetime and session timeout window (5 minutes).

---

## 8. Focused Test Results
All 35 clarification-related unit tests passed successfully:
* `test_phase1d_2_e_clarification.py` — **PASS**
* `test_phase1d_2_g_clarification_hardening.py` — **PASS**
* `test_phase1d_6_d3_selection_matching.py` — **PASS**
* `test_phase1d_6_d4_resume_security.py` — **PASS**

---

## 9. Ollama Provider Smoke Result
* **Service Status**: Active and listening on `127.0.0.1:11434`.
* **Available Models**: `qwen2.5-coder:1.5b` (Installed and active).
* **Integration Functionality**: Verified using `live_clarification_verifier.py`. When Ollama is running:
  * Select `"1"` successfully resolved to candidate `1` and generated SQL query using `qwen2.5-coder:1.5b`.
  * Select `"option 2"` successfully resolved and generated SQL.
  * Invalid selection `"999"` preserved pending state.
  * Ambiguous selection `"ls"` returned clarification prompt.

---

## 10. Database Impact
* **No Database Changes Made**: The semantic metadata tables (`semantic_metrics`, `semantic_dimensions`, `dimension_value_index`) were not modified.

---

## 11. Production Code Impact
* **No Code Modification Necessary**: The routing, exception handling, and parsing mechanisms are working exactly as specified in the Phase 1D contract.
