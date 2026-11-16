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

WALL_MAKER_PRODUCTS = ["VELVETFRUIT_EXTRACT"]
WALL_QUOTE_SIZE = 80
WALL_TAKE_BUFFER = 0.0

VOUCHERS = ["VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]
STRIKES  = {"VEV_4000": 4000, "VEV_4500": 4500, 
            "VEV_5000": 5000, "VEV_5100": 5100, "VEV_5200": 5200,
            "VEV_5300": 5300, "VEV_5400": 5400, "VEV_5500": 5500}

SMILE_COEFFS = [0.0358, 0.0023, 0.1990]

DAYS_LEFT_AT_START = 8
TIMESTAMPS_PER_DAY = 1_000_000
DAY = 3

RESIDUAL_EMA_WINDOW = 1000
DEV_EMA_WINDOW      = 1000
Z_BIAS = 1.0
QUOTE_SIZE = 80
TAKE_BUFFER = 0.8

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
#  Hydrogel config
# ─────────────────────────────────────────────

HYDROGEL_LIMIT = 200


# ─────────────────────────────────────────────
#  BS helpers
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


# ─────────────────────────────────────────────
#  Wall maker (VELVETFRUIT_EXTRACT only now)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
#  Hydrogel trend-following short strategy
# ─────────────────────────────────────────────

class HydrogelTrader:
    PRODUCT = "HYDROGEL_PACK"
    LIMIT = HYDROGEL_LIMIT

    def __init__(self, state: TradingState, new_trader_data: dict):
        self.state = state
        self.new_trader_data = new_trader_data

        # Load hydrogel-specific sub-state from the shared traderData blob
        try:
            full = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            full = {}
        hg = full.get("hydrogel", {})
        self.mid_history: list = hg.get("mid_history", [])
        self.short_low = hg.get("short_low", None)
        self.mode: str = hg.get("mode", "WAIT")

    def _save(self):
        """Write hydrogel sub-state into new_trader_data so it gets persisted."""
        self.new_trader_data["hydrogel"] = {
            "mid_history": self.mid_history,
            "short_low": self.short_low,
            "mode": self.mode,
        }

    @staticmethod
    def _mean(values):
        return sum(values) / len(values) if values else 0

    def get_orders(self) -> Dict[str, List[Order]]:
        product = self.PRODUCT
        state = self.state

        if product not in state.order_depths:
            self._save()
            return {}

        depth = state.order_depths[product]
        orders: List[Order] = []

        # Best bid / ask
        best_bid = best_ask = None
        if depth.buy_orders:
            best_bid = max(depth.buy_orders.keys())
        if depth.sell_orders:
            best_ask = min(depth.sell_orders.keys())

        if best_bid is None or best_ask is None:
            self._save()
            return {}

        pos = state.position.get(product, 0)
        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid

        # Update mid history
        hist = self.mid_history
        hist.append(mid)
        if len(hist) > 120:
            hist = hist[-120:]
        self.mid_history = hist

        if len(hist) < 60:
            self._save()
            return {}

        trend_3  = hist[-1] - hist[-4]
        trend_5  = hist[-1] - hist[-6]
        trend_10 = hist[-1] - hist[-11]
        trend_20 = hist[-1] - hist[-21]
        trend_50 = hist[-1] - hist[-51]

        fast_ma = self._mean(hist[-15:])
        slow_ma = self._mean(hist[-60:])

        # Track lowest mid while short
        if pos < 0:
            if self.short_low is None:
                self.short_low = mid
            else:
                self.short_low = min(self.short_low, mid)
        else:
            self.short_low = None

        short_low = self.short_low
        bounce = 0 if short_low is None else mid - short_low

        early_short = (
            trend_20 < -3
            and trend_3 < 0
            and fast_ma < slow_ma - 1
            and spread <= 20
        )
        strong_short = (
            trend_50 < -12
            and trend_20 < -5
            and fast_ma < slow_ma - 3
            and spread <= 18
        )

        bounce_started = pos < 0 and bounce > 8
        strong_bounce  = pos < 0 and bounce > 14
        allow_new_short = not bounce_started

        max_buy  = self.LIMIT - pos
        max_sell = self.LIMIT + pos

        def _bid(price, qty):
            qty = min(abs(int(qty)), max_buy)
            if qty > 0:
                orders.append(Order(product, int(price), qty))

        def _ask(price, qty):
            qty = min(abs(int(qty)), max_sell)
            if qty > 0:
                orders.append(Order(product, int(price), -qty))

        # Emergency cover
        if pos < -185:
            _bid(best_ask, 60)
            self.mode = "EMERGENCY_COVER"

        # Passive de-risk on large bounce
        elif strong_bounce and pos < -130:
            buy_price = min(best_ask - 1, best_bid + 1)
            if buy_price < best_ask:
                _bid(buy_price, 25)
            self.mode = "PASSIVE_BOUNCE_COVER"

        elif strong_short and allow_new_short:
            self.mode = "STRONG_SHORT"
            target = -160
            if pos > target:
                qty = min(pos - target, pos + self.LIMIT, 45)
                price = best_bid if spread <= 14 else best_bid + 1
                _ask(price, qty)

        elif early_short and allow_new_short:
            self.mode = "EARLY_SHORT"
            target = -70
            if pos > target:
                qty = min(pos - target, pos + self.LIMIT, 25)
                price = best_bid + 1
                if price > best_bid:
                    _ask(price, qty)

        else:
            self.mode = "WAIT"
            # Passive inventory cleanup
            if pos < -150:
                buy_price = min(best_ask - 1, best_bid + 1)
                if buy_price < best_ask:
                    _bid(buy_price, 25)
            elif pos > 120:
                sell_price = max(best_bid + 1, best_ask - 1)
                if sell_price > best_bid:
                    _ask(sell_price, 25)

        print(
            f"{product} mode={self.mode} pos={pos} mid={mid:.1f} "
            f"spread={spread} t3={trend_3:.1f} t5={trend_5:.1f} "
            f"t10={trend_10:.1f} t20={trend_20:.1f} t50={trend_50:.1f} "
            f"fast={fast_ma:.1f} slow={slow_ma:.1f} "
            f"low={short_low} bounce={bounce:.1f} allow_short={allow_new_short} "
            f"orders={orders}"
        )

        self._save()
        return {product: orders}


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

        try:
            option_trader = OptionTrader(state, new_trader_data)
            result.update(option_trader.get_orders())
        except Exception:
            pass

        try:
            wall_maker = WallMakerTrader(state, new_trader_data)
            result.update(wall_maker.get_orders())
        except Exception:
            pass

        try:
            hydrogel_trader = HydrogelTrader(state, new_trader_data)
            result.update(hydrogel_trader.get_orders())
        except Exception:
            pass

        try:
            final_trader_data = json.dumps(new_trader_data)
        except Exception:
            final_trader_data = ""

        return result, 0, final_trader_data