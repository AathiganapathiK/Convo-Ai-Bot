# 1. Executive Verdict

The investigation has conclusively proven that the semantic context leakage (where a newly created Chat B inherits filter values like `ProdGrp2 = 'MENS PYJAMA PANT'` and SQL shape `GROUP BY CardName` / `SUM(CY)` from a previous Chat A) is **NOT** caused by session ID reuse, stale memory cache keys, database hydration bugs, or frontend routing failures.

Instead, the leakage is caused by **Few-Shot Example Pollution** via the **`QueryExamplesService`**. 

When a query in Chat A succeeds, its final SQL is globally stored in the `query_examples` table. When Chat B (a genuinely new session with empty history) receives a query like `"Show sales"`, `QueryExamplesService.retrieve` loads these global query examples based solely on connection ID, matching tables, and metrics. Because `"Show sales"` has no active value filters, it matches the criteria for the stored Chat A query containing the specific filter `ProdGrp2 = 'MENS PYJAMA PANT'`. The prompt builder injects this example under the `PREVIOUS SUCCESSFUL QUERIES` section, causing the LLM (running at temperature `0.0`) to copy the filter and query structure verbatim.

---

# 2. Chat A vs Chat B Identity

The frontend and backend correctly generate and isolate session IDs:
* **Chat A Session ID:** `139`
* **Chat B Session ID:** `140`
* **Difference:** The session IDs are completely distinct (`140 != 139`).
* **Session Ownership:** Session ownership is correctly looked up and verified downstream, ensuring that each session routes to its respective ID.

---

# 3. Frontend Session Creation

