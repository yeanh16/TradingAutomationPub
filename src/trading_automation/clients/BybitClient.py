from datetime import datetime, timedelta
from typing import Any
from pybit.unified_trading import HTTP
from pybit.exceptions import InvalidRequestError
from trading_automation.core.Utils import binance_intervals_to_seconds


class BybitClient:
    API_URL = "https://api.bybit.com"

    def __init__(self, api_key, api_secret, timeout=0.3, base_url=API_URL) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._api_secret = api_secret
        self._timeout = timeout
        self._session = HTTP(api_key=self._api_key, api_secret=self._api_secret, max_retries=1, retry_delay=0)

    def _process_result(self, result: dict) -> Any:
        if not result:
            raise Exception("Bybit unable to get a result from API")
        else:
            if not result['retCode'] == 0:
                raise InvalidRequestError(
                    request=f'',
                    message=result["retMsg"],
                    status_code=result["retCode"],
                    time=datetime.utcnow().strftime("%H:%M:%S")
                )
            if 'list' in result['result']:
                # print(result['result']['list'])
                return result['result']['list']
            # print(result['result'])
            return result['result']

    def _process_result_wrapper(func):
        def wrapped(self, *args, **kwargs):
            return self._process_result(func(self, *args, **kwargs))
        return wrapped

    @_process_result_wrapper
    def query_kline(self, symbol, interval, start_time=None, limit=1000):
        if limit > 1000:
            # print(f"WARNING: BYBIT API query kline for {limit} > 1000 candles at once! Reducing to 1000 candles")
            limit = 1000
        return self._session.get_kline(symbol=symbol, interval=interval, limit=limit, start=start_time)

    @_process_result_wrapper
    def query_symbol(self, symbol=None):
        return self._session.get_instruments_info(category='linear', symbol=symbol)

    @_process_result_wrapper
    def latest_information_for_symbol(self, symbol):
        return self._session.get_tickers(category='linear', symbol=symbol)

    @_process_result_wrapper
    def my_position(self, symbol=None):
        settle_coin = None
        if symbol is None:
            settle_coin = 'USDT'
        return self._session.get_positions(category='linear', symbol=symbol, settleCoin=settle_coin)

    @_process_result_wrapper
    def get_wallet_balance(self, coin=None):
        return self._session.get_wallet_balance(accountType='UNIFIED', coin=coin)

    @_process_result_wrapper
    def place_order(self, side, symbol, order_type, qty, time_in_force, close_on_trigger, reduce_only, price="", order_link_id=""):
        if order_type == "MARKET":
            price = ""
            order_type = "Market"
        elif order_type == "LIMIT" and price != "":
            order_type = "Limit"
        elif price == "":
            raise Exception("Price required to place limit order!")
        if side == "BUY":
            side = "Buy"
        elif side == "SELL":
            side = "Sell"
        return self._session.place_order(category='linear', side=side, symbol=symbol, orderType=order_type, qty=str(qty), timeInForce=time_in_force, closeOnTrigger=close_on_trigger, reduceOnly=reduce_only, price=str(price), orderLinkId=order_link_id, positionIdx=0)

    @_process_result_wrapper
    def query_active_order(self, symbol, order_id="", order_link_id=""):
        return self._session.get_open_orders(category='linear', symbol=symbol, orderId=order_id, orderLinkId=order_link_id)

    @_process_result_wrapper
    def cancel_active_order(self, symbol, order_id="", order_link_id=""):
        return self._session.cancel_order(category='linear', symbol=symbol, orderId=order_id, orderLinkId=order_link_id)

    @_process_result_wrapper
    def cancel_all_active_orders(self, symbol):
        return self._session.cancel_all_orders(category='linear', symbol=symbol)

    @_process_result_wrapper
    def orderbook(self, symbol, limit=None):
        return self._session.get_orderbook(category='linear', symbol=symbol, limit=limit)

    @_process_result_wrapper
    def set_leverage(self, symbol, leverage):
        try:
            return self._session.set_leverage(category='linear', symbol=symbol, buyLeverage=str(leverage), sellLeverage=str(leverage))
        except InvalidRequestError as e:
            if e.status_code == 110043:
                return {
                        "retCode": 0,
                        "retMsg": "OK",
                        "result": {}
                        }
            else:
                raise e

    @_process_result_wrapper
    def position_mode_switch(self, symbol, mode):
        return self._session.switch_position_mode(category='linear', symbol=symbol, mode=mode)

