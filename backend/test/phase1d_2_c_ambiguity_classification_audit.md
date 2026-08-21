# Phase 1D.2.C — Real-Data Ambiguity Classification Audit

This document presents the diagnostic audit of the `AmbiguityClassifier` using both real-world semantic index matching results and synthetic test cases.

---

## 1. Real-Data Diagnostic Results

### Query 1: "pant"
- **Raw MatchResult Candidates**:
  - `B--PANT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['pant']`)
  - `LS PANT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['pant']`)
  - `DHOTI PANT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['pant']`)
  - `LINEN PANT` (Brand, SINGULAR_PLURAL, Conf: 0.95, Span: `['pant']`)
  - `RAMRAJ PANT` (Brand, SINGULAR_PLURAL, Conf: 0.95, Span: `['pant']`)
- **Classifier Input Order**: Ordered by `MatchRanker.rank` (exact same priority/confidence/token lengths).
- **Classifier Output**:
  - **Status**: `STRONG_AMBIGUITY`
  - **Dominant Match**: `None`
- **Explanation**: All candidates share equal match priority (`SINGULAR_PLURAL`), equal confidence (`0.95`), and equal token span length. Under Rule 3, since the confidence gap is `0.00 < 0.05`, they are correctly classified as strongly ambiguous.
- **Desirable**: **Yes**. These are true value-level and dimension-level alternative candidates.

### Query 2: "shirt"
- **Raw MatchResult Candidates**:
  - `C--SHIRT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['shirt']`)
  - `ADD SHIRT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['shirt']`)
  - `ETHER SHIRT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['shirt']`)
  - `RAMRAJ SHIRT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['shirt']`)
- **Classifier Input Order**: Ordered by `MatchRanker.rank`.
- **Classifier Output**:
  - **Status**: `STRONG_AMBIGUITY`
  - **Dominant Match**: `None`
- **Explanation**: Similar to `"pant"`, all candidates share equal priority, confidence, and span length, falling under Rule 3 with `conf_gap = 0.00`, remaining ambiguous.
- **Desirable**: **Yes**. True value-level alternatives.

### Query 3: "cotton pant"
- **Raw MatchResult Candidates**:
  - `LS ZARI COTTON` (SINGULAR_PLURAL, Conf: 0.95, Span: `['cotton', 'pant']`)
  - `MENS PYJAMA PANT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['cotton', 'pant']`)
  - `LS PANT` (FUZZY, Conf: 0.85, Span: `['cotton', 'pant']`)
- **Classifier Input Order**: Sorted by priority/confidence.
- **Classifier Output**:
  - **Status**: `STRONG_AMBIGUITY`
  - **Dominant Match**: `None`
- **Explanation**: The top candidates all match via the asymmetric fallback of `SingularPluralMatcher` and are assigned full `0.95` confidence and `SINGULAR_PLURAL` type. Because they all report identical properties (including the full query span), they are evaluated under Rule 3 as a strong same-type ambiguity.
- **Desirable**: **No (Suspicious)**. 
  - `LS ZARI COTTON` only matches `"cotton"` (not pants), whereas `MENS PYJAMA PANT` matches `"pant"` (pants, not cotton). They represent disjoint partial matches, but because the matcher assigns them equal confidence and identical span properties, the classifier is forced to treat them as equally valid, highly ambiguous candidates.

### Query 4: "formal shirt"
- **Raw MatchResult Candidates**:
  - `LS CREAM SHIRT` (SINGULAR_PLURAL, Conf: 0.95, Span: `['formal', 'shirt']`)
  - `FORMAL SOCKS DESIGN FULL` (SINGULAR_PLURAL, Conf: 0.95, Span: `['formal', 'shirt']`)
- **Classifier Input Order**: Sorted by priority/confidence.
- **Classifier Output**:
  - **Status**: `STRONG_AMBIGUITY`
  - **Dominant Match**: `None`
- **Explanation**: Both the shirt candidate and the socks candidate share the same confidence and priority. Because they both report `matched_question_tokens = ['formal', 'shirt']` (the entire question), they fall under Rule 3 with a gap of `0.00` and are classified as strongly ambiguous.
- **Desirable**: **No (Suspicious)**.
  - The shirt candidate matches `"shirt"`, while the socks candidate matches `"formal"`. They correspond to disjoint query spans. However, the classifier is unable to distinguish this because `SingularPluralMatcher` unconditionally sets `matched_question_tokens` to the entire query token list rather than the actual intersecting tokens that caused the match.

### Query 5: "banian"
- **Raw MatchResult Candidates**:
  - `BANIANS` (SINGULAR_PLURAL, Conf: 0.95, Span: `['banian']`)
  - `1 BANIAN` (SINGULAR_PLURAL, Conf: 0.95, Span: `['banian']`)
  - `ADVERTISEMENT BANIAN` (SINGULAR_PLURAL, Conf: 0.95, Span: `['banian']`)
- **Classifier Input Order**: Sorted by rank.
- **Classifier Output**:
  - **Status**: `STRONG_AMBIGUITY`
  - **Dominant Match**: `None`
