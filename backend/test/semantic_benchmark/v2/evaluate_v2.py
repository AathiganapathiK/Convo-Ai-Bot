"""
Gate 3 - the v2 comparison contract.

Identical to run_retrieval_benchmark.py's evaluate_case in every respect but
one: metrics and dimensions are compared on their PHYSICAL IDENTITY,
(table_name, column_name), instead of on their business name.

Why the change. A business name is a display string an administrator can edit
at any moment, and editing one silently breaks the benchmark. It has already
happened three times: `pendamt` -> `P A M T`, `Amt` -> `Amount`, and
`P A M T` -> `Pending Amount`. Each rename left the resolver returning exactly
the right column while the benchmark reported a failure. Step 16 recorded the
physical identity of every expected metric and dimension in `expected_identity`
for this purpose; this module is what finally reads it.

Values, ambiguity status, retrieval status and follow-up context are compared
exactly as v1 compares them - values are data, not names, so renaming does not
touch them.

Falls back to name comparison for any case with no `expected_identity` block,
so a dataset that predates Step 16 still runs.
"""

import time


def _identity_set(identity_entries):
    """The (table, column) pairs an expectation requires."""
    out = set()
    for entry in identity_entries or []:
        for physical in entry.get("physical") or []:
            table = (physical.get("table_name") or "").strip().lower()
            column = (physical.get("column_name") or "").strip().lower()
            if table or column:
                out.add((table, column))
    return out


def _actual_identity_set(objects):
    out = set()
    for obj in objects or []:
        table = (obj.get("table_name") or "").strip().lower()
        column = (obj.get("column_name") or "").strip().lower()
        if table or column:
            out.add((table, column))
    return out


def _fmt(pairs):
    return sorted("%s.%s" % (t, c) for t, c in pairs)


