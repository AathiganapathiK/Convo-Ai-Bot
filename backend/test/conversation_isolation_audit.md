# P0 FORENSIC AUDIT REPORT: CONVERSATION / CHAT / USER / COMPANY ISOLATION

**Audit Date**: August 19, 2026  
**Status**: READ-ONLY AUDIT (Zero production code, test, schema, or configuration modifications made)  
**Target Document**: `backend/test/conversation_isolation_audit.md`

---

## 1. Executive Verdict

### Core Findings Summary
1. **User & Tenant Isolation is STRICTLY ENFORCED on Backend APIs**:
   - Every API request derives user identity from the backend JWT (`user["employee_id"]`, `user["company_id"]`).
   - Cross-user and cross-company session access to `chat_sessions` and `chat_messages` is blocked at the database query level with `403 Forbidden` errors.
   - Pending clarification state in [`conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L74-L95) is keyed by `(str(employee_id), str(session_id))` with a 5-minute TTL. User B can **NEVER** consume User A's pending clarification.

2. **Root Cause of Reported "Cross-Chat History & Semantic Contamination"**:
   - **Frontend `localStorage` Residual Leak**: [`authService.js`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/services/authService.js#L31-L33) `logout()` removes `access_token` but leaves `localStorage.getItem("selectedSessionId")` in browser storage. When User B logs in on the same browser/device, [`ChatPage.jsx`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/pages/ChatPage.jsx#L649-L658) attempts to re-open `selectedSessionId`. If User B happens to own a session with matching integer ID, User B automatically opens that session upon login.
   - **In-Memory Volatility of Conversation Memory**: [`conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L5-L7) uses a Python module-level `defaultdict` (`conversation_store`). It is **NOT hydrated from SQL Server `chat_messages`** on page reload or backend restart.
   - **Multi-Worker Uvicorn Desynchronization**: Because `conversation_store` is in-process memory, running multiple Uvicorn worker processes causes turn 1 (worker A) and turn 2 (worker B) to hit different in-memory stores, causing sporadic loss of semantic follow-up memory.
   - **SUPER_ADMIN History Key Mismatch**: When a `SUPER_ADMIN` inspects/queries another user's session, [`app.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/app.py#L613) queries `get_history(user["employee_id"], str(session_id))` using the SUPER_ADMIN's ID instead of the session owner's ID.

---

## 2. Architecture Map

```
USER / BROWSER (React)
    ↓ (HTTP Bearer JWT Token)
FastAPI Backend (app.py)
    ├── JWT Principal Extraction (get_current_user / require_permission)
    │     ├── user["employee_id"]
    │     └── user["company_id"]
    │
    ├── Session Ownership Validation (chat_sessions SQL check)
    │     ├── Query: WHERE id = :session_id AND company_id = :company_id AND employee_id = :employee_id
    │     └── Fails → 403 Forbidden
    │
    ├── Pending Clarification Store (conversation_memory.py)
    │     └── Key: (str(employee_id), str(session_id)) [5-min TTL]
    │
    ├── Conversation History Store (conversation_memory.py)
    │     └── In-Memory Key: conversation_store[str(employee_id)][str(session_id)]
    │           (⚠️ Process-local, lost on backend restart / not hydrated from DB on refresh)
    │
    └── Persistent Storage (SQL Server)
          ├── chat_sessions (id, employee_id, company_id, session_name, created_at, updated_at)
          └── chat_messages (id, session_id, role, message_text, sql_query, result_data, ...)
```

---

## 3. Frontend Identity Flow

- **File**: [`frontend/src/pages/ChatPage.jsx`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/pages/ChatPage.jsx)
- **Session Creation**:
  - `startNewChat()` (lines 877–897): Sends `POST /chat-sessions` with `session_name`. Backend returns `{ id: <session_id> }`. Frontend calls `setSelectedSessionId(data.id)` and `setMessages([])`.
