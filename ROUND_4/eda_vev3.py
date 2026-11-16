"""
Trader Forward PnL Analysis
────────────────────────────
For each trader, simulates: at each trade, buy/sell at trade price,
mark to mid_price N ticks later. Aggregates expected PnL per trade
across horizons to identify informed vs noise traders.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────

# `HYDROGEL_PACK`  `VELVETFRUIT_EXTRACT`
# `VEV_4000`, `VEV_4500`, `VEV_5000`, `VEV_5100`, `VEV_5200`, `VEV_5300`, `VEV_5400`, `VEV_5500`, `VEV_6000`, `VEV_6500`

PRODUCTS  = ['VELVETFRUIT_EXTRACT']
DAYS      = [1, 2, 3]
DATA_DIR  = 'ROUND_4'
HORIZONS  = [50, 100, 200, 500, 1000]   # ticks forward

# ─────────────────────────────────────────────
#  Load
# ─────────────────────────────────────────────

price_frames, trade_frames = [], []
for day in DAYS:
    pf = pd.read_csv(f'{DATA_DIR}/prices_round_4_day_{day}.csv', sep=';')
    pf['day'] = day
    price_frames.append(pf)
    tf = pd.read_csv(f'{DATA_DIR}/trades_round_4_day_{day}.csv', sep=';')
    tf['day'] = day
    trade_frames.append(tf)

prices = pd.concat(price_frames, ignore_index=True)
trades = pd.concat(trade_frames, ignore_index=True)

hydro = prices[prices['product'] == 'HYDROGEL_PACK']['mid_price']
print(f"HYDROGEL_PACK global avg mid_price: {hydro.mean():.4f}")

# ─────────────────────────────────────────────
#  Analysis per product
# ─────────────────────────────────────────────

for product in PRODUCTS:
    print(f"\n{'='*60}")
    print(f"  {product}")
    print(f"{'='*60}")

    p = prices[prices['product'] == product].copy()
    p = p.sort_values(['day', 'timestamp']).reset_index(drop=True)
    p['x'] = np.arange(len(p))
    mid_arr = p['mid_price'].values   # indexed by x

    t = trades[trades['symbol'] == product].copy()
    t = t.sort_values(['day', 'timestamp']).reset_index(drop=True)

    ts_to_x = {(row.day, row.timestamp): row.x for row in p.itertuples()}
    t['x'] = [ts_to_x.get((row.day, row.timestamp), np.nan) for row in t.itertuples()]
    t = t.dropna(subset=['x'])
    t['x'] = t['x'].astype(int)

    N = len(mid_arr)
    all_traders = sorted(set(t['buyer'].dropna()) | set(t['seller'].dropna()))
    cmap = plt.cm.get_cmap('tab10', max(len(all_traders), 1))
    color_map = {trader: cmap(i) for i, trader in enumerate(all_traders)}

    # ── Compute forward PnL ───────────────────
    # For each trade row:
    #   buyer  PnL at horizon h = mid[x+h] - trade_price   (bought, want price to rise)
    #   seller PnL at horizon h = trade_price - mid[x+h]   (sold,   want price to fall)

    records = []
    for row in t.itertuples():
        x      = row.x
        price  = row.price
        qty    = abs(row.quantity)
        buyer  = row.buyer
        seller = row.seller

        for h in HORIZONS:
            x_fwd = x + h
            if x_fwd >= N:
                continue
            mid_fwd = mid_arr[x_fwd]

            if pd.notna(buyer):
                records.append({
                    'trader':    buyer,
                    'role':      'buyer',
                    'horizon':   h,
                    'pnl_per_unit': mid_fwd - price,
                    'pnl_total':   (mid_fwd - price) * qty,
                    'qty':         qty,
                    'x':           x,
                })
            if pd.notna(seller):
                records.append({
                    'trader':    seller,
                    'role':      'seller',
                    'horizon':   h,
                    'pnl_per_unit': price - mid_fwd,
                    'pnl_total':   (price - mid_fwd) * qty,
                    'qty':         qty,
                    'x':           x,
                })

    df = pd.DataFrame(records)
    if df.empty:
        print("  No trades found.")
        continue

    # ── Print summary table ───────────────────
    print(f"\n{'trader':<12} {'role':<8} {'horizon':>8} {'mean_pnl/unit':>14} {'total_pnl':>12} {'n_trades':>9}")
    print("-" * 65)
    for trader in all_traders:
        for role in ['buyer', 'seller']:
            sub = df[(df['trader'] == trader) & (df['role'] == role)]
            if sub.empty:
                continue
            for h in HORIZONS:
                s = sub[sub['horizon'] == h]
                if s.empty:
                    continue
                print(f"{trader:<12} {role:<8} {h:>8}   "
                      f"{s['pnl_per_unit'].mean():>12.3f}   "
                      f"{s['pnl_total'].sum():>10.1f}   "
                      f"{len(s):>7}")

    # ── Plot 1: Mean PnL/unit vs horizon per trader ───────────────
    fig = plt.figure(figsize=(16, 10), facecolor='white')
    fig.suptitle(f'{product} — Forward PnL Analysis', fontsize=14,
                 fontweight='bold', fontfamily='monospace')

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35,
                           left=0.07, right=0.97, top=0.91, bottom=0.07)

    ax_buy_pnl  = fig.add_subplot(gs[0, 0])
    ax_sell_pnl = fig.add_subplot(gs[0, 1])
    ax_cum_buy  = fig.add_subplot(gs[1, 0])
    ax_cum_sell = fig.add_subplot(gs[1, 1])

    for ax, title in [
        (ax_buy_pnl,  'Mean PnL/unit vs Horizon  (BUYERS)'),
        (ax_sell_pnl, 'Mean PnL/unit vs Horizon  (SELLERS)'),
        (ax_cum_buy,  'Cumulative PnL over time  (BUYERS, h=200)'),
        (ax_cum_sell, 'Cumulative PnL over time  (SELLERS, h=200)'),
    ]:
        ax.set_facecolor('#f7f7f7')
        ax.set_title(title, fontsize=10, fontweight='bold',
                     fontfamily='monospace', color='#111111')
        ax.grid(True, color='#dddddd', lw=0.7)
        ax.axhline(0, color='#aaaaaa', lw=1.0, ls='--')
        ax.tick_params(labelsize=9)

    # Mean PnL/unit vs horizon
    for trader in all_traders:
        c = color_map[trader]
        for role, ax in [('buyer', ax_buy_pnl), ('seller', ax_sell_pnl)]:
            sub = df[(df['trader'] == trader) & (df['role'] == role)]
            if sub.empty:
                continue
            means = [sub[sub['horizon'] == h]['pnl_per_unit'].mean() for h in HORIZONS]
            ax.plot(HORIZONS, means, marker='o', lw=2.0, markersize=6,
                    color=c, label=trader)

    for ax in [ax_buy_pnl, ax_sell_pnl]:
        ax.set_xlabel('horizon (ticks)', fontsize=9)
        ax.set_ylabel('mean PnL per unit', fontsize=9)
        ax.legend(fontsize=8, facecolor='white', edgecolor='#aaaaaa')

    # Cumulative PnL over time at h=200
    H_CUM = 200
    for trader in all_traders:
        c = color_map[trader]
        for role, ax in [('buyer', ax_cum_buy), ('seller', ax_cum_sell)]:
            sub = df[(df['trader'] == trader) & (df['role'] == role) &
                     (df['horizon'] == H_CUM)].sort_values('x')
            if sub.empty:
                continue
            cumulative = sub['pnl_total'].cumsum().values
            ax.plot(sub['x'].values, cumulative, lw=2.0, color=c, label=trader)

    for ax in [ax_cum_buy, ax_cum_sell]:
        ax.set_xlabel('row index', fontsize=9)
        ax.set_ylabel(f'cumulative PnL (h={H_CUM})', fontsize=9)
        ax.legend(fontsize=8, facecolor='white', edgecolor='#aaaaaa')

    plt.show()







tvf = trades[trades['symbol'] == 'VELVETFRUIT_EXTRACT']
print(f"Total trades: {len(tvf)}")
print(tvf.groupby(['buyer', 'seller']).size().sort_values(ascending=False).head(10))