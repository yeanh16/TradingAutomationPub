import threading
import sys
import random
from time import time, sleep
import multiprocessing
from threading import Thread, Event
from queue import Queue
from datetime import datetime
from typing import List
from trading_automation.clients.UniversalClient import UniversalClient, binance_intervals_to_seconds, PHEMEX_API_ID, PHEMEX_API_SECRET, PHEMEX_USE_HIGH_RATE_API_ENDPOINT
from trading_automation.websockets.FTXWebSocket import Websocket
import json
import hmac
from trading_automation.core.Utils import format_float_in_standard_form, check_if_candles_are_latest, get_current_datetime_string
from decimal import Decimal
import copy
from trading_automation.websockets.PhemexWebSocketManager import PhemexWebSocketManager


class PhemexWebSocketMaster(Websocket, Thread):
    _ENDPOINT = 'wss://phemex.com/ws'
    _ENDPOINT_HIGH_RATE = 'wss://vapi.phemex.com/ws'

    def __init__(self, input_q: Queue, output_q: Queue, api_key=None, api_secret=None, candles_limit=200):
        Websocket.__init__(self)
        Thread.__init__(self)
        self.input_q = input_q
        self.output_q = output_q
        self._api_key = api_key if api_key is not None else PHEMEX_API_ID
        self._api_secret = api_secret if api_secret is not None else PHEMEX_API_SECRET
        self.client = UniversalClient("PHEMEX")
        self.logger = self.client.logger
        self.account_id = 84621498874  # self.client.client_phemex.query_account_n_positions("USD")['account']['userID']
        self._login()
        self.candles_limit = candles_limit
        self.klines_interval_dict = {}
        self.orders = {}
        self.positions = {}
        sleep(5)
        self._set_up_orders()
        threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self):
        while True:
            self.send_json({'id': self.account_id, "method": "server.ping", 'params': []})
            sleep(5)

    def _login(self):
        def _sign(to_be_sign):
            return hmac.new(self._api_secret.encode('utf-8'), to_be_sign.encode('utf-8'), 'sha256').hexdigest()

        expiry = int(time()) + 5
        self.send_json({"method": "user.auth", "params": [
                                                "API",
                                                self._api_key,
                                                _sign(f"{self._api_key}{expiry}"),
                                                expiry], "id": self.account_id})
        self._logged_in = True

    def _get_url(self):
        if PHEMEX_USE_HIGH_RATE_API_ENDPOINT:
            return self._ENDPOINT_HIGH_RATE
        else:
            return self._ENDPOINT

    def _handle_kline_message(self, message):
        symbol = message['symbol']
        interval = self.klines_interval_dict[symbol]['interval']
        formatted_candles = []
        for kline in message['kline']:
            formatted_candle = [int(kline[0] * 1000),
                                format_float_in_standard_form(Decimal(str(kline[3])) * Decimal('0.0001')),
                                format_float_in_standard_form(Decimal(str(kline[4])) * Decimal('0.0001')),
                                format_float_in_standard_form(Decimal(str(kline[5])) * Decimal('0.0001')),
                                format_float_in_standard_form(Decimal(str(kline[6])) * Decimal('0.0001')),
                                format_float_in_standard_form(Decimal(str(kline[7]))),
                                int(kline[0] * 1000) + int(binance_intervals_to_seconds(interval)) * 1000 - 1,
                                format_float_in_standard_form(Decimal(str(kline[8])) * Decimal('0.0001'))]
            formatted_candles.append(formatted_candle)

            if message['type'] == 'snapshot':
                if len(formatted_candles) >= self.candles_limit:
                    self.klines_interval_dict[symbol]['klines'] = list(reversed(formatted_candles))
                    # print(f"stored_candles = {self.klines_interval_dict[symbol]['klines']}")
                    return

        for formatted_candle in reversed(formatted_candles):
            # if open_time of candle is the same as the last entry in self.candles - update, else append new candle
            # print(f"stored_candles = {self.klines_interval_dict[symbol]['klines']} formatted_candle = {formatted_candle}")
            if int(self.klines_interval_dict[symbol]['klines'][-1][0]) == int(formatted_candle[0]):
                self.klines_interval_dict[symbol]['klines'][-1] = formatted_candle
            else:
                # check if the next candle's open time fits in sequentially before adding
                if int(self.klines_interval_dict[symbol]['klines'][-1][0]) + binance_intervals_to_seconds(interval) * 1000 == int(formatted_candle[0]):
                    self.klines_interval_dict[symbol]['klines'].append(formatted_candle)
                    self.klines_interval_dict[symbol]['klines'] = self.klines_interval_dict[symbol]['klines'][1:]
                elif int(self.klines_interval_dict[symbol]['klines'][-1][0]) > int(formatted_candle[0]):
                    continue
                else:
                    # need to reset candles
                    print(f"{symbol} WARNING: PHEMEX WS new candle does not fit. Getting candles again...")
                    self._set_up_candlesticks(symbol, interval)

            self._last_candle_update_time = int(time())

    def _handle_account_message(self, message):
        for account in message['accounts']:
            # print(message['accounts'])
            if account['accountID'] == 45879400002:  # main account ID
                self.total_balance = str(Decimal(str(account['accountBalanceEv'])) * Decimal('0.0001'))

    def _handle_orders_message(self, message):
        for order in reversed(message['orders']):
            # print(order)
            if 'action' in order and (order['action'] == 'SettleFundingFee' or order['action'] == 'SetLeverage'):
                return
            if 'action' in order and order['action'] == 'Cancel':
                if order['orderID'] in self.orders:
                    self.orders[order['orderID']]['status'] = 'CANCELLED'
            else:
                self.orders[order['orderID']] = self.client.process_phemex_order_to_binance(order)

    def _handle_positions_message(self, message):
        for position in message['positions']:
            # print(position)
            if 'action' in position and position['action'] == 'SettleFundingFee':
                continue
            if position['symbol'] in self.klines_interval_dict:
                self.positions[position['symbol']] = [self.client.process_phemex_position_to_binance(position)]

    def _on_message(self, ws, message):
        message = json.loads(message)
        if 'error' in message and message['error'] is not None:
            raise Exception(f"PHEMEX WS error {message['error']}")
        if 'result' in message and (message['result'] == {'status': 'success'} or message['result'] == 'pong'):
            return

        # print(message)
        if 'kline' in message:
            self._handle_kline_message(message)
        if 'accounts' in message:
            self._handle_account_message(message)
        if 'orders' in message:
            self._handle_orders_message(message)
        if 'positions' in message:
            self._handle_positions_message(message)

    def _subscribe(self, subscription):
        pass

    def _unsubscribe(self, subscription):
        pass

    def _set_up_candlesticks(self, symbol, interval):
        self.klines_interval_dict[symbol] = {'klines': [], 'interval': interval}
        self.send_json({'id': self.account_id, 'method': 'kline.subscribe', 'params': [symbol, binance_intervals_to_seconds(interval)]})

    def _set_up_orders(self):
        self.send_json({'id': self.account_id, 'method': 'aop.subscribe', 'params': []})

    def handle_requests(self):
        while True:
            request, evt = self.input_q.get()
            evt.set()
            if request == 'get_wallet_balance':
                output = self.total_balance
            elif isinstance(request, tuple):  # a tuple of (symbol, interval) to return candles
                symbol = request[0]
                interval = request[1]
                if symbol not in self.klines_interval_dict:
                    self._set_up_candlesticks(symbol=symbol, interval=interval)
                    sleep(5)
                output = self.klines_interval_dict[symbol]['klines']
                if not output:
                    self._set_up_candlesticks(symbol=symbol, interval=interval)
            elif request == 'orders':
                output = self.orders
            elif request == 'refresh_orders':
                self._set_up_orders()
            else:  # lastly just assume that just the symbol is sent to request position
                if request in self.positions:
                    output = self.positions[request]
                else:
                    output = [{"entryPrice": '0',
                               "positionAmt": '0', "symbol": request,
                               "unRealizedProfit": '0'}]
            evt = Event()
            self.output_q.put((output, evt))
            evt.wait()

    def run(self):
        self.handle_requests()


if __name__ == '__main__':
    requests_q = Queue()
    outputs_q = Queue()
    pws = PhemexWebSocketMaster(requests_q, outputs_q, candles_limit=20)
    pws.start()
    pwsm = PhemexWebSocketManager('u100SWEATUSD', '1m', UniversalClient("PHEMEX"), requests_q, outputs_q)
