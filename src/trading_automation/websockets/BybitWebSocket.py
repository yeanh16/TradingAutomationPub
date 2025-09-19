import json
from .FTXWebSocket import Websocket
from trading_automation.core.Utils import check_if_candles_are_latest, get_current_datetime_string, binance_intervals_to_bybit_intervals, format_float_in_standard_form
from ..clients.UniversalClient import UniversalClient, BYBIT_API_SECRET, BYBIT_API_KEY, BYBIT_API_KEY_SECOND, BYBIT_API_SECRET_SECOND
from trading_automation.core.Utils import binance_intervals_to_seconds
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
import hmac, time
from typing import List
import threading
from time import sleep


class BybitWebSocket(Websocket, WebsocketInterface):
    _ENDPOINT_PUBLIC = 'wss://stream.bybit.com/v5/public/linear'
    _ENDPOINT_PRIVATE = 'wss://stream.bybit.com/v5/private'

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50, public=True) -> None:
        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.client = client
        self.logger = self.client.logger
        self._subscriptions: List = []
        self.OLD_ORDERS_TIME_LIMIT = 300000  # time limit in milliseconds
        self._api_key = BYBIT_API_KEY if "2" not in self.client.exchange else BYBIT_API_KEY_SECOND
        self._api_secret = BYBIT_API_SECRET if "2" not in self.client.exchange else BYBIT_API_SECRET_SECOND
        if public:
            self.url = self._ENDPOINT_PUBLIC
            self.KLINES_LIMIT = candles_limit
            self.candles = []
            self.set_up_candlesticks(resub_only=False)
        else:
            self.url = self._ENDPOINT_PRIVATE
            self._login()
            self.wallet_balance = client.futures_get_total_balance()
            self.position = self.client.futures_get_position(symbol=symbol)
            self.orders = {}
            open_orders = self.client.futures_get_open_orders(self.symbol)
            if open_orders:
                for order in open_orders:
                    order['updateTime'] = int(time.time() * 1000)
                    self.orders[order['orderId']] = order
            self._subscribe(['position', 'wallet', 'order'])

        threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self):
        while True:
            self.send_json({"op": "ping"})
            time.sleep(10)

    def _login(self):
        """
        Authorize websocket connection.
        """

        # Generate expires.
        expires = int((time.time() + 5) * 1000)

        # Generate signature.
        _val = f'GET/realtime{expires}'
        signature = str(hmac.new(
            bytes(self._api_secret, 'utf-8'),
            bytes(_val, 'utf-8'), digestmod='sha256'
        ).hexdigest())

        # Authenticate with API.
        self.send(
            json.dumps({
                'op': 'auth',
                'args': [self._api_key, expires, signature]
            })
        )
        self._logged_in = True

    def _get_url(self):
        return self.url

    def _handle_candlesticks_message(self, data):
        for candle_data in data:
            candle = [candle_data['start'],
                      format_float_in_standard_form(candle_data['open']),
                      format_float_in_standard_form(candle_data['high']),
                      format_float_in_standard_form(candle_data['low']),
                      format_float_in_standard_form(candle_data['close']),
                      candle_data['volume'],
                      candle_data['end'],
                      candle_data['turnover']]

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
                    # self.logger.writeline(f"{self.symbol} WARNING: BYBIT WS new candle does not fit. Getting candles from API...")
                    self.set_up_candlesticks(resub_only=False)
                    return
            self._last_candle_update_time = int(time.time())

    def _handle_position_message(self, data):
        for position_data in data:
            if position_data['symbol'] == self.symbol:
                position = self.client.process_bybit_position_to_binance(position_data)
                self.position = position

    def _handle_order_message(self, data):
        for order_data in data:
            if order_data['symbol'] == self.symbol:
                order = self.client.process_bybit_order_to_binance(order_data)
                order['updateTime'] = int(time.time() * 1000)
                self.orders[order['orderId']] = order

                # clean up old CANCELLED, FILLED and EXPIRED orders that are older than OLD_ORDERS_TIME_LIMIT
                to_delete = []
                for orderId, order in self.orders.items():
                    status = order["status"]
                    updateTime = order["updateTime"]
                    current_time = int(time.time() * 1000)
                    if status != "NEW" and (
                            updateTime < (current_time - self.OLD_ORDERS_TIME_LIMIT) or status == 'CANCELED'):
                        to_delete.append(orderId)
                for oid in to_delete:
                    self.orders.pop(oid)

    def _handle_wallet_message(self, data):
        # bybit websocket doesn't seem to give current equity balance (total wallet balance inc. unrealised pnl)
        for wallet_data in data:
            self.wallet_balance = wallet_data['walletBalance']

    def _on_message(self, ws, raw_message):
        message = json.loads(raw_message)
        # print(message)

        # Did we receive a message regarding auth or subscription?
        msg_json = message
        auth_message = True if isinstance(msg_json, dict) and \
            (msg_json.get('auth') or
             msg_json.get('request', {}).get('op') == 'auth') else False
        subscription_message = True if isinstance(msg_json, dict) and \
            ((msg_json.get('event') == 'sub' or msg_json.get('code')) or
             msg_json.get('request', {}).get('op') == 'subscribe') else False

        # Check auth
        if auth_message:
            if msg_json.get('auth') == 'fail' or \
                    msg_json.get('success') is False:
                self.client.logger.writeline(f'{self.symbol} ERROR BYBIT WEBSOCKETS Authorization failed')

        # Check subscription
        if subscription_message:
            # Futures subscription fail
            if msg_json.get('success') is False:
                response = msg_json['ret_msg']
                if 'unknown topic' in response:
                    self.client.logger.writeline(f'{self.symbol} ERROR BYBIT WEBSOCKETS Couldn\'t subscribe to topic.'
                                      f' Error: {response}.')
            # Spot subscription fail
            elif msg_json.get('code'):
                self.client.logger.writeline(f'{self.symbol} ERROR BYBIT WEBSOCKETS Couldn\'t subscribe to topic.'
                                  f' Error code: {msg_json["code"]}.'
                                  f' Error message: {msg_json.get("desc")}.')

        if 'topic' in message:
            if 'candle' in message['topic']:
                self._handle_candlesticks_message(message['data'])
            elif 'wallet' in message['topic']:
                self._handle_wallet_message(message['data'])
            elif 'position' in message['topic']:
                self._handle_position_message(message['data'])
            elif 'order' in message['topic']:
                self._handle_order_message(message['data'])

    def _subscribe(self, subscriptions: List):
        self.send_json({'op': 'subscribe', 'args': subscriptions})
        self._subscriptions += subscriptions

    def _unsubscribe(self, subscriptions: List):
        self.send_json({'op': 'unsubscribe', 'args': subscriptions})
        for subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def set_up_candlesticks(self, resub_only=True):
        if not resub_only:
            # self.logger.writeline("Resetting candles...")
            sleep(1)
            self.candles = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval, limit=self.KLINES_LIMIT)
        subscription = [f'candle.{binance_intervals_to_bybit_intervals(self.interval)}.{self.symbol}']
        self._unsubscribe(subscription)
        self._subscribe(subscription)

    def get_order(self, orderId):
        if orderId in self.orders:
            return self.orders[orderId]
        else:
            self.logger.writeline(f"ERROR get_order: {self.symbol} BYBIT Websockets order {orderId} does not exist")
            return None

    def get_order_api_first(self, orderId):
        order = self.client.futures_get_order(self.symbol, orderId)
        if order:
            return order
        else:
            order = self.get_order(orderId)
            if order:
                self.logger.writeline(f"{self.symbol} BYBIT Websockets provided order {order}")
                return order
        raise Exception(f"{self.symbol} ERROR: BYBIT Websockets and API not able to provide order")

    def get_candlesticks(self, limit):
        if check_if_candles_are_latest(self.candles):
            # self.logger.writeline(f"{self.symbol} BYBIT WS provided candlesticks")
            return self.candles[-limit:]
        else:
            self.logger.writeline(f"{self.symbol} ERROR BYBIT Websockets get_candlesticks candles not current! Last update time: {self._last_candle_update_time}")
            # reset candles
            self.set_up_candlesticks(resub_only=False)
            raise Exception(f"{self.symbol} {get_current_datetime_string()} BYBIT WS get_candlesticks unable to provide candlesticks!")

    def get_candlesticks_api_first(self, limit):
        try:
            candles = self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)
            if (200 > limit != len(candles)) or (limit >= 200 and len(candles) != 200) or candles is None:
                # API didn't get correct number of candles, return ws results instead
                return self.get_candlesticks(limit)
            else:
                return candles
        except:
            return self.get_candlesticks(limit)

    def get_position(self):
        return self.position

    def get_position_api_first(self):
        try:
            position = self.client.futures_get_position(self.symbol)
            return position
        except:
            self.logger.writeline(f"{self.symbol} BYBIT Websockets provided position {self.position}")
            return self.get_position()

    def get_wallet_balance_api_first(self):
        try:
            balance = self.client.futures_get_balance()
            return balance
        except:
            self.logger.writeline(f"{self.symbol} BYBIT Websockets provided wallet_balance {self.wallet_balance}")
            return self.wallet_balance

    def get_latest_price_api_first(self):
        try:
            price = self.client.futures_get_symbol_price(self.symbol)
            return price
        except:
            last_candle = self.get_candlesticks(1)
            latest_price = last_candle[4]
            self.logger.writeline(f"{self.symbol} Websockets provided latest_price {latest_price}")
            return latest_price

