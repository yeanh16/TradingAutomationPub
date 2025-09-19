import base64
import hmac
from collections import OrderedDict, namedtuple
import requests
import time
import urllib.request
from urllib.parse import urlparse
import hashlib
import json
import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables

load_dotenv(find_dotenv())


class XtAPIException(Exception):

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


# response
ResponseObj = namedtuple("ResponseObj", ["status", "response", "json"])
# PayloadObj
PayloadObj = namedtuple("PayloadObj", ["data", "uri", "method"])
XT_VALIDATE_ALGORITHMS = "HmacSHA256"
XT_VALIDATE_RECVWINDOW = "5000"
XT_VALIDATE_CONTENTTYPE_URLENCODE = "application/x-www-form-urlencoded"
XT_VALIDATE_CONTENTTYPE_JSON = "application/json;charset=UTF-8"


class XtClient(object):
    MAIN_NET_API_URL = 'https://fapi.xt.com'

    def __init__(self, api_key=None, api_secret=None, timeout=1):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_URL = self.MAIN_NET_API_URL
        self.timeout = timeout
        self.session = requests.session()

    def get_datas(self, param: dict = None):
        """ """
        data = {
            "accesskey": self.api_key,
            "secretkey": self.api_secret
        }
        if param and isinstance(param, dict):
            data.update(**param)
        return data

    def create_header(self):
        """ """
        header = OrderedDict()
        # header["xt-validate-algorithms"] = XT_VALIDATE_ALGORITHMS
        header["xt-validate-appkey"] = self.api_key
        # header["xt-validate-recvwindow"] = XT_VALIDATE_RECVWINDOW
        header["xt-validate-timestamp"] = str(int(time.time() * 1000))
        return header

    def create_signed(self, params: str, secretKey: str) -> str:
        """ """
        signature = hmac.new(secretKey.encode(
            'utf-8'), params.encode('utf-8'), hashlib.sha256).hexdigest().upper()
        return signature

    def create_payload(self, payload: PayloadObj) -> dict:
        """ """
        # Need sorted
        header = self.create_header()
        X = urllib.parse.urlencode(
            dict(sorted(header.items(), key=lambda kv: (kv[0], kv[1]))))
        path = urlparse(payload.uri).path
        decode, tmp = XT_VALIDATE_CONTENTTYPE_JSON, None

        if payload.data.pop("urlencoded", False):
            tmp = urllib.parse.urlencode(
                dict(sorted(payload.data.items(), key=lambda kv: (kv[0], kv[1]))), safe=",")
            decode = XT_VALIDATE_CONTENTTYPE_URLENCODE

        if not payload.data:
            param = None
            Y = "#{}#{}".format(path, "")
        else:
            param = json.dumps(payload.data)
            Y = "#{}#{}#{}".format(path, tmp or param, "")
            param = payload.data
        Y = "#{}#{}".format(path, "symbol=btc_usdt&interval=1m")

        signature = self.create_signed(X + Y, self.api_secret)
        header["xt-validate-signature"] = signature
        header["Content-Type"] = decode
        # print(f"X {X} | Y {Y}")
        return header, param

    def get_auth_payload(self, payload) -> dict:
        """ return payload contains request params"""
        if not payload.data.keys() & {"accesskey", "secretkey"}:
            return [None] * 2
        return self.create_payload(payload)

    def _request(self, method, url, params={}, **kwargs):
        """ """
        try:
            sortedKeys = sorted(params)
            paramsStr = "&".join(["%s=%s" % (x, params[x]) for x in sortedKeys if params[x] is not None])
            response = requests.request(method, self.MAIN_NET_API_URL+url+f'?{paramsStr}')
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            msg = 'Request timeout, content:{t}]........'.format(t=e.response.text)
            return ResponseObj(False, None, msg)

        if response.status_code == 200 and response:
            try:
                data = response.json()
            except Exception:
                msg = "Expecting value: line 1 column 1 (char 0)"
                return ResponseObj(False, None, msg)
            return ResponseObj(True, response, data)
        else:
            return ResponseObj(False, response, response.text)

    def request(self, method, url, *, auth=False, params={}):
        """ """
        headers, _ = self.get_auth_payload(PayloadObj(self.get_datas(params), url, method))
        request_obj = self._request(method, url, params=params, headers=headers)
        return request_obj.json['result']

    #
    # def genSignature(self, path, method, paramsMap):
    #     sortedKeys = sorted(paramsMap)
    #     paramsStr = "&".join(["%s=%s" % (x, paramsMap[x]) for x in sortedKeys])
    #     paramsStr = method + path + paramsStr
    #     return hmac.new(self.api_secret.encode("utf-8"), paramsStr.encode("utf-8"), digestmod="sha256").hexdigest().upper()
    #
    # def _send_request(self, method, endpoint, params={}):
    #     params['xt-validate-appkey'] = self.api_key
    #     params['xt-validate-timestamp'] = int(time.time()*1000)
    #     params['xt-validate-algorithms'] = "HmacSHA256"
    #     sortedKeys = sorted(params)
    #     paramsStr = "&".join(["%s=%s" % (x, params[x]) for x in sortedKeys])
    #     paramsStr += "&sign=" + urllib.parse.quote(base64.b64encode(self.genSignature(method=method, path=endpoint, paramsMap=params)))
    #     url = self.api_URL + endpoint
    #     response = self.session.request(method, url + f'?{paramsStr}', timeout=self.timeout)
    #
    #     if not str(response.status_code).startswith('2'):
    #         raise XtAPIException(response)
    #     try:
    #         res_json = response.json()
    #     except ValueError:
    #         raise XtAPIException('Invalid Response: %s' % response.text)
    #     if "code" in res_json and res_json["code"] != 0:
    #         raise XtAPIException(response)
    #     if "error" in res_json and res_json["error"]:
    #         raise XtAPIException(response)
    #
    #     if 'data' in res_json:
    #         return res_json['data']
    #     elif 'result' in res_json:
    #         return res_json['result']

    def get_exchange_info(self):
        return self.request("GET", "/future/market/v1/public/symbol/list")

    def get_account_info(self):
        return self.request("GET", "/future/user/v1/account/info")

    def get_kline(self, symbol, interval, startTime=None, endTime=None, limit=None):
        return self.request("GET", "/future/market/v1/public/q/kline", params={'symbol': symbol, 'interval':interval, 'startTime':startTime, 'endTime': endTime, 'limit': limit})


if __name__ == '__main__':
    # Load API credentials from environment variables
    xt_api_key = os.environ.get("XT_PUBLIC_KEY")
    xt_api_secret = os.environ.get("XT_PRIVATE_KEY")
    
    if not xt_api_key or not xt_api_secret:
        print("Error: XT_API_KEY and XT_API_SECRET environment variables must be set")
        exit(1)
    
    c = XtClient(api_key=xt_api_key, api_secret=xt_api_secret)
