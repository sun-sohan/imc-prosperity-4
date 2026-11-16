# IMC Prosperity 4: Algorithmic Trading Competition

Python trading algorithms, market data analysis, and backtesting tools built for **IMC Prosperity 4** (2026). IMC Trading runs this global competition for quantitative trading. Each team writes an automated trading bot that trades simulated products against market-making and market-taking bots on a limit order book. Teams are ranked by profit and loss (PnL).

**Tech stack:** Python · pandas · NumPy · Matplotlib · Jupyter Notebook · JSON log parsing · backtesting

**Topics:** algorithmic trading · market making · quantitative research · limit order book microstructure · statistical arbitrage · time-series analysis · risk and position management

---

## Highlights

- **Market-making strategy** for a stable-value product (`EMERALDS`). It quotes inside the bid-ask spread around a fixed fair value of 10,000 and respects position limits.
- **Adaptive fair-value strategy** for a mean-reverting product (`TOMATOES`). It uses an **exponential moving average (EMA)** of the mid price, carried between ticks through the exchange's `traderData` state string. It takes mispriced liquidity and also quotes passively when the spread is wide.
- **Local backtests:** the tutorial-round algorithm made about **13,900 SeaShells** of PnL over two simulated trading days (about 7.4K from `EMERALDS` and 6.5K from `TOMATOES`). See [`backtests/`](backtests/).
- **Log extraction tool** ([`testing_shit/extract_log.py`](testing_shit/extract_log.py)). It turns raw Prosperity submission logs (JSON) into clean order book and trade CSVs for offline analysis.
- **Exploratory data analysis (EDA)** of order book data: bid/ask levels, mid price, spread, and EMA smoothing, plotted with Matplotlib.

---

## Repository Structure

```
.
├── strategy.py              # Tutorial-round Trader: EMERALDS market making + TOMATOES EMA strategy
├── datamodel.py             # Exchange data model (TradingState, OrderDepth, Order, Trade, ...)
├── EDA_EMERALDS.py          # Order book visualization for EMERALDS
├── EDA_TOMATOES.py          # Bid/ask/mid price + EMA analysis for TOMATOES
├── prices_round_0_*.csv     # Tutorial-round order book snapshots
├── trades_round_0_*.csv     # Tutorial-round market trades
├── backtests/               # Backtester output logs (tutorial round)
├── round_1/
│   ├── osmium_and_pepper.py # Round 1 Trader scaffold (ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT)
│   ├── data_capsule/        # Round 1 price and trade data
│   └── backtests/           # Round 1 backtest logs
├── round_3/
│   └── data_capsule/        # Round 3 data: HYDROGEL_PACK, VELVETFRUIT_EXTRACT, VEV_* vouchers
└── testing_shit/
    ├── extract_log.py       # Converts submission logs to prices/trades CSVs
    └── testing.ipynb        # Research notebook
```

---

## Strategy Details

### EMERALDS: fixed fair-value market making
`EMERALDS` trades in a tight band around **10,000**. The algorithm:
1. Reads the best bid and best ask from the order book.
2. If the best ask is at least 2 above fair value, it posts a sell order **one tick inside** the ask.
3. If the best bid is at least 2 below fair value, it posts a buy order **one tick inside** the bid.
4. Limits order sizes so the position stays within **±60** units.

This captures the spread while staying competitive in queue priority.

### TOMATOES: EMA-based fair value
`TOMATOES` drifts over time, so a fixed fair value doesn't work. The algorithm:
1. Computes the mid price from the best bid and best ask.
2. Updates a **20-period EMA** (`k = 2 / (N + 1)`) and saves it in `traderData`, because the exchange runs the bot without keeping memory between ticks.
3. Uses the raw mid price as fair value during a short warm-up period, then switches to the EMA.
4. **Takes** liquidity when a quote is at least 5 away from fair value (aggressive orders).
5. **Makes** markets one tick inside the spread when quotes are at least 3 away from fair value (passive orders).
6. Keeps the position within **±30** units.

---

## Getting Started

```bash
git clone https://github.com/sun-sohan/imc-prosperity-4.git
cd imc-prosperity-4
pip install pandas numpy matplotlib

# Visualize tutorial-round order book data
python EDA_TOMATOES.py

# Convert a Prosperity submission log to CSVs
python testing_shit/extract_log.py path/to/submission.log
```

To backtest, run `strategy.py` through a community Prosperity backtester. The logs in `backtests/` came from that kind of run.

---

## Team

- Sohan Sunkari ([@sun-sohan](https://github.com/sun-sohan))
- Kevin Y ([@kev197](https://github.com/kev197))
- [@ashvinsat](https://github.com/ashvinsat)
