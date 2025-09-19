import json
from .FTXWebSocket import Websocket
from ..clients.UniversalClient import UniversalClient
from trading_automation.core.Utils import binance_intervals_to_seconds
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
import time
from typing import Dict, List
from trading_automation.core.Utils import binance_intervals_to_mexc_intervals, format_float_in_standard_form


class CapitalWebSocketManager(Websocket, WebsocketInterface):
    _ENDPOINT = 'wss://api-streaming-capital.backend-capital.com/connect'

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50) -> None:
        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.client = client
        self._api_key = None
        self._api_secret = None
        self.logger = self.client.logger
        self.KLINES_LIMIT = candles_limit
        self.candles_bids, self.candles_asks = self.client.futures_get_candlesticks(symbol=symbol, limit=self.KLINES_LIMIT,
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
        # threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self):
        while True:
            self.send_json({"destination": "ping",
                            "correlationId": 1,
                            "cst": self.client.client_capital._authorization_token,
                            "securityToken": self.client.client_capital._security_token
                            })
            time.sleep(60)

    def _get_url(self):
        return self._ENDPOINT

    def set_up_candlesticks(self, resub_only=True):
        if not resub_only:
            self.candles_bids, self.candles_asks = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval,
                                                                                        limit=self.KLINES_LIMIT)
        unsubscription = {"destination": "marketData.unsubscribe",
                          "correlationId": 1,
                          "cst": self.client.client_capital._authorization_token,
                          "securityToken": self.client.client_capital._security_token,
                          "payload": {"epics": [self.symbol]}
                          }
        subscription = {"destination": "marketData.subscribe",
                        "correlationId": 1,
                        "cst": self.client.client_capital._authorization_token,
                        "securityToken": self.client.client_capital._security_token,
                        "payload": {"epics": [self.symbol]}
                        }
        self._unsubscribe(unsubscription)
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

    def _on_message(self, ws, raw_message):
        message = json.loads(raw_message)
        # print(message)
        message_channel = message['destination']
        if message_channel in {'ping', "marketData.unsubscribe", "marketData.subscribe"}:
            return

        if message_channel == 'push.kline':
            self._handle_kline_message(message)

    def _subscribe(self, subscription: dict):
        self.send_json({**subscription})
        self._subscriptions.append(subscription)

    def _unsubscribe(self, subscription: dict):
        self.send_json({**subscription})
        while subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def get_order(self, orderId):
        return self.client.futures_get_order(self.symbol, orderId)

    def get_order_api_first(self, orderId):
        return self.get_order(orderId=orderId)

    def get_candlesticks(self, limit):
        return self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)

    def get_candlesticks_api_first(self, limit):
        return self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)

    def get_position_api_first(self):
        position = self.client.futures_get_position(self.symbol)
        if position:
            return position
        else:
            self.logger.writeline(f"{self.symbol} CAPITAL client unable to provide position")
            raise Exception(f"{self.symbol} CAPITAL client unable to provide position")

    def get_wallet_balance_api_first(self):
        balance = self.client.futures_get_balance()
        if balance is not None:
            return balance
        else:
            self.logger.writeline(f"{self.symbol} CAPITAL client unable to provide wallet_balance")
            raise Exception(f"{self.symbol} CAPITAL client unable to provide wallet_balance")

    def get_latest_price_api_first(self):
        try:
            price = self.client.futures_get_symbol_price(self.symbol)
            if price is not None:
                return price
            else:
                last_candle = self.get_candlesticks(1)
                latest_price = last_candle[4]
                self.logger.writeline(f"{self.symbol} CAPITAL Websockets provided latest_price {latest_price}")
                return latest_price
        except ConnectionError:
            last_candle = self.get_candlesticks(1)
            latest_price = last_candle[4]
            self.logger.writeline(f"{self.symbol} MEXC Websockets provided latest_price {latest_price}")
            return latest_price
