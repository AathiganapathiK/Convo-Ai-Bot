from typing import List
from rapidfuzz import process, fuzz

from semantic.matching.models import BaseMatcher, MatchingContext, MatchResult, MatchType
from semantic.matching.confidence import MatchSettings

class FuzzyMatcher(BaseMatcher):
    match_type = MatchType.FUZZY

    def __init__(self, extractor=None):
        from semantic.matching.candidate_phrase_extractor import CandidatePhraseExtractor
        self.extractor = extractor or CandidatePhraseExtractor()

    def match(self, context: MatchingContext) -> List[MatchResult]:
        if not context.indexed_values:
            return []

        cutoff = (
            context.settings.get("FUZZY_SCORE_CUTOFF", MatchSettings.FUZZY_SCORE_CUTOFF)
            if context.settings
            else MatchSettings.FUZZY_SCORE_CUTOFF
        )

        phrases = self.extractor.extract(context.question_context.normalized_question)
        if not phrases:
            return []

        candidate_strings = [val.normalized_value for val in context.indexed_values]
        
        best_score = -1.0
        best_match_val = None

        for phrase in phrases:
            results = process.extract(
                phrase,
                candidate_strings,
                scorer=fuzz.WRatio,
                score_cutoff=cutoff
            )
            if results:
                # Sort by score descending, then by character length difference ascending
                sorted_results = sorted(
                    results,
                    key=lambda x: (-x[1], abs(len(x[0]) - len(phrase)))
                )
                match_str, score, index = sorted_results[0]
                if score > best_score:
                    best_score = score
                    best_match_val = context.indexed_values[index]
                elif score == best_score:
                    if best_match_val is not None:
                        existing_diff = abs(len(best_match_val.normalized_value) - len(phrase))
                        new_diff = abs(len(match_str) - len(phrase))
                        if new_diff < existing_diff:
                            best_match_val = context.indexed_values[index]

        if best_match_val:
            norm_val = best_match_val.runtime_stored_norm if best_match_val.normalized_value else best_match_val.runtime_raw_norm
            return [MatchResult(
                matched=True,
                value=best_match_val.value,
                normalized_value=norm_val,
                confidence=best_score / 100.0,
                match_type=MatchType.FUZZY,
                reason=f"RapidFuzz similarity score {best_score:.1f}%",
                matched_question_tokens=context.question_context.q_tokens,
                matched_value_tokens=best_match_val.runtime_raw_tokens,
                dimension_id=best_match_val.semantic_dimension_id,
                business_name=best_match_val.business_name,
                table_name=best_match_val.table_name,
                column_name=best_match_val.column_name
            )]

        return []
