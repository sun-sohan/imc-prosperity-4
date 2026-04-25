import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

cutoff = 10000000000000000
days = [0, 1, 2]
products = ['HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT']

def show_plot():

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    for product in products:
        spreads = []
        for day in days:
            df = pd.read_csv(f'ROUND_3/prices_round_3_day_{day}.csv', sep=';')
            df = df[df['product'] == product].copy()
            spreads.append(df['ask_price_1'] - df['bid_price_1'])
        avg_spread = pd.concat(spreads).mean()
        print(f"{product}  avg spread: {avg_spread:.3f}")

    for ax, product in zip(axes, products):
        x_offset = 0

        for day in days:
            # -----------------------
            # PRICE DATA
            # -----------------------
            df = pd.read_csv(f'ROUND_3/prices_round_3_day_{day}.csv', sep=';')
            df = df[df['product'] == product].copy()
            df = df.sort_values('timestamp').reset_index(drop=True)
            df = df.iloc[:cutoff].copy()

            x = np.arange(len(df)) + x_offset
            y1 = df['ask_price_1']
            y2 = df['bid_price_1']
            y3 = df['mid_price']
            # y4 = y3.ewm(span=10000, adjust=False).mean()

            # -----------------------
            # TRADE DATA
            # -----------------------
            trades = pd.read_csv(f'ROUND_3/trades_round_3_day_{day}.csv', sep=';')
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

def show_corr():
    # ── load all days ─────────────────────────────────────────────
    dfs = []
    for day in [0, 1, 2]:
        df = pd.read_csv(f'ROUND_3/prices_round_3_day_{day}.csv', sep=';')
        dfs.append(df)
    df_all = pd.concat(dfs).reset_index(drop=True)

    # ── extract mid prices, deduplicate timestamps ────────────────
    hydro  = df_all[df_all['product'] == 'HYDROGEL_PACK'][['timestamp', 'mid_price']] \
                .groupby('timestamp')['mid_price'].mean().rename('hydro')
    velvet = df_all[df_all['product'] == 'VELVETFRUIT_EXTRACT'][['timestamp', 'mid_price']] \
                .groupby('timestamp')['mid_price'].mean().rename('velvet')

    merged = pd.merge(hydro, velvet, on='timestamp').sort_values('timestamp').reset_index(drop=True)

    print(f"hydro rows:  {len(hydro)}")
    print(f"velvet rows: {len(velvet)}")
    print(f"merged rows: {len(merged)}")

    # ── returns ───────────────────────────────────────────────────
    merged['hydro_ret']  = merged['hydro'].diff()
    merged['velvet_ret'] = merged['velvet'].diff()

    corr = merged['hydro_ret'].corr(merged['velvet_ret'])
    print(f"Return correlation: {corr:.4f}")

    # ── rolling correlation ───────────────────────────────────────
    window = 500
    merged['rolling_corr'] = merged['hydro_ret'].rolling(window).corr(merged['velvet_ret'])

    # ── plot ──────────────────────────────────────────────────────
    fig, axes = plt.subplots(3, 1, figsize=(12, 14))

    # -- price levels --
    ax = axes[0]
    ax.plot(merged['hydro'],   linewidth=0.8, color='steelblue', label='HYDROGEL_PACK')
    ax2 = ax.twinx()
    ax2.plot(merged['velvet'], linewidth=0.8, color='darkorange', alpha=0.7, label='VELVETFRUIT_EXTRACT')
    ax.set_title('Mid-price levels (dual axis)')
    ax.set_ylabel('HYDROGEL_PACK', color='steelblue')
    ax2.set_ylabel('VELVETFRUIT_EXTRACT', color='darkorange')
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')

    # -- returns scatter --
    ax = axes[1]
    ax.scatter(merged['hydro_ret'], merged['velvet_ret'], s=1, alpha=0.3, color='gray')
    ax.set_title(f'Return scatter  (corr = {corr:.4f})')
    ax.set_xlabel('HYDROGEL_PACK return')
    ax.set_ylabel('VELVETFRUIT_EXTRACT return')
    ax.axhline(0, color='black', linewidth=0.5)
    ax.axvline(0, color='black', linewidth=0.5)

    # -- rolling correlation --
    ax = axes[2]
    ax.plot(merged['rolling_corr'], linewidth=0.8, color='steelblue')
    ax.axhline(corr,  color='orange', linestyle='--', linewidth=1.0, label=f'overall: {corr:.3f}')
    ax.axhline(0,     color='gray',   linestyle='--', linewidth=0.6, alpha=0.5)
    ax.set_title(f'Rolling {window}-tick return correlation')
    ax.set_xlabel('row index')
    ax.set_ylabel('correlation')
    ax.legend()

    plt.tight_layout()
    # plt.show()

    from statsmodels.tsa.stattools import adfuller

    # def variance_ratio(series, lag=10):
    #     """VR > 1 → trending, VR < 1 → mean-reverting, VR = 1 → random walk"""
    #     series = np.array(series)
    #     r1  = np.diff(series)
    #     rl  = series[lag:] - series[:-lag]
    #     var1 = np.var(r1, ddof=1)
    #     varl = np.var(rl, ddof=1)
    #     return (varl / lag) / var1

    # for lag in [5, 10, 50, 100]:
    #     vr_h = variance_ratio(merged['hydro'],  lag)
    #     vr_v = variance_ratio(merged['velvet'], lag)
    #     print(f"lag={lag:>3}  HYDROGEL: {vr_h:.3f}   VELVETFRUIT: {vr_v:.3f}")

    for name in ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"]:
        df_p = df_all[df_all['product'] == name].copy()
        
        ask_cols = sorted([c for c in df_p.columns if c.startswith('ask_price_')])
        bid_cols = sorted([c for c in df_p.columns if c.startswith('bid_price_')])
        
        print(f"\n{name}")
        print(f"  ask levels available: {ask_cols}")
        print(f"  typical spread (best ask - best bid): {(df_p['ask_price_1'] - df_p['bid_price_1']).mean():.3f}")
        print(f"  worst ask - best ask: {(df_p[ask_cols].max(axis=1) - df_p['ask_price_1']).mean():.3f}")
        print(f"  best bid - worst bid: {(df_p['bid_price_1'] - df_p[bid_cols].min(axis=1)).mean():.3f}")

show_plot()

show_corr()

