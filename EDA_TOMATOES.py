import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv('prices_round_0_day_-2.csv', sep=';')
df = df.truncate(after=1000)

gb = df.groupby('product')

product = 'TOMATOES'

x = gb.get_group(product)['timestamp']
y1 = gb.get_group(product)['ask_price_1']
y2 = gb.get_group(product)['bid_price_1']
y3 = gb.get_group(product)['mid_price']
y4 = gb.get_group(product)['mid_price'].ewm(span=20, adjust=False).mean()

print((y1 - y3).mean())

plt.figure(figsize=(12, 6))
plt.plot(x, y1, linewidth=2, color='green')
plt.plot(x, y2, linewidth=2, color='red')
plt.plot(x, y3, linewidth=2, color='blue')
plt.plot(x, y4, linewidth=2, color='black')
plt.title(label='bid/ask of order book over time')
plt.ticklabel_format(useOffset=False)
plt.show()