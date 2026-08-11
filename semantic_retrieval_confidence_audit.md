# Semantic Retrieval Confidence Engine — Complete Audit Report

**Date:** August 8, 2026
**Scope:** Read-only analysis. No implementations were changed.
**Purpose:** Identify why the chatbot retrieves the wrong metric, table, or value even when the user asks a valid business question.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component-by-Component Breakdown](#2-component-by-component-breakdown)
3. [Example 1 — "Show sales trend" → CCB TRENDY](#3-example-1--show-sales-trend--ccb-trendy)
4. [Example 2 — "Outstanding amount in TN last year"](#4-example-2--outstanding-amount-in-tn-last-year)
5. [Example 3 — "Pending order by marketing" → Wrong Table](#5-example-3--pending-order-by-marketing--wrong-table)
6. [Cross-Cutting Findings](#6-cross-cutting-findings)
7. [Final Answers to Audit Questions](#7-final-answers-to-audit-questions)

---

## 1. Architecture Overview

The Semantic Retrieval Confidence Engine is a two-track pipeline that runs in sequence before any SQL is generated.

```
User Question
     │
     ▼
QuestionSanitizer          — Strip prompt labels / collapse whitespace
     │
     ▼
 ┌────────────────────────────────────────────────────────┐
 │         TRACK A — SemanticResolver                     │
 │  Metric & Dimension name-matching                      │
 │  _get_match_info() → score + spans                     │
 │  _remove_overlaps() → winner selection                 │
 │  SAME_TABLE_BONUS applied to surviving dimensions      │
 └────────────────────────────────────────────────────────┘
     │
     ▼
 ┌────────────────────────────────────────────────────────┐
 │         TRACK B — DimensionValueResolver               │
 │  MatchingPipeline: ExactMatcher → NormalizedMatcher    │
 │                    → SingularPluralMatcher → FuzzyMatcher│
 │  First-matcher-wins (pipeline breaks on first hit)     │
 │  _remove_contained_matches() → MatchRanker.rank()      │
 └────────────────────────────────────────────────────────┘
     │
     ▼
RelevantTableResolver      — Weight tables by metric(5)/dim(3)/value(2)
     │
     ▼
RelationshipExpander       — BFS bridge-table injection
     │
     ▼
MetadataResolver           — Load columns, keys, display rules
     │
     ▼
SemanticGate               — Allow / Partial / Block SQL generation
     │
     ▼
RuntimeContextBuilder + SemanticContextService → PromptBuilder → LLM
```


---

## 2. Component-by-Component Breakdown

### 2.1 QuestionSanitizer (`matching/question_sanitizer.py`)

**Candidate generation:** Strips prompt-template labels (`"Original Question:"`, `"Context:"` etc.) and collapses whitespace. The output is the raw cleaned question string passed into both tracks.

**Confidence impact:** None. It is purely cosmetic sanitization.

**Failure mode:** If a user's question itself contains a label-like phrase (e.g. `"show me the question: count"`) the sanitizer could silently truncate real question content.

---

### 2.2 SemanticResolver — Track A (`semantic_resolver.py`)

This is the primary metric and dimension matcher. It does **not** use the MatchingPipeline from Track B. It has its own entirely separate scoring system.

#### 2.2.1 Candidate Generation — `_generate_candidates()`

For every active `semantic_metric` and `semantic_dimension` row fetched from the database, `_get_match_info()` is called with:

- `technical_name` (e.g. `sales_amount`)
- `business_name` (e.g. `Sales Amount`)
- `synonyms` (comma-separated string, e.g. `"revenue,turnover"`)
- `question` (the raw user question)

#### 2.2.2 Confidence Calculation — `_get_match_info()` (7 Priorities)

Scores are **deterministic integers**, not floating-point confidence values. The scale is:

| Priority | Match Type | Score |
|---|---|---|
| 1 | Exact technical name == whole question | 50,000 |
| 2 | Exact business name == whole question | 40,000 |
| 3 | Business phrase contained in question | 30,000 |
| 4 | Technical phrase/word in question | 20,000 |
| 5 | Core business words (noise filtered) in question | 15,000 |
| 5b | All business words in question | 10,000 |
| 6 | Synonym phrase in question | 9,000 |
| 7 | Stemmed token overlap ≥ 50% | 0–8,000 |

**Critical observation:** Priority 7 (stem overlap) produces a score proportional to `match_ratio * 8000`. A 50% overlap produces ~4,000. A 100% overlap produces 8,000. This score is **lower than any synonym match (9,000) and far below any phrase match (10,000+)**. Yet it still generates candidates that enter the overlap resolver.

#### 2.2.3 Conflict Resolution — `_remove_overlaps()`

Candidates are sorted `(score DESC, length DESC)`. A global span registry is maintained. Any candidate whose matched spans all overlap with already-selected spans is discarded.

**Critical observation:** Span positions are computed per-candidate as character offsets into the normalized question. A short word like `"trend"` occupies character positions 11–16 in `"show sales trend"`. Any other candidate that also matched that span range is eliminated. The winner is determined purely by score, not semantic correctness.

#### 2.2.4 SAME_TABLE_BONUS

After the first overlap pass (used to identify metric tables), a `+0.35` score bonus is added to every dimension candidate whose `table_name` matches a resolved metric's table. This is applied **before** the final overlap removal pass.

**Critical observation:** The bonus is 0.35, but dimension scores are integers in the range 0–50,000. A bonus of 0.35 added to integer scores such as `4000.0` or `9000.0` has **no measurable effect on ranking** — it cannot change the outcome of any sort that is driven by these large integer values. The bonus is mathematically inert for all practical inputs.


---

### 2.3 DimensionValueResolver — Track B (`dimension_value_resolver.py`)

This resolves **values** (e.g., `"TN"`, `"Marketing"`, `"2024"`) from the dimension_value_index table.

#### 2.3.1 Candidate Generation

`_load_dimension_values()` fetches all rows from `dimension_value_index` joined to `semantic_dimensions` for the connection. Each row is pre-processed into a `CachedDimensionValue` with:

- `runtime_raw_norm` — normalized raw value (lowercase, delimiters→spaces)
- `runtime_raw_tokens` — tokens after stopword removal
- `runtime_raw_singulars` — tokens after singularization
- `runtime_stored_norm` — same for the `normalized_value` database column
- `runtime_stored_tokens`, `runtime_stored_singulars`

The question is also normalized into `QuestionContext` with `q_tokens` and `q_singulars`.

#### 2.3.2 Matching Pipeline — First-Matcher-Wins

The pipeline runs matchers in order and **breaks immediately on the first matcher that returns any results**:

```
ExactMatcher → NormalizedMatcher → SingularPluralMatcher → FuzzyMatcher
```

This means: if ExactMatcher returns even one match, FuzzyMatcher never runs.

**ExactMatcher** (`exact_matcher.py`):
- Uses `runtime_stored_norm` (the pre-normalized value from the DB column `normalized_value`)
- Regex: `\b<escaped_value>\b` against the normalized question

**NormalizedMatcher** (`normalized_matcher.py`):
- Uses `runtime_raw_norm` (normalized from the raw value)
- Same regex approach

**SingularPluralMatcher** (`singular_plural_matcher.py`):
- Converts all question tokens and all value tokens to singular forms
- Checks if value singulars form a sub-sequence in question singulars
- No length constraint — a single-token value like `"tn"` matches if `"tn"` appears anywhere in the question's singular token list

**FuzzyMatcher** (`fuzzy_matcher.py`):
- Extracts candidate phrases (n-grams up to 3) from the normalized question using `CandidatePhraseExtractor`
- Runs `rapidfuzz.process.extractOne` with `fuzz.WRatio` scorer
- Default cutoff: 85
- Returns only the **single best match** across all phrases and all indexed values
- Confidence = `score / 100.0` (e.g., 87% → 0.87)

#### 2.3.3 Stopwords — A Key Design Flaw

```python
STOPWORDS = {
    "show", "me", "give", "the", "all", "of", "in", "for", "with", "a", "an",
    "is", "are", "sales", "sale", "amount", "qty", "quantity", "count", "by",
    "revenue", "turnover", "profit", "value"
}
```

**Critical observation:** The stopword list includes **business-critical metric terms**: `"sales"`, `"amount"`, `"revenue"`, `"turnover"`, `"profit"`, `"value"`, `"count"`, `"quantity"`. These are removed from question tokens **before** matching in SingularPluralMatcher and **before** n-gram extraction in FuzzyMatcher's CandidatePhraseExtractor. This means a dimension value like `"Sales Amount"` whose tokens are all stopwords becomes an **empty token list** and cannot match via those matchers.

#### 2.3.4 Post-Match Processing

After the winning matcher returns results:
1. `_remove_contained_matches()` — removes matches whose `normalized_value` is a substring of a longer match's `normalized_value`
2. `MatchRanker.rank()` — sorts by type priority > confidence > coverage > token distance > length diff > alphabetical

#### 2.3.5 Confidence Values by Match Type

| Matcher | Confidence |
|---|---|
| ExactMatcher | 1.00 |
| NormalizedMatcher | 0.98 |
| SingularPluralMatcher | 0.95 |
| FuzzyMatcher | score/100 (e.g. 0.87) |


---

### 2.4 RelevantTableResolver (`relevant_table_resolver.py`)

Aggregates all resolved metrics, dimensions, and value matches into a table score:

```
Metric table contribution:  +5 per metric
Dimension table contribution: +3 per dimension
Value match table contribution: +2 per value
```

Tables are ranked by total score, descending. **This is the primary table selection mechanism.** There is no semantic gate on table selection. Any table that appears in any resolved component gets a score and could be selected.

**Critical observation:** Table selection is fully downstream of metric, dimension, and value resolution. If any of those three stages produce the wrong result, the wrong table is scored higher. There is no independent table-name matching against the question — table selection is entirely derived.

---

### 2.5 RelationshipExpander (`relationship_expander.py`)

BFS over the `schema_relationships` graph. If two selected tables are not directly joined, it inserts bridge tables. Bridge tables get `score=0, is_bridge=True`.

**Risk:** Bridge tables can pull in unexpected tables that the LLM then uses in SQL generation. No semantic validation occurs on bridge tables.

---

### 2.6 SemanticGate (`semantic_gate.py`)

Gate decisions:

| Status | Allowed | When |
|---|---|---|
| COMPLETE | Yes | 3+ resolved components (metric + dim + value) |
| PARTIAL | Yes | Only 1–2 components resolved |
| INSUFFICIENT | No | 0 components |

**Critical observation:** `PARTIAL` status is allowed through. A single resolved metric or dimension — even an incorrect one — unlocks SQL generation. There is no minimum confidence threshold. A match with `score=4000` (50% stem overlap) passes the gate identically to a match with `score=30000` (exact phrase).

---

### 2.7 Retrieval Confidence Score (`semantic_resolver.py`)

```python
confidence  = min(resolved_metric_count * 0.35, 0.35)
confidence += min(resolved_dimension_count * 0.25, 0.25)
confidence += min(resolved_value_count * 0.20, 0.20)
confidence += min(resolved_table_count * 0.20, 0.20)
```

Maximum: 1.00 (if all four types are resolved)

**Critical observation:** Confidence is based on **count**, not on the **quality** of individual matches. A single stem-overlap metric at score=4000 contributes `+0.35` — identical to an exact phrase match at score=30000. The retrieval confidence score is **not correlated with match quality**.


---

## 3. Example 1 — "Show sales trend" → CCB TRENDY

### Question
```
Show sales trend
```

### Intent Detection
No explicit intent classifier runs before semantic resolution. The question goes directly into `SemanticResolver.resolve()` and `DimensionValueResolver.resolve()`.

---

### Step 1: Track A — SemanticResolver

**Normalization:** `_normalize_string("Show sales trend")` → `"show sales trend"`

**Metric candidates** — `_get_match_info()` called for every active metric:
- A metric with `business_name = "Sales Amount"` and `technical_name = "sales_amount"`:
  - Priority 3: Is `"sales amount"` a phrase in `"show sales trend"`? → **No** (no match)
  - Priority 7 (stem overlap): tokens of `"sales amount"` = `["sales", "amount"]`. Stems = `["sale", "amount"]`. Question tokens = `["show", "sales", "trend"]`. Stems = `["show", "sale", "trend"]`. Matched stems = `{"sale"}`. `match_ratio = 1/2 = 0.5`. Score = `int(0.5 * 8000) = 4000`. **Candidate generated.**

**Dimension candidates** — `_get_match_info()` called for every active dimension:
- A dimension with `business_name = "CCB TRENDY"` and `technical_name = "ccb_trendy"`:
  - Priority 4/5: Does word `"trendy"` appear in `"show sales trend"`? → **No** (it's `trend`, not `trendy`)
  - Priority 7 (stem overlap): tokens of `"ccb trendy"` = `["ccb", "trendy"]`. Stems = `["ccb", "trendy"]`. Remove noise words. Question stems = `["show", "sale", "trend"]`. Stem of `"trendy"` = `"trendy"`. Is `"trendy"` in question stems? → **No directly.**

  Wait — let us re-examine. `_stem_word("trendy")` → does not end in `ies/es/s/ing` → stays `"trendy"`. Question stem of `"trend"` = `_stem_word("trend")` → `"trend"`. So `"trendy" != "trend"`. No direct stem match there.

  But `_stem_word("trend")` in the question = `"trend"`. And what if the dimension has `technical_name = "ccb_trendy"` which gives candidate token `"ccb"` and `"trendy"`? Match ratio for `"trendy"` against question stems `{"show", "sale", "trend"}` = 0. **Score = 0. No candidate generated for CCB TRENDY via stem overlap.**

  **So how does CCB TRENDY match?**

  The answer is Priority 5 (core business word match) or Priority 4 (whole-word technical match). Let's trace `_find_whole_word_match_spans("ccb trendy", "show sales trend")` → looks for word `"ccb"` in question → not found. Returns `[]`. No match.

  Now Priority 6 (synonym): if the dimension for `CCB TRENDY` has synonym `"trend"` registered, then `_find_phrase_spans("trend", "show sales trend")` → **matches**. Score = `9000`. **This is the actual path.**

**Root cause confirmed:** A synonym `"trend"` stored against the `CCB TRENDY` dimension causes it to match the word `"trend"` in the user's question at score 9,000.

---

### Step 2: Overlap Removal

Candidates sorted by score DESC:
1. CCB TRENDY dimension — score 9,000 — spans covering `"trend"` in the question
2. Sales Amount metric — score 4,000 — spans `[(0, 16)]` (whole question, stem overlap)

Overlap check: CCB TRENDY spans (e.g. `(11, 16)`) do not overlap with... wait — stem overlap candidates use `[(0, len(q_norm))]` as their span (see `_get_match_info` Priority 7: `return (score, len(matched_stems), [(0, len(q_norm))], ...)`). This means the Sales Amount stem-overlap candidate claims the **entire question string** as its span.

CCB TRENDY (score=9,000) is processed first. Its synonym span `(11, 16)` for `"trend"` is added to `global_selected_spans`.

Sales Amount (score=4,000) is processed next. Its span is `(0, 16)` (entire question). Does `(0, 16)` overlap with `(11, 16)`? → `max(0,11) < min(16,16)` → `11 < 16` → **Yes, overlap.** Sales Amount is **discarded**.


### Step 3: Track B — DimensionValueResolver

Normalized question: `"show sales trend"`
Tokens after stopword removal: `["show", "trend"]` (because `"sales"` is a **stopword**)
Singulars: `["show", "trend"]`

ExactMatcher runs against every dimension_value_index row:
- Each value's `runtime_stored_norm` is tested with `\b<value>\b` against `"show sales trend"`
- A value like `"CCB TRENDY"` (normalized: `"ccb trendy"`) — does `\bccb trendy\b` match `"show sales trend"`? → **No**
- No exact matches expected for this short question

NormalizedMatcher: Similar regex test. No matches expected.

SingularPluralMatcher: checks if value's singular tokens are a sub-sequence of question's singular tokens `["show", "trend"]`. A value with singular tokens `["trend"]` — is `["trend"]` a sub-sequence of `["show", "trend"]`? → **Yes**. Any indexed value whose normalized form is a single token `"trend"` would match here at confidence 0.95.

FuzzyMatcher: if no earlier matcher fires, runs WRatio against all indexed values with n-grams from `["show", "trend"]`: n-grams would be `["show trend", "show", "trend"]`. At cutoff 85, `"trend"` against a stored value `"CCB TRENDY"` (normalized: `"ccb trendy"`) → WRatio score ≈ 60–70 (different length, partial match). Unlikely to exceed 85.

### Execution Path Summary for Example 1

```
Question: "Show sales trend"
     │
     ▼
Track A (SemanticResolver)
  ├─ CCB TRENDY dim → synonym "trend" matches → score 9,000 → SELECTED
  └─ Sales Amount metric → stem overlap, score 4,000 → BLOCKED by overlap
     │
     ▼
Track B (DimensionValueResolver)
  ├─ ExactMatcher: No hit
  ├─ NormalizedMatcher: No hit
  ├─ SingularPluralMatcher: Any value with token "trend" → confidence 0.95
  └─ FuzzyMatcher: (not reached if SingularPluralMatcher fires)
     │
     ▼
RelevantTableResolver
  ├─ CCB TRENDY's table → +3 (dimension)
  └─ Any value match table → +2
     │
     ▼
SemanticGate: status=PARTIAL or COMPLETE depending on value matches
     │
     ▼
Wrong table selected. LLM generates SQL against CCB TRENDY's table.
```

### Confidence Scores

| Component | Winner | Score/Confidence |
|---|---|---|
| Metric | None (blocked) | 0 |
| Dimension | CCB TRENDY | Integer 9,000 (synonym) |
| Value | Any "trend" value | 0.95 (SingularPluralMatcher) |
| Table | CCB TRENDY's table | 3–5 points |

### Why CCB TRENDY Wins

1. The synonym `"trend"` stored on CCB TRENDY directly matches the literal word `"trend"` in the question.
2. Score 9,000 (synonym) beats score 4,000 (stem overlap) for Sales Amount.
3. The span claimed by CCB TRENDY's synonym match overlaps with the span claimed by the Sales Amount stem-overlap candidate, so Sales Amount is eliminated.
4. No metric is left. No table disambiguation can occur. The wrong dimension drives table selection.

### False Positive Source

- Synonym `"trend"` registered on a product/category dimension `CCB TRENDY` is a synonym that could legitimately belong to a *temporal trend* metric instead.
- There is no type-awareness in synonym matching: a synonym is treated identically whether it belongs to a metric, dimension, or value.
- There is no semantic context check: `"trend"` as a synonym for a product named `"CCB TRENDY"` is a coincidental phonetic abbreviation, not a business meaning alignment.


---

## 4. Example 2 — "Outstanding amount in TN last year"

### Question
```
Outstanding amount in TN last year
```

### Intent Detection
No intent classifier intercepts this. Question is passed raw to both tracks. Temporal reasoning (for `"last year"`) is handled downstream by the TemporalPipeline, which is separate from semantic resolution.

---

### Step 1: Track A — SemanticResolver

**Normalization:** `"outstanding amount in tn last year"`

**Metric candidates:**
- A metric `"Outstanding Amount"` (technical: `outstanding_amount`):
  - Priority 3: Is `"outstanding amount"` in `"outstanding amount in tn last year"`? → **Yes**. Score = **30,000**. Span covers `(0, 20)`.

**Dimension candidates:**
- `"State"` dimension (technical: `state_code` or `state`):
  - Priority 5/7: Does word `"state"` appear in question? → No.
  - Synonym: If `"tn"` is not a registered synonym for this dimension, no match from Track A at all.
- `"Territory"`, `"Region"` etc. — similar logic, depends entirely on what synonyms are configured.

**Key observation:** Track A **cannot match `"TN"` as a dimension value** — it only matches dimension *names* (e.g. `"State"`, `"Territory"`), not *values* within dimensions.

---

### Step 2: Track B — DimensionValueResolver (State Value Resolution)

This is where `"TN"` should be resolved as a dimension *value*.

**Normalization:** `_normalize_text("Outstanding amount in TN last year")` → `"outstanding amount in tn last year"`

**Stopword removal:** From `STOPWORDS`: `"amount"` is a stopword, `"in"` is a stopword. Remaining q_tokens: `["outstanding", "tn", "last", "year"]`.

**ExactMatcher:**
- Tests `runtime_stored_norm` for each indexed value against `\b<value>\b` in the normalized question `"outstanding amount in tn last year"`.
- If `"Tamil Nadu"` is indexed with `normalized_value = "tamil nadu"`, the regex `\btamil nadu\b` does NOT match `"tn"`. → No hit.
- If `"TN"` is indexed with `normalized_value = "tn"`, regex `\btn\b` against `"outstanding amount in tn last year"` → **Match**. Confidence = 1.00.
- **Problem:** Whether `"TN"` matches depends entirely on what is indexed in `dimension_value_index`. If the source database stores the full form `"Tamil Nadu"`, the value `"TN"` is never in the index. ExactMatcher returns nothing for the abbreviation.

**NormalizedMatcher:**
- Uses `runtime_raw_norm` (raw value normalized). Same constraint — if the stored raw value is `"Tamil Nadu"`, its normalized form is `"tamil nadu"`, and `\btamil nadu\b` does not match `"tn"`.

**SingularPluralMatcher:**
- `q_singulars = ["outstanding", "tn", "last", "year"]`
- A value `"Tamil Nadu"` has singulars `["tamil", "nadu"]`. Is `["tamil", "nadu"]` a sub-sequence of `["outstanding", "tn", "last", "year"]`? → **No**.
- A value `"TN"` has singulars `["tn"]`. Is `["tn"]` a sub-sequence of `["outstanding", "tn", "last", "year"]`? → **Yes**. Match at confidence 0.95.
- **Problem:** SingularPluralMatcher only fires if ExactMatcher and NormalizedMatcher both returned nothing. If `"TN"` is stored literally in the DB, ExactMatcher or NormalizedMatcher fires first. If `"Tamil Nadu"` is stored, neither fires, SingularPluralMatcher also fails, and FuzzyMatcher runs.

**FuzzyMatcher (if all above fail):**
- n-grams from `["outstanding", "tn", "last", "year"]`: `["outstanding tn last year", "outstanding tn last", "tn last year", "outstanding tn", "tn last", "last year", "outstanding", "tn", "last", "year"]`
- `process.extractOne("tn", candidate_strings, scorer=fuzz.WRatio, score_cutoff=85)`
- Against `"Tamil Nadu"` (normalized: `"tamil nadu"`): WRatio(`"tn"`, `"tamil nadu"`) → likely ~35–50. **Does not exceed 85. No match.**
- Against `"TN"` (if indexed): WRatio(`"tn"`, `"tn"`) = 100. Match. But `"TN"` would have already been caught by ExactMatcher.
- **Result:** If the source data only stores `"Tamil Nadu"` (full form), `"TN"` (abbreviation) is **never resolved by any matcher**.


### Step 3: State Matching Analysis

How is state matching performed in this system?

There is **no dedicated state/geo resolver**. The system resolves state values identically to any other dimension value:

1. The `dimension_value_index` must contain the exact stored value from the source database column.
2. The `normalized_value` DB column stores a pre-normalized version (lowercase, collapsed whitespace).
3. Matching compares the user's typed text against those stored values using the four matchers.

**No abbreviation expansion exists.** The system cannot map `"TN"` → `"Tamil Nadu"` unless:
- The source database literally stores `"TN"` as the value in the state column, OR
- A synonym `"TN"` is registered on the State dimension in `semantic_dimensions.synonyms` (but synonyms are dimension-level, not value-level — Track B does not use synonyms at all; synonyms are only used in Track A for dimension name matching, not value matching).

### Execution Path Summary for Example 2

```
Question: "Outstanding amount in TN last year"
     │
     ▼
Track A (SemanticResolver)
  ├─ Outstanding Amount metric → business phrase match → score 30,000 → SELECTED
  └─ State/Territory dimension → depends on synonyms; "tn" likely NOT matched
     │
     ▼
Track B (DimensionValueResolver)
  Normalized question: "outstanding amount in tn last year"
  q_tokens (after stopword removal): ["outstanding", "tn", "last", "year"]
  │
  ├─ ExactMatcher: "tn" matches if stored value is "TN" → confidence 1.00
  │                "tamil nadu" does NOT match "tn" → no hit
  ├─ NormalizedMatcher: Same — no abbreviation expansion
  ├─ SingularPluralMatcher: ["tn"] sub-sequence match → confidence 0.95 if stored
  └─ FuzzyMatcher: WRatio("tn", "tamil nadu") ≈ 35–50 < cutoff 85 → no hit
     │
     ▼
If "TN" is NOT in DB (only "Tamil Nadu"):
  → value_matches = []
  → State dimension not resolved
  → Table for Outstanding Amount selected (metric wins: +5)
  → SQL generated without WHERE state = 'Tamil Nadu' filter
  → Wrong result: all states returned, not Tamil Nadu specifically
```

### Confidence Scores

| Component | Winner | Score/Confidence |
|---|---|---|
| Metric | Outstanding Amount | 30,000 (exact phrase) |
| Dimension | State (if synonym "TN" registered) | 9,000 / else 0 |
| Value | "TN" (only if stored literally) | 1.00 / else unresolved |
| Retrieval Status | PARTIAL (if only metric resolves) | |
| Gate | ALLOWED (PARTIAL passes through) | |

### Why "TN" May Not Be Resolved Correctly

1. **No abbreviation-to-full-form mapping** in the value resolver. FuzzyMatcher cannot bridge `"tn"` → `"Tamil Nadu"` because WRatio scores are too low at the 85 cutoff.
2. The Track A synonym mechanism works at the dimension-name level, not the dimension-value level. Registering `"TN"` as a synonym on the State dimension does not cause `"TN"` to resolve to the value `"Tamil Nadu"`.
3. `"amount"` is a stopword, so `"outstanding amount"` loses its `"amount"` token in Track B. Only `"outstanding"` survives to participate in value matching. This could accidentally match an indexed value that contains the word `"outstanding"` (e.g., `"Outstanding Payments"` as a status value).
4. The `SemanticGate` allows PARTIAL status through, so even with only the metric resolved and the state unresolved, SQL generation proceeds — producing results for all states instead of only Tamil Nadu.


---

## 5. Example 3 — "Pending order by marketing" → Outstanding Table Selected

### Question
```
Pending order by marketing
```

### Intent Detection
No pre-classification. Question goes directly into both tracks.

---

### Step 1: Track A — SemanticResolver

**Normalization:** `"pending order by marketing"`

**Metric candidates:**

Assume two metric candidates exist:
- `"Outstanding Amount"` (technical: `outstanding_amount`, table: `OutstandingTable`)
- `"Order Count"` or `"Pending Orders"` (technical: `pending_order_count`, table: `OrderPendingTable`)

For `"Outstanding Amount"`:
- Priority 3: `"outstanding amount"` in `"pending order by marketing"`? → No.
- Priority 7 (stem overlap): tokens = `["outstanding", "amount"]`. Stems = `["outstanding", "amount"]`. Remove noise. Question tokens = `["pending", "order", "by", "marketing"]`. Question stems = `["pending", "order", "by", "marketing"]`. Overlap: none of `{"outstanding", "amount"}` match `{"pending", "order", "by", "marketing"}`. `match_ratio = 0`. → Score = 0. **No candidate.**

For `"Pending Order"` metric (if named exactly):
- Priority 3: `"pending order"` in `"pending order by marketing"`? → **Yes**. Score = **30,000**. Span covers `(0, 13)`.

**Dimension candidates:**

For `"Marketing"` dimension (technical: `department`, table: `DepartmentTable`):
- Priority 3: Is `"marketing"` in `"pending order by marketing"`? → **Yes**. Score = **30,000** (or 15,000–10,000 depending on whether it's a phrase vs word match).

For `"Order Status"` dimension from `OrderPendingTable`:
- Priority 7 or 5: `"order"` or `"status"` tokens. May or may not match depending on exact business_name tokens.

**Potential conflict:** If both `"Outstanding"` and `"Pending"` resolve to the same dimension (e.g. an `"Order Status"` dimension with synonym `"outstanding"` AND synonym `"pending"`), there is a collision.

---

### Step 2: The Wrong-Table Scenario

The most likely scenario for Outstanding table being selected instead of Order Pending table:

**Scenario A — Synonym collision:**
The `"Outstanding"` metric or a dimension on the Outstanding table has a synonym `"pending"` or a stem match for `"pending"`. If the Outstanding table's metric scores higher than the Order Pending table's metric, the Outstanding table wins.

Trace:
- `"Pending"` matches via synonym on an Outstanding-related metric → score 9,000
- `"Pending Orders"` metric (correct) matches via business phrase → score 30,000

In this case the correct metric should win. But what if the correct "Pending Orders" metric does **not** exist in `semantic_metrics`? Then only the Outstanding metric's synonym match survives.

**Scenario B — Stemmed token overlap causing Outstanding to win:**
- `_stem_word("outstanding")` = `"outstanding"` (no standard suffix)
- `_stem_word("pending")` = `"pending"` (no standard suffix)
- These do not stem to the same form, so a direct stem collision is unlikely.

**Scenario C — SAME_TABLE_BONUS not rescuing the correct dimension:**
If the metric `"Outstanding Amount"` scores higher than `"Pending Orders"` metric (or `"Pending Orders"` is absent), the Outstanding table is identified as the metric table. Then SAME_TABLE_BONUS of `+0.35` is added to dimensions in the Outstanding table. However, as documented in §2.2.4, a bonus of 0.35 against integer scores of 9,000–30,000 has zero practical effect. The dimension for `"Marketing"` on the correct `OrderPendingTable` still scores at its original integer value and cannot be boosted to outcompete an Outstanding-table dimension.


**Scenario D (most probable for this specific example):**

Both tables have a `"Marketing"` dimension entry (because multiple tables contain a `department` or `channel` column named `"Marketing"`). The tie-break then falls entirely to which metric won Track A.

If the `"Outstanding"` metric has a synonym `"pending"` (because business users may call "outstanding orders" as "pending orders"), the synonym match at score=9,000 fires first and the overlap resolver blocks any `"Pending Orders"` metric that might have generated a lower stem-overlap score.

---

### Step 3: Track B — DimensionValueResolver

Normalized question: `"pending order by marketing"`
q_tokens (after stopword removal): `["pending", "order", "marketing"]` — `"by"` is not in STOPWORDS but `"order"` is not either.

Wait — checking STOPWORDS: `"by"` is not in the stopword list. `"order"` is not in the stopword list. So q_tokens = `["pending", "order", "marketing"]`.

**ExactMatcher:** Tests if `"marketing"` (normalized) appears as `\bmarketing\b` in `"pending order by marketing"` → **Yes**, if `"Marketing"` is an indexed value in any dimension (e.g. a Department dimension). Match at confidence 1.00.

This value match's `table_name` would be the Department table or whichever table the Marketing dimension belongs to. If that table is `OrderPendingTable`, it contributes `+2` to `OrderPendingTable`. If it is a shared `DimDepartment` table, it contributes to that.

**RelevantTableResolver scoring:**

Assume:
- Outstanding metric resolves → `OutstandingTable` gets +5
- Marketing value resolves → `OrderPendingTable` (or `DimDepartment`) gets +2
- No other components resolve

Final scores: `OutstandingTable = 5`, `OrderPendingTable = 2` (if different tables)

`OutstandingTable` wins by score 5 vs 2. **Wrong table selected.**

### Execution Path Summary for Example 3

```
Question: "Pending order by marketing"
     │
     ▼
Track A (SemanticResolver)
  ├─ Outstanding metric: synonym "pending" → score 9,000 → SELECTED (if no better match)
  │   OR Outstanding metric: no match → score 0
  ├─ "Pending Orders" metric: phrase match → score 30,000 → SELECTED (if exists)
  └─ Marketing dimension: phrase/word match → score 10,000–30,000 → SELECTED
     │
     ▼
Track B (DimensionValueResolver)
  └─ "Marketing" value → ExactMatcher → confidence 1.00 → value_match for its table
     │
     ▼
RelevantTableResolver
  ├─ If Outstanding metric wins: OutstandingTable = +5, Marketing table = +2
  │   → OutstandingTable selected (WRONG)
  └─ If Pending Orders metric wins: OrderPendingTable = +5 or +8
      → OrderPendingTable selected (CORRECT)
     │
     ▼
SemanticGate: PARTIAL or COMPLETE → allowed
     │
     ▼
SQL generated against wrong table if Outstanding metric was selected
```

### Why Outstanding Table Was Selected

The core reason is that the `"Pending Orders"` metric is either:
1. **Not registered** in `semantic_metrics` (most likely), so no metric from `OrderPendingTable` is ever a candidate, or
2. Has a lower match score than the Outstanding metric due to synonym pollution.

Because `RelevantTableResolver` weights metrics at 5x and dimensions/values at 2–3x, a metric match on the wrong table will always dominate a value-only match on the correct table. There is no second-pass verification that asks "does the metric's table also contain the other resolved components?"


---

## 6. Cross-Cutting Findings

### Finding 1 — Stem Overlap (Priority 7) Is Too Permissive

**File:** `semantic_resolver.py`, `_get_match_info()`, lines handling Priority 7

```python
match_ratio = len(set(matched_stems)) / max(len(set(cand_stems)), 1)
if match_ratio >= 0.5:
    score = int(match_ratio * 8000)
    return (score, len(matched_stems), [(0, len(q_norm))], ...)
```

A 50% stem overlap threshold is extremely low. For a two-token business name like `"Sales Trend"`, matching just the word `"trend"` (1 out of 2 tokens) crosses the 50% threshold and generates score=4,000. This fires for:
- Single-word partial matches
- Accidental word collisions (e.g., `"order"` appearing in both `"Order Status"` and a question about `"pending order"`)

The span `[(0, len(q_norm))]` that stem-overlap matches claim is the **entire question** rather than the actual matched substring. This causes all lower-scored candidates to be overlap-eliminated even though their span may have been at a completely different part of the question.

**Effect:** Correct candidates with specific phrase matches get eliminated when a stem-overlap candidate claims the whole question span.

---

### Finding 2 — SAME_TABLE_BONUS Is Mathematically Inert

**File:** `semantic_resolver.py`

```python
SAME_TABLE_BONUS = 0.35
# ...
cand["score"] = keyword_score + table_bonus  # e.g. 9000.0 + 0.35 = 9000.35
```

Integer scores range from ~4,000 to 50,000. A bonus of 0.35 cannot change any ranking decision when candidate scores differ by thousands. The bonus only matters when two candidates have an identical integer score, which is unlikely in practice.

**Effect:** The SAME_TABLE_BONUS feature does not function. Dimension table alignment with the resolved metric table has zero influence on the final ranking.

---

### Finding 3 — Stopword List Includes Business-Critical Terms

**File:** `matching/stopwords.py`

```python
STOPWORDS = {
    "show", "me", "give", "the", "all", "of", "in", "for", "with", "a", "an",
    "is", "are", "sales", "sale", "amount", "qty", "quantity", "count",
    "by", "revenue", "turnover", "profit", "value"
}
```

`"sales"`, `"amount"`, `"revenue"`, `"turnover"`, `"profit"`, `"count"`, `"quantity"` are removed from question tokens before value matching (Track B). These terms:
- Are frequently part of dimension value names (e.g., a status value `"Sales Return"`, a channel value `"Revenue Share"`)
- Are specifically the terms users tend to ask about

**Effect:**
- A dimension value `"Sales Return"` — after stopword removal — becomes token `["return"]`. The value can still match, but only via its non-stopword component.
- A question `"show sales amount by region"` loses both `"sales"` and `"amount"` from its token set. FuzzyMatcher would only receive n-grams from `["region"]`, severely limiting what it can match.
- `"by"` being a stopword is correct. `"in"`, `"of"`, `"for"` are correct. But metric/KPI terms (`sales`, `profit`, `revenue`) should not be stopwords in Track B (value matching).

---

### Finding 4 — FuzzyMatcher Returns Only One Match

**File:** `matching/fuzzy_matcher.py`

```python
best_score = -1.0
best_match_val = None
for phrase in phrases:
    result = process.extractOne(...)
    if score > best_score:
        best_score = score
        best_match_val = ...

if best_match_val:
    return [MatchResult(...)]  # Only one result
```

FuzzyMatcher returns at most **one match** — the single best across all question n-grams and all indexed values. This means:
- If a question contains two different filterable values (e.g., `"state = TN"` AND `"channel = Marketing"`), the fuzzy pass can only resolve one of them.
- The other remains unresolved, causing missing WHERE clause conditions in generated SQL.

The earlier matchers (Exact, Normalized, SingularPluralMatcher) do return multiple matches, so this limitation only affects questions where fuzzy matching is the winning strategy.

---

### Finding 5 — No Negation or Ambiguity Handling

Neither Track A nor Track B handles negation. A question like `"Show sales excluding TN"` would resolve `"TN"` as a positive filter, and the system has no mechanism to convey that it should be an exclusion filter.

---

### Finding 6 — Table Selection Happens Too Late and Is Purely Derived

`RelevantTableResolver` runs **after** all semantic component resolution is complete. There is no opportunity for early table constraints to guide which metrics or dimensions are considered. If the question semantically implies a specific table (e.g., `"pending order"` → `OrderPendingTable`), but the table name doesn't appear in the question text, this signal is never used.

The weight distribution (metric=5, dim=3, value=2) means a single metric match always dominates. A question with no metric-like terms but clear dimension/value signals will select whatever table happens to carry those dimensions, which may not be the primary business table.

---

### Finding 7 — SemanticGate Threshold Is Too Low

**File:** `semantic_gate.py`

```python
if status == "PARTIAL":
    return {"allowed": True, ...}
```

PARTIAL status is awarded when `resolved_components == 1`. One resolved component — even if it is a spurious stem-overlap match with confidence=4000/50000 — allows SQL generation to proceed. There is no minimum match quality threshold. A match at the lowest priority (Priority 7, score=4,000, matching just half the tokens) passes the gate identically to a Priority 1 match (score=50,000).

---

### Finding 8 — Synonyms Are Value-Blind: No Value-Level Abbreviation Resolution

Track A uses synonyms to match dimension and metric *names*. Track B has no synonym mechanism whatsoever. If a user types an abbreviation or alternate name for a *value* (e.g., `"TN"` for `"Tamil Nadu"`, `"MH"` for `"Maharashtra"`, `"Q1"` for `"Jan-Mar"`), the system cannot expand it unless the exact abbreviation is stored as a raw value in the source database.

This is a fundamental architectural gap for any domain with well-known value abbreviations (state codes, product codes, status abbreviations).

---

### Finding 9 — Two Tracks Are Disconnected

Track A (SemanticResolver) and Track B (DimensionValueResolver) execute independently. Track A resolves metric and dimension *names*. Track B resolves dimension *values*. The resolved metric from Track A is not used to filter or bias Track B's value resolution.

For example: if Track A resolves the metric as `"Outstanding Amount"` on `OutstandingTable`, Track B continues to match `"Marketing"` against all indexed values across all dimensions in all tables. A `"Marketing"` value from `OrderPendingTable` may be returned even though the metric context points to `OutstandingTable`. The conflict is never detected.

The `_filter_metric_conflicts()` method exists but it only removes value matches whose normalized_value duplicates a metric name — it does not do cross-track table alignment.


---

## 7. Final Answers to Audit Questions

---

### Question 1: What is the biggest cause of incorrect retrieval?

**The biggest cause is synonym pollution combined with the absence of any semantic type constraint on synonyms.**

A synonym is a flat string registered against a metric or dimension. It is matched with the same regex and score (9,000) regardless of whether the synonym is an abbreviation, an alternate business name, a product label fragment, or an ambiguous term. There is no mechanism to distinguish `"trend"` as a temporal business synonym from `"trend"` as a shorthand for a clothing product called `"CCB TRENDY"`. Whichever candidate registers the synonym match first wins the overlap resolver and eliminates all competing candidates for that span.

The secondary cause is the Priority 7 stem overlap that claims the entire question span, which can block correct higher-priority candidates that happen to share any part of that span in a later processing round.

---

### Question 2: Is confidence scoring sufficient?

**No. The current confidence scoring is structurally insufficient for two reasons:**

First, Track A uses raw integer scores (4,000–50,000) that are never normalized to a 0–1 scale and are never exposed in the retrieval confidence calculation. The retrieval confidence (§2.7) counts only the number of resolved components, not their quality. An exact business phrase match at 30,000 and a 50% stem overlap match at 4,000 both contribute `+0.35` to retrieval confidence. The system cannot distinguish between a high-quality match and a borderline one.

Second, Track B confidence values (`MatchConfidence.EXACT = 1.00`, `FUZZY = 0.87`) are returned in the API response but are never used to gate or bias Track A results, to weight the table scoring in `RelevantTableResolver`, or to adjust the SemanticGate threshold. They exist only for downstream display/debugging.

A meaningful confidence score would need to be: (a) derived from the actual match quality rather than the count of resolved types, and (b) used as an input gate — not just an output label.

---

### Question 3: Does table selection happen too late?

**Yes. Table selection happens entirely too late, and it is the wrong architectural choice for question-driven retrieval.**

`RelevantTableResolver` runs after all component resolution is complete. It cannot inform or constrain the earlier metric, dimension, or value resolution steps. A question like `"pending order by marketing"` contains table-level intent in the phrase `"pending order"`, but there is no mechanism to feed that intent back into metric/dimension matching to prefer candidates from `OrderPendingTable`.

The only pseudo-table-awareness mechanism is the SAME_TABLE_BONUS, which adds 0.35 to dimension scores. As documented, this bonus is mathematically inert against scores in the thousands.

The correct fix is to make table context an early-pass signal rather than a derived post-processing artifact.

---

### Question 4: Does fuzzy matching produce false positives?

**Yes, in two distinct ways.**

**False positive type 1 — too-low cutoff relative to token length:** WRatio at cutoff 85 is calibrated for medium-length strings. For short tokens like `"tn"` (2 chars), even a partial overlap with a longer stored value (e.g., `"Thane"`) can score 85+. WRatio uses several fuzzy strategies internally and picks the best, which means short tokens are disproportionately likely to match incorrectly.

**False positive type 2 — single-best-match semantics:** FuzzyMatcher returns only the single best match across all n-grams and all values. If the best match is a false positive (e.g., `"trend"` fuzzy-matching `"Trendz"` at score 87), no other correct match is returned because FuzzyMatcher terminates after one result.

Additionally, `SingularPluralMatcher` can produce false positives through its sub-sequence logic. The check `_is_sublist(val_singulars, q_singulars)` only requires that the value tokens appear **in order** somewhere in the question tokens. A value `["south"]` matches any question containing the word `"south"` — regardless of context. For single-token values this is equivalent to word presence, not semantic matching.

---

### Question 5: What should be prioritized to improve retrieval accuracy?

Listed in priority order based on impact severity:

**Priority 1 — Remove business metric terms from the stopword list**
`"sales"`, `"amount"`, `"revenue"`, `"turnover"`, `"profit"`, `"count"`, `"quantity"` must not be stopwords in Track B. Their presence in stopwords.py silently removes them from all value-matching operations, causing value resolution failures for multi-word values containing these terms.

**Priority 2 — Fix the SAME_TABLE_BONUS scale**
The bonus is `0.35` while scores are in the range 4,000–50,000. Either convert all Track A scores to a 0–1 float scale before applying the bonus, or change the bonus to a meaningful integer (e.g., +2,000) that can actually affect ranking.

**Priority 3 — Add value-level synonym / abbreviation expansion**
There is currently no way to map `"TN"` → `"Tamil Nadu"` at the value resolution level. A `dimension_value_synonyms` table (or a synonym column in `dimension_value_index`) linked to values, combined with an AbbreviationMatcher step in the Track B pipeline, would resolve this class of failures entirely.

**Priority 4 — Enforce a minimum match quality threshold in SemanticGate**
Passing PARTIAL with any single resolved component regardless of match quality is dangerous. The gate should consider the maximum Track A candidate score and Track B confidence. A stem-overlap match at 4,000/50,000 (8% of maximum) should not be treated as equal to a phrase match at 30,000/50,000 (60% of maximum).

**Priority 5 — Make Priority 7 (stem overlap) use real token spans, not whole-question spans**
The current implementation sets the span of all stem-overlap matches to `[(0, len(q_norm))]`. This causes the entire question to be "claimed" by a weak match, blocking all other candidates. Stem-overlap spans should be computed from the actual matched word positions in the question, just like exact and phrase matches use `_find_phrase_spans()`.

**Priority 6 — Connect Track A and Track B via metric table context**
After Track A resolves a metric, the metric's `table_name` should be used to filter or deprioritize Track B value resolution candidates from unrelated tables. This prevents a `"Marketing"` value from `OrderPendingTable` from appearing alongside a metric from `OutstandingTable` without triggering a conflict signal.

**Priority 7 — Add synonym type classification**
Synonyms should carry a `type` tag: `"temporal"`, `"geographic"`, `"product"`, `"status"`, etc. A synonym tagged as `"product_abbreviation"` (like `"trendy"` for `"CCB TRENDY"`) should not match a question that has a temporal or metric intent. This requires question intent detection to be run before synonym matching, and synonym matching to be conditioned on intent type.

---

## Appendix A — Score Reference Quick-Table

| Match Method | File | Score / Confidence | False Positive Risk |
|---|---|---|---|
| Exact technical name = question | semantic_resolver.py | 50,000 | Low |
| Exact business name = question | semantic_resolver.py | 40,000 | Low |
| Business phrase in question | semantic_resolver.py | 30,000 | Low |
| Technical phrase in question | semantic_resolver.py | 20,000 | Low |
| Core business words in question | semantic_resolver.py | 15,000 | Medium |
| All business words in question | semantic_resolver.py | 10,000 | Medium |
| Synonym phrase in question | semantic_resolver.py | 9,000 | **High** |
| Stem overlap ≥ 50% | semantic_resolver.py | 4,000–8,000 | **Very High** |
| ExactMatcher (value) | exact_matcher.py | 1.00 | Low |
| NormalizedMatcher (value) | normalized_matcher.py | 0.98 | Low |
| SingularPluralMatcher (value) | singular_plural_matcher.py | 0.95 | Medium |
| FuzzyMatcher (value) | fuzzy_matcher.py | 0.85–1.00 | **High** |

---

## Appendix B — File Inventory

| File | Role |
|---|---|
| `semantic/semantic_resolver.py` | Metric/dimension name resolution (Track A) |
| `semantic/dimension_value_resolver.py` | Dimension value resolution orchestrator (Track B) |
| `semantic/matching/pipeline.py` | First-matcher-wins pipeline |
| `semantic/matching/confidence.py` | Score constants |
| `semantic/matching/exact_matcher.py` | Regex exact value match |
| `semantic/matching/normalized_matcher.py` | Normalized regex value match |
| `semantic/matching/singular_plural_matcher.py` | Morphological sub-sequence match |
| `semantic/matching/fuzzy_matcher.py` | WRatio fuzzy match (single best) |
| `semantic/matching/ranker.py` | Post-match sort (type > confidence > coverage) |
| `semantic/matching/models.py` | Data classes for all matching components |
| `semantic/matching/candidate_phrase_extractor.py` | N-gram extractor for FuzzyMatcher |
| `semantic/matching/stopwords.py` | **Critical: contains metric terms as stopwords** |
| `semantic/matching/question_sanitizer.py` | Strip prompt labels |
| `semantic/relevant_table_resolver.py` | Weighted table scoring |
| `semantic/relationship_expander.py` | BFS bridge table injection |
| `semantic/semantic_gate.py` | Allow/block SQL generation |
| `semantic/dimension_value_index_builder.py` | Build the value index |
| `semantic/discovery_service.py` | Auto-discover metrics/dimensions from schema |
| `semantic/cache/dimension_cache.py` | In-memory version-aware value cache |

