# Phase 1E Golden Retrieval Benchmark Report

## 1. Performance Executive Summary

- **Total Cases Merged**: 194
- **Evaluated (Currently Implemented)**: 190
- **Excluded (Future Roadmap)**: 4
- **Passed Cases**: 51
- **Failed Cases**: 139
- **Cases with Multiple Mismatches**: 66
- **Execution Errors**: 0
- **Retrieval Pass Rate**: **26.84%**
- **Average Resolving Time**: 1509.72 ms
- **Total Resolving Time**: 286846.59 ms

## 2. Category Accuracy Grid

| Category | Total Cases | Evaluated | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| AMBIGUOUS_VALUES | 18 | 18 | 14 | 4 | 0 | 77.78% |
| ENTITY_TOPIC_SHIFT | 8 | 8 | 0 | 8 | 0 | 0.0% |
| EXPLICIT_DIMENSION | 18 | 18 | 3 | 15 | 0 | 16.67% |
| FOLLOW_UP | 10 | 10 | 0 | 10 | 0 | 0.0% |
| METRIC_DIMENSION_VALUE | 22 | 22 | 8 | 14 | 0 | 36.36% |
| METRIC_SHIFT | 8 | 8 | 1 | 7 | 0 | 12.5% |
| MULTI_DIMENSION | 18 | 18 | 0 | 18 | 0 | 0.0% |
| NO_MATCH_ADVERSARIAL | 10 | 10 | 0 | 10 | 0 | 0.0% |
| PARTIAL_COVERAGE | 18 | 18 | 10 | 8 | 0 | 55.56% |
| SIMPLE_METRIC | 18 | 18 | 9 | 9 | 0 | 50.0% |
| SINGULAR_PLURAL | 18 | 18 | 1 | 17 | 0 | 5.56% |
| TEMPORAL_QUESTIONS | 10 | 6 | 0 | 6 | 0 | 0.0% |
| TYPO_FUZZY | 18 | 18 | 5 | 13 | 0 | 27.78% |

## 3. Source-Tier Accuracy Breakdown

| Source Tier | Total | Evaluated | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| REAL_BUSINESS | 143 | 139 | 36 | 103 | 0 | 25.9% |
| REGRESSION | 15 | 15 | 5 | 10 | 0 | 33.33% |
| SYNTHETIC_SAFETY | 36 | 36 | 10 | 26 | 0 | 27.78% |

## 4. Failure Taxonomy & Breakdown

| Failure Code | Count | Description |
| :--- | :---: | :--- |
| wrong ambiguity | 105 | Mismatch or exception in benchmark run |
| wrong dimension | 17 | Mismatch or exception in benchmark run |
| wrong metric | 34 | Mismatch or exception in benchmark run |
| wrong retrieval status | 19 | Mismatch or exception in benchmark run |
| wrong value | 41 | Mismatch or exception in benchmark run |

## 5. Representative Mismatches / Failed Cases

