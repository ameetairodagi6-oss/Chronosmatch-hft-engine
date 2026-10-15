
"""Background SQLite persistence for ChronosMatch trades.

Trades are queued by the API and written in batches by a worker thread.
"""

import os
import queue
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "trades.db"
BATCH_SIZE = 100


class TradeLedger:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._saved = 0
        self._error = None
        self._closed = False

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
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

        self._worker = threading.Thread(
            target=self._run,
            name="chronosmatch-ledger",
            daemon=True,
        )
        self._worker.start()

    def submit(self, trade):
        """Queue a matched trade for asynchronous persistence."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Trade ledger is closed")
            if self._error is not None:
                raise RuntimeError("Trade ledger worker failed") from self._error

            record = (
                int(trade.buy_order_id),
                int(trade.sell_order_id),
                float(trade.price),
                int(trade.quantity),
                datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            )
            self._queue.put(record)

    def _run(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                stopping = False

                while not stopping:
                    first = self._queue.get()
                    batch = []

                    if first is None:
                        self._queue.task_done()
                        break

                    batch.append(first)

                    while len(batch) < BATCH_SIZE:
                        try:
                            item = self._queue.get_nowait()
                        except queue.Empty:
                            break

                        if item is None:
                            self._queue.task_done()
                            stopping = True
                            break

                        batch.append(item)

                    try:
                        conn.executemany("""
                            INSERT INTO trades (
                                buy_order_id, sell_order_id,
                                price, quantity, created_at
                            ) VALUES (?, ?, ?, ?, ?)
                        """, batch)
                        conn.commit()

                        with self._lock:
                            self._saved += len(batch)

                    except Exception as exc:
                        conn.rollback()
                        with self._lock:
                            if self._error is None:
                                self._error = exc

                    finally:
                        for _ in batch:
                            self._queue.task_done()

        except Exception as exc:
            with self._lock:
                if self._error is None:
                    self._error = exc

            # Mark all queued work complete so shutdown cannot hang.
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    self._queue.task_done()

    def status(self):
        with self._lock:
            error = self._error
            saved = self._saved
            closed = self._closed

        return {
            "database": os.path.basename(self.db_path),
            "saved_trades": saved,
            "pending_trades": self._queue.qsize(),
            "worker_alive": self._worker.is_alive(),
            "closed": closed,
            "error": str(error) if error else None,
        }

    def close(self):
        """Flush queued trades and stop the worker."""
        with self._lock:
            if self._closed:
                return
            self._closed = True

        if self._worker.is_alive():
            self._queue.put(None)
            self._queue.join()
            self._worker.join(timeout=10)

        if self._worker.is_alive():
            raise RuntimeError("Trade ledger worker did not stop")

        with self._lock:
            error = self._error

        if error is not None:
            raise RuntimeError("Trade ledger persistence failed") from error
