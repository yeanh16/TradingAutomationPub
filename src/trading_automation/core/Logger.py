import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
import csv
from decimal import Decimal
import sqlite3
from sqlite3 import Error
import re
from typing import Optional

from trading_automation.core.Utils import (
    DATETIME_STRING_FORMAT,
    get_current_datetime_string,
    get_datetime_from_string,
    round_interval_nearest,
)
from trading_automation.clients.DiscordClient import DiscordClient, DiscordNotificationService
from trading_automation.logging.config import get_logger, log_event

DB_LOG_PATH = str(Path(__file__).resolve().parents[2] / "logs" / "trades.sqlite")
LOG_PATH = str(Path(__file__).resolve().parents[2] / "logs" / "log.txt")

def create_connection(path):
    connection = None
    try:
        connection = sqlite3.connect(path)
        # print("Connection to SQLite DB successful")
    except Error as e:
        print(f"{get_current_datetime_string()} The error '{e}' occurred")

    return connection


def execute_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        # print(f"{query} \n Query executed successfully")
        return cursor
    except Error as e:
        print(f"{get_current_datetime_string()} The error '{e}' occurred for query \n {query}")


def execute_read_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        result = cursor.fetchall()
        return result
    except Error as e:
        print(f"{get_current_datetime_string()} The error '{e}' occurred for read query \n {query}")


def reverse_readline(filename, buf_size=8192):
    """A generator that returns the lines of a file in reverse order"""
    try:
        with open(filename) as fh:
            segment = None
            offset = 0
            fh.seek(0, os.SEEK_END)
            file_size = remaining_size = fh.tell()
            while remaining_size > 0:
                offset = min(file_size, offset + buf_size)
                fh.seek(file_size - offset)
                buffer = fh.read(min(remaining_size, buf_size))
                remaining_size -= buf_size
                lines = buffer.split('\n')
                # The first line of the buffer is probably not a complete line so
                # we'll save it and append it to the last line of the next buffer
                # we read
                if segment is not None:
                    # If the previous chunk starts right from the beginning of line
                    # do not concat the segment to the last line of new chunk.
                    # Instead, yield the segment first
                    if buffer[-1] != '\n':
                        lines[-1] += segment
                    else:
                        yield segment
                segment = lines[0]
                for index in range(len(lines) - 1, 0, -1):
                    if lines[index]:
                        yield lines[index]
            # Don't yield None if the file was empty
            if segment is not None:
                yield segment
    except FileNotFoundError:
        return None


def readcsv(path):
    lines = []
    try:
        with open(path, 'r', newline='') as csvfile:
            reader = list(csv.reader(csvfile))
            for row in reader:
                lines.append(row)
            csvfile.close()
        return lines
    except FileNotFoundError:
        return []


