"""
benchmark_latency.py
---------------------
Latency benchmark for the Cython matching engine.

Reports two views of the same run:

  * Per-order percentiles, read from the engine's own perf_counter_ns()
    timestamps (last_order_latency_ns / last_matching_phase_ns).
  * Batch throughput: total wall time divided by the number of orders.

Note on timer resolution: on Windows, perf_counter_ns() ticks roughly every
100 ns, so single readings are rounded to that step and a very fast match can
read 0. The batch figure is not affected by that and is the more reliable
average; the percentiles are best read as a distribution.

Run with:
    python benchmarks/benchmark_latency.py
"""

import statistics
import sys
import time
from pathlib import Path

# Allow importing the compiled Cython engine.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

from order_book import LimitOrderBook


def percentile(values, percent):
    ordered = sorted(values)
    index = round((percent / 100) * (len(ordered) - 1))
    return ordered[index]


def print_stats(title, values):
    print(f"\n{title}:")
    print(f"  Mean:   {statistics.mean(values):,.0f} ns")
    print(f"  Median: {statistics.median(values):,.0f} ns")
    print(f"  P95:    {percentile(values, 95):,.0f} ns")
    print(f"  P99:    {percentile(values, 99):,.0f} ns")
    print(f"  Max:    {max(values):,.0f} ns")


def run_benchmark(total_orders=100_000, warmup_orders=1_000):
    book = LimitOrderBook()

    # Warm up before collecting measurements. These Buys rest at 99.0 and
    # never match the Sells at 100.0 below.
    for i in range(warmup_orders):
        book.submit_order_fast(i, True, 99.0, 1)

    order_latencies = []
    matching_latencies = []
    executed_trades = 0

    batch_start = time.perf_counter_ns()
    for i in range(total_orders):
        # Alternate Sell / Buy at the same price so every second order matches.
        is_buy = i % 2 == 1
        executed_trades += book.submit_order_fast(
            warmup_orders + i, is_buy, 100.0, 1
        )
        order_latencies.append(book.last_order_latency_ns)
        matching_latencies.append(book.last_matching_phase_ns)
    batch_ns = time.perf_counter_ns() - batch_start

    print("\n=== ChronosMatch Latency Benchmark (C-level engine) ===")
    print(f"Warm-up orders:  {warmup_orders:,}")
    print(f"Measured orders: {total_orders:,}")
    print(f"Executed trades: {executed_trades:,}")

    print_stats("Order submission latency (whole call)", order_latencies)
    print_stats("Matching phase latency (C core only)", matching_latencies)

    print("\nBatch throughput (includes the benchmark loop itself):")
    print(f"  {batch_ns / total_orders:,.0f} ns per order on average")
    print(f"  {total_orders / (batch_ns / 1e9):,.0f} orders per second")


if __name__ == "__main__":
    run_benchmark()