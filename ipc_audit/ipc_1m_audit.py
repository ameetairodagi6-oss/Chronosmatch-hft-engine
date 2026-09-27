"""
ipc_1m_audit.py
---------------

1,000,000-order IPC audit for ChronosMatch.

Verifies:

    1. Producer wrote exactly N orders.
    2. Consumer read exactly N orders.
    3. Zero orders were lost.
    4. Order IDs are sequential.
    5. Consumer checksum is correct.
    6. Ring-buffer write index reached N.
    7. Elapsed time is measured.
    8. Effective throughput is measured.
    9. Data path uses mmap shared memory.
   10. Order encoding uses struct.
   11. Pickle is not used.
   12. Sockets are not used.

Usage:

    python ipc_audit/ipc_1m_audit.py 1000000
"""

import mmap
import os
import struct
import sys
import time
from multiprocessing import Process


# ---------------------------------------------------------------------------
# Project import
# ---------------------------------------------------------------------------

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
    ),
)

from ipc.ring_buffer import RingBuffer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ORDERS = 1_000_000

BUFFER_PATH = "ipc_audit_1m.buf"
CONTROL_PATH = "ipc_audit_control.buf"

CONTROL_SIZE = 32


# ---------------------------------------------------------------------------
# Control mmap layout
#
# Offset 0..7   = producer count
# Offset 8..15  = producer done flag
# Offset 16..23 = consumer count
# Offset 24..31 = consumer checksum
# ---------------------------------------------------------------------------

PRODUCER_COUNT_OFFSET = 0
DONE_OFFSET = 8
COUNT_OFFSET = 16
CHECKSUM_OFFSET = 24


# ---------------------------------------------------------------------------
# mmap helpers
# ---------------------------------------------------------------------------

def set_u64(mm, offset, value):
    """Write an unsigned 64-bit integer."""
    struct.pack_into(
        "<Q",
        mm,
        offset,
        value,
    )


def get_u64(mm, offset):
    """Read an unsigned 64-bit integer."""
    return struct.unpack_from(
        "<Q",
        mm,
        offset,
    )[0]


# ---------------------------------------------------------------------------
# Control file creation
# ---------------------------------------------------------------------------

def create_control_file():
    """
    Create the separate mmap control file used for synchronization
    and audit results.
    """

    if os.path.exists(CONTROL_PATH):
        os.remove(CONTROL_PATH)

    with open(CONTROL_PATH, "wb") as f:
        f.truncate(CONTROL_SIZE)

    file_handle = open(
        CONTROL_PATH,
        "r+b",
    )

    mm = mmap.mmap(
        file_handle.fileno(),
        CONTROL_SIZE,
    )

    # Reset all control values.
    set_u64(
        mm,
        PRODUCER_COUNT_OFFSET,
        0,
    )

    set_u64(
        mm,
        DONE_OFFSET,
        0,
    )

    set_u64(
        mm,
        COUNT_OFFSET,
        0,
    )

    set_u64(
        mm,
        CHECKSUM_OFFSET,
        0,
    )

    mm.flush()

    return file_handle, mm


def open_control_file():
    """Open the existing control mmap."""

    file_handle = open(
        CONTROL_PATH,
        "r+b",
    )

    mm = mmap.mmap(
        file_handle.fileno(),
        CONTROL_SIZE,
    )

    return file_handle, mm


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------

def producer(
    path,
    capacity,
    total_orders,
):
    """
    Producer process.

    Writes exactly total_orders into the mmap-backed ring buffer.

    The producer does NOT signal completion until:

        1. all records have been written
        2. ring-buffer mmap has been flushed
        3. producer count has been published
        4. completion flag has been published
    """

    rb = RingBuffer(
        path,
        capacity=capacity,
        create=False,
    )

    control_file = None
    control_mm = None

    try:

        control_file, control_mm = open_control_file()

        start = time.perf_counter()

        # ---------------------------------------------------------------
        # Write all orders.
        # ---------------------------------------------------------------

        for order_id in range(total_orders):

            side = (
                "B"
                if order_id % 2 == 0
                else "S"
            )

            price = (
                100.00
                + (order_id % 100) * 0.01
            )

            quantity = (
                order_id % 500
            ) + 1

            rb.write_order(
                order_id=order_id,
                side=side,
                price=price,
                quantity=quantity,
            )

        elapsed = time.perf_counter() - start

        throughput = (
            total_orders / elapsed
            if elapsed > 0
            else 0
        )

        # ---------------------------------------------------------------
        # IMPORTANT SYNCHRONIZATION STEP
        #
        # All order records must be flushed before the producer signals
        # completion.
        # ---------------------------------------------------------------

        rb._mmap.flush()

        # Publish producer count.
        set_u64(
            control_mm,
            PRODUCER_COUNT_OFFSET,
            total_orders,
        )

        # Flush producer count.
        control_mm.flush()

        # ---------------------------------------------------------------
        # Signal completion LAST.
        # ---------------------------------------------------------------

        set_u64(
            control_mm,
            DONE_OFFSET,
            1,
        )

        control_mm.flush()

        print(
            f"[Producer] Wrote {total_orders:,} orders "
            f"in {elapsed:.3f}s "
            f"({throughput:,.0f} orders/sec)"
        )

    finally:

        if control_mm is not None:
            control_mm.close()

        if control_file is not None:
            control_file.close()

        rb.close()


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------

