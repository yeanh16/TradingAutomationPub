from datetime import datetime, timedelta
from trading_automation.core.Utils import binance_intervals_to_kucoin_intervals, \
    make_cloned_zero_vol_candle
from trading_automation.clients.UniversalClient import UniversalClient
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
from threading import Event
from queue import Queue


class PhemexWebSocketManager(WebsocketInterface):

    def __init__(self, symbol, interval, client: UniversalClient, phemex_ws_input_q: Queue, phemex_ws_output_q: Queue, candles_limit=50) -> None:
        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.client = client
        self.KLINES_LIMIT = candles_limit
        self.phemex_ws_input_q = phemex_ws_input_q
        self.phemex_ws_output_q = phemex_ws_output_q
        self.candles = self._request_from_master((self.symbol, self.interval))
        self.orders = self._request_from_master('orders')
        self.position = self._request_from_master(self.symbol)
        self.total_wallet_balance = self._request_from_master('get_wallet_balance')

    def _request_from_master(self, request):
        evt = Event()
        self.phemex_ws_input_q.put((request, evt))
        evt.wait()
        response, evt = self.phemex_ws_output_q.get()
        evt.set()
        return response

    def get_order(self, orderId):
        self.orders = self._request_from_master('orders')
        if orderId in self.orders:
            return self.orders[orderId]
        return None

    def get_order_api_first(self, orderId):
        order = self.get_order(orderId)
        if order is None:
            self._request_from_master('refresh_orders')
            order = self.client.futures_get_order(symbol=self.symbol, orderId=orderId)
        return order

    def get_candlesticks(self, limit):
        self.candles = self._request_from_master((self.symbol, self.interval))
        # need to add on missing '0' volume candles until current time (if any)
        now = datetime.now()
        if binance_intervals_to_kucoin_intervals(self.interval) <= 60:
            current_start_time = now - timedelta(minutes=now.minute % binance_intervals_to_kucoin_intervals(self.interval),
                                                 seconds=now.second, microseconds=now.microsecond)
        elif binance_intervals_to_kucoin_intervals(self.interval) == 1440:
            current_start_time = now - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second,
                                                 microseconds=now.microsecond)
        else:
            current_start_time = now - timedelta(days=now.day, hours=now.hour, minutes=now.minute, seconds=now.second,
                                                 microseconds=now.microsecond)
        last_candle = self.candles[-1]
        while last_candle[0] != current_start_time.timestamp() * 1000:
            next_candle = make_cloned_zero_vol_candle(last_candle, self.interval)
            self.candles.append(next_candle)
            last_candle = next_candle

        return self.candles[-limit:]

    def get_candlesticks_api_first(self, limit):
        return self.get_candlesticks(limit)

    def get_position(self):
        self.position = self._request_from_master(self.symbol)
        return self.position

    def get_position_api_first(self):
        return self.get_position()

    def get_wallet_balance(self):
        self.total_wallet_balance = self._request_from_master('get_wallet_balance')
        return self.total_wallet_balance

    def get_wallet_balance_api_first(self):
        return self.get_wallet_balance()

    def get_latest_price_api_first(self):
        return self.client.futures_get_symbol_price(self.symbol)

