#!/usr/bin/env python3
"""
Auction Order Book Profit Optimizer
Finds the optimal (bid_price, quantity) for a single limit buy order
in a uniform-price sealed-bid double auction.

Rules:
- Clearing price = price that maximizes total traded volume (tie: higher price wins)
- All bids >= clearing price fill at the clearing price
- You are last in time priority at your price level
- Profit = fill * (settlement - clearing - buy_fee - sell_fee)
"""

# ── Product Definitions ────────────────────────────────────────────────────────

PRODUCTS = {
    "Dryland Flax": {
        "settlement": 30,
        "buy_fee":    0.00,
        "sell_fee":   0.00,
        "bids": {30: 30_000, 29: 5_000, 28: 12_000, 27: 28_000},
        "asks": {28: 40_000, 31: 20_000, 32: 20_000, 33: 30_000},
    },
    "Ember Mushroom": {
        "settlement": 20,
        "buy_fee":    0.05,
        "sell_fee":   0.05,
        "bids": {20: 43_000, 19: 17_000, 18: 6_000, 17: 5_000,
                 16: 10_000, 15: 5_000, 14: 10_000, 13: 7_000},
        "asks": {12: 20_000, 13: 25_000, 14: 35_000, 15: 6_000,
                 16: 5_000,  17: 0,      18: 10_000, 19: 12_000},
    },
}

# ── Core Functions ─────────────────────────────────────────────────────────────

def cum_bids(bids: dict, price: int) -> int:
    """Total bid volume at prices >= price."""
    return sum(v for p, v in bids.items() if p >= price)

def cum_asks(asks: dict, price: int) -> int:
    """Total ask volume at prices <= price."""
    return sum(v for p, v in asks.items() if p <= price)

def find_clearing_price(bids: dict, asks: dict) -> tuple[int, int]:
    """Return (clearing_price, total_traded_volume)."""
    all_prices = sorted(set(list(bids.keys()) + list(asks.keys())))
    best_vol, clearing = -1, None
    for p in all_prices:
        vol = min(cum_bids(bids, p), cum_asks(asks, p))
        if vol > best_vol or (vol == best_vol and (clearing is None or p > clearing)):
            best_vol, clearing = vol, p
    return clearing, best_vol

def simulate_order(product: dict, our_bid_price: int, our_qty: int) -> dict:
    """
    Simulate placing a single buy limit order and return outcome.
    We are last in time priority at our price level.
    """
    bids = dict(product["bids"])
    asks = product["asks"]
    settlement = product["settlement"]
    buy_fee    = product["buy_fee"]
    sell_fee   = product["sell_fee"]

    # Add our order to the bid side
    bids[our_bid_price] = bids.get(our_bid_price, 0) + our_qty

    clearing, total_traded = find_clearing_price(bids, asks)

    # We only fill if our bid >= clearing price
    if our_bid_price < clearing:
        return {"clearing": clearing, "fill": 0, "profit": 0.0, "profit_per_unit": 0.0}

    # Existing higher-priority bids at clearing consume supply first
    existing_priority = cum_bids(product["bids"], clearing)
    our_fill = max(0, min(our_qty, total_traded - existing_priority))

    profit = our_fill * (settlement - clearing - buy_fee - sell_fee)
    ppu    = profit / our_fill if our_fill > 0 else 0.0

    return {
        "clearing":       clearing,
        "fill":           our_fill,
        "profit":         profit,
        "profit_per_unit": ppu,
    }

# ── Optimizer ─────────────────────────────────────────────────────────────────

def find_optimal_order(product: dict, max_qty: int = 200_000, step: int = 500) -> dict:
    """Sweep all bid prices × quantities and return the global profit-maximising order."""
    all_prices = sorted(set(list(product["bids"].keys()) + list(product["asks"].keys())))
    best = {"profit": -1}

    for bid_price in all_prices:
        for qty in range(0, max_qty + step, step):
            result = simulate_order(product, bid_price, qty)
            result.update({"bid_price": bid_price, "qty": qty})
            if result["profit"] > best["profit"]:
                best = result

    return best

# ── Report ─────────────────────────────────────────────────────────────────────

