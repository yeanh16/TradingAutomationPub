from time import sleep

from trading_automation.clients.CapitalClient import CapitalClient
from trading_automation.clients.UniversalClient import UniversalClient
from datetime import datetime, timedelta, date
from trading_automation.core.Logger import reverse_readline, readcsv
from trading_automation.core.Utils import binance_intervals_to_seconds, DATETIME_STRING_FORMAT
from decimal import Decimal
import os
import re
from pathlib import Path
from dotenv import load_dotenv, find_dotenv


load_dotenv(find_dotenv())

CAPITALDOTCOM_API_KEY_SECOND = os.environ.get("CAPITALDOTCOM_API_KEY_SECOND")
CAPITALDOTCOM_USERNAME_SECOND = os.environ.get("CAPITALDOTCOM_USERNAME_SECOND")
CAPITALDOTCOM_PASSWORD_SECOND = os.environ.get("CAPITALDOTCOM_PASSWORD_SECOND")

"""
Downloads Klines for all symbols up to the present time. May need to be ran more than once if there are time-out 
failures
"""
EXCHANGES = ["XT", "GATE", "FTX", "BINANCE", "BYBIT", "MEXC"]
EXCHANGE = "BYBIT"
MAX_CANDLES_REQUEST = 1500
CLIENT_TIMEOUT = 5
CLIENT_TRIES = 20
CLIENT = UniversalClient(EXCHANGE, timeout=CLIENT_TIMEOUT, tries=CLIENT_TRIES)
EXCLUSIVE_START_TIME_EXCHANGES = ["OKEX", "KUCOIN"]  # exchanges where when requesting kline data and specifying the start time, the first kline where start time specified is excluded is returned
RECENT_ONLY_CANDLES_EXCHANGES = ["OKEX", "KUCOIN", "BITRUE"]  # exchanges where only the most recent kline data is available


def get_intervals(exchange=EXCHANGE):
    if "BINANCE" in exchange or exchange == "BYBIT":
        INTERVALS = ["1m", "3m", "5m", "15m", '1h', '1d']
    elif exchange == "OKEX":
        INTERVALS = ["1m", "3m", "5m", "15m", '1H', '1d']
    elif exchange in ["FTX", "GATE", "MEXC", "KUCOIN", "PHEMEX", "BITRUE", "BINGX", "XT"]:
        INTERVALS = ["1m", "5m", "15m", '1h', '1d']
    elif exchange in ["CAPITAL"]:
        INTERVALS = ['1h', '1d']
    return INTERVALS


def get_max_candles_request(exchange=EXCHANGE):
    if exchange == "OKEX":
        return 100
    elif exchange == "BYBIT" or exchange == "KUCOIN":
        return 200
    elif exchange == "CAPITAL":
        return 1000
    elif exchange in ["PHEMEX"]:
        return 1000
    elif exchange in ["BITRUE"]:
        return 300
    elif exchange in ["BINGX"]:
        return 1440
    elif exchange in ['XT']:
        return 1500
    else:
        return MAX_CANDLES_REQUEST


def get_symbols_list(client=CLIENT):
    symbols = []
    instruments = client.futures_exchange_info()
    for instrument in instruments:
        symbols.append(instrument.get("symbol"))
        # if "CAPITAL" in client.exchange:
        #     # add extra symbol directory to store ask prices as well
        #     symbols.append(instrument.get("symbol") + "_ASK")
    return symbols


