import base64
import hmac
import requests
import time
import urllib.request


class BingxAPIException(Exception):

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
        return 'HTTP(code=%s), API(errorcode=%s): %s' % (self.status_code, self.code, self.message)


class BingxClient(object):
    MAIN_NET_API_URL = 'https://api-swap-rest.bingbon.pro'

    def __init__(self, api_key=None, api_secret=None, timeout=1):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_URL = self.MAIN_NET_API_URL
        self.timeout = timeout
        self.session = requests.session()

    def genSignature(self, path, method, paramsMap):
        sortedKeys = sorted(paramsMap)
        paramsStr = "&".join(["%s=%s" % (x, paramsMap[x]) for x in sortedKeys])
        paramsStr = method + path + paramsStr
        return hmac.new(self.api_secret.encode("utf-8"), paramsStr.encode("utf-8"), digestmod="sha256").digest()

    def _send_request(self, method, endpoint, params={}):
        params['apiKey'] = self.api_key
        params['timestamp'] = int(time.time()*1000)
        sortedKeys = sorted(params)
        paramsStr = "&".join(["%s=%s" % (x, params[x]) for x in sortedKeys])
        paramsStr += "&sign=" + urllib.parse.quote(base64.b64encode(self.genSignature(method=method, path=endpoint, paramsMap=params)))
        url = self.api_URL + endpoint
        response = self.session.request(method, url + f'?{paramsStr}', timeout=self.timeout)

        if not str(response.status_code).startswith('2'):
            raise BingxAPIException(response)
        try:
            res_json = response.json()
        except ValueError:
            raise BingxAPIException('Invalid Response: %s' % response.text)
        if "code" in res_json and res_json["code"] != 0:
            raise BingxAPIException(response)
        if "error" in res_json and res_json["error"]:
            raise BingxAPIException(response)

        if 'data' in res_json:
            return res_json['data']
        elif 'result' in res_json:
            return res_json['result']

    def contract_information(self):
        return self._send_request("GET", "/api/v1/market/getAllContracts")

    def query_latest_kline(self, symbol, klineType):
        # NOTE: this endpoint seems to be quite unreliable as returns error "HTTP(code=200), API(errorcode=80012): GetKlineRealtime has some error" often
        return self._send_request("GET", "/api/v1/market/getLatestKline", params={"symbol": symbol, "klineType": klineType})

    def query_kline_history(self, symbol, klineType, startTs="", endTs=""):
        """
        Valid resolutions: 1,3,5,15,30,60,120,240,360,720,1D,1W,1M
        times are in milliseconds
        startTs inclusive, endTs exclusive and both are required
        max returned 1440 klines
        does not return current kline
        """
        return self._send_request("GET", "/api/v1/market/getHistoryKlines", params={"symbol": symbol, "klineType": klineType, "startTs": startTs, "endTs": endTs})

    def get_latest_price_of_a_trading_pair(self, symbol):
        return self._send_request("GET", "/api/v1/market/getLatestPrice", params={"symbol": symbol})

    def get_positions(self, symbol):
        if symbol is None:
            symbol = ""
        return self._send_request("POST", "/api/v1/user/getPositions", params={"symbol": symbol})

    def get_account_asset_information(self, currency=""):
        return self._send_request("POST", "/api/v1/user/getBalance", params={"currency": currency})

    def place_new_order(self, symbol, side, price, size, tradeType, action, takerProfitPrice="", stopLossPrice=""):
        assert side in ['Bid', 'Ask']
        assert tradeType in ['Market', 'Limit']
        assert action in ['Open', 'Close']
        return self._send_request("POST", "/api/v1/user/trade", params={"symbol": symbol,
                                                                        "side": side,
                                                                        "entrustPrice": price,
                                                                        "entrustVolume": size,
                                                                        "tradeType": tradeType,
                                                                        "action": action,
                                                                        "takerProfitPrice": takerProfitPrice,
                                                                        "stopLossPrice": stopLossPrice})

    def query_order(self, symbol, orderId):
        return self._send_request("POST", "/api/v1/user/queryOrderStatus", params={"symbol": symbol, "orderId": orderId})

    def query_unfilled_orders(self, symbol):
        return self._send_request("POST", "/api/v1/user/pendingOrders", params={"symbol": symbol})

    def cancel_order(self, symbol, orderId):
        return self._send_request("POST", "/api/v1/user/cancelOrder", params={"symbol": symbol, "orderId": orderId})

    def cancel_all_orders(self):
        return self._send_request("POST", "/api/v1/user/cancelAll", params={})

    def cancel_batch_orders(self, symbol, oids):
        return self._send_request("POST", "/api/v1/user/batchCancelOrders", params={"symbol": symbol, "oids": oids})

    def get_market_depth(self, symbol, level):
        return self._send_request("GET", "/api/v1/market/getMarketDepth", params={"symbol": symbol, "level": level})

    def switch_margin_mode(self, symbol, marginMode):
        assert marginMode in ['Isolated', 'Cross']
        return self._send_request("POST", "/api/v1/user/setMarginMode", params={"symbol": symbol, "marginMode": marginMode})

    def switch_leverage(self, symbol, leverage, side):
        return self._send_request("POST", "/api/v1/user/setLeverage", params={"symbol": symbol, "leverage": leverage, 'side': side})


