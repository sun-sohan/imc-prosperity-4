import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv('round_1/data_capsule/prices_round_1_day_0.csv', sep=';')
# df = df.truncate(before=8000, after=9000)

gb = df.groupby('product')

product = 'ASH_COATED_OSMIUM'

df = gb.get_group(product)

y3 = df['mid_price']
idx = y3[y3 < 100].index
print(idx)
df = df.drop(index=idx)

x = df['timestamp']
y1 = df['ask_price_1']
y2 = df['bid_price_1']
y3 = df['mid_price']
y4 = df['mid_price'].ewm(span=1000, adjust=False).mean()
print(y3.mean())
spread = y1 - y2

plt.figure(figsize=(10, 5))
# plt.plot(x, y1, linewidth=0.9, color='green')
# plt.plot(x, y2, linewidth=0.9, color='red')
# plt.plot(x, y3, linewidth=0.1, color='blue')
# plt.plot(x, y4, linewidth=0.9, color='yellow')
plt.plot(x, spread, linewidth=2, color='yellow')
plt.title('osmium')
plt.ticklabel_format(useOffset=False)
plt.show()