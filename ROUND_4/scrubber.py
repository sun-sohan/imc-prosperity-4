"""
Trader Scrubber
───────────────
Interactive tool to identify anomalous/insider traders by scrubbing
through price action and filtering trades by buyer/seller.

Controls:
  - Product dropdown    : switch between products
  - Trader checkboxes   : toggle individual traders on/off
  - Window slider       : zoom into a rolling time window
  - Scrub slider        : pan through the full timeline
  - "All" / "None"      : bulk select traders
  - Color-coded markers : each unique trader gets a fixed color
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from matplotlib.widgets import Slider, Button, CheckButtons
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors

# ─────────────────────────────────────────────
#  Config — edit these
# ─────────────────────────────────────────────

DAYS     = [1, 2, 3]
PRODUCTS = ['HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT']
DATA_DIR = 'ROUND_4'

# Window size (number of price rows visible at once)
DEFAULT_WINDOW = 2000

# ─────────────────────────────────────────────
#  Load data
# ─────────────────────────────────────────────

def load_data():
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
    return prices, trades


def build_product_data(prices, trades, product):
    """
    Returns (price_df, trade_df) with a global 'x' index stitched across days,
    and a 'trader' column combining buyer/seller into individual identities.
    """
    p = prices[prices['product'] == product].copy()
    p = p.sort_values(['day', 'timestamp']).reset_index(drop=True)
    p['x'] = np.arange(len(p))

    # Build timestamp -> x map
    ts_to_x = {}
    for _, row in p.iterrows():
        ts_to_x[(row['day'], row['timestamp'])] = row['x']

    t = trades[trades['symbol'] == product].copy()
    t = t.sort_values(['day', 'timestamp']).reset_index(drop=True)
    t['x'] = t.apply(lambda r: ts_to_x.get((r['day'], r['timestamp']), np.nan), axis=1)
    t = t.dropna(subset=['x'])
    t['x'] = t['x'].astype(int)

    # Day boundary x positions
    day_boundaries = []
    for day in DAYS[1:]:
        first_x = p[p['day'] == day]['x'].min()
        if not np.isnan(first_x):
            day_boundaries.append(first_x)

    return p, t, day_boundaries


def get_all_traders(trade_df):
    buyers  = trade_df['buyer'].dropna().unique().tolist()
    sellers = trade_df['seller'].dropna().unique().tolist()
    return sorted(set(buyers + sellers))


def assign_colors(traders):
    base_colors = list(mcolors.TABLEAU_COLORS.values()) + list(mcolors.CSS4_COLORS.values())
    # Filter to reasonably visible colors
    visible = [c for c in base_colors if c not in ('#ffffff', '#f0f0f0', '#fffafa')]
    color_map = {}
    for i, trader in enumerate(traders):
        color_map[trader] = visible[i % len(visible)]
    return color_map


# ─────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────

class TraderScrubber:

    def __init__(self, prices, trades):
        self.prices       = prices
        self.trades       = trades
        self.product      = PRODUCTS[0]
        self.window       = DEFAULT_WINDOW
        self.pos          = 0                 # left edge of view

        self._load_product()

        # ── Layout ──────────────────────────────
        self.fig = plt.figure(figsize=(18, 9), facecolor='#0f0f0f')
        self.fig.canvas.manager.set_window_title('Trader Scrubber')

        gs = gridspec.GridSpec(
            3, 2,
            figure=self.fig,
            left=0.05, right=0.72,
            top=0.93, bottom=0.15,
            hspace=0.35,
            width_ratios=[1, 0.001],
        )
        gs_ctrl = gridspec.GridSpec(
            1, 1,
            figure=self.fig,
            left=0.75, right=0.98,
            top=0.93, bottom=0.15,
        )

        self.ax_price  = self.fig.add_subplot(gs[0, 0])
        self.ax_volume = self.fig.add_subplot(gs[1, 0], sharex=self.ax_price)
        self.ax_count  = self.fig.add_subplot(gs[2, 0], sharex=self.ax_price)
        self.ax_ctrl   = self.fig.add_subplot(gs_ctrl[0, 0])
        self.ax_ctrl.axis('off')

        for ax in [self.ax_price, self.ax_volume, self.ax_count]:
            ax.set_facecolor('#0f0f0f')
            ax.tick_params(colors='#888888', labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor('#333333')

        self.ax_price.set_title(
            f'{self.product}', color='#dddddd', fontsize=10,
            fontfamily='monospace', pad=6
        )
        self.ax_price.set_ylabel('price', color='#888888', fontsize=8)
        self.ax_volume.set_ylabel('qty', color='#888888', fontsize=8)
        self.ax_count.set_ylabel('trade count', color='#888888', fontsize=8)
        self.ax_count.set_xlabel('row index', color='#888888', fontsize=8)

        # ── Sliders ──────────────────────────────
        ax_scrub  = self.fig.add_axes([0.05, 0.06, 0.65, 0.025], facecolor='#1a1a1a')
        ax_window = self.fig.add_axes([0.05, 0.02, 0.65, 0.025], facecolor='#1a1a1a')

        n = len(self.price_df)
        self.slider_scrub = Slider(
            ax_scrub, 'Scrub', 0, max(n - 1, 1),
            valinit=0, color='#3a7bd5', valstep=1
        )
        self.slider_window = Slider(
            ax_window, 'Window', 100, max(n, 200),
            valinit=DEFAULT_WINDOW, color='#444444', valstep=50
        )
        for sl in [self.slider_scrub, self.slider_window]:
            sl.label.set_color('#aaaaaa')
            sl.valtext.set_color('#aaaaaa')

        self.slider_scrub.on_changed(self._on_scrub)
        self.slider_window.on_changed(self._on_window)

        # ── Product buttons ───────────────────────
        self._btn_axes = []
        self._prod_btns = []
        for i, prod in enumerate(PRODUCTS):
            bax = self.fig.add_axes([0.75 + i * 0.115, 0.95, 0.10, 0.03])
            btn = Button(bax, prod.replace('_', '\n'),
                         color='#1a1a1a', hovercolor='#2a3a5a')
            btn.label.set_color('#dddddd')
            btn.label.set_fontsize(6)
            btn.on_clicked(lambda e, p=prod: self._switch_product(p))
            self._btn_axes.append(bax)
            self._prod_btns.append(btn)

        # ── Trader checkboxes ─────────────────────
        self._build_checkboxes()

        self._draw()
        plt.show()

    # ── Data loading ─────────────────────────────

    def _load_product(self):
        self.price_df, self.trade_df, self.day_boundaries = \
            build_product_data(self.prices, self.trades, self.product)
        self.all_traders  = get_all_traders(self.trade_df)
        self.color_map    = assign_colors(self.all_traders)
        self.active       = {t: True for t in self.all_traders}

    # ── Checkbox panel ────────────────────────────

    def _build_checkboxes(self):
        if hasattr(self, '_cb_ax') and self._cb_ax is not None:
            self._cb_ax.remove()

        traders = self.all_traders
        n = len(traders)
        height = min(0.75, n * 0.028 + 0.06)
        self._cb_ax = self.fig.add_axes(
            [0.75, 0.93 - height, 0.22, height],
            facecolor='#111111'
        )

        labels     = traders
        actives    = [self.active.get(t, True) for t in traders]
        self._cb   = CheckButtons(self._cb_ax, labels, actives)

        for text in self._cb.labels:
            trader_name = text.get_text()
            text.set_color(self.color_map.get(trader_name, '#dddddd'))
            text.set_fontsize(7)
            text.set_fontfamily('monospace')

        # with this:
        try:
            for rect in self._cb.rectangles:
                rect.set_facecolor('#1a1a1a')
                rect.set_edgecolor('#444444')
        except AttributeError:
            pass  # newer matplotlib uses patches instead, styling skipped

        self._cb.on_clicked(self._on_checkbox)

        # All / None buttons
        if hasattr(self, '_ax_all'):
            self._ax_all.remove()
            self._ax_none.remove()

        self._ax_all  = self.fig.add_axes([0.75, 0.93 - height - 0.04, 0.10, 0.03])
        self._ax_none = self.fig.add_axes([0.86, 0.93 - height - 0.04, 0.10, 0.03])

        self._btn_all  = Button(self._ax_all,  'All',  color='#1a2a1a', hovercolor='#2a4a2a')
        self._btn_none = Button(self._ax_none, 'None', color='#2a1a1a', hovercolor='#4a2a2a')
        self._btn_all.label.set_color('#88dd88')
        self._btn_none.label.set_color('#dd8888')
        self._btn_all.on_clicked(self._select_all)
        self._btn_none.on_clicked(self._select_none)

    def _on_checkbox(self, label):
        self.active[label] = not self.active[label]
        self._draw()

    def _select_all(self, event):
        for t in self.all_traders:
            self.active[t] = True
        self._rebuild_and_draw()

    def _select_none(self, event):
        for t in self.all_traders:
            self.active[t] = False
        self._rebuild_and_draw()

    def _rebuild_and_draw(self):
        self._build_checkboxes()
        self._draw()

    # ── Slider callbacks ──────────────────────────

    def _on_scrub(self, val):
        self.pos = int(val)
        self._draw()

    def _on_window(self, val):
        self.window = int(val)
        self._draw()

    # ── Product switch ────────────────────────────

    def _switch_product(self, product):
        self.product = product
        self._load_product()
        n = len(self.price_df)
        self.slider_scrub.valmax = max(n - 1, 1)
        self.slider_scrub.set_val(0)
        self.slider_window.valmax = max(n, 200)
        self.pos = 0
        self._rebuild_and_draw()

    # ── Draw ──────────────────────────────────────

    def _draw(self):
        lo = self.pos
        hi = min(lo + self.window, len(self.price_df))

        p  = self.price_df.iloc[lo:hi]
        x  = p['x'].values

        for ax in [self.ax_price, self.ax_volume, self.ax_count]:
            ax.cla()
            ax.set_facecolor('#0f0f0f')
            ax.tick_params(colors='#888888', labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor('#333333')

        # ── Price panel ───────────────────────────
        self.ax_price.plot(x, p['ask_price_1'], lw=0.6, color='#2a6a2a', alpha=0.5)
        self.ax_price.plot(x, p['bid_price_1'], lw=0.6, color='#6a2a2a', alpha=0.5)
        self.ax_price.plot(x, p['mid_price'],   lw=0.9, color='#cccccc', alpha=0.8)

        # Day separators
        for bx in self.day_boundaries:
            if lo <= bx <= hi:
                for ax in [self.ax_price, self.ax_volume, self.ax_count]:
                    ax.axvline(bx, color='#444466', lw=0.8, ls='--', alpha=0.7)

        # ── Trade overlays ────────────────────────
        t_window  = self.trade_df[(self.trade_df['x'] >= lo) & (self.trade_df['x'] < hi)]
        legend_handles = []

        # Per-trader volume and count accumulators for lower panels
        trader_vols   = {}
        trader_counts = {}

        for trader in self.all_traders:
            if not self.active[trader]:
                continue

            mask = (t_window['buyer'] == trader) | (t_window['seller'] == trader)
            t    = t_window[mask]
            if t.empty:
                continue

            color = self.color_map[trader]
            sizes = np.clip(t['quantity'].abs() * 3, 8, 120)

            self.ax_price.scatter(
                t['x'], t['price'],
                s=sizes, color=color, alpha=0.85,
                marker='x', linewidths=1.2, zorder=5
            )

            # Accumulate for lower panels
            for _, row in t.iterrows():
                bx = row['x']
                q  = abs(row['quantity'])
                trader_vols[trader]   = trader_vols.get(trader, {})
                trader_counts[trader] = trader_counts.get(trader, {})
                trader_vols[trader][bx]   = trader_vols[trader].get(bx, 0) + q
                trader_counts[trader][bx] = trader_counts[trader].get(bx, 0) + 1

            legend_handles.append(
                Line2D([0], [0], marker='x', color=color, linestyle='none',
                       markersize=6, markeredgewidth=1.2, label=trader)
            )

        # ── Volume panel ──────────────────────────
        for trader, vol_dict in trader_vols.items():
            color = self.color_map[trader]
            xs = list(vol_dict.keys())
            ys = list(vol_dict.values())
            self.ax_volume.bar(xs, ys, color=color, alpha=0.7, width=1.5)

        # ── Count panel ───────────────────────────
        for trader, cnt_dict in trader_counts.items():
            color = self.color_map[trader]
            xs = list(cnt_dict.keys())
            ys = list(cnt_dict.values())
            self.ax_count.bar(xs, ys, color=color, alpha=0.7, width=1.5)

        # ── Labels ────────────────────────────────
        self.ax_price.set_title(
            f'{self.product}  |  rows {lo}–{hi}',
            color='#dddddd', fontsize=9, fontfamily='monospace', pad=4
        )
        self.ax_price.set_ylabel('price',       color='#888888', fontsize=8)
        self.ax_volume.set_ylabel('qty',         color='#888888', fontsize=8)
        self.ax_count.set_ylabel('trade count', color='#888888', fontsize=8)
        self.ax_count.set_xlabel('row index',   color='#888888', fontsize=8)

        if legend_handles:
            self.ax_price.legend(
                handles=legend_handles,
                fontsize=6, facecolor='#111111', edgecolor='#333333',
                labelcolor='white', loc='upper left',
                ncol=max(1, len(legend_handles) // 12)
            )

        self.fig.canvas.draw_idle()


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == '__main__':
    print("Loading data...")
    prices, trades = load_data()
    print(f"Loaded {len(prices)} price rows, {len(trades)} trade rows")
    print(f"Products: {PRODUCTS}")
    all_traders = get_all_traders(trades)
    print(f"Unique traders: {all_traders}")
    TraderScrubber(prices, trades)