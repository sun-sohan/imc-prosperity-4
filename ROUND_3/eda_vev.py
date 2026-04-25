import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

DAY_TO_TTE = {0: 8/252, 1: 7/252, 2: 6/252}

VOUCHERS = ['VEV_4000', 'VEV_4500', 'VEV_5000', 'VEV_5100', 'VEV_5200',
            'VEV_5300', 'VEV_5400', 'VEV_5500', 'VEV_6000', 'VEV_6500']
STRIKES  = [int(v.split('_')[1]) for v in VOUCHERS]






dfs = []
for day in [0, 1, 2]:
    df = pd.read_csv(f'ROUND_3/prices_round_3_day_{day}.csv', sep=';')
    df['day'] = day
    df['ts_within_day'] = df['timestamp']
    df['timestamp'] = df['timestamp'] + day * 999_900   # global, unique
    dfs.append(df)
df_all = pd.concat(dfs).reset_index(drop=True)

underlying = df_all[df_all['product'] == 'VELVETFRUIT_EXTRACT'] \
                .set_index('timestamp')['mid_price'].rename('underlying')

voucher_series = {}
for v in VOUCHERS:
    voucher_series[v] = df_all[df_all['product'] == v] \
                            .set_index('timestamp')['mid_price'].rename(v)

merged = pd.concat([underlying] + list(voucher_series.values()), axis=1) \
            .dropna(subset=['underlying']) \
            .sort_index()

meta = df_all[df_all['product'] == 'VELVETFRUIT_EXTRACT'] \
            .set_index('timestamp')[['day', 'ts_within_day']]

merged = merged.join(meta)


# fig, axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)

# # underlying
# axes[0].plot(merged.index, merged['underlying'], linewidth=1.2, color='black')
# axes[0].set_ylabel('Underlying')
# axes[0].set_title('VELVETFRUIT_EXTRACT')
# axes[0].grid(True, alpha=0.3)

# # deep ITM (big values)
# for v in ['VEV_4000', 'VEV_4500']:
#     axes[1].plot(merged.index, merged[v], linewidth=1.2, label=v)
# axes[1].set_ylabel('Deep ITM')
# axes[1].legend(fontsize=9)
# axes[1].grid(True, alpha=0.3)

# # ATM and OTM (smaller values)
# for v in ['VEV_5000', 'VEV_5100', 'VEV_5200', 'VEV_5300', 'VEV_5400', 'VEV_5500', 'VEV_6000', 'VEV_6500']:
#     axes[2].plot(merged.index, merged[v], linewidth=1.2, label=v)
# axes[2].set_ylabel('ATM/OTM')
# axes[2].set_xlabel('Global timestamp')
# axes[2].legend(fontsize=9, ncol=2)
# axes[2].grid(True, alpha=0.3)

# for ax in axes:
#     for boundary in [999_900, 2 * 999_900]:
#         ax.axvline(boundary, color='red', linestyle='--', linewidth=0.8, alpha=0.5)

# plt.tight_layout()
# plt.show()







from scipy.stats import norm
from scipy.optimize import brentq

r = 0.0       

