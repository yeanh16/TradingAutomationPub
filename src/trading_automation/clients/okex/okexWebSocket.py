from trading_automation.websockets.WebsocketInterface import WebsocketInterface
from trading_automation.clients.UniversalClient import UniversalClient, OKEX_USE_DEMO, OKEX_PASSPHRASE, OKEX_API_KEY, OKEX_API_SECRET, OKEX_PASSPHRASE_SECOND, OKEX_API_KEY_SECOND, OKEX_API_SECRET_SECOND, OKEX_API_KEY_DEMO, OKEX_API_SECRET_DEMO, OKEX_PASSPHRASE_DEMO
from trading_automation.websockets.FTXWebSocket import Websocket
import time
import hmac
import json
import base64
from typing import Dict, List
import threading
from trading_automation.core.Utils import check_if_candles_are_latest, get_current_datetime_string, binance_intervals_to_seconds
import zlib


def update_bids(res, bids_p):
    bids_u = res['data'][0]['bids']
    for i in bids_u:
        bid_price = i[0]
        for j in bids_p:
            if bid_price == j[0]:
                if i[1] == '0':
                    bids_p.remove(j)
                    break
                else:
                    del j[1]
                    j.insert(1, i[1])
                    break
        else:
            if i[1] != "0":
                bids_p.append(i)
    else:
        bids_p.sort(key=lambda price: sort_num(price[0]), reverse=True)
    return bids_p


def update_asks(res, asks_p):
    asks_u = res['data'][0]['asks']
    for i in asks_u:
        ask_price = i[0]
        for j in asks_p:
            if ask_price == j[0]:
                if i[1] == '0':
                    asks_p.remove(j)
                    break
                else:
                    del j[1]
                    j.insert(1, i[1])
                    break
        else:
            if i[1] != "0":
                asks_p.append(i)
    else:
        asks_p.sort(key=lambda price: sort_num(price[0]))
    return asks_p


def sort_num(n):
    if n.isdigit():
        return int(n)
    else:
        return float(n)


def check(bids, asks):
    bids_l = []
    bid_l = []
    count_bid = 1
    while count_bid <= 25:
        if count_bid > len(bids):
            break
        bids_l.append(bids[count_bid - 1])
        count_bid += 1
    for j in bids_l:
        str_bid = ':'.join(j[0: 2])
        bid_l.append(str_bid)
    asks_l = []
    ask_l = []
    count_ask = 1
    while count_ask <= 25:
        if count_ask > len(asks):
            break
        asks_l.append(asks[count_ask - 1])
        count_ask += 1
    for k in asks_l:
        str_ask = ':'.join(k[0: 2])
        ask_l.append(str_ask)
    num = ''
    if len(bid_l) == len(ask_l):
        for m in range(len(bid_l)):
            num += bid_l[m] + ':' + ask_l[m] + ':'
    elif len(bid_l) > len(ask_l):
        for n in range(len(ask_l)):
            num += bid_l[n] + ':' + ask_l[n] + ':'
        for l in range(len(ask_l), len(bid_l)):
            num += bid_l[l] + ':'
    elif len(bid_l) < len(ask_l):
        for n in range(len(bid_l)):
            num += bid_l[n] + ':' + ask_l[n] + ':'
        for l in range(len(bid_l), len(ask_l)):
            num += ask_l[l] + ':'

    new_num = num[:-1]
    int_checksum = zlib.crc32(new_num.encode())
    fina = change(int_checksum)
    return fina


def change(num_old):
    num = pow(2, 31) - 1
    if num_old > num:
        out = num_old - num * 2 - 2
    else:
        out = num_old
    return out


