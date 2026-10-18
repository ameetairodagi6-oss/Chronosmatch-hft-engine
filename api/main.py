
"""
ChronosMatch - FastAPI Backend
--------------------------------
Connects the Cython matching engine, mmap trade buffer,
background persistence worker, and dashboard API.
"""

import multiprocessing
import os
import random
import sqlite3
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


# Make the compiled Cython matching engine importable.
ENGINE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "engine")
)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from order_book import LimitOrderBook
from ipc.trade_buffer import TradeBuffer
from persistence.trade_worker import run_worker


# Configuration
BUFFER_PATH = os.path.join(PROJECT_ROOT, "matched_trades.buf")
DATABASE_PATH = os.path.join(
    PROJECT_ROOT, "persistence", "trades.db"
)
BUFFER_CAPACITY = 100_000

# Engine state
lob = LimitOrderBook()
next_order_id = 0
total_orders = 0
total_trades = 0
total_latency_us = 0.0
engine_start_time = time.perf_counter()

trade_buffer = None
worker_process = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the trade persistence worker."""
    global trade_buffer, worker_process

    trade_buffer = TradeBuffer(
        BUFFER_PATH,
        capacity=BUFFER_CAPACITY,
        create=True,
    )

    worker_process = multiprocessing.Process(
        target=run_worker,
        args=(BUFFER_PATH, DATABASE_PATH, BUFFER_CAPACITY),
        name="ChronosMatchTradeWorker",
    )

    try:
        worker_process.start()
        yield
    finally:
        if worker_process.is_alive():
            trade_buffer.request_stop()
            worker_process.join(timeout=30)

        if worker_process.is_alive():
            worker_process.terminate()
            worker_process.join(timeout=5)

        trade_buffer.close()

        if worker_process.pid is not None:
            worker_process.close()


app = FastAPI(
    title="ChronosMatch HFT Engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def generate_order():
    """Generate a simulated market order."""
    global next_order_id

    order = {
        "order_id": next_order_id,
        "side": random.choice(["B", "S"]),
        "price": round(
            100.00 + random.uniform(-2.00, 2.00), 2
        ),
        "quantity": random.randint(1, 100),
    }

    next_order_id += 1
    return order


def process_orders(count=5):
    """Process simulated orders and enqueue matched trades."""
    global total_orders, total_trades, total_latency_us

    batch_latency = 0.0

    for _ in range(count):
        order = generate_order()

        start = time.perf_counter()

        trades = lob.submit_order(
            order["order_id"],
            order["side"],
            order["price"],
            order["quantity"],
        )

        elapsed = time.perf_counter() - start
        batch_latency += elapsed

        # Every matched trade is sent to the mmap persistence queue.
        for trade in trades:
            if trade_buffer is None:
                raise RuntimeError("Trade buffer is not initialized")

            trade_buffer.write_trade(
                buy_order_id=trade.buy_order_id,
                sell_order_id=trade.sell_order_id,
                price=trade.price,
                quantity=trade.quantity,
            )

        total_orders += 1
        total_trades += len(trades)

    if count > 0:
        total_latency_us = (
            batch_latency / count
        ) * 1_000_000


def get_throughput():
    """Average processed orders per second since API startup."""
    elapsed = time.perf_counter() - engine_start_time

    if elapsed <= 0:
        return 0.0

    return round(total_orders / elapsed, 2)


@app.get("/api/status")
def get_status():
    """Return the latest matching-engine status."""
    try:
        process_orders(5)
    except (BufferError, OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Order processing or trade buffering failed: {exc}",
        ) from exc

    best_bid = lob.best_bid()
    best_ask = lob.best_ask()

    return {
        "status": "RUNNING",
        "orders": total_orders,
        "trades": total_trades,
        "throughput": get_throughput(),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": lob.spread(),
        "ipc": "mmap",
        "encoding": "struct",
        "pickle": False,
        "latency_us": round(total_latency_us, 2),
        "resting_bids": len(lob.bids),
        "resting_asks": len(lob.asks),
    }


@app.get("/api/orderbook")
def get_orderbook():
    """Return up to ten resting orders from each side."""
    bids = [
        {
            "price": order.price,
            "quantity": order.quantity,
        }
        for order in lob.bids[:10]
    ]

    asks = [
        {
            "price": order.price,
            "quantity": order.quantity,
        }
        for order in lob.asks[:10]
    ]

    return {
        "bids": bids,
        "asks": asks,
    }


@app.get("/api/trades")
def get_trades():
    """Return the most recent in-memory matched trades."""
    recent_trades = lob.trades[-10:]

    return {
        "trades": [
            {
                "time": time.strftime("%H:%M:%S"),
                "side": "TRADE",
                "price": trade.price,
                "quantity": trade.quantity,
            }
            for trade in reversed(recent_trades)
        ]
    }



@app.get("/api/benchmark")
def get_benchmark():
    """Run an isolated benchmark against a fresh matching engine."""
    import time

    from engine.order_book import LimitOrderBook

    benchmark_orders = 10_000
    benchmark_lob = LimitOrderBook()
    next_id = 1

    start_time = time.perf_counter()

    for i in range(benchmark_orders):
        # Alternate buy and sell orders around the same price.
        side = "B" if i % 2 == 0 else "S"
        price = 100.0
        quantity = 1

        benchmark_lob.submit_order(
            next_id, side, price, quantity
        )
        next_id += 1

    elapsed_seconds = time.perf_counter() - start_time
    throughput = (
        benchmark_orders / elapsed_seconds
        if elapsed_seconds > 0
        else 0.0
    )

    return {
        "benchmark": "isolated_matching_engine",
        "orders_tested": benchmark_orders,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "throughput_orders_per_second": round(throughput, 2),
        "note": (
            "Measures sequential order submissions to a fresh "
            "matching engine; excludes IPC, API overhead, and persistence."
        ),
    }


@app.get("/api/persistence")
def get_persistence():
    """Report worker state and the trade queue depth."""
    pending = (
        trade_buffer.pending_count()
        if trade_buffer is not None
        else 0
    )

    return {
        "database": DATABASE_PATH,
        "worker_alive": (
            worker_process is not None
            and worker_process.is_alive()
        ),
        "pending_trades": pending,
        "ipc": "mmap",
        "storage": "SQLite",
    }


@app.get("/api/persisted-trades")
def get_persisted_trades(
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return the newest trades stored in SQLite."""
    try:
        with sqlite3.connect(
            DATABASE_PATH, timeout=5
        ) as conn:
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                """
                SELECT id, buy_order_id, sell_order_id,
                       price, quantity, created_at
                FROM trades
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return {"trades": [dict(row) for row in rows]}

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read persisted trades: {exc}",
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )
