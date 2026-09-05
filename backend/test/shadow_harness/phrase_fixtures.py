"""
Deterministic value-phrase source for the shadow harness.

WHAT THIS IS AND IS NOT

The harness must not call the LLM once per case, so value phrases come from
here instead. This is a STAND-IN for extraction, not a replacement for it, and
that distinction governs how the harness's numbers may be read:

    it measures the RESOLUTION layer, given plausible phrases.
    it does NOT measure extraction quality.

A real number for the whole path needs the real extractor and a real database.
When those are available, `load_cache()` reads a recorded question -> phrases
cache instead and this heuristic is bypassed entirely; the harness takes the
cache whenever one exists.

HOW THE HEURISTIC WORKS, AND WHY IT IS NOT CIRCULAR

It reads only the QUESTION. It never consults the value universe, the expected
answers, or any recorded result, so it cannot manufacture a correct phrase by
peeking at what the answer should be. It takes the span after a preposition and
strips leading question/metric wording. Dimension qualifier words are the real
configured dimension names supplied by the caller - names, never values.

It is crude, and it is meant to be: where it produces no phrase, the harness
reports the case UNMEASURABLE rather than pretending.
"""
import json
import os
import re

# Words that introduce a value span in these questions.
_PREPOSITIONS = ("for", "in", "at", "of", "from")

# Leading wording that is never part of a value.
_LEAD = re.compile(
    r"^(please\s+|kindly\s+|could you\s+|can you\s+|tell me\s+|show me\s+|show\s+|"
    r"give me\s+|list\s+|display\s+|what (is|are|was|were)\s+|which\s+|how much\s+|"
    r"how many\s+|total\s+|the\s+)+",
    re.I,
)

# Trailing wording that is never part of a value.
_TRAIL = re.compile(
    r"\s+(please|now|today|this (year|month|quarter|week)|last (year|month|quarter|week)|"
    r"ytd|so far|breakdown|trend|wise)\b.*$",
    re.I,
)

_STOP_TAIL = ("and", "or", "with", "by", "vs", "versus")


class Phrase:
    """Structural stand-in for ValuePhrase; the resolver reads it by shape."""

    def __init__(self, phrase, dimension=None, qualifier_explicit=False):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit

    def __repr__(self):
        return "Phrase(%r, %r, %s)" % (
            self.phrase, self.dimension, self.qualifier_explicit)


def _split_on_connectors(span: str):
    """'Chennai city and Ramraj brand' -> two spans, never concatenated."""
    parts = re.split(r"\s+(?:and|&)\s+", span, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def derive_phrases(question: str, dimension_names):
    """
    Value phrases for one question, from its wording alone.

    `dimension_names` are the real configured dimension names; a span ending in
    one of them is treated as explicitly qualified, which is the same rule
    Step 2 applies deterministically.
    """
    if not question:
        return []

    text = question.strip()
    lowered = text.lower()

    starts = []
    for prep in _PREPOSITIONS:
        for m in re.finditer(r"\b%s\b" % prep, lowered):
            starts.append(m.end())
    if not starts:
        return []

    span = text[min(starts):].strip()
    span = _TRAIL.sub("", span).strip(" ,.?!")
    if not span:
        return []

    phrases = []
    for part in _split_on_connectors(span):
        part = _LEAD.sub("", part).strip(" ,.?!")
        # Drop a dangling connector left by the split.
        words = part.split()
        while words and words[-1].lower() in _STOP_TAIL:
            words.pop()
        if not words:
            continue

        dimension, qualifier_explicit = None, False
        for name in sorted(dimension_names or [], key=len, reverse=True):
            tokens = name.lower().split()
            if len(words) > len(tokens) and \
                    [w.lower() for w in words[-len(tokens):]] == tokens:
                dimension = name
                qualifier_explicit = True
                words = words[:-len(tokens)]
                break

        if not words:
            continue

        phrases.append(Phrase(" ".join(words), dimension, qualifier_explicit))

    return phrases


def load_cache(path=None):
    """
    A recorded question -> phrases cache, when one exists.

    Format: {"<question>": [{"phrase": ..., "dimension": ..., "qualifier_explicit": ...}]}
    Produced from a real extraction run; preferred over the heuristic whenever
    present, because it is the real extractor's output rather than a stand-in.
    """
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "extraction_cache.json")
    if not os.path.exists(path):
        return {}
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}

    out = {}
    for question, entries in (raw or {}).items():
        out[question] = [
            Phrase(e.get("phrase"), e.get("dimension"), bool(e.get("qualifier_explicit")))
            for e in entries or [] if isinstance(e, dict) and e.get("phrase")
        ]
    return out
