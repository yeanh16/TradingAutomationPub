import re
import numpy as np
import random
from decimal import Decimal
from datetime import datetime

pattern = r"(\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}) .* (Sell|Buy) exit order .* \(\$(-?\d*\.\d*), gain: \$(-?\d*\.\d*), pnl%: (-?\d*.\d*)\)"
DATETIME_PATTERN = '%d/%m/%Y %H:%M:%S'

with open('discordlog.txt', 'r') as f:
    lines = f.readlines()


def process_trades_file(instrument=None):
    long_trades = []
    short_trades = []
    long_gains = []
    short_gains = []
    trades_day_dict = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    for line in lines:
        re_test = re.search(pattern, line)
        if re_test and (instrument in line if instrument is not None else True):
            if re_test.group(5) == "0.0" or re_test.group(5) == "0":
                continue
            trade_perc = float(re_test.group(5))
            trade_gain = float(re_test.group(4))
            if re_test.group(2) == "Sell":
                long_trades.append(trade_perc)
                long_gains.append(trade_gain)
            elif re_test.group(2) == "Buy":
                short_trades.append(float(trade_perc))
                short_gains.append(float(trade_gain))
            trades_day_dict[datetime.strptime(re_test.group(1), DATETIME_PATTERN).weekday()].append((trade_perc, trade_gain))
    # add missing liquidation trades
    for i in range(7):
        short_trades.append(-100)
    return long_trades, short_trades, long_gains, short_gains


long_trades, short_trades, long_gains, short_gains = process_trades_file()

"""
np.mean([x[0] for x in trades_day_dict[0]])
0.2322461892436008
np.mean([x[0] for x in trades_day_dict[1]])
0.1071971971971972
np.mean([x[0] for x in trades_day_dict[2]])
0.11980343368997266
np.mean([x[0] for x in trades_day_dict[3]])
0.21931318681318682
np.mean([x[0] for x in trades_day_dict[4]])
0.1359246358454718
np.mean([x[0] for x in trades_day_dict[5]])
0.2364734982332155
np.mean([x[0] for x in trades_day_dict[6]])
0.27586708203530635
np.sum([x[1] for x in trades_day_dict[0]])
8917.06
np.sum([x[1] for x in trades_day_dict[1]])
382.0720000000001
np.sum([x[1] for x in trades_day_dict[2]])
2295.5830000000005
np.sum([x[1] for x in trades_day_dict[3]])
6335.28
np.sum([x[1] for x in trades_day_dict[4]])
3538.9500000000007
np.sum([x[1] for x in trades_day_dict[5]])
2221.3279999999995
np.sum([x[1] for x in trades_day_dict[6]])
4726.522999999998
len(trades_day_dict[0])
3477
len(trades_day_dict[1])
3996
len(trades_day_dict[2])
4019
len(trades_day_dict[3])
2912
len(trades_day_dict[4])
3158
len(trades_day_dict[5])
2830
len(trades_day_dict[6])
2889
"""

def sample_trades_from_pnl_list(backtesttradeinfo_list, number_of_trades=1000, sample_size=1000, compounding=True):
    """
    also known as monte carlo testing
    """
    STARTING_BALANCE = 1000
    for ratio in [0.01, 0.03, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]:
        end_balance_results = []
        end_max_balance_drawdown_results = []
        for j in range(sample_size):
            balance = STARTING_BALANCE
            balance_tracker = [balance]
            for i in range(number_of_trades):
                bet_size = balance if compounding else min(balance, STARTING_BALANCE)
                # select randomly i number of trades to take using past performances
                random_trade = Decimal(backtesttradeinfo_list[random.randint(0, len(backtesttradeinfo_list) - 1)])
                balance = max(0, balance + Decimal(str(ratio)) * bet_size * Decimal(random_trade*Decimal('0.01')))
                balance_tracker.append(balance)
            # calculate balance drawdown
            highest_balance_seen = 0
            highest_balance_drawdown_seen = 0
            for b in balance_tracker:
                highest_balance_seen = b if b > highest_balance_seen else highest_balance_seen
                if b < highest_balance_seen:
                    balance_drawdown = (highest_balance_seen - b) / highest_balance_seen
                    highest_balance_drawdown_seen = balance_drawdown if balance_drawdown > highest_balance_drawdown_seen else highest_balance_drawdown_seen
            end_balance_results.append(balance)
            end_max_balance_drawdown_results.append(Decimal(str(highest_balance_drawdown_seen)))
        result_str = f"RATIO {ratio} MASTER RESULT MEDIAN {np.median(end_balance_results)} MIN {np.min(end_balance_results)} MAX {np.max(end_balance_results)} MEAN {np.mean(end_balance_results)} STANDARD_ERROR {Decimal(np.std(end_balance_results)) / Decimal(np.sqrt(sample_size))}. MAX DRAWDOWN STATS: MEAN BALANCE {np.mean(end_max_balance_drawdown_results)}"
        print(result_str)
