import json
import jsonpickle
from typing import Any

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


# ---------------------------------------------------------------------------
# Logger 
# ---------------------------------------------------------------------------
class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [self.compress_state(state, ""), self.compress_orders(orders), conversions, "", ""]
            )
        )
        max_item_length = (self.max_log_length - base_length) // 3
        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )
        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        return [
            [t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
            for arr in trades.values()
            for t in arr
        ]

    def compress_observations(self, observations: Observation) -> list[Any]:
        conv = {}
        for p, o in observations.conversionObservations.items():
            conv[p] = [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff,
                       o.importTariff, o.sugarPrice, o.sunlightIndex]
        return [observations.plainValueObservations, conv]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."
            if len(json.dumps(candidate)) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return out


logger = Logger()


# ---------------------------------------------------------------------------
# Constants — derived from 3-day data analysis
# ---------------------------------------------------------------------------

# ASH_COATED_OSMIUM
# - Fair value: fixed at 10,000 (mean=10000.20, std=5.35 across all days)
# - Dominant spread: 16 ticks (best_bid ≈ 9993-9994, best_ask ≈ 10009-10010)
# - Wall bids (vol≥25) cluster at 9991-9992; wall asks at 10012-10013
# - Lag-1 autocorr of mid changes: -0.50 (strong mean reversion, same as EMERALDS)
# - Trades spread across 9979-10026 (not just wall prices like EMERALDS)
ACO_SYM   = "ASH_COATED_OSMIUM"
ACO_LIMIT = 80    
ACO_FAIR  = 10_000

# INTARIAN_PEPPER_ROOT
# - Perfect linear uptrend: +1,000 units/day, slope = 0.001002 per timestamp unit
# - Day starts: Day-2≈9998.5, Day-1≈10998.5, Day0≈11998.5 (+1000 each day)
# - Residual noise around trend: std≈2, max≈10 (almost perfectly linear)
# - Lag-1 autocorr of mid changes: -0.50 (mean reversion on top of trend)
# - Spread: 13-14 ticks (half-integers, e.g. 11998.5)
# - ~332 trades/day, avg qty 5.2, avg gap 3034 ticks between trades
PEPPER_SYM   = "INTARIAN_PEPPER_ROOT"
PEPPER_LIMIT = 80    
PEPPER_SLOPE = 0.001002  # seashells per timestamp unit (verified across all 3 days)


# ---------------------------------------------------------------------------
# Persistent state (survives between run() calls via traderData)
# ---------------------------------------------------------------------------
class State:
    def __init__(self) -> None:
        # PEPPER: estimated price at timestamp=0 this day (updated on first tick)
        self.pepper_base: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_mid(order_depth: OrderDepth) -> float | None:
    """Best-bid/ask midpoint. Returns None if either side is empty."""
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    return (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2

def get_best_bid(order_depth: OrderDepth) -> int | None:
    return max(order_depth.buy_orders) if order_depth.buy_orders else None

def get_best_ask(order_depth: OrderDepth) -> int | None:
    return min(order_depth.sell_orders) if order_depth.sell_orders else None

# ---------------------------------------------------------------------------
# ASH_COATED_OSMIUM strategy stub
#
# Key insight: behaves like a noisier EMERALDS.
# Fair value is anchored at 10,000. Mean-reverts aggressively (-0.50 autocorr).
# The book floats: typical spread=16, best_bid≈9993-9994, best_ask≈10009-10010.
# Unlike EMERALDS, market trades happen at many price points (9979-10026),
# not just at fixed wall prices — so posting inside the spread should earn fills.
# ---------------------------------------------------------------------------

def aco_orders(order_depth: OrderDepth, position: int) -> list[Order]:
    orders: list[Order] = []

    buy_cap  = ACO_LIMIT - position   # remaining capacity to buy
    sell_cap = ACO_LIMIT + position   # remaining capacity to sell

    # TODO: implement strategy
    # Suggested approach:
    #   1. Aggressive: take any ask <= ACO_FAIR - N or bid >= ACO_FAIR + N
    #   2. Passive: post quotes inside the typical 16-tick spread (e.g. 9993/10009)
    #   3. Apply inventory skew if needed (similar to TOMATOES)

    return orders


# ---------------------------------------------------------------------------
# INTARIAN_PEPPER_ROOT strategy stub
#
# Key insight: price rises at exactly 0.001002 per timestamp unit (~10/iteration).
# This is NOT a mean-reversion product — it's a pure uptrend carry trade.
# Holding max long from the start of each day captures +1,000 units/day.
# The noise (std≈2) is negligible compared to the trend signal.
# Fair value at time t = pepper_base + PEPPER_SLOPE * t
# ---------------------------------------------------------------------------
def pepper_orders(order_depth: OrderDepth, position: int, timestamp: int, state: State) -> list[Order]:
    orders: list[Order] = []

    mid = get_mid(order_depth)
    if mid is None:
        return orders

    buy_cap  = PEPPER_LIMIT - position
    sell_cap = PEPPER_LIMIT + position

    # Estimate base price (price at timestamp=0 this day) on first tick
    if state.pepper_base is None:
        state.pepper_base = mid - PEPPER_SLOPE * timestamp

    # Fair value at the current timestamp
    fair_value = state.pepper_base + PEPPER_SLOPE * timestamp

    # TODO: implement strategy
    # Suggested approach:
    #   1. Aggressive buy: take all asks up to fair_value + buffer (trend makes it profitable)
    #   2. Passive bid: post at best_bid + 1 to attract sellers quickly
    #   3. Almost never sell — only post asks far above fair_value if needed for inventory
    # Example skeleton:
    #   best_ask = get_best_ask(order_depth)
    #   for ap in sorted(order_depth.sell_orders):
    #       if ap > fair_value + 15 or buy_cap <= 0:
    #           break
    #       qty = min(abs(order_depth.sell_orders[ap]), buy_cap)
    #       orders.append(Order(PEPPER_SYM, ap, qty))
    #       buy_cap -= qty

    return orders


# ---------------------------------------------------------------------------
# Main Trader
# ---------------------------------------------------------------------------
class Trader:

    def bid(self) -> int:
        return 15

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        result: dict[Symbol, list[Order]] = {}
        conversions = 0

        # Restore persistent state from last iteration
        s: State = jsonpickle.decode(state.traderData) if state.traderData else State()

        # Reset pepper base at the very start of each day
        if state.timestamp == 0:
            s.pepper_base = None

        if ACO_SYM in state.order_depths:
            result[ACO_SYM] = aco_orders(
                state.order_depths[ACO_SYM],
                state.position.get(ACO_SYM, 0),
            )

        if PEPPER_SYM in state.order_depths:
            result[PEPPER_SYM] = pepper_orders(
                state.order_depths[PEPPER_SYM],
                state.position.get(PEPPER_SYM, 0),
                state.timestamp,
                s,
            )

        trader_data = jsonpickle.encode(s)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