class Logger:
    def __init__(
        self,
        client,
        logpath: str = LOG_PATH,
        print_console: bool = True,
        discord_service: Optional[DiscordNotificationService] = None,
    ) -> None:
        self.logpath = logpath
        self.tradelog_path = DB_LOG_PATH
        self.print_console = print_console
        self.client = client
        logger_name = "trading_automation"
        if hasattr(client, "exchange") and client.exchange:
            logger_name = f"trading_automation.{client.exchange}"
        self._logger = get_logger(logger_name)
        self.discord_client = None
        if discord_service is not None:
            discord_service.start()
            self.discord_client = DiscordClient(service=discord_service)
        if logpath:
            try:
                os.makedirs(os.path.dirname(logpath), exist_ok=True)
            except OSError as e:
                print("Creation of the directory %s failed" % e)

        if logpath and not os.path.exists(self.logpath):
            with open(self.logpath, "w"):
                pass

        try:
            os.makedirs(os.path.dirname(self.tradelog_path), exist_ok=True)
        except OSError as e:
            print("Creation of the directory %s failed" % e)
        if not os.path.exists(self.tradelog_path):
            with open(self.logpath, "w"):
                pass

    def writeline(self, line, discord_channel_id=None):
        try:
            os.makedirs(os.path.dirname(self.logpath), exist_ok=True)
        except OSError as e:
            print("Creation of the directory %s failed" % e)

        if not os.path.exists(self.logpath):
            with open(self.logpath, "w"):
                pass
        file = open(self.logpath, "a")
        exchange_name = getattr(self.client, "exchange", "") if self.client is not None else ""
        log_event(self._logger, logging.INFO, line, exchange=exchange_name)
        log_entry = f"{get_current_datetime_string()} {exchange_name} {line}"
        if self.print_console:
            print(log_entry)
        with file:
            file.write(f"{log_entry}\n")
        file.close()

        if discord_channel_id and self.discord_client:
            self.discord_client.send_message(log_entry, channel_id=discord_channel_id)

    def readcsv(self, path):
        lines = []
        try:
            with open(path, 'r', newline='') as csvfile:
                reader = list(csv.reader(csvfile))
                for row in reader:
                    lines.append(row)
                csvfile.close()
            return lines
        except FileNotFoundError:
            return []

    def readlastcsvlines(self, n, path):
        """
        reads the last n number of lines
        """
        lines = []
        try:
            with open(path, 'r', newline='') as csvfile:
                reader = reversed(list(csv.reader(csvfile)))
                for row in reader:
                    lines.append(row)
                csvfile.close()
            return lines[:n]
        except FileNotFoundError:
            return None

    def writecsvlines(self, lines, path=None, write_mode="a"):
        if path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            except OSError as e:
                print("Creation of the directory %s failed" % e)

            if not os.path.exists(path):
                with open(path, "w"):
                    pass
        else:
            path = self.logpath

        file = open(path, write_mode, newline='')
        csv_writer = csv.writer(file, delimiter=',')
        with file:
            csv_writer.writerows(lines)
        file.close()

    def write_new_trade(self, setting,  position: dict = None, order: dict = None, post_only_entry=False):
        sql_connection = create_connection(self.tradelog_path)
        if position and not post_only_entry:
            if position['positionAmt'][0] == "-":
                position_side = "SHORT"
            else:
                position_side = "LONG"
            time = get_current_datetime_string()
            new_trade = f"""
            INSERT INTO
                trades (symbol, setting, entry_time, average_entry_price, entry_order_amount, position_size, position_size_usdt, position_side)
            VALUES
                ('{position['symbol']}', '{setting}', '{time}', '{position['entryPrice']}', '{abs(Decimal(position['positionAmt']))}', '{position['positionAmt']}', '{str(abs(Decimal(position['entryPrice']) * Decimal(position['positionAmt'])))}', '{position_side}')
            """
        elif position and post_only_entry:
            if position['positionAmt'][0] == "-":
                position_side = "SHORT"
            else:
                position_side = "LONG"
            time = get_current_datetime_string()
            _, avg_price, slippage = self.client.market_open_avg_price_and_slippage(order['symbol'], position_side, Decimal(order['price']) * Decimal(order['origQty']))
            new_trade = f"""
            INSERT INTO
                trades (symbol, setting, entry_time, average_entry_price, entry_order_amount, position_size, position_size_usdt, position_side, at_bid_ask_post_only_entry, if_market_open_avg_price, if_market_open_slippage)
            VALUES
                ('{position['symbol']}', '{setting}', '{time}', '{position['entryPrice']}', '{abs(Decimal(position['positionAmt']))}', '{position['positionAmt']}', '{str(abs(Decimal(position['entryPrice']) * Decimal(position['positionAmt'])))}', '{position_side}', 'TRUE', '{avg_price}', '{slippage}')
            """
        elif order and post_only_entry:
            if order['side'] == "BUY":
                position_side = "LONG"
            else:
                position_side = "SHORT"
            _, avg_price, slippage = self.client.market_open_avg_price_and_slippage(order['symbol'], position_side, Decimal(order['price']) * Decimal(order['origQty']))
            new_trade = f"""
            INSERT INTO
                trades (symbol, setting, entry_order_amount, average_entry_price, position_side, at_bid_ask_post_only_entry, if_market_open_avg_price, if_market_open_slippage)
            VALUES
                ('{order['symbol']}', '{setting}', '{order['origQty']}', '{order['price']}', '{position_side}', 'TRUE', '{avg_price}', '{slippage}')
            """
        elif order and not post_only_entry:
            # when an order is provided with not post_only_entry that means a partial filled entry order needs to be logged as a new trade
            if order['side'] == "BUY":
                position_side = "LONG"
            else:
                position_side = "SHORT"
            time = get_current_datetime_string()
            new_trade = f"""
            INSERT INTO
                trades (symbol, entry_time, setting, entry_order_amount, position_size, position_side, position_size_usdt, average_entry_price)
            VALUES
                ('{order['symbol']}', '{time}', '{setting}', '{order['origQty']}', '{'-' if position_side=='SHORT' else ''}{order['executedQty']}', '{position_side}', '{str(abs(Decimal(order['avgPrice']) * Decimal(order['executedQty'])))}', '{order['avgPrice']}')
            """
        record_id = execute_query(sql_connection, new_trade).lastrowid
        internal_wallet_record = self.get_internal_wallet_record(setting)
        update_last_trade_id_query = f"""
        UPDATE
            internal_wallets
        SET
            last_trade_id = {record_id}
        WHERE
            id = {internal_wallet_record[0]}
        """
        execute_query(sql_connection, update_last_trade_id_query)
        sql_connection.close()
        return record_id

    def update_trade_entry(self, tid: int, position: dict):
        if not tid:
            print("ERROR: update_trade_entry called with not tid")
            return
        sql_connection = create_connection(self.tradelog_path)
        time = get_current_datetime_string()
        update_trade = f"""
        UPDATE
            trades
        SET
            entry_time = '{time}',
            average_entry_price = '{position['entryPrice']}',
            position_size = '{position['positionAmt']}',
            position_size_usdt = '{str(abs(Decimal(position['entryPrice']) * Decimal(position['positionAmt'])))}'
        WHERE
            id = {tid}
        """
        execute_query(sql_connection, update_trade)
        sql_connection.close()

    def close_trade_update(self, tid: int, order: dict):
        if not tid:
            print("ERROR: close_trade_update called with not tid")
            return
        sql_connection = create_connection(self.tradelog_path)
        time = get_current_datetime_string()
        trade_record = execute_read_query(sql_connection, f"SELECT * FROM trades WHERE id={tid}")[0]
        symbol = trade_record[1]
        initial_position_size = abs(Decimal(trade_record[6]))
        # -------- calculate exit_amount and average_exit_price manually
        exit_amount = trade_record[10]
        if not exit_amount:
            exit_amount = 0
        else:
            exit_amount = Decimal(exit_amount)
        average_exit_price = trade_record[8]
        if not average_exit_price:
            average_exit_price = 0
        else:
            average_exit_price = Decimal(average_exit_price)
        if Decimal(order['origQty']) == initial_position_size:
            new_exit_amount = Decimal(order['executedQty'])
            new_average_exit_price = Decimal(order['avgPrice'])
        elif Decimal(order['origQty']) + exit_amount == initial_position_size:
            # the above case happens when an exit trade is spread over multiple orders
            new_exit_amount = initial_position_size - (Decimal(order['origQty']) - Decimal(order['executedQty']))
            new_average_exit_price = round_interval_nearest((exit_amount * average_exit_price + Decimal(order['executedQty']) * Decimal(order['avgPrice'])) / new_exit_amount, self.client.precisionPriceDict.get(symbol))
        elif Decimal(order['origQty']) + exit_amount > initial_position_size:
            # the above case happens when an exit trade is spread over multiple orders and is partially filled on the last trade twice
            new_exit_amount = initial_position_size - (Decimal(order['origQty']) - Decimal(order['executedQty']))
            new_filled_amount = new_exit_amount - exit_amount
            new_average_exit_price = round_interval_nearest((exit_amount * average_exit_price + new_filled_amount * Decimal(order['avgPrice'])) / new_exit_amount, self.client.precisionPriceDict.get(symbol))
            self.client.logger.writeline(f"{symbol} DEBUG: new_exit_amount {new_exit_amount} new_filled_amount {new_filled_amount} new_average_exit_price {new_average_exit_price} exit_amount {exit_amount} average_exit_price {average_exit_price}")
        else:
            # This case happens when an error happens such that a previous trade was not logged so the
            # above sums for each case is not possible. If there was no errors then the above cases
            # should catch all eventualities
            self.client.logger.writeline(f"{symbol} ERROR: unable to complete trade log")
            sql_connection.close()
            return
        # /---------- calcs done
        if abs(new_exit_amount) == abs(initial_position_size):
            # calc pnl and fully close trade as we have closed position entirely
            side = trade_record[4]
            initial_position_size_usdt = Decimal(trade_record[7])
            final_position_size_usdt = new_exit_amount * new_average_exit_price
            average_entry_price = Decimal(trade_record[8])
            if side == "LONG":
                raw_pnl = final_position_size_usdt - initial_position_size_usdt
                raw_pnl_percentage = round(((new_average_exit_price/average_entry_price) - 1) * 100, 3)
            elif side == "SHORT":
                raw_pnl = initial_position_size_usdt - final_position_size_usdt
                raw_pnl_percentage = round((1 - (new_average_exit_price/average_entry_price)) * 100, 3)
            entry_time = trade_record[3]
            ts_entry_time = datetime.strptime(entry_time, DATETIME_STRING_FORMAT).timestamp() * 1000
            interval = re.search("\\d*m", trade_record[2])[0]
            # Need to take off some time to include starting candle. below should be looked at if supporting 2m intervals.
            if interval == "1m":
                ts_entry_time -= 60000
            elif interval == "3m":
                ts_entry_time -= 180000
            elif interval == "5m":
                ts_entry_time -= 300000
            max_unrealised_loss = round(self.client.calculate_max_unrealised_loss_percentage(symbol, ts_entry_time, average_entry_price, side, interval), 3)
            wallet_balance = self.client.futures_get_balance()
            update_trade = f"""
            UPDATE
                trades
            SET
                exit_time = '{time}',
                exit_amount = '{str(new_exit_amount)}',
                average_exit_price = '{str(new_average_exit_price)}',
                raw_pnl = '{str(raw_pnl)}',
                raw_pnl_percentage = '{str(raw_pnl_percentage)}',
                max_unrealised_loss = '{str(max_unrealised_loss)}',
                wallet_balance = '{str(wallet_balance)}'
            WHERE
                id = {tid}
            """
            self.update_last_trade_id(tid, None)
        elif abs(new_exit_amount) != abs(initial_position_size):
            # trade not finished so update time, exit_amount and average_exit_price only
            update_trade = f"""
            UPDATE
                trades
            SET
                exit_time = '{time}',
                exit_amount = '{str(new_exit_amount)}',
                average_exit_price = '{str(new_average_exit_price)}'
            WHERE
                id = {tid}
            """
        execute_query(sql_connection, update_trade)
        sql_connection.close()

    def increase_post_only_exit_count(self, tid: int, position=None):
        if not tid:
            print("ERROR: increase_post_only_exit_count called with not tid")
            return
        sql_connection = create_connection(self.tradelog_path)
        trade_record = execute_read_query(sql_connection, f"SELECT * FROM trades WHERE id={tid}")[0]
        # these need to be adjusted if changes are made to the table
        symbol = trade_record[1]
        exit_count = trade_record[23]
        if exit_count:
            exit_count = int(exit_count) + 1
            update_trade = f"""
            UPDATE
                trades
            SET
                at_bid_ask_post_only_exit_count = {exit_count}
            WHERE
                id = {tid}
            """
        else:
            _, realised_pnl, average_price, slippage = self.client.market_close_now_profit(symbol, position=position)
            update_trade = f"""
            UPDATE
                trades
            SET
                at_bid_ask_post_only_exit_count = 1,
                at_bid_ask_post_only_exit_failed_count = 0,
                if_market_close_avg_price = '{str(average_price)}',
                if_market_close_pnl = '{str(realised_pnl)}',
                if_market_close_slippage = '{str(slippage)}'
            WHERE
                id = {tid}
            """
        execute_query(sql_connection, update_trade)
        sql_connection.close()

    def increase_post_only_exit_failed_count(self, tid: int):
        if not tid:
            print("ERROR: increase_post_only_exit_failed_count called with not tid")
            return
        sql_connection = create_connection(self.tradelog_path)
        trade_record = execute_read_query(sql_connection, f"SELECT * FROM trades WHERE id={tid}")[0]
        # these need to be adjusted if changes are made to the table
        exit_failed_count = trade_record[24]
        update_trade = f"""
        UPDATE
            trades
        SET
            at_bid_ask_post_only_exit_failed_count = {exit_failed_count + 1}
        WHERE
            id = {tid}
        """
        execute_query(sql_connection, update_trade)
        sql_connection.close()

    def trades_log_failed_entry(self, symbol):
        """
        use this to create a dummy entry when a trade has failed to log
        """
        sql_connection = create_connection(self.tradelog_path)
        time = get_current_datetime_string()
        new_trade = f"""
                INSERT INTO
                    trades (symbol, position_side, exit_time)
                VALUES
                    ('{symbol}', 'UNKNOWN', '{time}')
                """
        execute_query(sql_connection, new_trade)
        sql_connection.close()

    def get_internal_wallet_record(self, setting: str):
        """
        Only returns a record if found less than 30 days old
        :return: None or record
        """
        sql_connection = create_connection(self.tradelog_path)
        existing_records = execute_read_query(sql_connection, f"SELECT * FROM internal_wallets WHERE setting = '{setting}'")
        retval = None
        if existing_records:
            if len(existing_records) == 1:
                existing_record = existing_records[0]
            else:
                existing_records.sort(key=lambda x: get_datetime_from_string(x[1]))
                existing_record = existing_records[-1]
            if get_datetime_from_string(existing_record[1]) + timedelta(days=30) > datetime.now():
                retval = existing_record
        sql_connection.close()
        return retval

    def get_internal_wallet_balance_and_drawdown_value_and_last_trade_id(self, setting: str):
        """
        :param setting:
        :return: internal_wallet_value, internal_wallet_max_drawdown_value, last_trade_id
        """
        record = self.get_internal_wallet_record(setting)
        if record:
            return float(record[3]), float(record[4]), int(record[5]) if record[5] is not None else None
        else:
            return None

    def log_internal_wallet(self, setting: str, internal_wallet_value, internal_wallet_max_drawdown_value):
        """
        :param setting: str format of FuturesManager class
        :param internal_wallet_value:
        :param internal_wallet_max_drawdown_value: The value for which the strategy is terminated when internal
        wallet goes below
        :return:
        """
        sql_connection = create_connection(self.tradelog_path)
        existing_record = self.get_internal_wallet_record(setting)
        if existing_record:
            update_record_query = f"""
                UPDATE
                    internal_wallets
                SET
                    internal_wallet = '{str(round(internal_wallet_value,2))}',
                    internal_wallet_max_drawdown = '{str(round(internal_wallet_max_drawdown_value,2))}',
                    last_update_time = '{get_current_datetime_string()}'
                WHERE
                    id = {existing_record[0]}
                """
            execute_query(sql_connection, update_record_query)
        else:
            create_query = f"""
                INSERT INTO
                    internal_wallets (start_time, setting, internal_wallet, internal_wallet_max_drawdown, last_update_time)
                VALUES
                    ('{get_current_datetime_string()}', '{setting}', '{str(round(internal_wallet_value, 2))}', '{str(round(internal_wallet_max_drawdown_value, 2))}', '{get_current_datetime_string()}')
                """
            execute_query(sql_connection, create_query)
        sql_connection.close()

    def update_last_trade_id(self, old_tid, new_tid):
        sql_connection = create_connection(self.tradelog_path)
        if new_tid is None:
            new_tid = 'NULL'
        update_last_trade_id_query = f"""
        UPDATE
            internal_wallets
        SET
            last_trade_id = {new_tid}
        WHERE
            last_trade_id = {old_tid}
        """
        execute_query(sql_connection, update_last_trade_id_query)
        sql_connection.close()
