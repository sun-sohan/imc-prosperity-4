import json
import math
import sys
from typing import List, Dict

try:
    from datamodel import OrderDepth, TradingState, Order, ProsperityEncoder
except ModuleNotFoundError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
    from datamodel import OrderDepth, TradingState, Order, ProsperityEncoder


# ─────────────────────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────────────────────

class Logger:
    def __init__(self) -> None:
        self.logs = ""

    def print(self, *objects, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str) -> None:
        output = [
            self.compress_state(state),
            self.compress_orders(orders),
            conversions,
            trader_data,
            self.logs,
        ]
        print(json.dumps(output, cls=ProsperityEncoder, separators=(",", ":")))
        self.logs = ""

    def compress_state(self, state: TradingState):
        return [
            state.timestamp,
            state.traderData,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings):
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]

    def compress_order_depths(self, order_depths):
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}

    def compress_trades(self, trades):
        return [
            [t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
            for arr in trades.values() for t in arr
        ]

    def compress_observations(self, observations):
        conv = {}
        for product, obs in observations.conversionObservations.items():
            conv[product] = [
                obs.bidPrice, obs.askPrice, obs.transportFees,
                obs.exportTariff, obs.importTariff, obs.sunlight, obs.humidity,
            ]
        return [observations.plainValueObservations, conv]

    def compress_orders(self, orders):
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]


logger = Logger()


# ─────────────────────────────────────────────────────────────────────────────
# VELVETFRUIT_EXTRACT — teammate's mean-reversion strategy (377067.py)
# ─────────────────────────────────────────────────────────────────────────────

VELVET_MR_WINDOW = 1000
VELVET_MR_THR = 5
VELVET_POSITION_LIMIT = 200


class VelvetfruitTrader:
    """Mean-reversion strategy for VELVETFRUIT_EXTRACT (from 377067.py)."""

    def __init__(self, state: TradingState, td: dict, new_td: dict):
        self.name = "VELVETFRUIT_EXTRACT"
        self.state = state
        self.td = td
        self.new_td = new_td
        self.orders: List[Order] = []

        self.position = state.position.get(self.name, 0)
        self.max_buy = VELVET_POSITION_LIMIT - self.position
        self.max_sell = VELVET_POSITION_LIMIT + self.position

        od = state.order_depths.get(self.name)
        if od:
            buy_orders = {bp: abs(bv) for bp, bv in sorted(od.buy_orders.items(), reverse=True)}
            sell_orders = {sp: abs(sv) for sp, sv in sorted(od.sell_orders.items())}
        else:
            buy_orders, sell_orders = {}, {}

        self.best_bid = max(buy_orders) if buy_orders else None
        self.best_ask = min(sell_orders) if sell_orders else None
        self.bid_wall = min(buy_orders) if buy_orders else None
        self.ask_wall = max(sell_orders) if sell_orders else None
        self.wall_mid = (self.bid_wall + self.ask_wall) / 2 if self.bid_wall and self.ask_wall else None

    def _ema(self, key: str, window: int, value: float) -> float:
        old = self.td.get(key, value)
        alpha = 2 / (window + 1)
        new = alpha * value + (1 - alpha) * old
        self.new_td[key] = new
        return new

    def _bid(self, price: float, volume: float):
        vol = min(abs(int(volume)), self.max_buy)
        if vol <= 0:
            return
        self.orders.append(Order(self.name, int(price), vol))
        self.max_buy -= vol

    def _ask(self, price: float, volume: float):
        vol = min(abs(int(volume)), self.max_sell)
        if vol <= 0:
            return
        self.orders.append(Order(self.name, int(price), -vol))
        self.max_sell -= vol

    def get_orders(self) -> List[Order]:
        if self.wall_mid is None:
            return []

        ema = self._ema("velvet_ema", VELVET_MR_WINDOW, self.wall_mid)
        deviation = self.wall_mid - ema

        if deviation > VELVET_MR_THR and self.max_sell > 0:
            self._ask(self.bid_wall + 1, self.max_sell)
        elif deviation < -VELVET_MR_THR and self.max_buy > 0:
            self._bid(self.ask_wall - 1, self.max_buy)

        return self.orders


# ─────────────────────────────────────────────────────────────────────────────
# HYDROGEL_PACK — EMA WMP market-making strategy (WMP_strategy-2.py)
# ─────────────────────────────────────────────────────────────────────────────

HYDRO_POSITION_LIMIT = 200
HYDRO_QUOTE_SIZE = 2
HYDRO_UNWIND_THRESHOLD = 0.9
HYDRO_FAST_SPAN = 10
HYDRO_ALPHA_FAST = 2 / (HYDRO_FAST_SPAN + 1)
HYDRO_SPREAD_HALF = 4
HYDRO_SKEW_MULTIPLIER = 1.5
HYDRO_VOL_WINDOW = 50
HYDRO_VOL_THRESHOLD = 15
DAY_LENGTH = 1_000_000
FLATTEN_START = 900_000
FLATTEN_FINAL = 990_000


