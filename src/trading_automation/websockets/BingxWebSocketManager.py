import json
from trading_automation.core.Utils import *
from .FTXWebSocket import Websocket
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
from ..clients.UniversalClient import UniversalClient


class BingxSocketManager(Websocket, WebsocketInterface):
    _ENDPOINT = 'wss://open-ws-swap.bingbon.pro/ws/'

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50) -> None:
        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.client = client
        self.candles_limit = candles_limit
        self.position = self.client.futures_get_position(symbol)
        # TODO: finish implementing BINGX WS candles, seems to stall when subbing, maybe something to do with their compression?
        # self._set_up_candles()

    def _set_up_candles(self, resub_only=True):
        self._unsubscribe(f'market.kline.{self.symbol}.{binance_intervals_to_bitrue_intervals(self.interval)}')
        self._subscribe(f'market.kline.{self.symbol}.{binance_intervals_to_bitrue_intervals(self.interval)}')

    def _set_up_orders(self):
        pass

    def _get_url(self) -> str:
        return self._ENDPOINT

    def _on_message(self, ws, raw_message):
        message = json.loads(raw_message)
        print(message)

    def _subscribe(self, subscription):
        self.send_json({"id": f"{self.symbol}{subscription}", "reqType": "sub", "dataType": subscription})

    def _unsubscribe(self, subscription):
        self.send_json({"id": f"{self.symbol}{subscription}", "reqType": "unsub", "dataType": subscription})

    def get_order_api_first(self, orderId):
        # BINGX WS only provides public info
        return self.client.futures_get_order(symbol=self.symbol, orderId=orderId)

    def get_candlesticks_api_first(self, limit):
        return self.client.futures_get_candlesticks(symbol=self.symbol, limit=limit, interval=self.interval)

    def get_position_api_first(self):
        # BINGX WS only provides public info
        return self.client.futures_get_position(symbol=self.symbol)

    def get_wallet_balance_api_first(self):
        # BINGX WS only provides public info
        return self.client.futures_get_balance()

    def get_latest_price_api_first(self):
        return self.client.futures_get_symbol_price(self.symbol)


if __name__ == "__main__":
    wsm = BingxSocketManager("BTC-USDT", "1m", client=UniversalClient("BINGX"), candles_limit=4)
