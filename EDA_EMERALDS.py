import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv('prices_round_0_day_-1.csv', sep=';')
df = df.truncate(after=1000)
print(df)

gb = df.groupby('product')

product = 'EMERALDS'

x = gb.get_group(product)['timestamp']
y1 = gb.get_group(product)['ask_price_1']
y2 = gb.get_group(product)['bid_price_1']
# y3 = gb.get_group(product)['profit_and_loss']


plt.figure(figsize=(15, 8))
plt.plot(x, y1, linewidth=2, color='green')
plt.plot(x, y2, linewidth=2, color='red')
# plt.plot(x, y3, linewidth=2, color='blue')
plt.ticklabel_format(useOffset=False)
plt.show()