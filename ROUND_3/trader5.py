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

WALL_MAKER_PRODUCTS = ["VELVETFRUIT_EXTRACT", "HYDROGEL_PACK"]
WALL_QUOTE_SIZE = 200
WALL_TAKE_BUFFER = 0.0

VOUCHERS = ["VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]

OPTION_QUOTE_SIZE = 300
OPTION_TAKE_BUFFER = 0.0


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
#  Option market maker (wall-mid, no BS)
# ─────────────────────────────────────────────

class OptionTrader:
    def __init__(self, state, new_trader_data):
        self.state           = state
        self.new_trader_data = new_trader_data
        self.options = {v: ProductTrader(v, state, new_trader_data) for v in VOUCHERS}

    def get_orders(self) -> Dict[str, List[Order]]:
        out = {}

        for name, trader in self.options.items():
            if trader.best_bid is None or trader.best_ask is None:
                continue

            _, wall_mid, _ = trader.get_walls()
            if wall_mid is None:
                continue

            fair_value = wall_mid
            spread = trader.best_ask - trader.best_bid
            pos = trader.initial_position

            # TAKE: hit anything that crosses fair
            for sp, sv in trader.mkt_sell_orders.items():
                if sp < fair_value - OPTION_TAKE_BUFFER:
                    trader.bid(sp, abs(sv))
                else:
                    break
            for bp, bv in trader.mkt_buy_orders.items():
                if bp > fair_value + OPTION_TAKE_BUFFER:
                    trader.ask(bp, abs(bv))
                else:
                    break

            # MAKE: quote inside spread
            if spread > 1:
                bid_price = trader.best_bid + 1
                ask_price = trader.best_ask - 1
            else:
                bid_price = trader.best_bid
                ask_price = trader.best_ask

            buy_size  = min(OPTION_QUOTE_SIZE, trader.max_allowed_buy_volume)
            sell_size = min(OPTION_QUOTE_SIZE, trader.max_allowed_sell_volume)

            # Skew quotes to lean against large positions
            if pos > OPTION_QUOTE_SIZE:
                buy_size = max(0, buy_size - pos // 2)
            elif pos < -OPTION_QUOTE_SIZE:
                sell_size = max(0, sell_size + pos // 2)

            if buy_size > 0:
                trader.bid(bid_price, buy_size)
            if sell_size > 0:
                trader.ask(ask_price, sell_size)

            out[name] = trader.orders

        return out


# ─────────────────────────────────────────────
#  Wall maker
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
            final_trader_data = json.dumps(new_trader_data)
        except Exception:
            final_trader_data = ""

        return result, 0, final_trader_data