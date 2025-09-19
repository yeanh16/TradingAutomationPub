import time
import urllib.parse
from typing import Optional, Dict, Any, List
from requests import Request, Session, Response
import hmac
# from ciso8601 import parse_datetime
# from UniversalClient import CAPITALDOTCOM_API_KEY, CAPITALDOTCOM_PASSWORD, CAPITALDOTCOM_USERNAME
import threading
import os
from dotenv import load_dotenv, find_dotenv


load_dotenv(find_dotenv())
CAPITALDOTCOM_API_KEY = os.environ.get("CAPITALDOTCOM_API_KEY")
CAPITALDOTCOM_USERNAME = os.environ.get("CAPITALDOTCOM_USERNAME")
CAPITALDOTCOM_PASSWORD = os.environ.get("CAPITALDOTCOM_PASSWORD")


class CapitalClient:
    PROD_URL = 'https://api-capital.backend-capital.com/api/v1/'
    MAIN_ACCOUNT_ID = 150134481662013584
    DEMO_URL = 'https://demo-api-capital.backend-capital.com/api/v1/'
    MAIN_ACCOUNT_ID_DEMO = 166250276995212318
    SECOND_ACCOUNT_ID = 170989073324863632

    def __init__(self, api_key=None, username=None, password=None, timeout=0.5, subaccount=None, demo=False, second_account=False) -> None:
        self._session = Session()
        self._base_url = self.PROD_URL if not demo else self.DEMO_URL
        self._api_key = api_key
        self._username = username
        self._password = password
        self._timeout = timeout
        self._security_token = None
        self._authorization_token = None
        if not second_account:
            self._account_id = self.MAIN_ACCOUNT_ID if not demo else self.MAIN_ACCOUNT_ID_DEMO
        else:
            self._account_id = self.SECOND_ACCOUNT_ID
        self.refresh_security_tokens()
        self.subaccount = subaccount

        if subaccount:
            accounts = self.get_account_info()['accounts']
            for account in accounts:
                if account['accountName'] == self.subaccount:
                    accountId = account['accountId']
                    self._account_id = accountId
            self.refresh_security_tokens()

        # refresh security token thread
        threading.Thread(target=self._refresh_security_token_job, daemon=True).start()

    def refresh_security_tokens(self):
        request = Request('POST', self._base_url + "session", json={"encryptedPassword": False,
                                                                    "identifier": self._username,
                                                                    "password": self._password})
        self._sign_request(request)
        response = self._session.send(request.prepare(), timeout=self._timeout)
        self._security_token = response.headers['X-SECURITY-TOKEN']
        self._authorization_token = response.headers['CST']
        self._request('PUT', 'session', json={'accountId': self._account_id})

    def _refresh_security_token_job(self):
        while True:
            time.sleep(60 * 30)
            self.refresh_security_tokens()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('GET', path, params=params)

    def _post(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('POST', path, json=params)

    def _delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('DELETE', path, json=params)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        request = Request(method, self._base_url + path, **kwargs)
        self._sign_request(request)
        response = self._session.send(request.prepare(), timeout=self._timeout)
        return self._process_response(response)

    def _sign_request(self, request: Request) -> None:
        request.prepare()
        request.headers['X-CAP-API-KEY'] = self._api_key
        if self._security_token:
            request.headers['X-SECURITY-TOKEN'] = self._security_token
            request.headers['CST'] = self._authorization_token

    def _process_response(self, response: Response) -> Any:
        try:
            data = response.json()
            # headers = response.headers
            # print(data)
            # print(headers)
        except ValueError:
            response.raise_for_status()
            raise
        else:
            if 'error' in data:
                raise Exception(f"CapitalClient ERROR {data['status']} {data['error']} {data['message']}")
            if 'errorCode' in data:
                if data['errorCode'] == 'error.security.token-invalid' or data['errorCode'] == 'error.invalid.session.token':
                    self.refresh_security_tokens()
                elif data['errorCode'] == 'error.prices.not-found':
                    # this error happens when looking up really old kline data
                    return {'prices': []}
                elif data['errorCode'] == 'error.not-found.dealReference':
                    return {}
                elif data['errorCode'] == 'error.not-different.accountId':
                    return
                raise Exception(f"CapitalClient ERROR {data['errorCode']}")

            return data

    def get_account_info(self):
        return self._get(f'accounts')

    def get_marketnavigation(self, nodeId=''):
        return self._get(f'marketnavigation/{nodeId}')

    def get_market(self, epic):
        if isinstance(epic, str):
            return self._get(f'markets/{epic}')
        elif isinstance(epic, list):
            master_list = []
            while len(epic) > 0:
                data = self._get(f'markets', params={'epics': str(epic[:50])[2:-2].replace(" ", "").replace("'", "")})
                master_list += data['marketDetails']
                epic = epic[50:]
            return {'marketDetails': master_list}

    def get_positions(self):
        return self._get(f'positions')

    def get_klines(self, epic, resolution, start=None, end=None, limit=1000):
        assert resolution in ['MINUTE', 'MINUTE_5', 'MINUTE_10', 'MINUTE_15', 'MINUTE_30', 'HOUR', 'HOUR_4', 'DAY', 'WEEK']
        try:
            return self._get(f'prices/{epic}', params={'resolution': resolution, 'from': start, 'max': limit, 'to': end})
        except Exception as e:
            if 'error.not-found.epic' in str(e):
                raise Exception(f"CAPITAL epic '{epic}' does not exist")
            raise e

    def get_open_oders(self):
        return self._get(f'workingorders')

    def get_position_order_confirmation(self, dealReference):
        return self._get(f'confirms/{dealReference}')

    def cancel_order(self, orderId):
        return self._delete(f'workingorders/{orderId}')

    def create_order(self, side, epic, limit, size, order_type):
        assert order_type in ["LIMIT", "STOP"]
        assert side in ["BUY", "SELL"]
        return self._post(f'workingorders', params={"direction": side, "epic": epic, "level": limit, "size": size, "type": order_type})


if __name__ == '__main__':
    ucc = CapitalClient(api_key=CAPITALDOTCOM_API_KEY, username=CAPITALDOTCOM_USERNAME, password=CAPITALDOTCOM_PASSWORD)
