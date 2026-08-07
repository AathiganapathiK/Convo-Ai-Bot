from typing import List, Optional
from .models import DetectedTimeExpression
from .patterns import TEMPORAL_PATTERNS
from core.logger import debug_print as print

class TimeParser:
    """
    Parser that uses the pattern library to identify temporal expressions
    and extract matching metadata parameters.
    """
    def parse(self, normalized_text: str, tokens: List[str]) -> Optional[DetectedTimeExpression]:
        if not normalized_text:
            return None
            
        for pattern in TEMPORAL_PATTERNS:
            match = pattern.regex.search(normalized_text)
            if match:
                matched_str = match.group(0)
                # Split the matched string into tokens
                matched_tokens = [token.strip() for token in matched_str.split() if token.strip()]
                
                try:
                    metadata = pattern.extractor(match)
                except Exception:
                    metadata = {}
                
                print(
                    "\n========== TEMPORAL PARSER ==========\n"
                    f"Normalized Text : {normalized_text}\n"
                    f"Matched Pattern : {pattern.name}\n"
                    f"Matched Text    : {matched_str}\n"
                    f"Intent          : {pattern.intent_type.name}\n"
                    f"Confidence      : {pattern.confidence:.2f}\n"
                    "===================================="
                )
                return DetectedTimeExpression(
                    text=matched_str,
                    intent=pattern.intent_type,
                    confidence=pattern.confidence,
                    matched_tokens=matched_tokens,
                    metadata=metadata
                )
        print(
            "\n========== TEMPORAL PARSER ==========\n"
            f"Normalized Text : {normalized_text}\n"
            "Matched Pattern : NONE\n"
            "===================================="
        )
        return None
