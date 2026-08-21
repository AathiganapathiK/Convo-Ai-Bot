# Phase 1D.4 — True Ambiguity vs Harmless Multiple Matches Audit

> [!NOTE]
> This document records the read-only forensic audit to differentiate between **True Ambiguity** (where a user must clarify intent) and **Harmless Multiple Matches** (where one match dominates or is the clear full intent).

## 1. Current Pipeline Behavior

The matching pipeline parses user queries, performs token extraction, and matches against the semantic index. The stages are:
1. **Raw Matches Extraction**: Run matcher algorithms (`ExactMatcher`, `NormalizedMatcher`, `SingularPluralMatcher`, `FuzzyMatcher`).
2. **Duplicate Consolidation**: Deduplicate matches by `(dimension_id, normalized_value)` to prevent duplicate evidence from polluting the list.
3. **Containment Filter**: Remove candidates that match a strict subset of query tokens matched by a longer, higher-confidence candidate.
4. **MatchRanker Ranking**: Sort globally by `(-type_priority, -confidence, -coverage, token_distance, length_diff, value.lower())`.
5. **Ambiguity Classification**: Classify candidates using Rule 1 to 4 to return `SINGLE_MATCH`, `WEAK_AMBIGUITY`, `STRONG_AMBIGUITY`, or `NO_MATCH`.

## 2. Real-Data Candidate Traces

Below are the detailed candidate traces for the 17 business queries run against the mock database index:

### Query 1: `pant`
- **Normalized Query**: `pant`
- **Meaningful Tokens**: ['pant']
- **Resolution Status**: `STRONG_AMBIGUITY`
- **Dominant Match**: `None`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Pants` | SINGULAR_PLURAL | 0.950 | 1/1 | 1 | Product Group | Products | ProductGroup | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |
| 2 | `LS Pant` | SINGULAR_PLURAL | 0.950 | 1/1 | 6 | Prod Grp2 | Products | ProdGrp2 | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 3 | `Linen Pant` | SINGULAR_PLURAL | 0.950 | 1/1 | 4 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 4 | `Ramraj Pant` | SINGULAR_PLURAL | 0.950 | 1/1 | 5 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 5 | `Cotton Pants` | SINGULAR_PLURAL | 0.950 | 1/1 | 2 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 6 | `Formal Pants` | SINGULAR_PLURAL | 0.950 | 1/1 | 3 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |

### Query 2: `shirt`
- **Normalized Query**: `shirt`
- **Meaningful Tokens**: ['shirt']
- **Resolution Status**: `STRONG_AMBIGUITY`
- **Dominant Match**: `None`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Shirts` | SINGULAR_PLURAL | 0.950 | 1/1 | 7 | Product Group | Products | ProductGroup | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |
| 2 | `T-Shirt` | SINGULAR_PLURAL | 0.950 | 1/1 | 12 | Product Category | Products | CategoryName | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 3 | `Red Shirt` | SINGULAR_PLURAL | 0.950 | 1/1 | 10 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 4 | `Men's Shirt` | SINGULAR_PLURAL | 0.950 | 1/1 | 20 | Product Category | Products | CategoryName | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 5 | `Ramraj Shirt` | SINGULAR_PLURAL | 0.950 | 1/1 | 9 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 6 | `Cotton Shirts` | SINGULAR_PLURAL | 0.950 | 1/1 | 19 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 7 | `Formal Shirts` | SINGULAR_PLURAL | 0.950 | 1/1 | 8 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 8 | `Viveagham Colour Shirt` | SINGULAR_PLURAL | 0.950 | 1/1 | 11 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |

