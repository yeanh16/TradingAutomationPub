from decimal import Decimal, DivisionByZero
import math
import time
import re
from datetime import datetime

DATETIME_STRING_FORMAT = '%d/%m/%Y %H:%M:%S'
CAPITAL_DATETIME_STRING_FORMAT = '%Y-%m-%dT%H:%M:%S'
ARG_FILE_REGEX = r'^[^#]?@?(args_.*\.txt)(( ?-[a-z])*)?'


def get_current_datetime_string():
    return datetime.now().strftime(DATETIME_STRING_FORMAT)


def get_datetime_from_string(string):
    return datetime.strptime(string, DATETIME_STRING_FORMAT)


def calculate_pnl_percentage(entry_price, exit_price, side):
    """
    returns float. 1.0 = 100%
    :param entry_price:
    :param exit_price:
    :param side: "long" or "short"
    :return: pnl percentage as a float
    """
    try:
        if side == "long":
            return float((Decimal(str(exit_price)) / Decimal(str(entry_price))) - 1)
        elif side == "short":
            return float((Decimal(str(entry_price)) - Decimal(str(exit_price))) / Decimal(str(entry_price)))
        raise ValueError("argument 'side' must be 'long' or 'short'")
    except DivisionByZero:
        print(f"ERROR in calculate_pnl_percentage, division by zero")
        return 0


def input_to_percentage(input_float):
    """
    transform a float i.e 1.8 to percentage i.e 0.018
    :param input_float:
    :return: float
    """
    return float(Decimal(str(input_float)) / 100)


def percentage_to_input(percentage):
    """
    transform a percentage i.e. 0.018 to original input float i.e. 1.8
    :param percentage:
    :return: float
    """
    return float(Decimal(str(percentage)) * 100)


def round_interval_down(number, interval: Decimal):
    """
    Given a number, round this number down to the nearest interval
    :param interval: Decimal
    :returns answer: Decimal
    """
    number = Decimal(str(number))
    return interval * Decimal(str(round(math.floor(number / interval))))


def round_interval_up(number, interval: Decimal):
    """
    Given a number, round this number up to the nearest interval
    :param interval: Decimal
    :returns answer: Decimal
    """
    number = Decimal(str(number))
    return interval * Decimal(str(round(math.ceil(number / interval))))


def round_interval_nearest(number, interval: Decimal):
    """
    Given a number, round this number to the nearest interval
    :param interval: Decimal
    :returns answer: Decimal
    """
    number = Decimal(str(number))
    return interval * Decimal(str(round(number / interval)))


def add_candles(candles):
    opentime = candles[0][0]
    open = candles[0][1]
    high = max(candles, key=lambda x: float(x[2]))[2]
    low = min(candles, key=lambda x: float(x[3]))[3]
    close = candles[-1][4]
    volume = 0
    for candle in candles:
        volume += Decimal(candle[5])
    closetime = candles[-1][6]
    # There are more fields but these we will ignore:
    # Quote asset volume
    # Number of trades
    # Taker buy base asset volume
    # Taker buy quote asset volume
    # Ignore field.
    return [opentime, open, high, low, close, str(volume), closetime]


def convert_min_to_x_min_candles(candles, x):
    result = []
    for i in range(0, len(candles) - 1, x):
        result.append(add_candles(candles[i:i + x]))
    return result


def get_last_close_price_from_candles(candles):
    if candles:
        latest_candle = candles[-1:][0]
        close = latest_candle[4]
        return float(close)
    return None


def get_position_size(position):
    if position:
        return float(position[0].get('positionAmt'))
    else:
        return 0


def get_entry_price(position):
    if position:
        return float(position[0].get('entryPrice'))
    else:
        return 0


# @tries_wrapper
# def futures_get_margin_balance():
#     account = client.futures_account()
#     margin_balance = account.get("totalMarginBalance")
#     return margin_balance


# @tries_wrapper
# def futures_get_available_balance():
#     balances = client.futures_account_balance()
#     for balance in balances:
#         if balance['asset'] == 'USDT':
#             return balance['withdrawAvailable']
#     return None


def get_order_side(order):
    return order.get("side")


def is_order_filled(order):
    status = order.get("status")
    return status == "FILLED"


def is_order_filled_partial(order):
    status = order.get("status")
    return status == "PARTIALLY_FILLED"


def check_if_candles_are_latest(candles):
    """
    checks if the latest candle from the candles provided is latest
    based on the interval between candles
    :param candles:
    :return: boolean
    """
    if len(candles) < 2:
        raise Exception("Unable to call check_if_candles_are_latest with <2 candles")
    interval = int(candles[-1][0]) - int(candles[-2][0])
    close_time = int(candles[-1][0]) + interval - 1
    current_time = int(time.time() * 1000)
    if current_time <= close_time + 5000:  # add 5 seconds to account for rtt and time outs of receiving new candles
        return True
    else:
        return False


def format_float_in_standard_form(f):
    s = str(f)
    m = re.fullmatch(r'(-?)(\d)(?:\.(\d+))?e([+-]\d+)', s)
    if not m:
        return s
    sign, intpart, fractpart, exponent = m.groups('')
    exponent = int(exponent) + 1
    digits = intpart + fractpart
    if exponent < 0:
        return sign + '0.' + '0' * (-exponent) + digits
    exponent -= len(digits)
    return sign + digits + '0' * exponent + '.0'


