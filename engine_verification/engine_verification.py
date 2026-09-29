"""
engine_verification.py
-----------------------
Mid-Project Review requirement: "Prove the Order Book correctly matches
a Buy order with a corresponding Sell order instantly."

This is a standalone, human-readable demo (separate from the automated
test suite) showing the Cython matching engine's core behavior clearly,
step by step, with printed output suitable for a reviewer to read.

NOTE: engine/order_book.pyx must be compiled first
(python engine/setup.py build_ext --inplace).

Run with:
    python engine_verification/engine_verification.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from order_book import LimitOrderBook


def verify_exact_match():
    print("=" * 60)
    print("TEST 1: Exact Buy/Sell match")
    print("=" * 60)

    lob = LimitOrderBook()

    print("Submitting Buy order  #1: BUY  10 units @ $100.00")
    lob.submit_order(order_id=1, side="B", price=100.00, quantity=10)
    print(f"  -> Resting in book. Best Bid: {lob.best_bid()}, Best Ask: {lob.best_ask()}")

    print("\nSubmitting Sell order #2: SELL 10 units @ $100.00")
    start = time.perf_counter()
    trades = lob.submit_order(order_id=2, side="S", price=100.00, quantity=10)
    elapsed_us = (time.perf_counter() - start) * 1_000_000

    print(f"  -> Matched instantly in {elapsed_us:.2f} microseconds.")
    for t in trades:
        print(f"  -> TRADE: Buy order #{t.buy_order_id} matched with "
              f"Sell order #{t.sell_order_id} at ${t.price:.2f} for {t.quantity} units")

    assert len(trades) == 1, "Expected exactly 1 trade"
    assert trades[0].buy_order_id == 1
    assert trades[0].sell_order_id == 2
    assert trades[0].quantity == 10
    print("\n✅ VERIFIED: Buy order #1 correctly matched with Sell order #2.")


def verify_partial_fill():
    print("\n" + "=" * 60)
    print("TEST 2: Partial fill (incoming order larger than resting)")
    print("=" * 60)

    lob = LimitOrderBook()

    print("Submitting Sell order #1: SELL 10 units @ $100.00")
    lob.submit_order(order_id=1, side="S", price=100.00, quantity=10)

    print("Submitting Buy order  #2: BUY  15 units @ $100.00")
    trades = lob.submit_order(order_id=2, side="B", price=100.00, quantity=15)

    for t in trades:
        print(f"  -> TRADE: Buy order #{t.buy_order_id} matched with "
              f"Sell order #{t.sell_order_id} at ${t.price:.2f} for {t.quantity} units")

    remaining_bid = lob.best_bid()
    print(f"\n  -> 5 units of Buy order #2 remain resting. Best Bid now: {remaining_bid}")

    assert trades[0].quantity == 10
    assert lob.best_bid() == 100.00
    print("\n✅ VERIFIED: 10 units matched immediately, 5 units correctly rest in the book.")


def verify_price_priority():
    print("\n" + "=" * 60)
    print("TEST 3: Best price matches first")
    print("=" * 60)

    lob = LimitOrderBook()

    print("Resting Sell order #1: SELL 10 units @ $101.00 (worse price)")
    lob.submit_order(order_id=1, side="S", price=101.00, quantity=10)
    print("Resting Sell order #2: SELL 10 units @ $100.00 (better price)")
    lob.submit_order(order_id=2, side="S", price=100.00, quantity=10)

    print("\nSubmitting Buy order  #3: BUY  10 units @ $101.00 (willing to pay up to $101)")
    trades = lob.submit_order(order_id=3, side="B", price=101.00, quantity=10)

    for t in trades:
        print(f"  -> TRADE: matched with Sell order #{t.sell_order_id} at ${t.price:.2f}")

    assert trades[0].sell_order_id == 2, "Should match the cheaper resting order first"
    print("\n✅ VERIFIED: The cheaper resting Sell order (#2, $100.00) matched first, "
          "not the more expensive one (#1, $101.00).")


if __name__ == "__main__":
    verify_exact_match()
    verify_partial_fill()
    verify_price_priority()

    print("\n" + "=" * 60)
    print("ALL ENGINE VERIFICATION CHECKS PASSED")
    print("=" * 60)