import os
import sys
import json
import re

ALLOWED_CATEGORIES = {
    "SIMPLE_METRIC",
    "METRIC_DIMENSION_VALUE",
    "EXPLICIT_DIMENSION",
    "MULTI_DIMENSION",
    "AMBIGUOUS_VALUES",
    "PARTIAL_COVERAGE",
    "SINGULAR_PLURAL",
    "TYPO_FUZZY",
    "FOLLOW_UP",
    "METRIC_SHIFT",
    "ENTITY_TOPIC_SHIFT",
    "NO_MATCH_ADVERSARIAL",
    "TEMPORAL_QUESTIONS",
    "KPI_BUSINESS_QUESTION"
}

ALLOWED_SOURCES = {
    "REAL_BUSINESS",
    "REGRESSION",
    "SYNTHETIC_SAFETY",
    "KPI_LIBRARY"
}

# Two case_id families: retrieval benchmark cases (E1-001...) and KPI Prompt Library
# Sales cases, which keep the spreadsheet's own ids so they stay traceable to source.
CASE_ID_PATTERN = r"^(E1-[0-9]{3,}|SAL-(USE|MAN|HOD|CXO)-[0-9]{2})$"

ALLOWED_MODES = {
    "DESCRIPTIVE",
    "COMPARISON",
    "TREND",
    "RANKING",
    "DIAGNOSTIC",
    "PRESCRIPTIVE"
}

ALLOWED_GRAINS = {"DAY", "WEEK", "MONTH", "QUARTER", "YEAR"}

ALLOWED_OUTPUT_FORMATS = {"kpi", "table", "chart", "narrative"}

ALLOWED_DIRECTIONS = {"ASC", "DESC"}

ALLOWED_ANSWERABLE = {"yes", "partial", "no"}

ALLOWED_PLAN_FIELDS = {
    "mode",
    "metric",
    "entity",
    "filters",
    "time",
    "ranking",
    "output",
    "diagnostic",
    "assumptions_expected"
}

ALLOWED_SEVERITIES = {
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW"
}

ALLOWED_STATUSES = {
    "NO_MATCH",
    "SINGLE_MATCH",
    "WEAK_AMBIGUITY",
    "STRONG_AMBIGUITY",
    "PARTIAL_MATCH"
}

REQUIRED_CASE_FIELDS = {
    "case_id",
    "category",
    "source",
    "severity",
    "question",
    "conversation",
    "datasource_ref",
    "expected",
    "notes"
}

ALLOWED_CASE_FIELDS = REQUIRED_CASE_FIELDS | {
    "allowed_variations",
    "must_not",
    "expected_plan",
    "data_answerable",
    "missing_data"
}

REQUIRED_EXPECTED_FIELDS = {
    "metrics",
    "dimensions",
    "values",
    "status",
    "retrieval_status",
    "followup_context_applied"
}

ALLOWED_EXPECTED_FIELDS = REQUIRED_EXPECTED_FIELDS | {
    "dominant_candidate",
    "implementation_status",
    "retrieval_status"
}


