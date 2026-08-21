# PHASE 1D.6.D.1 — CLARIFICATION DATA-FLOW AUDIT

## Observed Production Defect

**Initial Query:** `"Show cotton pant sales"`

**Backend Response (seen in UI):**
```
Did you mean the Prod Grp2 'LS ZARI COTTON'
or the Prod Grp2 'LS COTTON BREEZE'
or the Prod Grp2 'MENS PYJAMA PANT'?
```

**User Reply:** `"I meant Prod Grp2 'MENS PYJAMA PANT'"`

**Backend Response:**
```
Your selection was ambiguous. Please clarify by choosing exactly one option.
```

---

## 1. CLARIFICATION EXCEPTION PAYLOAD CREATION

### Source: `prompt_builder.py` lines 394-443 (STRONG_AMBIGUITY)

When `SemanticGate.evaluate()` returns `status == "STRONG_AMBIGUITY"`, `PromptBuilder.build_sql_prompt()` constructs options from `semantic_result["value_matches"]`:

```python
options.append({
    "option_id": idx + 1,
    "value": m["value"],                                  # USER-FACING
    "dimension": m["business_name"],                      # "Prod Grp2" LEAKS
    "business_name": m["business_name"],                  # "Prod Grp2" LEAKS
    "dimension_id": m["dimension_id"],                    # INTERNAL GUID
    "table_name": m["table_name"],                        # INTERNAL
    "column_name": m["column_name"],                      # INTERNAL
    "normalized_value": m.get("normalized_value", ...),   # INTERNAL
    "match_type": m.get("match_type"),                    # INTERNAL
    "matched_question_tokens": m.get(...),                # INTERNAL
    "matched_value_tokens": m.get(...)                    # INTERNAL
})
```

The `msg` string is constructed at line 427-428:
```python
opt_str = "\n".join(f"{opt['option_id']}. {opt['value']}" for opt in options[:5])
msg = f'I found multiple possible matches for "{matched_phrase}".\nPlease choose one:\n\n{opt_str}'
```

**Finding:** The `msg` string itself is CLEAN (only shows `option_id` and `value`).
The `dimension` field contains `business_name` which is raw semantic metadata like `"Prod Grp2"`.

### Source: `prompt_builder.py` lines 357-383 (PARTIAL_MATCH)

Same pattern. Options include all internal fields.

---

## 2. HOW "PROD GRP2" REACHES THE USER

### Root Cause Analysis

The **backend message string** (`msg`) does NOT include "Prod Grp2". It looks like:
```
I found multiple possible matches for "cotton pant".
Please choose one:

1. LS ZARI COTTON
2. LS COTTON BREEZE
3. MENS PYJAMA PANT
```

However, the `dimension` and `dimension_id` fields are sent in the public response.

**There are TWO paths where "Prod Grp2" can reach the user:**

### Path A: The `dimension` field in the public option schema

At `app.py` lines 656-667, when the initial clarification is stored and returned:
```python
clean_options.append({
    "option_id": opt["option_id"],
    "value": opt["value"],
    "dimension": opt["dimension"],      # "Prod Grp2" LEAKS HERE
    "dimension_id": opt["dimension_id"] # GUID LEAKS HERE
})
```

The `dimension` field contains raw `business_name` from the semantic layer (e.g., `"Prod Grp2"`).
The `dimension_id` is a database GUID.

These fields are sent to the frontend. The frontend at `ChatPage.jsx` line 729 renders:
```javascript
content: typeof data.error === 'object' && data.error !== null
    ? data.error.message : String(data.error)
```

The frontend displays `data.error.message` which IS the clean message text.

### Path B: Previous version / chat history rendering

The `result_data` saved to `chat_messages` (line 681-686) includes the FULL error dict with `dimension` and `dimension_id`. When messages are loaded from history (line 601-604), this metadata is parsed back into the UI.

The **observed** "Prod Grp2" wording (`"Did you mean the Prod Grp2 'LS ZARI COTTON'..."`) does NOT match the current `msg` template. This indicates the observation was from a **previous code version** that used a different message template like:
```
"Did you mean the [dimension] '[value1]' or the [dimension] '[value2]'?"
```

This template was documented in `phase1d_2_d_clarification_contract_audit.md` line 125-126.

**Current state:** The `msg` template has been updated to show numbered clean options. But `dimension` and `dimension_id` still leak in the structured option objects.

---

