from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import jsonpickle, statistics


# ─────────────────────────────────────────────
#  Product config
# ─────────────────────────────────────────────

PRODUCTS = {
    "VELVETFRUIT_EXTRACT": {
        "position_limit": 180,
        "default_fair_value": 5250,
        "enabled": True,
    },
    "HYDROGEL_PACK": {
        "position_limit": 180,
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

        self.initial_position: int = 0
        self.orders: List[Order] = []
        self.mkt_sell_orders: Dict[int, int] = {}
        self.mkt_buy_orders:  Dict[int, int] = {}
        self.max_allowed_buy_volume:  int = 0
        self.max_allowed_sell_volume: int = 0

    def setup(self, order_depth: OrderDepth, position: int):
        self.initial_position       = position
        self.orders                 = []
        self.mkt_sell_orders        = dict(sorted(order_depth.sell_orders.items()))
        self.mkt_buy_orders         = dict(sorted(order_depth.buy_orders.items(), reverse=True))
        self.max_allowed_buy_volume  = self.limit - position
        self.max_allowed_sell_volume = self.limit + position

    def bid(self, price: float, volume: float, logging: bool = True):
        abs_volume = min(abs(int(volume)), self.max_allowed_buy_volume)
        if abs_volume <= 0:
            return
        self.orders.append(Order(self.name, int(price), abs_volume))
        self.max_allowed_buy_volume -= abs_volume

    def ask(self, price: float, volume: float, logging: bool = True):
        abs_volume = min(abs(int(volume)), self.max_allowed_sell_volume)
        if abs_volume <= 0:
            return
        self.orders.append(Order(self.name, int(price), -abs_volume))
        self.max_allowed_sell_volume -= abs_volume

    def mid_price(self) -> float | None:
        if not self.mkt_sell_orders or not self.mkt_buy_orders:
            return None
        return (min(self.mkt_sell_orders) + max(self.mkt_buy_orders)) / 2.0

    def run(self, order_depth: OrderDepth, position: int, state_data: dict) -> List[Order]:
        raise NotImplementedError


# ─────────────────────────────────────────────
#  Per-product traders
# ─────────────────────────────────────────────

class VelvetfruitExtractTrader(ProductTrader):

    def __init__(self):
        super().__init__("VELVETFRUIT_EXTRACT")

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
        STD      = 2.5
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


class HydrogelPackTrader(ProductTrader):

    def __init__(self):
        super().__init__("HYDROGEL_PACK")

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
        STD      = 8.0
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


# ─────────────────────────────────────────────
#  Top-level trader
# ─────────────────────────────────────────────

class Trader:

    def __init__(self):
        self.traders = {
            "VELVETFRUIT_EXTRACT": VelvetfruitExtractTrader(),
            "HYDROGEL_PACK":       HydrogelPackTrader(),
        }

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