"""
Gate 3 Step 16 - integrity checks for benchmark v2.

Read-only. Asserts the three properties Step 16 promised:

  1. The v1 expectation is preserved for every case, in
     `expectation_review.original_expected`. This is the historical record and
     must always match the v1 file, whether or not `expected` was corrected.
  2. Every case has exactly one verdict, drawn from A-E or VALID.
  3. No expectation was changed without evidence. `expected` may differ from
     v1 only when `expectation_changed_in_v2` is true AND a change_log records
     what was changed and why; otherwise it must be byte-identical to v1.

    python backend/test/semantic_benchmark/v2/validate_v2.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V1_DIR = os.path.dirname(HERE)

VALID_VERDICTS = {"A", "B", "C", "D", "E", "VALID"}
VALID_ANSWERABLE = {"yes", "no", "partial"}

failures = []
verdict_counts = {}
answerable_counts = {}
total = 0
human_review = []

for i in range(1, 7):
    v1_path = os.path.join(V1_DIR, "golden_dataset_1e_2_c%d.json" % i)
    v2_path = os.path.join(HERE, "golden_dataset_v2_c%d.json" % i)

    v1 = {c["case_id"]: c for c in json.load(open(v1_path, encoding="utf-8"))}
    v2 = json.load(open(v2_path, encoding="utf-8"))

    if len(v1) != len(v2):
        failures.append("c%d: case count %d in v1 vs %d in v2" % (i, len(v1), len(v2)))

    for case in v2:
        total += 1
        cid = case["case_id"]

        if cid not in v1:
            failures.append("%s: present in v2 but not in v1" % cid)
            continue

        # 1. handled together with rule 3 below, once the review is in hand

        review = case.get("expectation_review")
        if not review:
            failures.append("%s: no expectation_review" % cid)
            continue

        # 2. exactly one valid verdict
        verdict = review.get("verdict")
        if verdict not in VALID_VERDICTS:
            failures.append("%s: invalid verdict %r" % (cid, verdict))
        else:
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        if not review.get("rationale"):
            failures.append("%s: verdict has no rationale" % cid)

        # 1 + 3. the v1 expectation is always preserved as the historical
        # record; `expected` may only depart from it with a logged reason.
        if review.get("original_expected") != v1[cid]["expected"]:
            failures.append("%s: original_expected does not match the v1 file - "
                            "the historical record has been lost" % cid)

        changed = case["expected"] != v1[cid]["expected"]

        if changed and not review.get("expectation_changed_in_v2"):
            failures.append("%s: `expected` differs from v1 but "
                            "expectation_changed_in_v2 is false" % cid)

        if changed and not review.get("change_log"):
            failures.append("%s: expectation changed without a change_log" % cid)

        if review.get("expectation_changed_in_v2") and not changed:
            failures.append("%s: flagged as changed but `expected` is identical "
                            "to v1" % cid)

        evidence = review.get("evidence") or {}
        if verdict in {"A", "B", "C", "E"} and "diagnostic_run" not in evidence:
            failures.append("%s: verdict %s without diagnostic evidence" % (cid, verdict))

        if verdict == "B" and not evidence.get("config_problems"):
            failures.append("%s: verdict B but no config problem recorded" % cid)

        if review.get("requires_human_review"):
            human_review.append(cid)

        if "expected_identity" not in case:
            failures.append("%s: no expected_identity block" % cid)

        # 4. the two axes stay separate and internally consistent
        da = case.get("data_answerable")
        if da not in VALID_ANSWERABLE:
            failures.append("%s: data_answerable is %r, expected one of %s"
                            % (cid, da, sorted(VALID_ANSWERABLE)))
        else:
            answerable_counts[da] = answerable_counts.get(da, 0) + 1

        md = case.get("missing_data")
        if md is None:
            failures.append("%s: no missing_data field" % cid)
        elif da in {"no", "partial"} and not md:
            failures.append("%s: data_answerable=%s but missing_data is empty - "
                            "the blocking field or join must be named" % (cid, da))
        elif da == "yes" and md:
            failures.append("%s: data_answerable=yes but missing_data is "
                            "populated" % cid)

        # A verdict means the expectation is achievable, so it must carry no
        # configuration problems. Answerability is a separate axis and is
        # deliberately NOT consulted here - A with data_answerable=no is legal.
        if verdict == "A" and (review.get("evidence") or {}).get("config_problems"):
            failures.append("%s: verdict A but configuration problems exist" % cid)

        if verdict == "E" and not review.get("requires_human_review"):
            failures.append("%s: verdict E must be flagged for human review" % cid)

print("cases checked      : %d" % total)
print("verdict counts     : %s" % verdict_counts)
print("sum of verdicts    : %d" % sum(verdict_counts.values()))
print("data_answerable     : %s" % answerable_counts)
print("needing human review: %d %s" % (len(human_review), human_review[:12]))

if failures:
    print("\nFAILURES (%d):" % len(failures))
    for f in failures[:40]:
        print("  - %s" % f)
    sys.exit(1)

print("\nAll v2 integrity checks passed.")