## 3. PENDING CLARIFICATION STORAGE

### Source: `conversation_memory.py` lines 74-95

**Storage key:** `(employee_id, session_id)` tuple in `pending_clarification_store` dict.

**Stored object:**
```python
{
    "original_question": "Show cotton pant sales",
    "ambiguity_type": "SAME_DIMENSION" | "CROSS_DIMENSION",
    "options": {
        "1": {
            "option_id": 1,
            "value": "LS ZARI COTTON",
            "dimension": "Prod Grp2",
            "business_name": "Prod Grp2",
            "dimension_id": "DCBA558A-...",
            "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
            "column_name": "ProdGrp2",
            "normalized_value": "ls zari cotton",
            "match_type": "SINGULAR_PLURAL",
            "matched_question_tokens": ["cotton"],
            "matched_value_tokens": ["ls", "zari", "cotton"]
        },
        "2": { "..." : "..." },
        "3": { "..." : "..." }
    },
    "timestamp": 1723456789.123
}
```

**TTL:** 300 seconds (5 minutes). Checked at retrieval time.

**Isolation:** `(employee_id, session_id)` key ensures user and session isolation.

---

## 4. PUBLIC RESPONSE SCHEMA

### What the frontend receives (HTTP 400 response body):

```json
{
    "success": false,
    "action": "CLARIFICATION_REQUIRED",
    "error": {
        "code": "AMBIGUITY_DETECTED",
        "category": "SEMANTIC",
        "title": "Clarification Required",
        "message": "I found multiple possible matches for \"cotton pant\".\nPlease choose one:\n\n1. LS ZARI COTTON\n2. LS COTTON BREEZE\n3. MENS PYJAMA PANT",
        "suggestion": "Please clarify by selecting one of the options.",
        "details": {
            "original_question": "Show cotton pant sales",
            "ambiguity_type": "SAME_DIMENSION",
            "options": [
                {
                    "option_id": 1,
                    "value": "LS ZARI COTTON",
                    "dimension": "Prod Grp2",
                    "dimension_id": "DCBA558A-..."
                },
                {
                    "option_id": 2,
                    "value": "LS COTTON BREEZE",
                    "dimension": "Prod Grp2",
                    "dimension_id": "DCBA558A-..."
                },
                {
                    "option_id": 3,
                    "value": "MENS PYJAMA PANT",
                    "dimension": "Prod Grp2",
                    "dimension_id": "DCBA558A-..."
                }
            ]
        }
    }
}
```

### METADATA LEAK INVENTORY

| Field | Status | Risk |
|---|---|---|
| `option_id` | SAFE | Numeric sequence |
| `value` | SAFE | Display value |
| `dimension` | **LEAKS** | Contains raw `business_name` like `"Prod Grp2"` |
| `dimension_id` | **LEAKS** | Database GUID |
| `table_name` | Stripped | Not in public response |
| `column_name` | Stripped | Not in public response |
| `normalized_value` | Stripped | Not in public response |

---

## 5. SELECTION PARSING

### Source: `app.py` lines 407-487

**User input:** `question` parameter from `/ask?question=...`

The raw user question string arrives. It is lowercased and normalized.

### Tier 1: Numeric ID match (lines 428-436)
- Regex: `\b(?:option|number|no\.?|choice|select|want)?\s*([1-9])\b`
- Matches: `"1"`, `"option 2"`, `"number 3"`, `"select 1"`, `"first"` (via word-to-digit mapping)

### Tier 2: Exact candidate value (lines 438-443)
- Compares `q_clean == val_lower`
- **DEFECT D3:** Does NOT strip surrounding quotes. If user sends `'MENS PYJAMA PANT'` with quotes in the URL, exact match fails.

### Tier 3: Value embedded in input (lines 445-453)
- Strips single/double quotes from both sides
- Checks if `val_no_quotes in q_no_quotes`
- **Has `break`** (recently added). Stops after first match found.

### Tier 4: Prefix match (lines 455-461)
- Checks `val_lower.startswith(q_clean)`
- **Has `break`** (recently added).

### Tier 5: Substring match (lines 463-469)
- Checks `q_clean in val_lower`
- **Has `break`** (recently added).

### Tier 6: Token overlap match (lines 471-486)
- Removes conversational stopwords from user input
- Checks if ALL user tokens appear in option value tokens
- **DEFECT D4:** Does NOT have `break`. Can accumulate multiple matches.