def evaluate_case_v2(case, connection_id, resolver, normalize_list):
    """
    Score one v2 case. `resolver` and `normalize_list` are injected so this
    module holds no import-time dependency on the runner or the backend.
    """
    expected = case["expected"]
    identity = case.get("expected_identity") or {}
    impl_status = expected.get("implementation_status", "CURRENTLY_IMPLEMENTED")

    record = {
        "case_id": case["case_id"],
        "question": case["question"],
        "category": case["category"],
        "source": case["source"],
        "implementation_status": impl_status,
        "comparison_mode": "identity" if identity else "business_name",
        "scored": False,
        "pass_fail": "SKIPPED",
        "failure_codes": [],
        "failure_details": {},
        "reason": None,
        "duration_ms": 0.0,
        "expected": expected,
        "actual": None,
    }

    if impl_status == "FUTURE_PHASE":
        record["reason"] = "future capability"
        return record

    start = time.perf_counter()

    try:
        prev_context = None
        for turn in case.get("conversation", []):
            res = resolver.resolve(
                connection_id=connection_id,
                question=turn["question"],
                previous_semantic_context=prev_context,
            )
            prev_context = {
                "metrics": [
                    {"metric_name": m.get("metric_name"),
                     "business_name": m.get("business_name"),
                     "table_name": m.get("table_name"),
                     "column_name": m.get("column_name")}
                    for m in res.get("metric_objects", [])
                ],
                "dimensions": [
                    {"dimension_name": d.get("dimension_name"),
                     "business_name": d.get("business_name"),
                     "table_name": d.get("table_name"),
                     "column_name": d.get("column_name")}
                    for d in res.get("dimension_objects", [])
                ],
                "resolved_values": [
                    {"dimension_id": v.get("dimension_id"),
                     "business_name": v.get("business_name"),
                     "table_name": v.get("table_name"),
                     "column_name": v.get("column_name"),
                     "value": v.get("value"),
                     "normalized_value": v.get("normalized_value",
                                               (v.get("value") or "").lower())}
                    for v in res.get("value_matches", [])
                ],
            }

        final = resolver.resolve(
            connection_id=connection_id,
            question=case["question"],
            previous_semantic_context=prev_context,
        )

        record["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        record["scored"] = True

        metric_objs = final.get("metric_objects", []) or []
        dim_objs = final.get("dimension_objects", []) or []
        actual_values = [v.get("value") for v in (final.get("value_matches") or [])]

        ambiguity = final.get("ambiguity_result")
        actual_status = (
            ambiguity.status.value
            if ambiguity and hasattr(ambiguity.status, "value")
            else "NO_MATCH"
        )

        retrieval = final.get("retrieval")
        if not retrieval or "status" not in retrieval:
            raise ValueError("SemanticResolver result missing retrieval.status")
        retrieval_status = retrieval["status"]
        if retrieval_status not in {"COMPLETE", "PARTIAL", "INSUFFICIENT"}:
            raise ValueError("Invalid retrieval.status: %s" % retrieval_status)

        actual_followup = (final.get("followup_context", {}) or {}).get("applied", False)

        record["actual"] = {
            "metrics": [m.get("business_name") for m in metric_objs],
            "metric_identity": _fmt(_actual_identity_set(metric_objs)),
            "dimensions": [
                {"dimension_name": d.get("dimension_name"),
                 "business_name": d.get("business_name"),
                 "table_name": d.get("table_name"),
                 "column_name": d.get("column_name")}
                for d in dim_objs
            ],
            "dimension_identity": _fmt(_actual_identity_set(dim_objs)),
            "values": actual_values,
            "status": actual_status,
            "retrieval_status": retrieval_status,
            "followup_context_applied": actual_followup,
            "unresolved_terms": retrieval.get("unresolved_terms"),
        }

        codes, details = [], {}

        # 1 + 2. metrics and dimensions, on identity where v2 provides it.
        if identity:
            for field, expected_entries, actual_objs in (
                ("metrics", identity.get("metrics"), metric_objs),
                ("dimensions", identity.get("dimensions"), dim_objs),
            ):
                exp_set = _identity_set(expected_entries)
                act_set = _actual_identity_set(actual_objs)

                # An expectation whose name resolves to nothing in the current
                # configuration has no identity to compare. Those are the
                # Step 16 verdict-B cases; fall back to the name so they still
                # fail for the reason Step 16 recorded rather than passing
                # vacuously on an empty set.
                unresolved = [
                    e for e in (expected_entries or [])
                    if not e.get("resolved")
                ]
                if unresolved and not exp_set:
                    exp_names = normalize_list(expected.get(field))
                    act_names = normalize_list(
                        [o.get("business_name") for o in actual_objs]
                    )
                    if act_names != exp_names:
                        codes.append("wrong %s" % field[:-1])
                        details[field] = {"expected": exp_names,
                                          "actual": act_names,
                                          "compared_on": "business_name "
                                                         "(no resolvable identity)"}
                    continue

                if exp_set != act_set:
                    codes.append("wrong %s" % field[:-1])
                    details[field] = {"expected": _fmt(exp_set),
                                      "actual": _fmt(act_set),
                                      "compared_on": "identity"}
        else:
            exp_m = normalize_list(expected.get("metrics"))
            act_m = normalize_list([m.get("business_name") for m in metric_objs])
            if act_m != exp_m:
                codes.append("wrong metric")
                details["metrics"] = {"expected": exp_m, "actual": act_m}

            exp_d = normalize_list(expected.get("dimensions"))
            act_d = normalize_list([d.get("business_name") for d in dim_objs])
            if act_d != exp_d:
                codes.append("wrong dimension")
                details["dimensions"] = {"expected": exp_d, "actual": act_d}

        # 3. values - data, not names, so compared exactly as v1 does.
        exp_v = normalize_list(expected.get("values"))
        act_v = normalize_list(actual_values)
        if act_v != exp_v:
            codes.append("wrong value")
            details["values"] = {"expected": exp_v, "actual": act_v}

        # 4. ambiguity status
        exp_status = expected.get("status")
        if exp_status is not None and actual_status != exp_status:
            if expected.get("values") or case["category"] != "SIMPLE_METRIC":
                codes.append("wrong ambiguity")
                details["status"] = {"expected": exp_status, "actual": actual_status}

        # 5. retrieval status
        exp_ret = expected.get("retrieval_status")
        if exp_ret is not None and retrieval_status != exp_ret:
            codes.append("wrong retrieval status")
            details["retrieval_status"] = {"expected": exp_ret,
                                           "actual": retrieval_status}

        # 6. follow-up context
        exp_followup = expected.get("followup_context_applied", False)
        if actual_followup != exp_followup:
            codes.append("wrong context")
            details["followup_context_applied"] = {"expected": exp_followup,
                                                   "actual": actual_followup}

        record["failure_codes"] = codes
        record["failure_details"] = details
        record["pass_fail"] = "FAIL" if codes else "PASS"
        if codes:
            record["reason"] = "mismatches detected: " + ", ".join(codes)

    except Exception as exc:
        record["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        record["pass_fail"] = "ERROR"
        record["failure_codes"] = ["execution error"]
        record["failure_details"] = {"error": str(exc)}
        record["reason"] = str(exc)

    return record
