# IMC Prosperity 4

Our team's code for [IMC Prosperity 4](https://prosperity.imc.com/), a trading competition run by IMC Trading. Each round, teams write a Python bot that trades new simulated products on a limit order book, and the bot is scored on profit. Some rounds also include a manual trading puzzle.

## Rounds

### Tutorial: EMERALDS and TOMATOES
- **EMERALDS** stays near a fixed value of 10,000. The bot quotes one tick inside the best bid and ask whenever the spread is wide enough.
- **TOMATOES** drifts over time. The bot uses a 20-period EMA of the mid price as fair value. It trades against quotes far from that value and quotes inside the spread otherwise.
- In local backtests over the two tutorial days, it made about 13.9K in profit.

### Round 1: ASH_COATED_OSMIUM and INTARIAN_PEPPER_ROOT
- **Osmium** mean-reverts around 10,000. The bot measures how far the mid price is from a slow EMA as a z-score. It market-makes near fair value and leans its quotes toward the side the price should revert to.
- **Pepper Root** trends. The bot goes long to its limit when the price is above a 2000-period EMA. Below the EMA, it cuts its position and goes short in steps as the gap widens.
- **Manual round:** we wrote `auction_optimizer.py`. It finds the clearing price of a sealed-bid auction and searches for the bid price and size that make the most profit.

### Round 2: Same products, cleaner design
- We rewrote the bot into one class per product with a shared helper that enforces position limits.
- Osmium fair value now comes from the "wall mid": the middle of the deepest bid and ask levels, which is steadier than the top-of-book mid.
- Pepper Root buys in tranches at several prices above the best bid so more orders fill during uptrends.
- We also submitted a bid for extra market access (`bid()` returns 3700).

### Round 3: HYDROGEL_PACK, VELVETFRUIT_EXTRACT and vouchers
- The `VEV_*` vouchers are call options on Velvetfruit with strikes from 4000 to 6500.
- We fit a **volatility smile** (implied volatility as a quadratic in moneyness) and priced the vouchers with **Black-Scholes** to find mispriced ones.
- We also built simpler bots that trade each product's deviation from its EMA (mean reversion), and a version that combines the two approaches.
- For Hydrogel we also tried market making around a volume-weighted mid price. It shifted quotes against our inventory, paused when volatility spiked, and flattened the position before the end of the day.

### Round 4: Trading with counterparty data
- Same products as Round 3. The trade data includes which bot was on each side of every trade, and we focused on using that.
- We wrote analysis scripts (`scrubber.py`, `eda_vev3.py`). They score every trader by their average profit 50 to 1000 ticks after each trade, to separate informed traders from noise.
- `informed.py` adds a signal from that analysis: follow the trades of the informed bots and fade the noisy ones.
- The main bot used EMA mean reversion with a separate threshold for each voucher. At the start of each day it also blended the EMA with historical average prices, so the first trades weren't based on an empty EMA.

### Round 5: Many new product groups
- We plotted prices and return correlations across all ten product groups to look for pairs and lead-lag relationships.
- **Oxygen Shakes:** a market-making bot that quotes around a volume-weighted mid. It skews quotes against its inventory and only quotes passively when the spread is at least 2.

## Tools

- `testing_shit/extract_log.py` turns submission logs into price and trade CSVs.
- `EDA_*.py` and the `eda_*.py` scripts plot order books, mid prices and EMAs for each product.
- The backtests in `backtests/` came from a community Prosperity backtester.

## Team

[@sun-sohan](https://github.com/sun-sohan) · [@kev197](https://github.com/kev197) · [@ashvinsat](https://github.com/ashvinsat) · Sharath Venkat
