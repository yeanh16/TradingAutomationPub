# from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from ..clients.UniversalClient import *
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
import re

DONT_USE_BINANCE_WS_FLAG = True


def parse_position_data(data):
    """
    parse position data from websocket to match API return signature. Assumes One-Way mode
    :param data:
    :return:
    """
    position = {"entryPrice": data["ep"],
                "marginType": data["mt"],
                # "isAutoAddMargin": False,
                # "isolatedMargin": "0",
                # "leverage": "2",
                # "liquidationPrice": "0",
                # "markPrice": "6679.50671178",
                # "maxNotionalValue": "20000000",
                "positionAmt": data["pa"],
                "symbol": data["s"],
                "unRealizedProfit": data["up"],
                "positionSide": data["ps"]
                }
    return [position]


def klines_dict_to_array(data):
    kline = data["k"]
    open_time = kline["t"]
    open = kline["o"]
    high = kline["h"]
    low = kline["l"]
    close = kline["c"]
    volume = kline["v"]
    close_time = kline["T"]
    quote_asset_volume = kline["q"]
    number_of_trades = kline["n"]
    taker_buy_base_asset_volume = kline["V"]
    taker_buy_quote_asset_volume = kline["Q"]
    return [open_time, open, high, low, close, volume, close_time, quote_asset_volume, number_of_trades,
            taker_buy_base_asset_volume, taker_buy_quote_asset_volume]


def ceil_dt(delta, dt=None):
    if not dt:
        dt = datetime.now()
    return (dt + (datetime.min - dt) % timedelta(minutes=delta)).timestamp() * 1000


def floor_dt(delta, dt=None):
    if not dt:
        dt = datetime.now()
    rounded = dt - (dt - datetime.min) % timedelta(minutes=delta)
    return rounded.timestamp() * 1000