class HydrogelTrader:
    """EMA WMP market-making strategy for HYDROGEL_PACK (from WMP_strategy-2.py)."""

    def __init__(self, state: TradingState, td: dict, new_td: dict):
        self.name = "HYDROGEL_PACK"
        self.state = state
        self.td = td
        self.new_td = new_td
        self.orders: List[Order] = []

        self.position = state.position.get(self.name, 0)

        od = state.order_depths.get(self.name)
        self.best_bid = self.best_ask = self.best_bid_vol = self.best_ask_vol = None
        if od and od.buy_orders and od.sell_orders:
            self.best_bid = max(od.buy_orders)
            self.best_ask = min(od.sell_orders)
            self.best_bid_vol = abs(od.buy_orders[self.best_bid])
            self.best_ask_vol = abs(od.sell_orders[self.best_ask])

    def _wmp(self) -> float | None:
        if None in (self.best_bid, self.best_ask, self.best_bid_vol, self.best_ask_vol):
            return None
        denom = self.best_bid_vol + self.best_ask_vol
        if denom <= 0:
            return None
        return (self.best_ask * self.best_bid_vol + self.best_bid * self.best_ask_vol) / denom

    def _rolling_vol(self, history: list) -> float:
        if len(history) < 2:
            return 0.0
        changes = [history[i] - history[i - 1] for i in range(1, len(history))]
        n = len(changes)
        mean = sum(changes) / n
        variance = sum((c - mean) ** 2 for c in changes) / n
        return math.sqrt(variance)

    def get_orders(self) -> List[Order]:
        if self.best_bid is None or self.best_ask is None:
            return []

        wmp = self._wmp()
        if wmp is None:
            return []

        # Update WMP history
        history = self.td.get("hydro_wmp_history", [])
        history.append(wmp)
        if len(history) > HYDRO_VOL_WINDOW:
            history.pop(0)
        self.new_td["hydro_wmp_history"] = history

        time_in_day = self.state.timestamp % DAY_LENGTH
        near_end = time_in_day >= FLATTEN_START

        # End-of-day flattening (bypasses vol circuit breaker)
        if near_end:
            if self.position != 0:
                if time_in_day >= FLATTEN_FINAL:
                    qty = min(HYDRO_QUOTE_SIZE * 10, abs(self.position))
                else:
                    qty = min(HYDRO_QUOTE_SIZE * 4, abs(self.position))
                if self.position > 0:
                    self.orders.append(Order(self.name, self.best_bid, -qty))
                else:
                    self.orders.append(Order(self.name, self.best_ask, qty))
            return self.orders

        # Volatility circuit breaker
        current_vol = self._rolling_vol(history)
        if current_vol > HYDRO_VOL_THRESHOLD:
            return []

        # Update EMA
        prev_ema = self.td.get("hydro_ema_fast", None)
        ema_fast = wmp if prev_ema is None else HYDRO_ALPHA_FAST * wmp + (1 - HYDRO_ALPHA_FAST) * prev_ema
        self.new_td["hydro_ema_fast"] = ema_fast

        fair_value = ema_fast
        pos_limit = HYDRO_POSITION_LIMIT
        inventory_pct = abs(self.position) / pos_limit

        skew = (self.position / pos_limit) * HYDRO_SPREAD_HALF * HYDRO_SKEW_MULTIPLIER
        passive_bid_px = fair_value - HYDRO_SPREAD_HALF - skew
        passive_ask_px = fair_value + HYDRO_SPREAD_HALF - skew

        buy_price = int(math.floor(passive_bid_px))
        sell_price = int(math.ceil(passive_ask_px))
        if buy_price >= sell_price:
            sell_price = buy_price + 1

        # Critical inventory unwind
        if inventory_pct >= HYDRO_UNWIND_THRESHOLD:
            buy_price = min(buy_price, self.best_bid)
            sell_price = max(sell_price, self.best_ask)
            unwind_qty = min(HYDRO_QUOTE_SIZE * 2, abs(self.position))
            if self.position > 0 and unwind_qty > 0:
                self.orders.append(Order(self.name, self.best_bid, -unwind_qty))
            elif self.position < 0 and unwind_qty > 0:
                self.orders.append(Order(self.name, self.best_ask, unwind_qty))
            return self.orders

        # Normal passive quoting
        if self.position < pos_limit:
            buy_qty = min(HYDRO_QUOTE_SIZE, pos_limit - self.position)
            if buy_qty > 0:
                self.orders.append(Order(self.name, buy_price, buy_qty))

        if self.position > -pos_limit:
            sell_qty = min(HYDRO_QUOTE_SIZE, self.position + pos_limit)
            if sell_qty > 0:
                self.orders.append(Order(self.name, sell_price, -sell_qty))

        return self.orders


# ─────────────────────────────────────────────────────────────────────────────
# Top-level Trader
# ─────────────────────────────────────────────────────────────────────────────

class Trader:
    """
    Combined strategy:
      - HYDROGEL_PACK    → EMA WMP market-making (WMP_strategy-2.py)
      - VELVETFRUIT_EXTRACT → Mean-reversion EMA (377067.py)
    Shared traderData JSON with namespaced keys to avoid collisions.
    """

    def run(self, state: TradingState):
        # Load shared traderData
        td: dict = {}
        try:
            if state.traderData:
                td = json.loads(state.traderData)
        except Exception:
            td = {}

        new_td: dict = {}
        result: dict = {}

        # HYDROGEL_PACK
        if "HYDROGEL_PACK" in state.order_depths:
            hydro = HydrogelTrader(state, td, new_td)
            orders = hydro.get_orders()
            if orders:
                result["HYDROGEL_PACK"] = orders

        # VELVETFRUIT_EXTRACT
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            velvet = VelvetfruitTrader(state, td, new_td)
            orders = velvet.get_orders()
            if orders:
                result["VELVETFRUIT_EXTRACT"] = orders

        trader_data_out = json.dumps(new_td)
        conversions = 0
        logger.flush(state, result, conversions, trader_data_out)
        return result, conversions, trader_data_out
