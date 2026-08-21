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
    "TEMPORAL_QUESTIONS"
}

ALLOWED_SOURCES = {
    "REAL_BUSINESS",
    "REGRESSION",
    "SYNTHETIC_SAFETY"
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
    "must_not"
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
    if not isinstance(case_id, str) or not re.match(r"^E1-[0-9]{3,}$", case_id):
        errors.append(f"Case index {index} ({case_id}): Invalid case_id format. Must match ^E1-[0-9]{{3,}}$")

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

    # 10. Safety check: No SQL or database credentials
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
