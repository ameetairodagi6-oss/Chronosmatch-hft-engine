"""
test_order_book.py
-------------------
Day 2 (Week 2): Tests for the Cython Limit Order Book matching engine.

IMPORTANT: order_book.pyx must be compiled first
(python engine/setup.py build_ext --inplace) before this will import.

Run with:
    python tests/test_order_book.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from order_book import LimitOrderBook


class TestBasicMatching(unittest.TestCase):
    def setUp(self):
        self.lob = LimitOrderBook()

    def test_no_trade_when_book_is_empty(self):
        """A single resting order with nothing to match against generates no trades."""
        trades = self.lob.submit_order(1, "B", 100.0, 10)
        self.assertEqual(len(trades), 0)
        self.assertEqual(self.lob.best_bid(), 100.0)
        self.assertIsNone(self.lob.best_ask())

    def test_exact_match_buy_then_sell(self):
        """A resting Buy fully matches an incoming Sell at the same price/qty."""
        self.lob.submit_order(1, "B", 100.0, 10)
        trades = self.lob.submit_order(2, "S", 100.0, 10)

        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.buy_order_id, 1)
        self.assertEqual(trade.sell_order_id, 2)
        self.assertEqual(trade.price, 100.0)
        self.assertEqual(trade.quantity, 10)

        # Book should be empty on both sides after a full match.
        self.assertIsNone(self.lob.best_bid())
        self.assertIsNone(self.lob.best_ask())

    def test_exact_match_sell_then_buy(self):
        """Same as above but the resting order is a Sell."""
        self.lob.submit_order(1, "S", 100.0, 5)
        trades = self.lob.submit_order(2, "B", 100.0, 5)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].buy_order_id, 2)
        self.assertEqual(trades[0].sell_order_id, 1)


class TestPartialFills(unittest.TestCase):
    def setUp(self):
        self.lob = LimitOrderBook()

    def test_incoming_order_larger_than_resting(self):
        """Incoming Buy for 15 hits a resting Sell for 10 -> partial fill, remainder rests."""
        self.lob.submit_order(1, "S", 100.0, 10)
        trades = self.lob.submit_order(2, "B", 100.0, 15)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].quantity, 10)

        # 5 shares of the incoming Buy should now rest in the book.
        self.assertEqual(self.lob.best_bid(), 100.0)
        self.assertIsNone(self.lob.best_ask())

    def test_incoming_order_smaller_than_resting(self):
        """Incoming Sell for 4 hits a resting Buy for 10 -> resting order stays with remainder."""
        self.lob.submit_order(1, "B", 100.0, 10)
        trades = self.lob.submit_order(2, "S", 100.0, 4)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].quantity, 4)

        # 6 shares should still be resting on the bid side.
        self.assertEqual(self.lob.best_bid(), 100.0)


class TestPriceTimePriority(unittest.TestCase):
    def setUp(self):
        self.lob = LimitOrderBook()

    def test_best_price_matches_first(self):
        """Two resting Sells at different prices: the cheaper one should match first."""
        self.lob.submit_order(1, "S", 101.0, 10)  # worse price
        self.lob.submit_order(2, "S", 100.0, 10)  # better price, should match first

        trades = self.lob.submit_order(3, "B", 101.0, 10)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].sell_order_id, 2)  # the cheaper resting order
        self.assertEqual(trades[0].price, 100.0)

    def test_same_price_fifo_time_priority(self):
        """Two resting Sells at the SAME price: the earlier one should match first."""
        self.lob.submit_order(1, "S", 100.0, 10)  # arrives first
        self.lob.submit_order(2, "S", 100.0, 10)  # arrives second

        trades = self.lob.submit_order(3, "B", 100.0, 10)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].sell_order_id, 1)  # FIFO: order 1 matched, not order 2

    def test_sweeps_multiple_price_levels(self):
        """A large incoming Buy should sweep through multiple resting Sell price levels."""
        self.lob.submit_order(1, "S", 100.0, 5)
        self.lob.submit_order(2, "S", 101.0, 5)
        self.lob.submit_order(3, "S", 102.0, 5)

        # Willing to pay up to 102, needs 15 total -> should consume all three levels.
        trades = self.lob.submit_order(4, "B", 102.0, 15)

        self.assertEqual(len(trades), 3)
        prices_matched = [t.price for t in trades]
        self.assertEqual(prices_matched, [100.0, 101.0, 102.0])
        self.assertIsNone(self.lob.best_ask())


class TestSpread(unittest.TestCase):
    def setUp(self):
        self.lob = LimitOrderBook()

    def test_spread_none_when_one_side_empty(self):
        self.lob.submit_order(1, "B", 99.0, 10)
        self.assertIsNone(self.lob.spread())

    def test_spread_calculation(self):
        self.lob.submit_order(1, "B", 99.0, 10)
        self.lob.submit_order(2, "S", 101.0, 10)
        self.assertAlmostEqual(self.lob.spread(), 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)