def run(exchange, chunking=False, print_process=False, intervals_list=None):
    client = UniversalClient(exchange, timeout=CLIENT_TIMEOUT, tries=CLIENT_TRIES)
    if "CAPITAL" in exchange:
        # change api for CAPITAL to use secondary dormant account for kline data to free up rate limit on active account
        client.client_capital = CapitalClient(api_key=CAPITALDOTCOM_API_KEY_SECOND, username=CAPITALDOTCOM_USERNAME_SECOND, password=CAPITALDOTCOM_PASSWORD_SECOND, timeout=CLIENT_TIMEOUT, second_account=True)
    client.logger.writeline(f"{client.exchange} Downloading Klines")
    symbols = get_symbols_list(client)
    if intervals_list is None:
        intervals = get_intervals(client.exchange)
    else:
        intervals = intervals_list
    current_time = datetime.now().timestamp() * 1000
    for symbol in symbols:
        for interval in intervals:
            try:
                latest_chunking_path = f"klines/{client.exchange}/{get_start_of_week_current().strftime('%Y%m%d')}/{symbol}/{symbol}_{interval}.csv"
                previous_week_chunking_path = f"klines/{client.exchange}/{(get_start_of_week_current()-timedelta(days=7)).strftime('%Y%m%d')}/{symbol}/{symbol}_{interval}.csv"
                if chunking and Path(latest_chunking_path).is_file():
                    last_candle_on_file = next(reverse_readline(latest_chunking_path)).split(",")
                elif chunking and Path(previous_week_chunking_path).is_file():
                    last_candle_on_file = next(reverse_readline(previous_week_chunking_path)).split(",")
                else:
                    last_candle_on_file = next(reverse_readline(f"klines/{client.exchange}/{symbol}/{symbol}_{interval}.csv")).split(",")
            except StopIteration:
                last_candle_on_file = None
            if last_candle_on_file:
                startTime = int(last_candle_on_file[6]) + 1  # last_candle_on_file[6] is the previous candle's endTime, +1 to get new startTime
                if client.exchange in EXCLUSIVE_START_TIME_EXCHANGES:
                    startTime -= 1  # OKEX, KUCOIN is startTime exclusive
            elif client.exchange in RECENT_ONLY_CANDLES_EXCHANGES:
                startTime = round(current_time - binance_intervals_to_seconds(interval) * 1000 * 1439)
            else:
                startTime = 1672531200000  # 1627781246000  # Sunday, August 1, 2021 1:27:26 UTC
            if startTime < current_time:
                if print_process:
                    print(f"Downloading klines for {symbol} {interval}")
                max_candles = get_max_candles_request(client.exchange)
                current_time = round(datetime.now().timestamp() * 1000)
                stopSignal = False
                while not stopSignal:
                    endtime = startTime + binance_intervals_to_seconds(interval) * 1000 * max_candles - 1
                    if endtime > current_time:
                        endtime = current_time
                    candles = client.futures_get_candlesticks(symbol, interval=interval, limit=max_candles,
                                                                    startTime=startTime,
                                                                    endTime=endtime)
                    # print(f'client.futures_get_candlesticks("{symbol}", interval="{interval}", limit={max_candles}, startTime={startTime}, endTime={endtime}): {candles}')
                    if isinstance(candles, tuple):
                        # if result is tuple (ask and bid data) needs to be handled accordingly
                        candles_tuple = candles
                        bid_flag = True
                        for candles in candles_tuple:
                            if not bid_flag:
                                symbol_name = symbol + "_ASK"
                            else:
                                symbol_name = symbol
                                bid_flag = False
                            if candles and len(candles) > 1:
                                if not chunking:
                                    last_candle_endTime = candles[-1][6]
                                    if last_candle_endTime > current_time:
                                        # this means that we are on the current (incomplete) candle so should not write it down and finish loop
                                        candles = candles[:-1]
                                        stopSignal = True
                                    if last_candle_on_file is not None and "OKEX" in client.exchange and startTime + 1 != candles[0][0]:
                                        # if running OKEX locally, make sure that the candle will fit sequentially to not have gaps if missed
                                        # a period of not running on local machine. The gaps can be filled from server files using recombine_chunking
                                        # as normal
                                        print(
                                            f"WARNING: OKEX {symbol}_{interval} next candle does not fit sequentially! {startTime + 1} api start time: {candles[0][0]}")
                                        break
                                    client.logger.writecsvlines(lines=candles,
                                                                path=f"klines/{client.exchange}/{symbol_name}/{symbol_name}_{interval}.csv")
                                    startTime = last_candle_endTime + 1
                                    if client.exchange in EXCLUSIVE_START_TIME_EXCHANGES:  # exclusive start time exchanges go here
                                        startTime -= 1
                                else:
                                    first_candle_startTime = candles[0][0]
                                    week_beginning = get_start_of_week(datetime.fromtimestamp(first_candle_startTime / 1000))
                                    last_candle_endTime = candles[-1][6]
                                    if last_candle_endTime > current_time:
                                        # this means that we are on the current (incomplete) candle so should not write it down and finish loop
                                        candles = candles[:-1]
                                        stopSignal = True
                                    if (week_beginning + timedelta(days=7)).timestamp() < int(last_candle_endTime / 1000):
                                        # part of data needs to go another week's file
                                        # handle this naively, go through each candle separately and write them one by one
                                        for candle in candles:
                                            week_beginning_for_candle = get_start_of_week(
                                                datetime.fromtimestamp(candle[0] / 1000)).strftime('%Y%m%d')
                                            client.logger.writecsvlines(lines=[candle],
                                                                        path=f"klines/{client.exchange}/{week_beginning_for_candle}/{symbol_name}/{symbol_name}_{interval}.csv")
                                    else:
                                        client.logger.writecsvlines(lines=candles,
                                                                    path=f"klines/{client.exchange}/{week_beginning.strftime('%Y%m%d')}/{symbol_name}/{symbol_name}_{interval}.csv")
                                    startTime = last_candle_endTime + 1
                                    if client.exchange in EXCLUSIVE_START_TIME_EXCHANGES:  # exclusive start time exchanges go here
                                        startTime -= 1
                            else:
                                startTime = startTime + binance_intervals_to_seconds(interval) * 1000 * max_candles
                                if startTime > current_time:
                                    stopSignal = True
                    else:
                        if candles and len(candles) > 1:
                            if not chunking:
                                last_candle_endTime = candles[-1][6]
                                if last_candle_endTime > current_time:
                                    # this means that we are on the current (incomplete) candle so should not write it down and finish loop
                                    candles = candles[:-1]
                                    stopSignal = True
                                if last_candle_on_file is not None and "OKEX" in client.exchange and startTime + 1 != \
                                        candles[0][0]:
                                    # if running OKEX locally, make sure that the candle will fit sequentially to not have gaps if missed
                                    # a period of not running on local machine. The gaps can be filled from server files using recombine_chunking
                                    # as normal
                                    print(
                                        f"WARNING: OKEX {symbol}_{interval} next candle does not fit sequentially! last candle on file start time {int(last_candle_on_file[0])} api start time: {candles[0][0]}")
                                    # break
                                if last_candle_on_file is not None:
                                    while len(candles) >= 1 and int(last_candle_on_file[0]) >= int(candles[0][0]):
                                        if print_process:
                                            print(
                                                f"WARNING: {symbol}_{interval} next candle start time is before or same as the last candle start time on file! last candle on file start time {int(last_candle_on_file[0])} api start time: {candles[0][0]}, trimming first candle from api")
                                        candles = candles[1:]
                                if len(candles) > 1:
                                    client.logger.writecsvlines(lines=candles,
                                                                path=f"klines/{client.exchange}/{symbol}/{symbol}_{interval}.csv")
                                    last_candle_on_file = candles[-1]
                                else:
                                    stopSignal = True
                                startTime = last_candle_endTime + 1
                                if client.exchange in EXCLUSIVE_START_TIME_EXCHANGES:  # exclusive start time exchanges go here
                                    startTime -= 1
                            else:
                                first_candle_startTime = candles[0][0]
                                week_beginning = get_start_of_week(
                                    datetime.fromtimestamp(first_candle_startTime / 1000))
                                last_candle_endTime = candles[-1][6]
                                if last_candle_endTime > current_time:
                                    # this means that we are on the current (incomplete) candle so should not write it down and finish loop
                                    candles = candles[:-1]
                                    stopSignal = True
                                if (week_beginning + timedelta(days=7)).timestamp() < int(last_candle_endTime / 1000):
                                    # part of data needs to go another week's file
                                    # handle this naively, go through each candle separately and write them one by one
                                    for candle in candles:
                                        week_beginning_for_candle = get_start_of_week(
                                            datetime.fromtimestamp(candle[0] / 1000)).strftime('%Y%m%d')
                                        client.logger.writecsvlines(lines=[candle],
                                                                    path=f"klines/{client.exchange}/{week_beginning_for_candle}/{symbol}/{symbol}_{interval}.csv")
                                else:
                                    client.logger.writecsvlines(lines=candles,
                                                                path=f"klines/{client.exchange}/{week_beginning.strftime('%Y%m%d')}/{symbol}/{symbol}_{interval}.csv")
                                startTime = last_candle_endTime + 1
                                if client.exchange in EXCLUSIVE_START_TIME_EXCHANGES:  # exclusive start time exchanges go here
                                    startTime -= 1
                        else:
                            startTime = startTime + binance_intervals_to_seconds(interval) * 1000 * max_candles
                            if startTime > current_time:
                                stopSignal = True


