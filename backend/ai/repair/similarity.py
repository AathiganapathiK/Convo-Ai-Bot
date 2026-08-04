import difflib
from typing import List, Optional, Tuple


def normalize(text: str) -> str:
    """Normalize input text by lowercasing and stripping whitespace."""
    return text.strip().lower()


def exact_match(query: str, candidates: List[str]) -> Optional[str]:
    """Find a case-sensitive exact match among candidates."""
    for c in candidates:
        if c == query:
            return c
    return None


def case_match(query: str, candidates: List[str]) -> Optional[str]:
    """Find a case-insensitive match among candidates."""
    query_lower = query.lower()
    for c in candidates:
        if c.lower() == query_lower:
            return c
    return None


def sequence_similarity(a: str, b: str) -> float:
    """Calculate ratio sequence similarity between two strings using difflib."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def rank_candidates(query: str, candidates: List[str]) -> List[Tuple[str, float]]:
    """Rank candidates by their similarity score descending."""
    ranked = []
    for c in candidates:
        if c == query:
            score = 1.0
        elif c.lower() == query.lower():
            score = 0.95
        else:
            score = sequence_similarity(query, c)
        ranked.append((c, score))
    return sorted(ranked, key=lambda x: x[1], reverse=True)


def find_best_match(
    query: str, candidates: List[str], threshold: float = 0.5
) -> Optional[Tuple[str, float]]:
    """Get the candidate with the highest similarity score above a given threshold."""
    if not candidates:
        return None
    ranked = rank_candidates(query, candidates)
    best_candidate, best_score = ranked[0]
    if best_score >= threshold:
        return best_candidate, best_score
    return None
