"""
this doesnt work / the data is wrong
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pathlib
import sys

# Add parent directory to sys.path so we can import strategy and datamodel
project_root = pathlib.Path(r"c:\Users\Ashvin\Desktop\Projects\prosperity\imc-prosperity-4")
sys.path.append(str(project_root))

from strategy import Trader
from datamodel import TradingState, OrderDepth, Trade, Listing, Observation

def main():
    prices_csv = project_root / "testing_shit" / "prices_14d0e571-0c75-4431-b787-800d4212a0d5.csv"
    trades_csv = project_root / "testing_shit" / "trades_market_14d0e571-0c75-4431-b787-800d4212a0d5.csv"
    
    print("Loading data...")
    prices_df = pd.read_csv(prices_csv, sep=';')
    trades_df = pd.read_csv(trades_csv, sep=';')
    
    # Group market trades by timestamp so we can feed them into TradingState
    print("Processing market trades...")
    market_trades_by_ts = {}
    for ts, group in trades_df.groupby('timestamp'):
        ts_trades = {}
        for _, row in group.iterrows():
            symbol = row['symbol']
            if symbol not in ts_trades:
                ts_trades[symbol] = []
                
            buyer = row['buyer'] if pd.notna(row['buyer']) else ""
            seller = row['seller'] if pd.notna(row['seller']) else ""
            ts_trades[symbol].append(
                Trade(symbol, int(row['price']), int(row['quantity']), buyer, seller, ts)
            )
        market_trades_by_ts[ts] = ts_trades
        
    trader = Trader()
    traderData = ""
    position = {}
    balance = {}
    own_trades = {}
    active_orders = {}
    pnl_history = []
    
    timestamps = sorted(prices_df['timestamp'].unique())
    
    print("Starting backtest loop...")
    for ts in timestamps:
        if ts % 10000 == 0:
            print(f"  -> Reached timestamp {ts}")
            
        ts_prices = prices_df[prices_df['timestamp'] == ts]
        
        order_depths = {}
        listings = {}
        mid_prices = {}
        
        # Reconstruct the order book state for this tick
        for _, row in ts_prices.iterrows():
            product = row['product']
            listings[product] = Listing(product, product, "SEASHELLS")
            position.setdefault(product, 0)
            balance.setdefault(product, 0.0)
            mid_prices[product] = row['mid_price']
            
            od = OrderDepth()
            for i in range(1, 4):
                bp, bv = row.get(f'bid_price_{i}'), row.get(f'bid_volume_{i}')
                if pd.notna(bp) and pd.notna(bv):
                    od.buy_orders[int(bp)] = int(bv)
                
                ap, av = row.get(f'ask_price_{i}'), row.get(f'ask_volume_{i}')
                if pd.notna(ap) and pd.notna(av):
                    od.sell_orders[int(ap)] = -int(av) # Internal engine represents sell volume as negative
                    
            order_depths[product] = od
            
        # 1. Maker fills: match active_orders from previous tick against incoming market trades
        market_trades = market_trades_by_ts.get(ts, {})
        filtered_market_trades = {}
        
        for product, m_trades in market_trades.items():
            surviving_m_trades = []
            for mt in m_trades:
                rem_mt_qty = mt.quantity
                
                if product in active_orders:
                    # Match against resting orders
                    for order in active_orders[product]:
                        if order.quantity > 0 and mt.price <= order.price and rem_mt_qty > 0:
                            fill = min(order.quantity, rem_mt_qty)
                            position[product] += fill
                            balance[product] -= fill * order.price
                            order.quantity -= fill
                            rem_mt_qty -= fill
                            own_trades.setdefault(product, []).append(Trade(product, order.price, fill, "YOU", "BOT", ts))
                        elif order.quantity < 0 and mt.price >= order.price and rem_mt_qty > 0:
                            fill = min(-order.quantity, rem_mt_qty)
                            position[product] -= fill
                            balance[product] += fill * order.price
                            order.quantity += fill  # order.quantity is negative, so adding fill brings it closer to 0
                            rem_mt_qty -= fill
                            own_trades.setdefault(product, []).append(Trade(product, order.price, fill, "BOT", "YOU", ts))
                            
                if rem_mt_qty > 0:
                    surviving_m_trades.append(Trade(product, mt.price, rem_mt_qty, mt.buyer, mt.seller, ts))
            
            if surviving_m_trades:
                filtered_market_trades[product] = surviving_m_trades
        
        state = TradingState(
            traderData=traderData, timestamp=ts, listings=listings, order_depths=order_depths,
            own_trades=own_trades, market_trades=filtered_market_trades, position=position.copy(),
            observations=Observation({}, {})
        )
        
        orders, conversions, traderData = trader.run(state)
        own_trades = {} # Reset to populate with fills from THIS tick for the next state
        active_orders = {} # Reset active orders (DAY order lifecycle)
        
        # 2. Taker fills: Simulated matching engine against current book
        for product, prod_orders in orders.items():
            active_orders[product] = []
            own_trades.setdefault(product, [])
            od = order_depths[product]
            
            for order in prod_orders:
                if order.quantity > 0:  # BUY
                    rem_qty = order.quantity
                    for price in sorted(od.sell_orders.keys()):
                        if price <= order.price and rem_qty > 0:
                            avail = -od.sell_orders[price]
                            if avail <= 0: continue
                            fill = min(rem_qty, avail)
                            rem_qty -= fill
                            od.sell_orders[price] += fill
                            position[product] += fill
                            balance[product] -= fill * price
                            own_trades[product].append(Trade(product, price, fill, "YOU", "BOT", ts))
                    if rem_qty > 0:
                        order.quantity = rem_qty
                        active_orders[product].append(order)
                            
                elif order.quantity < 0:  # SELL
                    rem_qty = -order.quantity
                    for price in sorted(od.buy_orders.keys(), reverse=True):
                        if price >= order.price and rem_qty > 0:
                            avail = od.buy_orders[price]
                            if avail <= 0: continue
                            fill = min(rem_qty, avail)
                            rem_qty -= fill
                            od.buy_orders[price] -= fill
                            position[product] -= fill
                            balance[product] += fill * price
                            own_trades[product].append(Trade(product, price, fill, "BOT", "YOU", ts))
                    if rem_qty > 0:
                        order.quantity = -rem_qty
                        active_orders[product].append(order)
                            
        # Track state PnL
        current_pnl = sum(balance[p] + position[p] * mid_prices[p] for p in position)
        pnl_history.append({'timestamp': ts, 'pnl': current_pnl})
        
    print("Backtest complete!")
    print("-" * 30)
    print("Final Positions:", position)
    print("Final Balances:", {k: round(v, 2) for k, v in balance.items()})
    print("Final PnL by Symbol:")
    for p in position:
        print(f"  {p}: {balance[p] + position[p] * mid_prices[p]:.2f}")
    print(f"Total PnL: {pnl_history[-1]['pnl']:.2f}")
    
    # Plot cumulative PnL
    pnl_df = pd.DataFrame(pnl_history)
    plt.figure(figsize=(10, 5))
    plt.plot(pnl_df['timestamp'], pnl_df['pnl'], label='Simulated PnL', color='g', linewidth=2)
    plt.title('Backtest cumulative PnL')
    plt.xlabel('Timestamp')
    plt.ylabel('PnL')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()