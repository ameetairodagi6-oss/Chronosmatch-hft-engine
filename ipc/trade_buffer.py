
"""Memory-mapped IPC queue for matched trades."""

import mmap
import os
import struct

RECORD_FORMAT = "<QQdI"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)  # 28 bytes
HEADER_SIZE = 24  # write index, read index, stop flag


class TradeBuffer:
    """Single-producer, single-consumer mmap trade queue."""

    def __init__(self, path, capacity=100_000, create=False):
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self.path = os.fspath(path)
        self.capacity = capacity
        self.total_size = HEADER_SIZE + capacity * RECORD_SIZE

        exists = os.path.exists(self.path)
        if create or not exists:
            with open(self.path, "wb") as file:
                file.truncate(self.total_size)

        self._file = open(self.path, "r+b")

        if os.path.getsize(self.path) != self.total_size:
            self._file.close()
            raise ValueError("Trade buffer file size does not match capacity")

        self._mmap = mmap.mmap(self._file.fileno(), self.total_size)

        if create or not exists:
            struct.pack_into("<QQQ", self._mmap, 0, 0, 0, 0)

    def _indices(self):
        return struct.unpack_from("<QQQ", self._mmap, 0)

    def write_trade(self, buy_order_id, sell_order_id, price, quantity):
        write_index, read_index, stop_flag = self._indices()

        if stop_flag:
            raise RuntimeError("Trade buffer is stopping")

        if write_index - read_index >= self.capacity:
            raise BufferError("Trade buffer full; refusing to overwrite unread trades")

        offset = HEADER_SIZE + (write_index % self.capacity) * RECORD_SIZE
        struct.pack_into(
            RECORD_FORMAT,
            self._mmap,
            offset,
            int(buy_order_id),
            int(sell_order_id),
            float(price),
            int(quantity),
        )
        struct.pack_into("<Q", self._mmap, 0, write_index + 1)
        return write_index

    def read_trade(self):
        write_index, read_index, _ = self._indices()

        if read_index >= write_index:
            return None

        offset = HEADER_SIZE + (read_index % self.capacity) * RECORD_SIZE
        buy_id, sell_id, price, quantity = struct.unpack_from(
            RECORD_FORMAT, self._mmap, offset
        )
        struct.pack_into("<Q", self._mmap, 8, read_index + 1)

        return {
            "buy_order_id": buy_id,
            "sell_order_id": sell_id,
            "price": price,
            "quantity": quantity,
        }

    def pending_count(self):
        write_index, read_index, _ = self._indices()
        return write_index - read_index

    def request_stop(self):
        struct.pack_into("<Q", self._mmap, 16, 1)

    def stop_requested(self):
        return struct.unpack_from("<Q", self._mmap, 16)[0] == 1

    def close(self):
        self._mmap.flush()
        self._mmap.close()
        self._file.close()
