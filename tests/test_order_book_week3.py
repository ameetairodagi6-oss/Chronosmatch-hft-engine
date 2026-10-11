"""
test_order_book_week3.py
-------------------------
Week 3 tests for the C-level matching engine.

  1. Differential test: the C engine must behave exactly like a simple,
     obviously-correct reference model on thousands of random orders.
  2. Fast-path API (submit_order_fast / trade_at).
  3. Capacity growth (more resting orders than the initial C array holds).
  4. Latency metrics are recorded.
  5. The garbage collector does not run while orders are being matched.

order_book.pyx must be compiled first:
    cd engine
    python setup.py build_ext --inplace

Run with:
    python tests/test_order_book_week3.py
"""

import gc
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from order_book import LimitOrderBook


class ReferenceBook:
    """
    A deliberately simple Price-Time Priority book using plain Python lists.

    Slow but easy to verify by eye. The C engine is checked against it.
    Each resting order is [price, seq, order_id, quantity].
    """

    def __init__(self):
        self.bids = []
        self.asks = []
        self.seq = 0

    def submit(self, order_id, side, price, quantity):
        self.seq += 1
        trades = []
        if side == "B":
            while quantity > 0 and self.asks and self.asks[0][0] <= price:
                rest = self.asks[0]
                q = min(quantity, rest[3])
                trades.append((order_id, rest[2], rest[0], q))
                quantity -= q
                rest[3] -= q
                if rest[3] == 0:
                    self.asks.pop(0)
            if quantity > 0:
                self.bids.append([price, self.seq, order_id, quantity])
                # best bid first: highest price, then earliest arrival
                self.bids.sort(key=lambda o: (-o[0], o[1]))
        else:
            while quantity > 0 and self.bids and self.bids[0][0] >= price:
                rest = self.bids[0]
                q = min(quantity, rest[3])
                trades.append((rest[2], order_id, rest[0], q))
                quantity -= q
                rest[3] -= q
                if rest[3] == 0:
                    self.bids.pop(0)
            if quantity > 0:
                self.asks.append([price, self.seq, order_id, quantity])
                # best ask first: lowest price, then earliest arrival
                self.asks.sort(key=lambda o: (o[0], o[1]))
        return trades


def book_state(lob):
    """The engine's resting orders as comparable tuples, best first."""
    bids = [(o.order_id, o.price, o.quantity) for o in lob.bids]
    asks = [(o.order_id, o.price, o.quantity) for o in lob.asks]
    return bids, asks


def ref_state(ref):
    bids = [(o[2], o[0], o[3]) for o in ref.bids]
    asks = [(o[2], o[0], o[3]) for o in ref.asks]
    return bids, asks


class TestAgainstReferenceModel(unittest.TestCase):
    def run_random(self, seed, n_orders, price_levels, max_qty):
        rng = random.Random(seed)
        lob = LimitOrderBook()
        ref = ReferenceBook()

        for order_id in range(n_orders):
            side = rng.choice(["B", "S"])
            # A small price grid forces many ties and many partial fills.
            price = 100.0 + rng.randrange(price_levels) * 0.5
            qty = rng.randint(1, max_qty)

            got = [(t.buy_order_id, t.sell_order_id, t.price, t.quantity)
                   for t in lob.submit_order(order_id, side, price, qty)]
            want = ref.submit(order_id, side, price, qty)
            self.assertEqual(got, want, f"trades differ at order {order_id}")

            # Compare the full book periodically (comparing every step is slow).
            if order_id % 250 == 0:
                self.assertEqual(book_state(lob), ref_state(ref),
                                 f"book differs at order {order_id}")

        self.assertEqual(book_state(lob), ref_state(ref))

    def test_tight_price_grid_many_ties(self):
        self.run_random(seed=1, n_orders=6000, price_levels=5, max_qty=20)

    def test_wide_price_grid(self):
        self.run_random(seed=2, n_orders=6000, price_levels=40, max_qty=100)

    def test_large_orders_sweep_levels(self):
        self.run_random(seed=3, n_orders=4000, price_levels=10, max_qty=500)


