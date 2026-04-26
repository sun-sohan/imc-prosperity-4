from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────

PRODUCTS = {
    "VELVETFRUIT_EXTRACT": {"position_limit": 200},
    "HYDROGEL_PACK":       {"position_limit": 200},
    "VEV_4000": {"position_limit": 300},
    "VEV_4500": {"position_limit": 300},
    "VEV_5000": {"position_limit": 300},
    "VEV_5100": {"position_limit": 300},
    "VEV_5200": {"position_limit": 300},
    "VEV_5300": {"position_limit": 300},
    "VEV_5400": {"position_limit": 300},
    "VEV_5500": {"position_limit": 300},
    "VEV_6000": {"position_limit": 300},
    "VEV_6500": {"position_limit": 300},
}

# ── EMA MR params ─────────────────────────────
VELVET_MR_WINDOW  = 1000
VELVET_MR_THR     = 5

VOUCHER_MR_WINDOW = 1000
VOUCHER_MR_THR    = 5

HYDRO_MR_WINDOW   = 5000
HYDRO_MR_THR      = 10

# ── Voucher lists ─────────────────────────────
MR_VOUCHERS   = ["VEV_5000", "VEV_5100",
                  "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]
SKIP_VOUCHERS = ["VEV_6000", "VEV_6500"]


# ─────────────────────────────────────────────
#  Base product trader
# ─────────────────────────────────────────────

class ProductTrader:
    def __init__(self, name, state, new_trader_data):
        self.name            = name
        self.state           = state
        self.new_trader_data = new_trader_data
        self.orders: List[Order] = []

        self.last_trader_data = {}
        try:
            if state.traderData:
                self.last_trader_data = json.loads(state.traderData)
        except: pass

        self.position_limit   = PRODUCTS[name]["position_limit"]
        self.initial_position = state.position.get(name, 0)

        self.mkt_buy_orders, self.mkt_sell_orders = self._get_order_depth()
        self.best_bid, self.best_ask = self._get_best_bid_ask()

        self.max_allowed_buy_volume  = self.position_limit - self.initial_position
        self.max_allowed_sell_volume = self.position_limit + self.initial_position

    def _get_order_depth(self):
        buy_orders, sell_orders = {}, {}
        try:
            od = self.state.order_depths[self.name]
            buy_orders  = {bp: abs(bv) for bp, bv in sorted(od.buy_orders.items(), reverse=True)}
            sell_orders = {sp: abs(sv) for sp, sv in sorted(od.sell_orders.items())}
        except: pass
        return buy_orders, sell_orders

    def _get_best_bid_ask(self):
        best_bid = best_ask = None
        try: best_bid = max(self.mkt_buy_orders)
        except: pass
        try: best_ask = min(self.mkt_sell_orders)
        except: pass
        return best_bid, best_ask

    def get_walls(self):
        bid_wall = ask_wall = wall_mid = None
        try: bid_wall = min(self.mkt_buy_orders)
        except: pass
        try: ask_wall = max(self.mkt_sell_orders)
        except: pass
        try: wall_mid = (bid_wall + ask_wall) / 2
        except: pass
        return bid_wall, wall_mid, ask_wall

    def calculate_ema(self, td_key: str, window: int, value: float) -> float:
        old   = self.last_trader_data.get(td_key, value)
        alpha = 2 / (window + 1)
        new   = alpha * value + (1 - alpha) * old
        self.new_trader_data[td_key] = new
        return new

    def bid(self, price, volume):
        vol = min(abs(int(volume)), self.max_allowed_buy_volume)
        if vol <= 0: return
        self.orders.append(Order(self.name, int(price), vol))
        self.max_allowed_buy_volume -= vol

    def ask(self, price, volume):
        vol = min(abs(int(volume)), self.max_allowed_sell_volume)
        if vol <= 0: return
        self.orders.append(Order(self.name, int(price), -vol))
        self.max_allowed_sell_volume -= vol


# ─────────────────────────────────────────────
#  EMA MR Trader — shared logic for all products
# ─────────────────────────────────────────────

class EMAmrTrader:
    """
    Mean-reversion trader using wall_mid vs EMA.
    When wall_mid is above EMA by > threshold, sell at bid_wall + 1.
    When wall_mid is below EMA by > threshold, buy at ask_wall - 1.
    """

    def __init__(self, state, new_trader_data, products: List[str],
                 window: int, threshold: float):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.window          = window
        self.threshold       = threshold
        self.traders         = {p: ProductTrader(p, state, new_trader_data) for p in products}

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}
        for name, trader in self.traders.items():
            bid_wall, wall_mid, ask_wall = trader.get_walls()
            if wall_mid is None:
                continue

            td_key = f"ema_mr_{name}"
            ema = trader.calculate_ema(td_key, self.window, wall_mid)
            deviation = wall_mid - ema

            if deviation > self.threshold and trader.max_allowed_sell_volume > 0:
                trader.ask(bid_wall + 1, trader.max_allowed_sell_volume)

            elif deviation < -self.threshold and trader.max_allowed_buy_volume > 0:
                trader.bid(ask_wall - 1, trader.max_allowed_buy_volume)

            if trader.orders:
                out[name] = trader.orders

        return out


# ─────────────────────────────────────────────
#  Top-level Trader
# ─────────────────────────────────────────────

class Trader:
    def run(self, state: TradingState):
        new_trader_data = {}

        # Seed new_trader_data with existing state so EMA keys survive
        try:
            if state.traderData:
                new_trader_data = json.loads(state.traderData)
        except Exception:
            pass

        result = {}

        # VELVETFRUIT — EMA mean reversion
        try:
            velvet_mr = EMAmrTrader(
                state, new_trader_data,
                products=["VELVETFRUIT_EXTRACT"],
                window=VELVET_MR_WINDOW,
                threshold=VELVET_MR_THR,
            )
            result.update(velvet_mr.get_orders())
        except Exception:
            pass

        # Vouchers (excl. 6000/6500) — EMA mean reversion
        try:
            voucher_mr = EMAmrTrader(
                state, new_trader_data,
                products=MR_VOUCHERS,
                window=VOUCHER_MR_WINDOW,
                threshold=VOUCHER_MR_THR,
            )
            result.update(voucher_mr.get_orders())
        except Exception:
            pass

        # Hydrogel — slow EMA mean reversion
        try:
            hydrogel_mr = EMAmrTrader(
                state, new_trader_data,
                products=["HYDROGEL_PACK"],
                window=HYDRO_MR_WINDOW,
                threshold=HYDRO_MR_THR,
            )
            result.update(hydrogel_mr.get_orders())
        except Exception:
            pass

        try:
            final_trader_data = json.dumps(new_trader_data)
        except Exception:
            final_trader_data = ""

        return result, 0, final_trader_data