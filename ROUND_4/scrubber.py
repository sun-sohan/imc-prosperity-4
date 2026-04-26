"""
Trader Scrubber
───────────────
- Scroll wheel  : zoom in/out (centered on cursor)
- Click + drag  : pan left/right
- Hover         : shows trader name, qty, price

Change PRODUCT at the top to switch instruments.
"""

import pandas as pd
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import CheckButtons

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

# Pre-extract arrays per trader
buyer_data  = {}
seller_data = {}
for trader in all_traders:
    tb = t[t['buyer']  == trader]
    ts = t[t['seller'] == trader]
    if not tb.empty:
        buyer_data[trader]  = (tb['x'].values, tb['price'].values, tb['quantity'].abs().values)
    if not ts.empty:
        seller_data[trader] = (ts['x'].values, ts['price'].values, ts['quantity'].abs().values)
buyer_data_all  = dict(buyer_data)
seller_data_all = dict(seller_data)

# ─────────────────────────────────────────────
#  Figure — white theme
# ─────────────────────────────────────────────

plt.rcParams['toolbar'] = 'None'
plt.rcParams.update({
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
})

fig, (ax_buy, ax_sell) = plt.subplots(
    2, 1, figsize=(17, 9), sharex=True, facecolor='white'
)
fig.canvas.manager.set_window_title(f'{PRODUCT} — Trader Scrubber')
plt.subplots_adjust(left=0.06, right=0.98, top=0.93, bottom=0.07, hspace=0.22)

for ax, title in [
    (ax_buy,  f'BUYERS  —  {PRODUCT}'),
    (ax_sell,  'SELLERS'),
]:
    ax.set_facecolor('#f7f7f7')
    ax.tick_params(colors='#222222')
    ax.set_ylabel('price', fontsize=12, color='#222222', fontweight='bold')
    for spine in ax.spines.values():
        spine.set_edgecolor('#aaaaaa')
        spine.set_linewidth(1.2)
    ax.set_title(title, color='#111111', fontsize=13,
                 fontfamily='monospace', fontweight='bold', loc='left', pad=6)
    ax.grid(True, color='#dddddd', lw=0.7, zorder=0)

ax_sell.set_xlabel('row index', fontsize=12, color='#222222', fontweight='bold')

x_all = p['x'].values
y_mid = p['mid_price'].values
y_ask = p['ask_price_1'].values
y_bid = p['bid_price_1'].values

for ax in [ax_buy, ax_sell]:
    ax.plot(x_all, y_ask, lw=1.2, color='#27ae60', alpha=0.6,  label='ask')
    ax.plot(x_all, y_bid, lw=1.2, color='#e74c3c', alpha=0.6,  label='bid')
    ax.plot(x_all, y_mid, lw=2.0, color='#222222', alpha=0.9,  label='mid')
    for bx in day_boundaries:
        ax.axvline(bx, color='#7f8c8d', lw=1.5, ls='--', alpha=0.7)

N = len(p)

# Trade scatters
buy_scatters  = {}
sell_scatters = {}

for trader in all_traders:
    c = color_map[trader]

    if trader in buyer_data:
        xs, ys, qs = buyer_data[trader]
        sz = np.clip(qs * 5, 25, 180)
        sc = ax_buy.scatter(xs, ys, s=sz, c=[c], marker='X',
                            linewidths=1.2, alpha=0.9, zorder=5, label=trader)
        buy_scatters[trader] = sc

    if trader in seller_data:
        xs, ys, qs = seller_data[trader]
        sz = np.clip(qs * 5, 25, 180)
        sc = ax_sell.scatter(xs, ys, s=sz, c=[c], marker='X',
                             linewidths=1.2, alpha=0.9, zorder=5, label=trader)
        sell_scatters[trader] = sc

# Remove the existing legend block for both axes and replace with:

# ── Checkbox panel ────────────────────────────
check_ax = fig.add_axes([0.82, 0.07, 0.16, 0.86], facecolor='#f0f0f0')
check_ax.set_title('traders', fontsize=10, fontfamily='monospace',
                   fontweight='bold', color='#111111', pad=4)

labels  = all_traders
actives = [True] * len(labels)
cb = CheckButtons(check_ax, labels, actives)

for text in cb.labels:
    text.set_fontsize(30)
    text.set_fontfamily('monospace')
    text.set_color(color_map[text.get_text()])
    text.set_fontweight('bold')

# Resize figure to make room
plt.subplots_adjust(left=0.06, right=0.80, top=0.93, bottom=0.07, hspace=0.22)

def on_checkbox(label):
    visible = cb.get_status()[labels.index(label)]
    if label in buy_scatters:
        buy_scatters[label].set_visible(visible)
    if label in sell_scatters:
        sell_scatters[label].set_visible(visible)

    # toggle hover hit-testing too
    if visible:
        if label in buyer_data_all:
            buyer_data[label] = buyer_data_all[label]
        if label in seller_data_all:
            seller_data[label] = seller_data_all[label]
    else:
        buyer_data.pop(label, None)
        seller_data.pop(label, None)

    fig.canvas.draw_idle()

cb.on_clicked(on_checkbox)

ax_buy.set_xlim(0, min(3000, N))

# ── Annotation ────────────────────────────────
_ann_kw = dict(
    xy=(0, 0), xytext=(12, 12), textcoords='offset points',
    bbox=dict(boxstyle='round,pad=0.5', fc='white', ec='#2980b9', lw=2),
    color='#111111', fontsize=10, fontfamily='monospace',
    fontweight='bold', visible=False, zorder=20,
)
annot_buy  = ax_buy.annotate('', **_ann_kw)
annot_sell = ax_sell.annotate('', **_ann_kw)

