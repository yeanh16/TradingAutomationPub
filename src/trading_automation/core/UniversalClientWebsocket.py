from trading_automation.clients.UniversalClient import *
from trading_automation.clients.DiscordClient import DiscordNotificationService
from typing import Optional
from trading_automation.websockets.fwebsockets import WebSocketManager
from okex.okexWebSocketManager import OkexWebSocketManager
from trading_automation.websockets.FTXWebSocketManager import FtxWebSocketManager
from trading_automation.websockets.GateWebSocketManager import GateWebSocketManager
from trading_automation.websockets.MexcWebSocketManager import MexcWebSocketManager
from trading_automation.websockets.BybitWebSocketManager import BybitWebSocketManager
from trading_automation.websockets.IgWebSocketManager import IgWebSocketManager
from trading_automation.websockets.CapitalWebSocketManager import CapitalWebSocketManager
from trading_automation.websockets.PhemexWebSocketManager import PhemexWebSocketManager
from trading_automation.websockets.BingxWebSocketManager import BingxSocketManager


class UniversalClientWebsocket(UniversalClient):
    """
    A UniversalClient that also has a WS stream open of a particular symbol as a secondary source of data.
    Class to be used for all exchanges as a Client for REST API and WS methods combined.
    """

    def __init__(
        self,
        exchange,
        symbol,
        interval,
        candles_limit,
        discord_service: Optional[DiscordNotificationService] = None,
        phemex_input_q=None,
        phemex_output_q=None,
    ):
        super().__init__(exchange, discord_service=discord_service)
        if self.exchange == "BINANCE":
            self.ws = WebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "FTX" in self.exchange:
            self.ws = FtxWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "OKEX" in self.exchange:
            self.ws = OkexWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "GATE" in self.exchange:
            self.ws = GateWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "MEXC" in self.exchange:
            self.ws = MexcWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "BYBIT" in self.exchange:
            self.ws = BybitWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "IG" in self.exchange:
            self.ws = IgWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "CAPITAL" in self.exchange:
            self.ws = CapitalWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        elif "PHEMEX" in self.exchange:
            self.ws = PhemexWebSocketManager(symbol, interval, candles_limit=candles_limit, client=self, phemex_ws_input_q=phemex_input_q, phemex_ws_output_q=phemex_output_q)
        elif "BINGX" in self.exchange:
            self.ws = BingxSocketManager(symbol, interval, candles_limit=candles_limit, client=self)
        else:
            self.logger.writeline(f"ERROR no ws initiated self.exchange: {self.exchange}")
            raise Exception(f"ERROR no ws initiated self.exchange: {self.exchange}")
        self.symbol = symbol
        self.interval = interval
        self.candles_limit = candles_limit
        self.position = self.ws.position
        if "BYBIT" in self.exchange and get_position_size(self.position) == 0 and not self.futures_get_open_orders(symbol=self.symbol):
            # change leverage to always be max
            symbol_info = self.client_bybit.query_symbol(symbol=self.symbol)[0]
            max_leverage = symbol_info['leverageFilter']['maxLeverage']
            self.futures_change_leverage(symbol=symbol, leverage=max_leverage)
        elif "OKEX" in self.exchange and get_position_size(self.position) == 0 and not self.futures_get_open_orders(symbol=self.symbol):
            # change leverage on OKEX to always be 16
            self.futures_change_leverage(symbol=self.symbol, leverage=16)
        elif "PHEMEX" in self.exchange and get_position_size(self.position) == 0 and not self.futures_get_open_orders(symbol=self.symbol):
            self.futures_change_leverage(symbol=self.symbol, leverage=-0)  # -0 means max cross leverage (as opposed to isolated)
        elif "BINGX" in self.exchange and get_position_size(self.position) == 0 and not self.futures_get_open_orders(symbol=self.symbol):
            self.futures_change_leverage(symbol=self.symbol, leverage=20)
            self.client_bingx.switch_margin_mode(symbol, "Cross")
    # @UniversalClient.tries_wrapper
    # def futures_order_book(self, symbol, limit):
    #     # OKEX needs to use ws for orderbook as API is slow
    #     # 05/2022 UPDATE on above, orderbook no longer slow
    #     if "OKEX" in self.exchange:
    #         assert self.symbol == symbol
    #         orderbook = self.ws.get_orderbook(limit)
    #         if "USDT" in self.symbol:
    #             # since the quantity is given in 'sz', need to multiply this with the lot size to give quantity
    #             return {"asks": list(map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[self.symbol])],
    #                                      [[item for item in sub[:2]] for sub in orderbook['asks']])),
    #                     "bids": list(map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[self.symbol])],
    #                                      [[item for item in sub[:2]] for sub in orderbook['bids']]))}
    #         else:
    #             # quantity = sz * cont_size (or lot_size in USD) / price
    #             return {"asks": list(
    #                 map(lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[self.symbol] / Decimal(x[0]))],
    #                     [[item for item in sub[:2]] for sub in orderbook['asks']])),
    #                     "bids": list(map(
    #                         lambda x: [x[0], str(Decimal(x[1]) * self.precisionQuantityDict[self.symbol] / Decimal(x[0]))],
    #                         [[item for item in sub[:2]] for sub in orderbook['bids']]))}
    #     else:
    #         return super().futures_order_book(symbol, limit)
    #
    # @UniversalClient.tries_wrapper
    # def futures_orderbook_ticker(self, symbol):
    #     if "OKEX" in self.exchange:
    #         assert self.symbol == symbol
    #         orderbook = self.ws.get_orderbook(1)
    #         if 'USDT' in self.symbol:
    #             bidQty = str(Decimal(orderbook['bids'][0][1]) * self.precisionQuantityDict[self.symbol])
    #             askQty = str(Decimal(orderbook['asks'][0][1]) * self.precisionQuantityDict[self.symbol])
    #         else:
    #             bidQty = str(Decimal(orderbook['bids'][0][1]) * self.precisionQuantityDict[self.symbol] / Decimal(
    #                 orderbook['bids'][0][0]))
    #             askQty = str(Decimal(orderbook['asks'][0][1]) * self.precisionQuantityDict[self.symbol] / Decimal(
    #                 orderbook['asks'][0][0]))
    #         return {"symbol": self.symbol, "bidPrice": orderbook['bids'][0][0], "bidQty": bidQty,
    #                 "askPrice": orderbook['asks'][0][0], "askQty": askQty}
    #     else:
    #         return super().futures_orderbook_ticker(symbol)

    def get_order_api_first(self, orderId):
        return self.ws.get_order_api_first(orderId)

    def get_candlesticks_api_first(self, limit):
        return self.ws.get_candlesticks_api_first(limit)

    def get_position_api_first(self):
        return self.ws.get_position_api_first()

    def get_wallet_balance_api_first(self):
        return self.ws.get_wallet_balance_api_first()

    def get_latest_price_api_first(self):
        return self.ws.get_latest_price_api_first()
