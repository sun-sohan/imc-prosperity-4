from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import jsonpickle, statistics


# ─────────────────────────────────────────────
#  Product config
# ─────────────────────────────────────────────

PRODUCTS = {
    "ASH_COATED_OSMIUM": {
        "position_limit": 60,
        "default_fair_value": 10000,
        "enabled": False,
    },
    "INTARIAN_PEPPER_ROOT": {
        "position_limit": 80,
        "default_fair_value": 10000,
        "enabled": True,
    },
}


# ─────────────────────────────────────────────
#  Base product trader
# ─────────────────────────────────────────────

class ProductTrader:

    def __init__(self, name: str):
        self.name = name
        self.limit = PRODUCTS[name]["position_limit"]

        # set each run()
        self.initial_position: int = 0
        self.orders: List[Order] = []
        self.mkt_sell_orders: Dict[int, int] = {}   # ask price -> (negative) volume
        self.mkt_buy_orders:  Dict[int, int] = {}   # bid price -> volume
        self.max_allowed_buy_volume:  int = 0
        self.max_allowed_sell_volume: int = 0

    def setup(self, order_depth: OrderDepth, position: int):
        """Call at the top of each run() to reset per-tick state."""
        self.initial_position       = position
        self.orders                 = []
        self.mkt_sell_orders        = dict(sorted(order_depth.sell_orders.items()))           # ascending
        self.mkt_buy_orders         = dict(sorted(order_depth.buy_orders.items(), reverse=True))  # descending
        self.max_allowed_buy_volume  = self.limit - position
        self.max_allowed_sell_volume = self.limit + position

    # ── order helpers ────────────────────────

    def bid(self, price: float, volume: float, logging: bool = True):
        """Place a buy order, capped by remaining buy headroom."""
        abs_volume = min(abs(int(volume)), self.max_allowed_buy_volume)
        if abs_volume <= 0:
            return
        self.orders.append(Order(self.name, int(price), abs_volume))
        self.max_allowed_buy_volume -= abs_volume

    def ask(self, price: float, volume: float, logging: bool = True):
        """Place a sell order, capped by remaining sell headroom."""
        abs_volume = min(abs(int(volume)), self.max_allowed_sell_volume)
        if abs_volume <= 0:
            return
        self.orders.append(Order(self.name, int(price), -abs_volume))
        self.max_allowed_sell_volume -= abs_volume

    # ── mid-price util ───────────────────────

    def mid_price(self) -> float | None:
        if not self.mkt_sell_orders or not self.mkt_buy_orders:
            return None
        return (min(self.mkt_sell_orders) + max(self.mkt_buy_orders)) / 2.0

    def run(self, order_depth: OrderDepth, position: int, state_data: dict) -> List[Order]:
        raise NotImplementedError


# ─────────────────────────────────────────────
#  Per-product traders
# ─────────────────────────────────────────────

class AshCoatedOsmiumTrader(ProductTrader):

    def __init__(self):
        super().__init__("ASH_COATED_OSMIUM")

    def get_walls(self):
        bid_wall = ask_wall = wall_mid = None
        try: bid_wall = min(self.mkt_buy_orders)
        except: pass
        try: ask_wall = max(self.mkt_sell_orders)
        except: pass
        try: wall_mid = (bid_wall + ask_wall) / 2
        except: pass
        return bid_wall, wall_mid, ask_wall

    def run(self, order_depth: OrderDepth, position: int, state_data: dict) -> List[Order]:
        self.setup(order_depth, position)

        if not self.mkt_sell_orders or not self.mkt_buy_orders:
            return self.orders

        min_ask = min(self.mkt_sell_orders)
        max_bid = max(self.mkt_buy_orders)
        mid_price = (min_ask + max_bid) / 2.0

        bid_wall, wall_mid, ask_wall = self.get_walls()
        fair_value = wall_mid if wall_mid is not None else PRODUCTS[self.name]["default_fair_value"]

        # ── 1. take ───────────────────────────────────────────────────
        for sp, sv in self.mkt_sell_orders.items():
            if sp < fair_value:
                self.bid(sp, abs(sv), logging=False)
            elif sp <= fair_value and self.initial_position < 0:
                volume = min(abs(sv), abs(self.initial_position))
                self.bid(sp, volume, logging=False)

        for bp, bv in self.mkt_buy_orders.items():
            if bp > fair_value:
                self.ask(bp, abs(bv), logging=False)
            elif bp >= fair_value and self.initial_position > 0:
                volume = min(abs(bv), self.initial_position)
                self.ask(bp, volume, logging=False)

        # ── 2. make ───────────────────────────────────────────────────
        STD      = 5.0
        Z_THRESH = 1.0

        if wall_mid is not None:
            deviation = wall_mid - mid_price
            z = deviation / STD

            if abs(z) >= Z_THRESH:
                if z >= Z_THRESH:
                    self.bid(max_bid + 1, self.max_allowed_buy_volume)
                    self.ask(ask_wall - 2, self.max_allowed_sell_volume)
                else:
                    self.ask(min_ask - 1, self.max_allowed_sell_volume)
                    self.bid(bid_wall + 2, self.max_allowed_buy_volume)
            else:
                self.bid(max_bid + 1, self.max_allowed_buy_volume)
                self.ask(min_ask - 1, self.max_allowed_sell_volume)

        return self.orders


class IntarianPepperRootTrader(ProductTrader):

    EMA_N = 10
    BUY_REACH = 10

    def __init__(self):
        super().__init__("INTARIAN_PEPPER_ROOT")

    def run(self, order_depth: OrderDepth, position: int, state_data: dict) -> List[Order]:
        self.setup(order_depth, position)

        # ── 1. update EMA ────────────────────────────────────────────
        k = 2.0 / (self.EMA_N + 1.0)
        mid = self.mid_price()

        if "pepper_ema" not in state_data:
            last_ema = mid if mid is not None else PRODUCTS[self.name]["default_fair_value"]
        else:
            last_ema = state_data["pepper_ema"]

        ema = mid * k + last_ema * (1.0 - k) if mid is not None else last_ema
        state_data["pepper_ema"] = ema

        if mid is None:
            return self.orders

        # ── 2. if already at limit, do nothing ───────────────────────
        if position >= self.limit:
            return self.orders

        # ── 3. accumulate long to +80 ────────────────────────────────

        # take all asks up to mid + BUY_REACH
        for sp, sv in self.mkt_sell_orders.items():
            if sp <= mid + self.BUY_REACH:
                self.bid(sp, abs(sv))

        # passive bid at mid (not best_bid+1) — tracks trend more aggressively
        if self.max_allowed_buy_volume > 0:
            self.bid(int(mid), self.max_allowed_buy_volume)

        return self.orders


# ─────────────────────────────────────────────
#  Top-level trader
# ─────────────────────────────────────────────

class Trader:

    def __init__(self):
        self.traders = {
            "ASH_COATED_OSMIUM":    AshCoatedOsmiumTrader(),
            "INTARIAN_PEPPER_ROOT": IntarianPepperRootTrader(),
        }

    def bid(self):
        return 67

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        conversions = 0

        state_data = {}
        if state.traderData:
            try:
                state_data = jsonpickle.decode(state.traderData)
            except Exception:
                pass

        for product, trader in self.traders.items():
            if product not in state.order_depths:
                continue
            if not PRODUCTS[product].get("enabled", True):
                continue
            position = state.position.get(product, 0)
            orders = trader.run(state.order_depths[product], position, state_data)
            if orders:
                result[product] = orders

        traderData = jsonpickle.encode(state_data)
        return result, conversions, traderData