def check_candles_consistency(exchange):
    client = UniversalClient(exchange)
    symbols = get_symbols_list(client)
    intervals = get_intervals(client.exchange)
    for symbol in symbols:
        for interval in intervals:
            print(f"Checking {symbol}_{interval}.csv")
            candles = readcsv(f"klines/{client.exchange}/{symbol}/{symbol}_{interval}.csv")
            if not candles:
                continue
            last_candle = candles[-1]
            for i in range(len(candles)-1, 0, -1):
                next_candle = candles[i-1]
                startTime = int(next_candle[0])
                last_candle_start_time = int(last_candle[0])
                # print(f"{last_candle_start_time} {startTime}")
                if startTime != last_candle_start_time - binance_intervals_to_seconds(interval) * 1000:
                    print(f"Inconsistency found for {symbol}_{interval}.csv at {last_candle_start_time}")
                last_candle = next_candle


def add_usd_volume_column(client=CLIENT):
    symbols = get_symbols_list(client)
    intervals = get_intervals(client.exchange)
    for symbol in symbols:
        for interval in intervals:
            print(f"Rewriting {symbol}_{interval}.csv")
            path = f"klines/{client.exchange}/{symbol}/{symbol}_{interval}.csv"
            candles = readcsv(path)
            new_candles = []
            for kline in candles:
                if len(kline) < 8:
                    kline.append((round(Decimal(kline[5])*client.precisionQuantityDict[symbol] * ((Decimal(kline[2])+Decimal(kline[3]))/2), 2)))
                new_candles.append(kline)
            os.remove(path)
            client.logger.writecsvlines(new_candles, path=path)


