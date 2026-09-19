"""
test_ring_buffer.py
--------------------
Day 2: Dedicated tests for the mmap ring buffer, focused on verifying
wraparound behavior (writing more orders than the buffer's capacity).

Run with:
    python tests/test_ring_buffer.py
"""

import os
import sys
import unittest

# Allow running this file directly without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipc.ring_buffer import RingBuffer


TEST_FILE = "test_wraparound.buf"


class TestRingBufferBasic(unittest.TestCase):
    def setUp(self):
        self.rb = RingBuffer(TEST_FILE, capacity=5, create=True)

    def tearDown(self):
        self.rb.close()
        if os.path.exists(TEST_FILE):
            os.remove(TEST_FILE)

    def test_single_write_read_roundtrip(self):
        """Writing one order and reading it back returns identical values."""
        slot = self.rb.write_order(order_id=42, side="B", price=99.5, quantity=10)
        order = self.rb.read_order(slot)

        self.assertEqual(order["order_id"], 42)
        self.assertEqual(order["side"], "B")
        self.assertAlmostEqual(order["price"], 99.5)
        self.assertEqual(order["quantity"], 10)

    def test_sequential_writes_fill_distinct_slots(self):
        """Writing fewer orders than capacity should land in slots 0..N-1, in order."""
        slots = [
            self.rb.write_order(order_id=i, side="B", price=100 + i, quantity=1)
            for i in range(5)
        ]
        self.assertEqual(slots, [0, 1, 2, 3, 4])

    def test_write_index_advances_monotonically(self):
        """The internal write index keeps counting up even as slots wrap."""
        for i in range(5):
            self.rb.write_order(order_id=i, side="B", price=1.0, quantity=1)
        self.assertEqual(self.rb.current_write_index(), 5)


class TestRingBufferWraparound(unittest.TestCase):
    """
    Capacity is intentionally small (3) so we can force wraparound
    quickly and verify old data is correctly overwritten by new data,
    without corrupting neighboring slots.
    """

    def setUp(self):
        self.rb = RingBuffer(TEST_FILE, capacity=3, create=True)

    def tearDown(self):
        self.rb.close()
        if os.path.exists(TEST_FILE):
            os.remove(TEST_FILE)

    def test_wraparound_reuses_slot_zero(self):
        # Fill the buffer exactly (slots 0, 1, 2).
        self.rb.write_order(order_id=1, side="B", price=10.0, quantity=1)
        self.rb.write_order(order_id=2, side="B", price=20.0, quantity=1)
        self.rb.write_order(order_id=3, side="B", price=30.0, quantity=1)

        # This 4th write should wrap around and land back in slot 0.
        slot = self.rb.write_order(order_id=4, side="S", price=40.0, quantity=2)
        self.assertEqual(slot, 0)

        # Slot 0 should now hold order_id=4, NOT the original order_id=1.
        order = self.rb.read_order(0)
        self.assertEqual(order["order_id"], 4)
        self.assertEqual(order["side"], "S")

    def test_wraparound_does_not_corrupt_neighboring_slots(self):
        # Fill the buffer, then wrap exactly once.
        for i in range(1, 4):  # writes to slots 0, 1, 2
            self.rb.write_order(order_id=i, side="B", price=float(i), quantity=1)

        # Wrap: overwrite slot 0 only.
        self.rb.write_order(order_id=99, side="S", price=9.9, quantity=9)

        # Slots 1 and 2 must be untouched.
        order_1 = self.rb.read_order(1)
        order_2 = self.rb.read_order(2)
        self.assertEqual(order_1["order_id"], 2)
        self.assertEqual(order_2["order_id"], 3)

    def test_multiple_full_wraparounds(self):
        """Write 10 orders into a capacity-3 buffer (more than 3 full laps)."""
        total_orders = 10
        for i in range(total_orders):
            self.rb.write_order(order_id=i, side="B", price=float(i), quantity=1)

        # write_index should track the TRUE total, not just the wrapped slot.
        self.assertEqual(self.rb.current_write_index(), total_orders)

        # The last 3 orders written (ids 7, 8, 9) should be the ones
        # currently sitting in slots 1, 2, 0 respectively (10 % 3 == 1,
        # so the next write would go to slot 1; the most recent write,
        # order_id=9, landed in slot (10-1) % 3 = 0).
        last_order = self.rb.read_order(0)
        self.assertEqual(last_order["order_id"], 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)