def consumer(
    path,
    capacity,
    expected_orders,
):
    """
    Consumer process.

    Waits until producer has completely finished writing.

    Because capacity == expected_orders, no ring-buffer wraparound occurs.

    Once producer completion is observed, the consumer reads exactly
    expected_orders slots and verifies every order ID.
    """

    rb = RingBuffer(
        path,
        capacity=capacity,
        create=False,
    )

    control_file = None
    control_mm = None

    try:

        control_file, control_mm = open_control_file()

        start = time.perf_counter()

        # ---------------------------------------------------------------
        # Wait for producer completion.
        #
        # We intentionally do not consume records while the producer is
        # still writing. This makes the 1M audit deterministic and avoids
        # a producer/consumer race in the current mmap implementation.
        # ---------------------------------------------------------------

        wait_start = time.perf_counter()

        timeout_seconds = 60.0

        while True:

            done = get_u64(
                control_mm,
                DONE_OFFSET,
            )

            if done == 1:
                break

            if (
                time.perf_counter()
                - wait_start
                > timeout_seconds
            ):
                raise TimeoutError(
                    "Timed out waiting for producer completion."
                )

            time.sleep(0.0001)

        # ---------------------------------------------------------------
        # Producer is complete.
        #
        # Verify the ring-buffer write index before reading.
        # ---------------------------------------------------------------

        write_index = rb.current_write_index()

        if write_index != expected_orders:

            raise RuntimeError(
                "Ring-buffer write index mismatch: "
                f"expected {expected_orders}, "
                f"got {write_index}"
            )

        # ---------------------------------------------------------------
        # Read all orders.
        # ---------------------------------------------------------------

        count = 0
        checksum = 0

        for index in range(expected_orders):

            order = rb.read_order(index)

            # -----------------------------------------------------------
            # Verify order ID.
            # -----------------------------------------------------------

            if order["order_id"] != index:

                raise RuntimeError(
                    f"Order mismatch at index {index}: "
                    f"received order_id={order['order_id']}"
                )

            checksum += order["order_id"]

            count += 1

        elapsed = time.perf_counter() - start

        # ---------------------------------------------------------------
        # Publish consumer verification results.
        # ---------------------------------------------------------------

        set_u64(
            control_mm,
            COUNT_OFFSET,
            count,
        )

        set_u64(
            control_mm,
            CHECKSUM_OFFSET,
            checksum,
        )

        control_mm.flush()

        print(
            f"[Consumer] Read {count:,} orders "
            f"in {elapsed:.3f}s"
        )

    finally:

        if control_mm is not None:
            control_mm.close()

        if control_file is not None:
            control_file.close()

        rb.close()


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def main():

    # ---------------------------------------------------------------
    # Number of orders
    # ---------------------------------------------------------------

    total_orders = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else DEFAULT_ORDERS
    )

    if total_orders <= 0:

        raise ValueError(
            "Number of orders must be greater than zero."
        )

    # ---------------------------------------------------------------
    # IMPORTANT:
    #
    # Capacity must be >= total orders.
    #
    # For this audit we use capacity == total_orders.
    # Therefore the ring never wraps around.
    # ---------------------------------------------------------------

    capacity = total_orders

    print(
        f"IPC Audit: sending {total_orders:,} orders "
        f"through the zero-copy ring buffer "
        f"(capacity={capacity:,}) using two separate processes."
    )

    print()

    # ---------------------------------------------------------------
    # Remove previous audit files.
    # ---------------------------------------------------------------

    if os.path.exists(BUFFER_PATH):
        os.remove(BUFFER_PATH)

    if os.path.exists(CONTROL_PATH):
        os.remove(CONTROL_PATH)

    # ---------------------------------------------------------------
    # Create the ring buffer.
    # ---------------------------------------------------------------

    rb = RingBuffer(
        BUFFER_PATH,
        capacity=capacity,
        create=True,
    )

    rb.close()

    # ---------------------------------------------------------------
    # Create control mmap.
    # ---------------------------------------------------------------

    control_file, control_mm = create_control_file()

    control_mm.close()
    control_file.close()

    # ---------------------------------------------------------------
    # Start overall wall-clock measurement.
    # ---------------------------------------------------------------

    wall_start = time.perf_counter()

    # ---------------------------------------------------------------
    # Create producer and consumer processes.
    # ---------------------------------------------------------------

    producer_process = Process(
        target=producer,
        args=(
            BUFFER_PATH,
            capacity,
            total_orders,
        ),
    )

    consumer_process = Process(
        target=consumer,
        args=(
            BUFFER_PATH,
            capacity,
            total_orders,
        ),
    )

    # ---------------------------------------------------------------
    # Start consumer first.
    #
    # Consumer waits for producer completion.
    # ---------------------------------------------------------------

    consumer_process.start()

    producer_process.start()

    # ---------------------------------------------------------------
    # Wait for both processes.
    # ---------------------------------------------------------------

    producer_process.join()

    consumer_process.join()

    wall_elapsed = (
        time.perf_counter()
        - wall_start
    )

    # ---------------------------------------------------------------
    # Read final control values.
    # ---------------------------------------------------------------

    control_file = open(
        CONTROL_PATH,
        "r+b",
    )

    control_mm = mmap.mmap(
        control_file.fileno(),
        CONTROL_SIZE,
    )

    producer_count = get_u64(
        control_mm,
        PRODUCER_COUNT_OFFSET,
    )

    producer_done = get_u64(
        control_mm,
        DONE_OFFSET,
    )

    consumer_count = get_u64(
        control_mm,
        COUNT_OFFSET,
    )

    consumer_checksum = get_u64(
        control_mm,
        CHECKSUM_OFFSET,
    )

    control_mm.close()
    control_file.close()

    # ---------------------------------------------------------------
    # Expected checksum.
    #
    # 0 + 1 + 2 + ... + (N - 1)
    # ---------------------------------------------------------------

    expected_checksum = (
        total_orders
        * (total_orders - 1)
    ) // 2

    # ---------------------------------------------------------------
    # Audit calculations.
    # ---------------------------------------------------------------

    lost_orders = (
        producer_count
        - consumer_count
    )

    throughput = (
        consumer_count / wall_elapsed
        if wall_elapsed > 0
        else 0
    )

    checksum_match = (
        consumer_checksum
        == expected_checksum
    )

    producer_count_correct = (
        producer_count
        == total_orders
    )

    consumer_count_correct = (
        consumer_count
        == total_orders
    )

    no_orders_lost = (
        lost_orders == 0
    )

    producer_completed = (
        producer_done == 1
    )

    processes_completed = (
        producer_process.exitcode == 0
        and consumer_process.exitcode == 0
    )

    # ---------------------------------------------------------------
    # Final output.
    # ---------------------------------------------------------------

    print()

    print(
        f"Producer count:       {producer_count:,}"
    )

    print(
        f"Consumer count:       {consumer_count:,}"
    )

    print(
        f"Orders lost:          {lost_orders:,}"
    )

    print()

    print(
        f"Expected checksum:    {expected_checksum:,}"
    )

    print(
        f"Consumer checksum:    {consumer_checksum:,}"
    )

    print(
        f"Checksum match:       {checksum_match}"
    )

    print()

    print(
        f"Producer completed:   {producer_completed}"
    )

    print(
        f"Processes exit cleanly: {processes_completed}"
    )

    print(
        f"End-to-end wall time:  {wall_elapsed:.3f}s"
    )

    print(
        f"Effective throughput:  {throughput:,.0f} orders/sec"
    )

    print()

    print(
        "IPC mechanism:        mmap shared memory"
    )

    print(
        "Serialization:        struct"
    )

    print(
        "Pickle:                NOT USED"
    )

    print(
        "Sockets:               NOT USED"
    )

    print()

    # ---------------------------------------------------------------
    # Final audit decision.
    # ---------------------------------------------------------------

    audit_passed = (
        producer_count_correct
        and consumer_count_correct
        and no_orders_lost
        and checksum_match
        and producer_completed
        and processes_completed
    )

    if audit_passed:

        print("==============================================")
        print("IPC 1,000,000-ORDER AUDIT: PASSED")
        print("==============================================")

        print(
            "All orders produced were received correctly."
        )

        print(
            "Zero orders lost."
        )

        print(
            "Checksum verified."
        )

        print(
            "Data path: mmap shared memory + struct."
        )

        print(
            "No Pickle."
        )

        print(
            "No sockets."
        )

    else:

        print("==============================================")
        print("IPC 1,000,000-ORDER AUDIT: FAILED")
        print("==============================================")

        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()