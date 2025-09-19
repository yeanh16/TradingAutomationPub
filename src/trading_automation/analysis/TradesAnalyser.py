from trading_automation.core.Logger import *
import os
import sqlite3

SQL_CONNECTION = create_connection(DB_LOG_PATH)

#trades = execute_read_query(SQL_CONNECTION, "SELECT * FROM trades")


def calc_bid_ask_post_only_exit_difference(maker_fee=Decimal('0.0002'), taker_fee=Decimal('0.0004')):
    """ 
    calculate the net profit using bid/ask post only exit compared to market exits
    the profit is made up from the fees saved and better exit price from using this
    strategy
    """
    query = "SELECT position_side, average_entry_price, average_exit_price, " \
            "position_size, at_bid_ask_post_only_exit_count, " \
            "at_bid_ask_post_only_exit_failed_count, if_market_close_avg_price " \
            "FROM trades WHERE at_bid_ask_post_only_exit_count >= 1"
    trades = execute_read_query(SQL_CONNECTION, query)
    total_pnl = 0
    total_pnl_market_exit = 0
    for trade in trades:
        entry_price = Decimal(trade[1])
        exit_price = Decimal(trade[2])
        position_size = abs(Decimal(trade[3]))
        market_close_price = Decimal(trade[6])
        if trade[0] == "LONG":
            pnl = exit_price * position_size - entry_price * position_size
            pnl = pnl - (exit_price * position_size * maker_fee) - (entry_price * position_size * maker_fee)
            pnl_market_exit = market_close_price * position_size - entry_price * position_size
            pnl_market_exit = pnl_market_exit - (market_close_price * position_size * taker_fee) - (entry_price * position_size * maker_fee)
            total_pnl += pnl
            total_pnl_market_exit += pnl_market_exit
        else:
            pnl = entry_price * position_size - exit_price * position_size
            pnl = pnl - (entry_price * position_size * maker_fee) - (exit_price * position_size * maker_fee)
            pnl_market_exit = entry_price * position_size - market_close_price * position_size
            pnl_market_exit = pnl_market_exit - (entry_price * position_size * maker_fee) - (market_close_price * position_size * taker_fee)
            total_pnl += pnl
            total_pnl_market_exit += pnl_market_exit

    return total_pnl - total_pnl_market_exit

result = calc_bid_ask_post_only_exit_difference()
