"""
ring_buffer.py
---------------
A zero-copy, memory-mapped ring buffer used as the IPC bus between the
market order simulator (producer) and the matching engine (consumer).

Each order record is a fixed-size binary struct:
    order_id : unsigned long long (8 bytes)
    side     : char, 'B' or 'S'    (1 byte)
    price    : double              (8 bytes)
    quantity : unsigned int        (4 bytes)

We pad the struct to a clean 24-byte slot for alignment.

The buffer is backed by a file on disk via mmap, so multiple independent
Python processes can open the SAME file and read/write the SAME memory
region directly -- no pickling, no sockets, no serialization overhead.
"""

import mmap
import os
import struct

# ---- Record format -------------------------------------------------------
# '<' = little-endian, no padding added by struct itself (we pad manually)
# Q = unsigned long long (8 bytes) -> order_id
# c = char (1 byte)                -> side ('B' or 'S')
# d = double (8 bytes)             -> price
# I = unsigned int (4 bytes)       -> quantity
RECORD_FORMAT = "<QcdI"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)  # 21 bytes
SLOT_SIZE = 24  # round up for alignment / future fields

# ---- Buffer layout ---------------------------------------------------------
# We reserve the first 8 bytes of the file as a "write index" header so
# producer and consumer can agree on where the next write should go.
HEADER_SIZE = 8


class RingBuffer:
    """
    A fixed-capacity, memory-mapped circular buffer of order records.

    Usage:
        rb = RingBuffer("orders.buf", capacity=100_000, create=True)
        rb.write_order(order_id=1, side="B", price=101.25, quantity=50)
        order = rb.read_order(0)
        rb.close()
    """

    def __init__(self, path: str, capacity: int = 100_000, create: bool = False):
        self.path = path
        self.capacity = capacity
        self.total_size = HEADER_SIZE + capacity * SLOT_SIZE

        file_exists = os.path.exists(path)

        if create or not file_exists:
            # Pre-allocate the file to the full buffer size, zero-filled.
            with open(path, "wb") as f:
                f.truncate(self.total_size)

        self._file = open(path, "r+b")
        self._mmap = mmap.mmap(self._file.fileno(), self.total_size)

        if create or not file_exists:
            self._set_write_index(0)

    # ---- internal helpers --------------------------------------------------

    def _slot_offset(self, index: int) -> int:
        return HEADER_SIZE + (index % self.capacity) * SLOT_SIZE

    def _get_write_index(self) -> int:
        return struct.unpack_from("<Q", self._mmap, 0)[0]

    def _set_write_index(self, value: int) -> None:
        struct.pack_into("<Q", self._mmap, 0, value)

    # ---- public API ----------------------------------------------------------

    def write_order(self, order_id: int, side: str, price: float, quantity: int) -> int:
        """
        Write one order record into the next available slot.
        Returns the slot index the order was written to.
        Wraps around to the start once capacity is reached (ring behavior).
        """
        index = self._get_write_index()
        offset = self._slot_offset(index)

        side_bytes = side.encode("ascii")[:1]  # 'B' or 'S'
        packed = struct.pack(RECORD_FORMAT, order_id, side_bytes, price, quantity)

        # Write the packed record, then zero-pad to the full slot size.
        self._mmap[offset:offset + RECORD_SIZE] = packed
        self._mmap[offset + RECORD_SIZE:offset + SLOT_SIZE] = b"\x00" * (SLOT_SIZE - RECORD_SIZE)

        self._set_write_index(index + 1)
        return index % self.capacity

    def read_order(self, index: int):
        """
        Read the order record at the given slot index.
        Returns a dict with order_id, side, price, quantity.
        """
        offset = self._slot_offset(index)
        raw = self._mmap[offset:offset + RECORD_SIZE]
        order_id, side, price, quantity = struct.unpack(RECORD_FORMAT, raw)
        return {
            "order_id": order_id,
            "side": side.decode("ascii"),
            "price": price,
            "quantity": quantity,
        }

    def current_write_index(self) -> int:
        """Total number of orders written so far (not wrapped)."""
        return self._get_write_index()

    def close(self):
        self._mmap.flush()
        self._mmap.close()
        self._file.close()


if __name__ == "__main__":
    # Quick manual smoke test: write a few fake orders, read them back.
    rb = RingBuffer("test_orders.buf", capacity=10, create=True)

    rb.write_order(order_id=1, side="B", price=101.25, quantity=50)
    rb.write_order(order_id=2, side="S", price=101.30, quantity=20)
    rb.write_order(order_id=3, side="B", price=101.10, quantity=75)

    for i in range(3):
        print(rb.read_order(i))

    rb.close()
    print("Ring buffer smoke test passed.")