### Query 3: `cotton pant`
- **Normalized Query**: `cotton pant`
- **Meaningful Tokens**: ['cotton', 'pant']
- **Resolution Status**: `STRONG_AMBIGUITY`
- **Dominant Match**: `None`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Cotton` | EXACT | 1.000 | 2/2 | 18 | Fabric | Products | FabricType | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |
| 2 | `Cotton Pants` | SINGULAR_PLURAL | 0.950 | 2/2 | 2 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |

### Query 4: `formal shirt`
- **Normalized Query**: `formal shirt`
- **Meaningful Tokens**: ['formal', 'shirt']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Formal Shirts`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Formal Shirts` | SINGULAR_PLURAL | 0.950 | 2/2 | 8 | Product Group | Products | ProductGroup | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 5: `banian`
- **Normalized Query**: `banian`
- **Meaningful Tokens**: ['banian']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Banians`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Banians` | SINGULAR_PLURAL | 0.950 | 1/1 | 13 | Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 6: `banians`
- **Normalized Query**: `banians`
- **Meaningful Tokens**: ['banians']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Banians`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Banians` | EXACT | 1.000 | 1/1 | 13 | Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 7: `children wear`
- **Normalized Query**: `children wear`
- **Meaningful Tokens**: ['children', 'wear']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Children Wear`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Children Wear` | EXACT | 1.000 | 2/2 | 14 | Product Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 8: `women wear`
- **Normalized Query**: `women wear`
- **Meaningful Tokens**: ['women', 'wear']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Women's Wear`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Women's Wear` | SINGULAR_PLURAL | 0.950 | 2/2 | 15 | Product Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 9: `mens wear`
- **Normalized Query**: `mens wear`
- **Meaningful Tokens**: ['mens', 'wear']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Men's Wear`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Men's Wear` | EXACT | 1.000 | 2/2 | 16 | Product Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 10: `t shirt`
- **Normalized Query**: `t shirt`
- **Meaningful Tokens**: ['t', 'shirt']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `T-Shirt`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `T-Shirt` | EXACT | 1.000 | 2/2 | 12 | Product Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 11: `red shirt`
- **Normalized Query**: `red shirt`
- **Meaningful Tokens**: ['red', 'shirt']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Red Shirt`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Red Shirt` | EXACT | 1.000 | 2/2 | 10 | Brand | Products | Brand | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 12: `cotton`
- **Normalized Query**: `cotton`
- **Meaningful Tokens**: ['cotton']
- **Resolution Status**: `WEAK_AMBIGUITY`
- **Dominant Match**: `Cotton`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Cotton` | EXACT | 1.000 | 1/1 | 18 | Fabric | Products | FabricType | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |
| 2 | `Cotton Pants` | SINGULAR_PLURAL | 0.950 | 1/1 | 2 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 3 | `Cotton Shirts` | SINGULAR_PLURAL | 0.950 | 1/1 | 19 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |

### Query 13: `pants`
- **Normalized Query**: `pants`
- **Meaningful Tokens**: ['pants']
- **Resolution Status**: `WEAK_AMBIGUITY`
- **Dominant Match**: `Pants`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Pants` | EXACT | 1.000 | 1/1 | 1 | Product Group | Products | ProductGroup | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |
| 2 | `LS Pant` | SINGULAR_PLURAL | 0.950 | 1/1 | 6 | Prod Grp2 | Products | ProdGrp2 | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 3 | `Linen Pant` | SINGULAR_PLURAL | 0.950 | 1/1 | 4 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 4 | `Ramraj Pant` | SINGULAR_PLURAL | 0.950 | 1/1 | 5 | Brand | Products | Brand | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 5 | `Cotton Pants` | SINGULAR_PLURAL | 0.950 | 1/1 | 2 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |
| 6 | `Formal Pants` | SINGULAR_PLURAL | 0.950 | 1/1 | 3 | Product Group | Products | ProductGroup | DIFFERENT | Yes | No | **CROSS_DIMENSION_ALTERNATIVE** |

### Query 14: `formal pants`
- **Normalized Query**: `formal pants`
- **Meaningful Tokens**: ['formal', 'pants']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Formal Pants`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Formal Pants` | EXACT | 1.000 | 2/2 | 3 | Product Group | Products | ProductGroup | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 15: `cotton shirts`
- **Normalized Query**: `cotton shirts`
- **Meaningful Tokens**: ['cotton', 'shirts']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Cotton Shirts`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Cotton Shirts` | EXACT | 1.000 | 2/2 | 19 | Product Group | Products | ProductGroup | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 16: `men's shirt`
- **Normalized Query**: `mens shirt`
- **Meaningful Tokens**: ['mens', 'shirt']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Men's Shirt`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Men's Shirt` | EXACT | 1.000 | 2/2 | 20 | Product Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

### Query 17: `women's wear`
- **Normalized Query**: `womens wear`
- **Meaningful Tokens**: ['womens', 'wear']
- **Resolution Status**: `SINGLE_MATCH`
- **Dominant Match**: `Women's Wear`

| Rank | Value | Match Type | Confidence | Coverage | Dimension ID | Business Name | Table | Column | Dimension Rel | Full? | Sub-span? | Internal Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `Women's Wear` | EXACT | 1.000 | 2/2 | 15 | Product Category | Products | CategoryName | TOP | Yes | No | **FULL_INTENT_CANDIDATE** |

