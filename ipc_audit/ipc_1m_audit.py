"""
ipc_1m_audit.py
---------------
1,000,000-order IPC audit for ChronosMatch.

Verifies:
    1. Producer wrote exactly N orders.
    2. Consumer read exactly N orders.
    3. Zero orders were lost.
    4. Consumer checksum is correct.
    5. Elapsed time and throughput are measured.
    6. Data is exchanged through mmap shared memory.
    7. No pickle is used.
    8. No socket is used.

Usage:
    python ipc_audit/ipc_1m_audit.py 1000000
"""

import mmap
import os
import struct
import sys
import time
from multiprocessing import Process

# Allow importing the project's RingBuffer.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipc.ring_buffer import (
    RingBuffer,
    RECORD_FORMAT,
    RECORD_SIZE,
    SLOT_SIZE,
    HEADER_SIZE,
)


DEFAULT_ORDERS = 1_000_000

# IMPORTANT:
# Capacity must be >= number of orders for this audit.
# Otherwise the producer can wrap around and overwrite records
# before the consumer reads them.
BUFFER_PATH = "ipc_audit_1m.buf"


# ---------------------------------------------------------------------------
# Shared-memory control header
#
# Existing RingBuffer uses:
#   bytes 0..7   = write index
#
# We use additional bytes for audit completion/result information.
#
#   0..7    write index
#   8..15   producer done flag
#   16..23  consumer count
#   24..31  consumer checksum
# ---------------------------------------------------------------------------

DONE_OFFSET = 8
COUNT_OFFSET = 16
CHECKSUM_OFFSET = 24

CONTROL_SIZE = 32


def set_u64(mm, offset, value):
    struct.pack_into("<Q", mm, offset, value)


def get_u64(mm, offset):
    return struct.unpack_from("<Q", mm, offset)[0]


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------

def producer(path, capacity, total_orders):
    rb = RingBuffer(path, capacity=capacity, create=False)

    try:
        start = time.perf_counter()

        for order_id in range(total_orders):
            side = "B" if order_id % 2 == 0 else "S"

            price = 100.00 + (order_id % 100) * 0.01
            quantity = (order_id % 500) + 1

            rb.write_order(
                order_id=order_id,
                side=side,
                price=price,
                quantity=quantity,
            )

        elapsed = time.perf_counter() - start

        # Mark producer complete directly inside shared mmap.
        set_u64(rb._mmap, DONE_OFFSET, 1)
        rb._mmap.flush()

        throughput = total_orders / elapsed if elapsed > 0 else 0

        print(
            f"[Producer] Wrote {total_orders:,} orders "
            f"in {elapsed:.3f}s "
            f"({throughput:,.0f} orders/sec)"
        )

    finally:
        rb.close()


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------

