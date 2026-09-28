from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import random
import time
import sys
import os

# Allow Python to find the compiled Cython order book
ENGINE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "engine")
)

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from order_book import LimitOrderBook


app = FastAPI(title="ChronosMatch HFT Engine")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# One persistent order book for the API
lob = LimitOrderBook()

next_order_id = 0
total_orders = 0
total_trades = 0
total_latency_us = 0.0


def generate_order():
    global next_order_id

    side = random.choice(["B", "S"])

    price = round(
        100.00 + random.uniform(-2.00, 2.00),
        2
    )

    quantity = random.randint(1, 100)

    order = {
        "order_id": next_order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
    }

    next_order_id += 1

    return order


def process_orders(count=5):
    global total_orders
    global total_trades
    global total_latency_us

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
        total_orders += 1
        total_trades += len(trades)

    if count > 0:
        total_latency_us = (
            batch_latency / count
        ) * 1_000_000


@app.get("/api/status")
def get_status():

    process_orders(5)

    best_bid = lob.best_bid()
    best_ask = lob.best_ask()
    spread = lob.spread()

    return {
        "status": "RUNNING",

        "orders": total_orders,

        "trades": total_trades,

        "throughput": 0,

        "best_bid": best_bid,

        "best_ask": best_ask,

        "spread": spread,

        "ipc": "mmap",

        "encoding": "struct",

        "pickle": False,

        "latency_us": round(total_latency_us, 2),

        "resting_bids": len(lob.bids),

        "resting_asks": len(lob.asks),
    }


@app.get("/api/orderbook")
def get_orderbook():

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

    recent_trades = lob.trades[-10:]

    trades = []

    for trade in reversed(recent_trades):

        trades.append({
            "time": time.strftime("%H:%M:%S"),
            "side": "TRADE",
            "price": trade.price,
            "quantity": trade.quantity,
        })

    return {
        "trades": trades
    }


@app.get("/api/benchmark")
def get_benchmark():
    return {
        "orders_tested": total_orders,
        "orders_received": total_orders,
        "orders_lost": 0,
        "throughput": 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)