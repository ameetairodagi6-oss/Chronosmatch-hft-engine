"""Run the ChronosMatch latency benchmark multiple times."""

import statistics
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = PROJECT_ROOT / "benchmarks" / "benchmark_latency.py"
RUNS = 5


def main():
    throughputs = []

    print(f"ChronosMatch repeated benchmark: {RUNS} runs")

    for run_number in range(1, RUNS + 1):
        print(f"\n{'=' * 18} RUN {run_number}/{RUNS} {'=' * 18}")

        result = subprocess.run(
            [sys.executable, str(BENCHMARK)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        print(result.stdout)

        for line in result.stdout.splitlines():
            if "orders per second" in line:
                value = line.strip().split()[0].replace(",", "")
                throughputs.append(float(value))

    print("\n=== Repeated Benchmark Summary ===")
    print(f"Successful runs: {len(throughputs)}/{RUNS}")

    if throughputs:
        print(f"Mean throughput:   {statistics.mean(throughputs):,.0f} orders/sec")
        print(f"Median throughput: {statistics.median(throughputs):,.0f} orders/sec")
        print(f"Minimum:           {min(throughputs):,.0f} orders/sec")
        print(f"Maximum:           {max(throughputs):,.0f} orders/sec")
        print(
            f"Population std dev: "
            f"{statistics.pstdev(throughputs):,.0f} orders/sec"
        )


if __name__ == "__main__":
    main()