### 1. Case E1-015 (SIMPLE_METRIC)
- **Question**: "Show bill amount"
- **Failure Codes**: `["wrong metric"]`
- **Failure Details**: {"metrics": {"expected": ["amt"], "actual": ["billamt"]}}
- **Expected**: {"metrics": ["Amt"], "dimensions": [], "values": [], "status": "NO_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "PARTIAL"}
- **Actual**: {"metrics": ["billamt"], "dimensions": [], "values": [], "status": "NO_MATCH", "retrieval_status": "PARTIAL", "followup_context_applied": false, "dominant_candidate": null}

### 2. Case E1-016 (SIMPLE_METRIC)
- **Question**: "Total bill amount"
- **Failure Codes**: `["wrong metric"]`
- **Failure Details**: {"metrics": {"expected": ["amt"], "actual": ["billamt"]}}
- **Expected**: {"metrics": ["Amt"], "dimensions": [], "values": [], "status": "NO_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "PARTIAL"}
- **Actual**: {"metrics": ["billamt"], "dimensions": [], "values": [], "status": "NO_MATCH", "retrieval_status": "PARTIAL", "followup_context_applied": false, "dominant_candidate": null}

### 3. Case E1-017 (SIMPLE_METRIC)
- **Question**: "Show due amount"
- **Failure Codes**: `["wrong ambiguity"]`
- **Failure Details**: {"status": {"expected": "PARTIAL_MATCH", "actual": "STRONG_AMBIGUITY"}}
- **Expected**: {"metrics": ["due"], "dimensions": [], "values": ["NO DUE", "OVER DUE", "Due Today", "Future Due", "Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)"], "status": "PARTIAL_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["due"], "dimensions": [], "values": ["NO DUE", "OVER DUE", "Due Today", "Future Due", "Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)"], "status": "STRONG_AMBIGUITY", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": null}

### 4. Case E1-018 (SIMPLE_METRIC)
- **Question**: "Total due amount"
- **Failure Codes**: `["wrong ambiguity"]`
- **Failure Details**: {"status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}
- **Expected**: {"metrics": ["due"], "dimensions": [], "values": ["Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)"], "status": "SINGLE_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["due"], "dimensions": [], "values": ["Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)"], "status": "STRONG_AMBIGUITY", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": null}

### 5. Case E1-019 (SIMPLE_METRIC)
- **Question**: "Show payment amount"
- **Failure Codes**: `["wrong ambiguity"]`
- **Failure Details**: {"status": {"expected": "PARTIAL_MATCH", "actual": "STRONG_AMBIGUITY"}}
- **Expected**: {"metrics": ["Amt"], "dimensions": [], "values": ["FULL PAYMENT", "PARTIAL PAYMENT"], "status": "PARTIAL_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["Amt"], "dimensions": [], "values": ["FULL PAYMENT", "PARTIAL PAYMENT"], "status": "STRONG_AMBIGUITY", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": null}

### 6. Case E1-020 (SIMPLE_METRIC)
- **Question**: "Show due days"
- **Failure Codes**: `["wrong ambiguity"]`
- **Failure Details**: {"status": {"expected": "PARTIAL_MATCH", "actual": "STRONG_AMBIGUITY"}}
- **Expected**: {"metrics": ["due"], "dimensions": [], "values": ["Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)"], "status": "PARTIAL_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["due"], "dimensions": [], "values": ["Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)"], "status": "STRONG_AMBIGUITY", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": null}

### 7. Case E1-021 (SIMPLE_METRIC)
- **Question**: "Average due days"
- **Failure Codes**: `["wrong ambiguity"]`
- **Failure Details**: {"status": {"expected": "SINGLE_MATCH", "actual": "STRONG_AMBIGUITY"}}
- **Expected**: {"metrics": ["due"], "dimensions": [], "values": ["Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)", "Future Due", "Due Today"], "status": "SINGLE_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["due"], "dimensions": [], "values": ["Current Due (1-7)", "Delayed Due (16-30)", "Critical Due (31-60)", "Future Due", "Due Today"], "status": "STRONG_AMBIGUITY", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": null}

### 8. Case E1-022 (SIMPLE_METRIC)
- **Question**: "Current year sales"
- **Failure Codes**: `["wrong dimension"]`
- **Failure Details**: {"dimensions": {"expected": ["createddate year"], "actual": []}}
- **Expected**: {"metrics": ["C Y"], "dimensions": ["createddate Year"], "values": ["Current Due (1-7)"], "status": "PARTIAL_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["C Y"], "dimensions": [], "values": ["Current Due (1-7)"], "status": "PARTIAL_MATCH", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": "Current Due (1-7)"}

### 9. Case E1-023 (SIMPLE_METRIC)
- **Question**: "Previous year sales"
- **Failure Codes**: `["wrong metric", "wrong dimension"]`
- **Failure Details**: {"metrics": {"expected": ["c y"], "actual": ["p y"]}, "dimensions": {"expected": ["createddate year"], "actual": []}}
- **Expected**: {"metrics": ["C Y"], "dimensions": ["createddate Year"], "values": [], "status": "NO_MATCH", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "PARTIAL"}
- **Actual**: {"metrics": ["P Y"], "dimensions": [], "values": [], "status": "NO_MATCH", "retrieval_status": "PARTIAL", "followup_context_applied": false, "dominant_candidate": null}

### 10. Case E1-032 (METRIC_DIMENSION_VALUE)
- **Question**: "Show pending amount for Chennai city"
- **Failure Codes**: `["wrong ambiguity"]`
- **Failure Details**: {"status": {"expected": "WEAK_AMBIGUITY", "actual": "PARTIAL_MATCH"}}
- **Expected**: {"metrics": ["pendamt"], "dimensions": ["City"], "values": ["CHENNAI"], "status": "WEAK_AMBIGUITY", "followup_context_applied": false, "dominant_candidate": null, "retrieval_status": "COMPLETE"}
- **Actual**: {"metrics": ["pendamt"], "dimensions": [{"dimension_name": "city", "business_name": "City", "table_name": "PBI_OUTSTANDING_ENES_SUMMARY", "column_name": "City"}], "values": ["CHENNAI"], "status": "PARTIAL_MATCH", "retrieval_status": "COMPLETE", "followup_context_applied": false, "dominant_candidate": "CHENNAI"}

