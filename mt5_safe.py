"""
mt5_safe.py

Drop-in wrapper around mt5linux's MetaTrader5 bridge client that works around
a pickling bug in mt5linux==1.1.1: functions that return MT5's custom objects
(Tick, SymbolInfo, AccountInfo, TradePosition, TradeDeal, ...) fail with:

    _pickle.PicklingError: Can't pickle <class 'Tick'>: attribute lookup Tick
    on builtins failed

Root cause: those objects are dynamically-created classes on the Wine/remote
side, and rpyc's pickling can't locate the class definition to serialize it.

Workaround: instead of letting mt5linux fetch the raw object (which triggers
the broken pickle path), we ask the REMOTE side to convert the result to a
plain dict (`._asdict()`) before sending it back — plain dicts pickle fine.
On this side, we wrap the dict in a SimpleNamespace so existing code that
does `tick.bid`, `position.ticket`, etc. keeps working unmodified.

Usage — replace this:
    from mt5linux import MetaTrader5
    mt5 = MetaTrader5(host="localhost", port=18812)

With this:
    from mt5_safe import SafeMT5
    mt5 = SafeMT5(host="localhost", port=18812)

Everything else in your code (mt5.initialize(), mt5.order_send(), attribute
access on returned objects, etc.) stays exactly the same.
"""

from types import SimpleNamespace
from mt5linux import MetaTrader5


def _to_namespace(d):
    if isinstance(d, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in d.items()})
    if isinstance(d, list):
        return [_to_namespace(x) for x in d]
    return d


class SafeMT5:
    """
    Wraps a real mt5linux MetaTrader5 instance. Methods known to return
    problematic custom objects are overridden to fetch plain dicts via
    remote eval instead. Everything else is forwarded untouched via
    __getattr__.
    """

    # Methods that return a SINGLE object with attributes (need ._asdict())
    _SINGLE_OBJECT_METHODS = {
        "symbol_info_tick": "symbol",
        "symbol_info": "symbol",
        "account_info": None,
        "terminal_info": None,
        "order_check": "request",
    }

    # Methods that return a LIST of objects with attributes
    _LIST_METHODS = {
        "positions_get": None,   # accepts kwargs like symbol=, ticket=, group=
        "orders_get": None,
        "history_deals_get": None,
        "history_orders_get": None,
    }

    def __init__(self, *args, **kwargs):
        self._mt5 = MetaTrader5(*args, **kwargs)

    def __getattr__(self, name):
        # Anything not explicitly overridden below just forwards to the
        # real mt5linux instance (initialize, login, shutdown, symbol_select,
        # order_send, copy_rates_from_pos, constants like TRADE_ACTION_DEAL...)
        return getattr(self._mt5, name)

    # Single expression that converts an arbitrary MT5 object (and, one level
    # deep, any nested MT5 objects inside it — e.g. OrderSendResult.request)
    # into plain dicts of primitives. Two levels is enough for every MT5
    # structure we've seen (nested objects only ever contain primitives).
    _FLATTEN_1 = (
        "{k2: getattr(v, k2) for k2 in dir(v) "
        "if not k2.startswith('_') and not callable(getattr(v, k2))}"
    )
    _FLATTEN_0 = (
        "(lambda v: v if isinstance(v, (int, float, str, bool, type(None), dict, list)) "
        "else " + _FLATTEN_1 + ")"
    )

    def _eval_single(self, expr):
        """Fetch a single MT5 object as a plain (2-level-deep-flattened) dict,
        wrapped in a namespace. Built entirely on the REMOTE side, where the
        object is still real (not a proxy) — only primitives/dicts/lists
        ever cross the wire, avoiding the custom-class pickling bug."""
        code = (
            "(lambda _r: None if _r is None else ("
            "_r if isinstance(_r, (int, float, str, bool, dict)) else "
            "{k: " + self._FLATTEN_0 + "(getattr(_r, k)) for k in dir(_r) "
            "if not k.startswith('_') and not callable(getattr(_r, k))}"
            "))(" + expr + ")"
        )
        result = self._mt5._container.eval(code)
        return _to_namespace(result)

    def _eval_list(self, expr):
        """Fetch a list/tuple of MT5 objects as a list of plain flattened
        dicts (wrapped in namespaces), same approach as _eval_single applied
        per item."""
        code = (
            "(lambda _r: None if _r is None else ["
            "(x if isinstance(x, (int, float, str, bool, dict)) else "
            "{k: " + self._FLATTEN_0 + "(getattr(x, k)) for k in dir(x) "
            "if not k.startswith('_') and not callable(getattr(x, k))}) "
            "for x in _r"
            "])(" + expr + ")"
        )
        result = self._mt5._container.eval(code)
        return _to_namespace(result)

    def _fmt_args(self, args, kwargs):
        parts = [repr(a) for a in args]
        parts += [f"{k}={v!r}" for k, v in kwargs.items()]
        return ", ".join(parts)

    def symbol_info_tick(self, symbol):
        return self._eval_single(f'mt5.symbol_info_tick({symbol!r})')

    def symbol_info(self, symbol):
        return self._eval_single(f'mt5.symbol_info({symbol!r})')

    def account_info(self):
        return self._eval_single('mt5.account_info()')

    def terminal_info(self):
        return self._eval_single('mt5.terminal_info()')

    def order_check(self, request):
        return self._eval_single(f'mt5.order_check({request!r})')

    def positions_get(self, **kwargs):
        return self._eval_list(f'mt5.positions_get({self._fmt_args((), kwargs)})')

    def orders_get(self, **kwargs):
        return self._eval_list(f'mt5.orders_get({self._fmt_args((), kwargs)})')

    def history_deals_get(self, *args, **kwargs):
        return self._eval_list(f'mt5.history_deals_get({self._fmt_args(args, kwargs)})')

    def history_orders_get(self, *args, **kwargs):
        return self._eval_list(f'mt5.history_orders_get({self._fmt_args(args, kwargs)})')

    def order_send(self, request):
        # order_send's result (OrderSendResult) is also a namedtuple-like —
        # same treatment as the single-object methods.
        return self._eval_single(f'mt5.order_send({request!r})')