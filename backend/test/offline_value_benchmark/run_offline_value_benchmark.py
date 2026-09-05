"""
Offline candidate-scoped benchmark.

Exists because the existing v2 retrieval benchmark CANNOT validate this work:
run_retrieval_benchmark.py calls SemanticResolver.resolve() directly, so
extraction never runs and value_phrases is always None. That benchmark measures
the legacy path and nothing else.

This one drives the new path end to end from a value phrase, against the mock
provider, with no database, no model and no network. It is a measurement, not a
unit test: it prints a score and lists every failure with the reason the case
was written.

    python test/offline_value_benchmark/run_offline_value_benchmark.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(TEST_DIR))
sys.path.insert(0, TEST_DIR)

from fixtures.mock_value_provider import MockDimensionValueProvider  # noqa: E402
from semantic.dimension_value_resolver import DimensionValueResolver  # noqa: E402


class _Phrase:
    def __init__(self, phrase, dimension=None, qualifier_explicit=False):
        self.phrase = phrase
        self.dimension = dimension
        self.qualifier_explicit = qualifier_explicit


def run(verbose=True):
    cases = json.load(open(os.path.join(HERE, "cases.json"), encoding="utf-8"))
    provider = MockDimensionValueProvider()

    results = []
    for case in cases:
        resolutions = DimensionValueResolver.resolve_value_phrases(
            None,
            case["question"],
            [_Phrase(case["phrase"], case["dimension"], case["qualifier_explicit"])],
            provider=provider,
        )

        if not resolutions:
            actual_status, actual_values = "UNRESOLVED", []
        else:
            r = resolutions[0]
            actual_status = r.status
            actual_values = (
                [r.winner.value] if r.status == "RESOLVED" else sorted(r.values)
            )

        expected_values = sorted(case["expect_values"])
        ok = (
            actual_status == case["expect_status"]
            and sorted(actual_values) == expected_values
        )
        results.append((case, ok, actual_status, actual_values))

    passed = sum(1 for _, ok, _, _ in results if ok)

    if verbose:
        for case, ok, status, values in results:
            if ok:
                continue
            print("FAIL %s  %s" % (case["id"], case["question"]))
            print("     expected %s %s" % (case["expect_status"], sorted(case["expect_values"])))
            print("     actual   %s %s" % (status, values))
            print("     intent   %s" % case["why"])
        print("=" * 60)
        print("offline candidate-scoped benchmark: %d/%d" % (passed, len(results)))
        print("=" * 60)

    return passed, len(results), results


if __name__ == "__main__":
    ok, total, _ = run()
    sys.exit(0 if ok == total else 1)
