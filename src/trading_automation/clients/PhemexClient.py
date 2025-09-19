import base64
import hmac
import hashlib
import json
import requests
import time
from math import trunc
import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables

load_dotenv(find_dotenv())


class PhemexAPIException(Exception):

    def __init__(self, response):
        self.code = 0
        try:
            json_res = response.json()
        except ValueError:
            self.message = 'Invalid error message: {}'.format(response.text)
        else:
            if 'code' in json_res:
                self.code = json_res['code']
                self.message = json_res['msg']
            else:
                self.code = json_res['error']['code']
                self.message = json_res['error']['message']
        self.status_code = response.status_code
        self.response = response
        self.request = getattr(response, 'request', None)
        self.headers = response.headers

    def __str__(self):  # pragma: no cover
        return 'HTTP(code=%s), API(errorcode=%s): %s \n headers %s' % (self.status_code, self.code, self.message, self.headers)


class PhemexClient(object):
    MAIN_NET_API_URL = 'https://api.phemex.com'
    TEST_NET_API_URL = 'https://testnet-api.phemex.com'
    MAIN_NET_API_URL_HIGH_RATE = 'https://vapi.phemex.com'

    CURRENCY_BTC = "BTC"
    CURRENCY_USD = "USD"

    SYMBOL_BTCUSD = "BTCUSD"
    SYMBOL_ETHUSD = "ETHUSD"
    SYMBOL_XRPUSD = "XRPUSD"

    SIDE_BUY = "Buy"
    SIDE_SELL = "Sell"

    ORDER_TYPE_MARKET = "Market"
    ORDER_TYPE_LIMIT = "Limit"

    TIF_IMMEDIATE_OR_CANCEL = "ImmediateOrCancel"
    TIF_GOOD_TILL_CANCEL = "GoodTillCancel"
    TIF_FOK = "FillOrKill"

    ORDER_STATUS_NEW = "New"
    ORDER_STATUS_PFILL = "PartiallyFilled"
    ORDER_STATUS_FILL = "Filled"
    ORDER_STATUS_CANCELED = "Canceled"
    ORDER_STATUS_REJECTED = "Rejected"
    ORDER_STATUS_TRIGGERED = "Triggered"
    ORDER_STATUS_UNTRIGGERED = "Untriggered"

    def __init__(self, api_key=None, api_secret=None, is_testnet=False, timeout=1, use_high_rate_endpoint=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_URL = self.MAIN_NET_API_URL
        if use_high_rate_endpoint:
            self.api_URL = self.MAIN_NET_API_URL_HIGH_RATE
        if is_testnet:
            self.api_URL = self.TEST_NET_API_URL
        self.timeout = timeout
        self.session = requests.session()

    def _send_request(self, method, endpoint, params={}, body={}):
        expiry = str(trunc(time.time()) + 60)
        query_string = '&'.join(['{}={}'.format(k, v) for k, v in params.items()])
        message = endpoint + query_string + expiry
        body_str = ""
        if body:
            body_str = json.dumps(body, separators=(',', ':'))
            message += body_str
        signature = hmac.new(self.api_secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
        self.session.headers.update({
            'x-phemex-request-signature': signature.hexdigest(),
            'x-phemex-request-expiry': expiry,
            'x-phemex-access-token': self.api_key,
            'Content-Type': 'application/json'})
        url = self.api_URL + endpoint
        if query_string:
            url += '?' + query_string
        response = self.session.request(method, url, data=body_str.encode(), timeout=self.timeout)
        if not str(response.status_code).startswith('2'):
            raise PhemexAPIException(response)
        try:
            res_json = response.json()
        except ValueError:
            raise PhemexAPIException('Invalid Response: %s' % response.text)
        if "code" in res_json and res_json["code"] != 0:
            raise PhemexAPIException(response)
        if "error" in res_json and res_json["error"]:
            raise PhemexAPIException(response)

        if 'data' in res_json:
            return res_json['data']
        else:
            return res_json['result']

    def query_product_information(self):
        return self._send_request("GET", "/public/products")

    def query_kline(self, symbol, resolution, limit=5, from_time="", to_time=""):
        """
        Valid resolutions: 60, 300, 900, 1800, 3600, 14400, 86400,
        Valid limits: 5, 10, 50, 100, 500, 1000
        times are in seconds
        from_time inclusive, to_time exclusive
        Doesn't seem to get the most latest incomplete candle
        """
        if from_time == "":
            if limit > 1000:
                limit = 1000
            if limit not in [5, 10, 50, 100, 500, 1000]:
                for valid_limit in [5, 10, 50, 100, 500, 1000]:
                    if valid_limit > limit:
                        limit = valid_limit
                        break
            return self._send_request("GET", "/exchange/public/md/v2/kline", params={"symbol": symbol, "resolution": resolution, "limit": limit})
        else:
            if to_time == "":
                to_time = from_time + (1000*resolution)
            return self._send_request("GET", "/exchange/public/md/kline",
                                      params={"symbol": symbol, "resolution": resolution, "from": from_time, "to": to_time})

    def query_account_n_positions(self, currency: str):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#querytradeaccount
        """
        return self._send_request("get", "/accounts/accountPositions", {'currency': currency})

    def place_order(self, params={}):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#placeorder
        """
        return self._send_request("post", "/orders", body=params)

    def amend_order(self, symbol, orderID, params={}):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#622-amend-order-by-orderid
        """
        params["symbol"] = symbol
        params["orderID"] = orderID
        return self._send_request("put", "/orders/replace", params=params)

    def cancel_order(self, symbol, orderID=None, clOrderID=None):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#623-cancel-single-order
        """
        if orderID:
            return self._send_request("delete", "/orders/cancel", params={"symbol": symbol, "orderID": orderID})
        elif clOrderID:
            return self._send_request("delete", "/orders/cancel", params={"symbol": symbol, "clOrdID": clOrderID})
        raise Exception("cancel_order needs orderID or clOrderID")

    def _cancel_all(self, symbol, untriggered_order=False):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#625-cancel-all-orders
        """
        return self._send_request("delete", "/orders/all",
                                  params={"symbol": symbol, "untriggered": str(untriggered_order).lower()})

    def cancel_all_normal_orders(self, symbol):
        self._cancel_all(symbol, untriggered_order=False)

    def cancel_all_untriggered_conditional_orders(self, symbol):
        self._cancel_all(symbol, untriggered_order=True)

    def cancel_all(self, symbol):
        self._cancel_all(symbol, untriggered_order=False)
        self._cancel_all(symbol, untriggered_order=True)

    def change_leverage(self, symbol, leverage=0):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#627-change-leverage
        """
        return self._send_request("PUT", "/positions/leverage", params={"symbol": symbol, "leverage": leverage})

    def change_risklimit(self, symbol, risk_limit=0):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#628-change-position-risklimit
        """
        return self._send_request("PUT", "/positions/riskLimit", params={"symbol": symbol, "riskLimit": risk_limit})

    def query_open_orders(self, symbol):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#6210-query-open-orders-by-symbol
        """
        try:
            return self._send_request("GET", "/orders/activeList", params={"symbol": symbol})
        except PhemexAPIException as e:
            if e.code == 10002:  # "OM_ORDER_NOT_FOUND"
                return {'rows': []}
            else:
                raise e

    def query_order(self, symbol, orderId=None, cliOrderId=None):
        if orderId:
            return self._send_request("GET", "/exchange/order", params={"symbol": symbol, "orderID": orderId})
        elif cliOrderId:
            return self._send_request("GET", "/exchange/order", params={"symbol": symbol, "clOrdID": cliOrderId})
        raise Exception("query order needs orderID or cliOrderId")

    def query_24h_ticker(self, symbol):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#633-query-24-hours-ticker
        """
        return self._send_request("GET", "/md/ticker/24hr", params={"symbol": symbol})

    def query_client_and_wallets(self):
        return self._send_request("GET", "/phemex-user/users/children", params={})

    def query_orderbook(self, symbol):
        return self._send_request("GET", "/md/orderbook", params={'symbol': symbol})


if __name__ == "__main__":
    # Load API credentials from environment variables
    phemex_api_id = os.environ.get("PHEMEX_API_ID")
    phemex_api_secret = os.environ.get("PHEMEX_API_SECRET")
    
    if not phemex_api_id or not phemex_api_secret:
        print("Error: PHEMEX_API_ID and PHEMEX_API_SECRET environment variables must be set")
        exit(1)
    
    pc = PhemexClient(api_key=phemex_api_id, api_secret=phemex_api_secret)
