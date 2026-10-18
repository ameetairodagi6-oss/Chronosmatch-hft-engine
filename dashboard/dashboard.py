
"""
ChronosMatch - Live API Dashboard
---------------------------------
Displays live data from the ChronosMatch FastAPI backend.

Features:
- API connection and engine status
- Orders and matched trades
- Best bid, best ask, and spread
- Matching latency and throughput
- Resting bids and asks
- IPC method, encoding, and Pickle status
- Automatic refresh and connection-error handling

Run:
    python dashboard/dashboard.py

Press Q to quit.
"""

import curses
import json
import time
import urllib.error
import urllib.request


API_URL = "http://127.0.0.1:8000/api/status"
REFRESH_INTERVAL_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 1.0


def fetch_api_status():
    """Fetch the latest status from the FastAPI backend."""
    request = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            if response.status != 200:
                return None, f"HTTP status {response.status}"

            data = json.loads(response.read().decode("utf-8"))

            if not isinstance(data, dict):
                return None, "Unexpected API response format"

            return data, None

    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        return None, str(exc)


def format_value(value, decimals=None, suffix=""):
    """Format API values, including missing or null values."""
    if value is None:
        return "--"

    if decimals is not None:
        try:
            value = f"{float(value):.{decimals}f}"
        except (ValueError, TypeError):
            return "--"

    return f"{value}{suffix}"


def draw_line(stdscr, row, text, width):
    """Draw text without exceeding the terminal boundaries."""
    height, current_width = stdscr.getmaxyx()

    if row < 0 or row >= height or current_width <= 1:
        return

    safe_width = min(width, current_width - 1)

    if safe_width > 0:
        try:
            stdscr.addnstr(row, 0, str(text), safe_width)
        except curses.error:
            pass


def run_dashboard(stdscr):
    """Display live API data in a refreshing terminal dashboard."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.nodelay(True)
    stdscr.timeout(int(REFRESH_INTERVAL_SECONDS * 1000))

    api_status = None
    api_error = "Waiting for the API..."
    last_success_time = None

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break

        new_status, new_error = fetch_api_status()

        if new_status is not None:
            api_status = new_status
            api_error = None
            last_success_time = time.strftime("%H:%M:%S")
        else:
            api_error = new_error

        stdscr.erase()
        height, width = stdscr.getmaxyx()

        draw_line(
            stdscr, 0,
            "ChronosMatch - Live API Dashboard",
            width,
        )
        draw_line(stdscr, 1, "=" * 55, width)

        connection = (
            "CONNECTED" if api_error is None else "DISCONNECTED"
        )
        draw_line(
            stdscr, 3,
            f"API connection: {connection}",
            width,
        )

        if last_success_time:
            draw_line(
                stdscr, 4,
                f"Last successful update: {last_success_time}",
                width,
            )

        if api_status is None:
            draw_line(
                stdscr, 6,
                f"API error: {api_error}",
                width,
            )
            draw_line(
                stdscr, 8,
                "Check that the FastAPI server is running.",
                width,
            )
        else:
            data = api_status

            draw_line(
                stdscr, 6,
                f"Engine status: {data.get('status', '--')}",
                width,
            )
            draw_line(
                stdscr, 7,
                f"Orders submitted: {data.get('orders', '--')}",
                width,
            )
            draw_line(
                stdscr, 8,
                f"Trades matched:   {data.get('trades', '--')}",
                width,
            )

            draw_line(
                stdscr, 10,
                "--- Order Book ---",
                width,
            )
            draw_line(
                stdscr, 11,
                f"Best Bid: {format_value(data.get('best_bid'), 2)}",
                width,
            )
            draw_line(
                stdscr, 12,
                f"Best Ask: {format_value(data.get('best_ask'), 2)}",
                width,
            )
            draw_line(
                stdscr, 13,
                f"Spread:   {format_value(data.get('spread'), 4)}",
                width,
            )
            draw_line(
                stdscr, 14,
                f"Resting bids: {data.get('resting_bids', '--')}  "
                f"Resting asks: {data.get('resting_asks', '--')}",
                width,
            )

            draw_line(
                stdscr, 16,
                "--- Performance ---",
                width,
            )
            draw_line(
                stdscr, 17,
                f"Matching latency: "
                f"{format_value(data.get('latency_us'), 2, ' us')}",
                width,
            )
            draw_line(
                stdscr, 18,
                f"Throughput: {format_value(data.get('throughput'))}",
                width,
            )

            draw_line(
                stdscr, 20,
                "--- IPC Configuration ---",
                width,
            )
            draw_line(
                stdscr, 21,
                f"IPC: {data.get('ipc', '--')}  "
                f"Encoding: {data.get('encoding', '--')}",
                width,
            )
            draw_line(
                stdscr, 22,
                f"Pickle used: {data.get('pickle', '--')}",
                width,
            )

        draw_line(
            stdscr,
            height - 1,
            "Auto-refresh enabled | Press Q to quit",
            width,
        )

        stdscr.refresh()


def main():
    curses.wrapper(run_dashboard)


if __name__ == "__main__":
    main()