def validate_case(case: dict, seen_ids: set, index: int = 0) -> list[str]:
    errors = []
    
    # 1. Check for extra/unsupported fields
    extra_fields = set(case.keys()) - ALLOWED_CASE_FIELDS
    if extra_fields:
        errors.append(f"Case index {index}: Unsupported extra fields {sorted(list(extra_fields))}")

    # 2. Check required fields
    missing_fields = REQUIRED_CASE_FIELDS - set(case.keys())
    if missing_fields:
        errors.append(f"Case index {index}: Missing required fields {sorted(list(missing_fields))}")
        return errors

    case_id = case.get("case_id", "")
    if not isinstance(case_id, str) or not re.match(CASE_ID_PATTERN, case_id):
        errors.append(f"Case index {index} ({case_id}): Invalid case_id format. Must match {CASE_ID_PATTERN}")

    if case_id in seen_ids:
        errors.append(f"Case index {index}: Duplicate case_id '{case_id}'")
    else:
        seen_ids.add(case_id)

    # 3. Category validation
    category = case.get("category")
    if category not in ALLOWED_CATEGORIES:
        errors.append(f"Case {case_id}: Invalid category '{category}'. Allowed: {sorted(list(ALLOWED_CATEGORIES))}")

    # 4. Source validation
    source = case.get("source")
    if source not in ALLOWED_SOURCES:
        errors.append(f"Case {case_id}: Invalid source '{source}'. Allowed: {sorted(list(ALLOWED_SOURCES))}")

    # 5. Severity validation
    severity = case.get("severity")
    if severity not in ALLOWED_SEVERITIES:
        errors.append(f"Case {case_id}: Invalid severity '{severity}'. Allowed: {sorted(list(ALLOWED_SEVERITIES))}")

    # 6. Question validation
    question = case.get("question")
    if not isinstance(question, str) or not question.strip():
        errors.append(f"Case {case_id}: Question must be a non-empty string")

    # 7. Conversation validation
    conversation = case.get("conversation")
    if not isinstance(conversation, list):
        errors.append(f"Case {case_id}: Conversation must be a list")
    else:
        for turn_idx, turn in enumerate(conversation):
            if not isinstance(turn, dict):
                errors.append(f"Case {case_id}: Conversation turn {turn_idx} must be an object")
                continue
            turn_keys = set(turn.keys())
            if turn_keys != {"turn", "question"}:
                errors.append(f"Case {case_id}: Turn {turn_idx} keys must be exactly ['turn', 'question'], got {sorted(list(turn_keys))}")
            if not isinstance(turn.get("turn"), int) or turn.get("turn", 0) < 1:
                errors.append(f"Case {case_id}: Turn {turn_idx} 'turn' must be an integer >= 1")
            if not isinstance(turn.get("question"), str) or not turn.get("question", "").strip():
                errors.append(f"Case {case_id}: Turn {turn_idx} 'question' must be a non-empty string")

    # 8. Datasource ref safety validation
    datasource_ref = case.get("datasource_ref")
    if not isinstance(datasource_ref, str) or not datasource_ref.strip():
        errors.append(f"Case {case_id}: datasource_ref must be a non-empty string")
    elif re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", datasource_ref):
        errors.append(f"Case {case_id}: datasource_ref contains physical GUID '{datasource_ref}'. Must use logical label (e.g. 'Chatbot')")

    # 9. Expected semantic result validation
    expected = case.get("expected")
    if not isinstance(expected, dict):
        errors.append(f"Case {case_id}: 'expected' must be an object")
    else:
        exp_extra = set(expected.keys()) - ALLOWED_EXPECTED_FIELDS
        if exp_extra:
            errors.append(f"Case {case_id}: 'expected' has unsupported fields {sorted(list(exp_extra))}")

        exp_missing = REQUIRED_EXPECTED_FIELDS - set(expected.keys())
        if exp_missing:
            errors.append(f"Case {case_id}: 'expected' missing required fields {sorted(list(exp_missing))}")

        if not isinstance(expected.get("metrics"), list):
            errors.append(f"Case {case_id}: 'expected.metrics' must be a list")
        if not isinstance(expected.get("dimensions"), list):
            errors.append(f"Case {case_id}: 'expected.dimensions' must be a list")
        if not isinstance(expected.get("values"), list):
            errors.append(f"Case {case_id}: 'expected.values' must be a list")

        # Validation of implementation_status
        impl_status = expected.get("implementation_status", "CURRENTLY_IMPLEMENTED")
        if impl_status not in {"CURRENTLY_IMPLEMENTED", "FUTURE_PHASE"}:
            errors.append(f"Case {case_id}: Invalid expected.implementation_status '{impl_status}'. Allowed: ['CURRENTLY_IMPLEMENTED', 'FUTURE_PHASE']")
        
        # Validation of status
        status = expected.get("status")
        if impl_status == "CURRENTLY_IMPLEMENTED":
            if status not in ALLOWED_STATUSES:
                errors.append(f"Case {case_id}: status must be a valid ResolutionStatus when CURRENTLY_IMPLEMENTED (got '{status}')")
        elif impl_status == "FUTURE_PHASE":
            if status is not None and status not in ALLOWED_STATUSES:
                errors.append(f"Case {case_id}: status must be a valid ResolutionStatus or null when FUTURE_PHASE (got '{status}')")
                
        # Validation of retrieval_status
        ret_status = expected.get("retrieval_status")
        if "retrieval_status" not in expected:
            errors.append(f"Case {case_id}: 'expected' missing required field 'retrieval_status'")
        else:
            if impl_status == "CURRENTLY_IMPLEMENTED":
                if ret_status not in {"COMPLETE", "PARTIAL", "INSUFFICIENT"}:
                    errors.append(f"Case {case_id}: Invalid expected.retrieval_status '{ret_status}' for CURRENTLY_IMPLEMENTED. Allowed: ['COMPLETE', 'PARTIAL', 'INSUFFICIENT']")
            elif impl_status == "FUTURE_PHASE":
                if ret_status is not None and ret_status not in {"COMPLETE", "PARTIAL", "INSUFFICIENT"}:
                    errors.append(f"Case {case_id}: Invalid expected.retrieval_status '{ret_status}' for FUTURE_PHASE. Allowed: ['COMPLETE', 'PARTIAL', 'INSUFFICIENT', None]")

        if not isinstance(expected.get("followup_context_applied"), bool):
            errors.append(f"Case {case_id}: 'expected.followup_context_applied' must be a boolean")

    # 10. data_answerable / missing_data validation
    answerable = case.get("data_answerable")
    if "data_answerable" in case:
        if answerable not in ALLOWED_ANSWERABLE:
            errors.append(f"Case {case_id}: Invalid data_answerable '{answerable}'. Allowed: {sorted(list(ALLOWED_ANSWERABLE))}")

    missing_data = case.get("missing_data")
    if "missing_data" in case:
        if not isinstance(missing_data, list) or not all(isinstance(m, str) for m in missing_data):
            errors.append(f"Case {case_id}: 'missing_data' must be a list of strings")

    # A case the live data cannot answer must say what is missing, otherwise the
    # answerability tag is an unactionable dead end.
    if answerable in {"partial", "no"} and not missing_data:
        errors.append(f"Case {case_id}: data_answerable='{answerable}' requires a non-empty 'missing_data' list")
    if answerable == "yes" and missing_data:
        errors.append(f"Case {case_id}: data_answerable='yes' must not declare 'missing_data'")

    # 11. expected_plan validation
    plan = case.get("expected_plan")
    if "expected_plan" in case:
        if not isinstance(plan, dict):
            errors.append(f"Case {case_id}: 'expected_plan' must be an object")
        else:
            plan_extra = set(plan.keys()) - ALLOWED_PLAN_FIELDS
            if plan_extra:
                errors.append(f"Case {case_id}: 'expected_plan' has unsupported fields {sorted(list(plan_extra))}")

            if plan.get("mode") not in ALLOWED_MODES:
                errors.append(f"Case {case_id}: 'expected_plan.mode' must be one of {sorted(list(ALLOWED_MODES))} (got '{plan.get('mode')}')")

            metric = plan.get("metric")
            if metric is not None and not isinstance(metric, str):
                errors.append(f"Case {case_id}: 'expected_plan.metric' must be a string or null")

            entity = plan.get("entity")
            if entity is not None:
                if not isinstance(entity, dict):
                    errors.append(f"Case {case_id}: 'expected_plan.entity' must be an object or null")
                else:
                    ent_extra = set(entity.keys()) - {"dimension", "value", "resolved_id"}
                    if ent_extra:
                        errors.append(f"Case {case_id}: 'expected_plan.entity' has unsupported fields {sorted(list(ent_extra))}")

            filters = plan.get("filters")
            if filters is not None:
                if not isinstance(filters, list):
                    errors.append(f"Case {case_id}: 'expected_plan.filters' must be a list")
                else:
                    for f_idx, filt in enumerate(filters):
                        if not isinstance(filt, dict):
                            errors.append(f"Case {case_id}: filter {f_idx} must be an object")
                            continue
                        if set(filt.keys()) - {"field", "op", "value"}:
                            errors.append(f"Case {case_id}: filter {f_idx} keys must be within ['field', 'op', 'value']")
                        if not isinstance(filt.get("field"), str) or not isinstance(filt.get("op"), str):
                            errors.append(f"Case {case_id}: filter {f_idx} 'field' and 'op' must be strings")

            time_slot = plan.get("time")
            if time_slot is not None:
                if not isinstance(time_slot, dict):
                    errors.append(f"Case {case_id}: 'expected_plan.time' must be an object or null")
                else:
                    t_extra = set(time_slot.keys()) - {"period", "grain", "comparison_period"}
                    if t_extra:
                        errors.append(f"Case {case_id}: 'expected_plan.time' has unsupported fields {sorted(list(t_extra))}")
                    grain = time_slot.get("grain")
                    if grain is not None and grain not in ALLOWED_GRAINS:
                        errors.append(f"Case {case_id}: 'expected_plan.time.grain' must be one of {sorted(list(ALLOWED_GRAINS))} or null (got '{grain}')")

            ranking = plan.get("ranking")
            if ranking is not None:
                if not isinstance(ranking, dict):
                    errors.append(f"Case {case_id}: 'expected_plan.ranking' must be an object or null")
                else:
                    r_extra = set(ranking.keys()) - {"top_n", "direction"}
                    if r_extra:
                        errors.append(f"Case {case_id}: 'expected_plan.ranking' has unsupported fields {sorted(list(r_extra))}")
                    top_n = ranking.get("top_n")
                    if top_n is not None and (not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1):
                        errors.append(f"Case {case_id}: 'expected_plan.ranking.top_n' must be a positive integer or null")
                    direction = ranking.get("direction")
                    if direction is not None and direction not in ALLOWED_DIRECTIONS:
                        errors.append(f"Case {case_id}: 'expected_plan.ranking.direction' must be ASC, DESC or null (got '{direction}')")

            output = plan.get("output")
            if output is not None:
                if not isinstance(output, dict):
                    errors.append(f"Case {case_id}: 'expected_plan.output' must be an object or null")
                else:
                    o_extra = set(output.keys()) - {"format", "chart_type"}
                    if o_extra:
                        errors.append(f"Case {case_id}: 'expected_plan.output' has unsupported fields {sorted(list(o_extra))}")
                    fmt = output.get("format")
                    if fmt is not None and fmt not in ALLOWED_OUTPUT_FORMATS:
                        errors.append(f"Case {case_id}: 'expected_plan.output.format' must be one of {sorted(list(ALLOWED_OUTPUT_FORMATS))} or null (got '{fmt}')")

            diagnostic = plan.get("diagnostic")
            if diagnostic is not None:
                if not isinstance(diagnostic, dict):
                    errors.append(f"Case {case_id}: 'expected_plan.diagnostic' must be an object or null")
                else:
                    d_extra = set(diagnostic.keys()) - {"candidate_dimensions", "steps"}
                    if d_extra:
                        errors.append(f"Case {case_id}: 'expected_plan.diagnostic' has unsupported fields {sorted(list(d_extra))}")
                    for key in ("candidate_dimensions", "steps"):
                        val = diagnostic.get(key)
                        if val is not None and (not isinstance(val, list) or not all(isinstance(v, str) for v in val)):
                            errors.append(f"Case {case_id}: 'expected_plan.diagnostic.{key}' must be a list of strings")

            assumptions = plan.get("assumptions_expected")
            if assumptions is not None:
                if not isinstance(assumptions, list) or not all(isinstance(a, str) for a in assumptions):
                    errors.append(f"Case {case_id}: 'expected_plan.assumptions_expected' must be a list of strings")

    # A RANKING plan without a ranking slot is almost always an annotation slip.
    if isinstance(plan, dict) and plan.get("mode") == "RANKING" and not plan.get("ranking"):
        errors.append(f"Case {case_id}: mode RANKING requires a 'ranking' slot with top_n and/or direction")

    # Likewise a DIAGNOSTIC plan with nothing to decompose over.
    if isinstance(plan, dict) and plan.get("mode") == "DIAGNOSTIC":
        diag = plan.get("diagnostic")
        if not isinstance(diag, dict) or not diag.get("candidate_dimensions"):
            errors.append(f"Case {case_id}: mode DIAGNOSTIC requires a 'diagnostic' slot with candidate_dimensions")

    # KPI library cases are plan-scoped by definition; catch a missed annotation.
    if case.get("source") == "KPI_LIBRARY":
        if "expected_plan" not in case:
            errors.append(f"Case {case_id}: source KPI_LIBRARY requires an 'expected_plan'")
        if "data_answerable" not in case:
            errors.append(f"Case {case_id}: source KPI_LIBRARY requires a 'data_answerable' tag")

    # 12. Safety check: No SQL or database credentials
    case_str = json.dumps(case).lower()
    if "select " in case_str and "from " in case_str:
        errors.append(f"Case {case_id}: SQL queries detected in case definition. SQL is forbidden in golden dataset")
    
    cred_keywords = ["password", "pwd=", "uid=", "database_url", "odbc_connect", "secret"]
    for cred in cred_keywords:
        if cred in case_str:
            errors.append(f"Case {case_id}: Potential credential keyword '{cred}' detected in case definition")

    return errors