def binance_intervals_to_seconds(interval):
    """
    translates binance api intervals in string to intervals in seconds (for ftx api)
    """
    if interval == "5m":
        return int(300)
    elif interval == "1m":
        return int(60)
    elif interval == "3m":
        return int(180)
    elif interval == "15m":
        return int(900)
    elif interval == "1h" or interval == "1H":
        return int(3600)
    elif interval == "1d" or interval == "1D":
        return int(86400)
    else:
        raise Exception("binance_intervals_to_seconds not implemented requested interval conversion!")


def binance_intervals_to_bybit_intervals(interval):
    if interval == "1m":
        bybit_interval = 1
    elif interval == "3m":
        bybit_interval = 3
    elif interval == "5m":
        bybit_interval = 5
    elif interval == "15m":
        bybit_interval = 15
    elif interval == "30m":
        bybit_interval = 30
    elif interval == "1h" or interval == "1H":
        bybit_interval = 60
    elif interval == "1d" or interval == "1D":
        bybit_interval = "D"
    else:
        raise Exception("Bybit binance_intervals_to_bybit_intervals not implemented requested interval conversion!")
    return bybit_interval


def binance_intervals_to_kucoin_intervals(interval):
    if interval == "1m":
        bybit_interval = 1
    elif interval == "3m":
        bybit_interval = 3
    elif interval == "5m":
        bybit_interval = 5
    elif interval == "15m":
        bybit_interval = 15
    elif interval == "30m":
        bybit_interval = 30
    elif interval == "1h" or interval == "1H":
        bybit_interval = 60
    elif interval == "1d" or interval == "1D":
        bybit_interval = 1440
    else:
        raise Exception("Bybit binance_intervals_to_bybit_intervals not implemented requested interval conversion!")
    return bybit_interval


def binance_intervals_to_mexc_intervals(interval):
    if interval == "1m":
        mexc_interval = "Min1"
    elif interval == "3m":
        mexc_interval = "Min3"
    elif interval == "5m":
        mexc_interval = "Min5"
    elif interval == "15m":
        mexc_interval = "Min15"
    elif interval == "30m":
        mexc_interval = "Min30"
    elif interval == "1h" or interval == "1H":
        mexc_interval = "Min60"
    elif interval == "1d" or interval == "1D":
        mexc_interval = "Day1"
    else:
        raise Exception("Mexc binance_intervals_to_mexc_intervals not implemented requested interval conversion!")
    return mexc_interval


def binance_intervals_to_okex_intervals(interval):
    if interval in ['1m', '3m', '5m', '15m', '30m', '1H']:
        okex_interval = interval
    elif interval == "1h":
        okex_interval = "1H"
    elif interval == "1d" or interval == "1D":
        okex_interval = "1Dutc"
    else:
        raise Exception("binance_intervals_to_okex_intervals not implemented requested interval conversion!")
    return okex_interval


def binance_intervals_to_bitrue_intervals(interval):
    if interval == "1m":
        bitrue_interval = "1min"
    elif interval == "5m":
        bitrue_interval = "5min"
    elif interval == "15m":
        bitrue_interval = "15min"
    elif interval == "30m":
        bitrue_interval = "30min"
    elif interval == "1h" or interval == "1H":
        bitrue_interval = "1h"
    elif interval == "1d" or interval == "1D":
        bitrue_interval = "1day"
    elif interval == "1M":
        bitrue_interval = "1month"
    else:
        raise Exception("bitrue API does not support this interval")
    return bitrue_interval


def binance_intervals_to_capital_intervals(interval):
    if interval == "1m":
        capital_interval = "MINUTE"
    elif interval == "5m":
        capital_interval = "MINUTE_5"
    elif interval == "15m":
        capital_interval = "MINUTE_15"
    elif interval == "30m":
        capital_interval = "MINUTE_30"
    elif interval == "1h" or interval == "1H":
        capital_interval = "HOUR"
    elif interval == "1d" or interval == "1D":
        capital_interval = "DAY"
    else:
        raise Exception("CAPITAL not implemented requested interval conversion!")
    return capital_interval


def binance_intervals_to_bingx_intervals(interval):
    if interval == "1m":
        mexc_interval = "1"
    elif interval == "3m":
        mexc_interval = "3"
    elif interval == "5m":
        mexc_interval = "5"
    elif interval == "15m":
        mexc_interval = "15"
    elif interval == "30m":
        mexc_interval = "30"
    elif interval == "1h" or interval == "1H":
        mexc_interval = "60"
    elif interval == "1d" or interval == "1D":
        mexc_interval = "1D"
    else:
        raise Exception("BingX binance_intervals_to_bingx_intervals not implemented requested interval conversion!")
    return mexc_interval


def clean_instrument_name(name: str):
    """
    transforms exchange traded instrument to just the cryptocurreny e.g. LUNCUSDT -> LUNC, 1000XEC-USDT-SWAP -> XEC
    """
    clean_str = name
    clean_str = clean_str.replace('-USDT-SWAP', '')
    clean_str = clean_str.replace('_USDT', '')
    clean_str = clean_str.replace('-USDT', '')
    clean_str = clean_str.replace('-PERP', '')
    clean_str = clean_str.replace('u1000', '')
    clean_str = clean_str.replace('u100', '')
    clean_str = clean_str.replace('1000', '')
    clean_str = clean_str.replace('USDT', '')
    clean_str = clean_str.replace('USD', '')
    return clean_str


def make_cloned_zero_vol_candle(to_clone: list, interval):
    candle = to_clone.copy()
    candle[0] = to_clone[6] + 1
    candle[1] = to_clone[4]
    candle[2] = to_clone[4]
    candle[3] = to_clone[4]
    candle[4] = to_clone[4]
    candle[5] = '0'
    candle[6] = candle[0] + int(binance_intervals_to_seconds(interval)) * 1000 - 1
    candle[7] = '0'
    return candle