def kucoin_fill_in_kline_gaps():
    """
    to run this function you need to do the following first:
    delete all symbol master files
    run recombine_chunking with sequential_check = False
    """
    client = UniversalClient("KUCOIN")
    path = f"klines/KUCOIN"
    symbols = [f.name for f in os.scandir(path) if f.is_dir() and "20" not in f.name]
    intervals = get_intervals("KUCOIN")
    for symbol in symbols:
        for interval in intervals:
            print(f"Rewriting {symbol}_{interval}.csv")
            path = f"klines/KUCOIN/{symbol}/{symbol}_{interval}.csv"
            candles = readcsv(path)
            new_candles = []
            for i in range(len(candles)-1):
                current_candle = candles[i]
                new_candles.append(current_candle)
                current_candle_end_time = int(current_candle[6])
                next_candle_open_time = int(candles[i+1][0])
                while current_candle_end_time + 1 != next_candle_open_time:
                    # print(f"{current_candle_end_time} {next_candle_open_time}")
                    next_candle_end_time = int(current_candle_end_time + 1) + int(binance_intervals_to_seconds(interval)) * 1000 - 1
                    new_candles.append([current_candle_end_time + 1,
                                        current_candle[4],
                                        current_candle[4],
                                        current_candle[4],
                                        current_candle[4],
                                        "0",
                                        next_candle_end_time,
                                        "0"])
                    current_candle_end_time = next_candle_end_time
            os.remove(path)
            client.logger.writecsvlines(new_candles, path=path)