def bs_call_price(S, K, T, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

def implied_vol(market_prices, S, K, T, max_iter=50, tol=1e-6):
    """
    Vectorized IV via Newton-Raphson. Accepts scalars or arrays.
    Falls back to brentq for non-converged values.
    """
    market_prices = np.atleast_1d(np.asarray(market_prices, dtype=float))
    S = np.atleast_1d(np.asarray(S, dtype=float))
    K = np.atleast_1d(np.asarray(K, dtype=float))
    T = np.atleast_1d(np.asarray(T, dtype=float))
    
    # broadcast to common shape
    market_prices, S, K, T = np.broadcast_arrays(market_prices, S, K, T)
    out = np.full(market_prices.shape, np.nan)
    
    # filter invalid: non-positive price/S, or below intrinsic
    intrinsic = np.maximum(S - K, 0.0)
    valid = (market_prices > intrinsic) & (S > 0) & (T > 0)
    if not valid.any():
        return out if out.size > 1 else float(out[0])
    
    p = market_prices[valid]
    s = S[valid]
    k = K[valid]
    t = T[valid]
    
    # Manaster-Koehler initial guess: sigma_0 = sqrt(2 * |ln(S/K) + r*T| / T)
    # works well when near ATM; clip to sane range
    sigma = np.sqrt(np.maximum(2.0 * np.abs(np.log(s / k)) / t, 0.04))
    sigma = np.clip(sigma, 0.01, 3.0)
    
    sqrt_t = np.sqrt(t)
    converged = np.zeros_like(sigma, dtype=bool)
    
    for _ in range(max_iter):
        d1 = (np.log(s / k) + 0.5 * sigma**2 * t) / (sigma * sqrt_t)
        d2 = d1 - sigma * sqrt_t
        price = s * norm.cdf(d1) - k * norm.cdf(d2)   # r = 0
        vega = s * norm.pdf(d1) * sqrt_t
        
        diff = price - p
        converged = np.abs(diff) < tol
        if converged.all():
            break
        
        # avoid division by tiny vega
        step = np.where(vega > 1e-10, diff / vega, 0.0)
        sigma = sigma - step
        sigma = np.clip(sigma, 1e-6, 10.0)
    
    # write converged values back
    result_valid = np.where(converged, sigma, np.nan)
    
    # fallback to brentq for non-converged
    bad_idx = np.where(~converged)[0]
    for i in bad_idx:
        try:
            result_valid[i] = brentq(
                lambda sig: bs_call_price(s[i], k[i], t[i], sig) - p[i],
                1e-6, 10.0, xtol=tol
            )
        except ValueError:
            pass  # leave as NaN
    
    out[valid] = result_valid
    return out if out.size > 1 else float(out[0])
    
def moneyness(S, K, T):
    return np.log(K / S) / np.sqrt(T)










# TIMESTEPS_PER_DAY = 1_000_000
# ONE_DAY = 1/252
# T_AT_START = 8/252

# def tte_for(day, ts_within_day):
#     return T_AT_START - (day + ts_within_day / TIMESTEPS_PER_DAY) * ONE_DAY

# # build everything as flat arrays first
# ts_list, vouch_list, strike_list = [], [], []
# S_list, T_list, day_list, twd_list, price_list = [], [], [], [], []

# for ts, row in merged.iterrows():
#     if np.isnan(row['underlying']):
#         continue
#     T = tte_for(row['day'], row['ts_within_day'])
#     for v, K in zip(VOUCHERS, STRIKES):
#         if np.isnan(row[v]):
#             continue
#         ts_list.append(ts); vouch_list.append(v); strike_list.append(K)
#         S_list.append(row['underlying']); T_list.append(T)
#         day_list.append(row['day']); twd_list.append(row['ts_within_day'])
#         price_list.append(row[v])

# S_arr = np.array(S_list)
# K_arr = np.array(strike_list)
# T_arr = np.array(T_list)
# P_arr = np.array(price_list)

# iv_arr = implied_vol(P_arr, S_arr, K_arr, T_arr)   # one call, all rows

# iv_df = pd.DataFrame({
#     'timestamp': ts_list, 'voucher': vouch_list, 'strike': strike_list,
#     'T': T_arr, 'iv': iv_arr,
#     'moneyness': np.log(K_arr / S_arr) / np.sqrt(T_arr),
#     'underlying': S_arr, 'day': day_list, 'ts_within_day': twd_list,
# })

# iv_df_clean = iv_df.dropna(subset=['iv'])

# iv_df_clean.to_csv('iv_df_clean.csv', index=False)



















# # read in data once computed
iv_df_clean = pd.read_csv('ROUND_3/iv_df_clean.csv')












from numpy.polynomial import polynomial as P
VOUCHERS_FIT = ['VEV_5000', 'VEV_5100', 'VEV_5200', 'VEV_5300', 'VEV_5400', 'VEV_5500']
coeffs = np.polyfit(
    iv_df_clean[iv_df_clean['voucher'].isin(VOUCHERS_FIT)]['moneyness'],
    iv_df_clean[iv_df_clean['voucher'].isin(VOUCHERS_FIT)]['iv'],
    deg=2
)
print(f'a={coeffs[0]:.4f}, b={coeffs[1]:.4f}, c={coeffs[2]:.4f}')

def fair_vol(m_t):
    return coeffs[0] * (m_t**2) + coeffs[1] * m_t + coeffs[2]

x = np.linspace(iv_df_clean['moneyness'].min(), iv_df_clean['moneyness'].max(), 200)
y = np.polyval(coeffs, x)

plt.figure(figsize=(10, 6))
for v, group in iv_df_clean.groupby('voucher'):
    alpha = 0.3 if v in VOUCHERS_FIT else 0.05
    plt.scatter(group['moneyness'], group['iv'], alpha=alpha, s=10, label=v)
plt.plot(x, y, color='black', linewidth=2, label='fitted smile')
plt.legend(fontsize=7)
plt.xlabel('Moneyness log(K/S) / sqrt(T)')
plt.ylabel('Implied Volatility')
plt.title('Vol Smile')
plt.grid(True)
plt.show()







# fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
# for d, ax in zip([0, 1, 2], axes):
#     sub = iv_df_clean[iv_df_clean['day'] == d]
#     for v, group in sub.groupby('voucher'):
#         if v not in VOUCHERS_FIT: continue
#         ax.scatter(group['moneyness'], group['iv'], alpha=0.3, s=8, label=v)
#     ax.set_title(f'Day {d}')
#     ax.legend(fontsize=7)
# plt.show()








# # now check residuals on 5400 and 5500
# for v in ['VEV_5400', 'VEV_5500']:
#     sub = iv_df_clean[iv_df_clean['voucher'] == v]
#     fair_iv = np.polyval(coeffs, sub['moneyness'])
#     vol_resid = sub['iv'] - fair_iv
#     print(f"{v}: mean vol residual = {vol_resid.mean():.4f}, std = {vol_resid.std():.4f}")










# Compute fair price for every row using fitted smile
fair_iv = np.polyval(coeffs, iv_df_clean['moneyness'].values)
S = iv_df_clean['underlying'].values
K = iv_df_clean['strike'].values
T = iv_df_clean['T'].values

# Vectorized BS call pricing
d1 = (np.log(S / K) + 0.5 * fair_iv**2 * T) / (fair_iv * np.sqrt(T))
d2 = d1 - fair_iv * np.sqrt(T)
fair_price = S * norm.cdf(d1) - K * norm.cdf(d2)

# Reconstruct market price from stored IV (will exactly equal original mid)
mkt_iv = iv_df_clean['iv'].values
d1m = (np.log(S / K) + 0.5 * mkt_iv**2 * T) / (mkt_iv * np.sqrt(T))
d2m = d1m - mkt_iv * np.sqrt(T)
market_price = S * norm.cdf(d1m) - K * norm.cdf(d2m)

iv_df_clean = iv_df_clean.copy()
iv_df_clean['fair_price'] = fair_price
iv_df_clean['market_price'] = market_price
iv_df_clean['price_residual'] = market_price - fair_price
iv_df_clean['vol_residual'] = mkt_iv - fair_iv





vdf = df_all[df_all['product'] == 'VELVETFRUIT_EXTRACT']
spread = vdf['ask_price_1'] - vdf['bid_price_1']
print(f"VELVETFRUIT_EXTRACT: mean={spread.mean():.2f}, median={spread.median():.2f}")






# # vouchers against fair value

# for v, K in zip(VOUCHERS, STRIKES):
#     if v != 'VEV_5300' and v != 'VEV_5400' and v != 'VEV_5500':
#         continue

#     group = iv_df_clean[iv_df_clean['voucher'] == v].sort_values('timestamp')
    
#     fair_prices = [
#         bs_call_price_safe(row['underlying'], K, DAY_TO_TTE[row['day']], r, fair_vol(row['moneyness']))
#         for _, row in group.iterrows()
#     ]
    
#     fig, ax = plt.subplots(figsize=(12, 4))
#     ax.plot(group['timestamp'], group['market_price'], linewidth=0.8, label='market price')
#     ax.plot(group['timestamp'], fair_prices, linewidth=0.8, linestyle='--', label='fair price')
#     ax.set_title(v)
#     ax.set_xlabel('Timestamp')
#     ax.set_ylabel('Price')
#     ax.legend(fontsize=7)
#     ax.grid(True)
#     plt.tight_layout()
#     plt.show()