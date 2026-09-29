# ChronosMatch: Zero-Copy High-Frequency Trading Engine

## Overview
ChronosMatch is a simulated high-frequency trading (HFT) engine built to demonstrate 
low-latency systems programming in Python. In real HFT, microseconds equal millions of 
dollars — but Python is typically dismissed for this domain due to Garbage Collector 
latency spikes and slow serialization (JSON/Pickle) when passing data between processes.

This project solves that by combining Cython, memory-mapped IPC, and asyncio to build 
a matching engine capable of sub-millisecond execution — entirely in Python's ecosystem.

## Key Modules
- **Cython Matching Engine** — Core Limit Order Book algorithm (Price-Time Priority) 
  compiled to a C-extension using C-structs and pointers instead of Python objects, 
  bypassing the GIL.
- **Zero-Copy IPC Bus (mmap & struct)** — A custom ring buffer mapped directly to 
  system memory, allowing distinct Python processes to share data instantly without 
  serialization overhead.
- **Market Simulator (asyncio)** — A high-throughput script simulating a firehose of 
  Nasdaq/NYSE-style tick data (Buy/Sell orders).
- **Latency Monitor (curses)** — A live terminal dashboard displaying the Bid/Ask 
  spread and end-to-end latency in microseconds (µs).

chronosmatch-hft-engine/
├── ipc/                  # mmap ring buffer (read/write raw order data)
├── engine/                # Cython (.pyx) Limit Order Book matching engine
├── simulator/              # asyncio market data firehose
├── dashboard/              # curses-based real-time latency UI
├── ipc_audit/              # high-volume IPC stress test (Mid-Review requirement)
├── engine_verification/         # standalone matching-correctness demo (Mid-Review requirement)
├── Frontend/               # web dashboard UI (HTML/CSS/JS) — bonus visual layer
├── api/                  # backend API connecting Frontend to the Python engine
├── requirements.txt
└── README.md

## How to Run

### 1. Ring Buffer (IPC layer)
Run a standalone smoke test that writes and reads back a few sample orders:
```bash
python ipc/ring_buffer.py
```

### 2. Test Suite
Run the wraparound correctness tests:
```bash
python tests/test_ring_buffer.py
```
Expected output: 6 tests, all passing (`OK`).

### 3. Market Firehose Simulator
Run the asyncio order generator, which writes randomized Buy/Sell orders 
into the shared ring buffer for 5 seconds and prints throughput stats:
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
Then run the tests:
```bash
python tests/test_order_book.py
```
Expected: 10 tests passing, covering matching, partial fills, and price-time priority.

### 5. Live Dashboard
```bash
python dashboard/dashboard.py
```
Displays live Best Bid, Best Ask, Spread, and per-order latency. Press 'q' to quit.

### 6. IPC Audit (Mid-Review Requirement)
Proves the zero-copy ring buffer handles high-volume order flow between 
two separate processes without a serialization/pickling bottleneck:
```bash
python ipc_audit/ipc_1m_audit.py 1000000
```
Expected: producer/consumer throughput stats and a matching checksum 
confirming zero data loss across 1,000,000 orders.

### 7. Engine Verification (Mid-Review Requirement)
A standalone, human-readable demo proving the matching engine correctly 
handles exact matches, partial fills, and price priority:
```bash
python engine_verification/engine_verification.py
```
Expected: three labeled test scenarios, each printing step-by-step 
results, ending with "ALL ENGINE VERIFICATION CHECKS PASSED".

### 8. Web Dashboard (Bonus)
A connected web-based dashboard was also built to visually present 
order book data for reviewers, alongside the core terminal-based 
curses dashboard:
- `Frontend/` — HTML/CSS/JS interface
- `api/` — backend API connecting the frontend to the Python engine

[Add your actual run instructions here — e.g. how to start the API 
server and open the frontend]

## Week 2 Status
✅ Cython Limit Order Book (Price-Time Priority) — compiled, 10 tests passing
✅ Curses live dashboard — Bid/Ask spread + latency, working
## Development Plan (4 Weeks)
- **Week 1:** Build the mmap ring buffer (IPC) + asyncio market order firehose
- **Week 2:** Write the Cython Limit Order Book engine + curses latency dashboard
- **Week 3:** Verify zero-copy IPC and order matching correctness; optimize Cython 
  code to eliminate GC pauses during matching
- **Week 4:** Add SQLite/ClickHouse trade ledger persistence; polish the dashboard UI

## Status
✅ Week 1 complete — Week 2 complete — Mid-Review checks (IPC Audit + 
Engine Verification) complete
🚧 In development — Infotact Solutions Advanced Python Engineering 
Internship (Month 2)

## Tech Stack
Python, Cython, mmap, struct, asyncio, curses
