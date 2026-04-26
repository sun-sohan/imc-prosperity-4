"""
Trader Scrubber
───────────────
- Scroll wheel  : zoom in/out (centered on cursor)
- Click + drag  : pan left/right
- Hover         : shows trader name, qty, price
- Two panels    : BUYERS (top) / SELLERS (bottom)

Change PRODUCT at the top to switch instruments.
"""

import pandas as pd
import matplotlib
matplotlib.use('TkAgg')          # TkAgg redraws much faster than Qt for this use case
import matplotlib.pyplot as plt
import numpy as np

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────

PRODUCT  = 'VELVETFRUIT_EXTRACT'
DAYS     = [1, 2, 3]
DATA_DIR = 'ROUND_4'

# ─────────────────────────────────────────────
#  Load + stitch
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

p = prices[prices['product'] == PRODUCT].copy()
p = p.sort_values(['day', 'timestamp']).reset_index(drop=True)
p['x'] = np.arange(len(p))

t = trades[trades['symbol'] == PRODUCT].copy()
t = t.sort_values(['day', 'timestamp']).reset_index(drop=True)

ts_to_x = {(row.day, row.timestamp): row.x for row in p.itertuples()}
t['x'] = [ts_to_x.get((row.day, row.timestamp), np.nan) for row in t.itertuples()]
t = t.dropna(subset=['x'])
t['x'] = t['x'].astype(int)

day_boundaries = []
for day in DAYS[1:]:
    fx = p[p['day'] == day]['x'].min()
    if pd.notna(fx):
        day_boundaries.append(int(fx))

all_traders = sorted(set(t['buyer'].dropna()) | set(t['seller'].dropna()))
cmap        = plt.cm.get_cmap('tab10', max(len(all_traders), 1))
color_map   = {trader: cmap(i) for i, trader in enumerate(all_traders)}

print(f"Product : {PRODUCT}")
print(f"Traders : {all_traders}")
print(f"Price rows: {len(p)}  |  Trade rows: {len(t)}")

# Pre-extract numpy arrays per trader for fast hit-testing
buyer_data  = {}   # trader -> (xs, ys, qtys)
seller_data = {}

for trader in all_traders:
    tb = t[t['buyer']  == trader]
    ts = t[t['seller'] == trader]
    if not tb.empty:
        buyer_data[trader]  = (tb['x'].values, tb['price'].values, tb['quantity'].abs().values)
    if not ts.empty:
        seller_data[trader] = (ts['x'].values, ts['price'].values, ts['quantity'].abs().values)

# ─────────────────────────────────────────────
#  Figure
# ─────────────────────────────────────────────

plt.rcParams['toolbar'] = 'None'   # disable default toolbar — kills lag

fig, (ax_buy, ax_sell) = plt.subplots(
    2, 1, figsize=(16, 8), sharex=True, facecolor='#0f0f0f'
)
fig.canvas.manager.set_window_title(f'{PRODUCT} — Trader Scrubber')
plt.subplots_adjust(left=0.05, right=0.98, top=0.93, bottom=0.06, hspace=0.12)

BG   = '#0f0f0f'
MID  = '#cccccc'
ASK  = '#2a6a2a'
BID  = '#6a2a2a'
GRID = '#1e1e1e'

for ax, title in [(ax_buy, 'BUYERS'), (ax_sell, 'SELLERS')]:
    ax.set_facecolor(BG)
    ax.tick_params(colors='#666666', labelsize=7)
    ax.yaxis.label.set_color('#666666')
    ax.set_ylabel('price', fontsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor('#222222')
    ax.set_title(title, color='#aaaaaa', fontsize=9,
                 fontfamily='monospace', loc='left', pad=4)

ax_sell.set_xlabel('row index', color='#666666', fontsize=8)
ax_buy.set_title(f'BUYERS  —  {PRODUCT}', color='#aaaaaa',
                 fontsize=9, fontfamily='monospace', loc='left', pad=4)

x_all = p['x'].values
y_mid = p['mid_price'].values
y_ask = p['ask_price_1'].values
y_bid = p['bid_price_1'].values

# ── Static price lines ────────────────────────
for ax in [ax_buy, ax_sell]:
    ax.plot(x_all, y_ask, lw=0.4, color=ASK,  alpha=0.45)
    ax.plot(x_all, y_bid, lw=0.4, color=BID,  alpha=0.45)
    ax.plot(x_all, y_mid, lw=0.7, color=MID,  alpha=0.85)
    for bx in day_boundaries:
        ax.axvline(bx, color='#334455', lw=0.8, ls='--', alpha=0.5)

# ── Trade scatter per trader ──────────────────
buy_scatters  = {}   # trader -> PathCollection
sell_scatters = {}

for trader in all_traders:
    c = color_map[trader]

    if trader in buyer_data:
        xs, ys, qs = buyer_data[trader]
        sz = np.clip(qs * 4, 10, 140)
        sc = ax_buy.scatter(xs, ys, s=sz, c=[c], marker='x',
                            linewidths=0.9, alpha=0.85, zorder=5, label=trader)
        buy_scatters[trader] = sc

    if trader in seller_data:
        xs, ys, qs = seller_data[trader]
        sz = np.clip(qs * 4, 10, 140)
        sc = ax_sell.scatter(xs, ys, s=sz, c=[c], marker='x',
                             linewidths=0.9, alpha=0.85, zorder=5, label=trader)
        sell_scatters[trader] = sc

for ax in [ax_buy, ax_sell]:
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7, facecolor='#111', edgecolor='#333',
                  labelcolor='white', loc='upper left', markerscale=1.1)

