# Phase 1D.5.A — Question-Context Evidence Audit

## 1. Current Context Sources
The backend repository contains several isolated contexts, but they are not fully integrated for resolving value ambiguity:
1. **Conversation Memory (`backend/services/conversation_memory.py`)**: Stores the raw user question and the generated SQL query for the last 5 turns of a conversation. It also manages a short-lived `pending_clarification_store` (5 minutes) for handling active user clarification cycles.
2. **Metadata Context (`backend/semantic/semantic_resolver.py`)**: Uses a `SAME_TABLE_BONUS` (0.35) during dimension candidate generation. If a metric is successfully matched to a table, other dimension candidates belonging to the same table receive a score bonus.
3. **Relationship Context (`backend/semantic/relationship_context_service.py` / `relationship_expander.py`)**: Builds path expansions and JOIN paths for SQL generation, but plays no role in resolving semantic value matches.

---

## 2. Available Signals
The system extracts or has access to the following signals:
* **Target Value Matches**: Exact/Fuzzy matching of query tokens against the pre-indexed dimension values.
* **Query-Token Coverage**: Calculated via `AmbiguityClassifier._compute_query_coverage()`.
* **Explicit Wordings / Labels**: Keyword mentions like `"brand"`, `"city"`, `"state"` within the query.
* **Metric Table Associations**: Which table the metric resides in.
* **Previous SQL Queries**: Stored in `conversation_store`.

---

## 3. Safe/Unsafe Classification

| Context Signal | Classification | Justification / Guards |
|---|---|---|
| **Exact Business-Value Mentions** | **SAFE TO USE** | Direct, deterministic exact string matches from the semantic index represent explicit user intent. |
| **Query-Token Coverage** | **SAFE TO USE** | Fully deterministic. Higher token coverage represents a stronger match than sub-spans. Already enforced by Containment filters and updated Rule 1 in `AmbiguityClassifier`. |
| **Explicit User Wordings (e.g. "brand", "city", "state")** | **SAFE TO USE** | Deterministic prefix/suffix matching. If the user writes `"city coimbatore"`, it explicitly narrows the context to the `City` dimension. |
| **Dimension/Business-Name Mentions** | **USE WITH GUARD** | Must be matched adjacently to the value token. If `"brand"` is far away in the query (e.g. `"show brand sales for Coimbatore"`), it may be a general prompt filler rather than a specific filter tag. |
| **Metric Context / Same Table Bonus** | **USE WITH GUARD** | Useful for tie-breaking, but must not be used as an absolute filter. A query could reference a metric on table A and a filter value on table B; table bonus should only act as a minor score weight. |
| **Previously Resolved Dimension/Value** | **USE WITH GUARD** | Critical for resolving elliptical queries (e.g., follow-up `"what about Chennai?"` uses previous city category). Guard: Only apply if the new query contains no other dimensions/metrics and matches the previous dimension type. |
| **Table/Context Hints** | **USE WITH GUARD** | Heuristics that should only act as tie-breakers. |
| **Previous-Turn Context** | **USE WITH GUARD** | Can be retrieved from memory, but must be guarded against topic shifts. |
| **Relationships Between Candidate Dimensions** | **NOT CURRENTLY AVAILABLE** | Dimension relationship matrices are built but not connected to the value resolution path. |
| **Conversation/Session Context (e.g., Company ID)** | **SAFE TO USE** | Strictly used as a security filter (company isolation). Cannot be used to resolve semantic ambiguity between two valid options within the same company. |

---

## 4. Real-Data Candidate Analysis

### Case 1: `show sales for pant`
* **Query Tokens:** `['sales', 'pant']` (excluding stopwords)
* **Candidates:**
  * `Pants` (Product Group)
  * `LS Pant` (Prod Grp2)
  * `Linen Pant` (Brand)
  * `Ramraj Pant` (Brand)
  * `Cotton Pants` (Product Group)
  * `Formal Pants` (Product Group)
* **Candidate Dimensions:** `Product Group`, `Prod Grp2`, `Brand`
* **Candidate Values:** `Pants`, `LS Pant`, `Linen Pant`, `Ramraj Pant`, `Cotton Pants`, `Formal Pants`
* **Available Contextual Evidence:** Metric is `sales`. All candidates are on the `Products` table. No other context is present.
* **Whether Context Should Resolve:** No. There is no semantic cue in the question to distinguish between these pant options.
* **Resolution:** **STRONG_AMBIGUITY** (Clarification required).

