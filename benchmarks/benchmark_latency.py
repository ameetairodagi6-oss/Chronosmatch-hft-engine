
import sys
import statistics
from pathlib import Path

# Allow importing the compiled Cython engine.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

from order_book import LimitOrderBook


def percentile(values, percent):
    ordered = sorted(values)
    index = round((percent / 100) * (len(ordered) - 1))
    return ordered[index]


def run_benchmark(total_orders=20_000, warmup_orders=1_000):
    book = LimitOrderBook()

    # Warm up the compiled code before collecting measurements.
    for i in range(warmup_orders):
        book.submit_order(i, "B", 99.0, 1)

    # Collect latency measurements.
    order_latencies = []
    matching_latencies = []
    executed_trades = 0

    for i in range(total_orders):
        # Alternate order sides and prices to exercise both sides
        # of the book and produce occasional matches.
        if i % 2 == 0:
            side, price = "S", 100.0
        else:
            side, price = "B", 100.0

        trades = book.submit_order(
            warmup_orders + i,
            side,
            price,
            1,
        )

        order_latencies.append(book.last_order_latency_ns)
        matching_latencies.append(book.last_matching_phase_ns)
        executed_trades += len(trades)

    print("\n=== ChronosMatch Latency Benchmark ===")
    print(f"Warm-up orders: {warmup_orders:,}")
    print(f"Measured orders: {total_orders:,}")
    print(f"Executed trades: {executed_trades:,}")
    print("\nOrder submission latency:")
    print(f"  Mean:   {statistics.mean(order_latencies):,.0f} ns")
    print(f"  Median: {statistics.median(order_latencies):,.0f} ns")
    print(f"  P95:    {percentile(order_latencies, 95):,.0f} ns")
    print(f"  P99:    {percentile(order_latencies, 99):,.0f} ns")
    print("\nMatching phase latency:")
    print(f"  Mean:   {statistics.mean(matching_latencies):,.0f} ns")
    print(f"  Median: {statistics.median(matching_latencies):,.0f} ns")
    print(f"  P95:    {percentile(matching_latencies, 95):,.0f} ns")
    print(f"  P99:    {percentile(matching_latencies, 99):,.0f} ns")


if __name__ == "__main__":
    run_benchmark()