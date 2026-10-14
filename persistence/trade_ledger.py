"""Background SQLite persistence for ChronosMatch trades."""

import os
import queue
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "trades.db"


class TradeLedger:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self._queue = queue.Queue()
        self._error = None
        self._saved = 0
        self._lock = threading.Lock()
        self._worker = threading.Thread(
            target=self._run,
            name="chronosmatch-ledger",
            daemon=True,
        )

        with sqlite3.connect(self.db_path) as conn:
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

        self._worker.start()

    def submit(self, trade):
        """Queue a trade; do not perform a database write here."""
        if self._error:
            raise RuntimeError("Trade ledger worker failed") from self._error

        self._queue.put((
            int(trade.buy_order_id),
            int(trade.sell_order_id),
            float(trade.price),
            int(trade.quantity),
            time.strftime("%Y-%m-%d %H:%M:%S"),
        ))

    def _run(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                while True:
                    item = self._queue.get()
                    try:
                        if item is None:
                            conn.commit()
                            return

                        conn.execute("""
                            INSERT INTO trades (
                                buy_order_id, sell_order_id,
                                price, quantity, created_at
                            ) VALUES (?, ?, ?, ?, ?)
                        """, item)

                        if self._queue.qsize() == 0:
                            conn.commit()

                        with self._lock:
                            self._saved += 1
                    finally:
                        self._queue.task_done()
        except Exception as exc:
            self._error = exc

    def status(self):
        with self._lock:
            saved = self._saved
        return {
            "database": os.path.basename(self.db_path),
            "saved_trades": saved,
            "pending_trades": self._queue.qsize(),
            "worker_alive": self._worker.is_alive(),
            "error": str(self._error) if self._error else None,
        }

    def close(self):
        self._queue.join()
        self._queue.put(None)
        self._queue.join()
        self._worker.join(timeout=5)
        if self._error:
            raise RuntimeError("Trade ledger worker failed") from self._error