---

## 6. THE CRITICAL BUG - WHY SELECTION FAILS

### Reproducing the exact reported scenario

User sends: `"I meant Prod Grp2 'MENS PYJAMA PANT'"`

`q_clean = "i meant prod grp2 'mens pyjama pant'"`

**Tier 1 (numeric):** No digits found. Skip.

**Tier 2 (exact):** `"i meant prod grp2 'mens pyjama pant'"` != any option value. Skip.

**Tier 3 (substring embed):**
```
q_no_quotes = "i meant prod grp2 mens pyjama pant"
```
- `"ls zari cotton"` in `"i meant prod grp2 mens pyjama pant"` -> NO
- `"ls cotton breeze"` in `"i meant prod grp2 mens pyjama pant"` -> NO
- `"mens pyjama pant"` in `"i meant prod grp2 mens pyjama pant"` -> **YES** -> match + break

**Result: 1 match -> SHOULD RESOLVE CORRECTLY.**

This means the Tier 3 substring match DOES work for this input. The issue with the "ambiguous" response was from **before the `break` was added** or from a different input pattern.

### Alternative failure scenario (no break, old code)

With the OLD code (no `break` in Tier 3), all options are checked:
- Only `"mens pyjama pant"` matches -> still 1 match -> should work

### Alternative failure scenario (token overlap without break)

If somehow Tiers 2-5 all miss, Tier 6 processes:
```
q_tokens after stopword removal: ["prod", "grp2", "mens", "pyjama", "pant"]
```
- Option "MENS PYJAMA PANT" tokens: `["mens", "pyjama", "pant"]`
- Check: all of `["prod", "grp2", "mens", "pyjama", "pant"]` in `["mens", "pyjama", "pant"]`? 
- `"prod"` NOT in option tokens -> NO MATCH

So Tier 6 correctly fails. The fallback is to the `else` branch which checks for intent shift or reports invalid selection.

### TRUE ROOT CAUSE

The old message template `"Did you mean the Prod Grp2 'MENS PYJAMA PANT'"` exposed the dimension name. When the user echoed it back as `"I meant Prod Grp2 'MENS PYJAMA PANT'"`, the matching algorithm at that time was different (possibly a simpler version without the current tiered approach), and produced either an ambiguous or invalid result.

The current tiered matching DOES handle this case correctly in Tier 3. However, the `dimension` and `dimension_id` metadata leaks are still present in the public response, which means:

1. The UI can still theoretically display "Prod Grp2" if the frontend renders the structured options
2. The `chat_messages` table stores the full error payload including "Prod Grp2"
3. The old stored messages will show the old format when loaded from history

---

## 7. RESUME PATH

### Source: `app.py` lines 489-510

When `len(matched_options) == 1`:
1. `selected_candidate = matched_options[0]` - full internal option object
2. CLS validation against `selected_candidate["column_name"]`
3. `question = original_question` - restores the original question
4. `is_clarification_resume = True`
5. Falls through to `generate_sql_query(question, history, company_id, clarified_candidate=selected_candidate)`
6. On success: `clear_pending_clarification()` at line 693-694

**Security revalidation:** CLS check pre-SQL, RBAC on endpoint, RLS at query execution.

---

## 8. PENDING-STATE CLEARING

| Event | State Action | Location |
|---|---|---|
| Valid selection + successful SQL | Clear | `app.py:693-694` |
| Invalid selection | Keep (re-prompt) | `app.py:561-590` |
| Ambiguous selection | Keep (re-prompt + refresh TTL) | `app.py:532-543` |
| Intent shift | Clear | `app.py:558-560` |
| TTL expiry | Auto-clear on next retrieval | `conversation_memory.py:83-85` |

---

## 9. TTL HANDLING

- Set at `set_pending_clarification()` with `state["timestamp"] = time.time()`
- Checked at `get_pending_clarification()` with `time.time() - state["timestamp"] > 300`
- On expiry: `pending_clarification_store.pop(key, None)` and returns `None`
- 300 seconds = 5 minutes

---

## 10. INTENT-SHIFT HANDLING

### Source: `app.py` lines 544-560

When matched_options is empty:
1. Call `SemanticResolver.resolve(connection_id, question)` on the NEW question
2. Check if the new question resolves any metrics, dimensions, or values
3. If YES -> intent shift -> `clear_pending_clarification()` -> process normally
4. If NO -> invalid selection -> return error, keep state

