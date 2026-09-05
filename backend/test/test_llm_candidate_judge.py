"""
The constrained LLM candidate judge.

Every test injects `invoke`, so no model is called. What is being tested is not
the model's taste but the cage around it: the judge sees only real candidates,
may answer only with one of them, and every other reply degrades to the
deterministic answer.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fixtures.mock_value_provider import MockDimensionValueProvider  # noqa: E402
from semantic.candidate_judge import (  # noqa: E402
    LLMCandidateJudge,
    apply_judge,
    judge_enabled,
)
from semantic.candidate_scoring import (  # noqa: E402
    AMBIGUOUS,
    RESOLVED,
    UNRESOLVED,
    resolve_phrase,
)
from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402


class _Phrase:
    def __init__(self, phrase, dimension=None, qualifier_explicit=False):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit


def reply(choice):
    return lambda purpose, prompt: json.dumps({"choice": choice})


class JudgeBase(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("SEMANTIC_VALUE_JUDGE")
        os.environ["SEMANTIC_VALUE_JUDGE"] = "on"
        self.provider = MockDimensionValueProvider()

    def tearDown(self):
        os.environ.pop("SEMANTIC_VALUE_JUDGE", None)
        if self._previous is not None:
            os.environ["SEMANTIC_VALUE_JUDGE"] = self._previous

    def ambiguous(self):
        """
        A same-dimension family tie: RAMRAJ vs RAMRAJ PANT/SHIRT/DHOTI.

        Deliberately not the bare-"Chennai" tie. That one has two candidates
        whose VALUE is identical (City CHENNAI and District CHENNAI), so a
        judge answering with the value alone cannot identify one of them - see
        test_cross_dimension_same_value_cannot_be_settled below.
        """
        r = resolve_phrase(
            self.provider.get_candidates(None, "Ramraj"),
            "Ramraj", "Show sales for Ramraj")
        self.assertEqual(r.status, AMBIGUOUS)
        return r


class TestJudgeGating(unittest.TestCase):
    """8. Never consulted when deterministic ranking already decided."""

    def setUp(self):
        os.environ["SEMANTIC_VALUE_JUDGE"] = "on"
        self.provider = MockDimensionValueProvider()

    def tearDown(self):
        os.environ.pop("SEMANTIC_VALUE_JUDGE", None)

    def test_default_is_off(self):
        os.environ.pop("SEMANTIC_VALUE_JUDGE", None)
        self.assertFalse(judge_enabled())

    def test_resolved_phrase_never_calls_the_judge(self):
        judge = LLMCandidateJudge(invoke=reply("MUMBAI"))
        r = resolve_phrase(
            self.provider.get_candidates(None, "Mumbai"),
            "Mumbai", "Show sales for Mumbai")
        self.assertEqual(r.status, RESOLVED)
        apply_judge(r, "Show sales for Mumbai", judge)
        self.assertEqual(judge.calls, 0)

    def test_unresolved_phrase_never_calls_the_judge(self):
        judge = LLMCandidateJudge(invoke=reply("CHENNAI"))
        r = resolve_phrase(
            self.provider.get_candidates(None, "Atlantis"),
            "Atlantis", "Show sales for Atlantis")
        self.assertEqual(r.status, UNRESOLVED)
        apply_judge(r, "q", judge)
        self.assertEqual(judge.calls, 0)


class TestJudgeAnswers(JudgeBase):

    def test_a_valid_candidate_is_accepted(self):
        r = self.ambiguous()
        judge = LLMCandidateJudge(invoke=reply("RAMRAJ PANT"))
        out = apply_judge(r, "Show sales for Ramraj", judge)
        self.assertEqual(out.status, RESOLVED)
        self.assertEqual(out.winner.value, "RAMRAJ PANT")
        self.assertEqual((judge.calls, judge.accepted), (1, 1))

    def test_cross_dimension_same_value_cannot_be_settled(self):
        """
        City CHENNAI and District CHENNAI are two candidates with one value.
        A judge that answers "CHENNAI" has not chosen between them, so the
        seam refuses it and the clarification survives. Settling this needs the
        dimension as well, which today's contract does not carry.
        """
        r = resolve_phrase(
            self.provider.get_candidates(None, "Chennai"),
            "Chennai", "Show sales for Chennai")
        self.assertEqual(r.status, AMBIGUOUS)
        judge = LLMCandidateJudge(invoke=reply("CHENNAI"))
        self.assertEqual(apply_judge(r, "q", judge).status, AMBIGUOUS)

    def test_ambiguous_verdict_leaves_ambiguity(self):
        r = self.ambiguous()
        judge = LLMCandidateJudge(invoke=reply("AMBIGUOUS"))
        out = apply_judge(r, "q", judge)
        self.assertEqual(out.status, AMBIGUOUS)
        self.assertEqual(judge.abstained, 1)

    def test_unresolved_verdict_leaves_ambiguity(self):
        r = self.ambiguous()
        judge = LLMCandidateJudge(invoke=reply("UNRESOLVED"))
        out = apply_judge(r, "q", judge)
        self.assertEqual(out.status, AMBIGUOUS)
        self.assertEqual(judge.abstained, 1)

    def test_invented_candidate_is_rejected(self):
        r = self.ambiguous()
        judge = LLMCandidateJudge(invoke=reply("BENGALURU"))
        out = apply_judge(r, "q", judge)
        self.assertEqual(out.status, AMBIGUOUS)
        self.assertEqual((judge.rejected, judge.accepted), (1, 0))

    def test_reformatted_candidate_is_rejected(self):
        """'Ramraj Pant' is not 'RAMRAJ PANT'. Copy exactly or abstain."""
        r = self.ambiguous()
        judge = LLMCandidateJudge(invoke=reply("Ramraj Pant"))
        out = apply_judge(r, "q", judge)
        self.assertEqual(out.status, AMBIGUOUS)
        self.assertEqual(judge.rejected, 1)

    def test_malformed_reply_abstains(self):
        for raw in ("", "no json here", "{broken", None):
            r = self.ambiguous()
            judge = LLMCandidateJudge(invoke=lambda p, q, raw=raw: raw)
            self.assertEqual(apply_judge(r, "q", judge).status, AMBIGUOUS)

    def test_model_exception_abstains(self):
        def boom(purpose, prompt):
            raise RuntimeError("provider down")
        r = self.ambiguous()
        judge = LLMCandidateJudge(invoke=boom)
        self.assertEqual(apply_judge(r, "q", judge).status, AMBIGUOUS)


class TestJudgeInputs(JudgeBase):
    """7. The judge sees only what it is allowed to see."""

    def test_prompt_carries_only_real_candidates(self):
        seen = {}

        def capture(purpose, prompt):
            seen["prompt"] = prompt
            return json.dumps({"choice": "AMBIGUOUS"})

        r = self.ambiguous()
        apply_judge(r, "Show sales for Ramraj", LLMCandidateJudge(invoke=capture))
        prompt = seen["prompt"]

        self.assertIn("Show sales for Ramraj", prompt)
        for candidate in r.competitive:
            self.assertIn(candidate.value, prompt)
            self.assertIn(candidate.dimension, prompt)
        # No database reach-through: a real value that is NOT among these
        # candidates must not appear in the prompt at all.
        self.assertNotIn("CHENNAI", prompt)
        self.assertNotIn("MUMBAI", prompt)


class TestJudgeThroughResolution(JudgeBase):
    """The seam as the resolver actually calls it."""

    def test_judge_settles_ambiguity_end_to_end(self):
        judge = LLMCandidateJudge(invoke=reply("RAMRAJ PANT"))
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Ramraj", [_Phrase("Ramraj")],
            provider=self.provider, judge=judge)
        self.assertEqual(resolutions[0].status, RESOLVED)
        self.assertEqual(judge.accepted, 1)

    def test_judge_is_not_called_for_each_resolved_phrase(self):
        judge = LLMCandidateJudge(invoke=reply("MUMBAI"))
        DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Mumbai and Ramraj brand",
            [_Phrase("Mumbai"), _Phrase("Ramraj", "Brand", True)],
            provider=self.provider, judge=judge)
        self.assertEqual(judge.calls, 0)

    def test_no_judge_supplied_is_a_no_op(self):
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None, "Show sales for Ramraj", [_Phrase("Ramraj")],
            provider=self.provider)
        self.assertEqual(resolutions[0].status, AMBIGUOUS)


if __name__ == "__main__":
    unittest.main()