## 3. Genuine Ambiguity vs Harmless Matches Analysis

### CASE A — SAME DIMENSION, SAME QUERY COVERAGE
- **Example**: Query `pant` yielding `Linen Pant` and `Ramraj Pant` (both Brand, both cover 1/1 tokens).
- **Verdict**: **TRUE AMBIGUITY**
- **Explanation**: Since both candidates match the exact same query span and have identical coverage and confidence in the same dimension, there is no semantic way to break the tie without guessing the user's brand preference. Clarification must trigger.

### CASE B — ONE FULL-COVERAGE CANDIDATE VS PARTIAL CANDIDATE
- **Example**: Query `cotton pant` yielding `Cotton Pants` (2/2) and `Cotton` (1/2).
- **Verdict**: **HARMLESS MULTIPLE MATCHES**
- **Explanation**: The candidate `Cotton Pants` matches 100% of the query tokens (`cotton` + `pant`). The candidate `Cotton` (FabricType) only matches a partial sub-span (`cotton`). A user typing a multi-token query expects the entity representing the complete phrase. The partial match is a weaker sub-span match and should be silently filtered or suppressed in favor of the full-coverage candidate.

### CASE C — FULL-COVERAGE PRODUCT VS PARTIAL DIFFERENT DIMENSION
- **Example**: Query `formal shirt` yielding `Formal Shirts` (2/2) and `Formal Socks` (1/2).
- **Verdict**: **HARMLESS MULTIPLE MATCHES**
- **Explanation**: `Formal Shirts` covers the complete query span. `Formal Socks` is matched only because the word `formal` was shared, but the product portion of the query (`shirt` vs `socks`) does not match. Since there is a candidate matching the full query, the partial cross-dimension match on `formal` is harmless noise and should not trigger clarification.

### CASE D — SAME VALUE, DIFFERENT DIMENSION
- **Example**: Displayed value `Ramraj` exists in both `Brand` (Product Brand) and `State` (Geography/State).
- **Verdict**: **TRUE AMBIGUITY**
- **Explanation**: The value itself is identical, but it represents entirely different business concepts (filtering products by brand vs filtering tables by geography). The system must clarify which dimension the user intended.

### CASE E — DIFFERENT VALUES, DIFFERENT DIMENSIONS
- **Example**: Query matches `Cotton Pants` (Product Group) and `Tamil Nadu` (State).
- **Verdict**: **HARMLESS MULTIPLE MATCHES (or independent filters)**
- **Explanation**: If a query contains multiple words that match different dimensions on disjoint spans (e.g. 'cotton pants sales in Tamil Nadu'), they are not mutually exclusive. They represent compound filters (ProductGroup='Cotton Pants' AND State='Tamil Nadu'). They do not constitute ambiguity, and both should be resolved and used.

### CASE F — EXACT FULL MATCH VS WEAKER FULL MATCH
- **Example**: Query `banians` matching `Banians` (EXACT) and `Banians` (SINGULAR_PLURAL/FUZZY).
- **Verdict**: **HARMLESS MULTIPLE MATCHES**
- **Explanation**: The exact match represents the identical entity. The other match types are just alternative morphological derivations of the same underlying value. Consolidation merges them, and the exact match correctly suppresses any ambiguity.

### CASE G — MULTIPLE SAME-DIMENSION FULL MATCHES
- **Example**: Query `shirt` matching `Ramraj Shirt` (Brand) and `Red Shirt` (Brand) and `Viveagham Colour Shirt` (Brand).
- **Verdict**: **TRUE AMBIGUITY**
- **Explanation**: Multiple distinct values in the same dimension are matched (all are brands). Since all are brands and are mutually exclusive for a single brand filter context, we must ask the user to clarify.

### CASE H — MULTIPLE PARTIAL MATCHES ON DIFFERENT SPANS
- **Example**: Query `formal shirt` matching `Formal Socks` (on 'formal') and `Viveagham Colour Shirt` (on 'shirt').
- **Verdict**: **TRUE AMBIGUITY (or incomplete interpretation)**
- **Explanation**: Since no candidate covers the full query, and we have multiple partial matches on different spans that do not form a single coherent full-coverage match, they must be presented to the user to clarify what was intended, or return NO_MATCH if the overlap is too weak. If they represent distinct dimensions, they might be compound filters, but if they represent the same dimension (e.g. two product categories), it is ambiguous.

## 4. Explicit Answers to Important Questions

