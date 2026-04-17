import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv('round_1/data_capsule/prices_round_1_day_0.csv', sep=';')
# df = df.truncate(before=1000, after=9000)

gb = df.groupby('product')

product = 'INTARIAN_PEPPER_ROOT'

df = gb.get_group(product)

y3 = df['mid_price']
idx = y3[y3 < 100].index
print(idx)
print(len(idx))
df = df.drop(index=idx).reset_index()

x = df['timestamp']
y1 = df['ask_price_1']
y2 = df['bid_price_1']
y3 = df['mid_price']
# v = y3[5000]

# for i in range(5001, 7000):
#     y3[i] = v
#     v -= 0.07
# for i in range(7000, 9983):
#     y3[i] = v
#     v += 0.0001
y4 = y3.ewm(span=2000, adjust=False).mean()
y5 = y3.rolling(window=800).mean()
spread = y1 - y2


plt.figure(figsize=(10, 5))
# plt.plot(x, y1, linewidth=2, color='green')
plt.plot(x, y3, linewidth=2, color='red')
plt.plot(x, y4, linewidth=2, color='blue')
# plt.plot(x, y5, linewidth=2, color='yellow')
plt.title('peppers')
plt.ticklabel_format(useOffset=False)
plt.show()