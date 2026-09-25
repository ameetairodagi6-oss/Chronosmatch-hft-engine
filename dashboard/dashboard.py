"""
dashboard.py
------------
Day 3 (Week 2): A curses-based terminal dashboard that displays the
Limit Order Book's top-of-book (best Bid, best Ask, spread) in real
time, along with per-order matching latency in microseconds.

For this demo, the dashboard feeds itself a stream of randomized
orders directly into the LimitOrderBook (simulating what would, in
the full system, arrive via the market_firehose + IPC ring buffer).

NOTE (Windows users): curses is a Unix library and is NOT included in
standard Windows Python. Install the Windows port first:
    pip install windows-curses

Run with:
    python dashboard/dashboard.py
(press 'q' to quit)
"""

import curses
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from order_book import LimitOrderBook


BASE_PRICE = 100.00
PRICE_SPREAD = 2.00
MIN_QUANTITY = 1
MAX_QUANTITY = 100
ORDERS_PER_TICK = 5          # orders submitted per screen refresh
REFRESH_INTERVAL_SECONDS = 0.2  # how often the screen updates


def generate_random_order(order_id: int) -> dict:
    side = random.choice(["B", "S"])
    price = round(BASE_PRICE + random.uniform(-PRICE_SPREAD, PRICE_SPREAD), 2)
    quantity = random.randint(MIN_QUANTITY, MAX_QUANTITY)
    return {"order_id": order_id, "side": side, "price": price, "quantity": quantity}


def run_dashboard(stdscr):
    curses.curs_set(0)          # hide the blinking cursor
    stdscr.nodelay(True)        # don't block waiting for keypresses
    stdscr.timeout(int(REFRESH_INTERVAL_SECONDS * 1000))

    lob = LimitOrderBook()
    order_id = 0
    total_trades = 0
    last_latency_us = 0.0

    while True:
        key = stdscr.getch()
        if key == ord("q"):
            break

        # Feed in a small batch of random orders and measure matching latency.
        tick_start = time.perf_counter()
        for _ in range(ORDERS_PER_TICK):
            order = generate_random_order(order_id)
            trades = lob.submit_order(
                order["order_id"], order["side"], order["price"], order["quantity"]
            )
            total_trades += len(trades)
            order_id += 1
        tick_elapsed = time.perf_counter() - tick_start
        # Average latency per order in this batch, in microseconds.
        last_latency_us = (tick_elapsed / ORDERS_PER_TICK) * 1_000_000

        # ---- Render ----------------------------------------------------------
        stdscr.erase()
        stdscr.addstr(0, 0, "ChronosMatch — Live Order Book Dashboard", curses.A_BOLD)
        stdscr.addstr(1, 0, "=" * 50)

        best_bid = lob.best_bid()
        best_ask = lob.best_ask()
        spread = lob.spread()

        stdscr.addstr(3, 0, f"Best Bid:  {best_bid if best_bid is not None else '--':>10}")
        stdscr.addstr(4, 0, f"Best Ask:  {best_ask if best_ask is not None else '--':>10}")
        stdscr.addstr(5, 0, f"Spread:    {spread if spread is not None else '--':>10}")

        stdscr.addstr(7, 0, f"Orders submitted:  {order_id}")
        stdscr.addstr(8, 0, f"Trades matched:    {total_trades}")
        stdscr.addstr(9, 0, f"Avg latency/order: {last_latency_us:.2f} us")

        stdscr.addstr(11, 0, f"Resting bids: {len(lob.bids)}   Resting asks: {len(lob.asks)}")

        stdscr.addstr(13, 0, "Press 'q' to quit.")
        stdscr.refresh()


def main():
    curses.wrapper(run_dashboard)


if __name__ == "__main__":
    main()