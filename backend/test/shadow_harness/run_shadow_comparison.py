"""
LEGACY vs CANDIDATE_SCOPED, case by case, offline.

WHAT THIS MEASURES

For each of the 190 scored benchmark cases it resolves values twice - once
through the legacy matcher path, once through the candidate-scoped path -
against an IDENTICAL value universe rebuilt from committed benchmark
artifacts. Any difference is therefore a difference in resolution behaviour.

WHAT THIS DOES NOT MEASURE

    * It is NOT the 190/103 benchmark. That needs the real database and the
      real extractor. This number must never be quoted as revalidating it.
    * Value phrases come from a documented heuristic stand-in, not the LLM, so
      extraction quality is out of scope.
    * The value universe holds only values a recorded run resolved, so a case
      whose expected value is absent is reported UNMEASURABLE, not failed.

Buckets: IMPROVED / REGRESSED / UNCHANGED_CORRECT / UNCHANGED_WRONG /
UNMEASURABLE. Only the first two are interesting, and both are listed per case.

    python test/shadow_harness/run_shadow_comparison.py
"""
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(TEST_DIR))
sys.path.insert(0, TEST_DIR)
sys.path.insert(0, HERE)

from shadow_harness import recorded_universe as universe  # noqa: E402
from shadow_harness import phrase_fixtures  # noqa: E402
from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402

GOLDEN = os.path.join(TEST_DIR, "semantic_benchmark", "v2", "golden_dataset_v2_c*.json")


def _cases():
    out = []
    for path in sorted(glob.glob(GOLDEN)):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for case in payload if isinstance(payload, list) else payload.get("cases", []):
            if isinstance(case, dict) and case.get("question"):
                out.append(case)
    return out


def _resolve(mode, question, phrases, index, provider, judge=None):
    """Resolve one question in one mode, with both paths on the same data."""
    previous = os.environ.get("SEMANTIC_VALUE_MODE")
    if mode is None:
        os.environ.pop("SEMANTIC_VALUE_MODE", None)
    else:
        os.environ["SEMANTIC_VALUE_MODE"] = mode

    real_members_of = DimensionValueResolver._members_of
    DimensionValueResolver._members_of = staticmethod(lambda *a, **k: ())
    try:
        resolver = DimensionValueResolver()
        resolver._load_dimension_values = lambda connection_id: index
        matches = resolver.resolve_matches(
            "shadow", question,
            value_phrases=phrases or None,
            value_provider=provider,
            value_judge=judge,
        )
        rr = getattr(resolver, "last_resolution_result", None)
        return {
            "values": sorted({
                m.get("value") for m in (matches or [])
                if isinstance(m, dict) and m.get("value")
            }),
            "dimensions": sorted({
                m.get("business_name") for m in (matches or [])
                if isinstance(m, dict) and m.get("business_name")
            }),
            "status": getattr(getattr(rr, "status", None), "name", None),
        }
    except Exception as exc:
        return {"values": ["<error: %s>" % type(exc).__name__],
                "dimensions": [], "status": "ERROR"}
    finally:
        DimensionValueResolver._members_of = real_members_of
        os.environ.pop("SEMANTIC_VALUE_MODE", None)
        if previous is not None:
            os.environ["SEMANTIC_VALUE_MODE"] = previous


REAL_CONNECTION_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"


def _real_universe():
    """
    The production value index and the production provider.

    Both paths read the same real configuration, so the comparison stays
    like for like - the only difference is which resolution path runs.
    """
    from semantic.dimension_value_resolver import DimensionValueResolver as R
    from semantic.value_provider import DbDimensionValueProvider

    provider = DbDimensionValueProvider(connection_id=REAL_CONNECTION_ID)
    index = R()._load_dimension_values(REAL_CONNECTION_ID)
    known = {v.value for v in index}
    names = sorted({v.business_name for v in index if v.business_name})
    return index, provider, known, names


def _root_cause(expected, legacy, scoped, phrases, legacy_full, scoped_full, known):
    """Where a difference came from. One label per case, most specific first."""
    if not phrases:
        return "extraction: no value phrase"
    if expected and not set(expected) <= known:
        return "candidate retrieval: expected value not in the index"
    if scoped == expected:
        return "resolved correctly"

    phrase_texts = [p[0] for p in phrases]
    if not scoped and legacy:
        # Nothing survived scoring, but the legacy matcher found something.
        return "deterministic scoring: evidence floor refused a legacy match"
    if scoped and not legacy:
        return "deterministic scoring: scored a candidate legacy did not"
    if len(scoped) > len(expected):
        qualified = any(p[2] for p in phrases)
        return ("qualification: no dimension narrowing" if not qualified
                else "ambiguity: competitive set wider than expected")
    if scoped_full.get("status") != legacy_full.get("status"):
        return "ambiguity: status differs"
    if any(w in " ".join(phrase_texts).lower()
           for w in ("previous", "that", "it", "instead", "now")):
        return "context/follow-up"
    return "other"


