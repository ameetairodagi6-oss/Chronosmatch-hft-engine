"""
gc_audit.py
-----------
Week 3 audit: prove the Python garbage collector does not run while the
Cython engine is matching trades.

How it works
------------
  1. All order data is generated BEFORE the timed loop, so the loop itself
     allocates nothing the garbage collector tracks.
  2. A callback is registered with gc.callbacks. Python calls it every time a
     collection starts. The garbage collector stays ENABLED the whole time.
  3. 1,000,000 orders go through submit_order_fast(), which runs the matching
     core as a nogil C function.
  4. We report how many collections started during the loop. Expected: 0.

Run with:
    python benchmarks/gc_audit.py [num_orders]
"""

import gc
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

from order_book import LimitOrderBook


def main():
    num_orders = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000

    print(f"GC Audit: {num_orders:,} orders through the C matching core\n")

    # Build every input up front (this part is allowed to allocate).
    rng = random.Random(42)
    sides = [rng.random() < 0.5 for _ in range(num_orders)]
    prices = [round(100.0 + rng.uniform(-2.0, 2.0), 2) for _ in range(num_orders)]
    qtys = [rng.randint(1, 100) for _ in range(num_orders)]

    book = LimitOrderBook()
    collections = []

    def on_gc(phase, info):
        if phase == "start":
            collections.append(info.get("generation"))

    gc.collect()                       # start from a clean slate
    gc.callbacks.append(on_gc)
    trades = 0

    start = time.perf_counter_ns()
    try:
        for i in range(num_orders):
            trades += book.submit_order_fast(i, sides[i], prices[i], qtys[i])
    finally:
        elapsed_ns = time.perf_counter_ns() - start
        gc.callbacks.remove(on_gc)

    print(f"Orders submitted:      {num_orders:,}")
    print(f"Trades matched:        {trades:,}")
    print(f"Resting bids / asks:   {book.bid_count:,} / {book.ask_count:,}")
    print(f"Wall time:             {elapsed_ns / 1e9:.3f} s "
          f"({elapsed_ns / num_orders:,.0f} ns per order, loop included)")
    print(f"GC enabled throughout: {gc.isenabled()}")
    print(f"GC collections during matching: {len(collections)}")

    if collections:
        print("\nAUDIT FAILED: the garbage collector ran during matching.")
        sys.exit(1)

    print("\nAUDIT PASSED: zero garbage-collection pauses while matching.")


if __name__ == "__main__":
    main()