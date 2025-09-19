import threading
import time
from typing import Optional

from binance.client import Client
from pybit.exceptions import InvalidRequestError, FailedRequestError
# from FtxClient import FtxClient
import sys
from pathlib import Path

# Ensure the 'src' directory is on sys.path when running this module directly
SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trading_automation.core.Logger import Logger
# from MexcClient import MxcClient
import os
from binance.exceptions import BinanceAPIException
from trading_automation.core.Utils import *
from time import sleep
from datetime import datetime, timezone, timedelta
from requests import Timeout
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder, FuturesPriceTriggeredOrder
from gate_api.exceptions import GateApiException
from urllib3.exceptions import MaxRetryError
from trading_automation.core.Utils import binance_intervals_to_seconds
from okex.okexclient import OkexClient
from okex.exceptions import OkexAPIException
import traceback
from trading_automation.clients.BybitClient import BybitClient
# from kucoin_futures.client import Market, User, Trade
import random
from trading_automation.clients.CapitalClient import CapitalClient
# from IgClient import IgClient
from trading_automation.clients.PhemexClient import PhemexClient, PhemexAPIException
from trading_automation.clients.BitrueClient import BitrueClient
from trading_automation.clients.BingxClient import BingxClient, BingxAPIException
import statistics
from trading_automation.clients.XtClient import XtClient, XtAPIException
from trading_automation.clients.order_processors import (
    process_ftx_order_to_binance,
    process_okex_order_to_binance as normalize_okex_order,
    process_gate_order_to_binance as normalize_gate_order,
    process_mexc_order_to_binance as normalize_mexc_order,
    process_bybit_order_to_binance as normalize_bybit_order,
    process_phemex_order_to_binance as normalize_phemex_order,
    process_bingx_order_to_binance as normalize_bingx_order,
)

from trading_automation.config.settings import get_settings
from trading_automation.clients.DiscordClient import DiscordNotificationService

settings = get_settings()

BINANCE_API_KEY = settings.binance_api_key
BINANCE_API_SECRET = settings.binance_api_secret
FTX_API_KEY = settings.ftx_api_key
FTX_API_SECRET = settings.ftx_api_secret
OKEX_API_KEY = settings.okex_api_key
OKEX_API_SECRET = settings.okex_api_secret
OKEX_PASSPHRASE = settings.okex_passphrase
OKEX_API_KEY_SECOND = settings.okex_api_key_second
OKEX_API_SECRET_SECOND = settings.okex_api_secret_second
OKEX_PASSPHRASE_SECOND = settings.okex_passphrase_second
OKEX_API_KEY_DEMO = settings.okex_api_key_demo
OKEX_API_SECRET_DEMO = settings.okex_api_secret_demo
OKEX_PASSPHRASE_DEMO = settings.okex_passphrase_demo
OKEX_POS_MODE = settings.okex_pos_mode
GATEIO_API_KEY = settings.gateio_api_key
GATEIO_API_SECRET = settings.gateio_api_secret
GATEIO_USER_ID = settings.gateio_user_id
GATEIO_API_KEY_SECOND = settings.gateio_api_key_second
GATEIO_API_SECRET_SECOND = settings.gateio_api_secret_second
GATEIO_USER_ID_SECOND = settings.gateio_user_id_second
GATEIO_API_KEY_THIRD = settings.gateio_api_key_third
GATEIO_API_SECRET_THIRD = settings.gateio_api_secret_third
GATEIO_USER_ID_THIRD = settings.gateio_user_id_third
GATEIO_API_KEY_FOURTH = settings.gateio_api_key_fourth
GATEIO_API_SECRET_FOURTH = settings.gateio_api_secret_fourth
GATEIO_USER_ID_FOURTH = settings.gateio_user_id_fourth
BYBIT_API_KEY = settings.bybit_api_key
BYBIT_API_SECRET = settings.bybit_api_secret
BYBIT_API_KEY_SECOND = settings.bybit_api_key_second
BYBIT_API_SECRET_SECOND = settings.bybit_api_secret_second
BYBIT_API_KEY_THIRD = settings.bybit_api_key_third
BYBIT_API_SECRET_THIRD = settings.bybit_api_secret_third
MEXC_API_SECRET = settings.mexc_api_secret
MEXC_API_KEY = settings.mexc_api_key
KUCOIN_API_KEY = settings.kucoin_api_key
KUCOIN_API_SECRET = settings.kucoin_api_secret
KUCOIN_API_PASSPHRASE = settings.kucoin_api_passphrase
IG_API_KEY = settings.ig_api_key
IG_USERNAME = settings.ig_username
IG_PASSWORD = settings.ig_password
IG_API_KEY_DEMO = settings.ig_api_key_demo
IG_USERNAME_DEMO = settings.ig_username_demo
IG_PASSWORD_DEMO = settings.ig_password_demo
CAPITALDOTCOM_API_KEY = settings.capitaldotcom_api_key
CAPITALDOTCOM_USERNAME = settings.capitaldotcom_username
CAPITALDOTCOM_PASSWORD = settings.capitaldotcom_password
PHEMEX_API_ID = settings.phemex_api_id
PHEMEX_API_SECRET = settings.phemex_api_secret
BINGX_API_KEY = settings.bingx_api_key
BINGX_API_SECRET = settings.bingx_api_secret
XT_API_KEY = settings.xt_api_key
XT_API_SECRET = settings.xt_api_secret

DISCORD_ERROR_MESSAGES_CHANNEL_ID = settings.discord_error_messages_channel_id or 0

API0 = 'https://api.binance.{}/api'.format('com')
API1 = 'https://api1.binance.{}/api'.format('com')
API2 = 'https://api2.binance.{}/api'.format('com')
API3 = 'https://api3.binance.{}/api'.format('com')

PRINT_CONSOLE = settings.print_console
LOG_TRACEBACK = settings.log_traceback
TIMEOUT = settings.timeout
TRIES = settings.tries
DEFAULT_RECVWINDOW = settings.default_recvwindow
OKEX_USE_DEMO = settings.okex_use_demo
STAGGER_BYBIT_CLIENT_INITS = settings.stagger_bybit_client_inits
IG_USE_DEMO = settings.ig_use_demo
PHEMEX_USE_HIGH_RATE_API_ENDPOINT = settings.phemex_use_high_rate_api_endpoint
CAPITAL_ACCOUNT_CURRENCY = settings.capital_account_currency