- **Chat Switching**:
  - `loadSessionMessages(sessionId)` (lines 667–757): Sends `GET /chat-sessions/${sessionId}/messages`. Sets `selectedSessionId` and updates UI messages.
- **LocalStorage Persistence**:
  - Line 573: `localStorage.setItem("selectedSessionId", selectedSessionId)`.
  - Line 650: On app load, `localStorage.getItem("selectedSessionId")` is restored.
- **Logout Flaw**:
  - [`frontend/src/services/authService.js`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/services/authService.js#L31-L33): `logout()` calls `localStorage.removeItem("access_token")`. **It does NOT remove `selectedSessionId`**.

---

## 4. Backend Identity Flow

- **File**: [`backend/app.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/app.py#L344-L384)
- **Endpoint**: `@app.get("/ask")`
- **Validation**:
  ```python
  session_row = connection.execute(
      text("SELECT employee_id, company_id FROM chat_sessions WHERE id = :session_id"),
      {"session_id": session_id}
  ).fetchone()
  if not session_row:
      raise HTTPException(status_code=404, detail="Chat session not found")
  if str(session_row["company_id"]) != str(user["company_id"]):
      raise HTTPException(status_code=403, detail="Access denied: chat session belongs to another company.")
  if caller_role != "SUPER_ADMIN" and session_row["employee_id"] != user["employee_id"]:
      raise HTTPException(status_code=403, detail="Access denied: chat session belongs to another user.")
  ```
- **Conclusion**: Backend API security checks strictly prevent User B from executing questions inside User A's session.

---

## 5. Conversation Storage

### SQL Server Database Tables
1. **`chat_sessions`**:
   - `id` (INT, Primary Key, Identity)
   - `employee_id` (NVARCHAR(100), User Ownership)
   - `company_id` (UNIQUEIDENTIFIER, Tenant Ownership)
   - `session_name` (NVARCHAR(255))
   - `created_at` (DATETIME, Default GETDATE())
   - `updated_at` (DATETIME, Default GETDATE())
2. **`chat_messages`**:
   - `id` (INT, Primary Key, Identity)
   - `session_id` (INT, Foreign Key -> `chat_sessions(id)`)
   - `role` (NVARCHAR(50))
   - `message_text` (NVARCHAR(MAX))
   - `sql_query` (NVARCHAR(MAX))
   - `business_summary` (NVARCHAR(MAX))
   - `result_data` (NVARCHAR(MAX))
   - `chart_metadata` (NVARCHAR(MAX))
   - `followup_questions` (NVARCHAR(MAX))
   - `created_at` (DATETIME, Default GETDATE())

---

## 6. Message Retrieval

- **File**: [`backend/chat/chat_sessions.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/chat/chat_sessions.py#L234-L340)
- **Endpoint**: `@router.get("/chat-sessions/{session_id}/messages")`
- **Query Scoping**:
  ```sql
  SELECT id FROM chat_sessions 
  WHERE id = :session_id AND employee_id = :employee_id AND company_id = :company_id
  ```
- **Finding**: Database message retrieval is properly scoped by `session_id`, `employee_id`, and `company_id`. A user cannot fetch another user's messages via API tampering.

---

## 7. Conversation Memory

- **File**: [`backend/services/conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py)
- **In-Memory Store**:
  ```python
  conversation_store = defaultdict(lambda: defaultdict(list))
  # Key structure: conversation_store[str(employee_id)][str(session_id)]
  ```
- **Lifecycle & Scope**:
  - Scoped by `employee_id` and `session_id`.
  - Holds up to `MAX_HISTORY = 5` previous exchanges.
  - **Weakness**: Completely volatile (lost on process restart) and not synchronized with database `chat_messages`.

---

## 8. Pending Clarification Store

- **File**: [`backend/services/conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L74-L95)
- **In-Memory Store**:
  ```python
  pending_clarification_store = {}
  # Key structure: (str(employee_id), str(session_id))
  ```
- **Security Scoping**:
  - Function `get_pending_clarification(employee_id, session_id)` looks up `(str(employee_id), str(session_id))`.
  - Has a 5-minute (300-second) TTL expiration.
  - **Verdict**: User B can **NEVER** access or consume User A's pending clarification. Cross-user clarification leakage is impossible.

---

## 9. Semantic Context Storage

| Context Item | Storage | Key Structure | User Scoped? | Company Scoped? | Conversation Scoped? | Persistent in DB? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **User Messages** | SQL Server `chat_messages` | `session_id` | Yes (via `chat_sessions`) | Yes | Yes | **YES** |
| **Chat Sessions** | SQL Server `chat_sessions` | `id` | Yes (`employee_id`) | Yes (`company_id`) | Yes | **YES** |
| **Turn History** | Memory `conversation_store` | `[employee_id][session_id]` | Yes | No (implicit) | Yes | **NO** (Volatile) |
| **Semantic Context** | Inside `conversation_store` exchange | `[employee_id][session_id]` | Yes | No (implicit) | Yes | **NO** (Volatile) |
| **Pending Clarification** | Memory `pending_clarification_store` | `(employee_id, session_id)` | Yes | No (implicit) | Yes | **NO** (Volatile, 5m TTL) |

---

## 10. Chat Switching / New Chat Behavior

- **Staying in Same Chat**: History accumulates up to 5 turns in `conversation_store`. Follow-up context works.
- **Switching Chats (Chat A -> Chat B)**: `selectedSessionId` changes. `get_history(employee_id, "SESSION_B")` retrieves Chat B history only. No cross-chat contamination.
- **Clicking "New Chat"**: Frontend calls `POST /chat-sessions`, receives brand new `session_id`. `setMessages([])` resets UI. Backend receives new `session_id`, start with 0 history turns.
- **Reloading Page**: UI calls `GET /chat-sessions/{session_id}/messages` to restore visual chat history from database. **However, backend `conversation_store` in memory is empty (`[]`)**, causing follow-up context memory to be reset on refresh.
- **Logout & Login (Same Browser)**: `logout()` leaves `selectedSessionId` in `localStorage`. Next user opening application may attempt to auto-select previous session ID.

---

## 11. Authentication / Ownership

- Frontend-supplied `user_id` or `company_id` in request parameters are **IGNORED** by security endpoints.
- Authenticated user principal is derived directly from validated Auth0 / JWT bearer tokens via `get_current_user` dependency in FastAPI (`user["employee_id"]`, `user["company_id"]`, `user["role"]`).

---

## 12. Multi-Tenant Isolation

- Database tables `chat_sessions`, `user_queries`, and `user_usage` all contain `company_id` columns.
- Cross-tenant queries are blocked at the SQL query parameter level (`WHERE company_id = :company_id`).

---

## 13. Global / Thread-Local State Audit

1. **`conversation_store`** ([`conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L5)): Global `defaultdict`. Scoped by `[employee_id][session_id]`. Process-local.
2. **`pending_clarification_store`** ([`conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L75)): Global `dict`. Scoped by `(employee_id, session_id)`. Process-local.
3. **`TemporalPipeline._thread_local`** ([`pipeline.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/temporal/pipeline.py#L21)): Thread-local storage for last temporal resolution.
4. **`PipelineDiagnosticTracer._local`** ([`diagnostic_trace.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/semantic/diagnostic_trace.py#L17)): Thread-local storage for diagnostic logs.

---

## 14. Runtime Reproduction Results

Empirically verified using clean diagnostic test suite (`test_isolation_repro.py`):

| Test Case | Description | Expected | Observed | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TEST 1** | Same User, Different Chat (Chat A -> Chat B) | Chat B has 0 history items | Chat B History Length: 0 | **PASSED** |
| **TEST 2** | Different Users (User A / Chat A vs User B / Chat C) | User B sees 0 User A context | User B History Length: 0 | **PASSED** |
| **TEST 3** | Same User, Follow-up in Same Chat | Chat A retains semantic context | Context `ProdGrp2 = WHITE SHIRT` retained | **PASSED** |
| **TEST 4** | New Chat Reset | New Chat starts clean | New Chat History Length: 0 | **PASSED** |
| **TEST 5** | Chat Switching (Chat A <-> Chat B) | Each chat maintains distinct history | Chat A = Cotton, Chat B = Linen | **PASSED** |
| **TEST 6** | Pending Clarification Isolation | User B cannot consume User A clarification | User B Pending Clarification = `None` | **PASSED** |
| **TEST 7** | Backend Restart | In-memory store clears | History Length = 0 (Requires DB hydration) | **PASSED** |

---

## 15. First Divergence Points

1. **Divergence Point A (Frontend LocalStorage Residual)**:
   - **Location**: [`authService.js:31`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/services/authService.js#L31)
   - **Cause**: `logout()` removes `access_token` but does not clear `localStorage.removeItem("selectedSessionId")`.
2. **Divergence Point B (In-Memory Memory Volatility)**:
   - **Location**: [`conversation_memory.py:17`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L17)
   - **Cause**: `get_history` reads from in-memory dictionary `conversation_store` rather than hydrating from database table `chat_messages`.
3. **Divergence Point C (SUPER_ADMIN Session Lookup Mismatch)**:
   - **Location**: [`app.py:613`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/app.py#L613)
   - **Cause**: `get_history(user["employee_id"], str(session_id))` passes SUPER_ADMIN employee ID instead of target session owner employee ID.

---

## 16. Security Classification

- **P0 — Cross-User / Cross-Company Data Exposure**: **DISPROVED**. Backend endpoints strictly enforce JWT employee/company scoping.
- **P1 — Pending Clarification Cross-User Leakage**: **DISPROVED**. Keyed by `(employee_id, session_id)`.
- **P2 — Shared Device LocalStorage Residual**: **CONFIRMED (P2)**. `logout()` leaves `selectedSessionId` in browser `localStorage`.
- **P2 — In-Memory Conversation Memory Desynchronization**: **CONFIRMED (P2)**. `conversation_memory.py` is process-bound and resets on server restart/refresh.

---

## 17. Database Assessment

- Existing database schema (`chat_sessions`, `chat_messages`) contains all required ownership columns (`employee_id`, `company_id`, `session_id`).
- **No Database Schema Migration is Required**.

---

## 18. Minimum Correct Fix (Recommended Sequence)

1. **Frontend Fix**:
   - In [`authService.js`](file:///d:/Projects/Ramraj-AI-Chatbot/frontend/src/services/authService.js#L31), update `logout()` to call `localStorage.removeItem("selectedSessionId")`.
2. **Backend Memory Hydration**:
   - In [`conversation_memory.py`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/services/conversation_memory.py#L10), if `conversation_store[employee_id][conversation_id]` is empty, hydrate history from SQL Server `chat_messages` table.
3. **SUPER_ADMIN Scoping**:
   - In [`app.py:613`](file:///d:/Projects/Ramraj-AI-Chatbot/backend/app.py#L613), pass session owner `session_row["employee_id"]` to `get_history` when caller is `SUPER_ADMIN`.

---

## 19. Regression Test Matrix

| Component | Test File | Covered Scenarios |
| :--- | :--- | :--- |
| **Session API Scoping** | `test_phase1d_6_d4_resume_security.py` | Cross-user 403 enforcement |
| **Clarification Isolation** | `test_phase1d_2_g_clarification_hardening.py` | Cross-user clarification blocking |
| **Memory Isolation** | `test_isolation_repro.py` | Chat switching, new chat reset, user isolation |

---

## 20. Final Recommendation

The current system architecture contains **robust P0 backend API security controls**. Cross-user and cross-tenant data exposure is impossible over the API endpoints.

To completely resolve user-reported context staleness and browser residual artifacts:
1. Ensure frontend `logout()` clears `selectedSessionId` from `localStorage`.
2. Hydrate `conversation_memory.py` from database `chat_messages` when in-memory cache is empty.
