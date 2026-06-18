"""
tests/test_succession.py
========================
Regression tests for the succession-fidelity ordering core. Zero test framework
beyond the standard library (unittest); numpy is the only hard dep. The real-data
smoke also needs pandas and the emitted web/ files, and skips itself otherwise.

  python -m unittest discover -s tests -p "test_*.py"
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import succession  # noqa: E402


class ForbiddenPairs(unittest.TestCase):
    def setUp(self):
        # w0 rises with varying steps; w1 = 1 - w0 (a clean anti-correlated
        # "handoff" shape); w2 rises *with* w0 (correlated, not a handoff).
        w0 = np.array([0, .1, .15, .4, .5, .55, .8, .9, .95, 1.0])
        w1 = 1.0 - w0
        w2 = w0 * 0.5
        self.streams = ["A", "B", "C"]
        self.W = np.column_stack([w0, w1, w2])  # years x streams

    def test_anti_correlated_with_no_transfer_is_forbidden(self):
        forb = succession.forbidden_pairs(self.W, self.streams, pair_transfer={})
        self.assertIn(frozenset((0, 1)), forb, "A/B look like a handoff but none happened")

    def test_real_transfer_lifts_the_forbidding(self):
        pair = {frozenset(("A", "B")): 0.9}  # well above TRANSFER_FRAC of the peak
        forb = succession.forbidden_pairs(self.W, self.streams, pair)
        self.assertNotIn(frozenset((0, 1)), forb, "a real transfer justifies the adjacency")

    def test_correlated_pair_is_not_a_handoff(self):
        forb = succession.forbidden_pairs(self.W, self.streams, pair_transfer={})
        self.assertNotIn(frozenset((0, 2)), forb, "A/C rise together — not a succession")


class Optimize(unittest.TestCase):
    def test_optimizer_satisfies_a_feasible_constraint(self):
        rng = np.random.default_rng(0)
        W = rng.random((40, 6))
        forbidden = {frozenset((0, 1)), frozenset((2, 3))}
        order, viol = succession.optimize(W, forbidden)
        self.assertEqual(viol, 0)
        self.assertEqual(succession.violations(order, forbidden), 0)
        self.assertEqual(sorted(order), list(range(6)), "order is a permutation")

    def test_no_constraint_is_pure_wiggle_minimization(self):
        rng = np.random.default_rng(1)
        W = rng.random((30, 5))
        order, viol = succession.optimize(W, forbidden=set())
        self.assertEqual(viol, 0)
        # the optimized order should not be worse than the inside-out start
        self.assertLessEqual(succession.wiggle(order, W),
                             succession.wiggle(succession.inside_out(W), W) + 1e-9)


class RealDataSmoke(unittest.TestCase):
    """The emitted orders must be free of false-handoff adjacencies."""

    def test_area_lens_order_has_zero_violations(self):
        try:
            import pandas  # noqa: F401
            from reoptimize_orders import (load_global, component_shares,
                                           stream_transfers, mat)
        except Exception as e:  # pandas missing, etc.
            self.skipTest(f"deps/data unavailable: {e}")

        web = ROOT / "web"
        for f in ("facts.js", "totals.js", "orders.js"):
            if not (web / f).exists():
                self.skipTest("emitted web data not present")

        facts = load_global(web / "facts.js", "FACTS")
        totals = load_global(web / "totals.js", "TOTALS")
        streams = load_global(web / "orders.js", "ORDERS")["pop"]
        years = sorted(int(y) for y in facts)
        _, area, _ = component_shares(facts, totals, streams, years)
        pair = stream_transfers(streams)

        W = mat(area, streams, years)
        forb = succession.forbidden_pairs(W, streams, pair)
        order, viol = succession.optimize(W, forb)
        self.assertEqual(viol, 0, "area order still contains a false handoff")
        self.assertEqual(set(order), set(range(len(streams))))


if __name__ == "__main__":
    unittest.main()
