import pandas as pd
import numpy as np

iv_df_clean = pd.read_csv('ROUND_3/iv_df_clean.csv')

# recompute residuals (in case CSV doesn't have them)
SMILE_COEFFS = [0.0589, 0.0226, 0.2020]
fair_iv = np.polyval(SMILE_COEFFS, iv_df_clean['moneyness'].values)
S = iv_df_clean['underlying'].values
K = iv_df_clean['strike'].values
T = iv_df_clean['T'].values

from scipy.stats import norm
d1 = (np.log(S/K) + 0.5 * fair_iv**2 * T) / (fair_iv * np.sqrt(T))
d2 = d1 - fair_iv * np.sqrt(T)
fair_price = S * norm.cdf(d1) - K * norm.cdf(d2)

mkt_iv = iv_df_clean['iv'].values
d1m = (np.log(S/K) + 0.5 * mkt_iv**2 * T) / (mkt_iv * np.sqrt(T))
d2m = d1m - mkt_iv * np.sqrt(T)
market_price = S * norm.cdf(d1m) - K * norm.cdf(d2m)

iv_df_clean = iv_df_clean.copy()
iv_df_clean['price_residual'] = market_price - fair_price

# init values
for v in ['VEV_5400', 'VEV_5500']:
    sub = iv_df_clean[iv_df_clean['voucher'] == v].sort_values('timestamp').reset_index(drop=True)
    ema_resid = sub['price_residual'].ewm(span=20000).mean()
    dev = (sub['price_residual'] - ema_resid).abs().ewm(span=20000).mean()
    print(f"{v}: residual_init = {sub['price_residual'].mean():.4f}, dev_init = {dev.mean():.4f}")









for v in ['VEV_4500', 'VEV_4000']:
    sub = iv_df_clean[iv_df_clean['voucher'] == v].sort_values('timestamp').reset_index(drop=True)
    ema = sub['price_residual'].ewm(span=1000).mean()
    dev = (sub['price_residual'] - ema).abs().ewm(span=1000).mean()
    print(f'    "{v}": {sub["price_residual"].mean():.3f},  # mean')
    print(f'    "{v}": {dev.mean():.3f},   # dev')