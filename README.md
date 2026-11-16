# IMC Prosperity 4

Our team's code for [IMC Prosperity 4](https://prosperity.imc.com/), a trading competition where each team writes a Python bot that trades simulated products on a limit order book. Teams are ranked by profit.

## Tutorial round strategy (`strategy.py`)

- **EMERALDS** stays near a fixed value of 10,000. The bot quotes one tick inside the best bid and ask and keeps its position within ±60.
- **TOMATOES** drifts over time. The bot tracks a 20-period EMA of the mid price as its fair value. It buys or sells against quotes that are far from fair value and quotes inside the spread otherwise. Its position stays within ±30.

In local backtests over the two tutorial days, it made about 13.9K in profit (7.4K from EMERALDS, 6.5K from TOMATOES).

## Layout

| Path | Contents |
| --- | --- |
| `strategy.py` | Tutorial round trading bot |
| `datamodel.py` | Data types from the competition's exchange |
| `EDA_*.py` | Order book plots for the tutorial products |
| `round_1/`, `round_3/` | Price and trade data for later rounds, plus the round 1 bot (unfinished) |
| `backtests/` | Backtest logs |
| `testing_shit/extract_log.py` | Turns submission logs into price and trade CSVs |

## Team

[@sun-sohan](https://github.com/sun-sohan) · [@kev197](https://github.com/kev197) · [@ashvinsat](https://github.com/ashvinsat)
