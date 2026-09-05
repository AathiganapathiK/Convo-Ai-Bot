"""
The seam a future LLM candidate judge would plug into. No judge exists yet.

WHY THIS FILE EXISTS NOW

Deciding WHERE a judge may run is an architectural choice and belongs with the
architecture; deciding WHETHER to add one is a later, evidence-based call. The
constraint worth freezing today is the narrow one:

    value phrase
      -> real candidate retrieval        (provider; the only source of values)
      -> deterministic ranking           (scorer; decides RESOLVED/UNRESOLVED)
      -> ONLY genuine remaining ambiguity -> optional judge

A judge may therefore only ever CHOOSE AMONG candidates a provider already
vouched for, and only when deterministic scoring has already declared the
choice genuinely ambiguous. It cannot rescue an UNRESOLVED phrase, cannot
overturn a RESOLVED one, and cannot introduce a value. Those three
prohibitions are enforced in `apply_judge` below rather than left to the
judge's good behaviour, so a badly-behaved implementation degrades to the
deterministic answer instead of corrupting it.

The default is NullCandidateJudge, which abstains. Nothing in this module
calls a model.
"""
from typing import List, Optional

from semantic.candidate_scoring import AMBIGUOUS, RESOLVED, PhraseResolution


class CandidateJudge:
    """
    Chooses among genuinely competitive candidates, or abstains.

    `choose` receives the phrase, the question, and the competitive candidates
    the scorer could not separate. It returns the chosen candidate's value, or
    None to abstain. Returning anything not in `resolution.competitive` is
    treated as abstention.
    """

    def choose(
        self,
        resolution: PhraseResolution,
        question: str,
    ) -> Optional[str]:
        raise NotImplementedError


class NullCandidateJudge(CandidateJudge):
    """The default. Always abstains, so ambiguity is reported to the user."""

    def choose(self, resolution, question):
        return None


JUDGE_PURPOSE = "value_candidate_judge"

# The three answers a judge may give. Anything else is an abstention.
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNRESOLVED = "UNRESOLVED"


def judge_enabled() -> bool:
    """
    Off unless SEMANTIC_VALUE_JUDGE=on, and off by default.

    Separate from SEMANTIC_VALUE_MODE on purpose: the deterministic
    candidate-scoped path must be adoptable without also adopting a second
    model call, and a measurement run needs to switch the judge on alone.
    """
    import os
    return (os.getenv("SEMANTIC_VALUE_JUDGE", "off") or "").strip().lower() == "on"


_PROMPT = """\
A user asked a business question. One phrase in it refers to a value in the
database, and deterministic ranking could not decide which of several REAL
values was meant.

QUESTION
{question}

VALUE PHRASE
{phrase}

DIMENSION THE USER NAMED
{dimension}

CANDIDATE VALUES - these are the ONLY permitted answers. Every one of them
exists in the database. The score is what deterministic ranking gave it.
{candidates}

Reply with JSON and nothing else:

  {{"choice": "<one candidate value exactly as written above>"}}

or, if the question genuinely does not say which was meant:

  {{"choice": "AMBIGUOUS"}}

or, if none of them is what the user meant:

  {{"choice": "UNRESOLVED"}}

RULES
1. Copy a candidate exactly. Do not correct, expand, shorten or reformat it.
2. Never answer with a value that is not in the list, however likely it seems.
3. Prefer AMBIGUOUS over guessing. A wrong confident answer is worse than a
   clarification, because the user cannot tell it was a guess.
"""


class LLMCandidateJudge(CandidateJudge):
    """
    A constrained judge over candidates a provider already vouched for.

    Everything it is shown is real: the question, the extracted phrase, the
    configured dimension, and the candidate values with their deterministic
    scores. It cannot see the database, cannot search, and cannot widen the
    candidate list - it chooses among what it was handed or abstains.

    `invoke` is injectable so the judge is testable without a provider or a
    network; the default path reuses the extraction layer's model caller so
    provider selection, fallback and credentials stay in one place.
    """

    def __init__(self, company_id=None, invoke=None):
        self.company_id = company_id
        self._invoke = invoke
        self.calls = 0
        self.accepted = 0
        self.rejected = 0
        self.abstained = 0

    def _call(self, prompt):
        if self._invoke is not None:
            return self._invoke(JUDGE_PURPOSE, prompt)
        from ai.extraction.slot_extractor import _call_with_fallback
        return _call_with_fallback(JUDGE_PURPOSE, prompt, self.company_id)

    def choose(self, resolution, question):
        self.calls += 1

        listing = "\n".join(
            "- %s   (dimension: %s, score: %.2f)" % (
                s.value, s.dimension, s.score)
            for s in resolution.competitive
        )
        dimension = next(
            (s.dimension for s in resolution.competitive if s.dimension), "not stated")

        prompt = _PROMPT.format(
            question=question or "",
            phrase=resolution.phrase,
            dimension=dimension,
            candidates=listing,
        )

        try:
            raw = self._call(prompt)
        except Exception:
            self.abstained += 1
            return None

        choice = _extract_choice(raw)
        if not choice or choice in (VERDICT_AMBIGUOUS, VERDICT_UNRESOLVED):
            self.abstained += 1
            return None

        # apply_judge re-checks this, but counting it here is what makes
        # "how often did the judge invent something" measurable.
        if choice not in {s.value for s in resolution.competitive}:
            self.rejected += 1
            return None

        self.accepted += 1
        return choice


def _extract_choice(raw):
    """The `choice` string from a model reply, or None."""
    import json
    import re

    if not isinstance(raw, str) or not raw.strip():
        return None

    text = raw.strip()
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            payload = json.loads(match.group(0))
            value = payload.get("choice")
            return value.strip() if isinstance(value, str) else None
        except Exception:
            pass
    return None


def apply_judge(
    resolution: PhraseResolution,
    question: str,
    judge: Optional[CandidateJudge] = None,
) -> PhraseResolution:
    """
    Give a judge the chance to settle one genuinely ambiguous phrase.

    Currently a no-op in every path: `judge_enabled()` is False and the default
    judge abstains. The invariants are implemented now, while they are cheap,
    so that adding a judge later cannot quietly widen its remit:

      * only an AMBIGUOUS resolution is offered to a judge
      * the choice must be one of the candidates already scored competitive
      * an abstention, an unknown value, or an exception leaves the
        deterministic resolution exactly as it was
    """
    if not judge_enabled():
        return resolution

    if resolution.status != AMBIGUOUS or not resolution.competitive:
        return resolution

    judge = judge or NullCandidateJudge()

    try:
        chosen = judge.choose(resolution, question)
    except Exception:
        return resolution

    if not chosen:
        return resolution

    picked = [s for s in resolution.competitive if s.value == chosen]
    if len(picked) != 1:
        # A value the judge invented, or one that maps to several candidates.
        # Neither is a decision this seam is allowed to act on.
        return resolution

    return PhraseResolution(
        phrase=resolution.phrase,
        status=RESOLVED,
        scored=resolution.scored,
        winner=picked[0],
        competitive=picked,
        reason="%s; settled by judge among %d competitive candidates" % (
            resolution.reason, len(resolution.competitive)),
    )


def competitive_candidates(resolutions: List[PhraseResolution]):
    """
    The phrases a judge would be asked about, if one existed.

    Useful on its own: it is the exact set of questions deterministic ranking
    could not settle, which is the evidence needed to decide whether a judge is
    worth adding at all.
    """
    return [r for r in resolutions if r.status == AMBIGUOUS and r.competitive]
