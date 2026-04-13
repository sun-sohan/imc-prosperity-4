"""
extract_log.py  –  pull all market data out of a Prosperity .log file

Works with logs produced by the logging trader.py in this repo.

Usage:
    python extract_log.py 86269.log

Outputs (in same directory as the log):
    prices_<submission_id>.csv   – full order book snapshot every tick
    trades_<submission_id>.csv   – every trade (own + market / bot-vs-bot)
"""

import json, sys, pathlib

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_log.py <logfile>")
        sys.exit(1)

    log_path = pathlib.Path(sys.argv[1])
    raw = json.loads(log_path.read_text())

    submission_id = raw.get("submissionId", "unknown")
    out_dir = log_path.parent

    # ── A. activitiesLog → prices CSV ─────────────────────────────────────
    # This is always present and is a verbatim semicolon-delimited CSV.
    prices_csv = raw.get("activitiesLog", "").strip()
    if prices_csv:
        prices_path = out_dir / f"prices_{submission_id}.csv"
        prices_path.write_text(prices_csv)
        n_prices = len(prices_csv.splitlines()) - 1  # minus header
        print(f"[prices]  {n_prices} rows  →  {prices_path}")
    else:
        print("[prices]  activitiesLog is empty – nothing written")

    # ── B. tradeHistory → trades CSV (partial: only algo's own fills) ──────
    trade_history = raw.get("tradeHistory", [])
    if trade_history:
        header = "timestamp;buyer;seller;symbol;currency;price;quantity"
        lines  = [header]
        for t in trade_history:
            lines.append(";".join([
                str(t["timestamp"]),
                t.get("buyer",  ""),
                t.get("seller", ""),
                t["symbol"],
                t["currency"],
                str(t["price"]),
                str(t["quantity"]),
            ]))
        th_path = out_dir / f"trades_own_{submission_id}.csv"
        th_path.write_text("\n".join(lines))
        print(f"[trades/own]  {len(trade_history)} rows  →  {th_path}")

    # ── C. sandboxLog → full market trades CSV (requires logging trader) ───
    # Each non-empty sandboxLog entry is one JSON line printed by trader.py.
    logs = raw.get("logs", [])
    mkt_rows  = []   # bot-vs-bot + algo trades from state.market_trades
    own_rows  = []   # algo fills from state.own_trades (double-check)

    for entry in logs:
        line = (entry.get("lambdaLog") or "").strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = rec.get("t", "")

        for product, trades in rec.get("mkt", {}).items():
            for t in trades:
                mkt_rows.append(";".join([
                    str(t.get("ts", ts)),
                    str(t.get("buyer",  "")),
                    str(t.get("seller", "")),
                    product,
                    "XIRECS",
                    str(t["price"]),
                    str(t["qty"]),
                ]))

        for product, trades in rec.get("own", {}).items():
            for t in trades:
                own_rows.append(";".join([
                    str(t.get("ts", ts)),
                    str(t.get("buyer",  "")),
                    str(t.get("seller", "")),
                    product,
                    "XIRECS",
                    str(t["price"]),
                    str(t["qty"]),
                ]))

    trade_header = "timestamp;buyer;seller;symbol;currency;price;quantity"

    if mkt_rows:
        mkt_path = out_dir / f"trades_market_{submission_id}.csv"
        mkt_path.write_text(trade_header + "\n" + "\n".join(mkt_rows))
        print(f"[trades/market]  {len(mkt_rows)} rows  →  {mkt_path}")
    else:
        print("[trades/market]  no sandboxLog trade data – did you use the logging trader?")

    if own_rows:
        own2_path = out_dir / f"trades_own_verified_{submission_id}.csv"
        own2_path.write_text(trade_header + "\n" + "\n".join(own_rows))
        print(f"[trades/own-verified]  {len(own_rows)} rows  →  {own2_path}")

    print("Done.")

if __name__ == "__main__":
    main()