class UniversalClient:
    ORDER_TYPE_MARKET = 'MARKET'
    ORDER_TYPE_LIMIT = "LIMIT"
    ORDER_TYPE_STOP = 'STOP'
    ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
    SIDE_BUY = 'BUY'
    SIDE_SELL = 'SELL'
    TIME_IN_FORCE_GTC = 'GTC'  # Good till cancelled
    TIME_IN_FORCE_GTX = 'GTX'  # Good till crossing (post only)
    KLINE_INTERVAL_5MINUTE = '5m'

    def __init__(
        self,
        exchange,
        timeout=TIMEOUT,
        tries=TRIES,
        discord_service: Optional[DiscordNotificationService] = None,
        use_local_tick_and_step_data=False,
    ):
        self.tries = tries
        self.timeout = timeout
        self.exchange = exchange
        self.use_local_tick_and_step_data = use_local_tick_and_step_data
        self.okex_pos_mode = OKEX_POS_MODE
        self.logger = Logger(self, print_console=PRINT_CONSOLE, discord_service=discord_service)
        if self.exchange == "BINANCE" or self.exchange == "BINANCE_SPOT":
            self.client_binance = Client(BINANCE_API_KEY, BINANCE_API_SECRET, requests_params={'timeout': self.timeout})
        elif "FTX" in self.exchange:
            #check for subaccount e.g. "FTX_subaccount1"
            subaccount = None
            if len(self.exchange.split("_")) == 2:
                subaccount = self.exchange.split("_")[1]
                # self.exchange = self.exchange.split("_")[0]
            self.client_ftx = FtxClient(api_key=FTX_API_KEY, api_secret=FTX_API_SECRET, timeout=self.timeout, subaccount_name=subaccount)
        elif "OKEX" in self.exchange:
            if OKEX_USE_DEMO:
                self.client_okex = OkexClient(OKEX_API_KEY_DEMO, OKEX_API_SECRET_DEMO, OKEX_PASSPHRASE_DEMO, False, '1', timeout=self.timeout)
            else:
                if "LowStakes" in self.exchange or "2" in self.exchange:
                    self.client_okex = OkexClient(OKEX_API_KEY_SECOND, OKEX_API_SECRET_SECOND, OKEX_PASSPHRASE_SECOND, False, '0', timeout=timeout)
                else:
                    self.client_okex = OkexClient(OKEX_API_KEY, OKEX_API_SECRET, OKEX_PASSPHRASE, False, '0', timeout=timeout)
            if self.okex_pos_mode == 'net':
                self.reduce_only_orders = {}  # orderId: time_added (in seconds)
        elif "GATE" in self.exchange:
            if "LowStakes" in self.exchange or "2" in self.exchange:
                self.client_gate = FuturesApi(ApiClient(Configuration(key=GATEIO_API_KEY_SECOND, secret=GATEIO_API_SECRET_SECOND)))
            elif "3" in self.exchange:
                self.client_gate = FuturesApi(ApiClient(Configuration(key=GATEIO_API_KEY_THIRD, secret=GATEIO_API_SECRET_THIRD)))
            elif "4" in self.exchange:
                self.client_gate = FuturesApi(ApiClient(Configuration(key=GATEIO_API_KEY_FOURTH, secret=GATEIO_API_SECRET_FOURTH)))
            else:
                self.client_gate = FuturesApi(ApiClient(Configuration(key=GATEIO_API_KEY, secret=GATEIO_API_SECRET)))
        elif "BYBIT" in self.exchange:
            if STAGGER_BYBIT_CLIENT_INITS:
                # stagger BYBIT initialisation because of strict IP rate limits
                sleep(6)
            if "LowStakes" in self.exchange or "2" in self.exchange:
                self.client_bybit = BybitClient(api_key=BYBIT_API_KEY_SECOND, api_secret=BYBIT_API_SECRET_SECOND, timeout=timeout)
            elif "3" in self.exchange:
                self.client_bybit = BybitClient(api_key=BYBIT_API_KEY_THIRD, api_secret=BYBIT_API_SECRET_THIRD, timeout=timeout)
            else:
                self.client_bybit = BybitClient(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET, timeout=timeout)
            self.bybit_symbol_max_quantity = {}
            for symbol_data in self._get_bybit_symbol_data():
                self.bybit_symbol_max_quantity[symbol_data['symbol']] = Decimal(symbol_data['lotSizeFilter']['maxOrderQty'])
        elif "MEXC" in self.exchange:
            self.client_mexc = MxcClient(access_key=MEXC_API_KEY, secret_key=MEXC_API_SECRET, timeout=timeout)
        elif "KUCOIN" in self.exchange:
            self.client_kucoin_market = Market()
        elif "CAPITAL" in self.exchange:
            subaccount = None
            if len(self.exchange.split("_")) == 2:
                subaccount = self.exchange.split("_")[1]
            self.client_capital = CapitalClient(api_key=CAPITALDOTCOM_API_KEY, username=CAPITALDOTCOM_USERNAME, password=CAPITALDOTCOM_PASSWORD, subaccount=subaccount, timeout=timeout)
            self.capital_exchange_rate_data = {}
            self.capital_instrument_currency_data = {}
            if not use_local_tick_and_step_data:
                threading.Thread(target=self._capital_update_exchange_rates_job).start()
        elif "IG" in self.exchange:
            subaccount = None
            if len(self.exchange.split("_")) == 2:
                subaccount = self.exchange.split("_")[1]
            if IG_USE_DEMO:
                api_key = IG_API_KEY_DEMO
                user_name = IG_USERNAME_DEMO
                password = IG_PASSWORD_DEMO
                acc_type = "demo"
            else:
                api_key = IG_API_KEY
                user_name = IG_USERNAME
                password = IG_PASSWORD
                acc_type = "live"
            # self.client_ig = IgClient(api_key=api_key, username=user_name, password=password, acc_type=acc_type, subaccount=subaccount, timeout=timeout)
        elif "PHEMEX" in self.exchange:
            self.client_phemex = PhemexClient(api_key=PHEMEX_API_ID, api_secret=PHEMEX_API_SECRET, timeout=timeout, use_high_rate_endpoint=PHEMEX_USE_HIGH_RATE_API_ENDPOINT)
        elif "BITRUE" in self.exchange:
            self.client_bitrue = BitrueClient()
        elif "BINGX" in self.exchange:
            self.client_bingx = BingxClient(api_key=BINGX_API_KEY, api_secret=BINGX_API_SECRET, timeout=timeout)
        elif "XT" in self.exchange:
            self.client_xt = XtClient(api_key=XT_API_KEY, api_secret=XT_API_SECRET, timeout=timeout)
        self.current_api_url = API0
        self.precisionPriceDict = {}
        self.precisionQuantityDict = {}
        for pair in self.futures_exchange_info():
            self.precisionPriceDict[pair.get('symbol')] = Decimal(pair.get('tickSize'))
            self.precisionQuantityDict[pair.get('symbol')] = Decimal(pair.get('stepSize'))

    def _capital_update_exchange_rates_job(self):
        while True:
            sleep(60*60*24 + random.randint(0, 60*60*12))
            self.logger.writeline(f"Updating exchange rates")
            forex_pairs = ['AUDCAD', 'AUDCHF', 'AUDCNH', 'AUDHKD', 'AUDJPY', 'AUDMXN', 'AUDNOK', 'AUDNZD', 'AUDPLN', 'AUDSGD', 'AUDTRY', 'AUDUSD', 'AUDZAR', 'CADCHF', 'CADCNH', 'CADHKD', 'CADJPY', 'CADMXN', 'CADNOK', 'CADPLN', 'CADSEK', 'CADSGD', 'CADTRY', 'CADZAR', 'CHFCNH', 'CHFCZK', 'CHFDKK', 'CHFHKD', 'CHFHUF', 'CHFJPY', 'CHFMXN', 'CHFNOK', 'CHFPLN', 'CHFSEK', 'CHFSGD', 'CHFTRY', 'CHFZAR', 'CNHHKD', 'CNHJPY', 'DKKJPY', 'DKKSEK', 'EURAUD', 'EURCAD', 'EURCHF', 'EURCNH', 'EURCZK', 'EURDKK', 'EURGBP', 'EURHKD', 'EURHUF', 'EURILS', 'EURJPY', 'EURMXN', 'EURNOK', 'EURNZD', 'EURPLN', 'EURSEK', 'EURSGD', 'EURTRY', 'EURUSD', 'EURZAR', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPCNH', 'GBPCZK', 'GBPDKK', 'GBPHKD', 'GBPHUF', 'GBPJPY', 'GBPMXN', 'GBPNOK', 'GBPNZD', 'GBPPLN', 'GBPSEK', 'GBPSGD', 'GBPTRY', 'GBPUSD', 'GBPZAR', 'HKDMXN', 'HKDSEK', 'HKDTRY', 'MXNJPY', 'NOKDKK', 'NOKJPY', 'NOKSEK', 'NOKTRY', 'NZDCAD', 'NZDCHF', 'NZDCNH', 'NZDHKD', 'NZDJPY', 'NZDMXN', 'NZDPLN', 'NZDSEK', 'NZDSGD', 'NZDTRY', 'NZDUSD', 'PLNJPY', 'PLNSEK', 'PLNTRY', 'SEKJPY', 'SEKMXN', 'SEKTRY', 'SGDHKD', 'SGDJPY', 'SGDMXN', 'TRYJPY', 'USDCAD', 'USDCHF', 'USDCNH', 'USDCZK', 'USDDKK', 'USDHKD', 'USDHUF', 'USDILS', 'USDJPY', 'USDMXN', 'USDNOK', 'USDPLN', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR', 'ZARJPY']
            self.client_capital.refresh_security_tokens()
            for sym_data in self.client_capital.get_market([x for x in forex_pairs if CAPITAL_ACCOUNT_CURRENCY in x])['marketDetails']:
                if sym_data['instrument']['type'] == 'CURRENCIES' and 'bid' in sym_data['snapshot']:
                    self.capital_exchange_rate_data[sym_data['instrument']['epic']] = sym_data['snapshot']['bid']
                self.capital_instrument_currency_data[sym_data['instrument']['epic']] = sym_data['instrument']['currency']

    def switch_api_url(self):
        if self.exchange == "BINANCE":
            if self.current_api_url == API0:
                self.client_binance.API_URL = API1
                self.current_api_url = API1
            elif self.current_api_url == API1:
                self.client_binance.API_URL = API2
                self.current_api_url = API2
            elif self.current_api_url == API2:
                self.client_binance.API_URL = API3
                self.current_api_url = API3
            elif self.current_api_url == API3:
                self.client_binance.API_URL = API0
                self.current_api_url = API0

    def process_okex_position_to_binance_position(self, position, symbol):
        if position:
            if isinstance(position, list):
                found_pos = False
                for i in range(len(position)):
                    if position[i]['avgPx'] != '':
                        position = position[i]
                        found_pos = True
                        break
                if not found_pos:
                    position = position[0]
            symbol = position['instId']
            entry_price = position['avgPx']
            if not entry_price:
                entry_price = '0'
                position_amt = '0'
                unRealizedProfit = '0'
            else:
                if 'USDT' in symbol:
                    position_amt = str(Decimal(position['pos']) * self.precisionQuantityDict[symbol])
                else:
                    position_amt = str(Decimal(position['pos']) * self.precisionQuantityDict[symbol] / Decimal(entry_price))
                if position['posSide'] == 'short':
                    position_amt = '-' + position_amt
                else:
                    try:
                        if float(position['posSide']) < 0:
                            position_amt = '-' + position_amt
                    except ValueError:
                        pass
                unRealizedProfit = position['upl']
        else:
            entry_price = '0'
            position_amt = '0'
            unRealizedProfit = '0'
        return {"entryPrice": entry_price,
                 "positionAmt": position_amt, "symbol": symbol,
                 "unRealizedProfit": unRealizedProfit}

    def process_okex_order_to_binance(self, order):
        return normalize_okex_order(self, order)


    def process_gate_order_to_binance(self, order):
        return normalize_gate_order(self, order)


    def process_mexc_order_to_binance(self, order):
        return normalize_mexc_order(self, order)


    def process_bybit_order_to_binance(self, order):
        return normalize_bybit_order(self, order)


    def process_phemex_order_to_binance(self, order):
        return normalize_phemex_order(self, order)


    def process_bingx_order_to_binance(self, order, symbol=None):
        return normalize_bingx_order(self, order, symbol)


    def process_mexc_position_to_binance(self, position):
        if position['positionType'] == 2:
            position_dir = "-"
        else:
            position_dir = ""
        return {"entryPrice": format_float_in_standard_form(position['holdAvgPrice']),
                "positionAmt": position_dir + str(
                    Decimal(str(position['holdVol'])) * self.precisionQuantityDict[position['symbol']]),
                "symbol": position['symbol'],
                "unRealizedProfit": None}  # MEXC API does not provide unrealised profit

    def process_phemex_position_to_binance(self, position):
        # get latest mark price to calc unrealised pnl
        mark_price = Decimal(str(self.client_phemex.query_24h_ticker(symbol=position['symbol'])['markPrice'])) * Decimal('0.0001')
        if 'avgEntryPrice' in position:
            entry_price = format_float_in_standard_form(position['avgEntryPrice'])
        else:
            entry_price = str(Decimal(str(position['avgEntryPriceEp'])) * Decimal('0.0001'))
        if position['side'] == "Sell":
            position_dir = "-"
            unRealizedProfit = (Decimal(str(position['size'])) * self.precisionQuantityDict[position['symbol']]) * Decimal(entry_price) - (Decimal(str(position['size'])) * self.precisionQuantityDict[position['symbol']]) * mark_price
        else:
            position_dir = ""
            unRealizedProfit = (Decimal(str(position['size'])) * self.precisionQuantityDict[position['symbol']]) * mark_price - (Decimal(str(position['size'])) * self.precisionQuantityDict[position['symbol']]) * Decimal(entry_price)
        return {"entryPrice": entry_price,
                "positionAmt": position_dir + str(Decimal(str(position['size'])) * self.precisionQuantityDict[position['symbol']]),
                "symbol": position['symbol'],
                "unRealizedProfit": str(unRealizedProfit)}

    def process_bingx_position_to_binance(self, position):
        symbol = position['symbol']
        entry_price = round_interval_nearest(position['avgPrice'], self.precisionPriceDict[symbol])
        size = round_interval_nearest(position['volume'], self.precisionQuantityDict[symbol])
        if position['positionSide'] == "Short":
            position_dir = "-"
        else:
            position_dir = ""
        return {"entryPrice": str(entry_price),
                "positionAmt": f'{position_dir}{size}',
                "symbol": symbol,
                "unRealizedProfit": str(position['unrealisedPNL'])}

    def process_bybit_position_to_binance(self, position):
        if position['side'] == "Sell" and position['size'] != 0:
            position_dir = "-"
        else:
            position_dir = ""
        unRealizedProfit = format_float_in_standard_form(position['unrealisedPnl']) if ('unrealisedPnl' in position and position['unrealisedPnl'] != '') else None
        return {"entryPrice": format_float_in_standard_form(position['avgPrice']) if format_float_in_standard_form(position['avgPrice']) != '' else '0',
                "positionAmt": position_dir + str(position['size']),
                "symbol": position['symbol'],
                "unRealizedProfit": unRealizedProfit}

    def process_ig_position_to_binance(self, position):
        # also works for CAPITAL positions
        entry_price = position['position']['level']
        position_size = Decimal(str(position['position']['size'])) * Decimal(str(position['position']['contractSize']))
        size_pre_str = ''
        if position['position']['direction'] == "SELL":
            size_pre_str = '-'
            if_close_price = position['market']['offer']
            unrealisedp = (Decimal(str(entry_price)) * position_size) - (Decimal(str(if_close_price)) * position_size)
        else:
            if_close_price = position['market']['bid']
            unrealisedp = (Decimal(str(if_close_price)) * position_size) - (Decimal(str(entry_price)) * position_size)
        return {"entryPrice": format_float_in_standard_form(entry_price),
                "positionAmt": size_pre_str + str(position_size),
                "symbol": position['market']['epic'],
                "unRealizedProfit": str(round(unrealisedp, 3))}

    def tries_wrapper(func):
        """
        only use on functions that interact with API directly (functions that use self.client_binance
        or self.client_ftx
        """
        def get_symbol_from_args(*args, **kwargs):
            try:
                symbol = kwargs['symbol']
                return symbol
            except KeyError:
                return args[1]

        def handle_duplicate_client_id_error(self, *args, **kwargs):
            # We cannot simply use futures_get_order and search for client_id in kwargs as FTX
            # conditional orders cannot be found using client_ids as they do not store them.
            symbol = get_symbol_from_args(*args, **kwargs)
            isLongStopLoss = kwargs['side'] == "SELL" and kwargs['reduceOnly'] is True and kwargs[
                'type'] == self.ORDER_TYPE_STOP_MARKET
            isShortStopLoss = kwargs['side'] == "BUY" and kwargs['reduceOnly'] is True and kwargs[
                'type'] == self.ORDER_TYPE_STOP_MARKET
            order = None
            if kwargs['side'] == "BUY" and kwargs['type'] == self.ORDER_TYPE_LIMIT:
                order = self.futures_get_open_buy_limit_orders(symbol)
            elif kwargs['side'] == "SELL" and kwargs['type'] == self.ORDER_TYPE_LIMIT:
                order = self.futures_get_open_sell_limit_orders(symbol)
            elif isLongStopLoss:
                order = self.futures_get_long_stop_loss_order(symbol)
            elif isShortStopLoss:
                order = self.futures_get_short_stop_loss_order(symbol)

            if not order:
                self.logger.writeline(f"{symbol} ERROR in handle_duplicate_client_id_error, not able to find duplicate client id order!")
                return None
            return order[0]

        def handle_rate_limit_or_timeout_when_placing_order(self, *args, **kwargs):
            """
            #NOTE: if using stop loss orders this needs rework as it assumes only one buy or sell order active at one time
            Use for exchanges where no client id's are used so we must manually prevent duplicate orders
            :return: None if no order was found
            order if order is found
            """
            sleep(1)
            self.logger.writeline(f"timeout out or rate limited when placing order, checking if order has still gone through... {kwargs}")
            # check if no position created and previous order is not present
            symbol = get_symbol_from_args(*args, **kwargs)
            if kwargs['side'] == "BUY":
                open_orders = self.futures_get_open_buy_orders(symbol)
            else:
                open_orders = self.futures_get_open_sell_orders(symbol)
            if open_orders:
                for order in open_orders:
                    if order['type'] == kwargs['type']:
                        self.logger.writeline(f"{symbol} found open order {order}")
                        return order
            if get_position_size(self.futures_get_position(symbol)) == 0 and not kwargs['reduceOnly']:
                if kwargs['side'] == "BUY":
                    self.futures_cancel_open_buy_orders(symbol)
                else:
                    self.futures_cancel_open_sell_orders(symbol)
                self.logger.writeline(f"no open position and orders found {kwargs}, retrying placing entry order..")
                return None
            elif not kwargs['reduceOnly']:
                self.logger.writeline(f"position created from timeout or rate limited order {kwargs}")
                if "CAPITAL" in self.exchange:
                    # get orderId (deal ref) from position info
                    positions = self.client_capital.get_positions()['positions']
                    for position in positions:
                        if position['market']['epic'] == symbol:
                            return {'orderId': position['position']['dealReference']}
                return {'orderId': None}
            elif kwargs['reduceOnly']:
                self.logger.writeline(f"{symbol} retrying reduceOnly exit order {kwargs}...")
                return None

        def tries(*args, **kwargs):
            returnValue = None
            i = 0
            self: UniversalClient = args[0]
            while i < self.tries:
                try:
                    returnValue = func(*args, **kwargs)
                except Exception as e:
                    # MEXC exchange specific: When sending a new reduce only order,
                    # MEXC api seems to be a bit delayed thinking the previous reduce only order has not
                    # been cancelled yet so gives below warning. Need to wait a bit then resend
                    mexc_reduce_only_order_error = "MEXC" in str(e) and ("Close order's vol must less or equals than position hold vol" in str(e) or "2008" in str(e))
                    if ((i < self.tries - 1) and (isinstance(e, Timeout) or isinstance(e, MaxRetryError))) or mexc_reduce_only_order_error or \
                       'CAPITAL unable to get deal confirmation' in str(e):
                        if mexc_reduce_only_order_error:
                            sleep(0.05)
                        if sum([x in self.exchange for x in ["BINGX", "CAPITAL"]]) and func.__name__ == "futures_create_order":
                            # Custom handling of create order timeout since no unique client order ID
                            order = handle_rate_limit_or_timeout_when_placing_order(self, *args, **kwargs)
                            if order:
                                return order
                        # ignore logging time outs unless we hit max retries
                        i = i + 1
                        continue
                    if bool(re.match(r"Do not send more than \d orders( total)? per 200ms", str(e))) or \
                            (isinstance(e, OkexAPIException) and e.code == "50011") or \
                            ("MEXC" in str(e) and "510" in str(e)) or \
                            (isinstance(e, InvalidRequestError) and e.status_code == 10018) or \
                            'CapitalClient ERROR error.public-api.exceeded-request-rate-allowance' in str(e) or \
                            'CapitalClient ERROR error.too-many.requests' in str(e) or \
                            ((isinstance(e, BingxAPIException) and e.code == 80012) and 'System currently busy, try again' in str(e)) or \
                            (isinstance(e, BingxAPIException) and e.status_code == 429):
                        # BINGX code 80012: System currently busy, try again. Status code 429: Too Many Requests
                        # OKEX error 50011 = Requests too frequent.
                        # FTX order rate is limited per 200ms
                        # MEXC error 510 = Request frequently too fast
                        # BYBIT 10018 = Out of frequency limit
                        if func.__name__ == 'futures_create_order' and "CAPITAL" in self.exchange:
                            # CAPITAL even if rate limited error returned, order sometimes goes through
                            order = handle_rate_limit_or_timeout_when_placing_order(self, *args, **kwargs)
                            if order:
                                return order
                            else:
                                i = i + 2
                        i = i - 1  # -1 from i means we try again infinitely many times until all orders are through
                        sleep(0.1)
                        continue
                    if isinstance(e, FailedRequestError) and e.status_code == 403:
                        # BYBIT IP rate limited, sleep for longer
                        random_time_to_wait = random.randint(5, 60)
                        self.logger.writeline(f"BYBIT IP rate limited from {func.__name__}!, waiting {random_time_to_wait} seconds")
                        i = i - 1
                        sleep(random_time_to_wait)
                        continue
                    if 'CapitalClient ERROR error.security.token-invalid' in str(e) or 'CapitalClient ERROR error.invalid.session.token' in str(e):
                        self.client_capital.refresh_security_tokens()
                        i = i - 1
                        continue
                    if isinstance(e, PhemexAPIException) and e.status_code == 429:
                        if 'X-RateLimit-Retry-After-OTHER' in e.headers.keys():
                            seconds_to_wait = int(e.headers['X-RateLimit-Retry-After-OTHER'])
                        elif 'X-RateLimit-Retry-After-SPOTORDER' in e.headers.keys():
                            seconds_to_wait = int(e.headers['X-RateLimit-Retry-After-SPOTORDER'])
                        elif 'X-RateLimit-Retry-After-CONTRACT' in e.headers.keys():
                            seconds_to_wait = int(e.headers['X-RateLimit-Retry-After-CONTRACT'])
                        else:
                            seconds_to_wait = int(e.headers['X-RateLimit-Retry-After'])
                        self.logger.writeline(f"PHEMEX rate limited from {func.__name__}!, waiting {seconds_to_wait} seconds", discord_channel_id=DISCORD_ERROR_MESSAGES_CHANNEL_ID)
                        sleep(seconds_to_wait)
                        i = i - 1
                        continue
                    # self.logger.writeline(f"EXCEPTION in {func.__name__}!: {args[1:]} {kwargs} {e}")
                    if LOG_TRACEBACK:
                        self.logger.writeline(f"{traceback.format_exc()}")
                    if func.__name__ == "futures_create_order":
                        isLongStopLoss = kwargs['side'] == "SELL" and kwargs['reduceOnly'] is True and kwargs['type'] == self.ORDER_TYPE_STOP_MARKET
                        isShortStopLoss = kwargs['side'] == "BUY" and kwargs['reduceOnly'] is True and kwargs['type'] == self.ORDER_TYPE_STOP_MARKET
                        if self.exchange == "BINANCE":
                            if isLongStopLoss and isShortStopLoss and isinstance(e, BinanceAPIException) and e.code == -2021:  # code for 'Order will immediately trigger'
                                self.logger.writeline(f"ERROR: {func.__name__} {args[1:]} {kwargs} Stop loss unable to be submitted, closing at market...")
                                return self.futures_close_position(get_symbol_from_args(*args, **kwargs))
                            # if the error when placing a limit order is one of the following then we need to return the order
                            # that was submitted successfully to the server
                            if isinstance(e, BinanceAPIException) and (e.code == -2022 or e.code == -4015):  # codes for 'ReduceOnly Order is rejected' and 'Client order id is not valid'
                                return handle_duplicate_client_id_error(self, *args, **kwargs)
                        elif "FTX" in self.exchange:
                            if str(e) == "Duplicate client order ID":
                                return handle_duplicate_client_id_error(self, *args, **kwargs)
                            if str(e) == "Invalid reduce-only order":
                                # attempted to close a position but a previous reduce-only order must've been filled
                                # at the same time or there is already a reduce-only order open.
                                # TODO: Will need to return the previous filled order for logging
                                if 'newClientOrderId' in kwargs.keys():
                                    order = self.futures_get_order(origClientOrderId=kwargs['newClientOrderId'])
                                    if order:
                                        return order
                                self.logger.writeline(f"ERROR: {get_symbol_from_args(*args, **kwargs)} 'Invalid reduce-only order' and unable to get past reduce only order, skipping new reduce only order placement")
                                raise Exception(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ERROR: {get_symbol_from_args(*args, **kwargs)} skipping reduce only order placement")
                        elif "OKEX" in self.exchange:
                            if (isLongStopLoss or isShortStopLoss) and isinstance(e, OkexAPIException) and e.message == "Close order size exceeds your available size":
                                # OKEX does not allow a TP limit order be active the same time as a STOP or STOP MARKET stop loss order
                                # Will need to work with OCO trigger orders if this feature is to be used
                                raise Exception("OKEX stop loss orders not supported")
                            if isinstance(e, OkexAPIException) and e.code == "51016":  # duplicate client ID
                                return handle_duplicate_client_id_error(self, *args, **kwargs)
                            if isinstance(e, OkexAPIException) and e.code == "51112":  # close order size exceeds your available size
                                symbol = get_symbol_from_args(*args, **kwargs)
                                position_size = get_position_size(self.futures_get_position(symbol))
                                stopPrice = None if 'stopPrice' not in kwargs.keys() else kwargs['stopPrice']
                                self.logger.writeline(f"{symbol} Updating quantity to {position_size}")
                                return self.futures_create_order(symbol=symbol,
                                                                 side=kwargs['side'],
                                                                 type=kwargs['type'],
                                                                 price=kwargs['price'],
                                                                 quantity=position_size,
                                                                 reduceOnly=kwargs['reduceOnly'],
                                                                 timeInForce=kwargs['timeInForce'],
                                                                 recvWindow=kwargs['recvWindow'],
                                                                 newClientOrderId=kwargs['newClientOrderId'],
                                                                 stopPrice=stopPrice)
                            if isinstance(e, OkexAPIException) and e.code == "51004":  # Order amount exceeds current tier limit
                                symbol = get_symbol_from_args(*args, **kwargs)
                                current_leverage = int(self.client_okex.get_leverage(symbol, "cross")[0]['lever'])
                                self.logger.writeline(f"{symbol} Changing leverage to {current_leverage-1}")
                                self.futures_cancel_all_orders(symbol=symbol)
                                self.futures_change_leverage(symbol, current_leverage-1)
                        elif "GATE" in self.exchange:
                            pass
                        elif "MEXC" in self.exchange:
                            if "Duplicate order ID" in str(e) or "2042" in str(e):
                                return handle_duplicate_client_id_error(self, *args, **kwargs)
                        elif "BYBIT" in self.exchange:
                            if isinstance(e, InvalidRequestError) and (e.status_code == 30089 or e.status_code == 1141):
                                return handle_duplicate_client_id_error(self, *args, **kwargs)
                        elif "PHEMEX" in self.exchange:
                            if isinstance(e, PhemexAPIException) and e.code == 11085:  # duplicate client order id
                                return handle_duplicate_client_id_error(self, *args, **kwargs)
                            elif isinstance(e, PhemexAPIException) and e.code == 11011:  # invalid reduce only
                                return
                        elif "BINGX" in self.exchange:
                            if isinstance(e, BingxAPIException) and e.code == 80014:  # "Insufficient position, please adjust and resubmit" when placing an invalid reduce only order, we skip
                                return
                            if '"Code":101414' in str(e):  # sometimes this error code appears when placing orders, must try again
                                i = i + 1
                                sleep(random.randint(10, 25) * 0.01)
                                continue
                            # TODO: keep an eye for futures BINGX api versions that allow client order ID's
                            # because BINGX v1 api does not have client ID's, it's safer to just cancel placing the order if there is a problem to avoid duplicate orders
                            symbol = get_symbol_from_args(*args, **kwargs)
                            self.logger.writeline(f"ERROR {e} when placing BINGX order for {symbol} {kwargs}, cancelling", discord_channel_id=DISCORD_ERROR_MESSAGES_CHANNEL_ID)
                            return
                        elif "CAPITAL" in self.exchange:
                            # if there is an error creating an order it probably means we tried to reduce position
                            # with no position opened or error trying to get the order we already placed
                            # so we don't retry for either cases
                            self.logger.writeline(f'{e}')
                            raise e
                    if isinstance(e, BinanceAPIException) and e.code == -2013:  # Order does not exist
                        return None
                    if isinstance(e, OkexAPIException) and e.code == "51603":  # Order does not exist
                        return None
                    if isinstance(e, GateApiException) and e.label == "ORDER_NOT_FOUND":
                        return None
                    if isinstance(e, GateApiException) and str(e.status) == "500":  # Server Error
                        raise e
                    # if isinstance(e, InvalidRequestError) and e.status_code == 10018:
                    #     self.logger.writeline(f"{symbol} BYBIT API rate limited, waiting 60 secs...")
                    #     sleep(60)
                    self.switch_api_url()
                    if i < self.tries - 1:
                        i = i + 1
                        continue
                    else:
                        # if isinstance(e, Timeout):
                        #     self.logger.writeline(f"ERROR: maximum timeouts! {args[1:]}")
                        self.logger.writeline(f"ERROR: maximum retries made for {func.__name__}! {args[1:]} {kwargs} {str(e)}")
                        # if isinstance(e, GateApiException):
                        #     raise e
                        raise e
                        # raise ConnectionError(f"ERROR: maximum retries made for {func.__name__}! {args[1:]} {kwargs}")
                        # if func.__name__ == "futures_close_best_price":
                        #     # unable to complete close at best price so need to close at market
                        #     self.logger.writeline(
                        #         f"ERROR: futures_close_best_price {args[1:]} {kwargs} Unable to close at best price, closing at market...")
                        #     return self.futures_close_position(get_symbol_from_args(*args, **kwargs))
                return returnValue
        return tries

    @tries_wrapper
    def _get_bybit_symbol_data(self):
        """
        Used on BYBIT only, to get max qty an order allows
        :return:
        """
        return self.client_bybit.query_symbol()

    @tries_wrapper
    def futures_exchange_info(self):
        """
        Gets all perpertual futures:
        [
            {
                symbol: str,
                tickSize: str,
                stepSize: str
            }
        ]
        :return:
        """
        result = []

        if self.use_local_tick_and_step_data:
            exchange_name = str(self.exchange).split("_")[0]
            path = os.path.realpath(__file__).replace('UniversalClient.py', "") + f'exchange_data_{exchange_name}.csv'
            csv_data_list = self.logger.readcsv(path)
            for csv_data in csv_data_list:
                result.append({"symbol": csv_data[0],
                               "tickSize": csv_data[1],
                               "stepSize": csv_data[2]})
            return result

        if self.exchange == "BINANCE":
            for pair in self.client_binance.futures_exchange_info().get('symbols'):
                for f in pair['filters']:
                    if f.get('tickSize'):
                        tickSize = f.get('tickSize')
                    if f.get('stepSize') and f.get(
                            'filterType') == "LOT_SIZE":  # there is another stepSize under ['filterType']="MARKET_LOT_SIZE" that is given
                        stepSize = f.get('stepSize')
                result.append({"symbol": pair.get('symbol'), "tickSize": tickSize, "stepSize": stepSize})
        elif self.exchange == "BINANCE_SPOT":
            for pair in self.client_binance.get_exchange_info().get('symbols'):
                if str(pair['symbol']).endswith("USDT"):
                    for f in pair['filters']:
                        if f.get('tickSize'):
                            tickSize = f.get('tickSize')
                        if f.get('stepSize') and f.get(
                                'filterType') == "LOT_SIZE":  # there is another stepSize under ['filterType']="MARKET_LOT_SIZE" that is given
                            stepSize = f.get('stepSize')
                    result.append({"symbol": pair.get('symbol'), "tickSize": tickSize, "stepSize": stepSize})
        elif "FTX" in self.exchange:
            for pair in self.client_ftx.get_markets():
                if "PERP" in pair.get('name') and "PERP/USD" not in pair.get('name'):
                    result.append({"symbol": pair.get('name'),
                                   "tickSize": format_float_in_standard_form(pair.get("priceIncrement")),
                                   "stepSize": format_float_in_standard_form(pair.get('sizeIncrement'))})
        elif "OKEX" in self.exchange:
            for instrument in self.client_okex.get_instruments("SWAP"):
                result.append({"symbol": instrument.get('instId'),
                               "tickSize": instrument.get("tickSz"),
                               "stepSize": instrument.get('ctVal')})
        elif "GATE" in self.exchange:
            for instrument in self.client_gate.list_futures_contracts(settle="usdt", _request_timeout=(self.timeout, self.timeout)):
                result.append({"symbol": instrument.name,
                               "tickSize": instrument.order_price_round,
                               "stepSize": instrument.quanto_multiplier})
        elif "BYBIT" in self.exchange:
            for instrument in self.client_bybit.query_symbol():
                if instrument["contractType"] == 'LinearPerpetual':
                    result.append({"symbol": instrument['symbol'],
                                   "tickSize": instrument['priceFilter']['tickSize'],
                                   "stepSize": format_float_in_standard_form(instrument['lotSizeFilter']['qtyStep'])})
        elif "MEXC" in self.exchange:
            for instrument in self.client_mexc.get_contract_detail():
                result.append({"symbol": instrument.get('symbol'),
                               "tickSize": format_float_in_standard_form(instrument.get("priceUnit")),
                               "stepSize": format_float_in_standard_form(instrument.get('contractSize'))})
        elif "KUCOIN" in self.exchange:
            for instrument in self.client_kucoin_market.get_contracts_list():
                if "USDTM" in instrument.get('symbol'):
                    result.append({"symbol": instrument.get('symbol'),
                                   "tickSize": format_float_in_standard_form(instrument.get("tickSize")),
                                   "stepSize": format_float_in_standard_form(instrument.get('multiplier'))})
        elif "CAPITAL" in self.exchange:
            # API does not provide all instruments, only what is most trending/traded so getting instruments
            # from the API varies from whenever it is called. We must therefore store a local file of known
            # instruments to look up upon.
            symbols_list = []
            # forex_groups = self.client_capital.get_marketnavigation('hierarchy_v1.forex')['nodes']
            # for group in forex_groups:
            #     for market in self.client_capital.get_marketnavigation(group['id'])['markets']:
            #         symbol_list.append(market['epic'])
            with open(os.path.realpath(__file__).replace('UniversalClient.py', "") + 'capital_instruments.txt', mode='r') as f:
                lines = f.readlines()
                symbols_list = [line.strip() for line in lines]

            def traverse_hierarchy(root_id):
                sleep(0.05)
                root = self.client_capital.get_marketnavigation(nodeId=root_id)
                # print(f'getting root_id {root_id}')
                if 'nodes' in root and root['nodes']:
                    for branch in root['nodes']:
                        traverse_hierarchy(branch['id'])
                if 'markets' in root:
                    for market in root['markets']:
                        symbols_list.append(market['epic'])

            # traverse_hierarchy("")
            # symbols_list = list(set(symbols_list))
            # symbols_list.sort()
            # with open('capital_instruments.txt', mode='w') as f:
            #     for symbol in symbols_list:
            #         f.write(symbol + '\n')

            for sym_data in self.client_capital.get_market(symbols_list)['marketDetails']:
                result.append({"symbol": sym_data['instrument']['epic'],
                               "tickSize": format_float_in_standard_form(sym_data['dealingRules']['minStepDistance']['value']),
                               "stepSize": format_float_in_standard_form(sym_data['dealingRules']['minDealSize']['value'])})
                if sym_data['instrument']['type'] == 'CURRENCIES' and 'bid' in sym_data['snapshot']:
                    self.capital_exchange_rate_data[sym_data['instrument']['epic']] = sym_data['snapshot']['bid']
                self.capital_instrument_currency_data[sym_data['instrument']['epic']] = sym_data['instrument']['currency']
        elif "IG" in self.exchange:
            symbol_list = []
            result = []
            node_ids_to_check = ['264146', '264141', '264148', '264246', '264160',
                                 '264158']  # ids for (mini) categories 'Major FX', "Minor FX", "Australasian", "Emerging Markets FX", "Exotic", "Scandinavians"
            for node_id in node_ids_to_check:
                for market in self.client_ig.browse_markets(node_id)['markets']:
                    symbol_list.append(market['epic'])
            symbol_list = list(dict.fromkeys(symbol_list))
            for sym_data in self.client_ig.get_markets_list(epics=symbol_list)['marketDetails']:
                result.append({"symbol": sym_data['instrument']['epic'],
                               "tickSize": format_float_in_standard_form(
                                   10 ** -sym_data['snapshot']['decimalPlacesFactor']),
                               "stepSize": format_float_in_standard_form(float(sym_data['instrument'][
                                                                                   'contractSize']) * 0.01)})  # Step size for forex is denoted for first quoted currency. Hard coded 0.01 ratio step size as this seems to be the default and is not listed in api
        elif "PHEMEX" in self.exchange:
            result = []
            products = self.client_phemex.query_product_information()['products']
            for product in products:
                if product['type'] == 'Perpetual' and product['symbol'] != "BTCUSD" and product['symbol'][0] != 'c' and product['status'] != 'Delisted':
                    result.append({"symbol": product['symbol'],
                                   "tickSize": format_float_in_standard_form(product['tickSize']),
                                   "stepSize": format_float_in_standard_form(product['contractSize'])})
        elif "BITRUE" in self.exchange:
            result = []
            contracts = self.client_bitrue.get_contracts()
            for contract in contracts:
                if "USDT" in contract['symbol']:
                    result.append({"symbol": contract['symbol'],
                                   "tickSize": format_float_in_standard_form(10 ** -contract['pricePrecision']),
                                   "stepSize": format_float_in_standard_form(contract['multiplier'])})
        elif "BINGX" in self.exchange:
            result = []
            contracts = self.client_bingx.contract_information()['contracts']
            for contract in contracts:
                result.append({"symbol": contract['symbol'],
                               "tickSize": contract['minStep'],
                               "stepSize": contract['size']})
        elif "XT" in self.exchange:
            result = []
            contracts = self.client_xt.get_exchange_info()
            for contract in contracts:
                if contract['contractType'] == 'PERPETUAL':
                    result.append({"symbol": contract['symbol'],
                                   "tickSize": format_float_in_standard_form(10 ** -contract['pricePrecision']),
                                   "stepSize": contract['contractSize']})
        if not self.use_local_tick_and_step_data:
            exchange_name = str(self.exchange).split("_")[0]
            path = os.path.realpath(__file__).replace('UniversalClient.py', "") + f'exchange_data_{exchange_name}.csv'
            csv_data_list = self.logger.readcsv(path)
            new_csv_data = []
            for instrument_data in result:
                new_csv_data.append([instrument_data['symbol'], instrument_data['tickSize'], instrument_data['stepSize']])
            for csv_data in csv_data_list:
                if csv_data[0] not in [x[0] for x in new_csv_data]:
                    new_csv_data.append(csv_data)
            self.logger.writecsvlines(new_csv_data, path=path, write_mode='w')

        return result

    @tries_wrapper
    def futures_symbol_ticker(self, symbol):
        """
        gets latest price for a symbol
        :param symbol:
        :return:
        {
            symbol: str,
            price: str
        }
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_symbol_ticker(symbol=symbol)
        elif "FTX" in self.exchange:
            result = self.client_ftx.get_market(market=symbol)
            return {"symbol": result['name'], "price": format_float_in_standard_form(result['last'])}
        elif "OKEX" in self.exchange:
            result = self.client_okex.get_ticker(symbol)
            return {"symbol": result['instId'], "price": result['last']}
        elif "GATE" in self.exchange:
            result = self.client_gate.list_futures_tickers(settle="usdt", contract=symbol, _request_timeout=(self.timeout, self.timeout))[0]
            return {"symbol": result.contract, "price": result.last}
        elif "MEXC" in self.exchange:
            result = self.client_mexc.get_contract_ticker(symbol=symbol)
            return {"symbol": result['symbol'], "price": format_float_in_standard_form(result['lastPrice'])}
        elif "BYBIT" in self.exchange:
            result = self.client_bybit.latest_information_for_symbol(symbol=symbol)[0]
            return {"symbol": result['symbol'], "price": result['lastPrice']}
        elif "IG" in self.exchange:
            # return mid price of bid and ask
            result = self.client_ig.get_klines(epic=symbol, resolution="MINUTE", limit=1)
            bid = result['prices'][0]['closePrice']['bid']
            ask = result['prices'][0]['closePrice']['ask']
            mid_price = round_interval_nearest((bid + ask) / 2, self.precisionPriceDict[symbol])
            return {"symbol": symbol, "price": str(mid_price)}
        elif "CAPITAL" in self.exchange:
            # return mid price of bid and ask
            result = self.client_capital.get_klines(epic=symbol, resolution="MINUTE", limit=1)
            bid = result['prices'][0]['closePrice']['bid']
            ask = result['prices'][0]['closePrice']['ask']
            mid_price = round_interval_nearest((bid + ask) / 2, self.precisionPriceDict[symbol])
            return {"symbol": symbol, "price": str(mid_price)}
        elif "PHEMEX" in self.exchange:
            last_price = Decimal(str(self.client_phemex.query_24h_ticker(symbol=symbol)['close'])) * Decimal('0.0001')
            return {"symbol": symbol, "price": str(last_price)}
        elif "BINGX" in self.exchange:
            last_price = self.client_bingx.get_latest_price_of_a_trading_pair(symbol)
            return {"symbol": symbol, "price": str(round_interval_nearest(last_price['tradePrice'], self.precisionPriceDict[symbol]))}

    @tries_wrapper
    def futures_mark_price(self, symbol):
        if self.exchange == "BINANCE":
            return self.client_binance.futures_mark_price(symbol=symbol)
        elif "FTX" in self.exchange:
            # TODO: futures_mark_price for FTX (not currently needed for strategy)
            raise Exception("futures_mark_price for FTX TODO")
        elif "OKEX" in self.exchange:
            # TODO: futures_mark_price for OKEX (not currently needed for strategy)
            raise Exception("futures_mark_price for OKEX TODO")
        elif "GATE" in self.exchange:
            # TODO: futures_mark_price for GATE (not currently needed for strategy)
            raise Exception("futures_mark_price for GATE TODO")
        raise Exception("futures_mark_price TODO")

    @tries_wrapper
    def futures_klines(self, symbol, limit, interval, startTime=None, endTime=None):
        """
        gets klines
        NOTE: volume given on FTX is in USD
        startTime and endTime assumed to be given in milliseconds epoch
        interval: [1m, 3m, 5m, 15m, 30m, 1h, 1d]
        :return: klines goes from oldest to newest in a list
        [
            [
            open_time: int
            open: str
            high: str
            low: str
            close: str
            volume: str
            close_time: int
            volume_usdt: str (only appears if the above 'volume' is not in usdt already)
            ]
        ]
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_klines(symbol=symbol, interval=interval, limit=limit,
                                                      startTime=startTime, endTime=endTime)
        elif self.exchange == "BINANCE_SPOT":
            return self.client_binance.get_klines(symbol=symbol, interval=interval, limit=limit,
                                                  startTime=startTime, endTime=endTime)
        elif "FTX" in self.exchange:
            # FTX kline data from REST API is not updated realtime
            # Completed candles can are also not final it seems, the completed candles can change when queried in the future
            # The candles don't also match up exactly on TV
            result = []
            if startTime:
                startTime = int(round(startTime / 1000))
            if endTime:
                endTime = int(round(endTime / 1000))
            for kline in self.client_ftx.get_historical_data(market_name=symbol,
                                                             resolution=binance_intervals_to_seconds(interval), limit=limit,
                                                             start_time=startTime, end_time=endTime):
                result.append([int(kline['time']), format_float_in_standard_form(kline['open']),
                               format_float_in_standard_form(kline['high']),
                               format_float_in_standard_form(kline['low']),
                               format_float_in_standard_form(kline['close']),
                               format_float_in_standard_form(kline['volume']),
                               int(kline['time']) + int(binance_intervals_to_seconds(interval))*1000 - 1])
            return result
        elif "OKEX" in self.exchange:
            # start time exclusive
            # end time exclusive
            result = []
            if endTime is None:
                endTime = ''
            if startTime is None:
                startTime = ''
            candles = self.client_okex.get_candlesticks(symbol, bar=binance_intervals_to_okex_intervals(interval), after=endTime, before=startTime, limit=limit)
            candles.reverse()
            for kline in candles:
                result.append([int(kline[0]),
                              kline[1],
                              kline[2],
                              kline[3],
                              kline[4],
                              kline[5],
                              int(kline[0]) + int(binance_intervals_to_seconds(interval))*1000 - 1,
                              round(Decimal(kline[6]) * ((Decimal(kline[2])+Decimal(kline[3]))/2), 2)])  # estimated volume in USD
            return result
        elif "GATE" in self.exchange:
            # NOTE: if retrieving last n candles and all n candles have 0 volume, GATE API returns an empty array!
            # To counter the above, always fetch at least 300 candles and return only the last specified limit
            result = []
            if startTime or endTime:
                candles = self.client_gate.list_futures_candlesticks(settle="usdt", contract=symbol, interval=interval,
                                                                     _from=int(round(startTime / 1000)),
                                                                     to=int(round(endTime / 1000)),
                                                                     _request_timeout=(self.timeout, self.timeout))
            else:
                min_limit = max(300, limit)
                candles = self.client_gate.list_futures_candlesticks(settle="usdt", contract=symbol, interval=interval,
                                                                     limit=min_limit, _request_timeout=(self.timeout, self.timeout))
            for kline in candles:
                # if high or low values are blank assume they are the same as the open
                open = kline.o
                high = kline.h if kline.h != '' else open
                low = kline.l if kline.l != '' else open
                close = kline.c
                result.append([int(round(kline.t*1000)),
                              open,
                              high,
                              low,
                              close,
                              kline.v,
                              int(round(kline.t*1000)) + int(binance_intervals_to_seconds(interval))*1000 - 1,
                              str(round(Decimal(kline.v)*self.precisionQuantityDict[symbol] * ((Decimal(high)+Decimal(low))/2), 2))])  # estimated vol in usd since GATE does not provide this
            if startTime or endTime:
                return result[:limit]
            else:
                return result[-limit:]
        elif "BYBIT" in self.exchange:
            # NOTE: BYBIT API sometimes does not return the freshly created candle. e.g. when requesting 2 candles
            # at around the time a new candle is generated, only 1 candle (the old candle) is returned.
            # currently handle the above using WS
            result = []
            if startTime is not None:
                startTime = int(startTime)
            candles = self.client_bybit.query_kline(symbol=symbol, interval=binance_intervals_to_bybit_intervals(interval), limit=limit, start_time=startTime)
            candles.reverse()
            if candles:
                for kline in candles:
                    result.append([kline[0],
                                   str(kline[1]),
                                   str(kline[2]),
                                   str(kline[3]),
                                   str(kline[4]),
                                   str(kline[5]),
                                   int(kline[0]) + int(binance_intervals_to_seconds(interval))*1000 - 1,
                                   str(kline[6])])
                # if limit != 200 and (200 > limit != len(candles)) or (limit >= 200 and len(candles) != 200):
                #     self.logger.writeline(f"{symbol} API WARNING: Asked for {limit} candles but got {len(candles)}")
            return result
        elif "MEXC" in self.exchange:
            result = []
            if startTime is None:
                start_time = ""
            else:
                start_time = int(startTime/1000)
            if endTime is None:
                end_time = ""
            else:
                end_time = int(endTime/1000)
            candles = self.client_mexc.get_contract_kline(symbol=symbol, interval=binance_intervals_to_mexc_intervals(interval), start=start_time, end=end_time)
            num_of_candles_returned = len(candles['time'])
            if num_of_candles_returned > 0:
                for i in range(min(limit, num_of_candles_returned), 0, -1):
                    result.append([int(candles['time'][-i] * 1000),
                                   format_float_in_standard_form(candles['open'][-i]),
                                   format_float_in_standard_form(candles['high'][-i]),
                                   format_float_in_standard_form(candles['low'][-i]),
                                   format_float_in_standard_form(candles['close'][-i]),
                                   format_float_in_standard_form(candles['vol'][-i]),
                                   int(candles['time'][-i] * 1000) + int(binance_intervals_to_seconds(interval)) * 1000 - 1,
                                   format_float_in_standard_form(candles['amount'][-i])])
            return result
        elif "KUCOIN" in self.exchange:
            # API Note: Candles with 0 volume are skipped e.g if requesting the latest 3 candles but one of the candles
            # has 0 volume, the API skips the 0 volume candle and returns the last 3 candles with volume in. This can
            # cause gaps in the 'start_time' values in the candles data and retrieves older data than asked so is
            # unwanted behaviour for our function.
            result = []
            candles = self.client_kucoin_market.get_kline_data(symbol=symbol, granularity=binance_intervals_to_kucoin_intervals(interval), begin_t=startTime)
            if isinstance(candles, dict):  # API returns dict: '{'code': '200000', 'data': []}' if no data
                return []
            # if specifying a start time, sometimes the first candle from API is a later candle with volume because of above feature
            if startTime is not None:
                start_time_pointer = startTime
                received_start_time = int(candles[0][0])
                KUCOIN_KLINE_TRIES = 5
                kucoin_try_count = 0
                while received_start_time > startTime and kucoin_try_count < KUCOIN_KLINE_TRIES:
                    start_time_pointer = start_time_pointer - 199*(int(binance_intervals_to_seconds(interval)) * 1000)
                    older_candles = self.client_kucoin_market.get_kline_data(symbol=symbol, granularity=binance_intervals_to_kucoin_intervals(interval), begin_t=start_time_pointer)
                    older_candles = [c for c in older_candles if int(c[0]) < received_start_time]
                    if older_candles:
                        received_start_time = int(older_candles[0][0])
                        # print(f'OLDER CANDLES {older_candles}')
                        candles = older_candles + candles
                    kucoin_try_count += 1
                if kucoin_try_count == KUCOIN_KLINE_TRIES:
                    print(f'KUCOIN WARNING: {symbol} {interval} requested klines from {startTime} but unable to get any klines older than {received_start_time}')
            prev_candle = None
            # fill in time gaps with '0' volume duplicates of previous candle
            for kline in candles:
                if prev_candle is not None:
                    while prev_candle[6] + 1 != int(kline[0]):
                        next_candle = make_cloned_zero_vol_candle(prev_candle, interval)
                        result.append(next_candle)
                        prev_candle = next_candle
                        # print(f'added cloned candle {prev_candle}')
                prev_candle = [int(kline[0]),
                               format_float_in_standard_form(kline[1]),
                               format_float_in_standard_form(kline[2]),
                               format_float_in_standard_form(kline[3]),
                               format_float_in_standard_form(kline[4]),
                               format_float_in_standard_form(kline[5]),
                               int(kline[0]) + int(binance_intervals_to_seconds(interval)) * 1000 - 1,
                               str(round(Decimal(kline[5]) * ((Decimal(kline[2])+Decimal(kline[3]))/2) * self.precisionQuantityDict[symbol], 2))]
                result.append(prev_candle)
                # print(f'added actual candle {prev_candle}')
            # need to add on missing '0' volume candles until current time (if any)
            now = datetime.now()
            if binance_intervals_to_kucoin_intervals(interval) <= 60:
                current_start_time = now - timedelta(minutes=now.minute % binance_intervals_to_kucoin_intervals(interval), seconds=now.second, microseconds=now.microsecond)
            elif binance_intervals_to_kucoin_intervals(interval) == 1440:
                current_start_time = now - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
            else:
                current_start_time = now - timedelta(days=now.day, hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
            while prev_candle[0] != current_start_time.timestamp() * 1000:
                next_candle = make_cloned_zero_vol_candle(prev_candle, interval)
                # print(f'adding extra candle {next_candle}')
                result.append(next_candle)
                prev_candle = next_candle
            # only return candles from specified start_time or the most latest asked for
            if startTime is not None:
                result = [c for c in result if c[0] >= startTime]
                return result[:limit]
            return result[-limit:]
        elif "CAPITAL" in self.exchange or "IG" in self.exchange:
            # CAPITAL Klines seem to be delayed by around 20 seconds, may also be gaps in candles if no volume traded.
            # New candles may not be made on time until volume shows up
            # IG only gives last 20 klines in a single call, 60 stored
            if "CAPITAL" in self.exchange:
                client = self.client_capital
            elif "IG" in self.exchange:
                client = self.client_ig
            result = []
            result_asks = []
            if startTime is not None:
                if "CAPITAL" in self.exchange:
                    # CAPITAL takes UTC time
                    startTime = datetime.utcfromtimestamp(startTime/1000).strftime(CAPITAL_DATETIME_STRING_FORMAT)
                else:
                    # IG takes time in local(?)
                    startTime = datetime.fromtimestamp(startTime / 1000).strftime(CAPITAL_DATETIME_STRING_FORMAT)
            if endTime is not None:
                if "CAPITAL" in self.exchange:
                    endTime = datetime.utcfromtimestamp(endTime/1000).strftime(CAPITAL_DATETIME_STRING_FORMAT)
                else:
                    endTime = datetime.fromtimestamp(endTime / 1000).strftime(CAPITAL_DATETIME_STRING_FORMAT)
            candles = client.get_klines(epic=symbol, resolution=binance_intervals_to_capital_intervals(interval), start=startTime, end=endTime, limit=limit)['prices']
            for kline in candles:
                dt = datetime.strptime(kline['snapshotTimeUTC'], CAPITAL_DATETIME_STRING_FORMAT)
                kline_start_time = int(dt.replace(tzinfo=timezone.utc).timestamp()*1000)
                try:
                    result.append([kline_start_time,
                                   format_float_in_standard_form(kline['openPrice']['bid']),
                                   format_float_in_standard_form(kline['highPrice']['bid']),
                                   format_float_in_standard_form(kline['lowPrice']['bid']),
                                   format_float_in_standard_form(kline['closePrice']['bid']),
                                   format_float_in_standard_form(kline['lastTradedVolume']),
                                   kline_start_time + int(binance_intervals_to_seconds(interval)) * 1000 - 1
                                   ])
                    result_asks.append([kline_start_time,
                                   format_float_in_standard_form(kline['openPrice']['ask']),
                                   format_float_in_standard_form(kline['highPrice']['ask']),
                                   format_float_in_standard_form(kline['lowPrice']['ask']),
                                   format_float_in_standard_form(kline['closePrice']['ask']),
                                   format_float_in_standard_form(kline['lastTradedVolume']),
                                   kline_start_time + int(binance_intervals_to_seconds(interval)) * 1000 - 1
                                   ])
                except KeyError:
                    continue
            return result, result_asks
        elif "PHEMEX" in self.exchange:
            # note candles are delayed by 1 min
            result = []
            if endTime is None:
                endTime = ''
            else:
                endTime = int(endTime/1000)
            if startTime is None:
                startTime = ''
            else:
                startTime = int(startTime/1000)
            candles = self.client_phemex.query_kline(symbol=symbol, resolution=binance_intervals_to_seconds(interval), limit=limit, from_time=startTime, to_time=endTime)['rows']
            if startTime == '':
                candles.reverse()
            for kline in candles:
                result.append([int(kline[0]*1000),
                              format_float_in_standard_form(Decimal(str(kline[3])) * Decimal('0.0001')),
                              format_float_in_standard_form(Decimal(str(kline[4])) * Decimal('0.0001')),
                              format_float_in_standard_form(Decimal(str(kline[5])) * Decimal('0.0001')),
                              format_float_in_standard_form(Decimal(str(kline[6])) * Decimal('0.0001')),
                              format_float_in_standard_form(Decimal(str(kline[7]))),
                              int(kline[0]*1000) + int(binance_intervals_to_seconds(interval))*1000 - 1,
                              format_float_in_standard_form(Decimal(str(kline[8])) * Decimal('0.0001'))])  # estimated volume in USD
            return result[-limit:]
        elif "BITRUE" in self.exchange:
            # not does not return current incomplete candle
            result = []
            candles = self.client_bitrue.get_klines(contractName=symbol, interval=binance_intervals_to_bitrue_intervals(interval), limit=min(300, limit))
            for kline in reversed(candles):
                result.append([kline['idx'],
                               kline['open'],
                               kline['high'],
                               kline['low'],
                               kline['close'],
                               str(Decimal(kline['vol']) * self.precisionQuantityDict[symbol]),
                               kline['idx'] + int(binance_intervals_to_seconds(interval)) * 1000 - 1,
                               str(round(Decimal(kline['vol']) * self.precisionQuantityDict[symbol] * ((Decimal(kline['high'])+Decimal(kline['low']))/2), 2))  # estimated volume in USD
                               ])
            if startTime is not None:
                result = [k for k in result if k[0] >= startTime]
            if endTime is not None:
                result = [k for k in result if k[6] < endTime]
            return result
        elif "BINGX" in self.exchange:
            # Note: daily candles are in UTC+8
            # Does not get latest candle, described below
            result = []
            limit = min(1440, limit)
            current_time = int(time.time()*1000)
            latest_kline = None
            if startTime is None:
                startTime = current_time - binance_intervals_to_seconds(interval) * 1000 * limit
            if endTime is None:
                endTime = current_time
                # doesnt get latest candle because endpoint for query_latest_kline() is unreliable as returns error often
                # latest_kline = self.client_bingx.query_latest_kline(symbol=symbol, klineType=binance_intervals_to_bingx_intervals(interval))['kline']
            candles = self.client_bingx.query_kline_history(symbol=symbol, klineType=binance_intervals_to_bingx_intervals(interval), startTs=startTime, endTs=endTime)['klines']
            if latest_kline is not None:
                if len(candles) > 0:
                    last_candle_time = candles[-1]['ts']
                    if latest_kline['ts'] != last_candle_time:
                        candles.append(latest_kline)
                        candles = candles[-limit:]
                else:
                    candles.append(latest_kline)
            for kline in candles:
                op = round_interval_nearest(kline['open'], self.precisionPriceDict[symbol])
                hi = round_interval_nearest(kline['high'], self.precisionPriceDict[symbol])
                lo = round_interval_nearest(kline['low'], self.precisionPriceDict[symbol])
                cl = round_interval_nearest(kline['close'], self.precisionPriceDict[symbol])
                vol = Decimal(str(kline['volume']))
                result.append([kline['ts'],
                               str(op),
                               str(hi),
                               str(lo),
                               str(cl),
                               str(vol),
                               kline['ts'] + int(binance_intervals_to_seconds(interval)) * 1000 - 1,
                               str(round(vol * ((hi+lo)/2), 2))  # estimated volume in USD
                               ])
            return result
        elif "XT" in self.exchange:
            result = []
            klines = self.client_xt.get_kline(symbol=symbol, interval=interval, startTime=startTime, endTime=endTime, limit=limit)
            for kline in klines:
                result.append([int(kline['t']),
                               str(kline['o']),
                               str(kline['h']),
                               str(kline['l']),
                               str(kline['c']),
                               str(kline['v']),
                               int(kline['t']) + int(binance_intervals_to_seconds(interval)) * 1000 - 1,
                               ])
            return list(reversed(result))

    @tries_wrapper
    def futures_get_position(self, symbol=None):
        """
        :return: position or positions of all symbols if no symbol is provided
        with symbol provided, no active position open    -> 0 initialised dict
        with no symbol provided, no active positions open-> empty array
        [
            {
                "entryPrice": str,
                "positionAmt": str,
                "symbol": str,
                "unRealizedProfit": str
            }
        ]
        """
        def zero_initialised_dict():
            if symbol is None:
                raise Exception("Need a symbol provided!")
            return {"entryPrice": '0',
                    "positionAmt": '0', "symbol": symbol,
                    "unRealizedProfit": '0'}

        if self.exchange == "BINANCE":
            if symbol:
                return self.client_binance.futures_position_information(symbol=symbol)
            else:
                return [x for x in self.client_binance.futures_position_information() if float(x['positionAmt']) != 0]
        elif "FTX" in self.exchange:
            result = []
            if symbol:
                positions = [x for x in self.client_ftx.get_positions() if x and x['size'] != 0 and x['future'] == symbol]
            else:
                positions = [x for x in self.client_ftx.get_positions() if x and x['size'] != 0]
            if positions:
                for position in positions:
                    entry_price = position['recentAverageOpenPrice']
                    if Decimal(str(entry_price)) % self.precisionPriceDict[symbol] != 0:
                        self.logger.writeline(f"{symbol} ERROR FTX position entry price calculation error, got entry_price {entry_price}")
                        entry_price = round_interval_nearest(entry_price, self.precisionPriceDict[symbol])
                        # raise Exception(f"{symbol} FTX position entry price calculation ERROR, got entry_price {entry_price}")
                    if not entry_price:
                        entry_price = '0'
                    position_amt = position['netSize']
                    symbol = position['future']
                    unRealizedProfit = position['unrealizedPnl']
                    result.append({"entryPrice": format_float_in_standard_form(entry_price),
                                   "positionAmt": format_float_in_standard_form(position_amt), "symbol": symbol,
                                   "unRealizedProfit": format_float_in_standard_form(unRealizedProfit)})
            elif symbol:
                result.append(zero_initialised_dict())
            return result
        elif "OKEX" in self.exchange:
            result = []
            positions = self.client_okex.get_positions("SWAP", symbol)
            if isinstance(positions, dict):  # if only one position if found, OKEX api returns it as a dict instead of a list
                positions = [positions]
            if symbol:
                result.append(self.process_okex_position_to_binance_position(positions, symbol))
            else:
                for position in positions:
                    result.append(self.process_okex_position_to_binance_position(position, symbol))
            return result
        elif "GATE" in self.exchange:
            result = []
            positions = []
            if symbol:
                try:
                    position = self.client_gate.get_position(settle="usdt", contract=symbol, _request_timeout=(self.timeout, self.timeout))
                    if position.size == 0:
                        result.append(zero_initialised_dict())
                    else:
                        result.append({"entryPrice": position.entry_price,
                                       "positionAmt": str(position.size * self.precisionQuantityDict[position.contract]), "symbol": position.contract,
                                       "unRealizedProfit": position.unrealised_pnl})
                except GateApiException as e:
                    if e.label == "POSITION_NOT_FOUND":
                        result.append(zero_initialised_dict())
                    else:
                        raise e
            else:
                positions = self.client_gate.list_positions(settle='usdt', _request_timeout=(self.timeout, self.timeout))
            for position in positions:
                if position.size != 0:
                    result.append({"entryPrice": position.entry_price,
                                   "positionAmt": str(position.size * self.precisionQuantityDict[position.contract]), "symbol": position.contract,
                                   "unRealizedProfit": position.unrealised_pnl})
            return result
        elif "MEXC" in self.exchange:
            result = []
            positions = self.client_mexc.get_open_positions(symbol=symbol)
            if not positions and symbol is not None:
                result.append(zero_initialised_dict())
            for position in positions:
                result.append(self.process_mexc_position_to_binance(position))
            return result
        elif "BYBIT" in self.exchange:
            result = []
            positions = self.client_bybit.my_position(symbol=symbol)
            if symbol is not None:
                for position in positions:
                    if position['size'] != 0:
                        result.append(self.process_bybit_position_to_binance(position))
                if not result and symbol is not None:
                    result.append(zero_initialised_dict())
            else:
                # bybit API returns different structure if no symbol is provided
                for position in positions:
                    result.append(self.process_bybit_position_to_binance(position))
            return result
        elif "IG" in self.exchange:
            result = []
            positions = self.client_ig.fetch_open_positions()['positions']
            if not positions and symbol is not None:
                return [zero_initialised_dict()]
            if symbol is not None:
                for position in positions:
                    if position['market']['epic'] == symbol:
                        result.append(self.process_ig_position_to_binance(position))
            else:
                for position in positions:
                    result.append(self.process_ig_position_to_binance(position))
            return result
        elif "CAPITAL" in self.exchange:
            result = []
            positions = self.client_capital.get_positions()['positions']
            if symbol is not None:
                # collect all positions of a symbol and combine into one
                position_list = []
                for position in positions:
                    if position['market']['epic'] == symbol:
                        position_list.append(self.process_ig_position_to_binance(position))
                if len(position_list) >= 2:
                    total_position_size = sum([Decimal(x['entryPrice']) * Decimal(x['positionAmt']) for x in position_list])
                    total_position_amt = sum([Decimal(x['positionAmt']) for x in position_list])
                    avgEntryPrice = round_interval_nearest(total_position_size / total_position_amt, self.precisionPriceDict[symbol])
                    result.append({'entryPrice': str(avgEntryPrice),
                                   'positionAmt': str(total_position_amt),
                                   'symbol': symbol,
                                   'unRealizedProfit': str(sum([Decimal(x['unRealizedProfit']) for x in position_list]))})
                else:
                    result += position_list
            else:
                for position in positions:
                    result.append(self.process_ig_position_to_binance(position))
            if not result and symbol is not None:
                return [zero_initialised_dict()]
            return result
        elif "PHEMEX" in self.exchange:
            result = []
            positions = self.client_phemex.query_account_n_positions('USD')['positions']
            positions = [p for p in positions if p['size'] != 0]
            for position in positions:
                if symbol is None or position['symbol'] == symbol:
                    result.append(self.process_phemex_position_to_binance(position))
            if not result and symbol is not None:
                result.append(zero_initialised_dict())
            return result
        elif "BINGX" in self.exchange:
            result = []
            positions = self.client_bingx.get_positions(symbol)['positions']
            if positions:
                for position in positions:
                    if symbol is None or position['symbol'] == symbol:
                        result.append(self.process_bingx_position_to_binance(position))
            if not result and symbol is not None:
                result.append(zero_initialised_dict())
            return result

    @tries_wrapper
    def futures_account_balance(self):
        """
        Gets balances of all assets in account
        :return:
        [
            {
            asset: str,
            balance: str
            }
        ]
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_account_balance()
        elif "FTX" in self.exchange:
            result = []
            for asset in self.client_ftx.get_balances():
                result.append({"asset": asset['coin'], "balance": format_float_in_standard_form(asset['total'])})
            return result
        elif "OKEX" in self.exchange:
            result = []
            for asset in self.client_okex.get_account()['details']:
                result.append({"asset": asset['ccy'], "balance": asset['eq']})
            return result
        elif "GATE" in self.exchange:
            result = []
            settle_currencies = ['usdt']
            for cur in settle_currencies:
                res = self.client_gate.list_futures_accounts(settle=cur, _request_timeout=(self.timeout, self.timeout))
                result.append({"asset": res.currency, "balance": res.total})
            return result
        elif "MEXC" in self.exchange:
            result = []
            assets = self.client_mexc.get_account_assets()
            for asset in assets:
                result.append({"asset": asset['currency'], "balance": format_float_in_standard_form(asset['equity'])})
            return result
        elif "BYBIT" in self.exchange:
            result = []
            assets = self.client_bybit.get_wallet_balance()[0]['coin']
            for asset in assets:
                result.append({"asset": asset['coin'], "balance": format_float_in_standard_form(asset['equity'])})
            return result
        elif "IG" in self.exchange:
            accounts = self.client_ig.fetch_accounts()['accounts']
            for account in accounts:
                if self.client_ig.subaccount is None and account['preferred']:
                    return [{"asset": account['currency'], "balance": format_float_in_standard_form(account['balance']['balance'])}]
                elif account['accountName'] == self.client_ig.subaccount:
                    return [{"asset": account['currency'], "balance": format_float_in_standard_form(account['balance']['balance'])}]
        elif "CAPITAL" in self.exchange:
            accounts = self.client_capital.get_account_info()['accounts']
            for account in accounts:
                if self.client_capital.subaccount is None and account['preferred']:
                    return [{"asset": account['currency'], "balance": format_float_in_standard_form(account['balance']['balance'])}]
                elif account['accountName'] == self.client_capital.subaccount:
                    return [{"asset": account['currency'], "balance": format_float_in_standard_form(account['balance']['balance'])}]
        elif "PHEMEX" in self.exchange:
            # currently only returns main account balances, is there a way to use subaccounts from API?
            result = []
            accounts = self.client_phemex.query_client_and_wallets()
            main_account = [a for a in accounts if a['parentId'] == 0][0]
            assets = main_account['userMarginVo']
            for asset in assets:
                result.append({"asset": asset['currency'], "balance": asset['accountBalance']})
            return result
        elif "BINGX" in self.exchange:
            result = []
            account = self.client_bingx.get_account_asset_information('USDT')['account']
            result.append({"asset": account['currency'], "balance": account['balance']})
            return result

    @tries_wrapper
    def binance_futures_get_multi_margin_assets(self):
        """BINANCE ONLY
        gets the assets that are able to be used as margin for multi-margin asset mode
        :return: list of multi-margin assets
        """
        if self.exchange == "BINANCE":
            assets = self.client_binance.futures_account()['assets']
            result = []
            for asset in assets:
                if asset['marginAvailable']:
                    result.append(asset['asset'])
            return result
        else:
            raise Exception("binance_futures_get_multi_margin_assets is a BINANCE only function!")

    @tries_wrapper
    def futures_get_balance(self):
        """
        Gets total collateral equity (margin balance + unrealised pnl) for futures trading
        for Binance, utilises multi-margin mode to get total of all available assets
        :return: for BINANCE: total margin of all multi-margin assets
        for FTX: USD equity
        for OKEX: USDT equity
        for GATE: USDT equity
        for MEXC: USDT equity
        for BYBIT: USDT equity
        for IG: GBP equity
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_account()['totalMarginBalance']
        elif "FTX" in self.exchange:
            balances = self.client_ftx.get_balances()
            for balance in balances:
                if balance['coin'] == 'USD':
                    return format_float_in_standard_form(balance['total'])
        elif "OKEX" in self.exchange:
            return self.client_okex.get_account("USDT")['details'][0]['eq']
        elif "GATE" in self.exchange:
            ac_info = self.client_gate.list_futures_accounts(settle="usdt", _request_timeout=(self.timeout, self.timeout))
            return str(Decimal(ac_info.total) + Decimal(ac_info.unrealised_pnl))
        elif "MEXC" in self.exchange:
            return format_float_in_standard_form(self.client_mexc.get_account_asset("USDT")['equity'])
        elif "BYBIT" in self.exchange:
            return format_float_in_standard_form(self.client_bybit.get_wallet_balance(coin="USDT")[0]["totalEquity"])
        elif "IG" in self.exchange:
            accounts = self.client_ig.fetch_accounts()['accounts']
            for account in accounts:
                if self.client_ig.subaccount is None and account['preferred']:
                    return format_float_in_standard_form(account['balance']['balance'] + account['balance']['profitLoss'])
                elif account['accountName'] == self.client_ig.subaccount:
                    return format_float_in_standard_form(account['balance']['balance'] + account['balance']['profitLoss'])
        elif "CAPITAL" in self.exchange:
            accounts = self.client_capital.get_account_info()['accounts']
            for account in accounts:
                if self.client_capital.subaccount is None and account['preferred']:
                    return format_float_in_standard_form(account['balance']['balance'] + account['balance']['profitLoss'])
                elif account['accountName'] == self.client_capital.subaccount:
                    return format_float_in_standard_form(account['balance']['balance'] + account['balance']['profitLoss'])
        elif "PHEMEX" in self.exchange:
            balance = [b for b in self.futures_account_balance() if b['asset'] == 'USD'][0]['balance']
            positions_unrealised = [Decimal(p['unRealizedProfit']) for p in self.futures_get_position()]
            return str(Decimal(balance) + sum(positions_unrealised))
        elif "BINGX" in self.exchange:
            equity = self.client_bingx.get_account_asset_information("USDT")['account']['equity']
            return str(equity)

    @tries_wrapper
    def futures_get_total_balance(self):
        """
        Gets total margin wallet balance (just margin balance without unrealised pnl) for futures trading
        for Binance, utilises multi-margin mode to get total of all available assets
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_account()['totalWalletBalance']
        elif "FTX" in self.exchange:
            balances = self.client_ftx.get_balances()
            for balance in balances:
                if balance['coin'] == 'USD':
                    equity = balance['total']
            total_unrealised_pnl = 0
            for position in self.client_ftx.get_positions():
                if position['size'] != 0.0:
                    total_unrealised_pnl += position['recentPnl']
            return str(format_float_in_standard_form(equity - total_unrealised_pnl))
        elif "OKEX" in self.exchange:
            return self.client_okex.get_account("USDT")['details'][0]['cashBal']
        elif "GATE" in self.exchange:
            return self.client_gate.list_futures_accounts(settle="usdt", _request_timeout=(self.timeout, self.timeout)).total
        elif "MEXC" in self.exchange:
            return format_float_in_standard_form(self.client_mexc.get_account_asset("USDT")['cashBalance'])
        elif "BYBIT" in self.exchange:
            return format_float_in_standard_form(self.client_bybit.get_wallet_balance(coin="USDT")[0]['coin'][0]["walletBalance"])
        elif "IG" in self.exchange:
            return self.futures_account_balance()[0]['balance']
        elif "CAPITAL" in self.exchange:
            return self.futures_account_balance()[0]['balance']
        elif "PHEMEX" in self.exchange:
            return [b for b in self.futures_account_balance() if b['asset'] == 'USD'][0]['balance']
        elif "BINGX" in self.exchange:
            balance = self.client_bingx.get_account_asset_information("USDT")['account']['balance']
            return str(balance)

    @tries_wrapper
    def futures_create_order(self, symbol, side, type=None, price=None, quantity=None, reduceOnly=None,
                             timeInForce=None, recvWindow=None, newClientOrderId=None, stopPrice=None):
        """
        :param quantity: denoted in the cryptocurrency
        :return:
        {
            "clientOrderId": "testOrder",
            "executedQty": "0",
            "orderId": 22542179,
            "avgPrice": "0.00000",
            "origQty": "10",
            "price": "0",
            "reduceOnly": false,
            "side": "BUY",
            "status": "NEW",
            "stopPrice": "9300",        // please ignore when order type is TRAILING_STOP_MARKET
            "symbol": "BTCUSDT",
            "type": "TRAILING_STOP_MARKET",
        }
        """
        if newClientOrderId is None:
            newClientOrderId = str(int(time.time()))

        if self.exchange == "BINANCE":
            return self.client_binance.futures_create_order(symbol=symbol,
                                                            side=side,
                                                            type=type,
                                                            price=price,
                                                            quantity=quantity,
                                                            reduceOnly=reduceOnly,
                                                            timeInForce=timeInForce,
                                                            recvWindow=recvWindow,
                                                            newClientOrderId=newClientOrderId,
                                                            stopPrice=stopPrice)
        elif "FTX" in self.exchange:
            # Note that Binance and FTX have same 'side' and 'type' specifications but FTX defines them in lower case
            # e.g. on Binance, side = "BUY" | "SELL", on FTX side = "buy" | "sell". Therefore we .lower() these params
            # Binance valid order statuses:
            # NEW
            # PARTIALLY_FILLED
            # FILLED
            # CANCELED
            # REJECTED
            # EXPIRED
            if timeInForce == "GTX":  # on Binance GTX means Good Till Crossing (or post only)
                postOnly = True
            else:
                postOnly = False
            if reduceOnly is None:
                reduceOnly = False
            # Use str representation of price/quantity even though code complains because the FTX api allows it
            # even if it expects floats
            if stopPrice is None:
                order = self.client_ftx.place_order(market=symbol,
                                                    side=side.lower(),
                                                    type=type.lower(),
                                                    price=str(price),
                                                    size=str(quantity),
                                                    reduce_only=reduceOnly,
                                                    post_only=postOnly,
                                                    client_id=newClientOrderId)
                return process_ftx_order_to_binance(order)
            elif stopPrice:
                if type == self.ORDER_TYPE_STOP:
                    order = self.client_ftx.place_conditional_order(market=symbol,
                                                                    side=side.lower(),
                                                                    type=type.lower(),
                                                                    limit_price=str(price),
                                                                    trigger_price=str(stopPrice),
                                                                    size=str(quantity),
                                                                    reduce_only=reduceOnly)
                    # Note FTX does not allow clientId for stop/stop market orders
                elif type == self.ORDER_TYPE_STOP_MARKET:
                    order = self.client_ftx.place_conditional_order(market=symbol,
                                                                    side=side.lower(),
                                                                    type="stop",
                                                                    trigger_price=str(stopPrice),
                                                                    size=str(quantity),
                                                                    reduce_only=reduceOnly)
                if order['status'] == 'open':
                    status = "NEW"
                elif order['status'] == 'triggered':
                    status = "FILLED"
                else:
                    status = "EXPIRED"
                return {"orderId": order['id'],
                        "symbol": order['market'],
                        "price": order['orderPrice'],
                        "stopPrice": format_float_in_standard_form(order['triggerPrice']),
                        "side": order['side'].upper(),
                        "type": order['type'].upper(),
                        "status": status,
                        "reduceOnly": order['reduceOnly'],
                        "origQty": format_float_in_standard_form(order['size'])}
        elif "OKEX" in self.exchange:
            # 'sz' must be an integer multiple of lot size - we must convert quantity (denoted in crypto) to an integer
            # if the instrument is USDT margined, lot_size is denoted in the cryptocurrency
            # else if the instrument is USD margined, lot_size is denoted in USD
            if "USDT" in symbol:
                sz = int(math.floor(Decimal(str(quantity)) / self.precisionQuantityDict[symbol]))
                # origQty = sz * self.precisionQuantityDict[symbol]
            elif type is not self.ORDER_TYPE_MARKET and type is not self.ORDER_TYPE_STOP_MARKET:
                # this case means that lot_size is in USD, to find 'sz' we must use the price
                sz = int(math.floor((Decimal(str(quantity)) * Decimal(str(price))) / self.precisionQuantityDict[symbol]))
                # origQty = (sz * self.precisionQuantityDict[symbol]) / (Decimal(str(quantity)) * Decimal(str(price)))
            else:
                # TODO: what if price is None (e.g. for a market order)? How to determine sz in this case?
                raise Exception("OKEX client cannot determine 'sz' for order!")
            if sz == 0:
                raise Exception("OKEX client too small order size!")

            if timeInForce == "GTX":  # on Binance GTX means Good Till Crossing (or post only)
                ordType = "post_only"
            else:
                ordType = type.lower()
            if self.okex_pos_mode == 'net':
                posSide = 'net'
            else:
                if reduceOnly is None or reduceOnly is False:
                    if side == self.SIDE_BUY:
                        posSide = 'long'
                    else:
                        posSide = 'short'
                else:
                    if side == self.SIDE_BUY:
                        posSide = 'short'
                    else:
                        posSide = 'long'
            orderId = None
            if stopPrice is None:
                # need to strip non alpha-numeric characters and truncate to 32 length for the clientID
                clOrdId = ''.join(ch for ch in newClientOrderId if ch.isalnum())[:32]
                order = self.client_okex.place_order(instId=symbol,
                                                     tdMode="cross",
                                                     ccy="USDT",
                                                     side=side.lower(),
                                                     posSide=posSide,
                                                     ordType=ordType,
                                                     sz=str(sz),
                                                     px=format(price, f".{abs(self.precisionPriceDict[symbol].as_tuple().exponent)}f"),
                                                     clOrdId=clOrdId
                                                     )
                orderId = order['ordId']
            elif stopPrice:
                if type == self.ORDER_TYPE_STOP:
                    orderPx = str(price)
                elif type == self.ORDER_TYPE_STOP_MARKET:
                    orderPx = '-1'  # '-1' means that the order will be executed at market price
                else:
                    raise Exception("Incorrect order type to have a stop price!")
                order = self.client_okex.place_algo_order(instId=symbol,
                                                          tdMode="cross",
                                                          ccy="USDT",
                                                          side=side.lower(),
                                                          posSide=posSide,
                                                          sz=str(sz),
                                                          ordType="conditional",
                                                          slTriggerPx=str(stopPrice),
                                                          slOrdPx=orderPx
                                                          )
                orderId = order['algoId']
            if self.okex_pos_mode == 'net' and reduceOnly:
                self.reduce_only_orders[orderId] = int(time.time())
            return self.futures_get_order(symbol=symbol, orderId=orderId)
        elif "GATE" in self.exchange:
            if timeInForce == "GTX":
                time_in_force = "poc"
            else:
                time_in_force = "gtc"
            if reduceOnly is None:
                reduceOnly = False
            size = int(math.floor(Decimal(str(quantity)) / self.precisionQuantityDict[symbol]))
            if size == 0:
                raise Exception("GATE client too small order size!")
            if side == self.SIDE_SELL:
                size = size * -1
            if type == self.ORDER_TYPE_MARKET or type == self.ORDER_TYPE_STOP_MARKET:
                price = 0
                time_in_force = "ioc"
            else:
                price = price
            if stopPrice is None:
                # need to strip non alpha-numeric characters and truncate to 26 length for the clientID
                clOrdId = "t-" + ''.join(ch for ch in newClientOrderId if ch.isalnum())[:26]
                futures_order = FuturesOrder(contract=symbol, size=size, price=format_float_in_standard_form(float(price)), tif=time_in_force, reduce_only=reduceOnly, text=clOrdId)
                order = self.client_gate.create_futures_order(settle="usdt", futures_order=futures_order, _request_timeout=(self.timeout, self.timeout))
                return self.process_gate_order_to_binance(order)
            elif stopPrice:
                if type == self.ORDER_TYPE_STOP_MARKET:
                    price = str(0)
                elif type == self.ORDER_TYPE_STOP:
                    price = str(price)
                rule = 1 if side == self.SIDE_BUY else 2
                body = FuturesPriceTriggeredOrder(initial={"contract": symbol, "size": size, "price": price, "reduce_only": reduceOnly, "tif": time_in_force, "text": "api"},
                                                  trigger={"price": str(stopPrice), "rule": rule})
                order = self.client_gate.create_price_triggered_order(settle="usdt", futures_price_triggered_order=body, _request_timeout=(self.timeout, self.timeout))
                return self.futures_get_order(symbol=symbol, orderId=order.id)
        elif "MEXC" in self.exchange:
            # orderType, 1:price limited order, 2:Post Only Maker, 3:transact or cancel instantly,
            # 4 : transact completely or cancel completely, 5:market orders,6 convert market price to current price
            type = 1
            if timeInForce == "GTX":
                type = 2
            if type == self.ORDER_TYPE_MARKET:
                type = 5
            size = int(math.floor(Decimal(str(quantity)) / self.precisionQuantityDict[symbol]))
            if size == 0:
                raise Exception("MEXC client too small order size!")
            # order_side 1 open long ,2close short,3open short ,4 close l
            if side == self.SIDE_BUY and not reduceOnly:
                order_side = 1
            elif side == self.SIDE_BUY and reduceOnly is True:
                order_side = 2
            elif side == self.SIDE_SELL and reduceOnly is True:
                order_side = 4
            elif side == self.SIDE_SELL and not reduceOnly:
                order_side = 3
            order_id = self.client_mexc.submit_order(symbol=symbol, price=str(price), vol=size, side=order_side, type_=type, open_type=2, external_oid=newClientOrderId[:32])
            order = self.futures_get_order(symbol=symbol, orderId=order_id)
            return order
        elif "BYBIT" in self.exchange:
            # NOTE: Bybit heavily limits large orders so have to split them up when submitting. For purposes of the bot, only returns last order
            if timeInForce == "GTX":  # on Binance GTX means Good Till Crossing (or post only)
                timeInForce = "PostOnly"
            else:
                timeInForce = "GTC"
            repeat_order_number = 0
            if side == self.SIDE_BUY:
                self.futures_cancel_open_buy_orders(symbol)
            else:
                self.futures_cancel_open_sell_orders(symbol)
            while quantity > self.bybit_symbol_max_quantity[symbol]:
                order_id = self.client_bybit.place_order(side=side, symbol=symbol, order_type=type,
                                                         qty=self.bybit_symbol_max_quantity[symbol],
                                                         price=price, time_in_force=timeInForce, close_on_trigger=False,
                                                         reduce_only=reduceOnly,
                                                         order_link_id=(str(repeat_order_number) + newClientOrderId)[
                                                                       :36])['orderId']
                repeat_order_number += 1
                quantity = quantity - self.bybit_symbol_max_quantity[symbol]
            if quantity > 0:
                order_id = self.client_bybit.place_order(side=side, symbol=symbol, order_type=type, qty=quantity, price=price,
                                                         time_in_force=timeInForce, close_on_trigger=False, reduce_only=reduceOnly,
                                                         order_link_id=(str(repeat_order_number) + newClientOrderId)[:36])['orderId']
            order = self.futures_get_order(symbol=symbol, orderId=order_id)
            return order
        elif "IG" in self.exchange:
            size = Decimal(str(quantity)) / 10000
            # since forex trading does not have reduceOnly, need to manually check current position size
            if reduceOnly:
                position_size = Decimal(str(get_position_size(self.futures_get_position(symbol=symbol)))) / 10000
                if abs(size) > abs(position_size):
                    size = abs(position_size)
                if position_size == 0:
                    self.logger.writeline(f"{symbol} tried to place a reduceOnly order with no current position open!")
                    raise Exception(f"{symbol} tried to place a reduceOnly order with no current position open!")
            currency_code = symbol.split(".")[2][3:]
            order = self.client_ig.create_working_order(currency_code=currency_code, direction=side, epic=symbol, order_type=type, level=float(price), size=float(size), guaranteed_stop=False, time_in_force='GOOD_TILL_CANCELLED', expiry="-", force_open=False)
            if order['status'] == 'OPEN':
                status = "NEW"
            elif order['status'] is None:
                # happens when a limit order would execute immediately
                status = "EXPIRED"
            else:
                status = "EXPIRED"
            return {"orderId": order['dealId'],
                    "symbol": order['epic'],
                    "price": format_float_in_standard_form(order['level']),
                    "stopPrice": format_float_in_standard_form(order['stopLevel']),
                    "side": order['direction'].upper(),
                    "type": type,
                    "status": status,
                    "reduceOnly": reduceOnly,
                    "origQty": format_float_in_standard_form(size)}
        elif "CAPITAL" in self.exchange:
            size = Decimal(str(quantity))
            # since forex trading does not have reduceOnly, need to manually check current position size
            if reduceOnly:
                position_size = Decimal(str(get_position_size(self.futures_get_position(symbol=symbol))))
                if abs(size) > abs(position_size):
                    size = abs(position_size)
                if position_size == 0:
                    self.logger.writeline(f"{symbol} tried to place a reduceOnly order with no current position open!")
                    raise Exception(f"{symbol} tried to place a reduceOnly order with no current position open!")
            deal_ref = self.client_capital.create_order(side=side, epic=symbol, order_type=type, limit=float(price), size=float(size))
            if deal_ref and 'dealReference' in deal_ref:
                deal_ref = deal_ref['dealReference']
            for i in range(10):
                sleep(1)
                confirmation = self.client_capital.get_position_order_confirmation(deal_ref)
                if 'dealStatus' in confirmation and confirmation['dealStatus'] == 'REJECTED':
                    # self.logger.writeline(f'{symbol} deal rejected, resending order')
                    deal_ref = self.client_capital.create_order(side=side, epic=symbol, order_type=type,
                                                                limit=float(price), size=float(size))
                    if deal_ref and 'dealReference' in deal_ref:
                        deal_ref = deal_ref['dealReference']
                order = self.futures_get_order(symbol=symbol, orderId=deal_ref)
                if order and order['status'] != "CANCELLED":
                    return order
            raise Exception(f'CAPITAL client create order error: could not create order (dealReference: {deal_ref} {side}, {symbol}, {size} @{price})')
        elif "PHEMEX" in self.exchange:
            if side == self.SIDE_BUY:
                order_side = "Buy"
            elif side == self.SIDE_SELL:
                order_side = "Sell"
            size = int(math.floor(Decimal(str(quantity)) / self.precisionQuantityDict[symbol]))
            if size == 0:
                raise Exception("PHEMEX too small order size!")
            priceEp = float(Decimal(str(price)) * Decimal('10000')) if price else None
            if type == self.ORDER_TYPE_MARKET:
                ordType = "Market"
            elif type == self.ORDER_TYPE_LIMIT:
                ordType = "Limit"
            elif type == self.ORDER_TYPE_STOP_MARKET:
                ordType = "Stop"
            elif type == self.ORDER_TYPE_STOP:
                ordType = "StopLimit"
            stopPxEp = float(Decimal(str(stopPrice)) * Decimal('10000')) if stopPrice else None
            typeInForce = "GoodTillCancel"
            if timeInForce == self.TIME_IN_FORCE_GTX:
                typeInForce = "PostOnly"
            reduce_only = True if reduceOnly else False
            order = self.client_phemex.place_order({'symbol': symbol, 'clOrdID': newClientOrderId[:40], 'side': order_side,
                                                    'orderQty': size, 'priceEp': priceEp, 'ordType': ordType, 'stopPxEp': stopPxEp,
                                                    'timeInForce': typeInForce, 'reduceOnly': reduce_only})
            return self.process_phemex_order_to_binance(order)
        elif "BINGX" in self.exchange:
            # NOTE: current v1 api does not support client ID's
            if side == self.SIDE_BUY:
                order_side = "Bid"
            else:
                order_side = "Ask"
            if type == self.ORDER_TYPE_MARKET:
                ordType = "Market"
            elif type == self.ORDER_TYPE_LIMIT:
                ordType = "Limit"
            else:
                raise Exception(f"BINGX API currently does not support order type {type}")
            order_action = 'Open' if not reduceOnly else 'Close'
            orderId = self.client_bingx.place_new_order(symbol=symbol, side=order_side, price=price, size=quantity, tradeType=ordType, action=order_action)['orderId']
            return self.futures_get_order(symbol=symbol, orderId=orderId)

    @tries_wrapper
    def futures_get_order(self, symbol, orderId=None, origClientOrderId=None):
        """
        :return:
        {
            "clientOrderId": "testOrder",
            "executedQty": "0",
            "orderId": 22542179,
            "avgPrice": "0.00000",
            "origQty": "10",
            "price": "0",
            "reduceOnly": false,
            "side": "BUY",
            "status": "NEW",
            "stopPrice": "9300",        // please ignore when order type is TRAILING_STOP_MARKET
            "symbol": "BTCUSDT",
            "type": "TRAILING_STOP_MARKET",
            "updateTime": int
        }
        """
        if not orderId and not origClientOrderId:
            raise Exception("No orderId/clientId provided")
        if self.exchange == "BINANCE":
            if orderId:
                return self.client_binance.futures_get_order(symbol=symbol, orderId=orderId)
            elif origClientOrderId:
                return self.client_binance.futures_get_order(symbol=symbol, origClientOrderId=origClientOrderId)
        elif "FTX" in self.exchange:
            # FTX stores normal LIMIT orders and STOP/STOP-MARKET orders separately, API calls
            # are made to different endpoints to retrieve normal and trigger based orders
            if orderId:
                order = process_ftx_order_to_binance(self.client_ftx.get_order_by_order_id(order_id=orderId))
            elif origClientOrderId:
                order = process_ftx_order_to_binance(
                    self.client_ftx.get_order_by_client_id(client_order_id=origClientOrderId))
            if order:
                return order
            else:
                # we need to also check condition orders
                conditional_orders = self.client_ftx.get_conditional_order_history(market=symbol)
                for order in conditional_orders:
                    if order['id'] == orderId:  # clientId does not exist for FTX conditional orders
                        return process_ftx_order_to_binance(order)
        elif "OKEX" in self.exchange:
            if orderId is None:
                orderId = ""
            if origClientOrderId is None:
                origClientOrderId = ""
            order = self.client_okex.get_orders(instId=symbol, ordId=orderId, clOrdId=origClientOrderId)
            if order:
                return self.process_okex_order_to_binance(order)
            # need to check conditional orders
            order = self.client_okex.order_algos_list(algoId=orderId, instType="SWAP", instId=symbol, ordType="conditional")
            if order:
                return self.process_okex_order_to_binance(order)
            order = self.client_okex.order_algos_history(algoId=orderId, instType="SWAP", instId=symbol, ordType="conditional")
            if order:
                return self.process_okex_order_to_binance(order)
        elif "GATE" in self.exchange:
            oid = orderId if orderId else origClientOrderId
            order = self.process_gate_order_to_binance(self.client_gate.get_futures_order(settle="usdt", order_id=oid, _request_timeout=(self.timeout, self.timeout)))
            if order:
                return order
            else:
                return self.process_gate_order_to_binance(self.client_gate.get_price_triggered_order(settle="usdt", order_id=orderId))
        elif "MEXC" in self.exchange:
            if orderId:
                order = self.client_mexc.get_order_by_order_id(orderId)
            else:
                order = self.client_mexc.get_order_by_external_oid(symbol=symbol, external_oid=origClientOrderId)
            return self.process_mexc_order_to_binance(order)
        elif "BYBIT" in self.exchange:
            if orderId is None:
                orderId = ""
            if origClientOrderId is None:
                origClientOrderId = ""
            order = self.client_bybit.query_active_order(symbol=symbol, order_id=orderId, order_link_id=origClientOrderId)[0]
            return self.process_bybit_order_to_binance(order)
        elif "IG" in self.exchange:
            # if an order is returned, it is always open and unfilled, hence 'working order'
            orders = self.client_ig.fetch_working_orders(version='2')
            for order in orders['workingOrders']:
                if order['workingOrderData']['epic'] == symbol and order['workingOrderData']['dealId'] == orderId:
                    dt = datetime.strptime(order['workingOrderData']['createdDateUTC'], CAPITAL_DATETIME_STRING_FORMAT)
                    update_time = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
                    return {
                            "clientOrderId": None,
                            "executedQty": "0",
                            "orderId": orderId,
                            "avgPrice": "0.00000",
                            "origQty": str(order['workingOrderData']['orderSize'] * 10000),
                            "price": str(order['workingOrderData']['orderLevel']),
                            "reduceOnly": None,  # not determinable
                            "side": order['workingOrderData']['direction'],
                            "status": "NEW",
                            "stopPrice": None,
                            "symbol": symbol,
                            "type": order['workingOrderData']['orderType'],
                            "updateTime": update_time
                            }
        elif "CAPITAL" in self.exchange:
            order_status = None
            if orderId[:2] in ['r_', 'o_', 'p_']:
                # sometimes a deal ref is provided, we can use this to get the actual order Id
                confirmation = self.client_capital.get_position_order_confirmation(dealReference=orderId)
                if not confirmation:
                    # may not be ready to retrieve from server, wait and retry...
                    sleep(1)
                    raise Exception(f"CAPITAL unable to get deal confirmation for {orderId}")
                deal_id = confirmation['affectedDeals'][0]['dealId']
                order_status = confirmation['affectedDeals'][0]['status']
            else:
                deal_id = orderId
            if order_status is None or order_status not in ["DELETED", "FULLY_CLOSED"]:
                orders = self.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    if order['orderId'] == deal_id:
                        return order
            #  if above does not return then the order is no longer active or not yet available from API.
            #  FULLY_CLOSED status means FILLED
            if order_status == 'FULLY_CLOSED' or order_status == 'OPENED':
                origQty = confirmation['size']
                price = confirmation['level']
                side = confirmation['direction']
                executedQty = origQty
                avgPrice = price
                status = "FILLED"
            elif order_status == "DELETED":
                origQty = confirmation['size']
                price = confirmation['level']
                side = confirmation['direction']
                executedQty = "0.0"
                avgPrice = "0.0"
                status = "CANCELLED"
            else:
                # unable to obtain original data through only orderId from API, just assume the order was cancelled
                # although it may also not be available to retrieve from API yet.
                origQty = None
                price = None
                side = None
                avgPrice = "0.0"
                status = "CANCELLED"
                executedQty = "0.0"
            return {
                "clientOrderId": None,
                "executedQty": str(executedQty),
                "orderId": orderId,
                "avgPrice": str(avgPrice),
                "origQty": str(origQty),
                "price": str(price),
                "reduceOnly": None,  # not determinable
                "side": side,
                "status": status,
                "stopPrice": None,
                "symbol": symbol,
                "type": None,  # not determinable
                "updateTime": None
            }
        elif "PHEMEX" in self.exchange:
            orders = self.client_phemex.query_order(symbol=symbol, orderId=orderId, cliOrderId=origClientOrderId)
            if orders:
                return self.process_phemex_order_to_binance(orders[0])
            raise Exception(f"PHEMEX Order (orderId '{orderId}' / origClientOrderId '{origClientOrderId}') not found (was it recently made?)")
        elif "BINGX" in self.exchange:
            order = self.client_bingx.query_order(symbol=symbol, orderId=orderId)
            return self.process_bingx_order_to_binance(order, symbol)
        return None

    @tries_wrapper
    def futures_get_open_orders(self, symbol):
        if self.exchange == "BINANCE":
            return self.client_binance.futures_get_open_orders(symbol=symbol)
        elif "FTX" in self.exchange:
            normal_orders = list(map(process_ftx_order_to_binance, self.client_ftx.get_open_orders(market=symbol)))
            trigger_orders = list(map(process_ftx_order_to_binance, self.client_ftx.get_conditional_orders(market=symbol)))
            return normal_orders + trigger_orders
        elif "OKEX" in self.exchange:
            orders = self.client_okex.get_order_list(instId=symbol)
            if isinstance(orders, dict):
                # this case happens if only 1 order is returned, it is in a dict but we need it in an array
                orders = [orders]
            normal_orders = list(map(self.process_okex_order_to_binance, orders))
            orders = self.client_okex.order_algos_list(instId=symbol, instType="SWAP", ordType="conditional")
            if isinstance(orders, dict):
                orders = [orders]
            trigger_orders = list(map(self.process_okex_order_to_binance, orders))
            return normal_orders + trigger_orders
        elif "GATE" in self.exchange:
            orders = self.client_gate.list_futures_orders(settle="usdt", contract=symbol, status="open", _request_timeout=(self.timeout, self.timeout))
            return list(map(self.process_gate_order_to_binance, orders))
        elif "MEXC" in self.exchange:
            orders = self.client_mexc.get_open_orders(symbol=symbol)['resultList']
            return list(map(self.process_mexc_order_to_binance, orders))
        elif "BYBIT" in self.exchange:
            orders = self.client_bybit.query_active_order(symbol=symbol)
            return list(map(self.process_bybit_order_to_binance, orders))
        elif "IG" in self.exchange:
            # if an order is returned, it is always open and unfilled, hence 'working order'
            results = []
            orders = self.client_ig.fetch_working_orders(version='2')
            for order in orders['workingOrders']:
                if order['workingOrderData']['epic'] == symbol:
                    dt = datetime.strptime(order['workingOrderData']['createdDateUTC'], CAPITAL_DATETIME_STRING_FORMAT)
                    update_time = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
                    results.append({
                                    "clientOrderId": None,
                                    "executedQty": "0",
                                    "orderId": order['workingOrderData']['dealId'],
                                    "avgPrice": "0.00000",
                                    "origQty": str(order['workingOrderData']['orderSize'] * 10000),
                                    "price": str(order['workingOrderData']['orderLevel']),
                                    "reduceOnly": None,
                                    "side": order['workingOrderData']['direction'],
                                    "status": "NEW",
                                    "stopPrice": None,
                                    "symbol": symbol,
                                    "type": order['workingOrderData']['orderType'],
                                    "updateTime": update_time
                                    })
            return results
        elif "CAPITAL" in self.exchange:
            # if an order is returned, it is always open and unfilled, hence 'working order'
            results = []
            orders = self.client_capital.get_open_oders()
            for order in orders['workingOrders']:
                if order['workingOrderData']['epic'] == symbol:
                    dt = datetime.strptime(order['workingOrderData']['createdDateUTC'][:-4], CAPITAL_DATETIME_STRING_FORMAT)
                    update_time = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
                    results.append({
                        "clientOrderId": None,
                        "executedQty": "0",
                        "orderId": order['workingOrderData']['dealId'],
                        "avgPrice": "0.00000",
                        "origQty": str(order['workingOrderData']['orderSize']),
                        "price": str(order['workingOrderData']['orderLevel']),
                        "reduceOnly": None,
                        "side": order['workingOrderData']['direction'],
                        "status": "NEW",
                        "stopPrice": None,
                        "symbol": symbol,
                        "type": order['workingOrderData']['orderType'],
                        "updateTime": update_time
                    })
            return results
        elif "PHEMEX" in self.exchange:
            orders = self.client_phemex.query_open_orders(symbol)['rows']
            return list(map(self.process_phemex_order_to_binance, orders))
        elif "BINGX" in self.exchange:
            orders = self.client_bingx.query_unfilled_orders(symbol)['orders']
            if orders:
                return list(map(self.process_bingx_order_to_binance, orders))
            else:
                return []

    @tries_wrapper
    def futures_cancel_order(self, symbol, orderID):
        if self.exchange == "BINANCE":
            self.client_binance.futures_cancel_order(symbol=symbol, orderID=orderID)
        elif "FTX" in self.exchange:
            self.client_ftx.cancel_order(order_id=orderID)
        elif "OKEX" in self.exchange:
            # TODO: cancel trigger orders (using algoId=orderID)
            self.client_okex.cancel_order(instId=symbol, ordId=orderID)
        elif "GATE" in self.exchange:
            self.client_gate.cancel_futures_order(settle="usdt", order_id=orderID, _request_timeout=(self.timeout, self.timeout))
        elif "MEXC" in self.exchange:
            self.client_mexc.cancel_orders([orderID])
        elif "BYBIT" in self.exchange:
            self.client_bybit.cancel_active_order(symbol=symbol, order_id=orderID)
        elif "IG" in self.exchange:
            self.client_ig.delete_working_order(deal_id=orderID)
        elif "CAPITAL" in self.exchange:
            if orderID[:2] in ['r_', 'o_', 'p_']:
                # sometimes a deal ref is provided, we can use this to get the actual order Id
                confirmation = self.client_capital.get_position_order_confirmation(dealReference=orderID)
                if not confirmation:
                    # may not be ready to retrieve from server, wait and retry...
                    sleep(1)
                    raise Exception(f"CAPITAL unable to get deal confirmation for {orderID}")
                orderID = confirmation['affectedDeals'][0]['dealId']
            self.client_capital.cancel_order(orderId=orderID)
        elif "PHEMEX" in self.exchange:
            self.client_phemex.cancel_order(symbol=symbol, orderID=orderID)
        elif "BINGX" in self.exchange:
            self.client_bingx.cancel_order(symbol, orderID)

    @tries_wrapper
    def futures_cancel_all_open_orders(self, symbol):
        if self.exchange == "BINANCE":
            self.client_binance.futures_cancel_all_open_orders(symbol=symbol)
        elif "FTX" in self.exchange:
            self.client_ftx.cancel_orders(market_name=symbol)
        elif "OKEX" in self.exchange:
            orders = self.client_okex.get_order_list(instId=symbol)
            if isinstance(orders, dict):
                orders = [orders]
            cancel_list = []
            for order in orders:
                cancel_list.append({"instId": symbol, "ordId": order['ordId']})
            if cancel_list:
                self.client_okex.cancel_multiple_orders(cancel_list)
            orders = self.client_okex.order_algos_list(instId=symbol, instType="SWAP", ordType="conditional")
            if isinstance(orders, dict):
                orders = [orders]
            cancel_list = []
            for order in orders:
                cancel_list.append({"instId": symbol, "algoId": order['algoId']})
            if cancel_list:
                self.client_okex.cancel_algo_order_list(cancel_list)
        elif "GATE" in self.exchange:
            self.client_gate.cancel_futures_orders(settle="usdt", contract=symbol, _request_timeout=(self.timeout, self.timeout))
        elif "MEXC" in self.exchange:
            self.client_mexc.cancel_all_orders(symbol=symbol)
        elif "BYBIT" in self.exchange:
            self.client_bybit.cancel_all_active_orders(symbol=symbol)
        elif "IG" in self.exchange:
            open_orders = self.futures_get_open_orders(symbol=symbol)
            for order in open_orders:
                self.client_ig.delete_working_order(deal_id=order['orderId'])
        elif "CAPITAL" in self.exchange:
            open_orders = self.futures_get_open_orders(symbol=symbol)
            for order in open_orders:
                self.client_capital.cancel_order(orderId=order['orderId'])
        elif "PHEMEX" in self.exchange:
            # note only cancels limit orders, for stop limits and stop losses need to change below
            self.client_phemex.cancel_all_normal_orders(symbol)
        elif "BINGX" in self.exchange:
            open_orders = self.futures_get_open_orders(symbol)
            to_delete_list = [o['orderId'] for o in open_orders]
            if to_delete_list:
                self.client_bingx.cancel_batch_orders(symbol, ','.join(map(str, to_delete_list)))

    @tries_wrapper
    def futures_order_book(self, symbol, limit):
        """
        :return:
        {
            "bids": [
                [
                "4.00000000", // PRICE
                "431.00000000" // QTY
                ]
            ],
            "asks": [
                [
                    "4.00000200",
                    "12.00000000"
                ]
            ]
        }
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_order_book(symbol=symbol, limit=limit)
        elif "FTX" in self.exchange:
            orderbook = self.client_ftx.get_orderbook(symbol, limit)
            return {"asks": [[format_float_in_standard_form(item) for item in sub] for sub in orderbook['asks']],
                    "bids": [[format_float_in_standard_form(item) for item in sub] for sub in orderbook['bids']]}
        elif "OKEX" in self.exchange:
            orderbook = self.client_okex.get_orderbook(instId=symbol, sz=limit)
            if "USDT" in symbol:
                # since the quantity is given in 'sz', need to multiply this with the lot size to give quantity
                return {"asks": list(map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[symbol])], [[item for item in sub[:2]] for sub in orderbook['asks']])),
                        "bids": list(map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[symbol])], [[item for item in sub[:2]] for sub in orderbook['bids']]))}
            else:
                # quantity = sz * cont_size (or lot_size in USD) / price
                return {"asks": list(map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[symbol] / Decimal(x[0]))], [[item for item in sub[:2]] for sub in orderbook['asks']])),
                        "bids": list(map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[symbol] / Decimal(x[0]))], [[item for item in sub[:2]] for sub in orderbook['bids']]))}
        elif "GATE" in self.exchange:
            limit = min(limit, 50)
            orderbook = self.client_gate.list_futures_order_book(settle="usdt", contract=symbol, limit=limit, _request_timeout=(self.timeout, self.timeout))
            return {"asks": list(map(lambda x: [x.p, str(Decimal(x.s) * self.precisionQuantityDict[symbol])], [item for item in orderbook.asks])),
                    "bids": list(map(lambda x: [x.p, str(Decimal(x.s) * self.precisionQuantityDict[symbol])], [item for item in orderbook.bids]))}
        elif "MEXC" in self.exchange:
            orderbook = self.client_mexc.get_contract_depth(symbol=symbol, limit=limit)
            return {"asks": list(map(lambda x: [format_float_in_standard_form(x[0]), str(Decimal(str(x[1])) * self.precisionQuantityDict[symbol])], [[item for item in sub[:2]] for sub in orderbook['asks']])),
                    "bids": list(map(lambda x: [format_float_in_standard_form(x[0]), str(Decimal(str(x[1])) * self.precisionQuantityDict[symbol])], [[item for item in sub[:2]] for sub in orderbook['bids']]))}
        elif "BYBIT" in self.exchange:
            orderbook = self.client_bybit.orderbook(symbol=symbol)
            asks = []
            bids = []
            for obBids in orderbook['b']:
                bids.append([obBids[0], obBids[1]])
            for obAsks in orderbook['a']:
                asks.append([obAsks[0], obAsks[1]])
            return {"asks": asks[:limit], "bids": bids[:limit]}
        elif "IG" in self.exchange:
            # only offers the best bid/ask with unspecified qty
            data = self.client_ig.fetch_market_by_epic(epic=symbol)
            return {"asks": [[data['snapshot']['offer'], 0]], "bids": [[data['snapshot']['bid'], 0]]}
        elif "CAPITAL" in self.exchange:
            # only offers the best bid/ask with unspecified qty
            data = self.client_capital.get_market(epic=symbol)
            return {"asks": [[data['snapshot']['offer'], 0]], "bids": [[data['snapshot']['bid'], 0]]}
        elif "PHEMEX" in self.exchange:
            orderbook = self.client_phemex.query_orderbook(symbol)['book']
            return {"asks": list(map(lambda x: [format_float_in_standard_form(x[0] * 0.0001), str(Decimal(str(x[1])) * self.precisionQuantityDict[symbol])], [[item for item in sub[:2]] for sub in orderbook['asks']]))[:limit],
                    "bids": list(map(lambda x: [format_float_in_standard_form(x[0] * 0.0001), str(Decimal(str(x[1])) * self.precisionQuantityDict[symbol])], [[item for item in sub[:2]] for sub in orderbook['bids']]))[:limit]}
        elif "BINGX" in self.exchange:
            orderbook = self.client_bingx.get_market_depth(symbol, limit)
            return {"asks": [[format_float_in_standard_form(round_interval_nearest(x['p'], self.precisionPriceDict[symbol])), str(Decimal(str(x['v'])))] for x in orderbook['asks']],
                    "bids": [[format_float_in_standard_form(round_interval_nearest(x['p'], self.precisionPriceDict[symbol])), str(Decimal(str(x['v'])))] for x in orderbook['bids']]}

    @tries_wrapper
    def futures_orderbook_ticker(self, symbol):
        """
        Gets best bid/ask and qty
        :return:
        {
          "symbol": "BTCUSDT",
          "bidPrice": "4.00000000",
          "bidQty": "431.00000000",
          "askPrice": "4.00000200",
          "askQty": "9.00000000",
          "time": 1589437530011   // Transaction time
        }
        """
        if self.exchange == "BINANCE":
            return self.client_binance.futures_orderbook_ticker(symbol=symbol)
        elif "FTX" in self.exchange:
            orderbook = self.client_ftx.get_orderbook(symbol, 1)
            bidPrice = format_float_in_standard_form(orderbook['bids'][0][0])
            bidQty = format_float_in_standard_form(orderbook['bids'][0][1])
            askPrice = format_float_in_standard_form(orderbook['asks'][0][0])
            askQty = format_float_in_standard_form(orderbook['asks'][0][1])
            return {"symbol": symbol, "bidPrice": bidPrice, "bidQty": bidQty, "askPrice": askPrice, "askQty": askQty}
        elif "OKEX" in self.exchange:
            orderbook = self.client_okex.get_ticker(instId=symbol)
            if 'USDT' in symbol:
                bidQty = str(Decimal(orderbook['bidSz']) * self.precisionQuantityDict[symbol])
                askQty = str(Decimal(orderbook['askSz']) * self.precisionQuantityDict[symbol])
            else:
                bidQty = str(Decimal(orderbook['bidSz']) * self.precisionQuantityDict[symbol] / Decimal(orderbook['bidPx']))
                askQty = str(Decimal(orderbook['askSz']) * self.precisionQuantityDict[symbol] / Decimal(orderbook['askPx']))
            return {"symbol": symbol, "bidPrice": orderbook['bidPx'], "bidQty": bidQty,
                    "askPrice": orderbook['askPx'], "askQty": askQty}
        elif "GATE" in self.exchange:
            orderbook = self.client_gate.list_futures_order_book(settle="usdt", contract=symbol, limit=1,
                                                                 _request_timeout=(self.timeout, self.timeout))
            bidPrice = orderbook.bids[0].p
            bidQty = str(Decimal(str(orderbook.bids[0].s)) * self.precisionQuantityDict[symbol])
            askPrice = orderbook.asks[0].p
            askQty = str(Decimal(str(orderbook.asks[0].s)) * self.precisionQuantityDict[symbol])
            return {"symbol": symbol, "bidPrice": bidPrice, "bidQty": bidQty, "askPrice": askPrice, "askQty": askQty}
        elif "MEXC" in self.exchange or "BYBIT" in self.exchange or "IG" in self.exchange or "CAPITAL" in self.exchange or "PHEMEX" in self.exchange or "BINGX" in self.exchange:
            # The below could be applied to all exchanges...
            orderbook = self.futures_get_order_book(symbol=symbol, limit=1)
            bidPrice = format_float_in_standard_form(orderbook['bids'][0][0])
            bidQty = format_float_in_standard_form(orderbook['bids'][0][1])
            askPrice = format_float_in_standard_form(orderbook['asks'][0][0])
            askQty = format_float_in_standard_form(orderbook['asks'][0][1])
            return {"symbol": symbol, "bidPrice": bidPrice, "bidQty": bidQty, "askPrice": askPrice, "askQty": askQty}

    @tries_wrapper
    def futures_change_leverage(self, symbol, leverage):
        if self.exchange == "BINANCE":
            self.client_binance.futures_change_leverage(symbol=symbol, leverage=leverage)
        elif "FTX" in self.exchange:
            self.client_ftx.set_leverage(leverage)
        elif "OKEX" in self.exchange:
            self.client_okex.set_leverage(instId=symbol, ccy='USDT', lever=leverage, mgnMode='cross')
        elif "GATE" in self.exchange:
            self.client_gate.update_position_leverage(settle="usdt", contract=symbol, leverage=leverage, _request_timeout=(self.timeout, self.timeout))
        elif "MEXC" in self.exchange:
            raise Exception("MEXC API change leverage not supported")
        elif "BYBIT" in self.exchange:
            self.client_bybit.set_leverage(symbol=symbol, leverage=leverage)
        elif "PHEMEX" in self.exchange:
            self.client_phemex.change_leverage(symbol=symbol, leverage=leverage)
        elif "BINGX" in self.exchange:
            self.client_bingx.switch_leverage(symbol, leverage, 'Long')
            self.client_bingx.switch_leverage(symbol, leverage, 'Short')

    @tries_wrapper
    def futures_get_trades(self, symbol, limit):
        if self.exchange == "BINANCE":
            raise NotImplementedError
        elif "FTX" in self.exchange:
            return self.client_ftx.get_trades(market=symbol, limit=limit)
        elif "OKEX" in self.exchange:
            return NotImplementedError
        elif "GATE" in self.exchange:
            return NotImplementedError

    def futures_cancel_open_buy_orders(self, symbol):
        buy_orders = self.futures_get_open_buy_orders(symbol)
        for order in buy_orders:
            self.futures_cancel_order(symbol=symbol, orderID=order['orderId'])

    def futures_cancel_open_sell_orders(self, symbol):
        sell_orders = self.futures_get_open_sell_orders(symbol)
        for order in sell_orders:
            self.futures_cancel_order(symbol=symbol, orderID=order['orderId'])

    def futures_get_symbol_price(self, symbol):
        return float(self.futures_symbol_ticker(symbol=symbol).get("price"))

    def futures_get_mark_price(self, symbol=None):
        return self.futures_mark_price(symbol=symbol)

    def futures_get_candlesticks(self, symbol, limit=500, interval="5m", startTime=None, endTime=None):
        """
        returns https://binance-docs.github.io/apidocs/futures/en/#compressed-aggregate-trades-list
        last entry is most recent (incomplete) candle
        if getting 2m candles, the result will vary depending on the time it is run. To match TV, only run on odd minutes
        :returns
        [
            [
            open_time: int
            open: str
            high: str
            low: str
            close: str
            volume: str
            close_time: int
            ]
        ]
        """
        if interval == "2m":
            limit = limit * 2
            candles = self.futures_klines(symbol=symbol, interval="1m", limit=limit, startTime=startTime,
                                          endTime=endTime)
            return convert_min_to_x_min_candles(candles, 2)
        return self.futures_klines(symbol=symbol, interval=interval, limit=limit, startTime=startTime, endTime=endTime)

    def futures_position_size(self, symbol):
        position = self.futures_get_position(symbol)
        if position:
            return get_position_size(position)
        else:
            return None

    def futures_is_open_position(self, symbol):
        # returns if there is an open position for symbol
        if self.futures_position_size(symbol) != 0.0:
            return True
        else:
            return False

    def futures_get_multi_margin_assets(self):
        """BINANCE ONLY
        gets the assets that are able to be used as margin for multi-margin asset mode
        :return: list of multi-margin assets
        """
        return self.binance_futures_get_multi_margin_assets()

    def futures_get_asset_balance(self, asset):
        balances = self.futures_account_balance()
        for balance in balances:
            if balance['asset'] == asset:
                return balance['balance']
        return None

    def futures_get_order_from_client_id(self, symbol, clientOrderId):
        order = self.futures_get_order(symbol=symbol, origClientOrderId=clientOrderId)
        if order:
            return order
        return None

    def futures_get_open_buy_orders(self, symbol):
        orders = self.futures_get_open_orders(symbol)
        buyOrders = [order for order in orders if order.get("side") == 'BUY']
        return buyOrders

    def futures_get_open_buy_limit_orders(self, symbol):
        orders = self.futures_get_open_orders(symbol)
        buyOrders = [order for order in orders if
                     order.get("side") == 'BUY' and order.get('type') == self.ORDER_TYPE_LIMIT]
        return buyOrders

    def futures_get_long_stop_loss_order(self, symbol):
        orders = self.futures_get_open_orders(symbol)
        longSLOrders = [order for order in orders if
                        order.get("side") == 'SELL' and order.get('type') == self.ORDER_TYPE_STOP_MARKET and order.get('reduceOnly') is True]
        return longSLOrders

    def futures_get_open_sell_orders(self, symbol):
        orders = self.futures_get_open_orders(symbol)
        sellOrders = [order for order in orders if order.get("side") == 'SELL']
        return sellOrders

    def futures_get_open_sell_limit_orders(self, symbol):
        orders = self.futures_get_open_orders(symbol)
        sellOrders = [order for order in orders if
                      order.get("side") == 'SELL' and order.get('type') == self.ORDER_TYPE_LIMIT]
        return sellOrders

    def futures_get_short_stop_loss_order(self, symbol):
        orders = self.futures_get_open_orders(symbol)
        shortSLOrders = [order for order in orders if
                         order.get("side") == 'BUY' and order.get('type') == self.ORDER_TYPE_STOP_MARKET and order.get('reduceOnly') is True]
        return shortSLOrders

    def futures_is_order_filled(self, symbol, orderID):
        order = self.futures_get_order(symbol, orderID)
        return is_order_filled(order)

    def futures_is_order_filled_partial(self, symbol, orderID):
        order = self.futures_get_order(symbol, orderID)
        return is_order_filled_partial(order)

    def futures_is_order_filled_any(self, symbol, orderID):
        order = self.futures_get_order(symbol, orderID)
        return is_order_filled(order) or is_order_filled_partial(order)

    def futures_cancel_all_orders(self, symbol):
        self.futures_cancel_all_open_orders(symbol=symbol)

    # TV limits rounding testing
    # Buy	sf<5	sf>5 (significant figure<5 cases should normally round down and vice versa)
    # Entry	down	down
    # Exit	down	down
    #
    # Sell
    # Entry	up	    up
    # Exit	up	    up
    # So floor for buy limits and ceil for sell limits
    def futures_create_limit_order(self, symbol, limit, side, stop=None, quantity=None, balancePercent=None,
                                   fixedBalance=None,
                                   reduceOnly=False, postOnly=False, recvWindow=DEFAULT_RECVWINDOW, balance=None,
                                   atBid=False, atAsk=False, volume_based_max_usdt_pos_size=False,
                                   absoluteMaxUsdtPosSize=0.0):
        """
        :param side: BUY | SELL
        :param volume_based_max_usdt_pos_size: adaptive max usdt pos size based on the last 24hr volume (only applies if balancePercent is used)
        :param balance: str
        :param recvWindow:
        :param symbol:
        :param limit:
        :param stop:
        :param quantity: number of coins
        :param balancePercent: position based on percentage of total balance
        :param fixedBalance: position using a fixed amount of money (USDT)
        :param reduceOnly:
        :param postOnly:
        :param atBid: places limit order at the bid price (instead of param limit price)
        :param absoluteMaxUsdtPosSize: absolute max position size in usdt that an order can make. 0 means unlimited
        :return:
        """
        def convert_value_to_capital_account_currency(value):
            instrument_currency = self.capital_instrument_currency_data[symbol]
            if instrument_currency != CAPITAL_ACCOUNT_CURRENCY:
                exchange_rate_name = [x for x in self.capital_exchange_rate_data.keys() if
                                      CAPITAL_ACCOUNT_CURRENCY in x and instrument_currency in x][0]
                if CAPITAL_ACCOUNT_CURRENCY == exchange_rate_name[:3]:
                    value = Decimal(value) * Decimal(self.capital_exchange_rate_data[exchange_rate_name])
                else:
                    value = Decimal(value) / Decimal(self.capital_exchange_rate_data[exchange_rate_name])
            return value

        if (quantity and balancePercent) or (quantity and fixedBalance) or (balancePercent and fixedBalance):
            print("ERROR: Only specify one of quantity, balancePercent or fixedBalance!")
            return
        if atBid or atAsk:
            return self.futures_post_only_at_bid_or_ask(symbol, side, atBid, quantity, balancePercent, fixedBalance,
                                                        reduceOnly,
                                                        balance, volume_based_max_usdt_pos_size)
        else:
            limit = round_interval_down(limit, self.precisionPriceDict.get(symbol)) if side == self.SIDE_BUY else round_interval_up(limit, self.precisionPriceDict.get(symbol))
        if quantity:
            if 0 < absoluteMaxUsdtPosSize < Decimal(str(quantity)) * Decimal(str(limit)):
                quantity = round_interval_down(absoluteMaxUsdtPosSize / limit)
            quantity = round_interval_nearest(Decimal(str(quantity)), self.precisionQuantityDict.get(symbol))
        elif balancePercent:
            if not balance:  # perhaps needs a cleaner method/structure so that this doesn't need to make an API call
                balance = self.futures_get_balance()
            if "CAPITAL" in self.exchange:
                #  Instrument price may be in different currency.
                #  Need to convert the size to be CAPITAL_ACCOUNT_CURRENCY (probably GBP) instead.
                balance = convert_value_to_capital_account_currency(balance)
            if absoluteMaxUsdtPosSize == 0.0:
                usdt_pos_size = Decimal(str(balance)) * Decimal(str(balancePercent))
            else:
                usdt_pos_size = min(Decimal(str(balance)) * Decimal(str(balancePercent)), Decimal(str(absoluteMaxUsdtPosSize)))
            if volume_based_max_usdt_pos_size:
                max_usdt_pos_size = Decimal(str(self.get_volume_based_max_usdt_pos_size(symbol)))
                usdt_pos_size = max_usdt_pos_size if usdt_pos_size > max_usdt_pos_size else usdt_pos_size
            quantity = round_interval_down(
                usdt_pos_size / Decimal(str(limit)),
                self.precisionQuantityDict.get(symbol))
        elif fixedBalance:
            if "CAPITAL" in self.exchange:
                fixedBalance = convert_value_to_capital_account_currency(fixedBalance)
            fixedBalance = fixedBalance if absoluteMaxUsdtPosSize == 0.0 else min(fixedBalance, absoluteMaxUsdtPosSize)
            quantity = round_interval_down(Decimal(str(fixedBalance)) / Decimal(str(limit)),
                                           self.precisionQuantityDict.get(symbol))
        else:
            self.logger.writeline(f"ERROR: futures_create_limit_order requires quantity or balancePercent or fixedBalance")
            return
        currency_symbol = "$" if "CAPITAL" not in self.exchange else self.capital_instrument_currency_data[symbol] + " "
        order = None
        clientId = side + symbol + str(datetime.now().timestamp())
        if stop is None:
            if postOnly:
                time_in_force = self.TIME_IN_FORCE_GTX
            else:
                time_in_force = self.TIME_IN_FORCE_GTC
            order = self.futures_create_order(symbol=symbol,
                                              side=side,
                                              type=self.ORDER_TYPE_LIMIT,
                                              price=limit,
                                              quantity=quantity,
                                              reduceOnly=reduceOnly,
                                              timeInForce=time_in_force,
                                              recvWindow=recvWindow,
                                              newClientOrderId=clientId
                                              )
            orderId = order.get('orderId')
            if not reduceOnly:
                self.logger.writeline(
                    f"{symbol} {side} entry limit @{format_float_in_standard_form(float(limit))} for {str(quantity)} ({currency_symbol}{round(limit * quantity, 2)}). OrderId: {orderId}")
            else:
                self.logger.writeline(
                    f"{symbol} {side} exit limit @{format_float_in_standard_form(float(limit))} for {str(quantity)} ({currency_symbol}{round(limit * quantity, 2)}). OrderId: {orderId}")
        elif stop is not None:
            stop = round_interval_down(stop, self.precisionPriceDict.get(symbol))
            order = self.futures_create_order(symbol=symbol,
                                              side=side,
                                              type=self.ORDER_TYPE_STOP,
                                              quantity=quantity,
                                              reduceOnly=reduceOnly,
                                              price=limit,
                                              stopPrice=stop,
                                              timeInForce=self.TIME_IN_FORCE_GTC,
                                              recvWindow=recvWindow,
                                              newClientOrderId=clientId
                                              )
            orderId = order.get('orderId')
            if not reduceOnly:
                self.logger.writeline(
                    f"{symbol} {side} entry Stop @{format_float_in_standard_form(float(stop))} Limit @{format_float_in_standard_form(float(limit))} for {str(quantity)} ({currency_symbol}{round(limit * quantity, 2)}). OrderId: {orderId}")
            else:
                self.logger.writeline(
                    f"{symbol} {side} exit Stop @{format_float_in_standard_form(float(stop))} Limit @{format_float_in_standard_form(float(limit))} for {str(quantity)} ({currency_symbol}{round(limit * quantity, 2)}). OrderId: {orderId}")
        return order

    def futures_short_stop_loss(self, symbol, stop, quantity, recvWindow=DEFAULT_RECVWINDOW):
        stop_price = round_interval_down(stop, self.precisionPriceDict.get(symbol))
        clientId = "ShortStopLoss" + symbol + str(datetime.now().timestamp())
        stopOrder = self.futures_create_order(symbol=symbol,
                                              side=self.SIDE_BUY,
                                              type=self.ORDER_TYPE_STOP_MARKET,
                                              quantity=quantity,
                                              reduceOnly=True,
                                              stopPrice=stop_price,
                                              timeInForce=self.TIME_IN_FORCE_GTC,
                                              recvWindow=recvWindow,
                                              newClientOrderId=clientId
                                              )
        orderId = stopOrder.get('orderId')
        self.logger.writeline(f"{symbol} Short stop loss @{stop_price}. OrderId: {orderId}")
        return stopOrder

    def futures_long_stop_loss(self, symbol, stop, quantity, recvWindow=DEFAULT_RECVWINDOW):
        stop_price = round_interval_up(stop, self.precisionPriceDict.get(symbol))
        clientId = "LongStopLoss" + symbol + str(datetime.now().timestamp())
        stopOrder = self.futures_create_order(symbol=symbol,
                                              side=self.SIDE_SELL,
                                              type=self.ORDER_TYPE_STOP_MARKET,
                                              quantity=quantity,
                                              reduceOnly=True,
                                              stopPrice=stop_price,
                                              timeInForce=self.TIME_IN_FORCE_GTC,
                                              recvWindow=recvWindow,
                                              newClientOrderId=clientId
                                              )
        orderId = stopOrder.get('orderId')
        self.logger.writeline(f"{symbol} Long stop loss @{stop_price}. OrderId: {orderId}")
        return stopOrder

    def futures_post_only_at_bid_or_ask(self, symbol, side, atBid, quantity=None, balancePercent=None, fixedBalance=None,
                                        reduceOnly=False, balance=None, volume_based_max_usdt_pos_size=None):
        """
        helper function for futures_buy_limit_order/futures_sell_limit_order when atBid/atAsk==True.
        The purpose of this function is to guarantee an order is placed at the bid/ask using post only orders.
        Note: 'stop', 'limit' and 'post_only' parameters are not used here as redundant.
        :return: orderId
        """
        order = None
        orderStatus = 'EXPIRED'
        if side.upper() == "BUY":
            # logger.writeline(f"{symbol} placing post only buy orders at bid...")
            while orderStatus == 'EXPIRED' or orderStatus == 'CANCELLED':
                if atBid:
                    price = self.futures_get_bid(symbol=symbol)
                else:
                    price = self.futures_get_ask(symbol=symbol)
                order = self.futures_create_limit_order(symbol, price, quantity=quantity,
                                                        balancePercent=balancePercent,
                                                        fixedBalance=fixedBalance, reduceOnly=reduceOnly,
                                                        balance=balance,
                                                        postOnly=True,
                                                        volume_based_max_usdt_pos_size=volume_based_max_usdt_pos_size,
                                                        side="BUY")
                orderStatus = self.futures_get_order(symbol, order['orderId'])['status']
        elif side.upper() == "SELL":
            # logger.writeline(f"{symbol} placing post only sell orders at ask...")
            if atBid:
                price = self.futures_get_bid(symbol=symbol)
            else:
                price = self.futures_get_ask(symbol=symbol)
            while orderStatus == 'EXPIRED' or orderStatus == 'CANCELLED':
                order = self.futures_create_limit_order(symbol, price, quantity=quantity,
                                                        balancePercent=balancePercent,
                                                        fixedBalance=fixedBalance, reduceOnly=reduceOnly,
                                                        balance=balance,
                                                        postOnly=True,
                                                        volume_based_max_usdt_pos_size=volume_based_max_usdt_pos_size,
                                                        side="SELL")
                orderStatus = self.futures_get_order(symbol, order['orderId'])['status']
        # logger.writeline(f"{symbol} post only order placed")
        return order

    def futures_market_buy(self, symbol, quantity, reduceOnly=False):
        order = self.futures_create_order(symbol=symbol,
                                          side=self.SIDE_BUY,
                                          type=self.ORDER_TYPE_MARKET,
                                          quantity=quantity,
                                          reduceOnly=reduceOnly
                                          )
        return order

    def futures_market_sell(self, symbol, quantity, reduceOnly=False):
        order = self.futures_create_order(symbol=symbol,
                                          side=self.SIDE_SELL,
                                          type=self.ORDER_TYPE_MARKET,
                                          quantity=quantity,
                                          reduceOnly=reduceOnly
                                          )
        return order

    def futures_close_position(self, symbol):
        positionSize = self.futures_position_size(symbol)
        if positionSize > 0:
            return self.futures_market_sell(symbol, positionSize, reduceOnly=True)
        elif positionSize < 0:
            return self.futures_market_buy(symbol, abs(positionSize), reduceOnly=True)
        else:
            # TODO: Needs to make sure position is closed instead of return
            return

    def futures_get_order_book(self, symbol, limit=500):
        """
        gets full order book for symbol
        :param symbol:
        :param limit:
        :return:
        """
        return self.futures_order_book(symbol=symbol, limit=limit)

    def futures_get_bid(self, symbol):
        return self.futures_orderbook_ticker(symbol=symbol).get('bidPrice')

    def futures_get_ask(self, symbol):
        return self.futures_orderbook_ticker(symbol=symbol).get('askPrice')

    def futures_get_bid_min_value(self, symbol, minValue=0):
        """
        Gets the bid with minValue threshold for the price returned
        :param symbol:
        :param minValue:
        :return:
        """
        order_book = self.futures_get_order_book(symbol)
        if order_book:
            bids = order_book.get('bids')
            total = 0
            for bid in bids:
                total += float(bid[0]) * float(bid[1])
                if total > minValue:
                    return float(bid[0])
        return None

    def futures_get_ask_min_value(self, symbol, minValue=0):
        """
        Gets the ask with minValue threshold for the price returned
        :param symbol:
        :param minValue:
        :return:
        """
        order_book = self.futures_get_order_book(symbol)
        if order_book:
            asks = order_book.get('asks')
            total = 0
            for ask in asks:
                total += float(ask[0]) * float(ask[1])
                if total > minValue:
                    return float(ask[0])
        return None

    def market_open_avg_price_and_slippage(self, symbol, side, amount_usd):
        """
        :param symbol:
        :param side:
        :param amount_usd:
        :return: total amount of asset bought, avg price, slippage
        """
        order_book = self.futures_get_order_book(symbol)
        slippage_start = 0
        if side == "LONG":
            asks = order_book.get('asks')
            money_left = amount_usd
            total_asset = 0
            for ask in asks:
                if money_left > Decimal(ask[0]) * Decimal(ask[1]):
                    money_left = money_left - (Decimal(ask[0]) * Decimal(ask[1]))
                    total_asset = total_asset + Decimal(ask[1])
                    if slippage_start == 0:
                        slippage_start = Decimal(ask[0])
                elif Decimal(ask[0]) * Decimal(ask[1]) > money_left:
                    total_asset = total_asset + (money_left / Decimal(ask[0]))
                    slippage_end = Decimal(ask[0])
                    if slippage_start == 0:
                        slippage_start = slippage_end
                    return round_interval_nearest(total_asset, self.precisionPriceDict[symbol]), round_interval_nearest(
                        amount_usd / total_asset, self.precisionPriceDict[symbol]), round_interval_nearest(
                        slippage_end - slippage_start, self.precisionPriceDict[symbol])
        if side == "SHORT":
            bids = order_book.get('bids')
            money_left = amount_usd
            total_asset = 0
            for bid in bids:
                if money_left > Decimal(bid[0]) * Decimal(bid[1]):
                    money_left = money_left - (Decimal(bid[0]) * Decimal(bid[1]))
                    total_asset = total_asset + Decimal(bid[1])
                    if slippage_start == 0:
                        slippage_start = Decimal(bid[0])
                elif Decimal(bid[0]) * Decimal(bid[1]) > money_left:
                    total_asset = total_asset + (money_left / Decimal(bid[0]))
                    slippage_end = Decimal(bid[0])
                    if slippage_start == 0:
                        slippage_start = slippage_end
                    return round_interval_nearest(total_asset, self.precisionPriceDict[symbol]), round_interval_nearest(
                        amount_usd / total_asset, self.precisionPriceDict[symbol]), round_interval_nearest(
                        slippage_start - slippage_end, self.precisionPriceDict[symbol])

    def market_close_now_profit(self, symbol, position=None):
        """
        What the realised profits would be if you were to close the position at market price
        :param symbol:
        :param position:
        :return: total, realised pnl, average price, slippage
        """
        if not position:
            position = self.futures_get_position(symbol)
        positionSize = get_position_size(position)
        if positionSize == 0:
            return None
        entryPrice = get_entry_price(position)
        entryTotal = entryPrice * abs(positionSize)
        order_book = self.futures_get_order_book(symbol)
        slippage_start = 0
        if positionSize > 0:
            bids = order_book.get('bids')
            positionSize_left = positionSize
            total = 0
            for bid in bids:
                if positionSize_left > float(bid[1]):
                    total = total + (float(bid[0]) * float(bid[1]))
                    positionSize_left = positionSize_left - float(bid[1])
                    if slippage_start == 0:
                        slippage_start = float(bid[0])
                elif float(bid[1]) > positionSize_left:
                    total = total + (float(bid[0]) * positionSize_left)
                    if slippage_start == 0:
                        slippage_end = 0
                    else:
                        slippage_end = float(bid[0])
                    return round(total, 3), round(total - entryTotal, 3), round_interval_nearest(total / positionSize,
                                                                                                 self.precisionPriceDict[
                                                                                                     symbol]), round_interval_nearest(
                        slippage_start - slippage_end, self.precisionPriceDict[symbol])
        if positionSize < 0:
            asks = order_book.get('asks')
            positionSize = abs(positionSize)
            positionSize_left = positionSize
            total = 0
            for ask in asks:
                if positionSize_left > float(ask[1]):
                    total = total + (float(ask[0]) * float(ask[1]))
                    positionSize_left = positionSize_left - float(ask[1])
                    if slippage_start == 0:
                        slippage_start = float(ask[0])
                elif float(ask[1]) > positionSize_left:
                    total = total + (float(ask[0]) * positionSize_left)
                    if slippage_start == 0:
                        slippage_end = 0
                    else:
                        slippage_end = float(ask[0])
                    return round(total, 3), round(entryTotal - total, 3), round_interval_nearest(total / positionSize,
                                                                                                 self.precisionPriceDict[
                                                                                                     symbol]), round_interval_nearest(
                        slippage_end - slippage_start, self.precisionPriceDict[symbol])

    def calculate_max_unrealised_loss_percentage(self, symbol, start_time: float, entry_price, side, interval="5m"):
        candles = self.futures_get_candlesticks(symbol, interval=interval, startTime=round(start_time),
                                                endTime=round(datetime.now().timestamp() * 1000) + 5000)
        # print(f"len(candles) {len(candles)} interval {interval} start_time {start_time} end_time={round(datetime.now().timestamp() * 1000)+5000}")
        if side == "LONG":
            lowest_point = min(Decimal(candle[3]) for candle in candles)
            # print(lowest_point)
            if lowest_point >= entry_price:
                percentage = 0
            else:
                percentage = (1 - (lowest_point / entry_price)) * 100
        elif side == "SHORT":
            highest_point = max(Decimal(candle[2]) for candle in candles)
            # print(highest_point)
            if highest_point <= entry_price:
                percentage = 0
            else:
                percentage = ((highest_point / entry_price) - 1) * 100
        return percentage

    def futures_close_best_price(self, symbol, minValue=0, position=None):
        """
        Closes the position by making a limit order that is continuously at the best bid/ask price (or after
        CLOSE_BEST_PRICE_MIN_VALUE threshold if used)
        :param position:
        :param minValue:
        :param symbol:
        :return:
        """
        # TODO: check if there is a current exit order and check it's limit price before cancelling
        self.logger.writeline(f"{symbol} Beginning closing position at best price...")
        if position is None:
            # TODO: figure out a way for Utils to be able to utilise websockets so the following line has a fallback option
            position = self.futures_get_position(symbol)
        if position:
            positionSize = get_position_size(position)
            if positionSize == 0:
                self.logger.writeline(f"{symbol} No position to close")
                return
            total, pnl, avPrice, slippage = self.market_close_now_profit(symbol, position)
            self.logger.writeline(
                f"{symbol} Close at market now total ${total} pnl {pnl}, avPrice {avPrice}, slippage {slippage}")
        else:
            raise ValueError(f'{symbol} futures_close_best_price unable to get position size')
        current_limit = 0.0
        while positionSize != 0:
            positionSize = self.futures_position_size(symbol)
            if isinstance(positionSize, float) is False:
                raise ValueError(f'{symbol} futures_close_best_price unable to get position size')
            if positionSize > 0:
                currentAsk = self.futures_get_ask_min_value(symbol, minValue)
                if isinstance(currentAsk, float) is False:
                    raise ValueError(f'{symbol} futures_close_best_price unable to get currentAsk')
                if currentAsk != current_limit:
                    self.futures_cancel_all_orders(symbol)
                    self.futures_create_limit_order(symbol, limit=currentAsk, reduceOnly=True, postOnly=True,
                                                    quantity=positionSize, side="SELL")
                    current_limit = currentAsk
            elif positionSize < 0:
                currentBid = self.futures_get_bid_min_value(symbol, minValue)
                if isinstance(currentBid, float) is False:
                    raise ValueError(f'{symbol} futures_close_best_price unable to get currentBid')
                if currentBid != current_limit:
                    self.futures_cancel_all_orders(symbol)
                    self.futures_create_limit_order(symbol, limit=currentBid, reduceOnly=True, postOnly=True,
                                                    quantity=abs(positionSize), side="BUY")
                    current_limit = currentBid
            else:
                self.logger.writeline(f"{symbol} Position closed")
                return
            sleep(1)
        self.logger.writeline(f"{symbol} No position to close")

    def get_tick_volume(self, symbol, interval="5m", ticks=1, num_of_candles=1499):
        candles = self.futures_get_candlesticks(symbol, interval=interval, limit=num_of_candles + 1)[:-1]
        # total_tick_volume = 0
        total_ticks = 0
        total_usd_vol = 0
        for candle in candles:
            # tick_vol = usd_vol / number_of_ticks_in_candle
            # usd_vol = volume * avg_price_of_candle
            # number_of_ticks_in_candle = (candle_high - candle_low) / tickSize
            if self.exchange == "BINANCE":
                usd_vol = Decimal(candle[5]) * ((Decimal(candle[2]) + Decimal(candle[3])) / Decimal("2"))
            elif "FTX" in self.exchange:
                # on FTX usd_vol is provided by default (quote price volume)
                usd_vol = Decimal(candle[5])
            total_usd_vol = total_usd_vol + usd_vol
            number_of_ticks_in_candle = max(1, (Decimal(candle[2]) - Decimal(candle[3])) / self.precisionPriceDict[symbol])
            total_ticks = total_ticks + number_of_ticks_in_candle
            # tick_vol = usd_vol / number_of_ticks_in_candle
            # total_tick_volume = total_tick_volume + tick_vol
        # average tick_volume = total_usd_volume / total_ticks
        return total_usd_vol / total_ticks

    def change_leverage_for_all_symbols(self, leverage):
        for symbols in self.futures_exchange_info():
            try:
                symbol = symbols.get('symbol')
                self.futures_change_leverage(symbol=symbol, leverage=leverage)
            except Exception as e:
                pass

    def get_last_24h_usdt_volume(self, symbol):
        candles = self.futures_klines(symbol=symbol, interval="1h", limit=24)
        if isinstance(candles, tuple):
            candles = candles[0]
        volume = 0
        for candle in candles:
            if len(candle) == 7:
                # FTX candles, volume is index 5
                volume += float(candle[5])
            else:
                volume += float(candle[7])
        return volume

    def get_volume_based_max_usdt_pos_size(self, symbol):
        last_24h_volume = self.get_last_24h_usdt_volume(symbol)
        ratio_of_volume_for_max_usdt_size = 0.004
        return last_24h_volume * ratio_of_volume_for_max_usdt_size

    def get_av_volume_for_past_n_days(self, symbol, n):
        candles = self.futures_klines(symbol=symbol, interval="1d", limit=n+1)[:-1]  # trim latest (unfinished) candle
        if isinstance(candles, tuple):
            candles = candles[0]
        volume = 0
        for candle in candles:
            if len(candle) == 7:
                # FTX candles, volume is index 5
                volume += float(candle[5])
            else:
                volume += float(candle[7])
        if len(candles) != 0:
            return volume/len(candles)
        else:
            return 0

    def abnormal_volume_check(self, symbol, abnormal_volume_spike_multiplier_threshold, abnormal_volume_spike_average_number_of_days):
        """
        Returns True if last_24h_volume > abnormal_volume_spike_average_number_of_days * abnormal_volume_spike_multiplier_threshold
        """
        return self.get_last_24h_usdt_volume(symbol=symbol) > self.get_av_volume_for_past_n_days(
            symbol=symbol, n=abnormal_volume_spike_average_number_of_days) * abnormal_volume_spike_multiplier_threshold

    def cancel_all_orders_for_all_symbols(self):
        for symbols in self.futures_exchange_info():
            symbol = symbols.get('symbol')
            self.futures_cancel_all_orders(symbol)

# client = FtxClient(api_key=FTX_API_KEY, api_secret=FTX_API_SECRET)
# uniClientFTX = UniversalClient("FTX")
# uniCLientBINANCE = UniversalClient("BINANCE")
# uco = UniversalClient("OKEX")
# print FTX tickers:
# for ticker in ucf.precisionQuantityDict.keys():
#     print(f"FTX:{ticker.replace('-','')},")
# print OKEX tickers:
# for ticker in uco.precisionQuantityDict.keys():
#     print(f"OKEX:{ticker.replace('-','').replace('SWAP','')}PERP,")
# for BINANCE:
# for ticker in ucb.precisionQuantityDict.keys():
#     print(f"BINANCE:{ticker}PERP,")