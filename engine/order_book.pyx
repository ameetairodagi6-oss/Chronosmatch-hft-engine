# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
order_book.pyx
---------------
Week 3: C-level Limit Order Book (LOB) matching engine.

Matching uses Price-Time Priority: the best price matches first, and at the
same price the order that arrived first matches first (FIFO).

What changed from Week 2
------------------------
Week 2 stored resting orders as Python `Order` objects inside Python lists and
built Python `Trade` objects while matching. Every one of those is a Python
object interaction inside the matching loop.

Now the whole matching path is plain C:

  * Orders and trades are C structs (COrder, CTrade), not Python objects.
  * Each side of the book is a C array (malloc/realloc) kept sorted so the
    BEST order is always the LAST element. Matching therefore reads and pops
    from the end in O(1).
  * `_match()` is a `nogil` C function. It cannot touch a Python object, so
    it cannot allocate a GC-tracked object, and the garbage collector has no
    reason to run while a trade is being matched.
  * Trades are written into a preallocated C buffer. Python `Trade` objects
    are only built afterwards, outside the matching loop, and only by the
    convenience method `submit_order()`.

Two entry points
----------------
  submit_order(...)       Python-friendly. Returns a list of `Trade` objects.
  submit_order_fast(...)  Hot path. Returns only the NUMBER of trades; read
                          them with trade_at(i). Creates no Python containers.

Metrics
-------
`time.perf_counter_ns()` is read immediately before and after the C matching
call (never inside it, since it is a Python function):

  last_matching_phase_ns   time spent inside the nogil C matching core
  last_order_latency_ns    whole submit call, including argument handling

Each figure includes the cost of one perf_counter_ns() call, so treat very
small values as an upper bound.

