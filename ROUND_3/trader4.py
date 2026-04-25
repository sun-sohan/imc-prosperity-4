from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import math

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────

PRODUCTS = {
    "VELVETFRUIT_EXTRACT": {"position_limit": 200, "enabled": True},
    "VEV_4000":            {"position_limit": 300, "enabled": True},
    "VEV_4500":            {"position_limit": 300, "enabled": True},
    "VEV_5000":            {"position_limit": 300, "enabled": True},
    "VEV_5100":            {"position_limit": 300, "enabled": True},
    "VEV_5200":            {"position_limit": 300, "enabled": True},
    "VEV_5300":            {"position_limit": 300, "enabled": True},
    "VEV_5400":            {"position_limit": 300, "enabled": True},
    "VEV_5500":            {"position_limit": 300, "enabled": True},
    "VEV_6000":            {"position_limit": 300, "enabled": True},
    "VEV_6500":            {"position_limit": 300, "enabled": True},
}

VOUCHERS = [
    "VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200",
    "VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500",
]
STRIKES = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500, "VEV_6000": 6000,
    "VEV_6500": 6500,
}

# ── Separate bid/ask smile coefficients ──────────────────────────────────────
# Fit these offline: bid params on bid-side IVs, ask params on ask-side IVs.
# This is how the reference code quotes a vol spread rather than a price spread.
# Replace with your own fitted values.
BID_PARAMS = {"a": 0.1602, "b": -0.0304, "c": 0.1706}   # bid vol surface
ASK_PARAMS = {"a": 0.1602, "b": -0.0304, "c": 0.2106}   # ask vol surface
# The gap between c_ask and c_bid is your vol spread (here ~0.04).
# Wider gap = wider quoted market = more edge, fewer fills.

DAYS_LEFT_AT_START = 5
TIMESTAMPS_PER_DAY = 999900
DAY = 3

# Max size to quote on each side per voucher
MAX_QUOTE_SIZE = 80

# Delta hedge: underlying buy/sell order counters (reset each tick)
UNDERLYING = "VELVETFRUIT_EXTRACT"


# ─────────────────────────────────────────────
#  BS helpers
# ─────────────────────────────────────────────

