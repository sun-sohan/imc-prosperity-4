import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

cutoff = 10000000000000000
days = [1, 2, 3]
products = ['HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT']

def show_plot():

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    for product in products:
        for day in days:
            df = pd.read_csv(f'ROUND_4/prices_round_4_day_{day}.csv', sep=';')
            df = df[df['product'] == product].copy()

    for ax, product in zip(axes, products):
        x_offset = 0

        for day in days:
            # -----------------------
            df = pd.read_csv(f'ROUND_4/prices_round_4_day_{day}.csv', sep=';')
            df = df[df['product'] == product].copy()
            df = df.sort_values('timestamp').reset_index(drop=True)
            df = df.iloc[:cutoff].copy()

            x = np.arange(len(df)) + x_offset
            y1 = df['ask_price_1']
            y2 = df['bid_price_1']
            y3 = df['mid_price']

            trades = pd.read_csv(f'ROUND_4/trades_round_4_day_{day}.csv', sep=';')
            trades = trades[trades['symbol'] == product].copy()
            trades = trades.sort_values('timestamp').reset_index(drop=True)
            trades = trades.iloc[:cutoff].copy()

            timestamp_to_x = {ts: i + x_offset for i, ts in enumerate(df['timestamp'])}
            trades = trades[trades['timestamp'].isin(timestamp_to_x)].copy()
            trades['x'] = trades['timestamp'].map(timestamp_to_x)

            tx = trades['x']
            tp = trades['price']
            tq = trades['quantity'].abs()
            sizes = 4 * tq

            # -----------------------
            # PLOT
            # -----------------------
            label_suffix = f' (d{day})'
            ax.plot(x, y1, linewidth=0.8, color='green', alpha=0.2,
                    label='ask' + label_suffix if day == days[0] else '_nolegend_')
            ax.plot(x, y2, linewidth=0.8, color='red', alpha=0.2,
                    label='bid' + label_suffix if day == days[0] else '_nolegend_')
            # ax.plot(x, y4, linewidth=1.0, color='orange',
            #         label='ema' + label_suffix if day == days[0] else '_nolegend_')
            ax.scatter(tx, tp, s=sizes, color='black', alpha=0.7, marker='x',
                    label='trades' + label_suffix if day == days[0] else '_nolegend_')

            # vertical day separator
            if day != days[0]:
                ax.axvline(x=x_offset, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)

            x_offset += len(df)

        ax.set_title(product)
        ax.set_xlabel('row index')
        ax.set_ylabel('price')
        ax.ticklabel_format(useOffset=False, axis='y')
        ax.legend()

    plt.tight_layout()
    plt.show()


show_plot()


