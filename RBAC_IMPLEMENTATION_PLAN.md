# Updated Implementation Plan: RBAC & Access Control System in Admin Settings

## Overview & Background
This updated implementation plan addresses all user feedback regarding the Access Control system in **Admin Settings**. The system governs page access, chat feature capabilities, and business data boundaries across **Roles** and **Users**.

---

## 1. Audit Report of Prior Database Changes
Per your explicit directive, **no database execution, SQL queries, migration scripts, or schema changes will be executed without prior written approval.**

The actual state of database changes from prior executions is as follows:
- **Schema Alterations (DDL)**: `0` (None). No tables (`user_permission_overrides`, `role_data_access`) were created, and no columns (`division_code`) were added to `chat_sessions` because DDL statements were blocked by database user permission settings.
- **Data Seeded (DML)**: 25 permissions (`page:*:v`, `page:*:m`, `chat:ask`, `chat:history`, `chat:delete`) were inserted into the `permissions` table and mapped to `role_permissions` for system roles (`SUPER_ADMIN`, `ADMIN`, `ANALYST`).
- **Business Data Status**: 0 business records modified, updated, or deleted.

---

## 2. Key Architecture & Design Principles

### A. Location & Drive Policy
- All project code, implementation plans, scripts, reports, and documentation reside inside the project workspace directory on `D:\RR_Bot\Convo-Ai-Bot`. No project code or repository files will be written outside `D:\RR_Bot\Convo-Ai-Bot`.

### B. Core Access Control Dimensions
The Access Control interface in **Admin Settings** provides a tabbed UI with `[ By Roles ]` and `[ By Users ]`:

1. **Page Access (`V` / `M`)**:
   - **`V` (View)**: Grants permission to view, open, navigate to, and read page contents.
   - **`M` (Modify)**: Grants permission to create, edit, delete, or modify settings on that page.
   - *Behavior*: `V` only = Read-only mode. `V + M` = Full access. `No V` = Page hidden & route blocked.

2. **Chat Access (`A` / `H` / `D`)**:
   - **`A` (Ask)**: Submit analytical questions to chatbot.
   - **`H` (History)**: View chat sessions and past conversation messages.
   - **`D` (Delete)**: Delete chat sessions.

3. **Data Scope (Full Business Dimension Names)**:
   - Full dimension names: **`Region`**, **`Product`**, **`Channel`**, **`Division`**.
   - No single-letter codes (`R/P/C/D`) to avoid confusion with `D = Delete`.

### C. Division-Level Chat Isolation (Sales vs. Manufacturing)
- Chat session access is governed at the **Division / Data Scope** level.
- **Rule**:
  - `Sales` user querying/viewing `Sales` chats $\rightarrow$ **ALLOWED**
  - `Sales` user querying/viewing `Manufacturing` chats $\rightarrow$ **DENIED**
  - `Manufacturing` user querying/viewing `Manufacturing` chats $\rightarrow$ **ALLOWED**
  - `Manufacturing` user querying/viewing `Sales` chats $\rightarrow$ **DENIED**

### D. User Overrides & Privilege Escalation Guard
- **Precedence**: User-specific overrides allow administrators to customize or restrict access for individual employees.
- **Privilege Escalation Protection**: An individual user override **cannot** expand beyond the maximum security boundary defined by the administrator or corporate policy (e.g., if Role Division Scope is `Sales`, a user override cannot silently grant `Manufacturing` access unless an administrator explicitly expands the policy).

### E. Centralized Authorization Engine
- All permission evaluation is centralized inside `security/rbac_service.py` and `services/access_control_service.py`.
- Ad-hoc or scattered checks (`if SUPER_ADMIN`) are eliminated in favor of a single authorization pipeline:
  $$\text{User} \rightarrow \text{Role} \rightarrow \text{Role Permissions} \rightarrow \text{User Overrides} \rightarrow \text{Data Scope} \rightarrow \text{Effective Permissions}$$

---

## 3. Proposed File Changes

### Backend Components
1. **[MODIFY] [access_control_service.py](file:///d:/RR_Bot/Convo-Ai-Bot/backend/services/access_control_service.py)**
   - Implement matrix resolution for Page Access (`V`/`M`), Chat Access (`A`/`H`/`D`), and Data Scope (`Region`, `Product`, `Channel`, `Division`).
   - Implement user-override precedence logic with privilege escalation boundary checks.

2. **[MODIFY] [role_management.py](file:///d:/RR_Bot/Convo-Ai-Bot/backend/admin/role_management.py)** & **[user_management.py](file:///d:/RR_Bot/Convo-Ai-Bot/backend/admin/user_management.py)**
   - Expose GET/PUT matrix endpoints for Roles and Users.

3. **[MODIFY] [chat_sessions.py](file:///d:/RR_Bot/Convo-Ai-Bot/backend/chat/chat_sessions.py)**
   - Enforce division-level chat isolation (`Sales` vs `Manufacturing` division scope boundary) on chat session creation, listing, message viewing, and deletion.

4. **[MODIFY] [rbac_service.py](file:///d:/RR_Bot/Convo-Ai-Bot/backend/security/rbac_service.py)**
   - Centralize permission requirement checks.

### Frontend Components
1. **[NEW] [AccessControlMatrixModal.jsx](file:///d:/RR_Bot/Convo-Ai-Bot/frontend/src/components/AccessControlMatrixModal.jsx)**
   - Render Admin UI modal with `[ By Roles ]` and `[ By Users ]` tabs, Page Access (`V`/`M`), Chat Access (`A`/`H`/`D`), and Data Scope (`Region`, `Product`, `Channel`, `Division`).

2. **[MODIFY] [RoleManagement.jsx](file:///d:/RR_Bot/Convo-Ai-Bot/frontend/src/pages/RoleManagement.jsx)** & **[UserManagement.jsx](file:///d:/RR_Bot/Convo-Ai-Bot/frontend/src/pages/UserManagement.jsx)**
   - Add "Access Control Matrix" action buttons to trigger matrix configuration modal.

3. **[MODIFY] [App.js](file:///d:/RR_Bot/Convo-Ai-Bot/frontend/src/App.js)**
   - Dynamically load effective permissions and filter sidebar navigation items and route guards by `V` (View) permission.

---

## 4. Verification & Safety Plan

### Automated & Integration Testing
- Verify backend FastAPI startup: `venv\Scripts\activate; python -c "import app"`
- Verify zero syntax or runtime errors.

### Manual Verification Scenarios
1. **Page Access Test**: Verify user with `V` on Chat and `No V` on AI Providers sees Chat in sidebar but AI Providers is hidden and route `/providers` returns access denied.
2. **Chat Action Test**: Verify user with `A` + `H` (no `D`) can ask questions and view history, but delete button is disabled/hidden.
3. **Division Chat Isolation Test**: Verify a `Sales` division user cannot view or retrieve `Manufacturing` chat sessions via UI or API endpoints.

---

## 5. Explicit Guarantees
- **No Database Modification**: No migration scripts or SQL statements will be executed without prior written user approval.
- **Project Directory Compliance**: All project code and repository files remain strictly inside `D:\RR_Bot\Convo-Ai-Bot`.
- **Zero Breaking Changes**: Existing authentication, chat execution, schema discovery, and provider integration flows remain 100% intact.