def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def bs_call(S, K, T, sigma):
    if sigma <= 0 or S <= 0 or T <= 0:
        return None
    d1 = (math.log(S / K) + 0.5 * sigma**2 * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * norm_cdf(d2)

def bs_delta(S, K, T, sigma):
    if sigma <= 0 or T <= 0:
        return None
    d1 = (math.log(S / K) + 0.5 * sigma**2 * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1)

def moneyness(S, K, T):
    return math.log(S / K) / math.sqrt(T)   # log(S/K)/√T  (positive = ITM)

def predict_iv(m, params):
    v = params["a"] * m**2 + params["b"] * m + params["c"]
    return max(v, 0.01)

def get_tte(timestamp):
    days_elapsed = DAY + timestamp / TIMESTAMPS_PER_DAY
    days_left    = max(DAYS_LEFT_AT_START - days_elapsed, 1e-4)
    return days_left / 252


# ─────────────────────────────────────────────
#  Base product trader (unchanged)
# ─────────────────────────────────────────────

class ProductTrader:

    def __init__(self, name: str, state: TradingState, new_trader_data: dict):
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

        od = state.order_depths.get(name)
        self.best_bid = max(od.buy_orders)  if od and od.buy_orders  else None
        self.best_ask = min(od.sell_orders) if od and od.sell_orders else None

        self.max_buy  = self.position_limit - self.initial_position
        self.max_sell = self.position_limit + self.initial_position

    def bid(self, price: float, volume: float):
        vol = min(int(abs(volume)), self.max_buy)
        if vol <= 0: return
        self.orders.append(Order(self.name, int(price), vol))
        self.max_buy -= vol

    def ask(self, price: float, volume: float):
        vol = min(int(abs(volume)), self.max_sell)
        if vol <= 0: return
        self.orders.append(Order(self.name, int(price), -vol))
        self.max_sell -= vol

    def get_mid(self):
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None


# ─────────────────────────────────────────────
#  Option trader — vol-space MM + delta hedge
# ─────────────────────────────────────────────

class OptionTrader:

    def __init__(self, state: TradingState, new_trader_data: dict):
        self.state           = state
        self.new_trader_data = new_trader_data

        self.underlying = ProductTrader(UNDERLYING, state, new_trader_data)
        self.options    = {v: ProductTrader(v, state, new_trader_data) for v in VOUCHERS}

        # track underlying orders sent this tick to respect position limits
        self._underlying_buy_sent  = 0
        self._underlying_sell_sent = 0

    # ── Vol-space quoted prices ───────────────

    def _quoted_prices(self, S, K, T):
        """
        Returns (bid_price, ask_price) by running BS with bid/ask vol curves.
        The spread lives in vol space — no arbitrary price spread needed.
        """
        m        = moneyness(S, K, T)
        bid_vol  = predict_iv(m, BID_PARAMS)
        ask_vol  = predict_iv(m, ASK_PARAMS)
        bid_px   = bs_call(S, K, T, bid_vol)
        ask_px   = bs_call(S, K, T, ask_vol)
        avg_vol  = (bid_vol + ask_vol) / 2
        delta    = bs_delta(S, K, T, avg_vol)
        return bid_px, ask_px, delta

    # ── Delta hedge the underlying ────────────

    def _hedge_delta(self, delta, filled_size, bought: bool):
        """
        After a fill of `filled_size` contracts, hedge the resulting delta
        immediately by trading the underlying.
        """
        raw = delta * filled_size
        size = int(round(raw))
        if size == 0:
            return

        underlying_pos = self.underlying.initial_position

        if bought:
            # we went long the option → long delta → sell underlying
            sell_vol = min(size,
                           self.underlying.max_sell - self._underlying_sell_sent,
                           underlying_pos + self.underlying.position_limit)
            if sell_vol > 0:
                price = self.underlying.best_bid
                if price is not None:
                    self.underlying.ask(price, sell_vol)
                    self._underlying_sell_sent += sell_vol
        else:
            # we went short the option → short delta → buy underlying
            buy_vol = min(size,
                          self.underlying.max_buy - self._underlying_buy_sent,
                          self.underlying.position_limit - underlying_pos)
            if buy_vol > 0:
                price = self.underlying.best_ask
                if price is not None:
                    self.underlying.bid(price, buy_vol)
                    self._underlying_buy_sent += buy_vol

    # ── Main order generation ─────────────────

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}

        S = self.underlying.get_mid()
        if S is None:
            return out

        T = get_tte(self.state.timestamp)

        for name, trader in self.options.items():
            K = STRIKES[name]

            bid_px, ask_px, delta = self._quoted_prices(S, K, T)
            if bid_px is None or ask_px is None or delta is None:
                continue

            # floor ask at intrinsic value — never quote below parity
            intrinsic = max(0.0, S - K)
            ask_px    = max(ask_px, intrinsic)

            bid_int = math.floor(bid_px)
            ask_int = math.ceil(ask_px)

            pos      = trader.initial_position
            bid_size = max(MAX_QUOTE_SIZE - pos,  0)
            ask_size = max(MAX_QUOTE_SIZE + pos,  0)

            sent_buys  = 0
            sent_sells = 0

            # ── Aggressive cross: eat mispriced orders ──
            if trader.best_ask is not None and trader.best_ask < bid_int:
                eat = min(bid_size, abs(self.state.order_depths[name].sell_orders.get(trader.best_ask, 0)))
                if eat > 0:
                    trader.bid(trader.best_ask, eat)
                    sent_buys += eat
                    self._hedge_delta(delta, eat, bought=True)
                    # step inside the market after eating
                    bid_int = (trader.best_bid + 1) if trader.best_bid is not None else trader.best_ask - 1

            if trader.best_bid is not None and trader.best_bid > ask_int:
                eat = min(ask_size, abs(self.state.order_depths[name].buy_orders.get(trader.best_bid, 0)))
                if eat > 0:
                    trader.ask(trader.best_bid, eat)
                    sent_sells += eat
                    self._hedge_delta(delta, eat, bought=False)
                    ask_int = (trader.best_ask - 1) if trader.best_ask is not None else trader.best_bid + 1

            # ── Passive quotes ──────────────────────────
            remaining_bid = max(bid_size - sent_buys,  0)
            remaining_ask = max(ask_size - sent_sells, 0)

            if bid_int < ask_int:  # only post if spread is valid
                if remaining_bid > 0:
                    trader.bid(bid_int, remaining_bid)
                if remaining_ask > 0:
                    trader.ask(ask_int, remaining_ask)

            if trader.orders:
                out[name] = trader.orders

        # include underlying hedge orders
        if self.underlying.orders:
            out[UNDERLYING] = self.underlying.orders

        return out


# ─────────────────────────────────────────────
#  Top-level trader
# ─────────────────────────────────────────────

class Trader:

    def run(self, state: TradingState):
        new_trader_data = {}

        result = {}
        try:
            trader = OptionTrader(state, new_trader_data)
            result.update(trader.get_orders())
        except: pass

        try:    final_trader_data = json.dumps(new_trader_data)
        except: final_trader_data = ""

        return result, 0, final_trader_data