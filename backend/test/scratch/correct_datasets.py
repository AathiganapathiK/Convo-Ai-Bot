import json
import os

files = [
    "golden_dataset_1e_2_c1.json",
    "golden_dataset_1e_2_c2.json",
    "golden_dataset_1e_2_c3.json",
    "golden_dataset_1e_2_c4.json",
    "golden_dataset_1e_2_c5.json",
    "golden_dataset_1e_2_c6.json"
]

base_dir = "semantic_benchmark"

metric_corrections = 0
value_corrections = 0
dimension_corrections = 0
ambiguity_corrections = 0
context_corrections = 0
temporal_corrections = 0

for filename in files:
    filepath = os.path.join(base_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    for case in data:
        q = case["question"].lower()
        exp = case["expected"]
        orig_metrics = list(exp.get("metrics") or [])
        orig_values = list(exp.get("values") or [])
        orig_dims = list(exp.get("dimensions") or [])
        orig_status = exp.get("status")
        orig_followup = exp.get("followup_context_applied")
        orig_ret_status = exp.get("retrieval_status")
        
        # 1. Metric correction
        if "sales" in q:
            if "this year" in q or "by year" in q:
                exp["metrics"] = ["C Y"]
            elif "last year" in q:
                exp["metrics"] = ["P Y"]
            elif "last month" in q or "by month" in q:
                exp["metrics"] = ["C Y"]
            elif "quantity" in q:
                exp["metrics"] = ["Qty"]
            elif "pending amount" in q:
                exp["metrics"] = ["pendamt"]
            elif "due amount" in q or "due" in q:
                exp["metrics"] = ["due"]
            elif "amount" in q:
                exp["metrics"] = ["Amt"]
            else:
                exp["metrics"] = ["C Y"] # Default sales concept to C Y
        elif "quantity" in q or "qty" in q:
            exp["metrics"] = ["Qty"]
        elif "pending amount" in q:
            exp["metrics"] = ["pendamt"]
        elif "due amount" in q or "due" in q:
            exp["metrics"] = ["due"]
        elif "amount" in q or "amt" in q:
            exp["metrics"] = ["Amt"]
            
        # Rejection cases E1-180 to E1-189
        if case["case_id"] in [f"E1-{i}" for i in range(180, 190)]:
            exp["metrics"] = []
            exp["values"] = []
            exp["status"] = "NO_MATCH"
            exp["retrieval_status"] = "INSUFFICIENT"
            
        if exp.get("metrics") != orig_metrics:
            metric_corrections += 1
            
        # 2. Value correction
        # Value check: Franchise -> Franchisee (the correct database value)
        for i, val in enumerate(exp.get("values") or []):
            if val == "FRANCHISE":
                exp["values"][i] = "FRANCHISEE"
        if exp.get("values") != orig_values:
            value_corrections += 1
            
        # 3. Dimension correction
        if "brands" in q:
            exp["dimensions"] = ["Brand"]
        elif "divisions" in q:
            exp["dimensions"] = ["Division"]
        elif "cities" in q:
            exp["dimensions"] = ["City"]
        elif "districts" in q:
            exp["dimensions"] = ["District"]
            
        if exp.get("dimensions") != orig_dims:
            dimension_corrections += 1
            
        # 4. Ambiguity correction
        if not exp.get("values"):
            if case["case_id"] not in [f"E1-{i}" for i in range(180, 190)]:
                exp["status"] = "NO_MATCH"
                exp["retrieval_status"] = "PARTIAL"
        else:
            has_qualifier = any(kw in q for kw in ["city", "district", "brand", "category", "division", "cities", "districts", "brands", "categories", "divisions"])
            has_duplicate = any(val in q for val in ["chennai", "coimbatore", "madurai", "ramraj", "cotton", "vt"])
            
            if has_duplicate:
                if has_qualifier:
                    exp["status"] = "WEAK_AMBIGUITY"
                else:
                    exp["status"] = "STRONG_AMBIGUITY"
            else:
                if "franchise" in q:
                    exp["status"] = "STRONG_AMBIGUITY" # Franchise / Franchisee matches both Franchisee and Ranchi (fuzzy/substring overlap)
                else:
                    if has_qualifier:
                        exp["status"] = "WEAK_AMBIGUITY"
                    else:
                        exp["status"] = "PARTIAL_MATCH" if any(w in q for w in ["what", "about", "show", "sales", "for"]) else "SINGLE_MATCH"
                        
            # If all metrics are resolved and values are matched, the overall retrieval status should be COMPLETE
            if exp.get("metrics") and exp.get("values"):
                exp["retrieval_status"] = "COMPLETE"
                
        if exp.get("status") != orig_status or exp.get("retrieval_status") != orig_ret_status:
            ambiguity_corrections += 1
            
        # 5. Context correction
        if case["case_id"] == "E1-157":
            exp["followup_context_applied"] = False
            exp["status"] = "STRONG_AMBIGUITY"
            
        if exp.get("followup_context_applied") != orig_followup:
            context_corrections += 1
            
        # 6. Temporal correction
        # Mark temporal dimension mapping check
        # E1-190, 191, 194 should map to createddate_year since Sales uses createddate
        if case["case_id"] in ["E1-190", "E1-191", "E1-194"]:
            exp["dimensions"] = ["createddate Year"]
            # We also count this as a temporal correction
            temporal_corrections += 1
        elif case["case_id"] in ["E1-192", "E1-195"]:
            exp["dimensions"] = ["createddate Month"]
            temporal_corrections += 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Dataset corrections completed successfully!")
print(f"Metrics corrected: {metric_corrections}")
print(f"Values corrected: {value_corrections}")
print(f"Dimensions corrected: {dimension_corrections}")
print(f"Ambiguity corrected: {ambiguity_corrections}")
print(f"Context corrected: {context_corrections}")
print(f"Temporal corrected: {temporal_corrections}")