class OkexWebSocket(Websocket, WebsocketInterface):
    _ENDPOINT_PUBLIC = "wss://ws.okx.com:8443/ws/v5/public"
    _ENDPOINT_PRIVATE = "wss://ws.okx.com:8443/ws/v5/private"
    _ENDPOINT_PUBLIC_DEMO = "wss://ws.okx.com:8443/ws/v5/public?brokerId=9999"
    _ENDPOINT_PRIVATE_DEMO = "wss://ws.okx.com:8443/ws/v5/private?brokerId=9999"
    _WS_CANDLES_TIMEOUT_LIMIT = 2  # in seconds, if the candles are not updated within this time - reset

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit, public: bool):
        """
        :param public: Whether this websocket will connect to OKEX public websocket url. Will connect to private if False
        """
        super().__init__()
        self.client = client
        self.symbol = symbol
        self.interval = interval
        self.KLINES_LIMIT = candles_limit
        self.OLD_ORDERS_TIME_LIMIT = 300000  # time limit in milliseconds
        self.logger = self.client.logger
        self.position = self.get_position_api_first()
        if OKEX_USE_DEMO:
            self.api_key = OKEX_API_KEY_DEMO
            self.api_secret = OKEX_API_SECRET_DEMO
            self.api_pass = OKEX_PASSPHRASE_DEMO
            if public:
                self.url = self._ENDPOINT_PUBLIC_DEMO
            else:
                self.url = self._ENDPOINT_PRIVATE_DEMO
        else:
            if "LowStakes" in self.client.exchange:
                self.api_key = OKEX_API_KEY_SECOND
                self.api_secret = OKEX_API_SECRET_SECOND
                self.api_pass = OKEX_PASSPHRASE_SECOND
            else:
                self.api_key = OKEX_API_KEY
                self.api_secret = OKEX_API_SECRET
                self.api_pass = OKEX_PASSPHRASE
            if public:
                self.url = self._ENDPOINT_PUBLIC
            else:
                self.url = self._ENDPOINT_PRIVATE
        self._logged_in = False
        self._subscriptions: List[Dict] = []
        if not public:
            self._login()
            self.orders = {}
            open_orders = self.client.futures_get_open_orders(self.symbol)
            if open_orders:
                for order in open_orders:
                    order['updateTime'] = int(time.time() * 1000)
                    self.orders[order['orderId']] = order
            self._subscribe({'channel': 'orders', 'instType': 'SWAP', 'instId': self.symbol})
            self.wallet_balance = self.client.futures_get_balance()
            self._subscribe({'channel': 'balance_and_position'})
            self._subscribe({'channel': 'positions', 'instType': 'SWAP', 'instId': self.symbol})
        else:
            # self._set_up_orderbooks()
            # threading.Thread(target=self._orderbook_check_alive, daemon=True).start()
            self.candles = []
            self.set_up_candlesticks(resub_only=False)
        # need a thread to constantly ping server to stay alive
        threading.Thread(target=self._keep_alive, daemon=True).start()
        self.latest_message = None

    def _keep_alive(self):
        while True:
            self.send("ping")
            time.sleep(25)

    def _orderbook_check_alive(self):
        while True:
            if self._last_orderbook_update_time + 10000 < int(time.time()) * 1000:
                self.logger.writeline(f"{self.symbol} WARNING: OKEX WS orderbook not updated for 10 seconds!")
                self._set_up_orderbooks()
            time.sleep(10)

    def _set_up_orderbooks(self):
        self.asks = []
        self.bids = []
        self._unsubscribe({'channel': 'books', 'instId': self.symbol})
        self._subscribe({'channel': 'books', 'instId': self.symbol})
        self._last_orderbook_update_time = int(time.time()) * 1000

    def _check_candle_subscription_channel(self):
        while True:
            if self._last_candle_update_time + self._WS_CANDLES_TIMEOUT_LIMIT < time.time():
                self.logger.writeline(f"{self.symbol} WARNING: OKEX WS candles not updated within timeout limit! Last update: {self._last_candle_update_time}")
                self.set_up_candlesticks()
            time.sleep(self._WS_CANDLES_TIMEOUT_LIMIT)

    def _login(self):
        timestamp = str(int(time.time()))
        message = timestamp + 'GET' + '/users/self/verify'
        mac = hmac.new(bytes(self.api_secret, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
        d = mac.digest()
        sign = base64.b64encode(d)

        login_param = {"op": "login", "args": [{"apiKey": self.api_key,
                                                "passphrase": self.api_pass,
                                                "timestamp": timestamp,
                                                "sign": sign.decode("utf-8")}]}
        self.send_json(login_param)
        self._logged_in = True

    def _subscribe(self, subscription: Dict) -> None:
        self.send_json({'op': 'subscribe', 'args': [subscription]})
        self._subscriptions.append(subscription)

    def _unsubscribe(self, subscription: Dict) -> None:
        self.send_json({'op': 'unsubscribe', 'args': [subscription]})
        while subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def _get_url(self):
        return self.url

    def set_up_candlesticks(self, resub_only=True):
        if not resub_only:
            self.candles = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval, limit=self.KLINES_LIMIT)
        subscription = {'channel': 'candle'+self.interval, 'instId': self.symbol}
        self._unsubscribe(subscription)
        self._subscribe(subscription)

    def _handle_candlesticks_message(self, candle):
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
                self.logger.writeline(f"{self.symbol} WARNING: OKEX WS new candle does not fit. Current candles: {self.candles}. New candle {candle}. Getting candles from API...")
                self.set_up_candlesticks(resub_only=False)
                return

        # if len(self.candles) > self.KLINES_LIMIT:
        #     self.candles = self.candles[1:]
        self._last_candle_update_time = int(time.time())

    def _handle_position_message(self, message):
        position = self.client.process_okex_position_to_binance_position(message, self.symbol)
        self.position = position

    def _handle_balance_and_position_message(self, message):
        balances = message['balData']
        for balance in balances:
            if balance['ccy'] == 'USDT':
                self.wallet_balance = balance['cashBal']

    def _handle_orders_message(self, message):
        order = self.client.process_okex_order_to_binance(message)
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

    def _handle_orderbook_message(self, message):
        if message['action'] == 'snapshot':
            self.bids = message['data'][0]['bids']
            self.asks = message['data'][0]['asks']
            # checksum
            checksum = message['data'][0]['checksum']
            check_num = check(self.bids, self.asks)
            if check_num != checksum:
                self.logger.writeline(f"{self.symbol} OKEX orderbook WS Checksum Failed")
                self._set_up_orderbooks()
        elif message['action'] == 'update':
            self.bids = update_bids(message, self.bids)
            self.asks = update_asks(message, self.asks)
            checksum = message['data'][0]['checksum']
            check_num = check(self.bids, self.asks)
            if check_num != checksum:
                self.logger.writeline(f"{self.symbol} OKEX orderbook WS Checksum Failed")
                self._set_up_orderbooks()
        self._last_orderbook_update_time = int(message['data'][0]['ts'])

    def _on_message(self, ws, raw_message):
        if raw_message == "pong":
            return
        # print(raw_message)
        self.latest_message = raw_message
        message = json.loads(raw_message)
        if 'event' in message:
            message_type = message['event']
            if message_type in {'subscribed', 'unsubscribed', 'subscribe', 'unsubscribe'}:
                return
            elif message_type == 'error':
                raise Exception(message)

        channel = None
        if 'arg' in message:
            channel = message['arg']['channel']

        if channel and 'candle' in channel:
            # print(f"{get_current_datetime_string()} {message['data'][0]}")
            self._handle_candlesticks_message(message['data'][0])
        elif 'positions' == channel:
            if len(message['data']) > 0:
                self._handle_position_message(message['data'][0])
            else:
                self._handle_position_message([])
        elif 'balance_and_position' == channel:
            self._handle_balance_and_position_message(message['data'][0])
        elif 'orders' == channel:
            self._handle_orders_message(message['data'][0])
        elif channel and 'books' in channel:
            self._handle_orderbook_message(message)

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
                raise Exception(f"{self.symbol} {get_current_datetime_string()} OKEX WS get_candlesticks Unable to provide candlesticks!")

    def get_candlesticks_api_first(self, limit):
        # REST API candles may be out of date so return WS candles instead
        return self.get_candlesticks(limit)

    def get_position(self):
        return self.position

    def get_position_api_first(self):
        try:
            position = self.client.futures_get_position(self.symbol)
            return position
        except ConnectionError:
            self.logger.writeline(f"{self.symbol} OKEX Websockets provided position {self.position}")
            return self.position

    def get_wallet_balance_api_first(self):
        try:
            balance = self.client.futures_get_balance()
            return balance
        except ConnectionError:
            self.logger.writeline(f"{self.symbol} Websockets provided wallet_balance {self.wallet_balance}")
            return self.wallet_balance

    def get_latest_price_api_first(self):
        try:
            price = self.client.futures_get_symbol_price(self.symbol)
            return price
        except ConnectionError:
            last_candle = self.get_candlesticks(1)
            latest_price = last_candle[4]
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
                return order
        raise Exception(f"{self.symbol} ERROR: Websockets and API not able to provide order")

    def get_orderbook(self, limit):
        try:
            return {'asks': self.asks[:limit], 'bids': self.bids[:limit]}
        except Exception as e:
            self.logger.writeline(f"ERROR: {self.symbol} Websockets cannot provide orderbook")
            self._set_up_orderbooks()
            return self.client.futures_get_order_book(symbol=self.symbol, limit=limit)

# wsm = OkexWebSocket("EOS-USDT-SWAP", "1m", client=UniversalClient("OKEX"), candles_limit=4, public=True)