---

## 11. WHAT THE FRONTEND DISPLAYS

### Source: `ChatPage.jsx` lines 725-734

```javascript
if (data.error) {
    errorMsg.content = data.error.message;  // Clean message text
    errorMsg.error = data.error;            // Full error object stored
}
```

### Source: `ChatPage.jsx` lines 1188-1206

Error rendered as `<Alert>`:
- title: `msg.error.title` -> "Clarification Required"
- description: `msg.error.message` -> the clean numbered options text
- suggestion shown below

**No special rendering of structured `options` array.** Frontend displays the raw `message` string as plain text. No clickable option buttons.

---

## 12. FIELD CLASSIFICATION

### USER-FACING (safe to expose)

| Field | Purpose |
|---|---|
| `option_id` | Numeric option sequence (1, 2, 3) |
| `value` | Display value (e.g., "MENS PYJAMA PANT") |

### SHOULD BE REMOVED FROM PUBLIC RESPONSE

| Field | Purpose | Risk |
|---|---|---|
| `dimension` | Raw `business_name` like "Prod Grp2" | Exposes internal semantic metadata |
| `dimension_id` | Database GUID | Exposes internal database identifier |

### INTERNAL ONLY (correctly stripped in current code)

| Field | Purpose |
|---|---|
| `table_name` | Source database table |
| `column_name` | Source database column |
| `normalized_value` | Lowercased match value |
| `match_type` | Internal matching algorithm type |
| `matched_question_tokens` | Debug tokens |
| `matched_value_tokens` | Debug tokens |

---

## 13. ANSWERS TO SPECIFIC QUESTIONS

### Where is "Prod Grp2" being added?

`prompt_builder.py` line 403: `"dimension": m["business_name"]`

The `business_name` comes from the `semantic_dimensions` table. For the Ramraj database, `ProdGrp2` column has `business_name = "Prod Grp2"`. This value flows through:
1. `dimension_value_resolver.py` -> `MatchResult.business_name`
2. `semantic_resolver.py` -> `value_matches[].business_name`
3. `prompt_builder.py` -> `options[].dimension = m["business_name"]`
4. `app.py` clean_options -> `"dimension": opt["dimension"]` (NOT stripped)
5. Frontend response -> `data.error.details.options[].dimension`

### Why can "MENS PYJAMA PANT" map to multiple candidates?

It should NOT in the current code. The reported bug was from the old code state. The current Tier 3 with `break` correctly resolves to exactly 1 match.

### Is matching against pending options or re-running global semantic retrieval?

**Against pending options.** The matching at `app.py:426-487` iterates `options_map` from the stored pending state. Global `SemanticResolver.resolve` is only called for intent shift detection when no option matches.

### What exact object is stored server-side?

Full internal candidate metadata including `table_name`, `column_name`, `normalized_value`, `dimension`, `dimension_id`, etc.

### What exact object is sent to the frontend?

Partially cleaned. `table_name`, `column_name`, `normalized_value` stripped. But `dimension` and `dimension_id` still leak.

### What exact user input is returned to /ask?

The raw `question` query parameter string from the URL.

---

## 14. COMPLETE DEFECT INVENTORY

| # | Defect | Location | Severity |
|---|---|---|---|
| D1 | `dimension` (raw business_name like "Prod Grp2") leaks in public response | `app.py` 3 clean_options blocks (lines 519-521, 567-571, 659-662) | HIGH |
| D2 | `dimension_id` (database GUID) leaks in public response | `app.py` 3 clean_options blocks (lines 522, 572, 663) | HIGH |
| D3 | Tier 2 exact match does not strip surrounding quotes | `app.py` line 442 | MEDIUM |
| D4 | Tier 6 token overlap match lacks `break` | `app.py` line 486 | MEDIUM |
| D5 | Old message template exposed dimension names | Previous code version | FIXED |

---

## 15. FINAL VERDICT

**FAIL - SELECTION/DATA-FLOW DEFECTS IDENTIFIED**

**4 open defects require fixing in Phase 1D.6.D.2:**

1. Remove `dimension` and `dimension_id` from all 3 `clean_options` blocks in `app.py`
2. Add quote stripping to Tier 2 exact match in `app.py`
3. Add `break` to Tier 6 token overlap match in `app.py`
4. Verify existing tests cover these exact scenarios

**Files to modify:** `app.py` only (minimal, focused changes)
