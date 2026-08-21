from multiprocessing import context
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

        phrases: List[str] = [str(p) for p in self.extractor.extract(
            context.question_context.normalized_question
        )]
        if not phrases:
            return []

        candidate_strings = [val.normalized_value for val in context.indexed_values]
        
        # Dict mapping (semantic_dimension_id, normalized_value) -> (MatchResult, score, phrase)
        best_results = {}

        for phrase in phrases:
            results = process.extract(
                phrase,
                candidate_strings,
                scorer=fuzz.WRatio,
                score_cutoff=cutoff
            )
            for match_str, score, index in results:
                val = context.indexed_values[index]
                
                # Integrate spelling-tolerant token-level quality check
                evidence = self._has_token_level_evidence(phrase, val.value)
                if not evidence["passed"]:
                    continue

                identity = (val.semantic_dimension_id, val.normalized_value.strip().lower())
                
                phrase_tokens = phrase.split()
                norm_val = val.runtime_stored_norm if val.normalized_value else val.runtime_raw_norm
                
                if identity in best_results:
                    existing_mr, existing_score, existing_phrase = best_results[identity]
                    
                    keep_new = False
                    if score > existing_score:
                        keep_new = True
                    elif score == existing_score:
                        new_words = len(phrase_tokens)
                        existing_words = len(existing_phrase.split())
                        if new_words > existing_words:
                            keep_new = True
                        elif new_words < existing_words:
                            keep_new = False
                        else:
                            if len(phrase) > len(existing_phrase):
                                keep_new = True
                            elif len(phrase) < len(existing_phrase):
                                keep_new = False
                            else:
                                new_diff = abs(len(val.normalized_value) - len(phrase))
                                existing_diff = abs(len(val.normalized_value) - len(existing_phrase))
                                if new_diff < existing_diff:
                                    keep_new = True
                                else:
                                    keep_new = False
                    
                    if not keep_new:
                        continue
                
                mr = MatchResult(
                    matched=True,
                    value=val.value,
                    normalized_value=norm_val,
                    confidence=score / 100.0,
                    match_type=MatchType.FUZZY,
                    reason=f"RapidFuzz similarity score {score:.1f}%",
                    matched_question_tokens=phrase_tokens,
                    matched_value_tokens=val.runtime_raw_tokens,
                    dimension_id=val.semantic_dimension_id,
                    business_name=val.business_name,
                    table_name=val.table_name,
                    column_name=val.column_name
                )
                best_results[identity] = (mr, score, phrase)

        return [mr for mr, _, _ in best_results.values()]

    @staticmethod
    def _has_token_level_evidence(
        query_phrase: str,
        candidate_value: str,
        threshold: float = 75.0
    ) -> dict:
        """
        Evaluate whether a fuzzy candidate has legitimate token-level evidence
        rather than merely substring similarity.
        """
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher
        from semantic.matching.stopwords import STOPWORDS
        from semantic.dimension_value_resolver import DimensionValueResolver
        from rapidfuzz import fuzz

        norm_query = DimensionValueResolver._normalize_text(query_phrase)
        norm_candidate = DimensionValueResolver._normalize_text(candidate_value)

        q_tokens = [t for t in norm_query.split() if t not in STOPWORDS]
        c_tokens = norm_candidate.split()

        if not q_tokens or not c_tokens:
            return {
                "passed": False,
                "best_token_similarity": 0.0,
                "matched_query_token": "",
                "matched_candidate_token": ""
            }

        q_singulars = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
        c_singulars = [SingularPluralMatcher._to_singular(t) for t in c_tokens]

        # Generate all pairs of token indices
        pairs = []
        for i, qt in enumerate(q_singulars):
            for j, ct in enumerate(c_singulars):
                pairs.append((i, j, qt, ct))

        # Filter for meaningful pairs (where both tokens have length > 1)
        meaningful_pairs = [
            p for p in pairs
            if len(q_tokens[p[0]]) > 1 and len(c_tokens[p[1]]) > 1
        ]

        # Fallback to all pairs if no meaningful pairs exist
        selected_pairs = meaningful_pairs if meaningful_pairs else pairs

        best_sim = 0.0
        best_q = ""
        best_c = ""

        for i, j, qt, ct in selected_pairs:
            sim = fuzz.ratio(qt, ct)
            if sim > best_sim:
                best_sim = sim
                best_q = q_tokens[i]
                best_c = c_tokens[j]

        # Also compare the full concatenated/spaced-removed versions of singularized tokens
        # to robustly handle spacing differences (e.g., "Ramraj" vs "Ram Raj")
        # only when token counts differ (indicating a spacing/word-splitting typo)
        if len(q_tokens) != len(c_tokens):
            clean_q = "".join(q_singulars)
            clean_c = "".join(c_singulars)
            full_sim = fuzz.ratio(clean_q, clean_c)
            if full_sim > best_sim:
                best_sim = full_sim
                best_q = query_phrase
                best_c = candidate_value

        passed = best_sim >= threshold
        return {
            "passed": passed,
            "best_token_similarity": best_sim,
            "matched_query_token": best_q,
            "matched_candidate_token": best_c
        }