### Case 2: `show sales for ramraj pant`
* **Query Tokens:** `['sales', 'ramraj', 'pant']`
* **Candidates:**
  * `Ramraj Pant` (Brand, coverage 2/2)
  * `Linen Pant` (Brand, coverage 1/2)
  * `LS Pant` (Prod Grp2, coverage 1/2)
  * `Pants` (Product Group, coverage 1/2)
* **Candidate Dimensions:** `Brand`, `Prod Grp2`, `Product Group`
* **Candidate Values:** `Ramraj Pant`, `Linen Pant`, `LS Pant`, `Pants`
* **Available Contextual Evidence:** `Ramraj Pant` has 2/2 coverage of the noun phrase.
* **Whether Context Should Resolve:** Yes. The full-coverage candidate represents the complete query target.
* **Resolution:** **WEAK_AMBIGUITY / SINGLE_MATCH** (Auto-resolve to `Ramraj Pant` silently).

### Case 3: `show sales for cotton pant`
* **Query Tokens:** `['sales', 'cotton', 'pant']`
* **Candidates:**
  * `Cotton Pants` (Product Group, coverage 2/2)
  * `Cotton` (Fabric, coverage 1/2)
  * `Linen Pant` (Brand, coverage 1/2)
  * `LS Pant` (Prod Grp2, coverage 1/2)
* **Candidate Dimensions:** `Product Group`, `Fabric`, `Brand`, `Prod Grp2`
* **Candidate Values:** `Cotton Pants`, `Cotton`, `Linen Pant`, `LS Pant`
* **Available Contextual Evidence:** `Cotton Pants` has 2/2 coverage of the noun phrase.
* **Whether Context Should Resolve:** Yes.
* **Resolution:** **WEAK_AMBIGUITY / SINGLE_MATCH** (Auto-resolve to `Cotton Pants` silently).

### Case 4: `show sales for brand ramraj pant`
* **Query Tokens:** `['sales', 'brand', 'ramraj', 'pant']`
* **Candidates:**
  * `Ramraj Pant` (Brand, coverage 2/3)
  * `Linen Pant` (Brand, coverage 1/3)
  * `LS Pant` (Prod Grp2, coverage 1/3)
  * `Pants` (Product Group, coverage 1/3)
* **Candidate Dimensions:** `Brand`, `Prod Grp2`, `Product Group`
* **Candidate Values:** `Ramraj Pant`, `Linen Pant`, `LS Pant`, `Pants`
* **Available Contextual Evidence:** The user explicitly wrote `"brand"` adjacent to the value `"ramraj"`.
* **Whether Context Should Resolve:** Yes. Explicit dimension mention resolves value matching to the `Brand` dimension.
* **Resolution:** **WEAK_AMBIGUITY / SINGLE_MATCH** (Auto-resolve to `Ramraj Pant` (Brand)).

### Case 5: `show sales for city coimbatore`
* **Query Tokens:** `['sales', 'city', 'coimbatore']`
* **Candidates:**
  * `Coimbatore` (City, coverage 1/2)
* **Candidate Dimensions:** `City`
* **Candidate Values:** `Coimbatore`
* **Available Contextual Evidence:** The user explicitly wrote `"city"`.
* **Whether Context Should Resolve:** Yes. Explicit dimension tag isolates context to the `City` dimension.
* **Resolution:** **SINGLE_MATCH** (Auto-resolve to `Coimbatore` (City)).

### Case 6: `show sales for coimbatore`
* **Query Tokens:** `['sales', 'coimbatore']`
* **Candidates:**
  * `Coimbatore` (City, coverage 1/1)
  * `Coimbatore` (State - assuming it also exists)
* **Candidate Dimensions:** `City`, `State`
* **Candidate Values:** `Coimbatore`
* **Available Contextual Evidence:** None.
* **Whether Context Should Resolve:** No.
* **Resolution:** **STRONG_AMBIGUITY** (Clarification required).

### Case 7: `show sales for shirt`
* **Query Tokens:** `['sales', 'shirt']`
* **Candidates:**
  * `Shirts` (Product Group)
  * `T-Shirt` (Product Category)
  * `Red Shirt` (Brand)
  * `Men's Shirt` (Product Category)
  * `Ramraj Shirt` (Brand)
  * `Cotton Shirts` (Product Group)
  * `Formal Shirts` (Product Group)
