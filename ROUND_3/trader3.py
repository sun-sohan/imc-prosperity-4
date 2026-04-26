from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import math

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
}

WALL_MAKER_PRODUCTS = ["VELVETFRUIT_EXTRACT", "HYDROGEL_PACK"]
WALL_QUOTE_SIZE = 80
WALL_TAKE_BUFFER = 0.0

VOUCHERS = ["VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]
STRIKES  = {"VEV_4000": 4000, "VEV_4500": 4500, 
            "VEV_5000": 5000, "VEV_5100": 5100, "VEV_5200": 5200,
            "VEV_5300": 5300, "VEV_5400": 5400, "VEV_5500": 5500}

SMILE_COEFFS = [0.0358, 0.0023, 0.1990]
# SMILE_COEFFS = [0.1660, -0.0129, 0.1944]

DAYS_LEFT_AT_START = 8
TIMESTAMPS_PER_DAY = 1_000_000
DAY = 3

RESIDUAL_EMA_WINDOW = 1000
DEV_EMA_WINDOW      = 1000
Z_BIAS = 1.0
QUOTE_SIZE = 80
TAKE_BUFFER = 0.8   # require this much edge over fair before taking

# Fill in real values from EDA for 5300/5400/5500
RESIDUAL_INIT = {
    "VEV_4000":  1.326,
    "VEV_4500":  0.737,
    "VEV_5000":  0.063,
    "VEV_5100": -0.096,
    "VEV_5200":  0.125,
    "VEV_5300": -0.054,
    "VEV_5400": -3.907,
    "VEV_5500": -0.881,
}
DEV_INIT = {
    "VEV_4000": 0.892,
    "VEV_4500": 0.395,
    "VEV_5000": 0.343,
    "VEV_5100": 0.328,
    "VEV_5200": 0.330,
    "VEV_5300": 0.323,
    "VEV_5400": 0.245,
    "VEV_5500": 0.213,
}


# ─────────────────────────────────────────────
#  BS helpers (unchanged)
# ─────────────────────────────────────────────

def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def bs_call(S, K, T, sigma, r=0):
    if sigma <= 0 or S <= 0 or T <= 0:
        return None, None, None
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    return price, norm_cdf(d1), S * norm_pdf(d1) * math.sqrt(T)

def moneyness(S, K, T):
    return math.log(K / S) / math.sqrt(T)

SLOPE = (0.71 - 0.42) / (-1.74 + 1)

def fair_vol(m):
    # if m < -0.6:
    #     return 0.42 + SLOPE * (m + 1)
    return SMILE_COEFFS[0] * m**2 + SMILE_COEFFS[1] * m + SMILE_COEFFS[2]

def get_option_values(S, K, T):
    return bs_call(S, K, T, fair_vol(moneyness(S, K, T)))

def get_tte(timestamp):
    days_elapsed = DAY + timestamp / TIMESTAMPS_PER_DAY
    days_left    = DAYS_LEFT_AT_START - days_elapsed
    return max(days_left / 252, 1e-6)


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

    def get_mid(self):
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None

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

    def calculate_ema(self, td_key, window, value, init_value=None):
        seed = init_value if init_value is not None else value
        old   = self.last_trader_data.get(td_key, seed)
        alpha = 2 / (window + 1)
        new   = alpha * value + (1 - alpha) * old
        self.new_trader_data[td_key] = new
        return new
    
    def get_walls(self):
        bid_wall = ask_wall = wall_mid = None
        try: bid_wall = min(self.mkt_buy_orders)
        except: pass
        try: ask_wall = max(self.mkt_sell_orders)
        except: pass
        try: wall_mid = (bid_wall + ask_wall) / 2
        except: pass
        return bid_wall, wall_mid, ask_wall


# ─────────────────────────────────────────────
#  Option market maker
# ─────────────────────────────────────────────

class OptionTrader:
    def __init__(self, state, new_trader_data):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.underlying = ProductTrader("VELVETFRUIT_EXTRACT", state, new_trader_data)
        self.options    = {v: ProductTrader(v, state, new_trader_data) for v in VOUCHERS}

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}
        S = self.underlying.get_mid()
        if S is None: return out
        T = get_tte(self.state.timestamp)
        if T <= 0: return out

        for name, trader in self.options.items():
            if trader.best_bid is None or trader.best_ask is None:
                continue

            mid = trader.get_mid()
            K = STRIKES[name]
            theo, _, _ = get_option_values(S, K, T)
            if theo is None: continue

            residual = mid - theo
            mean_resid = trader.calculate_ema(
                f'{name}_resid_mean', RESIDUAL_EMA_WINDOW, residual,
                init_value=RESIDUAL_INIT[name]
            )
            scale = trader.calculate_ema(
                f'{name}_resid_dev', DEV_EMA_WINDOW, abs(residual - mean_resid),
                init_value=DEV_INIT[name]
            )
            if scale < 0.01: scale = 0.01
            zscore = (residual - mean_resid) / scale

            adjusted_fair = theo + mean_resid

            spread = trader.best_ask - trader.best_bid
            pos = trader.initial_position

            # ── 1. TAKE: buffer scales with spread ──
            # Wider spread = market makers less competitive = more "fake" mispricings to filter out
            # Tight spread = real edge is small, don't filter
            if spread <= 2:
                take_buffer = 0.0
            elif spread == 3:
                take_buffer = 0.5
            else:
                take_buffer = (spread - 2) * 0.4

            for sp, sv in trader.mkt_sell_orders.items():
                if sp < adjusted_fair - take_buffer:
                    trader.bid(sp, abs(sv))
                else:
                    break
            for bp, bv in trader.mkt_buy_orders.items():
                if bp > adjusted_fair + take_buffer:
                    trader.ask(bp, abs(bv))
                else:
                    break

            # ── 2. MAKE: post inside the spread, biased by signal ──
            if spread > 1:
                bid_price = trader.best_bid + 1
                ask_price = trader.best_ask - 1
            else:
                bid_price = trader.best_bid
                ask_price = trader.best_ask

            if zscore > Z_BIAS:
                bid_price = trader.best_bid
                ask_price = max(trader.best_ask - 1, int(adjusted_fair) + 1)
            elif zscore < -Z_BIAS:
                bid_price = min(trader.best_bid + 1, int(adjusted_fair) - 1)
                ask_price = trader.best_ask

            buy_size  = min(QUOTE_SIZE, trader.max_allowed_buy_volume)
            sell_size = min(QUOTE_SIZE, trader.max_allowed_sell_volume)

            if pos > QUOTE_SIZE:
                buy_size = max(0, buy_size - pos // 2)
            elif pos < -QUOTE_SIZE:
                sell_size = max(0, sell_size + pos // 2)

            if buy_size > 0:
                trader.bid(bid_price, buy_size)
            if sell_size > 0:
                trader.ask(ask_price, sell_size)

            out[name] = trader.orders

        return out


class WallMakerTrader:
    def __init__(self, state, new_trader_data):
        self.state = state
        self.new_trader_data = new_trader_data
        self.products = {p: ProductTrader(p, state, new_trader_data) for p in WALL_MAKER_PRODUCTS}

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}
        for name, trader in self.products.items():
            if trader.best_bid is None or trader.best_ask is None:
                continue

            bid_wall, wall_mid, ask_wall = trader.get_walls()
            if wall_mid is None:
                continue

            fair_value = wall_mid
            spread = trader.best_ask - trader.best_bid

            # TAKE
            for sp, sv in trader.mkt_sell_orders.items():
                if sp < fair_value - WALL_TAKE_BUFFER:
                    trader.bid(sp, abs(sv))
                else:
                    break
            for bp, bv in trader.mkt_buy_orders.items():
                if bp > fair_value + WALL_TAKE_BUFFER:
                    trader.ask(bp, abs(bv))
                else:
                    break

            # MAKE
            if spread > 1:
                bid_price = trader.best_bid + 1
                ask_price = trader.best_ask - 1
            else:
                bid_price = trader.best_bid
                ask_price = trader.best_ask

            buy_size  = min(WALL_QUOTE_SIZE, trader.max_allowed_buy_volume)
            sell_size = min(WALL_QUOTE_SIZE, trader.max_allowed_sell_volume)

            pos = trader.initial_position
            if pos > WALL_QUOTE_SIZE:
                buy_size = max(0, buy_size - pos // 2)
            elif pos < -WALL_QUOTE_SIZE:
                sell_size = max(0, sell_size + pos // 2)

            if buy_size > 0:
                trader.bid(bid_price, buy_size)
            if sell_size > 0:
                trader.ask(ask_price, sell_size)

            out[name] = trader.orders

        return out

class Trader:
    def run(self, state: TradingState):
        new_trader_data = {}
        result = {}
        try:
            option_trader = OptionTrader(state, new_trader_data)
            result.update(option_trader.get_orders())
        except: pass

        try:
            wall_maker = WallMakerTrader(state, new_trader_data)
            result.update(wall_maker.get_orders())
        except: pass

        try: final_trader_data = json.dumps(new_trader_data)
        except: final_trader_data = ""

        return result, 0, final_trader_data