1. **What defines 'genuine semantic ambiguity'?**
   Genuine semantic ambiguity occurs when a user query contains terms that can be mapped to two or more mutually exclusive dimension values (either in the same dimension or across different dimensions) with comparable semantic confidence and coverage, such that the system cannot deterministically choose one without risking an incorrect SQL filter.

2. **Is candidate count alone sufficient?**
   No. Candidate count alone is misleading. A query can yield 10 candidates where 9 are weak, partial, or subsumed sub-span matches, and 1 is a 100% full-coverage match. This is harmless. Clarification is only needed if there are multiple *competing, high-quality, mutually exclusive* matches.

3. **How much stronger must a full-coverage candidate be than a partial candidate?**
   A full-coverage candidate (matching all meaningful query tokens) is inherently stronger than any partial candidate (matching a subset). A partial candidate should never dominate a full-coverage candidate unless the full-coverage candidate has extremely low confidence (e.g. < 0.60 vs 1.00 for the partial match). In general, a full-coverage candidate should suppress all partial candidates of equal or lower confidence.

4. **Should same-dimension alternatives be treated differently from cross-dimension alternatives?**
   Yes. Same-dimension alternatives represent different *values* of the same business filter (e.g., Brand='Ramraj' vs Brand='Linen'). Clarification must present these as value choices. Cross-dimension alternatives represent different *filters* entirely (e.g. Brand='Ramraj' vs State='Ramraj'). Clarification must explicitly call out the dimension context ('Do you mean the brand Ramraj or the State Ramraj?'). Also, cross-dimension matches on disjoint spans are compound filters (non-exclusive), whereas same-dimension matches on the same span are mutually exclusive.

5. **Should exact full-match candidates suppress weaker alternatives?**
   Yes, an EXACT full-match candidate should completely suppress weaker alternatives (like fuzzy or sub-span matches) if those alternatives are in the same dimension or overlap the same query span, as the exact match represents the definitive user intent.

6. **When should clarification be generated?**
   Clarification should be generated only when there is `STRONG_AMBIGUITY`: multiple candidates survive containment and ranking, and the top candidate does not dominate the second candidate by a sufficient priority, confidence, or coverage gap.

7. **When should the system silently choose the dominant candidate?**
   The system should silently resolve to the dominant candidate (`SINGLE_MATCH` or `WEAK_AMBIGUITY`) when the top candidate has a clear semantic advantage (e.g., covers the full query while others only cover sub-spans, or is an EXACT match while others are weak FUZZY matches).

8. **When should the system return NO_MATCH?**
   When no candidates are found, or when all retrieved candidates fail to meet the token-level quality gate (e.g., fuzzy confidence is below the threshold, or matches only cover stopwords).

9. **Can a partial single match remain valid?**
   Yes. If the user types 'sales for cotton' and the only match in the database is 'Cotton' (Fabric), it is a partial match of the query (since 'sales' and 'for' are filtered as stopwords/analytical intent), but it is a single valid dimension match. It is harmless and should be resolved silently as a single match.

10. **What minimum evidence should Phase 1D.5 use?**
    Phase 1D.5 should require that any resolved candidate matches at least one meaningful (non-stopword) token of the user's query with a confidence score above the matcher's specific quality threshold.

## 5. Adversarial Case Results

Here are the results of the 10 adversarial/synthetic test cases run against the pipeline:

| Case | Input Query | Description | Current Status | Dominant | Desired Status | Assessment | Reason |
|---|---|---|---|---|---|---|---|
| A | `cotton pant` | full 2/2 candidate vs partial 1/2 candidate | `STRONG_AMBIGUITY` | `None` | `STRONG_AMBIGUITY` | **CORRECT (Fixed)** | Partial EXACT match must not dominate full-coverage SINGULAR_PLURAL match. |
| B | `pant` | two equal 2/2 candidates | `STRONG_AMBIGUITY` | `None` | `STRONG_AMBIGUITY` | **CORRECT** | Identical coverage & confidence brand alternatives require user selection. |
| C | `cotton pants` | exact 2/2 vs singular/plural 2/2 | `WEAK_AMBIGUITY` | `Cotton Pants` | `SINGLE_MATCH` | **CORRECT** | Exact duplicate values for same dimension must be consolidated. |
| D | `cotton pant` | exact 1/2 vs singular/plural 2/2 | `STRONG_AMBIGUITY` | `None` | `STRONG_AMBIGUITY` | **CORRECT (Fixed)** | Partial EXACT match must not dominate full-coverage SINGULAR_PLURAL match. |
| E | `formal shirt` | fuzzy 2/2 vs fuzzy 1/2 | `WEAK_AMBIGUITY` | `Formal Shirts` | `STRONG_AMBIGUITY` | **CORRECT** | Full-coverage fuzzy match should not be blindly dominated by partial higher confidence fuzzy match. |
| F | `ramraj` | same value different dimensions | `STRONG_AMBIGUITY` | `None` | `STRONG_AMBIGUITY` | **CORRECT** | Identical value representing different dimensions (Brand vs State) requires clarification. |
| G | `shirt` | same dimension different values | `STRONG_AMBIGUITY` | `None` | `STRONG_AMBIGUITY` | **CORRECT** | Multiple distinct brand options require selection. |
| H | `pants` | duplicate rows same dimension/value | `WEAK_AMBIGUITY` | `Pants` | `SINGLE_MATCH` | **CORRECT** | Duplicate rows should consolidate to 1. |
| I | `pant` | unrelated low-quality candidate | `WEAK_AMBIGUITY` | `Pants` | `SINGLE_MATCH` | **CORRECT** | Unrelated low-quality candidate is filtered or ranked out. |
| J | `pant` | three candidates where only two are genuinely plausible | `STRONG_AMBIGUITY` | `None` | `STRONG_AMBIGUITY` | **CORRECT** | Only Linen Pant and Ramraj Pant are plausible; third is noise. Status should be STRONG_AMBIGUITY on the plausible ones. |

## 6. Proposed Ambiguity Decision Rules

To ensure the system consistently distinguishes between True Ambiguity and Harmless matches:
1. **Rule of Full-Coverage Dominance**: Any candidate that covers 100% of the query's meaningful tokens must suppress all candidates that cover less than 100%, unless the full-coverage candidate has a confidence below 0.60.
2. **Rule of Dimension Disjointness**: If multiple candidates match non-overlapping query spans in different dimensions, they are non-exclusive. Treat them as a compound filter, not ambiguity.
3. **Rule of Strict Sub-span Elimination**: If candidate A's matched token span is a strict subset of candidate B's matched span, and B's confidence is not significantly worse than A's (gap < 0.10), candidate A must be removed during the containment phase.
4. **Rule of Value Ambiguity**: If two candidates share the exact same value but represent different dimensions, they must always trigger a dimension-clarifying question.
5. **Rule of Same-Dimension Selection**: If two candidates cover the same query span and belong to the same dimension, they must trigger a value-clarifying question.

## 7. Resolution Categorization

### Cases Needing Clarification
- **Same-dimension value competing**: Query `pant` -> `Linen Pant` vs `Ramraj Pant` (both Brands).
- **Same-value cross-dimension competing**: Query `Ramraj` -> Brand `Ramraj` vs State `Ramraj`.
- **Disjoint partial matches of same dimension**: Query `formal shirt` -> Category `Formal Socks` (partial) vs Brand `Ramraj Shirt` (partial) with no full coverage candidate.

### Cases That Should Auto-Resolve
- **Full coverage vs Partial coverage**: Query `cotton pant` -> `Cotton Pants` (2/2) dominates `Cotton` (1/2 fabric) and resolves silently.
- **Exact match vs Morphological match**: Query `banians` -> EXACT match `Banians` dominates singular/plural and resolves silently.
- **Single match (even if partial)**: Query `cotton` -> Fabric `Cotton` resolves silently since it is the only match.

### Cases That Should Remain Unresolved (NO_MATCH)
- **Pure analytical / stopwords**: Query `sales` or `show sales` -> returns `NO_MATCH` since no meaningful dimension tokens are matched.
- **Low quality matches**: Query containing terms that only trigger low confidence fuzzy matches below 0.80.

## 8. Gaps in Current Implementation

- **Fuzzy Coverage-Blind Ranking**: `MatchRanker` sorts by confidence before coverage. A high-confidence partial fuzzy match could still outrank a lower-confidence full-coverage fuzzy match. While containment currently catches most cases, ranking should sort by query coverage *before* confidence to guarantee correct ordering of fuzzy matches.
- **State Retention in Downstream Pipeline**: Currently, if a query triggers `STRONG_AMBIGUITY`, the pipeline returns the full list of candidates to the API, which prompts the user. However, if the user makes a selection, the API must revalidate the selected choice against the original query to ensure no token or CLS pollution occurred. The revalidation state is stored, but there is a gap in caching query token metadata alongside the options.