def run(verbose=True, real=False, judge=None):
    if real:
        index, provider, known, dimension_names = _real_universe()
        label = "REAL production index: %d values, %d dimensions" % (
            len(index), len(dimension_names))
    else:
        index = universe.cached_dimension_values()
        provider = universe.RecordedValueProvider()
        known = {v for values in universe.values_by_dimension().values() for v in values}
        dimension_names = list(universe.values_by_dimension())
        label = universe.summary()
    cache = phrase_fixtures.load_cache()

    buckets = collections.Counter()
    details = []

    for case in _cases():
        question = case["question"]
        expected = sorted(case.get("expected", {}).get("values") or [])

        phrases = cache.get(question)
        if phrases is None:
            phrases = phrase_fixtures.derive_phrases(question, dimension_names)

        legacy_full = _resolve(None, question, phrases, index, provider)
        scoped_full = _resolve("candidate_scoped", question, phrases, index, provider, judge)
        legacy = legacy_full["values"]
        scoped = scoped_full["values"]

        # A case is only judgeable when its expected answer could exist in this
        # universe and a phrase was available to look up.
        if expected and not set(expected) <= known:
            bucket = "UNMEASURABLE"
            why = "expected value absent from the recorded universe"
        elif not phrases:
            bucket = "UNMEASURABLE"
            why = "no value phrase derivable from the question"
        else:
            legacy_ok = legacy == expected
            scoped_ok = scoped == expected
            if scoped_ok and not legacy_ok:
                bucket, why = "IMPROVED", ""
            elif legacy_ok and not scoped_ok:
                bucket, why = "REGRESSED", ""
            elif legacy_ok:
                bucket, why = "UNCHANGED_CORRECT", ""
            else:
                bucket, why = "UNCHANGED_WRONG", ""

        if bucket in ("IMPROVED", "REGRESSED", "UNCHANGED_WRONG"):
            root = _root_cause(expected, legacy, scoped, phrases,
                               legacy_full, scoped_full, known)
        else:
            root = ""

        buckets[bucket] += 1
        details.append({
            "id": case.get("case_id"), "question": question,
            "category": case.get("category"),
            "expected": expected, "legacy": legacy, "scoped": scoped,
            "legacy_dimensions": legacy_full["dimensions"],
            "scoped_dimensions": scoped_full["dimensions"],
            "legacy_status": legacy_full["status"],
            "scoped_status": scoped_full["status"],
            "expected_status": case.get("expected", {}).get("status"),
            "phrases": [(p.phrase, p.dimension, p.qualifier_explicit) for p in phrases],
            "bucket": bucket, "why": why, "root_cause": root,
        })

    if verbose:
        print(label)
        print("phrase source: %s" % ("recorded cache" if cache else "heuristic stand-in"))
        print()
        for row in details:
            if row["bucket"] in ("IMPROVED", "REGRESSED"):
                print("%-10s %-8s %s" % (row["bucket"], row["id"], row["question"]))
                print("           expected %s" % row["expected"])
                print("           legacy   %s" % row["legacy"])
                print("           scoped   %s" % row["scoped"])
                print("           phrases  %s" % row["phrases"])
                print("           dims     legacy=%s scoped=%s" % (
                    row["legacy_dimensions"], row["scoped_dimensions"]))
                print("           status   legacy=%s scoped=%s expected=%s" % (
                    row["legacy_status"], row["scoped_status"], row["expected_status"]))
        print("=" * 66)
        for name in ("IMPROVED", "REGRESSED", "UNCHANGED_CORRECT",
                     "UNCHANGED_WRONG", "UNMEASURABLE"):
            print("%-20s %d" % (name, buckets[name]))
        print("%-20s %d" % ("TOTAL", sum(buckets.values())))
        print("-" * 66)
        print("ROOT CAUSE of every non-correct case:")
        causes = collections.Counter(
            r["root_cause"] for r in details
            if r["root_cause"] and r["root_cause"] != "resolved correctly")
        for name, count in causes.most_common():
            print("  %-58s %d" % (name, count))
        print("=" * 66)
        print("NOT the 190-case benchmark. Resolution layer only, partial value")
        print("universe, heuristic phrases. Does not revalidate 103/190.")

    return buckets, details


if __name__ == "__main__":
    run(real="--real" in sys.argv)
