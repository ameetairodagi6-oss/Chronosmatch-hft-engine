
import pytest

from ipc.trade_buffer import TradeBuffer


def test_buffer_refuses_to_overwrite_unread_trades(tmp_path):
    buffer_path = tmp_path / "test_trades.buf"
    buffer = TradeBuffer(
        str(buffer_path),
        capacity=2,
        create=True,
    )

    try:
        buffer.write_trade(1, 2, 100.0, 5)
        buffer.write_trade(3, 4, 101.0, 10)

        assert buffer.pending_count() == 2

        with pytest.raises(BufferError):
            buffer.write_trade(5, 6, 102.0, 15)

        first = buffer.read_trade()
        assert first["buy_order_id"] == 1

        buffer.write_trade(5, 6, 102.0, 15)
        assert buffer.pending_count() == 2

        print("BUFFER FULL TEST PASSED")

    finally:
        buffer.close()
