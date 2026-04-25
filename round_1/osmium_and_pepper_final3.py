from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:

    def bid(self):
        return 0
    
    def run(self, state: TradingState):

        result = {}
        pepper_EMA = -1
        ash_EMA = -1
        EMAs = state.traderData.split(";")

        for product in state.order_depths:
            if product == "ASH_COATED_OSMIUM":
                order_depth: OrderDepth = state.order_depths[product]
                my_position = state.position.get(product, 0)
                orders: List[Order] = []

                # hyperparams
                N = 200
                k = 2.0 / (N + 1.0)
                bias = 0
                position_limit = 80

                if order_depth.sell_orders and order_depth.buy_orders:

                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    mid_price = (min_ask + max_bid) / 2.0

                    last_EMA = 0
                    if len(EMAs) > 1 and EMAs[1] != "":
                        last_EMA = float(EMAs[1])
                    else:
                        last_EMA = mid_price

                    ash_EMA = (mid_price + bias) * k + last_EMA * (1.0 - k)

                    # fair value - mid price
                    # >0 => reversion up
                    # <0 => reversion down
                    deviation = ash_EMA - mid_price
                    
                    fair_value = ash_EMA

                    if deviation < -2 and my_position > int(position_limit / (1.5)):
                        orders.append(Order(product, int(fair_value), -20))

                    elif deviation > 2 and my_position < -int(position_limit / (1.5)):
                        orders.append(Order(product, int(fair_value), 20))

                    else: 
                        cur_position = my_position

                        # take any favorable trades
                        for ask, amount in list(order_depth.sell_orders.items()):
                            if ask <= fair_value - 1:
                                my_amount = min(position_limit - cur_position, -amount)
                                orders.append(Order(product, ask, my_amount))
                                cur_position += my_amount
                        
                        for bid, amount in list(order_depth.buy_orders.items()):
                            if bid >= fair_value + 1:
                                my_amount = max(-position_limit - cur_position, -amount)
                                orders.append(Order(product, bid, my_amount))
                                cur_position += my_amount

                        # use the spread
                        if min_ask >= fair_value + 1:
                            ask_amount = min_ask_amount
                            if deviation < -2:
                                ask_amount = min(-20, 2 * ask_amount)
                            my_amount = max(ask_amount, -position_limit - cur_position)
                            orders.append(Order(product, min_ask - 1, my_amount))
                            cur_position += my_amount

                        if max_bid <= fair_value - 1:
                            bid_amount = max_bid_amount
                            if deviation > 2:
                                bid_amount = max(20, 2 * bid_amount)
                            my_amount = min(bid_amount, position_limit - cur_position)
                            orders.append(Order(product, max_bid + 1, my_amount))
                            cur_position += my_amount
                
                result[product] = orders

            elif product == "INTARIAN_PEPPER_ROOT":
                order_depth: OrderDepth = state.order_depths[product]
                my_position = state.position.get(product, 0)
                orders: List[Order] = []

                # hyperparams
                N = 800
                k = 2.0 / (N + 1.0)
                uptrend_position = 80
                downtrend_position = -80

                if order_depth.sell_orders and order_depth.buy_orders:

                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    mid_price = (min_ask + max_bid) / 2.0

                    last_EMA = 0
                    if len(EMAs) > 0 and EMAs[0] != "":
                        last_EMA = float(EMAs[0])
                    else:
                        last_EMA = mid_price

                    pepper_EMA = mid_price * k + last_EMA * (1.0 - k)

                    if mid_price >= pepper_EMA:
                        cur_position = my_position

                        for ask, amount in list(order_depth.sell_orders.items()):
                            if ask <= mid_price + 10:
                                my_amount = min(uptrend_position - cur_position, -amount)
                                orders.append(Order(product, ask, my_amount))
                                cur_position += my_amount
                        
                        orders.append(Order(product, max_bid, uptrend_position - cur_position))

                    elif mid_price < pepper_EMA:
                        cur_position = my_position

                        for bid, amount in list(order_depth.buy_orders.items()):
                            if bid >= mid_price - 10:
                                my_amount = max(downtrend_position - cur_position, -amount)
                                orders.append(Order(product, bid, my_amount))
                                cur_position += my_amount

                        orders.append(Order(product, min_ask, downtrend_position - cur_position))

                result[product] = orders

        if pepper_EMA == -1 and len(EMAs) > 0 and EMAs[0] != "":
            last_EMA = float(state.traderData.split(";")[0])
            pepper_EMA = last_EMA

        if ash_EMA == -1 and len(EMAs) > 1 and EMAs[1] != "":
            last_EMA = float(state.traderData.split(";")[1])
            ash_EMA = last_EMA
    
        traderData = (str(pepper_EMA) if pepper_EMA != -1 else "") + ";" + (str(ash_EMA) if ash_EMA != -1 else "")
        conversions = 0
        return result, conversions, traderData