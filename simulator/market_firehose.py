import asyncio
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipc.ring_buffer import RingBuffer

# ---- Simulation config -----------------------------------------------------
BUFFER_PATH = "market_orders.buf"
BUFFER_CAPACITY = 100_000        # number of order slots in the ring
TARGET_ORDERS_PER_SECOND = 20_000  # start conservative; tune upward later
BATCH_SIZE = 500                 # orders written per asyncio tick
RUN_DURATION_SECONDS = 5         # how long the firehose runs for this demo

BASE_PRICE = 100.00
PRICE_SPREAD = 2.00              # random walk range around the base price
MIN_QUANTITY = 1
MAX_QUANTITY = 500


def generate_random_order(order_id: int) -> dict:
    """Create one randomized mock order."""
    side = random.choice(["B", "S"])
    price = round(BASE_PRICE + random.uniform(-PRICE_SPREAD, PRICE_SPREAD), 2)
    quantity = random.randint(MIN_QUANTITY, MAX_QUANTITY)
    return {"order_id": order_id, "side": side, "price": price, "quantity": quantity}


async def firehose(rb: RingBuffer, duration_seconds: int = RUN_DURATION_SECONDS):
    """
    Continuously generate and write batches of mock orders into the ring
    buffer for `duration_seconds`, then stop and report throughput stats.
    """
    order_id = 0
    start_time = time.perf_counter()
    end_time = start_time + duration_seconds

    while time.perf_counter() < end_time:
        batch_start = time.perf_counter()

        for _ in range(BATCH_SIZE):
            order = generate_random_order(order_id)
            rb.write_order(
                order_id=order["order_id"],
                side=order["side"],
                price=order["price"],
                quantity=order["quantity"],
            )
            order_id += 1

        # Yield control back to the event loop between batches so this
        # stays a well-behaved async task (and doesn't just busy-loop).
        await asyncio.sleep(0)

        # Throttle towards our target rate rather than writing as fast
        # as physically possible -- keeps the simulation realistic and
        # measurable rather than just maxing out the CPU.
        batch_elapsed = time.perf_counter() - batch_start
        target_batch_time = BATCH_SIZE / TARGET_ORDERS_PER_SECOND
        sleep_time = target_batch_time - batch_elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

    total_elapsed = time.perf_counter() - start_time
    orders_per_second = order_id / total_elapsed if total_elapsed > 0 else 0

    print(f"Firehose finished: wrote {order_id} orders in {total_elapsed:.2f}s "
          f"(~{orders_per_second:,.0f} orders/sec).")
    print(f"Final write index (total orders ever written): {rb.current_write_index()}")


async def main():
    rb = RingBuffer(BUFFER_PATH, capacity=BUFFER_CAPACITY, create=True)
    try:
        await firehose(rb)

        # Sanity check: read back a handful of the most recent orders.
        print("\nSample of the last 5 orders written:")
        write_index = rb.current_write_index()
        for i in range(max(0, write_index - 5), write_index):
            order = rb.read_order(i % BUFFER_CAPACITY)
            print(f"  slot {i % BUFFER_CAPACITY}: {order}")
    finally:
        rb.close()


if __name__ == "__main__":
    asyncio.run(main())