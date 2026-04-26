from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Optional, Union
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

# ── Burn-in ───────────────────────────────────
BURN_IN_TIMESTAMP = 50_000
BURN_IN_BLEND     = 0.5

SEED_MEANS = {
    "VELVETFRUIT_EXTRACT": 5247.65,
    "VEV_5000":             251.14,
    "VEV_5100":             160.86,
    "VEV_5200":              88.99,
    "VEV_5300":              41.18,
    "VEV_5400":              12.63,
    "VEV_5500":               4.71,
}

# ── Velvet params ─────────────────────────────
VELVET_MR_WINDOW  = 3500
VELVET_MR_THR     = 12

# ── Voucher params ────────────────────────────
VOUCHER_MR_WINDOW = 2500

VOUCHER_MR_THR = {
    "VEV_5000": 10,
    "VEV_5100":  7,
    "VEV_5200":  5,
    "VEV_5300":  3,
    "VEV_5400":  2,
    "VEV_5500":  2,
}

# ── Hydrogel params ───────────────────────────
HYDRO_MR_WINDOW   = 5000
HYDRO_MR_THR      = 14
HYDRO_FIXED_FV    = 10000

# ── Wide-spread MM params (4000, 4500) ────────
WIDE_QUOTE_SIZE   = 100
# Inventory ratio beyond which we stop quoting the inventory-increasing side
WIDE_FADE_THRESH  = 0.5
WIDE_TAKE_THRESH = 0.7   # position ratio beyond which we take to flatten

# ── Voucher lists ─────────────────────────────
MR_VOUCHERS   = ["VEV_5000", "VEV_5100",
                  "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]
SKIP_VOUCHERS = ["VEV_6000", "VEV_6500"]
WIDE_VOUCHERS = ["VEV_4000", "VEV_4500"]


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
#  EMA MR Trader (with burn-in blend + per-product threshold)
# ─────────────────────────────────────────────

class EMAmrTrader:
    """
    Mean-reversion trader using wall_mid vs EMA.
    threshold can be a single float (shared) or a dict {product: float}.
    During burn-in, fair value = BURN_IN_BLEND * seed + (1 - BURN_IN_BLEND) * ema.
    After burn-in, fair value = ema.
    """

    def __init__(self, state, new_trader_data, products: List[str],
                 window: int, threshold: Union[float, Dict[str, float]]):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.window          = window
        self.threshold       = threshold
        self.traders         = {p: ProductTrader(p, state, new_trader_data) for p in products}
        self.burning_in      = state.timestamp < BURN_IN_TIMESTAMP

    def _get_threshold(self, name: str) -> float:
        if isinstance(self.threshold, dict):
            return self.threshold.get(name, 5)
        return self.threshold

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}
        for name, trader in self.traders.items():
            bid_wall, wall_mid, ask_wall = trader.get_walls()
            if wall_mid is None:
                continue

            td_key = f"ema_mr_{name}"
            ema = trader.calculate_ema(td_key, self.window, wall_mid)

            if self.burning_in and name in SEED_MEANS:
                fair_value = BURN_IN_BLEND * SEED_MEANS[name] + (1 - BURN_IN_BLEND) * ema
            else:
                fair_value = ema

            threshold = self._get_threshold(name)
            deviation = wall_mid - fair_value

            if deviation > threshold and trader.max_allowed_sell_volume > 0:
                trader.ask(bid_wall + 1, trader.max_allowed_sell_volume)

            elif deviation < -threshold and trader.max_allowed_buy_volume > 0:
                trader.bid(ask_wall - 1, trader.max_allowed_buy_volume)

            if trader.orders:
                out[name] = trader.orders

        return out


# ─────────────────────────────────────────────
#  Wide-spread MM Trader — inventory-aware passive quotes
# ─────────────────────────────────────────────