This file must be COMPILED before it can be imported from Python -- see
setup.py in the same folder.
"""

from libc.stdint cimport uint32_t, uint64_t
from libc.stdlib cimport free, realloc
from libc.string cimport memmove
from time import perf_counter_ns


# ---- C-level data layout ------------------------------------------------------

cdef struct COrder:
    uint64_t order_id
    double price
    uint32_t quantity
    uint64_t seq            # arrival number: gives FIFO priority at equal price


cdef struct CTrade:
    uint64_t buy_order_id
    uint64_t sell_order_id
    double price
    uint32_t quantity


cdef struct Side:
    COrder* data            # sorted so the best order is data[n - 1]
    Py_ssize_t n
    Py_ssize_t cap


cdef struct Book:
    Side bids               # ascending price: highest bid is last
    Side asks               # descending price: lowest ask is last
    CTrade* trades          # trades produced by the most recent order
    Py_ssize_t trades_cap
    Py_ssize_t n_trades
    uint64_t next_seq


# ---- C-level helpers (no Python objects, no GIL) ------------------------------

cdef int _reserve_side(Side* s) noexcept nogil:
    """Make room for one more order. Returns 0 on success, -1 if out of memory."""
    cdef Py_ssize_t newcap
    cdef COrder* p
    if s.n < s.cap:
        return 0
    newcap = s.cap * 2 if s.cap > 0 else 1024
    p = <COrder*> realloc(s.data, newcap * sizeof(COrder))
    if p == NULL:
        return -1
    s.data = p
    s.cap = newcap
    return 0


cdef int _reserve_trades(Book* b) noexcept nogil:
    """Make room for one more trade. Returns 0 on success, -1 if out of memory."""
    cdef Py_ssize_t newcap
    cdef CTrade* p
    if b.n_trades < b.trades_cap:
        return 0
    newcap = b.trades_cap * 2 if b.trades_cap > 0 else 64
    p = <CTrade*> realloc(b.trades, newcap * sizeof(CTrade))
    if p == NULL:
        return -1
    b.trades = p
    b.trades_cap = newcap
    return 0


cdef int _rest_bid(Side* s, COrder* o) noexcept nogil:
    """
    Insert a resting Buy, keeping the array ascending by price.

    Binary search finds the first slot whose price is >= the new price, and the
    new order goes in front of it. Among equal prices a newer order therefore
    sits at a LOWER index than an older one, so the oldest order at the best
    price is the one at the end, which is the one matched first (FIFO).
    """
    cdef Py_ssize_t lo = 0
    cdef Py_ssize_t hi = s.n
    cdef Py_ssize_t mid
    if _reserve_side(s) != 0:
        return -1
    while lo < hi:
        mid = (lo + hi) >> 1
        if s.data[mid].price < o.price:
            lo = mid + 1
        else:
            hi = mid
    memmove(&s.data[lo + 1], &s.data[lo], (s.n - lo) * sizeof(COrder))
    s.data[lo] = o[0]
    s.n += 1
    return 0


cdef int _rest_ask(Side* s, COrder* o) noexcept nogil:
    """
    Insert a resting Sell, keeping the array DEscending by price (lowest ask
    last). Same FIFO reasoning as _rest_bid.
    """
    cdef Py_ssize_t lo = 0
    cdef Py_ssize_t hi = s.n
    cdef Py_ssize_t mid
    if _reserve_side(s) != 0:
        return -1
    while lo < hi:
        mid = (lo + hi) >> 1
        if s.data[mid].price > o.price:
            lo = mid + 1
        else:
            hi = mid
    memmove(&s.data[lo + 1], &s.data[lo], (s.n - lo) * sizeof(COrder))
    s.data[lo] = o[0]
    s.n += 1
    return 0


cdef Py_ssize_t _match(Book* b, COrder* inc, bint is_buy) noexcept nogil:
    """
    The matching core. Pure C: no Python objects are touched.

    Matches `inc` against the opposite side while prices cross, writes each
    fill into b.trades, then rests any unfilled remainder.
    Returns the number of trades, or -1 if memory allocation failed.
    """
    cdef Side* opp
    cdef COrder* rest
    cdef CTrade* t
    cdef uint32_t q

    b.n_trades = 0
    inc.seq = b.next_seq
    b.next_seq += 1

    if is_buy:
        opp = &b.asks
    else:
        opp = &b.bids

    while inc.quantity > 0 and opp.n > 0:
        rest = &opp.data[opp.n - 1]            # best opposite order

        # Prices no longer cross -> nothing more to match.
        if is_buy:
            if rest.price > inc.price:
                break
        else:
            if rest.price < inc.price:
                break

        if _reserve_trades(b) != 0:
            return -1

        q = inc.quantity if inc.quantity < rest.quantity else rest.quantity

        t = &b.trades[b.n_trades]
        if is_buy:
            t.buy_order_id = inc.order_id
            t.sell_order_id = rest.order_id
        else:
            t.buy_order_id = rest.order_id
            t.sell_order_id = inc.order_id
        t.price = rest.price                   # the resting order sets the price
        t.quantity = q
        b.n_trades += 1

        inc.quantity -= q
        rest.quantity -= q
        if rest.quantity == 0:
            opp.n -= 1                         # fully filled: pop from the end

    if inc.quantity > 0:
        if is_buy:
            if _rest_bid(&b.bids, inc) != 0:
                return -1
        else:
            if _rest_ask(&b.asks, inc) != 0:
                return -1

    return b.n_trades


# ---- Python-facing record types ------------------------------------------------

cdef class Order:
    """A read-only snapshot of one resting order (used by the bids/asks views)."""
    cdef public unsigned long long order_id
    cdef public str side          # 'B' or 'S'
    cdef public double price
    cdef public unsigned int quantity

    def __init__(self, unsigned long long order_id, str side, double price,
                 unsigned int quantity):
        self.order_id = order_id
        self.side = side
        self.price = price
        self.quantity = quantity

    def __repr__(self):
        return (f"Order(id={self.order_id}, side={self.side}, "
                f"price={self.price}, qty={self.quantity})")


cdef class Trade:
    """A completed match between a buy order and a sell order."""
    cdef public unsigned long long buy_order_id
    cdef public unsigned long long sell_order_id
    cdef public double price
    cdef public unsigned int quantity

    def __init__(self, unsigned long long buy_order_id,
                 unsigned long long sell_order_id, double price,
                 unsigned int quantity):
        self.buy_order_id = buy_order_id
        self.sell_order_id = sell_order_id
        self.price = price
        self.quantity = quantity

    def __repr__(self):
        return (f"Trade(buy={self.buy_order_id}, sell={self.sell_order_id}, "
                f"price={self.price}, qty={self.quantity})")


# ---- The Limit Order Book --------------------------------------------------------

cdef class LimitOrderBook:
    """
    Resting Buy and Sell orders plus the matching engine.

    Public attributes kept from Week 2 so the dashboard, API and tests keep
    working: bids, asks (best first), trades, best_bid(), best_ask(), spread(),
    last_order_latency_ns, last_matching_phase_ns.
    """

    cdef Book _book
    cdef public list trades                     # Trade history (submit_order only)
    cdef public unsigned long long total_trades  # trade count (both entry points)
    cdef public unsigned long long last_order_latency_ns
    cdef public unsigned long long last_matching_phase_ns

    def __cinit__(self):
        self._book.bids.data = NULL
        self._book.bids.n = 0
        self._book.bids.cap = 0
        self._book.asks.data = NULL
        self._book.asks.n = 0
        self._book.asks.cap = 0
        self._book.trades = NULL
        self._book.trades_cap = 0
        self._book.n_trades = 0
        self._book.next_seq = 0

    def __init__(self):
        self.trades = []
        self.total_trades = 0
        self.last_order_latency_ns = 0
        self.last_matching_phase_ns = 0

    def __dealloc__(self):
        free(self._book.bids.data)
        free(self._book.asks.data)
        free(self._book.trades)

    # ---- internal ------------------------------------------------------------

    cdef Py_ssize_t _submit(self, unsigned long long order_id, bint is_buy,
                            double price, unsigned int quantity) except -2:
        """Run one order through the C core and record the timings."""
        cdef COrder inc
        cdef Py_ssize_t n
        cdef unsigned long long t_call = perf_counter_ns()
        cdef unsigned long long t_enter
        cdef unsigned long long t_exit

        inc.order_id = order_id
        inc.price = price
        inc.quantity = quantity
        inc.seq = 0

        t_enter = perf_counter_ns()             # trade enters the engine
        with nogil:
            n = _match(&self._book, &inc, is_buy)
        t_exit = perf_counter_ns()              # trade leaves the engine

        if n < 0:
            raise MemoryError("order book memory allocation failed")

        self.total_trades += n
        self.last_matching_phase_ns = t_exit - t_enter
        self.last_order_latency_ns = perf_counter_ns() - t_call
        return n

    cdef list _snapshot(self, Side* s, str side):
        """Best-first list of Order snapshots for one side of the book."""
        cdef list out = []
        cdef Py_ssize_t i = s.n - 1
        while i >= 0:
            out.append(Order(s.data[i].order_id, side,
                             s.data[i].price, s.data[i].quantity))
            i -= 1
        return out

    # ---- public API ------------------------------------------------------------

    def submit_order(self, unsigned long long order_id, str side,
                     double price, unsigned int quantity):
        """
        Submit an order and return the list of Trade objects it produced.

        Matching itself runs in C. The Trade objects are built afterwards,
        outside the matching loop.
        """
        cdef bint is_buy
        cdef Py_ssize_t n
        cdef Py_ssize_t i
        cdef CTrade* t
        cdef list new_trades

        if side == "B":
            is_buy = True
        elif side == "S":
            is_buy = False
        else:
            raise ValueError(f"side must be 'B' or 'S', got {side!r}")

        n = self._submit(order_id, is_buy, price, quantity)

        new_trades = []
        for i in range(n):
            t = &self._book.trades[i]
            new_trades.append(Trade(t.buy_order_id, t.sell_order_id,
                                    t.price, t.quantity))
        self.trades.extend(new_trades)
        return new_trades

    def submit_order_fast(self, unsigned long long order_id, bint is_buy,
                          double price, unsigned int quantity):
        """
        Hot path: submit an order and return only the number of trades.

        No Python containers are created. Read the fills with trade_at(i) for
        i in range(returned_count) before the next submit overwrites them.
        """
        return self._submit(order_id, is_buy, price, quantity)

    def trade_at(self, Py_ssize_t i):
        """Fill i of the most recent order as (buy_id, sell_id, price, qty)."""
        if i < 0 or i >= self._book.n_trades:
            raise IndexError("trade index out of range")
        return (self._book.trades[i].buy_order_id,
                self._book.trades[i].sell_order_id,
                self._book.trades[i].price,
                self._book.trades[i].quantity)

    def best_bid(self):
        """Highest resting Buy price, or None if the bid side is empty."""
        if self._book.bids.n == 0:
            return None
        return self._book.bids.data[self._book.bids.n - 1].price

    def best_ask(self):
        """Lowest resting Sell price, or None if the ask side is empty."""
        if self._book.asks.n == 0:
            return None
        return self._book.asks.data[self._book.asks.n - 1].price

    def spread(self):
        """Bid/Ask spread, or None if either side is empty."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    @property
    def bid_count(self):
        """Number of resting Buy orders (O(1), no snapshot)."""
        return self._book.bids.n

    @property
    def ask_count(self):
        """Number of resting Sell orders (O(1), no snapshot)."""
        return self._book.asks.n

    @property
    def bids(self):
        """Resting Buy orders, best (highest price) first, as Order snapshots."""
        return self._snapshot(&self._book.bids, "B")

    @property
    def asks(self):
        """Resting Sell orders, best (lowest price) first, as Order snapshots."""
        return self._snapshot(&self._book.asks, "S")