- **Explanation**: Evaluated under Rule 3 with identical characteristics, leading to strong ambiguity.
- **Desirable**: **Yes**. True value/dimension alternative matches.

### Query 6: "children wear"
- **Raw MatchResult Candidates**:
  - `N--NIGHT WEARS` (SINGULAR_PLURAL, Conf: 0.95, Span: `['children', 'wear']`)
- **Classifier Output**:
  - **Status**: `SINGLE_MATCH`
  - **Dominant Match**: `N--NIGHT WEARS`
- **Explanation**: Exactly one candidate survives the containment filters, leading directly to a `SINGLE_MATCH` classification.
- **Desirable**: **Yes**.

---

## 2. Synthetic Classifier-Only Cases

### Case A: EXACT 1.00 vs FUZZY 0.85
- **Input**: EXACT (1.00) and FUZZY (0.85).
- **Classifier Output**: `status: WEAK_AMBIGUITY`, `dominant_match: Exact Val`.
- **Rule Applied**: Rule 1 (Priority gap >= 2). Since `1.00 >= 0.85 - 0.10`, the exact match is declared dominant.
- **Desirable**: **Yes**. Exact matches must dominate fuzzy matches when confidence is high.

### Case B: SINGULAR_PLURAL 0.95 vs SINGULAR_PLURAL 0.95
- **Input**: SINGULAR_PLURAL (0.95) and SINGULAR_PLURAL (0.95).
- **Classifier Output**: `status: STRONG_AMBIGUITY`, `dominant_match: None`.
- **Rule Applied**: Rule 3 (Same priority, equal confidence).
- **Desirable**: **Yes**. Matches with equal confidence and priority must remain ambiguous.

### Case C: FUZZY 0.90 vs FUZZY 0.86
- **Input**: FUZZY (0.90) and FUZZY (0.86) with same span length.
- **Classifier Output**: `status: STRONG_AMBIGUITY`, `dominant_match: None`.
- **Rule Applied**: Rule 3 (Same priority, same span length). Since `conf_gap = 0.04 < 0.05`, it remains ambiguous.
- **Desirable**: **Yes**. Close fuzzy matches should be clarified.

### Case D: EXACT 1.00 vs EXACT 1.00
- **Input**: EXACT (1.00) and EXACT (1.00).
- **Classifier Output**: `status: STRONG_AMBIGUITY`, `dominant_match: None`.
- **Rule Applied**: Rule 3 (Same priority, equal confidence).
- **Desirable**: **Yes**.

### Case E: Candidate matching 2 query tokens at 0.90 vs Candidate matching 1 query token at 0.95 (both FUZZY)
- **Input**: Candidate 1 (2 tokens, Conf: 0.90, FUZZY) vs Candidate 2 (1 token, Conf: 0.95, FUZZY).
- **Classifier Output**: `status: STRONG_AMBIGUITY`, `dominant_match: None`.
- **Rule Applied**: Rule 3 (`p1 == p2`, `len1 > len2`). `c1` is dominant if `conf_gap >= -0.02`. Since `conf_gap = -0.05 < -0.02`, it fails to dominate and remains ambiguous.
- **Desirable**: **No (Undesirable)**.
  - A candidate matching 2 out of 2 query tokens (full coverage) represents a significantly stronger semantic match than a candidate matching only 1 out of 2 query tokens, even if the 1-token candidate has a slightly higher fuzzy score. The token coverage advantage should dominate larger confidence differences (e.g. up to `-0.08` or `-0.10`).

---

## 3. Findings & Diagnosed Issues

We have identified two critical structural issues preventing correct ambiguity classification:

1. **Sub-span Matcher Information Pollution**:
   `SingularPluralMatcher.match` unconditionally assigns `matched_question_tokens = q_tokens` (the entire query token list) to all generated matches, even when a candidate matched only a single sub-token during fallback (e.g. matching `"shirt"` in `"formal shirt"`). This tricks the classifier into seeing identical span lengths and prevents the identification of disjoint sub-spans.
2. **Insufficient Token Coverage Weighting**:
   In Rule 3 (same priority), when `len1 > len2` (more matched tokens), the current threshold for dominance requires `conf_gap >= -0.02`. This is too narrow. A 2-token coverage match should be allowed to dominate a 1-token coverage match even if the 1-token match has up to 0.08 or 0.10 higher confidence.

---

## 4. Verdict

**FAIL**

### Reasons for FAIL:
- **Rule 2 & 3 Modification Required**: The classifier's span length dominance rule (Rule 2 and Rule 3 with `len1 > len2`) is too conservative, failing to let candidates with higher query token coverage dominate candidates with lower coverage (e.g., Case E).
- **Matcher Output Corruption**: `SingularPluralMatcher` outputs incorrect `matched_question_tokens` (over-reporting them as the entire question), which blinds the classifier to token-level evidence differences in queries like `"formal shirt"`. Since production matcher code cannot be edited in this phase, the classifier must perform its own token-level intersection on the fly to count true matched tokens.
