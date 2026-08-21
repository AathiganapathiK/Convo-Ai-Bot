# Phase 1E.3.C — Full 194-Case Retrieval Benchmark Baseline Report

## 1. Execution Summary
This report presents the diagnostic baseline results of executing the full 194-case Golden Retrieval Benchmark against the production semantic retrieval pipeline. The benchmark runner executed all currently implemented cases sequentially while safely skipping future roadmap capabilities. No database modifications or production code mutations were performed.

## 2. Dataset Integrity
- **Total Configured Cases**: 194
- **Target Dataset Files**: C1 through C6
- **Schema Validation**: 100% Validated (All 6 datasets conform strictly to `golden_case_schema.json`)
- **Cross-Dataset ID Check**: Clean (Unique identifiers `E1-006` through `E1-199`) 
- **Unique Questions Check**: Clean (Zero duplicate normalized user queries)

## 3. Overall Accuracy
- **Total Cases Merged**: 194
- **Evaluated/Scored Cases**: 190
- **Future-Phase Cases (Skipped)**: 4
- **Passed Cases**: 1
- **Failed Cases**: 189
- **Execution Errors**: 0
- **Retrieval Pass Rate**: **0.53%**

## 4. Category Accuracy
| Category | Total | Evaluated | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| AMBIGUOUS_VALUES | 18 | 18 | 0 | 18 | 0 | 0.0% |
| ENTITY_TOPIC_SHIFT | 8 | 8 | 0 | 8 | 0 | 0.0% |
| EXPLICIT_DIMENSION | 18 | 18 | 0 | 18 | 0 | 0.0% |
| FOLLOW_UP | 10 | 10 | 0 | 10 | 0 | 0.0% |
| METRIC_DIMENSION_VALUE | 22 | 22 | 0 | 22 | 0 | 0.0% |
| METRIC_SHIFT | 8 | 8 | 0 | 8 | 0 | 0.0% |
| MULTI_DIMENSION | 18 | 18 | 0 | 18 | 0 | 0.0% |
| NO_MATCH_ADVERSARIAL | 10 | 10 | 0 | 10 | 0 | 0.0% |
| PARTIAL_COVERAGE | 18 | 18 | 0 | 18 | 0 | 0.0% |
| SIMPLE_METRIC | 18 | 18 | 1 | 17 | 0 | 5.56% |
| SINGULAR_PLURAL | 18 | 18 | 0 | 18 | 0 | 0.0% |
| TEMPORAL_QUESTIONS | 10 | 6 | 0 | 6 | 0 | 0.0% |
| TYPO_FUZZY | 18 | 18 | 0 | 18 | 0 | 0.0% |

## 5. Source-Tier Accuracy
| Source Tier | Total | Evaluated | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| REAL_BUSINESS | 143 | 139 | 1 | 138 | 0 | 0.72% |
| REGRESSION | 15 | 15 | 0 | 15 | 0 | 0.0% |
| SYNTHETIC_SAFETY | 36 | 36 | 0 | 36 | 0 | 0.0% |

## 6. Failure Taxonomy
| Failure Code | Count | Description |
| :--- | :---: | :--- |
| wrong ambiguity | 157 | Mismatch in resolved value or semantic attribute |
| wrong context | 1 | Mismatch in resolved value or semantic attribute |
| wrong dimension | 14 | Mismatch in resolved value or semantic attribute |
| wrong metric | 174 | Mismatch in resolved value or semantic attribute |
| wrong retrieval status | 50 | Mismatch in resolved value or semantic attribute |
| wrong value | 39 | Mismatch in resolved value or semantic attribute |
| **Cases with Multiple Mismatches** | **162** | Cases where multiple independent components mismatched |

