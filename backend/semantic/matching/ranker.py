from typing import List
from semantic.matching.models import MatchResult, MatchType
from semantic.matching.singular_plural_matcher import SingularPluralMatcher

class MatchRanker:
    @staticmethod
    def rank(matches: List[MatchResult], question_tokens: List[str]) -> List[MatchResult]:
        """
        Rank matches by:
        1. Match Type (EXACT > NORMALIZED > SINGULAR_PLURAL > FUZZY)
        2. Coverage (higher is better)
        3. Confidence (higher is better)
        4. Token Distance (smaller is better)
        5. Length Difference (smaller is better)
        6. Alphabetical (ascending)
        """
        def calculate_coverage(m: MatchResult, q_tokens: List[str]) -> float:
            if not q_tokens:
                return 0.0
            q_sing = set(SingularPluralMatcher._to_singular(t) for t in q_tokens)
            v_sing = set(SingularPluralMatcher._to_singular(t) for t in m.matched_value_tokens)
            matched_sing = q_sing.intersection(v_sing)
            return len(matched_sing) / len(q_sing)

        def score_match(m: MatchResult):
            match_type = m.match_type
            type_priority = 0
            if match_type == MatchType.EXACT:
                type_priority = 4
            elif match_type == MatchType.NORMALIZED:
                type_priority = 3
            elif match_type == MatchType.SINGULAR_PLURAL:
                type_priority = 2
            elif match_type == MatchType.FUZZY:
                type_priority = 1
                
            coverage = calculate_coverage(m, question_tokens)
            
            val_tokens = m.matched_value_tokens
            token_distance = abs(len(val_tokens) - len(question_tokens))
            
            # Character-based length difference
            length_diff = abs(len(m.value) - len(" ".join(question_tokens)))
            
            return (
                -type_priority,
                -coverage,
                -m.confidence,
                token_distance,
                length_diff,
                m.value.lower()
            )
            
        return sorted(matches, key=score_match)
