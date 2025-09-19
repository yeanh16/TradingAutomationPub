import hmac
import json
import zlib
from collections import defaultdict, deque
from itertools import zip_longest
from typing import DefaultDict, Deque, List, Dict, Tuple, Optional
from gevent.event import Event
from trading_automation.core.Utils import *
from .FTXWebSocket import Websocket
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
from ..clients.UniversalClient import FTX_API_SECRET, FTX_API_KEY, UniversalClient, process_ftx_order_to_binance
from trading_automation.core.Utils import binance_intervals_to_seconds
from statistics import median
import threading


class FtxWebSocketManager(Websocket, WebsocketInterface):
    _ENDPOINT = 'wss://ftx.com/ws/'
    _WS_CANDLES_TIMEOUT_LIMIT = 2  # in seconds, if the last price is not updated within this time - reset

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50) -> None:
        super().__init__()
        self._trades: DefaultDict[str, Deque] = defaultdict(lambda: deque([], maxlen=10000))
        self._fills: Deque = deque([], maxlen=10000)
        self._api_key = FTX_API_KEY
        self._api_secret = FTX_API_SECRET
        self._orderbook_update_events: DefaultDict[str, Event] = defaultdict(Event)
        self._reset_data()
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
        # below variables to keep track of last market trades
        self._set_up_orders()
        self._candles_last_update_time = int(time.time())
        self._set_up_candles(resub_only=False)
        # need a thread to constantly monitor candlestick update time
        threading.Thread(target=self._check_ticker_subscription_channel, daemon=True).start()
        # need a thread to constantly ping server to stay alive
        threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self):
        while True:
            self.send_json({'op': 'ping'})
            time.sleep(10)

    def _set_up_candles(self, resub_only=True):
        """
        :param resub_only set to True if we only want to resub to the ticker channel
        subscribes and begins storing candles from ws.
        can also be used to restart the process if stopped
        """
        if not resub_only:
            self.candles = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval, limit=self.KLINES_LIMIT)
            # change the last candle to have an up to date close time (to not trigger warning when checking if candles are latest)
            if self.candles:
                open_time = self.candles[-1][0]
                current_time = int(time.time())
                # make sure that the open time of the api candle is valid before changing close time
                if current_time - self.interval_seconds < open_time/1000:
                    self.candles[-1][6] = open_time + self.interval_seconds * 1000 - 1
                self.current_candle_open_time = int(self.candles[-1][0] / 1000)
                self._candles_last_update_time = current_time
        # (re)subscribe to ticker info
        self._unsubscribe({'channel': 'ticker', 'market': self.symbol})
        self.get_ticker(market=self.symbol)
        self.new_candle_flag = True
        # wait a bit for latest price to come through
        time.sleep(0.1)

    def _set_up_orders(self):
        """
        Subscribes and begins storing order info from ws.
        Can also be used to reset
        """
        open_orders = self.client.futures_get_open_orders(self.symbol)
        if open_orders:
            for order in open_orders:
                order['updateTime'] = int(time.time() * 1000)
                self.orders[order['orderId']] = order
        # subscribe to orders
        self._unsubscribe({'channel': 'orders'})
        self.get_orders()

    def _on_open(self, ws):
        self._reset_data()

    def _reset_data(self) -> None:
        self._subscriptions: List[Dict] = []
        self._orders: DefaultDict[int, Dict] = defaultdict(dict)
        self._tickers: DefaultDict[str, Dict] = defaultdict(dict)
        self._orderbook_timestamps: DefaultDict[str, float] = defaultdict(float)
        self._orderbook_update_events.clear()
        self._orderbooks: DefaultDict[str, Dict[str, DefaultDict[float, float]]] = defaultdict(
            lambda: {side: defaultdict(float) for side in {'bids', 'asks'}})
        self._orderbook_timestamps.clear()
        self._logged_in = False
        self._last_received_orderbook_data_at: float = 0.0

    def _reset_orderbook(self, market: str) -> None:
        if market in self._orderbooks:
            del self._orderbooks[market]
        if market in self._orderbook_timestamps:
            del self._orderbook_timestamps[market]

    def _get_url(self) -> str:
        return self._ENDPOINT

    def _login(self) -> None:
        ts = int(time.time() * 1000)
        self.send_json({'op': 'login', 'args': {
            'key': self._api_key,
            'sign': hmac.new(
                self._api_secret.encode(), f'{ts}websocket_login'.encode(), 'sha256').hexdigest(),
            'time': ts,
        }})
        self._logged_in = True

    def _subscribe(self, subscription: Dict) -> None:
        self.send_json({'op': 'subscribe', **subscription})
        self._subscriptions.append(subscription)

    def _unsubscribe(self, subscription: Dict) -> None:
        self.send_json({'op': 'unsubscribe', **subscription})
        while subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def _resubscribe(self, subscription: Dict) -> None:
        self._unsubscribe(subscription=subscription)
        self._subscribe(subscription=subscription)

    def get_fills(self) -> List[Dict]:
        if not self._logged_in:
            self._login()
        subscription = {'channel': 'fills'}
        if subscription not in self._subscriptions:
            self._subscribe(subscription)
        return list(self._fills.copy())

    def get_orders(self) -> Dict[int, Dict]:
        if not self._logged_in:
            self._login()
        subscription = {'channel': 'orders'}
        if subscription not in self._subscriptions:
            self._subscribe(subscription)
        return dict(self._orders.copy())

    def get_trades(self, market: str) -> List[Dict]:
        subscription = {'channel': 'trades', 'market': market}
        if subscription not in self._subscriptions:
            self._subscribe(subscription)
        return list(self._trades[market].copy())

    def get_orderbook(self, market: str) -> Dict[str, List[Tuple[float, float]]]:
        subscription = {'channel': 'orderbook', 'market': market}
        if subscription not in self._subscriptions:
            self._subscribe(subscription)
        if self._orderbook_timestamps[market] == 0:
            self.wait_for_orderbook_update(market, 5)
        return {
            side: sorted(
                [(price, quantity) for price, quantity in list(self._orderbooks[market][side].items())
                 if quantity],
                key=lambda order: order[0] * (-1 if side == 'bids' else 1)
            )
            for side in {'bids', 'asks'}
        }

    def get_orderbook_timestamp(self, market: str) -> float:
        return self._orderbook_timestamps[market]

    def wait_for_orderbook_update(self, market: str, timeout: Optional[float]) -> None:
        subscription = {'channel': 'orderbook', 'market': market}
        if subscription not in self._subscriptions:
            self._subscribe(subscription)
        self._orderbook_update_events[market].wait(timeout)

    def get_ticker(self, market: str) -> Dict:
        subscription = {'channel': 'ticker', 'market': market}
        if subscription not in self._subscriptions:
            self._subscribe(subscription)
        return self._tickers[market]

    def _handle_orderbook_message(self, message: Dict) -> None:
        market = message['market']
        subscription = {'channel': 'orderbook', 'market': market}
        if subscription not in self._subscriptions:
            return
        data = message['data']
        if data['action'] == 'partial':
            self._reset_orderbook(market)
        for side in {'bids', 'asks'}:
            book = self._orderbooks[market][side]
            for price, size in data[side]:
                if size:
                    book[price] = size
                else:
                    del book[price]
            self._orderbook_timestamps[market] = data['time']
        checksum = data['checksum']
        orderbook = self.get_orderbook(market)
        checksum_data = [
            ':'.join([f'{float(order[0])}:{float(order[1])}' for order in (bid, offer) if order])
            for (bid, offer) in zip_longest(orderbook['bids'][:100], orderbook['asks'][:100])
        ]

        computed_result = int(zlib.crc32(':'.join(checksum_data).encode()))
        if computed_result != checksum:
            self._last_received_orderbook_data_at = 0
            self._reset_orderbook(market)
            self._unsubscribe({'market': market, 'channel': 'orderbook'})
            self._subscribe({'market': market, 'channel': 'orderbook'})
        else:
            self._orderbook_update_events[market].set()
            self._orderbook_update_events[market].clear()

    def _handle_trades_message(self, message: Dict) -> None:
        self._trades[message['market']] = message['data']

    def _handle_ticker_message(self, message: Dict) -> None:
        # self._tickers[message['market']] = message['data']
        # manually create a new candle using the last_price from websocket at the specified interval
        # last_price = Mark Price which is median of last, best bid, best offer
        last_price = str(median([Decimal(format_float_in_standard_form(message['data']['bid'])), Decimal(format_float_in_standard_form(message['data']['ask'])), Decimal(format_float_in_standard_form(message['data']['last']))]))
        current_time = int(message['data']['time'])
        #print(f"{get_current_datetime_string()} {current_time} last price {last_price}")
        if current_time % self.interval_seconds == 0 and self.new_candle_flag:
            self.candles.pop(0)
            self.candles.append([current_time*1000, last_price, last_price, last_price, last_price, 0, (current_time+self.interval_seconds)*1000-1])
            self.current_candle_open_time = current_time
            # if the second/third most recent candle from API open_time is same as old stored candle, use it to replace stored candle
            latest_candles_from_api = self.client.futures_get_candlesticks(symbol=self.symbol, limit=3, interval=self.interval)
            if latest_candles_from_api[0][0] == self.candles[-4][0]:
                self.candles[-4] = latest_candles_from_api[0]
            elif latest_candles_from_api[0][0] == self.candles[-3][0]:
                self.candles[-3] = latest_candles_from_api[0]
            if latest_candles_from_api[1][0] == self.candles[-3][0]:
                self.candles[-3] = latest_candles_from_api[1]
            elif latest_candles_from_api[1][0] == self.candles[-2][0]:
                self.candles[-2] = latest_candles_from_api[1]
            self.new_candle_flag = False
            #print(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} {self.candles}")
        elif self.current_candle_open_time + self.interval_seconds <= current_time:
            # this case happens if no update was received on the interval second
            # we need to make a new candle
            self.candles.pop(0)
            self.candles.append([(self.current_candle_open_time + self.interval_seconds)*1000, last_price, last_price, last_price, last_price, 0, (current_time+self.interval_seconds)*1000-1])
            self.current_candle_open_time = self.current_candle_open_time + self.interval_seconds
            # if the second/third most recent candle from API open_time is same as old stored candle, use it to replace stored candle
            latest_candles_from_api = self.client.futures_get_candlesticks(symbol=self.symbol, limit=3, interval=self.interval)
            if latest_candles_from_api[0][0] == self.candles[-4][0]:
                self.candles[-4] = latest_candles_from_api[0]
            elif latest_candles_from_api[0][0] == self.candles[-3][0]:
                self.candles[-3] = latest_candles_from_api[0]
            if latest_candles_from_api[1][0] == self.candles[-3][0]:
                self.candles[-3] = latest_candles_from_api[1]
            elif latest_candles_from_api[1][0] == self.candles[-2][0]:
                self.candles[-2] = latest_candles_from_api[1]
            #print(f"{get_current_datetime_string()} Created a new candle not on interval! candles {self.candles}")
        else:
            latest_candle = self.candles[-1]
            latest_candle[4] = last_price
            if Decimal(latest_candle[2]) < Decimal(last_price):
                latest_candle[2] = last_price
            if Decimal(latest_candle[3]) > Decimal(last_price):
                latest_candle[3] = last_price
            self.candles[-1] = latest_candle
        if current_time % 2 == 1:
            self.new_candle_flag = True
        self._candles_last_update_time = int(time.time())

    def _check_ticker_subscription_channel(self):
        while True:
            if not self._candles_last_update_time_check():
                self._set_up_candles()
            time.sleep(self._WS_CANDLES_TIMEOUT_LIMIT)

    def _handle_fills_message(self, message: Dict) -> None:
        self._fills.append(message['data'])
        #print(f"fills {message['data']}")

    def _handle_orders_message(self, message: Dict) -> None:
        """
        we only get normal, non conditional order updates on this channel
        :param message:
        :return:
        """
        order = message['data']
        #print(f"update {order}")
        if order['market'] != self.symbol:
            return
        self.orders[order['id']] = process_ftx_order_to_binance(order)
        # add 'updateTime' to the order so that websocket manager knows when to delete
        current_time = int(time.time() * 1000)
        self.orders[order['id']]['updateTime'] = current_time
        # clean up old CANCELLED, FILLED and EXPIRED orders that are older than OLD_ORDERS_TIME_LIMIT
        to_delete = []
        for orderId, order in self.orders.items():
            status = order["status"]
            updateTime = order["updateTime"]
            if status != "NEW" and (updateTime < (current_time - self.OLD_ORDERS_TIME_LIMIT) or status == 'CANCELED'):
                to_delete.append(orderId)
        for oid in to_delete:
            self.orders.pop(oid)

    def _on_message(self, ws, raw_message: str) -> None:
        message = json.loads(raw_message)
        message_type = message['type']
        if message_type in {'subscribed', 'unsubscribed', 'pong'}:
            return
        elif message_type == 'info':
            if message['code'] == 20001:
                return self.reconnect()
        elif message_type == 'error':
            raise Exception(message)
        channel = message['channel']

        if channel == 'orderbook':
            self._handle_orderbook_message(message)
        elif channel == 'trades':
            self._handle_trades_message(message)
        elif channel == 'ticker':
            self._handle_ticker_message(message)
        elif channel == 'fills':
            self._handle_fills_message(message)
        elif channel == 'orders':
            self._handle_orders_message(message)

    def _candles_last_update_time_check(self):
        """
        checks that the ws has up to date data for candles (within _WS_CANDLES_TIMEOUT_LIMIT seconds).
        If not, then reset the subscription
        """
        if self._candles_last_update_time + self._WS_CANDLES_TIMEOUT_LIMIT < time.time():
            # self.logger.writeline(f"{self.symbol} WARNING: FTX WS candles not updated within timeout limit! Last update: {self._candles_last_update_time}")
            return False
        return True

    def get_candlesticks(self, limit):
        if check_if_candles_are_latest(self.candles):
            return self.candles[-limit:]
        else:
            self.logger.writeline(f"ERROR Websockets get_candlesticks: {self.symbol} candles not current!")
            # reset candles
            self._set_up_candles()
            raise Exception(f"{self.symbol} {get_current_datetime_string()} FTX WS get_candlesticks Unable to provide candlesticks!")

    def get_candlesticks_api_first(self, limit):
        # because FTX API candles are not latest, we return the stored ws candles
        return self.get_candlesticks(limit)

    def get_position(self):
        return self.position

    def get_position_api_first(self):
        """FTX WS does not have a position channel"""
        return self.client.futures_get_position(self.symbol)

    def get_wallet_balance_api_first(self):
        """FTX WS does not have an asset balance channel"""
        return self.client.futures_get_balance()

    def get_latest_price(self):
        if check_if_candles_are_latest(self.candles) and self._candles_last_update_time_check():
            return self.candles[-1][4]
        else:
            self.logger.writeline(f"ERROR Websockets get_latest_price: {self.symbol} candles not current!")
            self._set_up_candles()
            raise Exception(f"ERROR Websockets get_latest_price: {self.symbol} candles not current!")

    def get_latest_price_api_first(self):
        ticker = self.client.futures_symbol_ticker(self.symbol)
        if ticker:
            return ticker['price']
        else:
            latest_price = self.get_latest_price()
            if latest_price:
                self.logger.writeline(f"{self.symbol} Websockets provided latest_price {latest_price}")
            return latest_price

    def get_order(self, orderId):
        if orderId in self.orders:
            return self.orders[orderId]
        else:
            self.logger.writeline(f"ERROR get_order: {self.symbol} Websockets order {orderId} does not exist")
            return None

    def get_order_api_first(self, orderId):
        order = self.client.futures_get_order(self.symbol, orderId)
        if order:
            return order
        else:
            order = self.get_order(orderId)
            if order:
                self.logger.writeline(f"{self.symbol} Websockets provided order {order}")
                # remember to remove 'updateTime' as this is only used in websocket manager
                return order.pop('updateTime')
            else:
                self.logger.writeline(f"{self.symbol} FTX WS orders not up to date, resetting orders")
                self._set_up_orders()
                # TODO: be more proactive, instead of resetting when getting an order fails, constantly check status of
                #  the ws and reset when the status is down
                raise Exception(f"{self.symbol} get_order_api_first order not found!")

# wsm = FtxWebSocketManager("EOS-PERP", "1m", client=UniversalClient("FTX"), candles_limit=4)
