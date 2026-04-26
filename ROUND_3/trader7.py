from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json


class Trader:
    HYDROGEL = "HYDROGEL_PACK"
    VELVET = "VELVETFRUIT_EXTRACT"
    TRADE_HYDROGEL = True
    TRADE_VELVET = True

    LIMITS = {
        HYDROGEL: 200,
        VELVET: 200,
        "VEV_4000": 300,
        "VEV_4500": 300,
        "VEV_5000": 300,
        "VEV_5100": 300,
        "VEV_5200": 300,
        "VEV_5300": 300,
        "VEV_5400": 300,
        "VEV_5500": 300,
        "VEV_6000": 300,
        "VEV_6500": 300,
    }

    # Empirical average premium over intrinsic value from testing.py.
    VOUCHER_TIME_VALUE = {
        "VEV_4000": 0.01,
        "VEV_4500": 0.01,
        "VEV_5000": 4.92,
        "VEV_5100": 16.71,
        "VEV_5200": 45.45,
        "VEV_5300": 46.76,
        "VEV_5400": 15.95,
        "VEV_5500": 6.64,
        "VEV_6000": 0.50,
        "VEV_6500": 0.50,
    }

    # Only the voucher thresholds with positive scan results are enabled.
    VOUCHER_CONFIG = {
        "VEV_5300": {"buy": 15, "sell": 8, "max_abs_pos": 240, "max_qty": 35},
        "VEV_5400": {"buy": None, "sell": 2, "max_abs_pos": 80, "max_qty": 15},
    }

    HYDRO_MR_WINDOW = 100
    HYDRO_MR_EDGE = 10
    HYDRO_MR_HOLD = 100
    HYDRO_MR_MAX_POS = 80
    HYDRO_MR_QTY = 20
    HYDRO_MR_MAX_SPREAD = 20

    VELVET_MR_WINDOW = 50
    VELVET_MR_EDGE = 5
    VELVET_MR_HOLD = 100
    VELVET_MR_MAX_POS = 80
    VELVET_MR_QTY = 20
    VELVET_MR_MAX_SPREAD = 20
    UNDERLYING_COOLDOWN = 80

    def bid(self):
        return 0

    def _load_data(self, trader_data: str):
        default = {
            "mid_history": {},
            "signed_flow": {},
            "hydro_age": 0,
            "velvet_age": 0,
            "cooldown": {},
        }
        if not trader_data:
            return default
        try:
            data = json.loads(trader_data)
            data.setdefault("mid_history", {})
            data.setdefault("signed_flow", {})
            data.setdefault("hydro_age", 0)
            data.setdefault("velvet_age", 0)
            data.setdefault("cooldown", {})
            if not isinstance(data["mid_history"], dict):
                data["mid_history"] = {}
            if not isinstance(data["signed_flow"], dict):
                data["signed_flow"] = {}
            if not isinstance(data["cooldown"], dict):
                data["cooldown"] = {}
            return data
        except Exception:
            return default

    def _save_data(self, data):
        try:
            return json.dumps(data)[:50000]
        except Exception:
            return ""

    def _best_bid_ask(self, depth: OrderDepth) -> Tuple[Optional[int], int, Optional[int], int]:
        best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
        best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
        bid_vol = depth.buy_orders[best_bid] if best_bid is not None else 0
        ask_vol = abs(depth.sell_orders[best_ask]) if best_ask is not None else 0
        return best_bid, bid_vol, best_ask, ask_vol

    def _mid(self, book):
        return (book["bid"] + book["ask"]) / 2

    def _mean(self, values):
        return sum(values) / len(values) if values else 0

    def _strike(self, product):
        return int(product.split("_")[1])

    def _buy_capacity(self, product, pos, max_abs_pos=None):
        limit = self.LIMITS.get(product, 0)
        if max_abs_pos is not None:
            limit = min(limit, max_abs_pos)
        return max(0, limit - pos)

    def _sell_capacity(self, product, pos, max_abs_pos=None):
        limit = self.LIMITS.get(product, 0)
        if max_abs_pos is not None:
            limit = min(limit, max_abs_pos)
        return max(0, limit + pos)

    def _take_buy_levels(self, product, depth, fair, threshold, pos, max_qty, max_abs_pos=None):
        orders = []
        remaining = min(max_qty, self._buy_capacity(product, pos, max_abs_pos))
        if remaining <= 0:
            return orders

        for price, volume in sorted(depth.sell_orders.items()):
            if price >= fair - threshold or remaining <= 0:
                break
            qty = min(abs(volume), remaining)
            if qty > 0:
                orders.append(Order(product, price, qty))
                remaining -= qty
        return orders

    def _take_sell_levels(self, product, depth, fair, threshold, pos, max_qty, max_abs_pos=None):
        orders = []
        remaining = min(max_qty, self._sell_capacity(product, pos, max_abs_pos))
        if remaining <= 0:
            return orders

        for price, volume in sorted(depth.buy_orders.items(), reverse=True):
            if price <= fair + threshold or remaining <= 0:
                break
            qty = min(volume, remaining)
            if qty > 0:
                orders.append(Order(product, price, -qty))
                remaining -= qty
        return orders

    def _passive_buy_price(self, best_bid, best_ask):
        return min(best_bid + 1, best_ask - 1)

    def _passive_sell_price(self, best_bid, best_ask):
        return max(best_ask - 1, best_bid + 1)

    def _trade_attr(self, trade, name, default=None):
        if isinstance(trade, dict):
            return trade.get(name, default)
        return getattr(trade, name, default)

    def _signed_public_flow(self, state: TradingState, product, book):
        flow = 0
        market_trades = getattr(state, "market_trades", {}) or {}
        for trade in market_trades.get(product, []):
            buyer = self._trade_attr(trade, "buyer", "")
            seller = self._trade_attr(trade, "seller", "")
            if buyer == "SUBMISSION" or seller == "SUBMISSION":
                continue

            price = self._trade_attr(trade, "price", None)
            quantity = self._trade_attr(trade, "quantity", 0)
            if price is None:
                continue

            if price >= book["ask"]:
                flow += quantity
            elif price <= book["bid"]:
                flow -= quantity
            elif price > self._mid(book):
                flow += quantity
            elif price < self._mid(book):
                flow -= quantity
        return flow

    def _rolling_public_flow(self, state, data, product, book, window):
        flow = self._signed_public_flow(state, product, book)
        flow_by_product = data.setdefault("signed_flow", {})
        flow_hist = flow_by_product.get(product, [])
        flow_hist.append(flow)
        if len(flow_hist) > window:
            flow_hist = flow_hist[-window:]
        flow_by_product[product] = flow_hist
        data["signed_flow"] = flow_by_product
        return flow, sum(flow_hist)

    def _trade_vouchers(self, state, books, result):
        if self.VELVET not in books:
            return

        underlying_mid = self._mid(books[self.VELVET])
        for product, config in self.VOUCHER_CONFIG.items():
            if product not in state.order_depths:
                continue

            depth = state.order_depths[product]
            if product not in books:
                continue

            strike = self._strike(product)
            fair = max(underlying_mid - strike, 0) + self.VOUCHER_TIME_VALUE[product]
            pos = state.position.get(product, 0)
            orders = []

            buy_threshold = config["buy"]
            if buy_threshold is not None:
                orders.extend(
                    self._take_buy_levels(
                        product,
                        depth,
                        fair,
                        buy_threshold,
                        pos,
                        config["max_qty"],
                        config["max_abs_pos"],
                    )
                )
                pos += sum(order.quantity for order in orders if order.quantity > 0)

            sell_threshold = config["sell"]
            if sell_threshold is not None:
                orders.extend(
                    self._take_sell_levels(
                        product,
                        depth,
                        fair,
                        sell_threshold,
                        pos,
                        config["max_qty"],
                        config["max_abs_pos"],
                    )
                )

            if orders:
                result[product].extend(orders)

    def _trade_velvetfruit(self, state, data, books, result):
        product = self.VELVET

        if product not in books or product not in state.order_depths:
            return

        hist = data["mid_history"].get(product, [])
        if len(hist) < self.VELVET_MR_WINDOW:
            return

        book = books[product]
        pos = state.position.get(product, 0)

        best_bid = book["bid"]
        best_ask = book["ask"]
        spread = best_ask - best_bid
        mid = self._mid(book)

        if spread > self.VELVET_MR_MAX_SPREAD:
            return

        ma = self._mean(hist[-self.VELVET_MR_WINDOW:])
        edge = mid - ma
        age = data.get("velvet_age", 0)
        age = age + 1 if pos != 0 else 0
        data["velvet_age"] = age
        orders = []

        # Tested edge: Velvet worked best as short-only mean reversion.
        if pos < 0 and (edge <= 0 or age >= self.VELVET_MR_HOLD):
            qty = min(self.VELVET_MR_QTY, -pos)
            price = self._passive_buy_price(best_bid, best_ask)
            if qty > 0 and price < best_ask:
                orders.append(Order(product, price, qty))
        elif edge >= self.VELVET_MR_EDGE and pos > -self.VELVET_MR_MAX_POS:
            qty = min(
                self.VELVET_MR_QTY,
                pos + self.VELVET_MR_MAX_POS,
                self._sell_capacity(product, pos, self.VELVET_MR_MAX_POS),
            )
            price = self._passive_sell_price(best_bid, best_ask)
            if qty > 0 and price > best_bid:
                orders.append(Order(product, price, -qty))

        if orders:
            result[product].extend(orders)

        print(
            f"{product} MR_SHORT pos={pos} spread={spread} "
            f"edge50={edge:.1f} age={age} orders={orders}"
        )

    def _trade_hydrogel(self, state, data, books, result):
        product = self.HYDROGEL

        if product not in books or product not in state.order_depths:
            return

        hist = data["mid_history"].get(product, [])
        if len(hist) < self.HYDRO_MR_WINDOW:
            return

        book = books[product]

        best_bid = book["bid"]
        best_ask = book["ask"]
        pos = state.position.get(product, 0)
        spread = best_ask - best_bid

        if spread > self.HYDRO_MR_MAX_SPREAD:
            return

        mid = self._mid(book)
        ma = self._mean(hist[-self.HYDRO_MR_WINDOW:])
        edge = mid - ma
        age = data.get("hydro_age", 0)
        age = age + 1 if pos != 0 else 0
        data["hydro_age"] = age
        orders = []

        # Tested edge: Hydrogel was useful only as passive mean reversion.
        if pos > 0 and (edge >= 0 or age >= self.HYDRO_MR_HOLD):
            qty = min(self.HYDRO_MR_QTY, pos)
            price = self._passive_sell_price(best_bid, best_ask)
            if qty > 0 and price > best_bid:
                orders.append(Order(product, price, -qty))
        elif pos < 0 and (edge <= 0 or age >= self.HYDRO_MR_HOLD):
            qty = min(self.HYDRO_MR_QTY, -pos)
            price = self._passive_buy_price(best_bid, best_ask)
            if qty > 0 and price < best_ask:
                orders.append(Order(product, price, qty))
        elif edge <= -self.HYDRO_MR_EDGE and pos < self.HYDRO_MR_MAX_POS:
            qty = min(
                self.HYDRO_MR_QTY,
                self.HYDRO_MR_MAX_POS - pos,
                self._buy_capacity(product, pos, self.HYDRO_MR_MAX_POS),
            )
            price = self._passive_buy_price(best_bid, best_ask)
            if qty > 0 and price < best_ask:
                orders.append(Order(product, price, qty))
        elif edge >= self.HYDRO_MR_EDGE and pos > -self.HYDRO_MR_MAX_POS:
            qty = min(
                self.HYDRO_MR_QTY,
                pos + self.HYDRO_MR_MAX_POS,
                self._sell_capacity(product, pos, self.HYDRO_MR_MAX_POS),
            )
            price = self._passive_sell_price(best_bid, best_ask)
            if qty > 0 and price > best_bid:
                orders.append(Order(product, price, -qty))

        if orders:
            result[product].extend(orders)

        print(
            f"{product} MR_BOTH pos={pos} spread={spread} "
            f"edge100={edge:.1f} age={age} orders={orders}"
        )

    def _update_histories(self, data, books):
        histories = data["mid_history"]
        for product, book in books.items():
            hist = histories.get(product, [])
            hist.append(self._mid(book))
            if len(hist) > 250:
                hist = hist[-250:]
            histories[product] = hist
        data["mid_history"] = histories

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {product: [] for product in state.order_depths}
        conversions = 0
        data = self._load_data(state.traderData)

        books = {}
        for product, depth in state.order_depths.items():
            bid, bid_vol, ask, ask_vol = self._best_bid_ask(depth)
            if bid is None or ask is None:
                continue
            books[product] = {"bid": bid, "bid_vol": bid_vol, "ask": ask, "ask_vol": ask_vol}

        self._trade_vouchers(state, books, result)
        if self.TRADE_VELVET:
            self._trade_velvetfruit(state, data, books, result)
        if self.TRADE_HYDROGEL:
            self._trade_hydrogel(state, data, books, result)
        self._update_histories(data, books)

        return result, conversions, self._save_data(data)