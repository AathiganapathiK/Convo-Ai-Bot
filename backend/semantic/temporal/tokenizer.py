import re
from typing import List

class TimeTokenizer:
    """
    Tokenizer for extracting words from user queries.
    Responsibilities:
    - Lowercase
    - Remove punctuation (preserving internal hyphens if needed)
    - Split words
    - Normalize whitespace
    """
    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        
        # Lowercase
        text = text.lower()
        
        # Strip possessive 's (e.g. today's -> today, yesterday's -> yesterday)
        text = re.sub(r"'s\b", "", text)
        
        # Remove punctuation except hyphens/underscores/slashes for date pattern support
        text = re.sub(r"[^\w\s-]", "", text)
        
        # Split words and normalize whitespace
        tokens = [token.strip() for token in text.split() if token.strip()]
        return tokens