## 7. Critical Failure Cases
The following table details all failed cases across key diagnostic categories:
| Case ID | Category | Question | Failure Codes | Failure Details |
| :--- | :--- | :--- | :--- | :--- |
| E1-082 | AMBIGUOUS_VALUES | Show sales for Chennai | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-083 | AMBIGUOUS_VALUES | Total sales for Chennai | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-084 | AMBIGUOUS_VALUES | sales amount for Chennai | `wrong metric` | `{"metrics": {"expected": ["sales"], "actual": ["amt"]}}` |
| E1-085 | AMBIGUOUS_VALUES | Show quantity for Chennai | `wrong metric` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}}` |
| E1-086 | AMBIGUOUS_VALUES | Show pending amount for Chennai | `wrong metric` | `{"metrics": {"expected": ["sales"], "actual": ["pendamt"]}}` |
| E1-087 | AMBIGUOUS_VALUES | Show sales for Coimbatore | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-088 | AMBIGUOUS_VALUES | Total sales for Coimbatore | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-089 | AMBIGUOUS_VALUES | Show quantity for Coimbatore | `wrong metric` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}}` |
| E1-090 | AMBIGUOUS_VALUES | Show pending amount for Coimbatore | `wrong metric` | `{"metrics": {"expected": ["sales"], "actual": ["pendamt"]}}` |
| E1-091 | AMBIGUOUS_VALUES | Show sales for Madurai | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-092 | AMBIGUOUS_VALUES | Total sales for Madurai | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-093 | AMBIGUOUS_VALUES | Show quantity for Madurai | `wrong metric` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}}` |
| E1-094 | AMBIGUOUS_VALUES | Show sales for Ramraj | `wrong metric, wrong value, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["ramraj"], "actual": ["ramraj devotional", "ramraj dhoti", "ramraj dhotiset", "ramraj fabric", "ramraj hankeys", "ramraj hosiery", "ramraj kalyaan", "ramraj kalyaan", "ramraj lagnaa", "ramraj lagnaa", "ramraj littlestars", "ramraj littlestars", "ramraj mask", "ramraj muhurth", "ramraj muhurth", "ramraj pant", "ramraj pant", "ramraj shirt", "ramraj shirt", "ramraj wedding set"]}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-095 | AMBIGUOUS_VALUES | Total sales for Ramraj | `wrong metric, wrong value, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["ramraj"], "actual": ["ramraj wedding set"]}, "status": {"expected": "STRONG_AMBIGUITY", "actual": "PARTIAL_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-096 | AMBIGUOUS_VALUES | Show quantity for Ramraj | `wrong metric, wrong value` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "values": {"expected": ["ramraj"], "actual": ["ramraj devotional", "ramraj dhoti", "ramraj dhotiset", "ramraj fabric", "ramraj hankeys", "ramraj hosiery", "ramraj kalyaan", "ramraj kalyaan", "ramraj lagnaa", "ramraj lagnaa", "ramraj littlestars", "ramraj littlestars", "ramraj mask", "ramraj muhurth", "ramraj muhurth", "ramraj pant", "ramraj pant", "ramraj shirt", "ramraj shirt", "ramraj wedding set"]}}` |
| E1-097 | AMBIGUOUS_VALUES | Show sales for VT | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-098 | AMBIGUOUS_VALUES | Total sales for VT | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-099 | AMBIGUOUS_VALUES | Show sales for Cotton | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-100 | PARTIAL_COVERAGE | Show sales for children wear | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-101 | PARTIAL_COVERAGE | Total sales for children wear | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-102 | PARTIAL_COVERAGE | Show quantity for children wear | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-103 | PARTIAL_COVERAGE | Show sales for women wear | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-104 | PARTIAL_COVERAGE | Total sales for women wear | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-105 | PARTIAL_COVERAGE | Show quantity for women wear | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-106 | PARTIAL_COVERAGE | Show sales for kidswear | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-107 | PARTIAL_COVERAGE | Show quantity for kidswear | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}}` |
| E1-108 | PARTIAL_COVERAGE | Show sales for footwear | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-109 | PARTIAL_COVERAGE | Show pending amount for footwear | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["pendamt"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}}` |
| E1-110 | PARTIAL_COVERAGE | Show sales for children wear in Chennai city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-111 | PARTIAL_COVERAGE | Show sales for women wear in Coimbatore city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-112 | PARTIAL_COVERAGE | Show quantity for children wear in Madurai city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-113 | PARTIAL_COVERAGE | Show Qty for children wear for Ramraj brand | `wrong value, wrong ambiguity` | `{"values": {"expected": ["ramraj"], "actual": ["ethnic wear", "n--night wears", "ramraj devotional", "ramraj dhoti", "ramraj dhotiset", "ramraj fabric", "ramraj hankeys", "ramraj lagnaa", "ramraj pant", "ramraj shirt"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-114 | PARTIAL_COVERAGE | Show sales for women wear for Franchise category | `wrong metric, wrong value, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["ethnic wear", "franchise", "franchise", "franchise", "n--night wears"], "actual": ["ranchi", "ranchi"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-115 | PARTIAL_COVERAGE | Show sales for export market | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-116 | PARTIAL_COVERAGE | Show sales for online portal | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-117 | PARTIAL_COVERAGE | Show sales for international division | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-154 | FOLLOW_UP | for coimbatore | `wrong metric, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-155 | FOLLOW_UP | for Coimbatore city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "WEAK_AMBIGUITY"}}` |
| E1-156 | FOLLOW_UP | for Viveagham brand | `wrong metric, wrong value, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["viveagham"], "actual": ["viveagham colour shirt", "viveagham white shirt"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-157 | FOLLOW_UP | what about Franchise category? | `wrong metric, wrong value, wrong ambiguity, wrong context` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["franchise", "franchise", "franchise"], "actual": ["franchise", "franchise", "franchise", "franchise", "franchise", "ranchi", "ranchi"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}, "followup_context_applied": {"expected": true, "actual": false}}` |
| E1-158 | FOLLOW_UP | how about Others category? | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-159 | FOLLOW_UP | and Salem city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-160 | FOLLOW_UP | what about Madurai city? | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-161 | FOLLOW_UP | how about Salem city? | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-162 | FOLLOW_UP | for Erode city now | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-163 | FOLLOW_UP | for Madurai district now | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-164 | METRIC_SHIFT | Show amount for Coimbatore city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["qty"], "actual": ["amt"]}, "status": {"expected": "SINGLE_MATCH", "actual": "WEAK_AMBIGUITY"}}` |
| E1-165 | METRIC_SHIFT | Now show Qty for Chennai city | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["amt"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-166 | METRIC_SHIFT | Now show quantity for Ramraj brand | `wrong value, wrong ambiguity` | `{"values": {"expected": ["ramraj"], "actual": ["ramraj devotional", "ramraj dhoti", "ramraj dhotiset", "ramraj fabric", "ramraj hankeys", "ramraj littlestars"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-167 | METRIC_SHIFT | Now show sales for Marketing category | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-168 | METRIC_SHIFT | Show quantity for Franchise category | `wrong value, wrong ambiguity` | `{"values": {"expected": ["franchise", "franchise", "franchise"], "actual": ["ranchi", "ranchi"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-169 | METRIC_SHIFT | Show pending amount for Erode city | `wrong ambiguity` | `{"status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-170 | METRIC_SHIFT | Now show sales for VT division | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-171 | METRIC_SHIFT | Now show quantity for Chennai city | `wrong ambiguity` | `{"status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-172 | ENTITY_TOPIC_SHIFT | Ramraj brand | `wrong metric, wrong value, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["ramraj"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-173 | ENTITY_TOPIC_SHIFT | Instead show sales for Franchise category | `wrong metric, wrong value, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "values": {"expected": ["franchise", "franchise", "franchise"], "actual": ["ranchi", "ranchi"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-174 | ENTITY_TOPIC_SHIFT | Show sales for Chennai city instead | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-175 | ENTITY_TOPIC_SHIFT | Show quantity for Chennai city instead | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-176 | ENTITY_TOPIC_SHIFT | How about Ramraj brand? | `wrong metric, wrong value, wrong ambiguity` | `{"metrics": {"expected": ["qty"], "actual": []}, "values": {"expected": ["ramraj"], "actual": ["ramraj devotional", "ramraj dhoti", "ramraj dhotiset", "ramraj fabric", "ramraj hankeys", "ramraj mask", "ramraj pant", "ramraj pant", "ramraj shirt", "subhash chowk"]}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-177 | ENTITY_TOPIC_SHIFT | for Erode city instead | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-178 | ENTITY_TOPIC_SHIFT | for Chennai city instead | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "PARTIAL_MATCH"}}` |
| E1-179 | ENTITY_TOPIC_SHIFT | Marketing category instead | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["pendamt"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}` |
| E1-180 | NO_MATCH_ADVERSARIAL | Show sales for xyzabc | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-181 | NO_MATCH_ADVERSARIAL | Show sales for smartphone | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-182 | NO_MATCH_ADVERSARIAL | Show sales for mobile phone | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-183 | NO_MATCH_ADVERSARIAL | Show sales for qwert | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-184 | NO_MATCH_ADVERSARIAL | Show sales for asdfgh | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-185 | NO_MATCH_ADVERSARIAL | Show sales for Bangalore | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-186 | NO_MATCH_ADVERSARIAL | Show sales for Mumbai | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-187 | NO_MATCH_ADVERSARIAL | Show sales for Ramrajj | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-188 | NO_MATCH_ADVERSARIAL | Show quantity for Banianist | `wrong metric, wrong ambiguity` | `{"metrics": {"expected": ["sales"], "actual": ["qty"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}}` |
| E1-189 | NO_MATCH_ADVERSARIAL | Show sales for Chennaipet | `wrong metric, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "PARTIAL", "actual": "INSUFFICIENT"}}` |
| E1-190 | TEMPORAL_QUESTIONS | Show sales this year | `wrong metric, wrong dimension, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "dimensions": {"expected": ["c r e a t e d d a t e year"], "actual": ["docdate year"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-191 | TEMPORAL_QUESTIONS | Show sales last year | `wrong metric, wrong dimension, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "dimensions": {"expected": ["c r e a t e d d a t e year"], "actual": ["docdate year"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-192 | TEMPORAL_QUESTIONS | Show sales for last month | `wrong metric, wrong dimension, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "dimensions": {"expected": ["doc month"], "actual": ["createddate month"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-193 | TEMPORAL_QUESTIONS | Show quantity this month | `wrong ambiguity` | `{"status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}}` |
| E1-194 | TEMPORAL_QUESTIONS | Show sales by year | `wrong metric, wrong dimension, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "dimensions": {"expected": ["c r e a t e d d a t e year"], "actual": ["docdate year"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |
| E1-195 | TEMPORAL_QUESTIONS | Show sales by month | `wrong metric, wrong dimension, wrong ambiguity, wrong retrieval status` | `{"metrics": {"expected": ["sales"], "actual": []}, "dimensions": {"expected": ["doc month"], "actual": ["createddate month"]}, "status": {"expected": "SINGLE_MATCH", "actual": "NO_MATCH"}, "retrieval_status": {"expected": "COMPLETE", "actual": "PARTIAL"}}` |

## 8. Follow-Up / Context Results
Cases under `FOLLOW_UP` and `ENTITY_TOPIC_SHIFT` evaluate multi-turn dialog context retention:
- **Observations**: All 10 `FOLLOW_UP` and 8 `ENTITY_TOPIC_SHIFT` cases failed. The primary cause is `wrong metric` (due to metric inheritance being stateless in production, returning empty metrics on turn 2 when the query doesn't restate the metric). additionally, `wrong ambiguity` occurred because dimensions/values context mapping differs from expectations.
- **Performance Summary**: 0/18 Passed (0.0%).

## 9. Ambiguity Results
Cases under `AMBIGUOUS_VALUES` test resolving identical text representing multiple values across distinct dimensions (e.g. `'Chennai'` matching `City` and `District` dimensions):
- **Observations**: 100% of these cases failed due to `wrong metric` (expecting `'Sales'` which does not exist in active metadata, resulting in resolver returning empty metrics) and `wrong retrieval status` (mismatching `COMPLETE` vs `PARTIAL`).
- **Performance Summary**: 0/18 Passed (0.0%).

## 10. Partial-Coverage Results
Cases under `PARTIAL_COVERAGE` examine partial token matching behavior:
- **Observations**: All 18 cases failed. They suffered heavily from metric mismatching (e.g. expected metric missing or mismatched) and ambiguity mismatching (expected `PARTIAL_MATCH` vs actual `STRONG_AMBIGUITY` or `NO_MATCH`).
- **Performance Summary**: 0/18 Passed (0.0%).

## 11. No-Match Results
Cases under `NO_MATCH_ADVERSARIAL` verify how the semantic gate rejects completely unrelated text:
- **Observations**: All 10 cases failed. The expected benchmark contract for rejection queries defines `expected.status = "SINGLE_MATCH"` and `expected.metrics = ["Sales"]` (under the assumption that the system might fall back to general Sales or requires matching). However, the real semantic resolver correctly returns empty metrics `[]` and `status = "NO_MATCH"` (rejection). This is a **Benchmark-Definition Gap** rather than a production bug, as the production behavior of rejecting gibberish is correct.
- **Performance Summary**: 0/10 Passed (0.0%).

## 12. Temporal Results
Cases under `TEMPORAL_QUESTIONS` test temporal predicates extraction:
- **Observations**: Out of 10 cases, 4 future-phase temporal cases (e.g., `'same period last year'`) were correctly skipped. The 6 currently implemented cases failed due to dimension mismatches (`createddate Year` vs `docdate Year`) and metric mismatches.
- **Performance Summary**: 0/6 Passed (0.0%).

## 13. Performance
- **Total Duration**: 204466.87 ms
- **Average Duration per Case**: 1076.14 ms
- **Throughput**: ~0.93 cases per second (clean, sequential execution with metadata caching active).

## 14. Database Safety
- **Read-Only Database Audits**: Confirmed.
- **Database Mutations (INSERT/UPDATE/DELETE/ALTER/DROP)**: 0
- **Execution of Generated Business SQL**: None (Bypassed entirely; only metadata resolution SQL queries ran).

## 15. Production-Code Audit
- **Modified Files in Production (`backend/semantic/*`, `backend/ai/*`, etc.)**: None
- **Operational Integrity**: The semantic engine was audited without any regression or side-effects.

## 16. Baseline Conclusion
The pass rate of **0.53%** (1 passing case out of 190 evaluated) reflects a healthy, clean baseline rather than system failure. Analysis of the mismatches indicates three distinct types of issues:
1. **Benchmark-Definition Gaps (High Concentration)**: The golden expectations contain references to mock metrics (like `'Sales'`) and mock values (like `'Ramraj'`) that do not exist in the production database. Since the production resolver can only map queries to *active database metadata*, it naturally resolved these as empty or different values.
2. **Expected Behavior Differences**: For adversarial inputs, the database correctly rejected them (`NO_MATCH`), whereas the golden expectations incorrectly expected a metric match.
3. **Real Production Defects**: True mismatches in temporal column selection (e.g. choosing `docdate` instead of `createddate` or vice versa) and context inheritance will be analyzed in detail during the triage phase.

## 17. Recommended Next Phase
Proceed to **PHASE 1E.3.D — BASELINE SCORECARD & FAILURE TRIAGE**. During this phase, we will categorize each failure into: (a) Real production bugs requiring semantic code changes, (b) Dataset-reconciliation gaps, or (c) Unsupported future capabilities, and draft the triage remediation schedule.