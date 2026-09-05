"""
Runs the offline candidate-scoped benchmark as part of the normal suite.

The benchmark is a measurement with a printed score; this wrapper makes a
regression in it fail CI rather than waiting for someone to run it by hand.
Offline: no database, no model, no network.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "offline_value_benchmark"))

from run_offline_value_benchmark import run  # noqa: E402


class TestOfflineValueBenchmark(unittest.TestCase):

    def test_every_case_matches_its_intended_semantics(self):
        passed, total, results = run(verbose=False)
        failures = [
            "%s %r: expected %s %s, got %s %s"
            % (c["id"], c["question"], c["expect_status"],
               sorted(c["expect_values"]), status, values)
            for c, ok, status, values in results if not ok
        ]
        self.assertEqual(passed, total, "\n".join(failures))

    def test_the_matrix_covers_every_outcome(self):
        _, _, results = run(verbose=False)
        statuses = {c["expect_status"] for c, _, _, _ in results}
        self.assertEqual(statuses, {"RESOLVED", "AMBIGUOUS", "UNRESOLVED"})


if __name__ == "__main__":
    unittest.main()