class WideMMTrader:
    """
    Passive MM for wide-spread products with two inventory controls:

    1. Asymmetric sizing: quote size on the inventory-increasing side scales
       down linearly with |position_ratio|, so we naturally bleed inventory
       back toward flat over time.

    2. One-side fade: beyond WIDE_FADE_THRESH, stop quoting the side that
       would increase inventory further. Only quote the reducing side.
    """

    def __init__(self, state, new_trader_data, products: List[str], quote_size: int):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.quote_size      = quote_size
        self.traders         = {p: ProductTrader(p, state, new_trader_data) for p in products}

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}
        for name, trader in self.traders.items():
            if trader.best_bid is None or trader.best_ask is None:
                continue

            spread = trader.best_ask - trader.best_bid
            if spread > 1:
                bid_price = trader.best_bid + 1
                ask_price = trader.best_ask - 1
            else:
                bid_price = trader.best_bid
                ask_price = trader.best_ask

            pos_ratio = trader.initial_position / trader.position_limit

            # Soft take: if inventory is very skewed, hit the reducing side aggressively
            if pos_ratio > WIDE_TAKE_THRESH and trader.max_allowed_sell_volume > 0:
                trader.ask(trader.best_bid, trader.max_allowed_sell_volume)
            elif pos_ratio < -WIDE_TAKE_THRESH and trader.max_allowed_buy_volume > 0:
                trader.bid(trader.best_ask, trader.max_allowed_buy_volume)

            # Asymmetric sizing: scale down the side that grows inventory
            raw_buy_size  = int(self.quote_size * (1 - max(pos_ratio, 0)))
            raw_sell_size = int(self.quote_size * (1 + min(pos_ratio, 0)))

            # One-side fade: beyond threshold, zero out the inventory-increasing side
            if pos_ratio > WIDE_FADE_THRESH:
                raw_buy_size = 0
            elif pos_ratio < -WIDE_FADE_THRESH:
                raw_sell_size = 0

            buy_size  = min(raw_buy_size,  trader.max_allowed_buy_volume)
            sell_size = min(raw_sell_size, trader.max_allowed_sell_volume)

            if buy_size > 0:
                trader.bid(bid_price, buy_size)
            if sell_size > 0:
                trader.ask(ask_price, sell_size)

            if trader.orders:
                out[name] = trader.orders

        return out


# ─────────────────────────────────────────────
#  Hydrogel Trader — EMA MR
# ─────────────────────────────────────────────

class HydrogelTrader:
    def __init__(self, state, new_trader_data):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.trader          = ProductTrader("HYDROGEL_PACK", state, new_trader_data)

    def get_orders(self) -> Dict[str, List[Order]]:
        trader = self.trader
        bid_wall, wall_mid, ask_wall = trader.get_walls()
        if wall_mid is None:
            return {}

        ema = trader.calculate_ema("ema_mr_HYDROGEL_PACK", HYDRO_MR_WINDOW, wall_mid)
        deviation = wall_mid - ema

        if deviation > HYDRO_MR_THR and trader.max_allowed_sell_volume > 0:
            trader.ask(bid_wall + 1, trader.max_allowed_sell_volume)

        elif deviation < -HYDRO_MR_THR and trader.max_allowed_buy_volume > 0:
            trader.bid(ask_wall - 1, trader.max_allowed_buy_volume)

        return {"HYDROGEL_PACK": trader.orders} if trader.orders else {}


# ─────────────────────────────────────────────
#  Top-level Trader
# ─────────────────────────────────────────────

class Trader:
    def run(self, state: TradingState):
        new_trader_data = {}

        try:
            if state.traderData:
                new_trader_data = json.loads(state.traderData)
        except Exception:
            pass

        result = {}

        # VELVETFRUIT — EMA MR with burn-in blend
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

        # Wide-spread vouchers (4000, 4500) — inventory-aware passive MM
        try:
            wide_mm = WideMMTrader(
                state, new_trader_data,
                products=WIDE_VOUCHERS,
                quote_size=WIDE_QUOTE_SIZE,
            )
            result.update(wide_mm.get_orders())
        except Exception:
            pass

        # Vouchers 5000-5500 — EMA MR with burn-in blend + per-product thresholds
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

        # Hydrogel — EMA MR
        try:
            hydrogel = HydrogelTrader(state, new_trader_data)
            result.update(hydrogel.get_orders())
        except Exception:
            pass

        try:
            final_trader_data = json.dumps(new_trader_data)
        except Exception:
            final_trader_data = ""

        return result, 0, final_trader_data