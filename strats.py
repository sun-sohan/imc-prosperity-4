from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import json


class Trader:
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    def bid(self):
        return 0

    def _load_data(self, traderData: str) -> Dict:
        if traderData == "" or traderData is None:
            return {
                "ema_pepper": None
            }
        try:
            return json.loads(traderData)
        except Exception:
            return {
                "ema_pepper": None
            }
    # save state for the next tick
    def _save_data(self, data: Dict) -> str:
        try:
            return json.dumps(data)[:50000]
        except Exception:
            return ""

    def _best_bid_ask(self, order_depth: OrderDepth):
        best_bid, best_bid_amount = None, 0
        best_ask, best_ask_amount = None, 0

        if len(order_depth.buy_orders) > 0:
            best_bid = max(order_depth.buy_orders.keys())
            best_bid_amount = order_depth.buy_orders[best_bid]

        if len(order_depth.sell_orders) > 0:
            best_ask = min(order_depth.sell_orders.keys())
            best_ask_amount = order_depth.sell_orders[best_ask]  # negative

        return best_bid, best_bid_amount, best_ask, best_ask_amount

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        conversions = 0
        data = self._load_data(state.traderData)

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)
            limit = self.POSITION_LIMITS[product]

            best_bid, best_bid_amount, best_ask, best_ask_amount = self._best_bid_ask(order_depth)

            if best_bid is None or best_ask is None:
                result[product] = orders
                continue

            mid_price = (best_bid + best_ask) / 2.0

            if product == "ASH_COATED_OSMIUM":
                fair_value = 10000
                soft_limit = 45
                hard_limit = 68

                # 1) Take clearly favorable prices
                for ask, amount in sorted(order_depth.sell_orders.items()):
                    if ask <= fair_value - 2:
                        buy_qty = min(limit - pos, -amount, 32)
                        if buy_qty > 0:
                            orders.append(Order(product, ask, buy_qty))
                            pos += buy_qty
                    else:
                        break

                for bid, amount in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid >= fair_value + 2:
                        sell_qty = min(pos + limit, amount, 32)
                        if sell_qty > 0:
                            orders.append(Order(product, bid, -sell_qty))
                            pos -= sell_qty
                    else:
                        break

                # 2) Passive quote more often with larger size
                if best_ask >= fair_value:
                    sell_qty = min(24, pos + limit)
                    if pos > soft_limit:
                        sell_qty = min(32, pos + limit)
                    if sell_qty > 0:
                        orders.append(Order(product, best_ask - 1, -sell_qty))

                if best_bid <= fair_value:
                    buy_qty = min(24, limit - pos)
                    if pos < -soft_limit:
                        buy_qty = min(32, limit - pos)
                    if buy_qty > 0:
                        orders.append(Order(product, best_bid + 1, buy_qty))

                # 3) Flatten earlier near fair
                if abs(mid_price - fair_value) <= 1:
                    if pos > 15:
                        qty = min(18, pos)
                        orders.append(Order(product, best_bid, -qty))
                    elif pos < -15:
                        qty = min(18, -pos)
                        orders.append(Order(product, best_ask, qty))

                # 4) Hard unwind
                if pos > hard_limit:
                    qty = min(32, pos)
                    orders.append(Order(product, best_bid, -qty))
                elif pos < -hard_limit:
                    qty = min(32, -pos)
                    orders.append(Order(product, best_ask, qty))

            elif product == "INTARIAN_PEPPER_ROOT":
                N = 18
                k = 2.0 / (N + 1.0)

                last_ema = data.get("ema_pepper")
                if last_ema is None:
                    last_ema = mid_price

                ema = mid_price * k + last_ema * (1.0 - k)
                data["ema_pepper"] = ema

                fair_value = mid_price if state.timestamp <= 2000 else ema

                soft_limit = 28
                hard_limit = 60

                # 1) Take favorable prices
                for ask, amount in sorted(order_depth.sell_orders.items()):
                    if ask <= fair_value - 3:
                        buy_qty = min(limit - pos, -amount, 18)
                        if buy_qty > 0:
                            orders.append(Order(product, ask, buy_qty))
                            pos += buy_qty
                    else:
                        break

                for bid, amount in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid >= fair_value + 3:
                        sell_qty = min(pos + limit, amount, 18)
                        if sell_qty > 0:
                            orders.append(Order(product, bid, -sell_qty))
                            pos -= sell_qty
                    else:
                        break

                # 2) Passive quotes, looser and bigger
                if best_ask >= fair_value + 2:
                    sell_qty = min(18, pos + limit)
                    if pos > soft_limit:
                        sell_qty = min(24, pos + limit)
                    if sell_qty > 0:
                        orders.append(Order(product, best_ask - 1, -sell_qty))

                if best_bid <= fair_value - 2:
                    buy_qty = min(18, limit - pos)
                    if pos < -soft_limit:
                        buy_qty = min(24, limit - pos)
                    if buy_qty > 0:
                        orders.append(Order(product, best_bid + 1, buy_qty))

                # 3) Earlier cleanup near fair
                if abs(mid_price - fair_value) <= 2:
                    if pos > 12:
                        qty = min(16, pos)
                        orders.append(Order(product, best_bid, -qty))
                    elif pos < -12:
                        qty = min(16, -pos)
                        orders.append(Order(product, best_ask, qty))

                # 4) Hard unwind
                if pos > hard_limit:
                    qty = min(24, pos)
                    orders.append(Order(product, best_bid, -qty))
                elif pos < -hard_limit:
                    qty = min(24, -pos)
                    orders.append(Order(product, best_ask, qty))

            print(
                f"{product} | pos={state.position.get(product, 0)} | "
                f"bid={best_bid} ask={best_ask} mid={mid_price:.2f} | "
                f"orders={orders}"
            )

            result[product] = orders

        traderData = self._save_data(data)
        return result, conversions, traderData