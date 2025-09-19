import json
from .FTXWebSocket import Websocket
from trading_automation.core.Utils import check_if_candles_are_latest, get_current_datetime_string
from ..clients.UniversalClient import UniversalClient, GATEIO_API_SECRET, GATEIO_API_KEY, GATEIO_USER_ID, GATEIO_API_SECRET_SECOND, GATEIO_API_KEY_SECOND, GATEIO_USER_ID_SECOND, GATEIO_API_SECRET_THIRD, GATEIO_API_KEY_THIRD, GATEIO_USER_ID_THIRD, GATEIO_API_SECRET_FOURTH, GATEIO_API_KEY_FOURTH, GATEIO_USER_ID_FOURTH
from trading_automation.core.Utils import binance_intervals_to_seconds
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
import hmac, hashlib, time
from typing import Dict, List
from gate_api import FuturesOrder, ApiException
import threading


class GateWebSocketManager(Websocket, WebsocketInterface):
    """
    Notes: Candlesticks only push updates roughly every 3 seconds
    """
    _ENDPOINT = 'wss://fx-ws.gateio.ws/v4/ws/usdt'

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50) -> None:
        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.OLD_ORDERS_TIME_LIMIT = 300000  # time limit in milliseconds 300000 = 5 minute
        self.interval_seconds = binance_intervals_to_seconds(interval)
        self.wallet_balance = 0
        self.client = client
        self.logger = self.client.logger
        self.position = self.client.futures_get_position(symbol=symbol)
        self.orders = {}
        self.KLINES_LIMIT = candles_limit
        self._subscriptions: List[Dict] = []
        self.candles = []
        self.set_up_candlesticks(resub_only=False)
        self._last_candle_update_time = int(time.time())
        self.orders = {}
        open_orders = self.client.futures_get_open_orders(self.symbol)
        if open_orders:
            for order in open_orders:
                order["updateTime"] = int(time.time() * 1000)
                self.orders[order['orderId']] = order
        if "LowStakes" in self.client.exchange:
            self.gateio_user_id = GATEIO_USER_ID_SECOND
            self.gateio_api_secret = GATEIO_API_SECRET_SECOND
            self.gateio_api_key = GATEIO_API_KEY_SECOND
        elif "3" in self.client.exchange:
            self.gateio_user_id = GATEIO_USER_ID_THIRD
            self.gateio_api_secret = GATEIO_API_SECRET_THIRD
            self.gateio_api_key = GATEIO_API_KEY_THIRD
        elif "4" in self.client.exchange:
            self.gateio_user_id = GATEIO_USER_ID_FOURTH
            self.gateio_api_secret = GATEIO_API_SECRET_FOURTH
            self.gateio_api_key = GATEIO_API_KEY_FOURTH
        else:
            self.gateio_user_id = GATEIO_USER_ID
            self.gateio_api_secret = GATEIO_API_SECRET
            self.gateio_api_key = GATEIO_API_KEY
        self._subscribe("futures.orders", payload=[self.gateio_user_id, self.symbol], auth_required=True)
        self.position = self.get_position_api_first()
        self._subscribe("futures.positions", payload=[self.gateio_user_id, self.symbol], auth_required=True)
        self._subscribe("futures.position_closes", payload=[self.gateio_user_id, self.symbol], auth_required=True)
        self.wallet_balance = self.client.futures_get_balance()
        self._subscribe("futures.balances", payload=[self.gateio_user_id], auth_required=True)
        threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self):
        while True:
            self._request("futures.ping")
            time.sleep(10)

    def _get_url(self) -> str:
        return self._ENDPOINT

    def _get_sign(self, message):
        h = hmac.new(self.gateio_api_secret.encode("utf8"), message.encode("utf8"), hashlib.sha512)
        return h.hexdigest()

    def _request(self, channel, event=None, payload=None, auth_required=False):
        current_time = int(time.time())
        data = {
            "time": current_time,
            "channel": channel,
            "event": event,
            "payload": payload,
        }
        if auth_required:
            message = 'channel=%s&event=%s&time=%d' % (channel, event, current_time)
            data['auth'] = {
                "method": "api_key",
                "KEY": self.gateio_api_key,
                "SIGN": self._get_sign(message),
            }
        self.send_json(data)

    def _subscribe(self, channel, payload=None, auth_required=False):
        self._request(channel, "subscribe", payload, auth_required)

    def _unsubscribe(self, channel, payload=None, auth_required=False):
        self._request(channel, "unsubscribe", payload, auth_required)

    def set_up_candlesticks(self, resub_only=True):
        if not resub_only:
            self.candles = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval,
                                                                limit=self.KLINES_LIMIT)
            self._last_candle_update_time = int(time.time())
        self._unsubscribe("futures.candlesticks", payload=[self.interval, self.symbol])
        self._subscribe("futures.candlesticks", payload=[self.interval, self.symbol])

    def _handle_candlesticks_message(self, candles):
        candles = [[candle['t'] * 1000, candle['o'], candle['h'], candle['l'], candle['c'],
                    (candle['t'] + binance_intervals_to_seconds(self.interval)) * 1000 - 1] for candle in candles]
        for candle in candles:
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
                    # self.logger.writeline(f"{self.symbol} WARNING: GATE WS new candle does not fit. Current candles: {self.candles}. New candle {candle}. Getting candles from API...")
                    self.set_up_candlesticks(resub_only=False)
                    return

        self._last_candle_update_time = int(time.time())

    def _handle_orders_message(self, o):
        finish_as = o['finish_as'] if o['finish_as'] in \
            ['filled', 'cancelled', 'liquidated', 'ioc', 'auto_deleveraged', 'reduce_only', 'position_closed', 'reduce_out'] \
            else None
        order = self.client.process_gate_order_to_binance(FuturesOrder(text=o['text'], id=o['id'], contract=o['contract'], price=o['price'], size=o['size'], status=o['status'], finish_as=finish_as, is_reduce_only=o['is_reduce_only'], fill_price=o['fill_price'], left=o['left']))
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

    def _handle_position_message(self, position):
        position = [{"entryPrice": str(position['entry_price']),
                     "positionAmt": str(position['size'] * self.client.precisionQuantityDict[self.symbol]),
                     "symbol": position['contract'],
                     "unRealizedProfit": 'unknown'}]
        self.position = position

    def _handle_wallet_message(self, message):
        self.wallet_balance = message['balance']

    def _on_message(self, ws, raw_message):
        message = json.loads(raw_message)
        if 'channel' in message:
            if message['channel'] == "futures.candlesticks" and message['event'] == "update":
                self._handle_candlesticks_message(message['result'])
            elif message['channel'] == "futures.position_closes" and message['event'] == "update":
                self.position = [{"entryPrice": "0",
                                  "positionAmt": "0", "symbol": self.symbol,
                                  "unRealizedProfit": "0"}]
            elif message['channel'] == "futures.positions" and message['event'] == "update":
                self._handle_position_message(message['result'][0])
            elif message['channel'] == "futures.balances" and message['event'] == "update":
                self._handle_wallet_message(message['result'][0])
            elif message['channel'] == "futures.orders" and message['event'] == "update":
                self._handle_orders_message(message['result'][0])

    def get_order(self, orderId):
        if orderId in self.orders:
            self.logger.writeline(f"{self.symbol} GATE Websockets provided order {self.orders[orderId]}")
            return self.orders[orderId]
        else:
            self.logger.writeline(f"{self.symbol} ERROR get_order: Websockets order {orderId} does not exist")
            self._subscribe("futures.orders", payload=[self.gateio_user_id, self.symbol], auth_required=True)
            return None

    def get_order_api_first(self, orderId):
        try:
            order = self.client.futures_get_order(self.symbol, orderId)
            if order:
                return order
            else:
                return self.get_order(orderId)
        except (ConnectionError, ApiException):
            return self.get_order(orderId)

    def get_candlesticks(self, limit):
        if check_if_candles_are_latest(self.candles):
            return self.candles[-limit:]
        else:
            self.logger.writeline(f"{self.symbol} ERROR Websockets get_candlesticks candles not current! Last update time: {self._last_candle_update_time}")
            # reset candles
            self.set_up_candlesticks(resub_only=False)
            if check_if_candles_are_latest(self.candles):
                self.logger.writeline(f"{self.symbol} API provided candlesticks")
                return self.candles[-limit:]
            else:
                raise Exception(f"{self.symbol} {get_current_datetime_string()} GATE WS get_candlesticks Unable to provide candlesticks!")

    def get_candlesticks_api_first(self, limit):
        # candlesticks = self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)
        # if candlesticks and check_if_candles_are_latest(candlesticks):
        #     return candlesticks
        # else:
        #     candlesticks = self.get_candlesticks(limit)
        #     if candlesticks:
        #         self.logger.writeline(f"{self.symbol} Websockets provided candlesticks")
        #     return candlesticks
        # Because api candles are not as latest as ws, return ws results.
        return self.get_candlesticks(limit)

    def get_position_api_first(self):
        try:
            position = self.client.futures_get_position(self.symbol)
            if position:
                return position
            else:
                self.logger.writeline(f"{self.symbol} GATE Websockets provided position {self.position}")
                return self.position
        except (ConnectionError, ApiException):
            self.logger.writeline(f"{self.symbol} GATE Websockets provided position {self.position}")
            return self.position

    def get_wallet_balance_api_first(self):
        try:
            balance = self.client.futures_get_balance()
            if balance is not None:
                return balance
            else:
                self.logger.writeline(f"{self.symbol} GATE Websockets provided wallet_balance {self.wallet_balance}")
                return self.wallet_balance
        except (ConnectionError, ApiException):
            self.logger.writeline(f"{self.symbol} GATE Websockets provided wallet_balance {self.wallet_balance}")
            return self.wallet_balance

    def get_latest_price_api_first(self):
        try:
            price = self.client.futures_get_symbol_price(self.symbol)
            if price is not None:
                return price
            else:
                last_candle = self.get_candlesticks(1)
                latest_price = last_candle[4]
                self.logger.writeline(f"{self.symbol} GATE Websockets provided latest_price {latest_price}")
                return latest_price
        except (ConnectionError, ApiException):
            last_candle = self.get_candlesticks(1)
            latest_price = last_candle[4]
            self.logger.writeline(f"{self.symbol} GATE Websockets provided latest_price {latest_price}")
            return latest_price
