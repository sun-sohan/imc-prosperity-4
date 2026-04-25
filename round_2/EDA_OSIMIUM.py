import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

cutoff = 10000000
product = 'ASH_COATED_OSMIUM'

# -----------------------
# PRICE DATA
# -----------------------
df = pd.read_csv('round_1/data_capsule/prices_round_1_day_0.csv', sep=';')
df = df[df['product'] == product].copy()
df = df.sort_values('timestamp').reset_index(drop=True)
df = df.iloc[:cutoff].copy()

# remove bogus rows
df = df[df['mid_price'] >= 100].reset_index(drop=True)

# use row number for x-axis so spacing is uniform
x = np.arange(len(df))

y1 = df['ask_price_1']
y2 = df['bid_price_1']
y3 = df['mid_price']
y4 = y3.ewm(span=80, adjust=False).mean()

# -----------------------
# TRADE DATA
# -----------------------
trades = pd.read_csv('round_1/data_capsule/trades_round_1_day_-1.csv', sep=';')
trades = trades[trades['symbol'] == product].copy()
trades = trades.sort_values('timestamp').reset_index(drop=True)
trades = trades.iloc[:cutoff].copy()

# optional cleanup for weird trade prices
trades = trades[trades['price'] >= 100].reset_index(drop=True)

# map trade timestamps onto the price row index so they align visually
timestamp_to_x = {ts: i for i, ts in enumerate(df['timestamp'])}
trades = trades[trades['timestamp'].isin(timestamp_to_x)].copy()
trades['x'] = trades['timestamp'].map(timestamp_to_x)

tx = trades['x']
tp = trades['price']
tq = trades['quantity'].abs()

# marker size reflects quantity
sizes = 4 * tq

# -----------------------
# PLOT
# -----------------------
plt.figure(figsize=(12, 7))

plt.plot(x, y1, linewidth=0.8, color='green', label='ask', alpha=0.2)
plt.plot(x, y2, linewidth=0.8, color='red', label='bid', alpha=0.2)
# plt.plot(x, y3, linewidth=1.0, color='blue', label='mid', alpha=0.7)
plt.plot(x, y4, linewidth=1.0, color='orange', label='ema')

plt.scatter(tx, tp, s=sizes, color='black', alpha=0.7, marker='x', label='trades')

plt.title(product)
plt.xlabel('row index')
plt.ylabel('price')
plt.ticklabel_format(useOffset=False, axis='y')
plt.legend()
plt.tight_layout()
plt.show()