# ─────────────────────────────────────────────
#  Interaction
# ─────────────────────────────────────────────

state = {
    'drag_start_x': None,
    'drag_xlim':    None,
    'dragging':     False,
}

HIT_PX = 12


def _hit_test(event, ax, data_dict):
    """Return (trader, x, y, qty) for nearest point within HIT_PX pixels."""
    if event.xdata is None or event.ydata is None:
        return None
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    win  = ax.get_window_extent()
    if win.width == 0 or win.height == 0:
        return None
    x_scale = win.width  / (xlim[1] - xlim[0])
    y_scale = win.height / (ylim[1] - ylim[0])

    best_dist = HIT_PX + 1
    best      = None
    for trader, (xs, ys, qs) in data_dict.items():
        mask = (xs >= xlim[0] - 1) & (xs <= xlim[1] + 1)
        if not mask.any():
            continue
        dx    = (xs[mask] - event.xdata) * x_scale
        dy    = (ys[mask] - event.ydata) * y_scale
        dists = np.hypot(dx, dy)
        i     = dists.argmin()
        if dists[i] < best_dist:
            best_dist = dists[i]
            oi   = np.where(mask)[0][i]
            best = (trader, xs[oi], ys[oi], int(qs[oi]))
    return best


state = {
    'drag_start_px': None,
    'drag_xlim':     None,
    'dragging':      False,
}


def on_scroll(event):
    if event.inaxes not in (ax_buy, ax_sell):
        return
    xlim     = ax_buy.get_xlim()
    span     = xlim[1] - xlim[0]
    factor   = 0.72 if event.button == 'up' else 1.38
    new_span = max(200, min(N, span * factor))
    inv      = ax_buy.transData.inverted()
    cx       = inv.transform((event.x, event.y))[0]
    cx       = np.clip(cx, xlim[0], xlim[1])
    ratio    = (cx - xlim[0]) / span
    lo       = cx - ratio * new_span
    lo       = max(0, min(N - new_span, lo))
    ax_buy.set_xlim(lo, lo + new_span)
    fig.canvas.draw_idle()



def on_press(event):
    if event.inaxes not in (ax_buy, ax_sell) or event.button != 1:
        return
    state['drag_start_px'] = event.x
    state['drag_xlim']     = ax_buy.get_xlim()
    state['dragging']      = False


def on_release(event):
    if event.button == 1:
        state['drag_start_px'] = None
        state['drag_xlim']     = None
        state['dragging']      = False


def on_motion(event):
    # ── Pan ───────────────────────────────────
    if state['drag_start_px'] is not None:
        state['dragging'] = True
        lo0, hi0 = state['drag_xlim']
        span     = hi0 - lo0
        win      = ax_buy.get_window_extent()
        dx_data  = (event.x - state['drag_start_px']) * span / win.width
        lo       = np.clip(lo0 - dx_data, 0, N - span)
        ax_buy.set_xlim(lo, lo + span)
        annot_buy.set_visible(False)
        annot_sell.set_visible(False)
        fig.canvas.draw_idle()
        return

    # ── Hover ─────────────────────────────────
    if event.inaxes not in (ax_buy, ax_sell) or event.xdata is None:
        if annot_buy.get_visible() or annot_sell.get_visible():
            annot_buy.set_visible(False)
            annot_sell.set_visible(False)
            fig.canvas.draw_idle()
        return

    changed = False

    if event.inaxes == ax_buy:
        hit = _hit_test(event, ax_buy, buyer_data)
        if hit:
            trader, hx, hy, qty = hit
            annot_buy.set_text(f'{trader}\nqty={qty}   px={hy:.1f}')
            annot_buy.xy = (hx, hy)
            annot_buy.set_visible(True)
            changed = True
            row = t[(t['buyer'] == trader) & (t['x'] == hx)]
            if not row.empty:
                row = row.iloc[0]
                seller = row['seller']
                annot_sell.set_text(f'{seller}\nqty={int(abs(row["quantity"]))}   px={row["price"]:.1f}')
                annot_sell.xy = (hx, row['price'])
                annot_sell.set_visible(True)
                changed = True
            else:
                if annot_sell.get_visible():
                    annot_sell.set_visible(False)
                    changed = True
        else:
            if annot_buy.get_visible():
                annot_buy.set_visible(False)
                changed = True
            if annot_sell.get_visible():
                annot_sell.set_visible(False)
                changed = True

    elif event.inaxes == ax_sell:
        hit = _hit_test(event, ax_sell, seller_data)
        if hit:
            trader, hx, hy, qty = hit
            annot_sell.set_text(f'{trader}\nqty={qty}   px={hy:.1f}')
            annot_sell.xy = (hx, hy)
            annot_sell.set_visible(True)
            changed = True
            row = t[(t['seller'] == trader) & (t['x'] == hx)]
            if not row.empty:
                row = row.iloc[0]
                buyer = row['buyer']
                annot_buy.set_text(f'{buyer}\nqty={int(abs(row["quantity"]))}   px={row["price"]:.1f}')
                annot_buy.xy = (hx, row['price'])
                annot_buy.set_visible(True)
                changed = True
            else:
                if annot_buy.get_visible():
                    annot_buy.set_visible(False)
                    changed = True
        else:
            if annot_sell.get_visible():
                annot_sell.set_visible(False)
                changed = True
            if annot_buy.get_visible():
                annot_buy.set_visible(False)
                changed = True

    if changed:
        fig.canvas.draw_idle()

fig.canvas.mpl_connect('scroll_event',         on_scroll)
fig.canvas.mpl_connect('button_press_event',   on_press)
fig.canvas.mpl_connect('button_release_event', on_release)
fig.canvas.mpl_connect('motion_notify_event',  on_motion)

plt.show()