def validate_dataset_file(filepath: str) -> tuple[bool, list[str]]:
    if not os.path.exists(filepath):
        return False, [f"File not found: {filepath}"]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"JSON Syntax Error in {filepath}: {str(e)}"]

    if isinstance(data, dict):
        cases = [data]
    elif isinstance(data, list):
        cases = data
    else:
        return False, [f"Root structure in {filepath} must be a list of case objects or a single case object"]

    all_errors = []
    seen_ids = set()
    seen_questions = set()

    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            all_errors.append(f"Item at index {idx} is not a valid JSON object")
            continue
        errs = validate_case(case, seen_ids, idx)
        all_errors.extend(errs)

        q_norm = case.get("question", "").strip().lower()
        if q_norm:
            if q_norm in seen_questions:
                all_errors.append(f"Case index {idx} ({case.get('case_id')}): Duplicate question '{case.get('question')}' detected")
            else:
                seen_questions.add(q_norm)

    is_valid = len(all_errors) == 0
    return is_valid, all_errors


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = os.path.join(os.path.dirname(__file__), "golden_dataset_examples.json")

    print(f"==================================================")
    print(f"VALIDATING GOLDEN BENCHMARK DATASET: {target}")
    print(f"==================================================")

    valid, errors = validate_dataset_file(target)
    if valid:
        print("VALIDATION SUCCESSFUL: All golden cases adhere strictly to the schema contract!")
        sys.exit(0)
    else:
        print(f"VALIDATION FAILED with {len(errors)} errors:")
        for e in errors:
            print(f" - {e}")
        sys.exit(1)
