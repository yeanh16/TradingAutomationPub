from ..clients.UniversalClient import UniversalClient
from trading_automation.websockets.WebsocketInterface import WebsocketInterface
from trading_automation.websockets.BybitWebSocket import BybitWebSocket


class BybitWebSocketManager(WebsocketInterface):

    def __init__(self, symbol, interval, client: UniversalClient, candles_limit=50) -> None:
        super().__init__()
        self.public_ws = BybitWebSocket(symbol, interval, client, candles_limit, True)
        self.private_ws = BybitWebSocket(symbol, interval, client, candles_limit, False)
        self.position = self.private_ws.position

    def get_order_api_first(self, orderId):
        return self.private_ws.get_order_api_first(orderId)

    def get_candlesticks_api_first(self, limit):
        return self.public_ws.get_candlesticks_api_first(limit)

    def get_position_api_first(self):
        return self.private_ws.get_position_api_first()

    def get_wallet_balance_api_first(self):
        return self.private_ws.get_wallet_balance_api_first()

    def get_latest_price_api_first(self):
        return self.public_ws.get_latest_price_api_first()

