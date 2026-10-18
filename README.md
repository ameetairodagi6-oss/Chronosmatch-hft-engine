# ChronosMatch: Zero-Copy High-Frequency Trading Engine

## Overview

ChronosMatch is a simulated high-frequency trading (HFT) engine built to demonstrate  
low-latency systems programming in Python. In real HFT, microseconds equal millions of  
dollars — but Python is typically dismissed for this domain due to Garbage Collector  
latency spikes and slow serialization (JSON/Pickle) when passing data between processes.

This project solves that by combining Cython, memory-mapped IPC, and asyncio to build  
a matching engine capable of sub-millisecond execution — entirely in Python's ecosystem.

The project has since been extended with a FastAPI backend, a connected web dashboard,  
and SQLite trade persistence to make the engine easier to monitor and demonstrate.

## Key Modules

- **Cython Matching Engine** — Core Limit Order Book algorithm (Price-Time Priority)  
  compiled to a C-extension using C-structs and pointers to reduce Python overhead.
- **Zero-Copy IPC Bus (mmap & struct)** — A custom ring buffer mapped directly to  
  system memory, allowing distinct Python processes to share data without Pickle-based  
  serialization.
- **Market Simulator (asyncio)** — A high-throughput script simulating a firehose of  
  Nasdaq/NYSE-style tick data (Buy/Sell orders).
- **Latency Monitor (curses)** — A live terminal dashboard displaying the Bid/Ask  
  spread and order-processing latency in microseconds (µs).
- **FastAPI Backend** — Provides endpoints for engine status, order-book data, trades,  
  benchmark measurements, and persistence status.
- **Web Dashboard (HTML/CSS/JS)** — Provides a visual interface connected to the API  
  for displaying engine information.
- **Trade Persistence (mmap + SQLite)** — Uses a memory-mapped trade buffer and a  
  background worker to persist executed trades in a SQLite database.
- **Automated Tests and Verification** — Tests matching behavior, partial fills,  
  price-time priority, IPC ring-buffer behavior, and trade persistence.

## Project Structure

```text
Chronosmatch-hft-engine/
├── ipc/                         # mmap ring buffer
├── engine/                      # Cython Limit Order Book
├── simulator/                   # asyncio market data firehose
├── dashboard/                   # curses-based terminal dashboard
├── ipc_audit/                   # high-volume IPC stress test
├── engine_verification/         # standalone matching-correctness demo
├── Frontend/                    # web dashboard UI (HTML/CSS/JS)
├── api/                         # FastAPI backend
├── persistence/                 # trade worker and SQLite storage
├── tests/                       # automated tests
├── requirements.txt
└── README.md
```

The project may also contain generated Cython build artifacts, local database files,  
and temporary IPC buffers during development.

## How to Run

### Prerequisites

- Python installed on your system
- pip
- A compatible C compiler and Python build environment for Cython
- Git

### Installation

Clone the repository:

```bash
git clone https://github.com/ameetairodagi6-oss/Chronosmatch-hft-engine.git
cd Chronosmatch-hft-engine
```

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

### 1. Ring Buffer (IPC layer)

Run a standalone smoke test that writes and reads back a few sample orders:

```bash
python ipc/ring_buffer.py
```

### 2. Test Suite

Run the ring-buffer correctness tests:

```bash
python tests/test_ring_buffer.py
```

Expected output: 6 tests, all passing (`OK`), as described in the original project instructions.

To run the **complete current test suite**, use:

```bash
python -m pytest -v
```

**Latest verified result:**

```text
29 passed in 0.92s
```

The 29 tests cover the matching engine, price-time priority, partial fills, capacity growth, latency metrics, ring-buffer behavior, trade-buffer safety, and trade-worker persistence.

### 3. Market Firehose Simulator

Run the asyncio order generator, which writes randomized Buy/Sell orders  
into the shared ring buffer for 5 seconds and prints throughput statistics:

```bash
python simulator/market_firehose.py
```

Expected output: total orders written, achieved orders/sec, and a sample  
of the last 5 orders read back from the buffer.

### 4. Cython Order Book Engine

Compile it first:

```bash
cd engine
python setup.py build_ext --inplace
cd ..
```

Then run the matching-engine tests:

```bash
python tests/test_order_book.py
```

The original Week 2 test target was 10 tests covering matching, partial fills,  
and price-time priority. The project now also includes the Week 3 test suite.

Run all matching-engine and project tests with:

```bash
python -m pytest -v
```

### 5. Live Terminal Dashboard

Start the terminal dashboard:

```bash
python dashboard/dashboard.py
```

The dashboard displays engine information such as Best Bid, Best Ask, Spread,  
and order-processing latency. Press `q` to quit, if supported by the running version.

The API-connected version retrieves status information from the local FastAPI server.  
Start the API before launching the connected dashboard.

### 6. IPC Audit (Mid-Review Requirement)

The IPC audit checks whether the zero-copy ring buffer can transfer high-volume  
order data between two separate processes without a Pickle-based serialization  
bottleneck:

```bash
python ipc_audit/ipc_1m_audit.py 1000000
```

The audit checks producer and consumer counts, lost orders, checksums, elapsed time,  
and throughput.

**Previously verified IPC audit result:**

- Orders transferred: 1,000,000
- Lost orders: 0
- Producer and consumer checksums: matched
- IPC mechanism: `mmap` shared memory
- Record encoding: `struct`
- Pickle used: No
- Sockets used: No
- Audit result: PASSED

These results document the successful audit run. Performance can vary with hardware  
and system load.

### 7. Engine Verification (Mid-Review Requirement)

Run the standalone matching-correctness demonstration:

```bash
python engine_verification/engine_verification.py
```

The verification scenarios check exact matches, partial fills, and price priority.  
The previously reported verification run passed all checks.

Expected final message:

```text
ALL ENGINE VERIFICATION CHECKS PASSED
```

### 8. Web Dashboard and FastAPI Backend

The project includes a web dashboard and a backend API for monitoring the simulated  
trading engine.

Start the API from the project root:

```bash
python -m uvicorn api.main:app --reload
```

The API is available locally at:

```text
http://127.0.0.1:8000
```

Open the interactive API documentation at:

```text
http://127.0.0.1:8000/docs
```

The API provides the following endpoints:

| Endpoint | Purpose |
|---|---|
| `/api/status` | Engine status, order counts, order-book summary, and latency |
| `/api/orderbook` | Current resting buy and sell orders |
| `/api/trades` | Recent in-memory trade records |
| `/api/benchmark` | Isolated matching-engine benchmark |
| `/api/persistence` | Trade-worker and persistence status |
| `/api/persisted-trades` | Recent trades stored in SQLite |

The web dashboard is located in `Frontend/` and uses the backend API to display  
engine information. Keep the API running while using the connected dashboard.

Open the frontend entry HTML file in your browser or use the development server  
configured for the frontend, if applicable. The exact frontend startup command depends  
on the files and configuration in that directory.

### 9. Trade Persistence (SQLite)

Executed trades are transferred through a memory-mapped trade buffer and handled  
by a background worker that writes records to SQLite.

The persistence endpoint can be checked at:

```text
http://127.0.0.1:8000/api/persistence
```

The persisted-trades endpoint can be checked at:

```text
http://127.0.0.1:8000/api/persisted-trades
```

The persistence response includes fields such as:

- Database path
- Background worker status
- Pending trade count
- IPC mechanism
- Storage backend

A previously observed response confirmed that the worker was alive, the pending  
trade count was zero, IPC was `mmap`, and storage was SQLite.

## New Work Completed

### FastAPI Integration

A FastAPI backend was added to connect the engine to monitoring interfaces. It exposes  
endpoints for status, order-book data, recent trades, benchmark measurements, and  
persistence information.

### Web Dashboard Integration

A web dashboard was added alongside the existing terminal dashboard. It retrieves  
status information from the API, allowing reviewers to inspect the engine through  
a browser.

### SQLite Trade Persistence

A background trade worker and SQLite database were integrated to store executed  
trades separately from the live matching process. The API exposes persistence status  
and stored trade records.

### Expanded Automated Testing

The current test suite includes matching-engine tests, Week 3 reference-model and  
performance-related tests, ring-buffer tests, trade-buffer tests, and trade-worker tests.

The latest complete test run reported:

```text
29 passed in 0.92s
```

### Isolated Matching-Engine Benchmark

The `/api/benchmark` endpoint was updated to execute a benchmark against a fresh  
matching-engine instance rather than returning only the average live counter.

**Observed result from one run:**

| Metric | Result |
|---|---:|
| Orders tested | 10,000 |
| Elapsed time | 0.011046 seconds |
| Throughput | 905,280.5 orders/second |

This result is an observed measurement from one run, not a guaranteed performance figure.

**Benchmark scope:** The test measures sequential order submissions to a fresh matching  
engine. It excludes IPC, API overhead, and database persistence. It therefore does not  
represent end-to-end system throughput or establish production HFT performance.

## Week 2 Status

- Cython Limit Order Book (Price-Time Priority) — compiled, with the original Week 2  
  matching tests implemented.
- Curses live dashboard — Bid/Ask spread and latency display implemented.
- IPC ring buffer — implemented and tested.

## Development Plan (4 Weeks)

- **Week 1:** Build the mmap ring buffer (IPC) and asyncio market order firehose.
- **Week 2:** Write the Cython Limit Order Book engine and curses latency dashboard.
- **Week 3:** Verify zero-copy IPC and order-matching correctness; optimize Cython code  
  to reduce garbage-collection pauses during matching.
- **Week 4:** Add SQLite/ClickHouse trade ledger persistence and polish the dashboard UI.

The current implementation includes SQLite persistence. ClickHouse integration should  
not be considered complete unless it has been implemented and verified separately.

## Status

- Week 1 — complete.
- Week 2 — complete.
- Mid-review checks — IPC audit and engine verification completed in previously  
  reported successful runs.
- Week 3 — matching-engine optimization and expanded testing implemented.
- Week 4 — FastAPI integration, web dashboard integration, and SQLite trade persistence  
  implemented and tested.
- Automated tests — 29 passed in the latest recorded run.
- Isolated matching-engine benchmark — 905,280.5 orders/second in one observed run.
- Infotact Solutions Advanced Python Engineering Internship — Month 2 project  
  development and final documentation in progress.

## Tech Stack

Python, Cython, mmap, struct, asyncio, curses, FastAPI, SQLite, HTML, CSS, JavaScript, pytest.

## Future Improvements

- Run repeatable benchmarks with warm-up and multiple trials.
- Report median and percentile latency in addition to average latency.
- Measure end-to-end throughput across matching, IPC, and persistence.
- Add more stress tests for buffer saturation, worker failure, and recovery.
- Improve monitoring, error handling, and dashboard visualizations.
- Add ClickHouse only if it is part of the intended final implementation.

## Author

Amit Laxman Airodagi

GitHub: https://github.com/ameetairodagi6-oss

## Disclaimer

ChronosMatch is a simulated trading-engine project intended for learning and demonstration.  
It is not connected to a live stock exchange and is not intended for real-money trading.