class TestFastPath(unittest.TestCase):
    def test_returns_trade_count_and_trade_at(self):
        lob = LimitOrderBook()
        self.assertEqual(lob.submit_order_fast(1, False, 100.0, 5), 0)   # Sell rests
        self.assertEqual(lob.submit_order_fast(2, False, 101.0, 5), 0)   # Sell rests
        n = lob.submit_order_fast(3, True, 101.0, 8)                     # Buy sweeps
        self.assertEqual(n, 2)
        self.assertEqual(lob.trade_at(0), (3, 1, 100.0, 5))
        self.assertEqual(lob.trade_at(1), (3, 2, 101.0, 3))
        self.assertEqual(lob.total_trades, 2)

    def test_trade_at_out_of_range(self):
        lob = LimitOrderBook()
        lob.submit_order_fast(1, True, 100.0, 5)
        with self.assertRaises(IndexError):
            lob.trade_at(0)

    def test_counts(self):
        lob = LimitOrderBook()
        lob.submit_order_fast(1, True, 99.0, 5)
        lob.submit_order_fast(2, True, 98.0, 5)
        lob.submit_order_fast(3, False, 105.0, 5)
        self.assertEqual(lob.bid_count, 2)
        self.assertEqual(lob.ask_count, 1)

    def test_invalid_side_rejected(self):
        lob = LimitOrderBook()
        with self.assertRaises(ValueError):
            lob.submit_order(1, "X", 100.0, 5)


class TestCapacityGrowth(unittest.TestCase):
    def test_more_resting_orders_than_initial_capacity(self):
        """The C arrays start small and must grow without losing orders."""
        lob = LimitOrderBook()
        n = 5000
        for i in range(n):
            lob.submit_order_fast(i, True, 50.0 + (i % 100) * 0.01, 1)
        self.assertEqual(lob.bid_count, n)
        self.assertEqual(lob.best_bid(), 50.0 + 99 * 0.01)

    def test_one_order_producing_many_trades(self):
        """The trade buffer must also grow (one big Buy sweeps 500 Sells)."""
        lob = LimitOrderBook()
        for i in range(500):
            lob.submit_order_fast(i, False, 100.0, 1)
        n = lob.submit_order_fast(10_000, True, 100.0, 500)
        self.assertEqual(n, 500)
        self.assertEqual(lob.trade_at(499)[3], 1)
        self.assertEqual(lob.ask_count, 0)


class TestLatencyMetrics(unittest.TestCase):
    def test_timings_recorded(self):
        """
        Over many orders the timers must read non-zero at least once, and the
        matching core must never take longer than the whole submit call.
        (Windows' timer ticks every ~100 ns, so a single reading can be 0.)
        """
        lob = LimitOrderBook()
        saw_order_time = False
        saw_match_time = False
        for i in range(2000):
            lob.submit_order(i, "S" if i % 2 == 0 else "B", 100.0, 1)
            self.assertLessEqual(lob.last_matching_phase_ns,
                                 lob.last_order_latency_ns)
            saw_order_time |= lob.last_order_latency_ns > 0
            saw_match_time |= lob.last_matching_phase_ns > 0
        self.assertTrue(saw_order_time)
        self.assertTrue(saw_match_time)


class TestNoGarbageCollection(unittest.TestCase):
    def test_gc_never_runs_while_matching(self):
        """
        Submit 100,000 orders through the fast path with the garbage collector
        enabled and count how many collections start. Expected: zero.

        All inputs are built up front so this loop allocates nothing that the
        collector tracks. Any collection counted here would have to come from
        the engine itself.
        """
        n = 100_000
        rng = random.Random(7)
        ids = list(range(n))
        sides = [rng.random() < 0.5 for _ in range(n)]
        prices = [round(100.0 + rng.uniform(-2.0, 2.0), 2) for _ in range(n)]
        qtys = [rng.randint(1, 100) for _ in range(n)]

        lob = LimitOrderBook()
        collections = []

        def on_gc(phase, info):
            if phase == "start":
                collections.append(info.get("generation"))

        gc.collect()
        gc.callbacks.append(on_gc)
        try:
            for i in range(n):
                lob.submit_order_fast(ids[i], sides[i], prices[i], qtys[i])
        finally:
            gc.callbacks.remove(on_gc)

        self.assertEqual(len(collections), 0,
                         f"GC ran {len(collections)} time(s) while matching")


if __name__ == "__main__":
    unittest.main(verbosity=2)