# Set initial view
N = len(p)
ax_buy.set_xlim(0, min(3000, N))

# ── Annotation (single, reused) ───────────────
_ann_kw = dict(
    xy=(0, 0), xytext=(10, 10), textcoords='offset points',
    bbox=dict(boxstyle='round,pad=0.35', fc='#111122', ec='#3a3a7a', lw=1),
    color='#dddddd', fontsize=8, fontfamily='monospace',
    visible=False, zorder=20, animated=True
)
annot_buy  = ax_buy.annotate('', **_ann_kw)
annot_sell = ax_sell.annotate('', **_ann_kw)

# ─────────────────────────────────────────────
#  Interaction state
# ─────────────────────────────────────────────

state = {
    'drag_start_x'  : None,   # x data coord where drag began
    'drag_xlim'     : None,   # xlim at drag start
    'last_ann_pos'  : None,   # (x, y) of last annotation to avoid redundant redraws
}

HIT_RADIUS_PX = 8   # pixels for hover hit-test


def _hit_test(event, ax, data_dict):
    """Return (trader, x, y, qty) for nearest marker within HIT_RADIUS_PX, else None."""
    if not data_dict:
        return None
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    ax_w = ax.get_window_extent().width
    ax_h = ax.get_window_extent().height
    x_scale = ax_w / (xlim[1] - xlim[0]) if xlim[1] != xlim[0] else 1
    y_scale = ax_h / (ylim[1] - ylim[0]) if ylim[1] != ylim[0] else 1

    best_dist = HIT_RADIUS_PX + 1
    best      = None
    for trader, (xs, ys, qs) in data_dict.items():
        # Only check points in current x view (fast)
        mask = (xs >= xlim[0]) & (xs <= xlim[1])
        if not mask.any():
            continue
        dx = (xs[mask] - event.xdata) * x_scale
        dy = (ys[mask] - event.ydata) * y_scale
        dists = np.hypot(dx, dy)
        idx   = dists.argmin()
        if dists[idx] < best_dist:
            best_dist = dists[idx]
            # Map back to original index
            orig_idx  = np.where(mask)[0][idx]
            best = (trader, xs[orig_idx], ys[orig_idx], int(qs[orig_idx]))
    return best


def on_scroll(event):
    if event.inaxes not in (ax_buy, ax_sell):
        return
    xlim = ax_buy.get_xlim()
    span = xlim[1] - xlim[0]
    # Zoom toward cursor x
    cx   = event.xdata if event.xdata is not None else (xlim[0] + xlim[1]) / 2
    factor = 0.75 if event.button == 'up' else 1.33
    new_span = max(200, min(N, span * factor))
    lo = cx - (cx - xlim[0]) * (new_span / span)
    lo = max(0, min(N - new_span, lo))
    ax_buy.set_xlim(lo, lo + new_span)
    fig.canvas.draw_idle()


def on_press(event):
    if event.inaxes not in (ax_buy, ax_sell):
        return
    if event.button == 1:
        state['drag_start_x'] = event.xdata
        state['drag_xlim']    = ax_buy.get_xlim()


def on_release(event):
    if event.button == 1:
        state['drag_start_x'] = None
        state['drag_xlim']    = None


def on_motion(event):
    # ── Drag pan ──────────────────────────────
    if state['drag_start_x'] is not None and event.xdata is not None:
        dx   = event.xdata - state['drag_start_x']
        lo0, hi0 = state['drag_xlim']
        span = hi0 - lo0
        lo   = np.clip(lo0 - dx, 0, N - span)
        ax_buy.set_xlim(lo, lo + span)
        fig.canvas.draw_idle()
        return   # skip hover during drag

    # ── Hover hit-test ────────────────────────
    if event.inaxes not in (ax_buy, ax_sell) or event.xdata is None:
        if annot_buy.get_visible() or annot_sell.get_visible():
            annot_buy.set_visible(False)
            annot_sell.set_visible(False)
            fig.canvas.draw_idle()
        return

    if event.inaxes == ax_buy:
        hit = _hit_test(event, ax_buy, buyer_data)
        ann, other = annot_buy, annot_sell
    else:
        hit = _hit_test(event, ax_sell, seller_data)
        ann, other = annot_sell, annot_buy

    if hit:
        trader, hx, hy, qty = hit
        new_pos = (hx, hy)
        if state['last_ann_pos'] == new_pos:
            return   # nothing changed, skip redraw
        state['last_ann_pos'] = new_pos
        ann.set_text(f'{trader}\nqty={qty}  px={hy:.1f}')
        ann.xy = (hx, hy)
        ann.set_visible(True)
        other.set_visible(False)
    else:
        if not ann.get_visible() and not other.get_visible():
            return
        state['last_ann_pos'] = None
        ann.set_visible(False)
        other.set_visible(False)

    fig.canvas.draw_idle()


fig.canvas.mpl_connect('scroll_event',          on_scroll)
fig.canvas.mpl_connect('button_press_event',    on_press)
fig.canvas.mpl_connect('button_release_event',  on_release)
fig.canvas.mpl_connect('motion_notify_event',   on_motion)

plt.show()