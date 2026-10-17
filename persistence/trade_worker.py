
"""Separate process that persists mmap-buffered trades to SQLite."""

import os
import sqlite3
import time

from ipc.trade_buffer import TradeBuffer


def run_worker(
    buffer_path,
    db_path,
    capacity=100_000,
    poll_interval=0.005,
):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    buffer = TradeBuffer(buffer_path, capacity=capacity)
    conn = sqlite3.connect(db_path)

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buy_order_id INTEGER NOT NULL,
                sell_order_id INTEGER NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        batch = []

        while True:
            trade = buffer.read_trade()

            if trade is not None:
                batch.append((
                    trade["buy_order_id"],
                    trade["sell_order_id"],
                    trade["price"],
                    trade["quantity"],
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ))

            if len(batch) >= 100:
                conn.executemany("""
                    INSERT INTO trades (
                        buy_order_id, sell_order_id, price, quantity, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
                batch.clear()

            if buffer.stop_requested() and buffer.pending_count() == 0:
                break

            if trade is None:
                try:
                   time.sleep(poll_interval)
                except KeyboardInterrupt:
                 break

        if batch:
            conn.executemany("""
                INSERT INTO trades (
                    buy_order_id, sell_order_id, price, quantity, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, batch)
            conn.commit()

    finally:
        buffer.close()
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--buffer", default="matched_trades.buf")
    parser.add_argument("--database", default="persistence/trades.db")
    parser.add_argument("--capacity", type=int, default=100_000)
    args = parser.parse_args()

    run_worker(args.buffer, args.database, args.capacity)
