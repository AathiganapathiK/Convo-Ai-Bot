import re
from typing import List

class TimeNormalizer:
    """
    Normalizer to convert equivalent temporal expressions into a common form.
    Examples:
    - "last five years" -> "past 5 years"
    - "previous year" -> "last year"
    - "current year" -> "this year"
    """
    NUMBER_MAP = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
        "thirteen": "13",
        "fourteen": "14",
        "fifteen": "15",
        "sixteen": "16",
        "seventeen": "17",
        "eighteen": "18",
        "nineteen": "19",
        "twenty": "20",
        "thirty": "30",
        "forty": "40",
        "fifty": "50",
        "sixty": "60",
        "seventy": "70",
        "eighty": "80",
        "ninety": "90"
    }

    def normalize(self, tokens: List[str]) -> str:
        if not tokens:
            return ""
        
        # Join tokens back into a space-separated string
        text = " ".join(tokens)
        
        # Convert number words to digits using word boundaries
        for word, digit in self.NUMBER_MAP.items():
            text = re.sub(r"\b" + word + r"\b", digit, text)
            
        # Normalize "last N [period]s" -> "past N [period]s"
        # e.g., "last 5 years" -> "past 5 years"
        # e.g., "last 12 months" -> "past 12 months"
        text = re.sub(
            r"\blast\b\s+(\d+)\s+(year|month|week|day|years|months|weeks|days)\b",
            r"past \1 \2",
            text
        )
        
        # Normalize "previous [period]" -> "last [period]"
        # e.g., "previous year" -> "last year", "previous month" -> "last month"
        text = re.sub(
            r"\bprevious\b\s+(year|month|week|day|quarter)\b",
            r"last \1",
            text
        )
        
        # Normalize "current [period]" -> "this [period]"
        # e.g., "current year" -> "this year", "current month" -> "this month"
        text = re.sub(
            r"\bcurrent\b\s+(year|month|week|day|quarter)\b",
            r"this \1",
            text
        )
        
        # Normalize multiple spaces
        text = re.sub(r"\s+", " ", text).strip()
        
        return text
