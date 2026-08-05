import re

class QuestionSanitizer:

    @staticmethod
    def sanitize(question: str) -> str:
        """
        Sanitizes the input question by:
        1. Removing prompt templates and boundary labels.
        2. Collapsing all whitespace and newlines.
        3. Trimming leading/trailing whitespace.
        """
        if not question:
            return ""

        # Standardize newlines
        text = question.replace("\r\n", "\n")

        # Define primary and secondary headers to identify segments
        primary_patterns = [
            r"(?i)(?:^|\n)\s*original\s+question\s*:\s*",
            r"(?i)(?:^|\n)\s*user\s+question\s*:\s*",
            r"(?i)(?:^|\n)\s*question\s*:\s*",
            r"(?i)(?:^|\n)\s*user\s*:\s*"
        ]

        secondary_patterns = [
            r"(?i)(?:^|\n)\s*follow-up\s+question\s*:\s*",
            r"(?i)(?:^|\n)\s*followup\s+question\s*:\s*",
            r"(?i)(?:^|\n)\s*context\s*:\s*",
            r"(?i)(?:^|\n)\s*history\s*:\s*",
            r"(?i)(?:^|\n)\s*conversation\s+history\s*:\s*"
        ]

        # 1. Try to segment text if it has a primary question header
        matched_primary = None
        start_idx = -1
        for pattern in primary_patterns:
            match = re.search(pattern, text)
            if match:
                if start_idx == -1 or match.start() < start_idx:
                    start_idx = match.end()
                    matched_primary = match

        if matched_primary is not None and start_idx != -1:
            # Slice up to the next boundary header (if any)
            end_idx = len(text)
            for pattern in secondary_patterns:
                match = re.search(pattern, text[start_idx:])
                if match:
                    possible_end = start_idx + match.start()
                    if possible_end < end_idx:
                        end_idx = possible_end
            clean_text = text[start_idx:end_idx]
        else:
            # If no primary header was found, check for a secondary header on its own
            matched_secondary = None
            start_idx = -1
            for pattern in secondary_patterns:
                match = re.search(pattern, text)
                if match:
                    if start_idx == -1 or match.start() < start_idx:
                        start_idx = match.end()
                        matched_secondary = match

            if matched_secondary is not None and start_idx != -1:
                clean_text = text[start_idx:]
            else:
                clean_text = text

        # 2. Strip out any leftover label matches
        all_patterns = primary_patterns + secondary_patterns
        for pattern in all_patterns:
            clean_text = re.sub(pattern, " ", clean_text)

        # 3. Collapse whitespace
        clean_text = re.sub(r"\s+", " ", clean_text)

        # 4. Trim
        return clean_text.strip()
