import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

DAY = 3
DATA_DIR = 'ROUND_4'
PRODUCTS = [
    'HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT'
]

n = len(PRODUCTS)
fig, axes = plt.subplots(n, 1, figsize=(14, 3 * n))

prices = pd.read_csv(f'{DATA_DIR}/prices_round_4_day_{DAY}.csv', sep=';')
trades = pd.read_csv(f'{DATA_DIR}/trades_round_4_day_{DAY}.csv', sep=';')

for ax, product in zip(axes, PRODUCTS):
    df = prices[prices['product'] == product].copy()
    df = df.sort_values('timestamp').reset_index(drop=True)

    x = np.arange(len(df))

    tr = trades[trades['symbol'] == product].copy()
    tr = tr.sort_values('timestamp').reset_index(drop=True)
    ts_to_x = {ts: i for i, ts in enumerate(df['timestamp'])}
    tr = tr[tr['timestamp'].isin(ts_to_x)].copy()
    tr['x'] = tr['timestamp'].map(ts_to_x)

    ax.plot(x, df['ask_price_1'], linewidth=0.8, color='green', alpha=0.2, label='ask')
    ax.plot(x, df['bid_price_1'], linewidth=0.8, color='red',   alpha=0.2, label='bid')
    ax.plot(x, df['mid_price'],   linewidth=1.0, color='blue',  alpha=0.6, label='mid')
    ax.scatter(tr['x'], tr['price'], s=4 * tr['quantity'].abs(),
               color='black', alpha=0.7, marker='x', label='trades')

    ax.set_title(product)
    ax.set_xlabel('row index')
    ax.set_ylabel('price')
    ax.ticklabel_format(useOffset=False, axis='y')
    ax.legend()

plt.suptitle(f'VEV Products — Day {DAY} Prices', fontsize=13, fontweight='bold', y=1.001)
plt.tight_layout()
plt.show()