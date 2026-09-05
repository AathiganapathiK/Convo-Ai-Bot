"""
Populate the extraction cache from the REAL extractor, against real config.

Reads ONLY the question text from the golden datasets. It never opens the
`expected` block, so nothing about the intended answer can leak into the
phrases; the cache is the extractor's honest reading of the wording alone.

    python test/shadow_harness/run_real_extraction.py            # all questions
    python test/shadow_harness/run_real_extraction.py --verify   # 6 examples only

Output: test/shadow_harness/extraction_cache.json, which run_shadow_comparison
prefers over its heuristic stand-in whenever present.
"""
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(TEST_DIR))
sys.path.insert(0, TEST_DIR)

from ai.extraction.slot_extractor import extract_intent  # noqa: E402

CONNECTION_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
COMPANY_ID = "FD4925A0-9034-4343-A368-8D20A919DF92"

CACHE = os.path.join(HERE, "extraction_cache.json")
GOLDEN = os.path.join(TEST_DIR, "semantic_benchmark", "v2", "golden_dataset_v2_c*.json")

VERIFY = [
    "Show sales for Chennai city",
    "Show sales for Ramraj brand",
    "Show sales for Chennai city and Ramraj brand",
    "Show sales for Chennai",
    "Show sales for Ramraj",
    "Show pending for Chennai",
]


def questions():
    """Question text only. The expected block is never read."""
    seen, out = set(), []
    for path in sorted(glob.glob(GOLDEN)):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for case in payload if isinstance(payload, list) else payload.get("cases", []):
            q = isinstance(case, dict) and case.get("question")
            if q and q not in seen:
                seen.add(q)
                out.append(q)
    return out


def extract_one(question):
    intent = extract_intent(
        question=question,
        connection_id=CONNECTION_ID,
        company_id=COMPANY_ID,
        history_summary="",
    )
    return [
        {
            "phrase": p.phrase,
            "dimension": p.dimension,
            "qualifier_explicit": bool(p.qualifier_explicit),
            "confidence": p.confidence,
        }
        for p in (intent.value_phrases or [])
    ], intent


def _phrase_count(cache):
    return sum(1 for v in (cache or {}).values() if v)


def should_write(previous, current):
    """
    Whether a finished run may replace the cache. (allowed, reason).

    A run that knows LESS than the cache must not replace it. Two versions of
    this rule have now been tested against reality:

      v1 blocked only a completely empty run. A run during the provider's
         daily-token cutoff salvaged 1 extraction out of 194 and was therefore
         allowed to overwrite a cache holding more - the same data loss the
         guard existed to prevent, one phrase short of being caught.

      v2, here, compares counts. Fewer phrases than the cache already has is
         evidence about the provider, not about the questions.

    Equal counts are allowed through: a re-run that reproduces the same
    coverage is a legitimate refresh.
    """
    had, now = _phrase_count(previous), _phrase_count(current)
    if had and now < had:
        return False, (
            "cache holds %d questions with phrases, this run produced %d. "
            "Check provider health before retrying." % (had, now))
    return True, "%d -> %d questions with phrases" % (had, now)


def main():
    verify_only = "--verify" in sys.argv
    limit = None
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])

    # Resume: keep everything already extracted and only ask about questions
    # that have no phrases yet, so two sessions add up instead of replacing
    # each other.
    cache = {}
    if not verify_only and os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}

    if verify_only:
        targets = VERIFY
    else:
        done = {q for q, v in cache.items() if v}
        targets = [q for q in questions() if q not in done]
        if limit:
            targets = targets[:limit]
        print("%d questions already have phrases; %d to attempt this session"
              % (len(done), len(targets)))

    failures, started = [], time.time()

    for i, question in enumerate(targets, 1):
        try:
            phrases, intent = extract_one(question)
            cache[question] = phrases
            if verify_only:
                print("Q: %s" % question)
                print("   phrases : %s" % [
                    (p["phrase"], p["dimension"], p["qualifier_explicit"]) for p in phrases])
                print("   metrics : %s | dims: %s | tier: %s" % (
                    intent.metric_terms, intent.dimension_terms,
                    intent.escalation_tier.value))
        except Exception as exc:
            failures.append((question, "%s: %s" % (type(exc).__name__, exc)))

        if not verify_only and i % 25 == 0:
            print("  %d/%d (%.0fs)" % (i, len(targets), time.time() - started))

    with_phrases_now = sum(1 for v in cache.values() if v)

    if not verify_only:
        previous = {}
        if os.path.exists(CACHE):
            try:
                previous = json.load(open(CACHE, encoding="utf-8"))
            except Exception:
                previous = {}

        allowed, reason = should_write(previous, cache)
        if not allowed:
            print("REFUSED to overwrite: %s" % reason)
            return

        with open(CACHE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2, ensure_ascii=False)

    with_phrases = sum(1 for v in cache.values() if v)
    print("=" * 60)
    print("questions attempted : %d" % len(targets))
    print("extractions stored  : %d" % len(cache))
    print("with value phrases  : %d" % with_phrases)
    print("failures            : %d" % len(failures))
    print("elapsed             : %.0fs" % (time.time() - started))
    for q, err in failures[:5]:
        print("  FAIL %s -> %s" % (q[:50], err))
    if not verify_only:
        print("written to %s" % CACHE)


if __name__ == "__main__":
    main()
