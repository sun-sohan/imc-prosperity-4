from datamodel import Listing, Observation, OrderDepth, TradingState, Order, ProsperityEncoder, Symbol, Trade
from typing import List, Dict, Any
import json

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: Dict[str, List[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
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

    def compress_state(self, state: TradingState, trader_data: str):
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

    def compress_listings(self, listings: Dict[Symbol, Listing]):
        compressed = []
        for listing in listings.values():
            if isinstance(listing, dict):
                compressed.append([listing["symbol"], listing["product"], listing["denomination"]])
            else:
                compressed.append([listing.symbol, listing.product, listing.denomination])
        return compressed

    def compress_order_depths(self, order_depths: Dict[Symbol, OrderDepth]) -> Dict[str, List[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
        return compressed

    def compress_trades(self, trades: Dict[Symbol, List[Trade]]) -> List[List[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )
        return compressed

    def compress_observations(self, observations: Observation) -> List[Any]:
        conversion_observations = {}
        for product, obs in observations.conversionObservations.items():
            sunlight = getattr(obs, "sunlight", getattr(obs, "sunlightIndex", None))
            humidity = getattr(obs, "humidity", getattr(obs, "sugarPrice", None))
            conversion_observations[product] = [
                obs.bidPrice,
                obs.askPrice,
                obs.transportFees,
                obs.exportTariff,
                obs.importTariff,
                sunlight,
                humidity,
            ]
        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: Dict[str, List[Order]]) -> List[List[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])
        return compressed

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

            encoded_candidate = json.dumps(candidate)

            if len(encoded_candidate) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        return out

logger = Logger()

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

PRODUCTS = {
    "VELVETFRUIT_EXTRACT": {"position_limit": 200},
    "HYDROGEL_PACK":       {"position_limit": 200},
    "VEV_4000":  {"position_limit": 300},
    "VEV_4500":  {"position_limit": 300},
    "VEV_5000":  {"position_limit": 300},
    "VEV_5100":  {"position_limit": 300},
    "VEV_5200":  {"position_limit": 300},
    "VEV_5300":  {"position_limit": 300},
    "VEV_5400":  {"position_limit": 300},
    "VEV_5500":  {"position_limit": 300},
    "VEV_6000":  {"position_limit": 300},
    "VEV_6500":  {"position_limit": 300},
}

# ── EMA MR params ─────────────────────────────
VELVET_MR_WINDOW  = 1000
VELVET_MR_THR     = 5

VOUCHER_MR_WINDOW = 1000
VOUCHER_MR_THR    = 5

HYDRO_MR_WINDOW      = 1000
HYDRO_MR_THR         = 10
HYDRO_MAX_ORDER_SIZE = 50   # max units per signal tick
# If position is already beyond this (in the signal direction),
# block new entries — prevents piling into a trending move.
HYDRO_POSITION_BLOCK = 150  # out of 200 limit

# ── Voucher lists ─────────────────────────────
MR_VOUCHERS   = ["VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]
SKIP_VOUCHERS = ["VEV_6000", "VEV_6500"]

# ─────────────────────────────────────────────
# Base product trader
# ─────────────────────────────────────────────

class ProductTrader:
    def __init__(self, name, state, new_trader_data):
        self.name = name
        self.state = state
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
            buy_orders  = {bp: abs(bv) for bp, bv in sorted(od.buy_orders.items(),  reverse=True)}
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
# EMA MR Trader — shared logic (unchanged for
# velvet + vouchers)
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
        self.traders = {p: ProductTrader(p, state, new_trader_data) for p in products}

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}
        for name, trader in self.traders.items():
            bid_wall, wall_mid, ask_wall = trader.get_walls()
            if wall_mid is None:
                continue

            td_key    = f"ema_mr_{name}"
            ema       = trader.calculate_ema(td_key, self.window, wall_mid)
            deviation = wall_mid - ema

            if deviation > self.threshold and trader.max_allowed_sell_volume > 0:
                trader.ask(bid_wall + 1, trader.max_allowed_sell_volume)

            elif deviation < -self.threshold and trader.max_allowed_buy_volume > 0:
                trader.bid(ask_wall - 1, trader.max_allowed_buy_volume)

            if trader.orders:
                out[name] = trader.orders

        return out

# ─────────────────────────────────────────────
# Hydrogel-specific trader
#
# Changes vs original:
#   1. EMA tracks best_mid = (best_bid + best_ask) / 2
#      instead of noisy outer wall_mid
#   2. Order size capped at HYDRO_MAX_ORDER_SIZE (50)
#   3. Position-aware signal blocking: if already short
#      beyond HYDRO_POSITION_BLOCK, ignore sell signals;
#      if already long beyond HYDRO_POSITION_BLOCK,
#      ignore buy signals. Prevents piling into trends.
# ─────────────────────────────────────────────

class HydrogelTrader:
    def __init__(self, state, new_trader_data):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.trader          = ProductTrader("HYDROGEL_PACK", state, new_trader_data)

    def get_orders(self) -> Dict[str, List[Order]]:
        trader   = self.trader
        best_bid = trader.best_bid
        best_ask = trader.best_ask

        if best_bid is None or best_ask is None:
            return {}

        best_mid  = (best_bid + best_ask) / 2
        td_key    = "ema_mr_HYDROGEL_PACK"
        ema       = trader.calculate_ema(td_key, HYDRO_MR_WINDOW, best_mid)
        deviation = best_mid - ema

        pos = trader.initial_position  # current signed position

        if deviation > HYDRO_MR_THR and trader.max_allowed_sell_volume > 0:
            # Block sell signal if already heavily short (trending down — don't chase)
            if pos <= -HYDRO_POSITION_BLOCK:
                return {}
            size = min(trader.max_allowed_sell_volume, HYDRO_MAX_ORDER_SIZE)
            trader.ask(best_bid + 1, size)

        elif deviation < -HYDRO_MR_THR and trader.max_allowed_buy_volume > 0:
            # Block buy signal if already heavily long (trending up — don't chase)
            if pos >= HYDRO_POSITION_BLOCK:
                return {}
            size = min(trader.max_allowed_buy_volume, HYDRO_MAX_ORDER_SIZE)
            trader.bid(best_ask - 1, size)

        return {"HYDROGEL_PACK": trader.orders} if trader.orders else {}

# ─────────────────────────────────────────────
# Top-level Trader
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

        # VELVETFRUIT — EMA mean reversion (unchanged)
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

        # Vouchers (excl. 6000/6500) — EMA mean reversion (unchanged)
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

        # Hydrogel — best_mid EMA + capped size + position block
        try:
            hydrogel_mr = HydrogelTrader(state, new_trader_data)
            result.update(hydrogel_mr.get_orders())
        except Exception:
            pass

        try:
            final_trader_data = json.dumps(new_trader_data)
        except Exception:
            final_trader_data = ""

        conversions = 0
        logger.flush(state, result, conversions, final_trader_data)
        return result, conversions, final_trader_data