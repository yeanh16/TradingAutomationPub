import random as random
import numpy as np
import statistics

wingainspercentage = 13 * 0.01  # max percentage win
liquidationpercentage = 7.6 * 0.01  # percentage of liquidation (used before winpercentage)
winpercentage = 100 * 0.01  # percentage of times wingainspercentage target is hit (if not liquidated). If 0, assume a uniform random distribution of returns from -99% - wingainspercentage
starting_capital = 4000
max_pos_size = 80000
take_profit_percentage = 0 * 0.01  # amount to take off the table per loop
take_profit_percentage_array = [0]  # , 0.05, 0.1, 0.15, 0.2]
capital_risk_percentage_array = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]

loops = 208  # or number of months/time
runs = 50000
print(f"loops {loops} wingainspercentage {wingainspercentage} winpercentage {winpercentage} liquidationpercentage {liquidationpercentage}"
      f" starting_capital {starting_capital} max_pos_size {max_pos_size}")
for risk in capital_risk_percentage_array:
    for take_profit in take_profit_percentage_array:
        take_profit_percentage = take_profit
        print(f"Take profit @{take_profit}")
        results = []
        profits = []
        total_losses = []
        worst_run = 99999999999999
        best_run = 0
        for run in range(0, runs):
            capital = starting_capital
            taken_profits = 0
            total_loss = 0
            for i in range(0, loops):
                # print(f"{i} capital = {capital}")
                if capital == 0:
                    break
                position = capital * risk
                if position > max_pos_size:
                    position = max_pos_size
                capital = capital - position
                if random.random() <= liquidationpercentage:  # we don't fully realise wingainspercentage & get liquidated
                    total_loss += position
                elif random.random() <= winpercentage:  # we fully realise target wingainspercentage
                    capital = capital + position * (1 + wingainspercentage)
                else:  # we don't fully realise wingainspercentage but don't get liquidated
                    percentage_change = random.randint(-99, wingainspercentage * 100) * 0.01  # assume a random return between -99% to wingainspercentage
                    net_change = position * (1 + percentage_change)
                    capital = capital + net_change
                    if net_change < 0:
                        total_loss += net_change
                take_profit = (capital * take_profit_percentage)
                capital = capital - take_profit
                taken_profits = taken_profits + take_profit
            # print(f"{run} result = {capital}")
            results.append(capital)
            profits.append(taken_profits)
            total_losses.append(total_loss)
            if capital < worst_run:
                worst_run = capital
            if capital > best_run:
                best_run = capital
        print(f"risk {risk}:\t total money earned median = {statistics.median(results) + statistics.median(profits)},"
              f"\t median total loss = {statistics.median(total_losses)},"
              f"\t median profits taken = {statistics.median(profits)},"
              f"\t median end trading balance = {statistics.median(results)},"
              f"\t average = {np.mean(results)},"
              f"\t average profits taken = {np.mean(profits)},"
              f"\t total average = {np.mean(results) + np.mean(profits)},"
              f"\t s.d = {np.std(results)},"
              f"\t worst run = {worst_run},"
              f"\t best run = {best_run}")