* **File:** [`frontend/src/pages/ChatPage.jsx`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/pages/ChatPage.jsx#L877-L897)
* **Function:** `startNewChat()`
* **Mechanism:** 
  1. Calls `POST /chat-sessions` on backend to create a new session.
  2. Receives a new, unique integer ID (e.g. `140`) from backend.
  3. Updates React state: `setSelectedSessionId(data.id)`, `setMessages([])`, and `setQuestion("")`.
  4. React `useEffect` hook saves the new session ID to `localStorage.setItem("selectedSessionId", selectedSessionId)` (lines 572-578).

---

# 4. Backend Session Routing

* **File:** [`backend/app.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/app.py#L343-L362)
* **Function:** `ask_question()`
* **Mechanism:**
  1. Receives the query request containing `session_id` in query parameters.
  2. Executes validation against the `chat_sessions` database table:
     ```sql
     SELECT employee_id, company_id FROM chat_sessions WHERE id = :session_id
     ```
  3. Validates company and employee ownership. Routing continues using Chat B's session ID (`140`) exclusively.

---

# 5. History Isolation

* **File:** [`backend/services/conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L87-L125)
* **Function:** `get_history()`
* **Trace for Chat B:**
  - Before semantic resolution, history for Chat B evaluates to **`[]`** (empty list).
  - Since the session ID is new, there is no in-memory cache hit in `conversation_store[employee_id]['140']`.
  - Database hydration is triggered but returns `[]` because no messages have been associated with session `140` yet.

---

# 6. Memory Isolation

* **File:** [`backend/services/conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L5-L7)
* **Variable:** `conversation_store`
* **Key Structure:** `conversation_store[str(employee_id)][str(session_id)]`
* **Trace for Chat B:**
  - Key used: `conversation_store['EMP001']['140']`
  - Returns `[]`. Stale Chat A data under `conversation_store['EMP001']['139']` is isolated and not returned.

---

# 7. Database Hydration

* **File:** [`backend/services/conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L10-L85)
* **Function:** `hydrate_history_from_db()`
* **Trace for Chat B:**
  - Queries `chat_messages` table using Chat B's session ID (`140`):
    ```sql
    SELECT TOP 10 id, role, message_text, sql_query, created_at
    FROM chat_messages
    WHERE session_id = :session_id
    ORDER BY id DESC
    ```
  - Correctly yields `[]` (no records found). It cannot fetch Chat A (`139`) records because of the `session_id` filter.

---

# 8. Pending Clarification

* **File:** [`backend/services/conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L178-L198)
* **Function:** `get_pending_clarification()`
* **Trace for Chat B:**
  - Key inspected: `(str(employee_id), str(session_id))` $\rightarrow$ `('EMP001', '140')`
  - Yields `None`. Chat B does not inherit or consume any pending clarification from Chat A.

---

# 9. Semantic Context Sources

The backend loads semantic context entirely from the session history:
* **File:** [`backend/ai/prompt_builder.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/ai/prompt_builder.py#L223-L230)
* **Method:** `PromptBuilder.build_sql_prompt()`
* **Extraction Code:**
  ```python
  previous_semantic_context = None
  if history:
      for item in reversed(history):
          sem_ctx = item.get("semantic_context")
          if sem_ctx and isinstance(sem_ctx, dict):
              if sem_ctx.get("resolved_values") or sem_ctx.get("dimensions"):
                  previous_semantic_context = sem_ctx
                  break
  ```
* **Trace for Chat B:** Because `history` is `[]`, `previous_semantic_context` is evaluated as **`None`**. No thread-local, singleton, or module-level context variables exist to bypass this check.

---

# 10. First Appearance of MENS PYJAMA PANT

The value `'MENS PYJAMA PANT'` makes its first appearance in the execution of Chat B inside the **`QueryExamplesService.retrieve`** function return payload:

* **File:** [`backend/semantic/query_examples_service.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/query_examples_service.py#L41-L128)
* **Function:** `retrieve()`
* **Returned Value:**
  ```python
  [
      {
          "question": "Show sales",
          "sql_query": "SELECT TOP 100 CardName, SUM(CY) AS PantSales FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'MENS PYJAMA PANT' GROUP BY CardName ORDER BY PantSales DESC;"
      }
  ]
  ```

---

# 11. Show Sales Metric Resolution

The query `"Show sales"` is resolved by the semantic engine as follows:
* **File:** [`backend/semantic/semantic_resolver.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/semantic_resolver.py#L64-L161)
* **Function:** `_get_match_info()`
* **Reasoning:** The word `"sales"` matches the synonym configurations for metric `cy` (business name `"C Y"` / physical column `CY` in table `QB_MDJMD_SALES_5YRS_SUMMARY`).
* **Output:** `cy` is resolved with aggregation `SUM`.

---

# 12. Query Example Influence

* **File:** [`backend/semantic/query_examples_service.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/query_examples_service.py#L41-L128)
* **Function:** `retrieve()`
* **Reasoning:**
  1. The database query loads top examples filtered **only** by connection ID:
     ```sql
     SELECT TOP (50) question, sql_query FROM query_examples WHERE connection_id = :connection_id ORDER BY created_at DESC
     ```
  2. Because the current query `"Show sales"` has no resolved value matches (`value_matches = []`), the example compatibility loop is bypassed (`is_compatible` remains `True`).
  3. The query example containing `ProdGrp2 = 'MENS PYJAMA PANT'` is compatible with the resolved metric `cy` and references the table `QB_MDJMD_SALES_5YRS_SUMMARY`.
  4. The query is returned as a matching few-shot example.

---

# 13. LLM Influence

* **File:** [`backend/ai/prompt_builder.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/ai/prompt_builder.py#L856-L860)
* **Prompt Section:** `PREVIOUS SUCCESSFUL QUERIES`
* **Reasoning:**
  - The few-shot example SQL is rendered inside the prompt.
  - The LLM receives the question `"Show sales"`, matches it directly to the example question `"Show sales"`, and copies the filter `ProdGrp2 = 'MENS PYJAMA PANT'` and layout `GROUP BY CardName` verbatim due to temperature `0.0` execution constraints.

---

# 14. First Divergence Point

The first divergence point where Chat B gets contaminated is:
* **Location:** [`backend/semantic/query_examples_service.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/query_examples_service.py#L118)
* **Diverging Line:** `matched_examples.append({"question": ex_q, "sql_query": row[1]})`
* **Trigger:** The retrieval function appends Chat A's successful SQL query containing the specific product filter, even though Chat B's query `"Show sales"` does not ask for or resolve to `'MENS PYJAMA PANT'`.

---

# 15. Root Cause

1. **Lack of User/Session Scope in Query Examples:** Stored queries in the `query_examples` table are shared globally across all sessions.
2. **Missing Specificity Check in Example Retrieval:** `QueryExamplesService.retrieve` allows examples with specific filters (e.g. `ProdGrp2 = 'MENS PYJAMA PANT'`) to be matched for broad queries (e.g. `"Show sales"`) when `value_matches` is empty. The retriever does not ensure that value filters present in the example SQL are also resolved in the current query.

---

# 16. Minimal Correct Fix

In [`backend/semantic/query_examples_service.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/query_examples_service.py#L41-L128):
We must validate that any value filter present in the example SQL is also resolved in the current query's `value_matches`. If the example SQL contains a hardcoded string filter (e.g., `'MENS PYJAMA PANT'`) but no matching value match is present in the current query, we must reject it.

```python
# Draft Logic to add to retrieve():
import re

# Extract single quoted values from the example SQL
example_filters = re.findall(r"=\s*'([^']+)'", ex_sql)
if example_filters:
    # Ensure current query contains these resolved values
    current_values = {str(v.get("value")).lower() for v in (value_matches or []) if v.get("value")}
    for val in example_filters:
        if val.lower() not in current_values:
            is_compatible = False
            break
```

---

# 17. Regression Tests Required

Create a test in `backend/test/test_query_examples_service.py`:
1. Store a query example containing a specific filter (e.g., `ProdGrp2 = 'MENS PYJAMA PANT'`).
2. Retrieve examples for a query with **no** value filters (e.g. `value_matches = []`).
3. Assert that the returned examples list does **not** include the example containing the specific filter.