* **Candidate Dimensions:** `Product Group`, `Product Category`, `Brand`
* **Candidate Values:** `Shirts`, `T-Shirt`, `Red Shirt`, `Men's Shirt`, `Ramraj Shirt`, `Cotton Shirts`, `Formal Shirts`
* **Available Contextual Evidence:** None.
* **Whether Context Should Resolve:** No.
* **Resolution:** **STRONG_AMBIGUITY** (Clarification required).

### Case 8: `show sales for formal shirt`
* **Query Tokens:** `['sales', 'formal', 'shirt']`
* **Candidates:**
  * `Formal Shirts` (Product Group, coverage 2/2)
  * `Shirts` (Product Group, coverage 1/2)
  * `Formal Pants` (Product Group, coverage 1/2)
* **Candidate Dimensions:** `Product Group`
* **Candidate Values:** `Formal Shirts`, `Shirts`, `Formal Pants`
* **Available Contextual Evidence:** `Formal Shirts` matches 2/2 tokens.
* **Whether Context Should Resolve:** Yes.
* **Resolution:** **SINGLE_MATCH** (Auto-resolve to `Formal Shirts`).

### Case 9: `show sales for banian`
* **Query Tokens:** `['sales', 'banian']`
* **Candidates:**
  * `Banians` (Category, coverage 1/1)
* **Candidate Dimensions:** `Category`
* **Candidate Values:** `Banians`
* **Available Contextual Evidence:** Single match.
* **Whether Context Should Resolve:** Yes.
* **Resolution:** **SINGLE_MATCH** (Auto-resolve to `Banians`).

---

## 5. Identified Gaps
1. **Resolution Pipeline Isolation**: `DimensionValueResolver` is completely blind to matched dimension/metric metadata from the query analysis phase. It executes independent semantic matching against the raw database values, losing the score boosts (e.g. `SAME_TABLE_BONUS`) and explicit dimension filters (`"brand"`, `"city"`) matched by the parent resolver.
2. **Missing Dimension Name Prefix/Suffix Matching**: No helper exists in `DimensionValueResolver` to parse the user's query for adjacent dimension names (such as `"brand ramraj"`) and map those to a filter on `dimension.business_name` or `dimension.technical_name`.
3. **No Structured Turn History**: `ConversationMemory` stores raw queries and SQL but does not save the resolved dimensions or value filters from the previous turn in a structured schema. This makes it impossible to resolve elliptical follow-ups (e.g. `"what about Coimbatore?"` following `"show sales for Chennai"`) without re-parsing the entire history.

---

## 6. Proposed Deterministic Context-Resolution Contract
To safely resolve ambiguity without using loose heuristics or "highest rank" rules, the system will apply the following deterministic contract:
1. **Explicit Tag Rule**: If a value candidate `C` is associated with a query token `T` matching a dimension `D`, and the query contains `D`'s business/technical name adjacent to `T` (e.g., `[D_name] [Value]` or `[Value] [D_name]`), candidate `C` shall be selected and all other candidates for different dimensions shall be suppressed.
2. **Follow-Up Ellipsis Rule**: If the current query has a single target value that matches multiple dimensions, and the previous turn successfully resolved a query containing a value for one of those dimensions (with no topic shift in metrics), the system will select the candidate in the previously matched dimension.
3. **Metric Table Tie-Breaker**: If multiple candidates match the same query tokens with identical priority, coverage, and confidence, and one candidate's dimension belongs to the table resolved by the active query metric, that candidate will receive a small score bonus (+0.10). If the confidence gap remains $< 0.05$, the system must still fall back to `STRONG_AMBIGUITY`.
4. **Clarification Fallback**: If the conditions above are not met, the query MUST remain `STRONG_AMBIGUITY`.

---

## 7. Production Files Requiring Modification in 1D.5.B/C
* `backend/semantic/semantic_resolver.py`: To pass down resolved dimension/metric contexts to `DimensionValueResolver.resolve()`.
* `backend/semantic/dimension_value_resolver.py`: To accept dimension/metric contexts, evaluate prefix/suffix labels, apply follow-up state inference, and apply metric table bonuses.
* `backend/services/conversation_memory.py`: To store and retrieve resolved dimension/value metadata alongside the query history.
