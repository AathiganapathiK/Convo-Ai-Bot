import re
from typing import List
from semantic.matching.models import BaseMatcher, MatchingContext, MatchResult, MatchType
from semantic.matching.confidence import MatchConfidence

from semantic.matching.stopwords import STOPWORDS

class SingularPluralMatcher(BaseMatcher):
    match_type = MatchType.SINGULAR_PLURAL

    STOPWORDS = STOPWORDS

    PROTECTED_WORDS = {
        "business", "analysis", "glass", "dress", "class", "mass", "status",
        "species", "series", "focus", "bias", "canvas", "chaos", "lens", "wear"
    }

    IRREGULAR_FORMS = {
        "men": "man",
        "women": "woman",
        "children": "child",
        "people": "person",
        "feet": "foot",
        "teeth": "tooth",
        "mice": "mouse",
    }
    
    IRREGULAR_PLURAL_TO_SINGULAR = IRREGULAR_FORMS
    IRREGULAR_SINGULAR_TO_PLURAL = {v: k for k, v in IRREGULAR_FORMS.items()}
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        if text is None:
            return ""
        text = text.lower().strip()
        text = text.replace("'", "")
        text = re.sub(r"[-_/.]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _to_singular(word: str) -> str:
        word = word.lower().strip()
        
        # 1) Protected words stay unchanged
        if word in SingularPluralMatcher.PROTECTED_WORDS:
            return word
            
        # 2) Regular irregular lookup
        if word in SingularPluralMatcher.IRREGULAR_PLURAL_TO_SINGULAR.values():
            return word
        if word in SingularPluralMatcher.IRREGULAR_PLURAL_TO_SINGULAR:
            return SingularPluralMatcher.IRREGULAR_PLURAL_TO_SINGULAR[word]
            
        # 3) Suffix stripping rules
        if word.endswith("ies") and len(word) > 3:
            word = word[:-3] + "y"
        elif word.endswith("sses") or word.endswith("xes") or word.endswith("shes") or word.endswith("ches"):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 2:
            word = word[:-1]
            
        # Re-check irregular mapping after suffix reduction
        if word in SingularPluralMatcher.IRREGULAR_PLURAL_TO_SINGULAR:
            return SingularPluralMatcher.IRREGULAR_PLURAL_TO_SINGULAR[word]
            
        return word

    @staticmethod
    def _to_plural(word: str) -> str:
        word = word.lower().strip()
        if word in SingularPluralMatcher.IRREGULAR_PLURAL_TO_SINGULAR:
            return word
        if word in SingularPluralMatcher.IRREGULAR_SINGULAR_TO_PLURAL:
            return SingularPluralMatcher.IRREGULAR_SINGULAR_TO_PLURAL[word]
            
        if word.endswith("y") and not (len(word) > 1 and word[-2] in "aeiou"):
            return word[:-1] + "ies"
        if word.endswith("s") or word.endswith("x") or word.endswith("sh") or word.endswith("ch"):
            return word + "es"
        return word + "s"

    @staticmethod
    def _is_sublist(sublist: list, main_list: list) -> bool:
        if not sublist:
            return True
        sub_len = len(sublist)
        for i in range(len(main_list) - sub_len + 1):
            if main_list[i : i + sub_len] == sublist:
                return True
        return False

    @staticmethod
    def matches_tokens(q_singulars: list[str], val_singulars: list[str]) -> bool:
        return SingularPluralMatcher._is_sublist(val_singulars, q_singulars)

    def match(self, context: MatchingContext) -> List[MatchResult]:
        matches = []
        q_singulars = context.question_context.q_singulars
        q_tokens = context.question_context.q_tokens

        for val in context.indexed_values:
            val_singulars = val.runtime_raw_singulars
            if not val_singulars:
                continue
            
            if SingularPluralMatcher.matches_tokens(q_singulars, val_singulars):
                matches.append(MatchResult(
                    matched=True,
                    value=val.value,
                    normalized_value=val.runtime_raw_norm,
                    confidence=MatchConfidence.SINGULAR_PLURAL,
                    match_type=MatchType.SINGULAR_PLURAL,
                    matched_question_tokens=q_tokens,
                    matched_value_tokens=val.runtime_raw_tokens,
                    reason="Morphological singular/plural match",
                    dimension_id=val.semantic_dimension_id,
                    business_name=val.business_name,
                    table_name=val.table_name,
                    column_name=val.column_name
                ))
        return matches

    @staticmethod
    def matches(question: str, value: str) -> MatchResult:
        norm_q = SingularPluralMatcher._normalize_text(question)
        norm_val = SingularPluralMatcher._normalize_text(value)
        
        q_tokens = [t for t in norm_q.split() if t not in STOPWORDS]
        val_tokens = [t for t in norm_val.split() if t not in STOPWORDS]
        
        q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
        val_sing = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
        
        if not val_sing or not q_sing:
            return MatchResult(
                matched=False,
                value=value,
                normalized_value=norm_val,
                confidence=0.0,
                match_type=MatchType.SINGULAR_PLURAL,
                matched_question_tokens=q_tokens,
                matched_value_tokens=val_tokens,
                reason="Empty tokens after filtering"
            )
            
        is_match = SingularPluralMatcher._is_sublist(val_sing, q_sing)
        if is_match:
            return MatchResult(
                matched=True,
                value=value,
                normalized_value=norm_val,
                confidence=MatchConfidence.SINGULAR_PLURAL,
                match_type=MatchType.SINGULAR_PLURAL,
                matched_question_tokens=q_tokens,
                matched_value_tokens=val_tokens,
                reason="Sublist match found after singularization and stopword removal"
            )
            
        return MatchResult(
            matched=False,
            value=value,
            normalized_value=norm_val,
            confidence=0.0,
            match_type=MatchType.SINGULAR_PLURAL,
            matched_question_tokens=q_tokens,
            matched_value_tokens=val_tokens,
            reason="No sublist match found"
        )
