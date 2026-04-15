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
                N = 120
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

                    deviation = ash_EMA - mid_price
                    
                    fair_value = ash_EMA

                    if deviation < 0 and my_position > int(position_limit / (1.5)):
                        orders.append(Order(product, int(fair_value), -40))

                    elif deviation > 0 and my_position < -int(position_limit / (1.5)):
                        orders.append(Order(product, int(fair_value), 40))

                    else: 
                        # take any favorable trades
                        for ask, amount in list(order_depth.sell_orders.items()):
                            if ask <= fair_value - 1:
                                orders.append(Order(product, ask, min(position_limit - my_position, -amount)))
                        
                        for bid, amount in list(order_depth.buy_orders.items()):
                            if bid >= fair_value + 1:
                                orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                        # use the spread
                        if min_ask >= fair_value + 1:
                            my_amount = max(min_ask_amount, -my_position - position_limit)
                            orders.append(Order(product, min_ask - 1, my_amount))

                        if max_bid <= fair_value - 1:
                            my_amount = min(max_bid_amount, position_limit - my_position)
                            orders.append(Order(product, max_bid + 1, my_amount))
                
                result[product] = orders

            elif product == "INTARIAN_PEPPER_ROOT":
                order_depth: OrderDepth = state.order_depths[product]
                my_position = state.position.get(product, 0)
                orders: List[Order] = []

                # hyperparams
                N = 8
                k = 2.0 / (N + 1.0)
                bias = 10
                position_limit = 80

                if order_depth.sell_orders and order_depth.buy_orders:

                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    mid_price = (min_ask + max_bid) / 2.0

                    last_EMA = 0
                    if len(EMAs) > 0 and EMAs[0] != "":
                        last_EMA = float(EMAs[0])
                    else:
                        last_EMA = mid_price

                    pepper_EMA = (mid_price + bias) * k + last_EMA * (1.0 - k)
                    
                    fair_value = pepper_EMA

                    if my_position > int(position_limit / (1.2)):
                        orders.append(Order(product, int(fair_value), -25))

                    elif my_position < -int(position_limit / (1.2)):
                        orders.append(Order(product, int(fair_value), 25))

                    else:
                        # take any favorable trades
                        for ask, amount in list(order_depth.sell_orders.items()):
                            if ask <= fair_value + 2:
                                orders.append(Order(product, ask, min(position_limit - my_position, -amount)))
                        
                        for bid, amount in list(order_depth.buy_orders.items()):
                            if bid >= fair_value + 7:
                                orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                        # use the spread
                        if min_ask >= fair_value + 7:
                            my_amount = max(min_ask_amount, -my_position - position_limit)
                            orders.append(Order(product, min_ask - 1, my_amount))

                        if max_bid <= fair_value + 2:
                            my_amount = min(max_bid_amount, position_limit - my_position)
                            orders.append(Order(product, max_bid + 1, my_amount))
                    
                elif order_depth.sell_orders and len(EMAs) > 0 and EMAs[0] != "":
                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    
                    last_EMA = 0
                    last_EMA = float(state.traderData.split(";")[0])

                    pepper_EMA = last_EMA
                    fair_value = pepper_EMA

                    # take favorable trades
                    for ask, amount in list(order_depth.sell_orders.items()):
                        if ask <= fair_value + 2:
                            orders.append(Order(product, ask, min(position_limit - my_position, -amount)))

                    # use spread
                    if min_ask >= fair_value + 7:
                            my_amount = max(min_ask_amount, -my_position - position_limit)
                            orders.append(Order(product, min_ask - 1, my_amount))

                elif order_depth.buy_orders and len(EMAs) > 0 and EMAs[0] != "":
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    
                    last_EMA = 0
                    last_EMA = float(state.traderData.split(";")[0])

                    pepper_EMA = last_EMA
                    fair_value = pepper_EMA

                    # take favorable trades
                    for bid, amount in list(order_depth.buy_orders.items()):
                        if bid >= fair_value + 7:
                            orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                    # use spread
                    if max_bid <= fair_value + 2:
                            my_amount = min(max_bid_amount, position_limit - my_position)
                            orders.append(Order(product, max_bid + 1, my_amount))

                elif len(EMAs) > 0 and EMAs[0] != "":
                    last_EMA = float(state.traderData.split(";")[0])
                    pepper_EMA = last_EMA

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