
import time
from engine.order_book import LimitOrderBook


def run_insertion_benchmark(total_orders=20_000):
    book = LimitOrderBook()
    latencies = []

    start = time.perf_counter_ns()

    for i in range(total_orders):
        # Distinct prices keep these orders resting instead of matching.
        price = 100.0 - i * 0.01
        order_start = time.perf_counter_ns()

        book.submit_order_fast(
            i,
            True,
            price,
            1,
        )

        latencies.append(time.perf_counter_ns() - order_start)

    elapsed = time.perf_counter_ns() - start
    latencies.sort()

    def percentile(p):
        index = min(int(len(latencies) * p), len(latencies) - 1)
        return latencies[index]

    print("\n=== ChronosMatch Resting-Order Insertion Benchmark ===")
    print(f"Orders submitted: {total_orders:,}")
    print(f"Resting bids:     {book.bid_count:,}")
    print(f"Elapsed time:     {elapsed / 1e9:.3f} seconds")
    print(f"Throughput:       {total_orders / (elapsed / 1e9):,.0f} orders/sec")
    print(f"Median latency:   {percentile(0.50):,} ns")
    print(f"P95 latency:      {percentile(0.95):,} ns")
    print(f"P99 latency:      {percentile(0.99):,} ns")


if __name__ == "__main__":
   run_insertion_benchmark(total_orders=50_000)
