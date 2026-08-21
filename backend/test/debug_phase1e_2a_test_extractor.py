import sys
import os
import re
import json

test_files = [
    "test_phase1d_2_b_ambiguity.py",
    "test_phase1d_2_e_clarification.py",
    "test_phase1d_2_g_clarification_hardening.py",
    "test_phase1d_5_b1_explicit_dimension_context.py",
    "test_phase1d_5_b2_followup_dimension_context.py",
    "test_phase1d_5_b3_metric_guard_refinement.py",
    "test_phase1d_5_c_integration_gaps.py",
    "test_phase1d_6_a_thread_safety.py",
    "test_phase1d_6_c_partial_coverage_safety.py",
    "test_phase1d_6_d3_selection_matching.py",
    "test_phase1d_6_d4_resume_security.py"
]

def extract_test_cases():
    test_dir = os.path.dirname(__file__)
    all_extracted = []

    for tf in test_files:
        filepath = os.path.join(test_dir, tf)
        if not os.path.exists(filepath):
            continue
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Find test method names and strings/queries in them
        methods = re.findall(r'def (test_\w+)\(self.*?\):', content)
        # Find string literals in resolve / ask_question / tests
        queries = re.findall(r'question\s*=\s*["\']([^"\']+)["\']', content)
        queries += re.findall(r'resolve\([^,\n]+,\s*["\']([^"\']+)["\']', content)
        queries += re.findall(r'ask_question\([^,\n]+,\s*["\']([^"\']+)["\']', content)

        all_extracted.append({
            "file": tf,
            "test_count": len(methods),
            "test_methods": methods,
            "sample_queries": sorted(list(set(queries)))
        })

    print(json.dumps(all_extracted, indent=2))
    with open("backend/test/test_extraction_output.json", "w") as f:
        json.dump(all_extracted, f, indent=2)

if __name__ == "__main__":
    extract_test_cases()