def print_profit_table(product: dict, name: str, bid_price: int, max_qty: int = 50_000, step: int = 1_000):
    """Print profit at each quantity for a fixed bid price."""
    print(f"\n{'─'*62}")
    print(f"  {name}  |  bid @ {bid_price}  |  settlement = {product['settlement']}")
    print(f"{'─'*62}")
    print(f"  {'Qty':>8}  {'Clearing':>9}  {'Fill':>8}  {'Profit':>12}  {'Per Unit':>9}")
    print(f"{'─'*62}")
    prev_clearing = None
    for qty in range(0, max_qty + step, step):
        r = simulate_order(product, bid_price, qty)
        if r["clearing"] != prev_clearing or qty == 0:
            marker = ""
            prev_clearing = r["clearing"]
        print(f"  {qty:>8,}  {r['clearing']:>9}  {r['fill']:>8,}  {r['profit']:>12,.1f}  {r['profit_per_unit']:>9.2f}")

def main():
    for name, product in PRODUCTS.items():
        print(f"\n{'═'*62}")
        print(f"  PRODUCT: {name}")
        print(f"{'═'*62}")

        # Find global optimum
        best = find_optimal_order(product)
        print(f"\n  ★ OPTIMAL ORDER")
        print(f"    Bid Price   : {best['bid_price']}")
        print(f"    Quantity    : {best['qty']:,}")
        print(f"    Clearing    : {best['clearing']}")
        print(f"    Fill        : {best['fill']:,}")
        print(f"    Profit      : {best['profit']:,.1f} XIRECs")
        print(f"    Per Unit    : {best['profit_per_unit']:.2f} XIRECs")

        # Show profit table at optimal bid price
        print_profit_table(product, name, best["bid_price"])

if __name__ == "__main__":
    main()

# ── Charting ───────────────────────────────────────────────────────────────────


# ── Charting ───────────────────────────────────────────────────────────────────

def generate_charts():
    import plotly.graph_objects as go
    import json

    MAX_QTY = 200_000
    STEP    = 500

    for name, product in PRODUCTS.items():
        all_prices = sorted(set(list(product["bids"].keys()) + list(product["asks"].keys())))
        best = find_optimal_order(product, max_qty=MAX_QTY, step=STEP)
        qtys = list(range(0, MAX_QTY + STEP, STEP))

        fig = go.Figure()

        colors = [
            "#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0",
            "#00BCD4", "#FF5722", "#8BC34A", "#FFC107", "#607D8B",
        ]

        for i, bid_price in enumerate(all_prices):
            profits = [simulate_order(product, bid_price, qty)["profit"] for qty in qtys]
            is_optimal_price = (bid_price == best["bid_price"])
            fig.add_trace(go.Scatter(
                x=[q / 1000 for q in qtys],
                y=profits,
                mode="lines",
                name=f"Bid @ {bid_price}",
                line=dict(
                    color=colors[i % len(colors)],
                    width=3 if is_optimal_price else 1.5,
                    dash="solid" if is_optimal_price else "dot",
                ),
                opacity=1.0 if is_optimal_price else 0.55,
            ))

        fig.add_trace(go.Scatter(
            x=[best["qty"] / 1000],
            y=[best["profit"]],
            mode="markers",
            name=f"Optimal: bid {best['bid_price']}, {best['qty']//1000}k units",
            marker=dict(symbol="star", size=18, color="gold",
                        line=dict(color="black", width=1.5)),
        ))

        slug = name.lower().replace(" ", "_")
        fig.update_layout(
            title={
                "text": (
                    f"{name} — Profit vs Qty by Bid Price<br>"
                    f"<span style='font-size:16px;font-weight:normal;'>"
                    f"Settlement={product['settlement']} | "
                    f"Fees={product['buy_fee']+product['sell_fee']:.2f}/unit | "
                    f"Optimal: bid {best['bid_price']}, qty {best['qty']//1000}k -> "
                    f"{best['profit']:,.0f} XIRECs"
                    f"</span>"
                )
            },
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        )
        fig.update_xaxes(title_text="Quantity (k units)")
        fig.update_yaxes(title_text="Profit (XIRECs)")

        fname = f"{slug}_profit_chart.html"
        fig.write_html(fname, include_plotlyjs="cdn", full_html=True)
        print(f"Saved: {fname}")


if __name__ == "__main__":
    main()
    generate_charts()
