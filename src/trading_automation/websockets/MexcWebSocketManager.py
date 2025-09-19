import json
from .FTXWebSocket import Websocket
from trading_automation.core.Utils import check_if_candles_are_latest, get_current_datetime_string
from ..clients.UniversalClient import UniversalClient, MEXC_API_KEY, MEXC_API_SECRET
from trading_automation.core.Utils import binance_intervals_to_seconds
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
import hmac, time
from typing import Dict, List
import threading
from trading_automation.core.Utils import binance_intervals_to_mexc_intervals, format_float_in_standard_form


class MexcWebSocketManager(Websocket, WebsocketInterface):
    _ENDPOINT = 'wss://contract.mexc.com/ws'

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50) -> None:
        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.client = client
        self._api_key = MEXC_API_KEY
        self._api_secret = MEXC_API_SECRET
        self._login()
        self.logger = self.client.logger
        self.KLINES_LIMIT = candles_limit
        self.candles = self.client.futures_get_candlesticks(symbol=symbol, limit=self.KLINES_LIMIT,
                                                            interval=self.interval)
        self.position = self.client.futures_get_position(symbol=symbol)
        self.wallet_balance = client.futures_get_balance()
        self.orders = {}
        open_orders = self.client.futures_get_open_orders(self.symbol)
        if open_orders:
            for order in open_orders:
                order["updateTime"] = int(time.time() * 1000)
                self.orders[order['orderId']] = order
        self.OLD_ORDERS_TIME_LIMIT = 300000  # time limit in milliseconds
        self._subscriptions: List[Dict] = []
        threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self):
        while True:
            self.send_json({"method": "ping"})
            time.sleep(10)

    def _sign(self, to_be_sign):
        return hmac.new(self._api_secret.encode('utf-8'), to_be_sign.encode('utf-8'), 'sha256').hexdigest()

    def _login(self):
        # Logging in WS for this exchange automatically subscribes to all private channels
        ts = int(time.time() * 1000)
        self.send_json({"method": "login", 'param': {
            'apiKey': self._api_key,
            'reqTime': ts,
            'signature': self._sign(f'{self._api_key}{ts}'),
        }})
        self._logged_in = True

    def _get_url(self):
        return self._ENDPOINT

    def set_up_candlesticks(self, resub_only=True):
        if not resub_only:
            self.candles = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval,
                                                                limit=self.KLINES_LIMIT)
        subscription = {"method": "sub.kline", 'param': {'symbol': self.symbol,
                                                         'interval': binance_intervals_to_mexc_intervals(
                                                             self.interval)}}
        self._unsubscribe(subscription)
        self._subscribe(subscription)

    def _handle_kline_message(self, message):
        assert message['symbol'] == self.symbol
        assert message['data']['interval'] == binance_intervals_to_mexc_intervals(self.interval)
        message = message['data']
        candle = [int(message['t'] * 1000),
                  format_float_in_standard_form(message['o']),
                  format_float_in_standard_form(message['h']),
                  format_float_in_standard_form(message['l']),
                  format_float_in_standard_form(message['c']),
                  format_float_in_standard_form(message['q']),
                  int(message['t'] * 1000) + int(binance_intervals_to_seconds(self.interval)) * 1000 - 1,
                  format_float_in_standard_form(message['a'])]
        if len(self.candles) == 0:
            self.candles.append(candle)
            return

        # if open_time of candle is the same as the last entry in self.candles - update, else append new candle
        if int(self.candles[-1][0]) == int(candle[0]):
            self.candles[-1] = candle
        else:
            # check if the next candle's open time fits in sequentially before adding
            if int(self.candles[-1][0]) + binance_intervals_to_seconds(self.interval) * 1000 == int(candle[0]):
                self.candles.append(candle)
                self.candles = self.candles[1:]
            else:
                # need to reset candles
                self.logger.writeline(
                    f"{self.symbol} WARNING: MEXC WS new candle does not fit. Getting candles from API...")
                self.set_up_candlesticks(resub_only=False)
                return

        self._last_candle_update_time = int(time.time())

    def _handle_order_message(self, message):
        if message['data']['symbol'] != self.symbol:
            return
        order = self.client.process_mexc_order_to_binance(message['data'])
        order['updateTime'] = int(time.time() * 1000)
        self.orders[order['orderId']] = order

        # clean up old CANCELLED, FILLED and EXPIRED orders that are older than OLD_ORDERS_TIME_LIMIT
        to_delete = []
        for orderId, order in self.orders.items():
            status = order["status"]
            updateTime = order["updateTime"]
            current_time = int(time.time() * 1000)
            if status != "NEW" and (updateTime < (current_time - self.OLD_ORDERS_TIME_LIMIT) or status == 'CANCELED'):
                to_delete.append(orderId)
        for oid in to_delete:
            self.orders.pop(oid)

    def _handle_wallet_message(self, message):
        currency = message['data']['currency']
        if currency == 'USDT':
            self.wallet_balance = message['data']['availableBalance']

    def _handle_position_message(self, message):
        if message['data']['symbol'] != self.symbol:
            return
        self.position = self.client.process_mexc_position_to_binance(message['data'])

    def _on_message(self, ws, raw_message):
        message = json.loads(raw_message)
        message_channel = message['channel']
        if message_channel in {'pong'}:
            return

        if message_channel == 'push.kline':
            self._handle_kline_message(message)
        elif message_channel == 'push.personal.order':
            self._handle_order_message(message)
        elif message_channel == 'push.personal.asset':
            self._handle_wallet_message(message)
        elif message_channel == 'push.personal.position':
            self._handle_position_message(message)

    def _subscribe(self, subscription: dict):
        self.send_json({**subscription})
        self._subscriptions.append(subscription)

    def _unsubscribe(self, subscription: dict):
        self.send_json({**subscription})
        while subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def get_order(self, orderId):
        if orderId in self.orders:
            self.logger.writeline(f"{self.symbol} MEXC Websockets provided order {self.orders[orderId]}")
            return self.orders[orderId]
        else:
            self.logger.writeline(f"{self.symbol} ERROR get_order: MEXC Websockets order {orderId} does not exist")
            self._login()
            return None

    def get_order_api_first(self, orderId):
        try:
            order = self.client.futures_get_order(self.symbol, orderId)
            if order:
                return order
            else:
                return self.get_order(orderId)
        except ConnectionError:
            return self.get_order(orderId)

    def get_candlesticks(self, limit):
        if check_if_candles_are_latest(self.candles):
            self.logger.writeline(f"{self.symbol} MEXC WS provided candlesticks")
            return self.candles[-limit:]
        else:
            self.logger.writeline(f"{self.symbol} ERROR MEXC Websockets get_candlesticks candles not current! Last update time: {self._last_candle_update_time}")
            # reset candles
            self.set_up_candlesticks(resub_only=False)
            raise Exception(f"{self.symbol} {get_current_datetime_string()} MEXC WS get_candlesticks Unable to provide candlesticks!")

    def get_candlesticks_api_first(self, limit):
        try:
            candles = self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)
            if candles:
                return candles
            else:
                return self.get_candlesticks(limit)
        except ConnectionError:
            return self.get_candlesticks(limit)

    def get_position_api_first(self):
        try:
            position = self.client.futures_get_position(self.symbol)
            if position:
                return position
            else:
                self.logger.writeline(f"{self.symbol} MEXC Websockets provided position {self.position}")
                return self.position
        except ConnectionError:
            self.logger.writeline(f"{self.symbol} MEXC Websockets provided position {self.position}")
            return self.position

    def get_wallet_balance_api_first(self):
        try:
            balance = self.client.futures_get_balance()
            if balance is not None:
                return balance
            else:
                self.logger.writeline(f"{self.symbol} MEXC Websockets provided wallet_balance {self.wallet_balance}")
                return self.wallet_balance
        except ConnectionError:
            self.logger.writeline(f"{self.symbol} MEXC Websockets provided wallet_balance {self.wallet_balance}")
            return self.wallet_balance

    def get_latest_price_api_first(self):
        try:
            price = self.client.futures_get_symbol_price(self.symbol)
            if price is not None:
                return price
            else:
                last_candle = self.get_candlesticks(1)
                latest_price = last_candle[4]
                self.logger.writeline(f"{self.symbol} MEXC Websockets provided latest_price {latest_price}")
                return latest_price
        except ConnectionError:
            last_candle = self.get_candlesticks(1)
            latest_price = last_candle[4]
            self.logger.writeline(f"{self.symbol} MEXC Websockets provided latest_price {latest_price}")
            return latest_price
