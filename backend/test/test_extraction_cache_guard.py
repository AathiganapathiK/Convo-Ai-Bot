"""
The extraction cache write guard.

This exists because the loss it prevents already happened twice in one session:
a run during the provider's daily-token cutoff wrote 194 empty extractions over
a cache holding 105 real ones, and a later run salvaged exactly 1 of 194 and
overwrote a cache holding 2 - slipping past the first version of the guard.

No database, no model, no network.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "shadow_harness"))

from run_real_extraction import should_write  # noqa: E402


def cache(with_phrases, empty=0):
    out = {}
    for i in range(with_phrases):
        out["q%d" % i] = [{"phrase": "V%d" % i}]
    for i in range(empty):
        out["e%d" % i] = []
    return out


class TestCacheGuard(unittest.TestCase):

    def test_empty_run_cannot_replace_a_populated_cache(self):
        allowed, reason = should_write(cache(105), cache(0, empty=194))
        self.assertFalse(allowed)
        self.assertIn("105", reason)

    def test_partial_run_cannot_replace_a_better_cache(self):
        """The case that slipped past the first version of this guard."""
        allowed, _ = should_write(cache(2), cache(1, empty=193))
        self.assertFalse(allowed)

    def test_equal_coverage_is_a_legitimate_refresh(self):
        allowed, _ = should_write(cache(105), cache(105))
        self.assertTrue(allowed)

    def test_better_run_is_allowed(self):
        allowed, _ = should_write(cache(105), cache(140))
        self.assertTrue(allowed)

    def test_first_ever_run_is_allowed(self):
        for previous in ({}, None):
            allowed, _ = should_write(previous, cache(3))
            self.assertTrue(allowed)

    def test_empty_run_on_an_empty_cache_is_allowed(self):
        """Nothing to protect; the run is still recorded honestly."""
        allowed, _ = should_write(cache(0, empty=10), cache(0, empty=194))
        self.assertTrue(allowed)

    def test_reason_is_reported_either_way(self):
        for prev, cur in ((cache(5), cache(1)), (cache(1), cache(5))):
            _, reason = should_write(prev, cur)
            self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
