from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:

    def bid(self):
        return 0
    
    def run(self, state: TradingState):

        result = {}
        my_EMA = 0
        for product in state.order_depths:
            if product == "EMERALDS":
                order_depth: OrderDepth = state.order_depths[product]
                my_position = state.position.get(product, 0)
                orders: List[Order] = []

                fair_price = 10000
                position_limit = 60
        
                ask, amount = list(order_depth.sell_orders.items())[0]
                if ask >= fair_price + 2:
                    my_amount = max(amount, -my_position - position_limit)
                    orders.append(Order(product, ask - 1, my_amount))

                bid, amount = list(order_depth.buy_orders.items())[0]
                if bid <= fair_price - 2:
                    my_amount = min(amount, position_limit - my_position)
                    orders.append(Order(product, bid + 1, my_amount))
                
                result[product] = orders

            elif product == "TOMATOES":
                order_depth: OrderDepth = state.order_depths[product]
                my_position = state.position.get(product, 0)
                orders: List[Order] = []

                min_ask, min_ask_amount = list(order_depth.sell_orders.items())[0]
                max_bid, max_bid_amount = list(order_depth.buy_orders.items())[0]
                mid_price = (min_ask + max_bid) / 2.0

                N = 20
                k = 2.0 / (N + 1.0)
                last_EMA = 0
                if state.traderData != "":
                    last_EMA = float(state.traderData)
                else:
                    last_EMA = mid_price

                my_EMA = mid_price * k + last_EMA * (1.0 - k)
                
                fair_value = 0
                if state.timestamp <= 3000:
                    fair_value = mid_price
                else:
                    fair_value = my_EMA

                position_limit = 30

                # take any favorable trades
                for ask, amount in list(order_depth.sell_orders.items()):
                    if ask <= fair_value - 5:
                        orders.append(Order(product, ask, min(position_limit - my_position, -amount)))
                
                for bid, amount in list(order_depth.buy_orders.items()):
                    if bid >= fair_value + 5:
                        orders.append(Order(product, bid, max(-position_limit - my_position, -amount)))

                # use the spread
                if min_ask >= fair_value + 3:
                    my_amount = max(min_ask_amount, -my_position - position_limit)
                    orders.append(Order(product, min_ask - 1, my_amount))

                if max_bid <= fair_value - 3:
                    my_amount = min(max_bid_amount, position_limit - my_position)
                    orders.append(Order(product, max_bid + 1, my_amount))
                
                result[product] = orders
    
        traderData = str(my_EMA)
        conversions = 0
        return result, conversions, traderData