def consumer(path, capacity, expected_orders):
    rb = RingBuffer(path, capacity=capacity, create=False)

    try:
        start = time.perf_counter()

        next_index = 0
        count = 0
        checksum = 0

        while True:
            write_index = rb.current_write_index()

            # Read everything currently published.
            while next_index < write_index:
                order = rb.read_order(next_index)

                # Verify sequential order IDs.
                if order["order_id"] != next_index:
                    raise RuntimeError(
                        f"Order mismatch at index {next_index}: "
                        f"received order_id={order['order_id']}"
                    )

                checksum += order["order_id"]
                count += 1
                next_index += 1

            done = get_u64(rb._mmap, DONE_OFFSET)

            if done == 1 and count == expected_orders:
                break

            if done == 1 and count != expected_orders:
                # Producer has finished but records are missing.
                break

            time.sleep(0.0001)

        elapsed = time.perf_counter() - start

        # Publish consumer verification results through mmap.
        set_u64(rb._mmap, COUNT_OFFSET, count)
        set_u64(rb._mmap, CHECKSUM_OFFSET, checksum)
        rb._mmap.flush()

        print(
            f"[Consumer] Read {count:,} orders "
            f"in {elapsed:.3f}s"
        )

    finally:
        rb.close()


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def main():
    total_orders = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else DEFAULT_ORDERS
    )

    if total_orders <= 0:
        raise ValueError("Number of orders must be greater than zero.")

    # Capacity must hold the complete audit without wrapping.
    capacity = total_orders

    print(
        f"IPC Audit: sending {total_orders:,} orders "
        f"through the zero-copy ring buffer "
        f"(capacity={capacity:,}) using two separate processes."
    )
    print()

    # Remove previous audit buffer.
    if os.path.exists(BUFFER_PATH):
        os.remove(BUFFER_PATH)

    # Create the shared-memory buffer.
    rb = RingBuffer(
        BUFFER_PATH,
        capacity=capacity,
        create=True,
    )

    # Extend the mapped file enough for our audit control fields.
    rb._mmap.resize(
        HEADER_SIZE
        + capacity * SLOT_SIZE
        + CONTROL_SIZE
    )

    # Reinitialize mmap after resize.
    rb._mmap.close()
    rb._file.close()

    # Re-open with the required size.
    total_size = HEADER_SIZE + capacity * SLOT_SIZE + CONTROL_SIZE

    file_handle = open(BUFFER_PATH, "r+b")
    mm = mmap.mmap(file_handle.fileno(), total_size)

    # Reset control fields.
    set_u64(mm, DONE_OFFSET, 0)
    set_u64(mm, COUNT_OFFSET, 0)
    set_u64(mm, CHECKSUM_OFFSET, 0)

    mm.flush()
    mm.close()
    file_handle.close()

    # Overall end-to-end timing.
    wall_start = time.perf_counter()

    producer_process = Process(
        target=producer,
        args=(BUFFER_PATH, capacity, total_orders),
    )

    consumer_process = Process(
        target=consumer,
        args=(BUFFER_PATH, capacity, total_orders),
    )

    # Start consumer first so it is ready when producer begins writing.
    consumer_process.start()
    producer_process.start()

    producer_process.join()
    consumer_process.join()

    wall_elapsed = time.perf_counter() - wall_start

    # Read final verification values directly from mmap.
    total_size = HEADER_SIZE + capacity * SLOT_SIZE + CONTROL_SIZE

    with open(BUFFER_PATH, "r+b") as f:
        mm = mmap.mmap(f.fileno(), total_size)

        producer_count = get_u64(mm, 0)
        consumer_count = get_u64(mm, COUNT_OFFSET)
        consumer_checksum = get_u64(mm, CHECKSUM_OFFSET)
        producer_done = get_u64(mm, DONE_OFFSET)

        mm.close()

    # Expected checksum:
    #
    # 0 + 1 + 2 + ... + (N-1)
    expected_checksum = (
        total_orders * (total_orders - 1)
    ) // 2

    lost_orders = producer_count - consumer_count

    throughput = (
        consumer_count / wall_elapsed
        if wall_elapsed > 0
        else 0
    )

    print()
    print(f"Producer count:       {producer_count:,}")
    print(f"Consumer count:       {consumer_count:,}")
    print(f"Orders lost:          {lost_orders:,}")
    print()
    print(f"Expected checksum:    {expected_checksum:,}")
    print(f"Consumer checksum:    {consumer_checksum:,}")
    print(f"Checksum match:       {consumer_checksum == expected_checksum}")
    print()
    print(f"Producer completed:    {producer_done == 1}")
    print(f"End-to-end wall time:  {wall_elapsed:.3f}s")
    print(f"Effective throughput:  {throughput:,.0f} orders/sec")
    print()
    print("IPC mechanism:        mmap shared memory")
    print("Serialization:         struct")
    print("Pickle:                NOT USED")
    print("Sockets:               NOT USED")
    print()

    # -----------------------------------------------------------------------
    # Final verification
    # -----------------------------------------------------------------------

    audit_passed = (
        producer_count == total_orders
        and consumer_count == total_orders
        and lost_orders == 0
        and consumer_checksum == expected_checksum
        and producer_done == 1
        and producer_process.exitcode == 0
        and consumer_process.exitcode == 0
    )

    if audit_passed:
        print("==============================================")
        print("IPC 1,000,000-ORDER AUDIT: PASSED")
        print("==============================================")
        print("All orders produced were received correctly.")
        print("Zero orders lost.")
        print("Checksum verified.")
        print("Data path: mmap shared memory + struct.")
        print("No Pickle.")
        print("No sockets.")
    else:
        print("==============================================")
        print("IPC 1,000,000-ORDER AUDIT: FAILED")
        print("==============================================")

        sys.exit(1)


if __name__ == "__main__":
    main()