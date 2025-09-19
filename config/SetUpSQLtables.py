from Logger import *

create_trade_table = """
CREATE TABLE IF NOT EXISTS trades(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    setting TEXT,
    entry_time TEXT,
    position_side TEXT,
    entry_order_amount TEXT,
    position_size TEXT,
    position_size_usdt TEXT,
    average_entry_price TEXT,
    exit_time TEXT,
    exit_amount TEXT,
    average_exit_price TEXT,
    raw_pnl TEXT,
    raw_pnl_percentage TEXT,
    fee_BNB TEXT,
    fee_USDT TEXT,
    funding_fees TEXT,
    pnl_percentage_with_fees TEXT,
    pnl_with_fees TEXT,
    at_bid_ask_post_only_entry TEXT,
    if_market_open_avg_price TEXT,
    if_market_open_slippage TEXT,
    if_failed_entry_missed_gain_percentage	TEXT,
    at_bid_ask_post_only_exit_count INTEGER,
    at_bid_ask_post_only_exit_failed_count INTEGER,
    if_market_close_avg_price TEXT,
    if_market_close_pnl TEXT,
    if_market_close_pnl_percentage TEXT,
    if_market_close_slippage TEXT,
    if_market_close_fees TEXT,
    max_unrealised_loss TEXT,
    wallet_balance TEXT
);
"""

new_trade = f"""
INSERT INTO
    trades (symbol, exit_amount)
VALUES
    ('BTCUSDT', '12.3')
"""

execute_query(create_connection(DB_LOG_PATH), create_trade_table)

create_internal_wallet_table = """
CREATE TABLE IF NOT EXISTS internal_wallets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT,
    setting TEXT,
    internal_wallet TEXT,
    internal_wallet_max_drawdown TEXT,
    last_trade_id INTEGER,
    last_update_time TEXT
);
"""

execute_query(create_connection(DB_LOG_PATH), create_internal_wallet_table)
