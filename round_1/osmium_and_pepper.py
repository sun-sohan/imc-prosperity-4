from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:

    def bid(self):
        return 0
    
    def run(self, state: TradingState):

        result = {}
        my_EMA = -1

        for product in state.order_depths:
            if product == "ASH_COATED_OSMIUM":
                order_depth: OrderDepth = state.order_depths[product]
                my_position = state.position.get(product, 0)
                orders: List[Order] = []

                if order_depth.sell_orders and order_depth.buy_orders:

                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    mid_price = (min_ask + max_bid) / 2.0

                    fair_value = mid_price

                    position_limit = 70

                    if my_position > int(position_limit / (1.2)):
                        orders.append(Order(product, int(fair_value), -30))

                    elif my_position < -int(position_limit / (1.2)):
                        orders.append(Order(product, int(fair_value), 30))

                    # take any favorable trades
                    for ask, amount in list(order_depth.sell_orders.items()):
                        if ask <= fair_value - 2:
                            orders.append(Order(product, ask, min(position_limit - my_position, -amount)))
                    
                    for bid, amount in list(order_depth.buy_orders.items()):
                        if bid >= fair_value + 2:
                            orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                    # use the spread
                    if min_ask >= fair_value + 2:
                        my_amount = max(min_ask_amount, -my_position - position_limit)
                        orders.append(Order(product, min_ask - 1, my_amount))

                    if max_bid <= fair_value - 2:
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
                position_limit = 70

                if order_depth.sell_orders and order_depth.buy_orders:

                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    mid_price = (min_ask + max_bid) / 2.0

                    last_EMA = 0
                    if state.traderData != "":
                        last_EMA = float(state.traderData)
                    else:
                        last_EMA = mid_price

                    my_EMA = mid_price * k + last_EMA * (1.0 - k)
                    
                    fair_value = my_EMA

                    if my_position > int(position_limit / (1.2)):
                        orders.append(Order(product, int(fair_value), -30))

                    elif my_position < -int(position_limit / (1.2)):
                        orders.append(Order(product, int(fair_value), 30))

                    else:
                        # take any favorable trades
                        for ask, amount in list(order_depth.sell_orders.items()):
                            if ask <= fair_value:
                                orders.append(Order(product, ask, min(position_limit - my_position, -amount)))
                        
                        for bid, amount in list(order_depth.buy_orders.items()):
                            if bid >= fair_value + 7:
                                orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                        # use the spread
                        if min_ask >= fair_value + 7:
                            my_amount = max(min_ask_amount, -my_position - position_limit)
                            orders.append(Order(product, min_ask - 1, my_amount))

                        if max_bid <= fair_value:
                            my_amount = min(max_bid_amount, position_limit - my_position)
                            orders.append(Order(product, max_bid + 1, my_amount))
                    
                elif order_depth.sell_orders and state.traderData != "":
                    min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                    
                    last_EMA = 0
                    last_EMA = float(state.traderData)

                    my_EMA = last_EMA
                    fair_value = my_EMA

                    # take favorable trades
                    for ask, amount in list(order_depth.sell_orders.items()):
                        if ask <= fair_value:
                            orders.append(Order(product, ask, min(position_limit - my_position, -amount)))

                    # use spread
                    if min_ask >= fair_value + 7:
                            my_amount = max(min_ask_amount, -my_position - position_limit)
                            orders.append(Order(product, min_ask - 1, my_amount))

                elif order_depth.buy_orders and state.traderData != "":
                    max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                    
                    last_EMA = 0
                    last_EMA = float(state.traderData)

                    my_EMA = last_EMA
                    fair_value = my_EMA

                    # take favorable trades
                    for bid, amount in list(order_depth.buy_orders.items()):
                        if bid >= fair_value + 7:
                            orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                    # use spread
                    if max_bid <= fair_value:
                            my_amount = min(max_bid_amount, position_limit - my_position)
                            orders.append(Order(product, max_bid + 1, my_amount))

                elif state.traderData != "":
                    last_EMA = float(state.traderData)
                    my_EMA = last_EMA

                result[product] = orders

        if my_EMA == -1 and state.traderData != "":
            last_EMA = float(state.traderData)
            my_EMA = last_EMA
    
        traderData = str(my_EMA)
        conversions = 0
        return result, conversions, traderData