def create_combined_ask_bid_candles(exchange="CAPITAL"):
    client = UniversalClient(exchange)
    path = f"klines/{exchange}"
    symbols = [f.name for f in os.scandir(path) if f.is_dir() and "_ASK" not in f.name and "_COMBINED" not in f.name]
    intervals = get_intervals(exchange)
    for symbol in symbols:
        for interval in intervals:
            print(f"Combining {symbol}_{interval}.csv")
            bids_path = f"klines/{exchange}/{symbol}/{symbol}_{interval}.csv"
            asks_path = f"klines/{exchange}/{symbol}_ASK/{symbol}_ASK_{interval}.csv"
            bid_candles = readcsv(bids_path)
            ask_candles = readcsv(asks_path)
            new_candles = []
            bid_candle_tracker = 0
            ask_candle_tracker = 0
            for i in range(max(len(bid_candles), len(ask_candles))):
                try:
                    if int(bid_candles[bid_candle_tracker][0]) != int(ask_candles[ask_candle_tracker][0]):
                        if int(bid_candles[bid_candle_tracker][0]) < int(ask_candles[ask_candle_tracker][0]):
                            bid_candle_tracker += 1
                        else:
                            ask_candle_tracker += 1
                        continue
                    if float(bid_candles[bid_candle_tracker][1]) > float(bid_candles[bid_candle_tracker][4]):
                        red_candle = True
                    else:
                        red_candle = False
                    combined_open_price = ask_candles[ask_candle_tracker][1] if red_candle else bid_candles[bid_candle_tracker][1]
                    combined_close_price = bid_candles[bid_candle_tracker][4] if red_candle else ask_candles[ask_candle_tracker][4]
                    combined_high_price = str(max(float(ask_candles[ask_candle_tracker][2]), float(bid_candles[bid_candle_tracker][2])))
                    combined_low_price = str(min(float(ask_candles[ask_candle_tracker][3]), float(bid_candles[bid_candle_tracker][3])))
                    new_candle = [bid_candles[bid_candle_tracker][0],
                                  combined_open_price,
                                  combined_high_price,
                                  combined_low_price,
                                  combined_close_price,
                                  bid_candles[bid_candle_tracker][5],
                                  bid_candles[bid_candle_tracker][6]]
                    new_candles.append(new_candle)
                    bid_candle_tracker += 1
                    ask_candle_tracker += 1
                except IndexError as e:
                    print(f'Index error {e}! {symbol} {interval} bid_candle_tracker {bid_candle_tracker} ask_candle_tracker {ask_candle_tracker}')
                    break
            combined_candles_path = f"klines/{exchange}/{symbol}_COMBINED/{symbol}_COMBINED_{interval}.csv"
            client.logger.writecsvlines(new_candles, path=combined_candles_path, write_mode="w")


def run_all(exchanges=EXCHANGES):
    for exchange in exchanges:
        print(f"{exchange} downloading klines")
        run(exchange)
    print("Complete")


def get_start_of_week_current():
    """
    Gets datetime of the week beginning for current time
    Sunday midnight (Saturday evening) is new week
    :return: datetime object
    """
    today = datetime.combine(date.today(), datetime.min.time())
    return today - timedelta(days=(today.weekday() + 1) % 7)


