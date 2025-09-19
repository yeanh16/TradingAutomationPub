import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from trading_automation.core.Utils import *
from datetime import datetime

BRACKET = 100

while True:
    order_book = futures_get_order_book("SUSHIUSDT", limit=BRACKET)
    bids = order_book.get('bids')
    asks = order_book.get('asks')
    bids_total = 0
    asks_total = 0
    for i in range(BRACKET):
        bid = bids[i]
        bids_total += Decimal(bid[0]) * Decimal(bid[1])
        ask = asks[i]
        asks_total += Decimal(ask[0]) * Decimal(ask[1])
    if bids_total < asks_total:
        percentage = (1-(asks_total / bids_total)) * 100
    else:
        percentage = (1-(bids_total / asks_total)) * -100
    print(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} "
          f"bids_total: {bids_total}\t asks_total: {asks_total}\t percentage: {round(percentage, 5)}\t diff: {bids_total-asks_total}")
