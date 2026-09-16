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

## Project Structure
chronosmatch-hft-engine/
├── ipc/ # mmap ring buffer (read/write raw order data)
├── engine/ # Cython (.pyx) Limit Order Book matching engine
├── simulator/ # asyncio market data firehose
├── dashboard/ # curses-based real-time latency UI
├── requirements.txt
└── README.md

## Development Plan (4 Weeks)
- **Week 1:** Build the mmap ring buffer (IPC) + asyncio market order firehose
- **Week 2:** Write the Cython Limit Order Book engine + curses latency dashboard
- **Week 3:** Verify zero-copy IPC and order matching correctness; optimize Cython 
  code to eliminate GC pauses during matching
- **Week 4:** Add SQLite/ClickHouse trade ledger persistence; polish the dashboard UI

## Status
🚧 In development — Infotact Solutions Advanced Python Engineering Internship (Month 2)

## Tech Stack
Python, Cython, mmap, struct, asyncio, curses