class WebSocketManager(WebsocketInterface):
    """
    Websocket manager for Binance
    """
    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50):
        self.symbol = symbol
        self.interval = interval
        self.client = client
        self.logger = self.client.logger
        # below four variables are used to help handle kline streams for non supported intervals from websockets
        self.upper_interval_time = None
        self.lower_interval_time = None
        self.temp_candle = None
        self.temp_candle_needs_update = True
        self.update_interval_times(re.search("\\d*", self.interval)[0])
        # ----
        self.KLINES_LIMIT = candles_limit
        self.OLD_ORDERS_TIME_LIMIT = 300000  # time limit in milliseconds 300000 = 5 minute
        self.candles = self.client.futures_get_candlesticks(symbol=self.symbol, interval=self.interval, limit=self.KLINES_LIMIT)
        self.wallet_balance = 0
        self.multiMarginAssets = self.client.futures_get_multi_margin_assets()
        self.assetBalance = {}  # balances of the above multiMarginAssets that are used for collateral
        for asset in self.multiMarginAssets:
            balance = Decimal(self.client.futures_get_asset_balance(asset))
            self.assetBalance[asset] = balance
            self.wallet_balance += balance
        self.position = self.client.futures_get_position(self.symbol)
        self.orders = {}
        open_orders = self.client.futures_get_open_orders(self.symbol)
        if open_orders:
            for order in open_orders:
                self.orders[order['orderId']] = order
        # create instances of BinanceWebSocketApiManager
        self.binance_com_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com-futures",
                                                                            throw_exception_if_unrepairable=True)

        # create the userData streams
        self.binance_com_user_data_stream_id = self.binance_com_websocket_api_manager.create_stream('arr', '!userData',
                                                                                                    api_key=BINANCE_API_KEY,
                                                                                                    api_secret=BINANCE_API_SECRET,
                                                                                                    output="dict")
        if self.interval == "2m":  # special case for 2m intervals, as there is no data stream for 2m, we get 1m ones and convert manually
            self.binance_com_klines_data_stream_id = self.binance_com_websocket_api_manager.create_stream(
             [f'kline_1m'],
             [self.symbol], output="dict")
        else:
            self.binance_com_klines_data_stream_id = self.binance_com_websocket_api_manager.create_stream(
             [f'kline_{self.interval}'],
             [self.symbol], output="dict")

    # start a worker process to move the received stream_data from the stream_buffer to a print function
        worker_thread = threading.Thread(target=self.handle_stream)
        worker_thread.start()

    # # monitor the streams
    # while True:
    #     binance_com_websocket_api_manager.print_summary()
    #     time.sleep(5)

    def update_interval_times(self, delta):
        if delta:
            self.upper_interval_time = ceil_dt(int(delta)) - 1
            self.lower_interval_time = floor_dt(int(delta))
            # print(f"upper {self.upper_interval_time}")
            # print(f"lower {self.lower_interval_time}")

    def add_new_candle(self, candle):
        if len(self.candles) == 0:
            self.candles.append(candle)
            return

        # TODO: finish and test 2m intervals for websockets
        if self.interval == "2m":
            # if the start time of candle is same as the closest 2 minutes (floored) then we update as usual
            if candle[0] == self.lower_interval_time:
                candle[6] = self.upper_interval_time
                candle = candle[:-4]
            elif candle[0] > self.upper_interval_time:
                self.update_interval_times(2)
                self.temp_candle_needs_update = True
                candle[6] = self.upper_interval_time
                candle = candle[:-4]
            elif candle[0] < self.upper_interval_time:  # instead of adding a new candle, we update the most latest one otherwise
                if self.temp_candle_needs_update:
                    self.temp_candle = self.candles[-1]
                    self.temp_candle_needs_update = False
                candle = add_candles([self.temp_candle] + [candle])

        # if close_time of candle is the same as the last entry in self.candles - update, else append new candle
        if self.candles[-1][6] == candle[6]:
            self.candles.pop()
        self.candles.append(candle)

        if len(self.candles) > self.KLINES_LIMIT:
            self.candles = self.candles[1:]

        # if len(self.candles) > 1:
        #     api_candles = futures_get_candlesticks(symbol=self.symbol, limit=len(self.candles), interval=self.interval)[:-1]
        #     for candle in api_candles:
        #         candle.pop()  # pop last element which is 'ignore'
        #     assert api_candles == self.candles[:-1]

    def update_order_list(self, data):
        if data["s"] != self.symbol:
            return

        # parse data
        order = {"avgPrice": data["ap"],
                 "clientOrderId": data["c"],
                 # "cumQuote": "0",
                 "executedQty": data["z"],
                 "orderId": data["i"],
                 "origQty": data["q"],
                 "origType": data["ot"],
                 "price": data["p"],
                 "reduceOnly": data["R"],
                 "side": data["S"],
                 "positionSide": data["ps"],
                 "status": data["X"],
                 "stopPrice": data["sp"],
                 "closePosition": data["cp"],
                 "symbol": data["s"],
                 "time": data["T"],
                 "timeInForce": data["f"],
                 "type": data["o"],
                 # "priceRate": "0.3",
                 "updateTime": int(time.time() * 1000),
                 "workingType": data["wt"],
                 # "priceProtect": False
                 }
        if "AP" in data:
            order["activatePrice"] = data["AP"]

        self.orders[data["i"]] = order

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

    def handle_stream(self):
        while True:
            if self.binance_com_websocket_api_manager.is_manager_stopping():
                exit(0)
            oldest_stream_data_from_stream_buffer = self.binance_com_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer is False:
                time.sleep(0.01)
            else:
                # current_data = json.loads(oldest_stream_data_from_stream_buffer)
                current_data = oldest_stream_data_from_stream_buffer
                if "stream" in current_data:
                    candle = klines_dict_to_array(current_data["data"])
                    self.add_new_candle(candle)
                    continue
                # self.logger.writeline(oldest_stream_data_from_stream_buffer)
                # print(oldest_stream_data_from_stream_buffer)
                if "e" in current_data:
                    if current_data["e"] == "ACCOUNT_UPDATE":
                        data = current_data["a"]
                        if "B" in data:  # Balances
                            # update balances
                            balances = data["B"]
                            for balance in balances:
                                if balance["a"] in self.multiMarginAssets:
                                    self.assetBalance[balance["a"]] = Decimal(balance['wb'])
                            self.wallet_balance = sum(self.assetBalance.values())

                        if "P" in data and data["m"] == "ORDER":  # Position
                            position_data = data["P"][0]
                            if position_data["s"] == self.symbol:
                                position = parse_position_data(position_data)
                                self.position = position

                    elif current_data["e"] == "ORDER_TRADE_UPDATE":
                        order = current_data["o"]
                        self.update_order_list(order)

    def check_user_data_stream_status(self):
        account_stream_info = self.binance_com_websocket_api_manager.get_stream_info(
            self.binance_com_user_data_stream_id)
        if account_stream_info['status'] == 'running':
            return True
        else:
            self.logger.writeline(
                f"ERROR check_user_data_stream_status: {self.symbol} Websockets user data stream status: {account_stream_info['status']}")
            return False

    def get_order(self, orderId):
        if self.check_user_data_stream_status():
            if orderId in self.orders:
                return self.orders[orderId]
            else:
                self.logger.writeline(f"ERROR get_order: {self.symbol} Websockets order {orderId} does not exist")
                return None
        self.logger.writeline(f"ERROR: {self.symbol} Websockets could not get order")
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

    def get_candlesticks(self, limit):
        if check_if_candles_are_latest(self.candles):
            return self.candles[-limit:]
        else:
            self.logger.writeline(f"ERROR Binance Websockets get_candlesticks: {self.symbol} candles not current!")
            return None

    def get_candlesticks_api_first(self, limit):
        candlesticks = self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)
        if candlesticks and check_if_candles_are_latest(candlesticks):
            return candlesticks
        else:
            candlesticks = self.get_candlesticks(limit)
            if candlesticks:
                self.logger.writeline(f"{self.symbol} Websockets provided candlesticks")
            return candlesticks

    def get_position(self):
        if self.check_user_data_stream_status():
            return self.position
        self.logger.writeline(f"ERROR: {self.symbol} Websockets could not get position")
        return None

    def get_position_api_first(self):
        position = self.client.futures_get_position(self.symbol)
        if position:
            return position
        else:
            position = self.get_position()
            if position:
                self.logger.writeline(f"{self.symbol} Websockets provided position {position}")
            return position

    def get_wallet_balance(self):
        if self.check_user_data_stream_status():
            return self.wallet_balance
        self.logger.writeline(f"ERROR: {self.symbol} Websockets could not get balance")
        return None

    def get_wallet_balance_api_first(self):
        wallet_balance = self.client.futures_get_balance()
        if wallet_balance:
            return wallet_balance
        else:
            wallet_balance = self.get_wallet_balance()
            if wallet_balance:
                self.logger.writeline(f"{self.symbol} Websockets provided wallet_balance {wallet_balance}")
            return wallet_balance

    def get_latest_price(self):
        if check_if_candles_are_latest(self.candles):
            return self.candles[-1][4]
        else:
            self.logger.writeline(f"ERROR Websockets get_latest_price: {self.symbol} candles not current!")
            return None

    def get_latest_price_api_first(self):
        latest_price = self.client.futures_get_symbol_price(self.symbol)
        if latest_price:
            return latest_price
        else:
            latest_price = self.get_latest_price()
            if latest_price:
                self.logger.writeline(f"{self.symbol} Websockets provided latest_price {latest_price}")
            return latest_price
