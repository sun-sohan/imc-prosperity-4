import json
from typing import Any

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
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

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
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

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])
        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed: dict[Symbol, list[Any]] = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
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

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
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


class Trader:
    # Adjust limits if Round 4 wiki specifies different per-product limits
    POSITION_LIMITS = {
        "OXYGEN_SHAKE_MORNING_BREATH": 10,
        "OXYGEN_SHAKE_EVENING_BREATH": 10,
        "OXYGEN_SHAKE_CHOCOLATE": 10,
        "OXYGEN_SHAKE_GARLIC": 10,
    }

    BASE_QUOTE_SIZE = {
        "OXYGEN_SHAKE_MORNING_BREATH": 3,
        "OXYGEN_SHAKE_EVENING_BREATH": 5,
        "OXYGEN_SHAKE_CHOCOLATE": 4,
        "OXYGEN_SHAKE_GARLIC": 2,
    }

    INVENTORY_SKEW_COEFF = 0.15
    MIN_SPREAD_FOR_PASSIVE = 2  # only passive MM when spread wide enough

    def run(self, state: TradingState):
        result: dict[Symbol, list[Order]] = {}
        conversions = 0
        trader_data = ""

        for symbol, listing in state.listings.items():
            product = listing.product

            if product not in self.POSITION_LIMITS:
                continue

            if symbol not in state.order_depths:
                continue

            od = state.order_depths[symbol]
            buy_orders = od.buy_orders
            sell_orders = od.sell_orders

            if not buy_orders or not sell_orders:
                continue

            best_bid = max(buy_orders.keys())
            best_ask = min(sell_orders.keys())
            spread = best_ask - best_bid

            pos = state.position.get(product, 0)
            limit = self.POSITION_LIMITS[product]
            base_size = self.BASE_QUOTE_SIZE[product]

            best_bid_vol = abs(buy_orders[best_bid])
            best_ask_vol = abs(sell_orders[best_ask])

            total_top_vol = best_bid_vol + best_ask_vol
            if total_top_vol > 0:
                fair = (best_ask * best_bid_vol + best_bid * best_ask_vol) / total_top_vol
            else:
                fair = (best_bid + best_ask) / 2

            inventory_skew = self.INVENTORY_SKEW_COEFF * pos
            fair_bid = int(fair - 0.5 - inventory_skew)
            fair_ask = int(fair + 0.5 - inventory_skew)

            orders: list[Order] = []

            # Take obvious mispricings (crossed vs fair)
            if best_ask < fair and pos < limit:
                take_qty = min(base_size, limit - pos, abs(sell_orders[best_ask]))
                if take_qty > 0:
                    orders.append(Order(symbol, best_ask, take_qty))

            if best_bid > fair and pos > -limit:
                take_qty = min(base_size, limit + pos, abs(buy_orders[best_bid]))
                if take_qty > 0:
                    orders.append(Order(symbol, best_bid, -take_qty))

            # Passive market making only when spread is wide enough
            if spread >= self.MIN_SPREAD_FOR_PASSIVE:
                bid_px = min(fair_bid, best_bid + 1)
                ask_px = max(fair_ask, best_ask - 1)

                if bid_px < ask_px:
                    buy_qty = min(base_size, max(0, limit - pos))
                    sell_qty = min(base_size, max(0, limit + pos))

                    if buy_qty > 0:
                        orders.append(Order(symbol, bid_px, buy_qty))
                    if sell_qty > 0:
                        orders.append(Order(symbol, ask_px, -sell_qty))

            if orders:
                result[symbol] = orders

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data