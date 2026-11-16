from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────

PRODUCTS = {
    "VELVETFRUIT_EXTRACT": {"position_limit": 200, "enabled": True},
    "HYDROGEL_PACK":       {"position_limit": 200, "enabled": False},
}

# ── VELVETFRUIT params ────────────────────────
VELVET_MR_WINDOW = 1000
VELVET_MR_THR    = 5

# ── HYDROGEL params ───────────────────────────
HYDRO_MR_WINDOW  = 400
HYDRO_MR_THR     = 10


# ─────────────────────────────────────────────
#  Base product trader
# ─────────────────────────────────────────────

class ProductTrader:

    def __init__(self, name: str, state: TradingState, prints: dict, new_trader_data: dict):
        self.name            = name
        self.state           = state
        self.prints          = prints
        self.new_trader_data = new_trader_data
        self.orders: List[Order] = []

        self.last_trader_data = {}
        try:
            if state.traderData:
                self.last_trader_data = json.loads(state.traderData)
        except: pass

        self.position_limit   = PRODUCTS[name]["position_limit"]
        self.initial_position = state.position.get(name, 0)

        self.mkt_buy_orders, self.mkt_sell_orders = self.get_order_depth()
        self.bid_wall, self.wall_mid, self.ask_wall = self.get_walls()
        self.best_bid, self.best_ask = self.get_best_bid_ask()

        self.max_allowed_buy_volume  = self.position_limit - self.initial_position
        self.max_allowed_sell_volume = self.position_limit + self.initial_position

    def get_order_depth(self):
        buy_orders = sell_orders = {}
        try:
            od = self.state.order_depths[self.name]
            buy_orders  = {bp: abs(bv) for bp, bv in sorted(od.buy_orders.items(),  reverse=True)}
            sell_orders = {sp: abs(sv) for sp, sv in sorted(od.sell_orders.items())}
        except: pass
        return buy_orders, sell_orders

    def get_walls(self):
        bid_wall = ask_wall = wall_mid = None
        try: bid_wall = min(self.mkt_buy_orders)
        except: pass
        try: ask_wall = max(self.mkt_sell_orders)
        except: pass
        try: wall_mid = (bid_wall + ask_wall) / 2
        except: pass
        return bid_wall, wall_mid, ask_wall

    def get_best_bid_ask(self):
        best_bid = best_ask = None
        try: best_bid = max(self.mkt_buy_orders)
        except: pass
        try: best_ask = min(self.mkt_sell_orders)
        except: pass
        return best_bid, best_ask

    def bid(self, price: float, volume: float):
        vol = min(abs(int(volume)), self.max_allowed_buy_volume)
        if vol <= 0: return
        self.orders.append(Order(self.name, int(price), vol))
        self.max_allowed_buy_volume -= vol

    def ask(self, price: float, volume: float):
        vol = min(abs(int(volume)), self.max_allowed_sell_volume)
        if vol <= 0: return
        self.orders.append(Order(self.name, int(price), -vol))
        self.max_allowed_sell_volume -= vol

    def calculate_ema(self, td_key: str, window: int, value: float) -> float:
        old   = self.last_trader_data.get(td_key, value)
        alpha = 2 / (window + 1)
        new   = alpha * value + (1 - alpha) * old
        self.new_trader_data[td_key] = new
        return new

    def get_orders(self) -> Dict[str, List[Order]]:
        raise NotImplementedError


# ─────────────────────────────────────────────
#  Per-product traders
# ─────────────────────────────────────────────

class VelvetfruitExtractTrader(ProductTrader):

    def __init__(self, state: TradingState, prints: dict, new_trader_data: dict):
        super().__init__("VELVETFRUIT_EXTRACT", state, prints, new_trader_data)

    def get_orders(self) -> Dict[str, List[Order]]:
        if self.wall_mid is None:
            return {}

        ema = self.calculate_ema("velvet_ema", VELVET_MR_WINDOW, self.wall_mid)
        current_deviation = self.wall_mid - ema

        if current_deviation > VELVET_MR_THR and self.max_allowed_sell_volume > 0:
            self.ask(self.bid_wall + 1, self.max_allowed_sell_volume)

        elif current_deviation < -VELVET_MR_THR and self.max_allowed_buy_volume > 0:
            self.bid(self.ask_wall - 1, self.max_allowed_buy_volume)

        return {self.name: self.orders}


class HydrogelPackTrader(ProductTrader):

    def __init__(self, state: TradingState, prints: dict, new_trader_data: dict):
        super().__init__("HYDROGEL_PACK", state, prints, new_trader_data)

    def get_orders(self) -> Dict[str, List[Order]]:
        if self.wall_mid is None:
            return {}

        ema = self.calculate_ema("hydro_ema", HYDRO_MR_WINDOW, self.wall_mid)
        current_deviation = self.wall_mid - ema

        if current_deviation > HYDRO_MR_THR and self.max_allowed_sell_volume > 0:
            self.ask(self.bid_wall + 1, self.max_allowed_sell_volume)

        elif current_deviation < -HYDRO_MR_THR and self.max_allowed_buy_volume > 0:
            self.bid(self.ask_wall - 1, self.max_allowed_buy_volume)

        return {self.name: self.orders}


# ─────────────────────────────────────────────
#  Top-level trader
# ─────────────────────────────────────────────

class Trader:

    def run(self, state: TradingState):
        new_trader_data = {}
        prints = {
            "GENERAL": {
                "TIMESTAMP": state.timestamp,
                "POSITIONS": state.position,
            }
        }

        product_traders = {
            "VELVETFRUIT_EXTRACT": VelvetfruitExtractTrader,
            "HYDROGEL_PACK":       HydrogelPackTrader,
        }

        result = {}
        for symbol, trader_cls in product_traders.items():
            if not PRODUCTS[symbol].get("enabled", True):
                continue
            if symbol not in state.order_depths:
                continue
            try:
                trader = trader_cls(state, prints, new_trader_data)
                result.update(trader.get_orders())
            except: pass

        try:    final_trader_data = json.dumps(new_trader_data)
        except: final_trader_data = ""

        return result, 0, final_trader_data