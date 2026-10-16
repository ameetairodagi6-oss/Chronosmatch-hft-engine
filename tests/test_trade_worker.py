
import multiprocessing
import sqlite3
import tempfile
import time
from pathlib import Path

from ipc.trade_buffer import TradeBuffer
from persistence.trade_worker import run_worker


def test_worker_persists_all_trades():
    temp_dir = tempfile.mkdtemp()
    producer = None
    worker = None

    try:
        root = Path(temp_dir)
        buffer_path = str(root / "matched_trades.buf")
        db_path = str(root / "trades.db")
        capacity = 100
        total_trades = 25

        producer = TradeBuffer(
            buffer_path, capacity=capacity, create=True
        )

        worker = multiprocessing.Process(
            target=run_worker,
            args=(buffer_path, db_path, capacity),
        )
        worker.start()

        deadline = time.time() + 5
        while not Path(db_path).exists() and time.time() < deadline:
            time.sleep(0.01)

        for i in range(total_trades):
            producer.write_trade(
                buy_order_id=1000 + i,
                sell_order_id=2000 + i,
                price=100.0 + i,
                quantity=i + 1,
            )

        deadline = time.time() + 5
        while producer.pending_count() > 0 and time.time() < deadline:
            time.sleep(0.01)

        if producer.pending_count() != 0:
            raise AssertionError("Worker did not consume all trades")

        producer.request_stop()
        worker.join(timeout=10)

        print("Worker alive:", worker.is_alive())
        print("Worker exit code:", worker.exitcode)

        if worker.is_alive():
            worker.terminate()
            worker.join()
            raise AssertionError("Worker did not stop")

        if worker.exitcode != 0:
            raise AssertionError(
                f"Worker exited with code {worker.exitcode}"
            )

        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM trades"
            ).fetchone()[0]
            quantity_sum = conn.execute(
                "SELECT SUM(quantity) FROM trades"
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == total_trades, (
            f"Expected {total_trades}, got {count}"
        )
        assert quantity_sum == sum(range(1, total_trades + 1))

        print(f"Trades persisted: {count}")
        print(f"Quantity checksum: {quantity_sum}")
        print("TRADE WORKER TEST PASSED")

    finally:
        if worker is not None:
            if worker.is_alive():
                if producer is not None:
                    producer.request_stop()
                worker.join(timeout=5)

            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)

            if worker.is_alive():
                raise RuntimeError("Worker process did not terminate")

            if worker.pid is not None:
                worker.close()

        if producer is not None:
            producer.close()

        # Delete temporary files only after closing the handles.
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=False)


if __name__ == "__main__":
    test_worker_persists_all_trades()
