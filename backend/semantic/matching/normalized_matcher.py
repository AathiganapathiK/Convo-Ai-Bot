import re
from typing import List
from semantic.matching.models import BaseMatcher, MatchingContext, MatchResult, MatchType
from semantic.matching.confidence import MatchConfidence

class NormalizedMatcher(BaseMatcher):
    match_type = MatchType.NORMALIZED

    def match(self, context: MatchingContext) -> List[MatchResult]:
        MIN_VALUE_LENGTH = 2
        matches = []
        normalized_question = context.question_context.normalized_question
        q_tokens = context.question_context.q_tokens

        for val in context.indexed_values:
            normalized_value = val.runtime_raw_norm
            if not normalized_value or len(normalized_value.strip()) < MIN_VALUE_LENGTH:
                continue

            pattern = r"\b" + re.escape(normalized_value) + r"\b"
            if re.search(pattern, normalized_question):
                matches.append(MatchResult(
                    matched=True,
                    value=val.value,
                    normalized_value=normalized_value,
                    confidence=MatchConfidence.NORMALIZED,
                    match_type=MatchType.NORMALIZED,
                    matched_question_tokens=q_tokens,
                    matched_value_tokens=val.runtime_raw_tokens,
                    reason="Normalized raw value match in question context",
                    dimension_id=val.semantic_dimension_id,
                    business_name=val.business_name,
                    table_name=val.table_name,
                    column_name=val.column_name
                ))

        return matches
