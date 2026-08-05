from semantic.matching.stopwords import STOPWORDS
from semantic.matching.confidence import MatchSettings

class CandidatePhraseExtractor:
    def __init__(self, max_ngram: int = None):
        self.max_ngram = max_ngram if max_ngram is not None else MatchSettings.MAX_CANDIDATE_NGRAM

    def extract(self, question: str) -> list[str]:
        # Phase 2 — Reuse Existing Normalization via safe local import
        from semantic.dimension_value_resolver import DimensionValueResolver
        normalized = DimensionValueResolver._normalize_text(question)

        # Phase 3 — Reuse Existing Stopwords
        stopwords = STOPWORDS

        # Phase 4 — Tokenize
        tokens = [t for t in normalized.split() if t not in stopwords]

        if not tokens:
            return []

        # Phase 5 — Generate N-grams
        ngrams_list = []
        n = len(tokens)
        for size in range(1, min(self.max_ngram, n) + 1):
            for i in range(n - size + 1):
                ngram = " ".join(tokens[i : i + size])
                ngrams_list.append(ngram)

        # Phase 6 — Remove Duplicates preserving order
        seen = set()
        unique_ngrams = []
        for ng in ngrams_list:
            if ng not in seen:
                seen.add(ng)
                unique_ngrams.append(ng)

        # Phase 7 & 8 — Rank Phrases (longest word count first, stable sort preserves original sequence)
        unique_ngrams.sort(key=lambda x: len(x.split()), reverse=True)

        return unique_ngrams