def get_start_of_week(dt: datetime):
    """
    Gets datetime of the week beginning for the datetime dt provided
    Sunday midnight (Saturday evening) is new week
    :return: datetime object
    """
    day = datetime.combine(dt.date(), datetime.min.time())
    return day - timedelta(days=(day.weekday() + 1) % 7)


def recombine_chunking(exchange, sequential_check=True):
    client = UniversalClient(exchange)
    path = f"klines/{exchange}"
    list_subfolders = [f.name for f in os.scandir(path) if f.is_dir()]
    chunking_date_files = [file for file in list_subfolders if re.fullmatch(r"20\d*", file)]
    chunking_date_files.sort()
    for date_file in chunking_date_files:
        path = f"klines/{exchange}/{date_file}"
        symbols = [f.name for f in os.scandir(path) if f.is_dir()]
        for symbol in symbols:
            path = f"klines/{exchange}/{date_file}/{symbol}"
            csv_files = [f.name for f in os.scandir(path)]
            for csv in csv_files:
                master_csv_path = f"klines/{exchange}/{symbol}/{csv}"
                chunked_candles = readcsv(f"klines/{exchange}/{date_file}/{symbol}/{csv}")
                try:
                    updated = False
                    last_candle = next(reverse_readline(master_csv_path)).split(",")
                    if int(last_candle[0]) >= int(chunked_candles[-1][0]):
                        continue
                    elif not sequential_check or (int(last_candle[0]) < int(chunked_candles[0][0]) and int(last_candle[6])+1 == int(chunked_candles[0][0])):
                        client.logger.writecsvlines(chunked_candles, master_csv_path)
                        updated = True
                    else:
                        # go through each candle in chunked_candles until it's the next candle to be added to master csv file then write
                        for i in range(len(chunked_candles)-1):
                            if int(chunked_candles[i][0]) == int(last_candle[6])+1:
                                client.logger.writecsvlines(chunked_candles[i:], master_csv_path)
                                updated = True
                                break
                    if not updated:
                        print(f"WARNING: unable to update '{master_csv_path}' as chunked data from 'klines/{exchange}/{date_file}/{symbol}/{csv}' does not fit sequentially")
                except StopIteration:
                    client.logger.writecsvlines(chunked_candles, master_csv_path)


def run_capital():
    try:
        run("CAPITAL", print_process=True)
    except Exception as e:
        if "does not exist" in str(e):
            symbol_name = re.search(r"CAPITAL epic '(\S*)' does not exist", str(e)).group(1)
            print(f"Removing {symbol_name} from capital_instruments.txt")
            with open(os.path.realpath(__file__).replace('DownloadKlinesOneTime.py', "") + 'capital_instruments.txt', mode='r') as f:
                lines = f.readlines()
                symbols_list = [line.strip() for line in lines]
            symbols_list = list(set(symbols_list))
            symbols_list.sort()
            symbols_list.remove(symbol_name)
            with open('capital_instruments.txt', mode='w') as f:
                for symbol in symbols_list:
                    f.write(symbol + '\n')
        raise e

# # The following should be run on server to download candles where very old historical data is not given by API
# if __name__ == '__main__':
#     while True:
#         try:
#             run("OKEX", chunking=True)
#         except Exception as e:
#             print(f'{datetime.now()} DownloadKlinesOneTime ERROR: {e}')
#         try:
#             run("KUCOIN", chunking=True)
#         except Exception as e:
#             print(f'{datetime.now()} DownloadKlinesOneTime ERROR: {e}')
#         try:
#             run("BITRUE", chunking=True)
#         except Exception as e:
#             print(f'{datetime.now()} DownloadKlinesOneTime ERROR: {e}')
#         try:
#             run("BINGX", chunking=True)
#         except Exception as e:
#             print(f'{datetime.now()} DownloadKlinesOneTime ERROR: {e}')
#         sleep(3600)
