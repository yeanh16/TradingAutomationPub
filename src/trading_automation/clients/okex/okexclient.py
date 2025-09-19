from requests import Session
import json
from . import consts as c, utils, exceptions
from .consts import *


class OkexClient(object):
    """
    Largely taken from https://github.com/jane-cloud/Open-API-SDK-V5
    """
    def __init__(self, api_key, api_secret_key, passphrase, use_server_time=False, flag='0', timeout=0.3):

        self.API_KEY = api_key
        self.API_SECRET_KEY = api_secret_key
        self.PASSPHRASE = passphrase
        self.use_server_time = use_server_time
        self.flag = flag  # '0': real trading '1': demo trading
        self.timeout = timeout
        self.session = Session()

    def _request(self, method, request_path, params):
        """
        client.get_mark_price("SWAP", instId="BTC-USDT-SWAP")
        client.place_order(instId='BTC-USDT', tdMode='cross', side='buy', ordType='limit', sz='0.0001',px='20000', ccy='USDT')
        client.get_account()
        """
        if method == c.GET:
            request_path = request_path + utils.parse_params_to_str(params)
        # url
        url = c.API_URL + request_path
        timestamp = utils.get_timestamp()
        # sign & header
        if self.use_server_time:
            timestamp = self._get_timestamp()
        body = json.dumps(params) if method == c.POST else ""
        sign = utils.sign(utils.pre_hash(timestamp, method, request_path, str(body)), self.API_SECRET_KEY)
        header = utils.get_header(self.API_KEY, sign, timestamp, self.PASSPHRASE, self.flag)
        # send request
        response = None
        if method == c.GET:
            response = self.session.get(url, headers=header, timeout=self.timeout)
        elif method == c.POST:
            response = self.session.post(url, data=body, headers=header, timeout=self.timeout)
        # print(response.json())
        if not str(response.status_code).startswith('2') or response.json()['code'] != "0":
            if response.json()['code'] == "51603":  # Order does not exist, return empty
                return []
            raise exceptions.OkexAPIException(response)
        if len(response.json()['data']) == 1 and isinstance(response.json()['data'][0], dict):
            return response.json()['data'][0]
        return response.json()['data']

    def _request_without_params(self, method, request_path):
        return self._request(method, request_path, {})

    def _request_with_params(self, method, request_path, params):
        return self._request(method, request_path, params)

    def _get_timestamp(self):
        url = c.API_URL + c.SERVER_TIMESTAMP_URL
        response = self.session.get(url)
        # response = requests.get(url)
        if response.status_code == 200:
            return response.json()['data'][0]['ts']
        else:
            return ""

    # Get Positions
    def get_position_risk(self, instType=''):
        params = {}
        if instType:
            params['instType'] = instType
        return self._request_with_params(GET, POSITION_RISK, params)

    # Get Balance
    def get_account(self, ccy=''):
        params = {}
        if ccy:
            params['ccy'] = ccy
        return self._request_with_params(GET, ACCOUNT_INFO, params)

    # Get Positions
    def get_positions(self, instType='', instId=''):
        if instId is None:
            instId = ''
        params = {'instType': instType, 'instId': instId}
        return self._request_with_params(GET, POSITION_INFO, params)

    # Get Bills Details (recent 7 days)
    def get_bills_detail(self, instType='', ccy='', mgnMode='', ctType='', type='', subType='', after='', before='',
                         limit=''):
        params = {'instType': instType, 'ccy': ccy, 'mgnMode': mgnMode, 'ctType': ctType, 'type': type,
                  'subType': subType, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, BILLS_DETAIL, params)

    # Get Bills Details (recent 3 months)
    def get_bills_details(self, instType='', ccy='', mgnMode='', ctType='', type='', subType='', after='', before='',
                          limit=''):
        params = {'instType': instType, 'ccy': ccy, 'mgnMode': mgnMode, 'ctType': ctType, 'type': type,
                  'subType': subType, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, BILLS_ARCHIVE, params)

    # Get Account Configuration
    def get_account_config(self):
        return self._request_without_params(GET, ACCOUNT_CONFIG)

    # Get Account Configuration
    def get_position_mode(self, posMode):
        params = {'posMode': posMode}
        return self._request_with_params(POST, POSITION_MODE, params)

    # Get Account Configuration
    def set_leverage(self, lever, mgnMode, instId='', ccy='', posSide=''):
        params = {'lever': lever, 'mgnMode': mgnMode, 'instId': instId, 'ccy': ccy, 'posSide': posSide}
        return self._request_with_params(POST, SET_LEVERAGE, params)

    # Get Maximum Tradable Size For Instrument
    def get_maximum_trade_size(self, instId, tdMode, ccy='', px=''):
        params = {'instId': instId, 'tdMode': tdMode, 'ccy': ccy, 'px': px}
        return self._request_with_params(GET, MAX_TRADE_SIZE, params)

    # Get Maximum Available Tradable Amount
    def get_max_avail_size(self, instId, tdMode, ccy='', reduceOnly=''):
        params = {'instId': instId, 'tdMode': tdMode, 'ccy': ccy, 'reduceOnly': reduceOnly}
        return self._request_with_params(GET, MAX_AVAIL_SIZE, params)

    # Increase / Decrease margin
    def Adjustment_margin(self, instId, posSide, type, amt):
        params = {'instId': instId, 'posSide': posSide, 'type': type, 'amt': amt}
        return self._request_with_params(POST, ADJUSTMENT_MARGIN, params)

    # Get Leverage
    def get_leverage(self, instId, mgnMode):
        params = {'instId': instId, 'mgnMode': mgnMode}
        return self._request_with_params(GET, GET_LEVERAGE, params)

    # Get the maximum loan of isolated MARGIN
    def get_max_load(self, instId, mgnMode, mgnCcy):
        params = {'instId': instId, 'mgnMode': mgnMode, 'mgnCcy': mgnCcy}
        return self._request_with_params(GET, MAX_LOAN, params)

    # Get Fee Rates
    def get_fee_rates(self, instType, instId='', uly='', category=''):
        params = {'instType': instType, 'instId': instId, 'uly': uly, 'category': category}
        return self._request_with_params(GET, FEE_RATES, params)

    # Get interest-accrued
    def get_interest_accrued(self, instId='', ccy='', mgnMode='', after='', before='', limit=''):
        params = {'instId': instId, 'ccy': ccy, 'mgnMode': mgnMode, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, INTEREST_ACCRUED, params)

    # Get interest-accrued
    def get_interest_rate(self, ccy=''):
        params = {'ccy': ccy}
        return self._request_with_params(GET, INTEREST_RATE, params)

    # Set Greeks (PA/BS)
    def set_greeks(self, greeksType):
        params = {'greeksType': greeksType}
        return self._request_with_params(POST, SET_GREEKS, params)

    # Get Maximum Withdrawals
    def get_max_withdrawal(self, ccy=''):
        params = {'ccy': ccy}
        return self._request_with_params(GET, MAX_WITHDRAWAL, params)

    # Get Deposit Address
    def get_deposit_address(self, ccy):
        params = {'ccy': ccy}
        return self._request_with_params(GET, DEPOSIT_ADDRESS, params)

    # Get Balance
    def get_balances(self, ccy=''):
        params = {'ccy': ccy}
        return self._request_with_params(GET, GET_BALANCES, params)

    # Get Account Configuration
    def funds_transfer(self, ccy, amt, froms, to, type='0', subAcct='', instId='', toInstId=''):
        params = {'ccy': ccy, 'amt': amt, 'from': froms, 'to': to, 'type': type, 'subAcct': subAcct,
                  'instId': instId,
                  'toInstId': toInstId}
        return self._request_with_params(POST, FUNDS_TRANSFER, params)

    # Withdrawal
    def coin_withdraw(self, ccy, amt, dest, toAddr, pwd, fee):
        params = {'ccy': ccy, 'amt': amt, 'dest': dest, 'toAddr': toAddr, 'pwd': pwd, 'fee': fee}
        return self._request_with_params(POST, WITHDRAWAL_COIN, params)

    # Get Deposit History
    def get_deposit_history(self, ccy='', state='', after='', before='', limit=''):
        params = {'ccy': ccy, 'state': state, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, DEPOSIT_HISTORY, params)

    # Get Withdrawal History
    def get_withdrawal_history(self, ccy='', state='', after='', before='', limit=''):
        params = {'ccy': ccy, 'state': state, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, WITHDRAWAL_HISTORY, params)

    # Get Currencies
    def get_currency(self):
        return self._request_without_params(GET, CURRENCY_INFO)

    # PiggyBank Purchase/Redemption
    def purchase_redempt(self, ccy, amt, side):
        params = {'ccy': ccy, 'amt': amt, 'side': side}
        return self._request_with_params(POST, PURCHASE_REDEMPT, params)

    # Get Withdrawal History
    def get_bills(self, ccy='', type='', after='', before='', limit=''):
        params = {'ccy': ccy, 'type': type, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, BILLS_INFO, params)

    # Get Piggy Balance
    def get_piggy_balance(self, ccy=''):
        params = {}
        if ccy:
            params = {'ccy': ccy}
        return self._request_with_params(GET, PIGGY_BALANCE, params)

    # Get Tickers
    def get_tickers(self, instType, uly=''):
        if uly:
            params = {'instType': instType, 'uly': uly}
        else:
            params = {'instType': instType}
        return self._request_with_params(GET, TICKERS_INFO, params)

    # Get Ticker
    def get_ticker(self, instId):
        params = {'instId': instId}
        return self._request_with_params(GET, TICKER_INFO, params)

    # Get Index Tickers
    def get_index_ticker(self, quoteCcy='', instId=''):
        params = {'quoteCcy': quoteCcy, 'instId': instId}
        return self._request_with_params(GET, INDEX_TICKERS, params)

    # Get Order Book
    def get_orderbook(self, instId, sz=''):
        params = {'instId': instId, 'sz': sz}
        return self._request_with_params(GET, ORDER_BOOKS, params)

    # Get Candlesticks
    def get_candlesticks(self, instId, after='', before='', bar='', limit=''):
        params = {'instId': instId, 'after': after, 'before': before, 'bar': bar, 'limit': limit}
        return self._request_with_params(GET, MARKET_CANDLES, params)

    # GGet Candlesticks History（top currencies only）
    def get_history_candlesticks(self, instId, after='', before='', bar='', limit=''):
        params = {'instId': instId, 'after': after, 'before': before, 'bar': bar, 'limit': limit}
        return self._request_with_params(GET, HISTORY_CANDLES, params)

    # Get Index Candlesticks
    def get_index_candlesticks(self, instId, after='', before='', bar='', limit=''):
        params = {'instId': instId, 'after': after, 'before': before, 'bar': bar, 'limit': limit}
        return self._request_with_params(GET, INDEX_CANDLES, params)

    # Get Mark Price Candlesticks
    def get_markprice_candlesticks(self, instId, after='', before='', bar='', limit=''):
        params = {'instId': instId, 'after': after, 'before': before, 'bar': bar, 'limit': limit}
        return self._request_with_params(GET, MARKPRICE_CANDLES, params)

    # Get Index Candlesticks
    def get_trades(self, instId, limit=''):
        params = {'instId': instId, 'limit': limit}
        return self._request_with_params(GET, MARKET_TRADES, params)

    # Get Volume
    def get_volume(self):
        return self._request_without_params(GET, VOLUME)

    # Get Oracle
    def get_oracle(self):
        return self._request_without_params(GET, ORACLE)

    # Get Tier
    def get_tier(self, instType='', tdMode='', uly='', instId='', ccy='', tier=''):
        params = {'instType': instType, 'tdMode': tdMode, 'uly': uly, 'instId': instId, 'ccy': ccy, 'tier': tier}
        return self._request_with_params(GET, TIER, params)

    # Get Instruments
    def get_instruments(self, instType, uly='', instId=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId}
        return self._request_with_params(GET, INSTRUMENT_INFO, params)

    # Get Delivery/Exercise History
    def get_deliver_history(self, instType, uly, after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, DELIVERY_EXERCISE, params)

    # Get Open Interest
    def get_open_interest(self, instType, uly='', instId=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId}
        return self._request_with_params(GET, OPEN_INTEREST, params)

    # Get Funding Rate
    def get_funding_rate(self, instId):
        params = {'instId': instId}
        return self._request_with_params(GET, FUNDING_RATE, params)

    # Get Funding Rate History
    def funding_rate_history(self, instId, after='', before='', limit=''):
        params = {'instId': instId, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, FUNDING_RATE_HISTORY, params)

    # Get Limit Price
    def get_price_limit(self, instId):
        params = {'instId': instId}
        return self._request_with_params(GET, PRICE_LIMIT, params)

    # Get Option Market Data
    def get_opt_summary(self, uly, expTime=''):
        params = {'uly': uly, 'expTime': expTime}
        return self._request_with_params(GET, OPT_SUMMARY, params)

    # Get Estimated Delivery/Excercise Price
    def get_estimated_price(self, instId):
        params = {'instId': instId}
        return self._request_with_params(GET, ESTIMATED_PRICE, params)

    # Get Discount Rate And Interest-Free Quota
    def discount_interest_free_quota(self, ccy=''):
        params = {'ccy': ccy}
        return self._request_with_params(GET, DISCOUNT_INTEREST_INFO, params)

    # Get System Time
    def get_system_time(self):
        return self._request_without_params(GET, SYSTEM_TIME)

    # Get Liquidation Orders
    def get_liquidation_orders(self, instType, mgnMode='', instId='', ccy='', uly='', alias='', state='', before='',
                               after='', limit=''):
        params = {'instType': instType, 'mgnMode': mgnMode, 'instId': instId, 'ccy': ccy, 'uly': uly,
                  'alias': alias, 'state': state, 'before': before, 'after': after, 'limit': limit}
        return self._request_with_params(GET, LIQUIDATION_ORDERS, params)

    # Get Mark Price
    def get_mark_price(self, instType, uly='', instId=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId}
        return self._request_with_params(GET, MARK_PRICE, params)

    # Get Tier
    def get_tier(self, instType, tdMode, uly='', instId='', ccy='', tier=''):
        params = {'instType': instType, 'tdMode': tdMode, 'uly': uly, 'instId': instId, 'ccy': ccy, 'tier': tier}
        return self._request_with_params(GET, TIER, params)

    # Get Interest Rate and Loan Quota
    def get_interest_loan(self):
        return self._request_without_params(GET, INTEREST_LOAN)

    # Get underlying
    def get_underlying(self, instType):
        params = {'instType': instType}
        return self._request_with_params(GET, UNDERLYING, params)

    def status(self, state=''):
        params = {'state': state}
        return self._request_with_params(GET, STATUS, params)

    # ---------------- SUBACCOUNT API ---------------
    def balances(self, subAcct):
        params = {"subAcct": subAcct}
        return self._request_with_params(GET, BALANCE, params)

    def bills(self, ccy='', type='', subAcct='', after='', before='', limit=''):
        params = {"ccy": ccy, 'type': type, 'subAcct': subAcct, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, BILLs, params)

    def delete(self, pwd, subAcct, apiKey):
        params = {'pwd': pwd, 'subAcct': subAcct, 'apiKey': apiKey}
        return self._request_with_params(POST, DELETE, params)

    def reset(self, pwd, subAcct, label, apiKey, perm, ip=''):
        params = {'pwd': pwd, 'subAcct': subAcct, 'label': label, 'apiKey': apiKey, 'perm': perm, 'ip': ip}
        return self._request_with_params(POST, RESET, params)

    def create(self, pwd, subAcct, label, Passphrase, perm='', ip=''):
        params = {'pwd': pwd, 'subAcct': subAcct, 'label': label, 'Passphrase': Passphrase, 'perm': perm, 'ip': ip}
        return self._request_with_params(POST, CREATE, params)

    def view_list(self, enable='', subAcct='', after='', before='', limit=''):
        params = {'enable': enable, 'subAcct': subAcct, 'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, VIEW_LIST, params)

    def subAccount_transfer(self, ccy, amt, froms, to, fromSubAccount,toSubAccount):
        params = {'ccy': ccy, 'amt': amt, 'from': froms, 'to': to, 'fromSubAccount': fromSubAccount, 'toSubAccount': toSubAccount}
        return self._request_with_params(POST, SUBACCOUNT_TRANSFER, params)

    # Place Order
    def place_order(self, instId, tdMode, side, ordType, sz, ccy='', clOrdId='', tag='', posSide='', px='',
                    reduceOnly='', tgtCcy=''):
        params = {'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': ordType, 'sz': sz, 'ccy': ccy,
                  'clOrdId': clOrdId, 'tag': tag, 'posSide': posSide, 'px': px, 'reduceOnly': reduceOnly, 'tgtCcy' : tgtCcy}
        return self._request_with_params(POST, PLACE_ORDER, params)

    # Place Multiple Orders
    def place_multiple_orders(self, orders_data):
        return self._request_with_params(POST, BATCH_ORDERS, orders_data)

    # Cancel Order
    def cancel_order(self, instId, ordId='', clOrdId=''):
        params = {'instId': instId, 'ordId': ordId, 'clOrdId': clOrdId}
        return self._request_with_params(POST, CANCEL_ORDER, params)

    # Cancel Multiple Orders
    def cancel_multiple_orders(self, orders_data):
        return self._request_with_params(POST, CANCEL_BATCH_ORDERS, orders_data)

    # Amend Order
    def amend_order(self, instId, cxlOnFail='', ordId='', clOrdId='', reqId='', newSz='', newPx=''):
        params = {'instId': instId, 'cxlOnFailc': cxlOnFail, 'ordId': ordId, 'clOrdId': clOrdId, 'reqId': reqId,
                  'newSz': newSz,
                  'newPx': newPx}
        return self._request_with_params(POST, AMEND_ORDER, params)

    # Amend Multiple Orders
    def amend_multiple_orders(self, orders_data):
        return self._request_with_params(POST, AMEND_BATCH_ORDER, orders_data)

    # Close Positions
    def close_positions(self, instId, mgnMode, posSide='', ccy=''):
        params = {'instId': instId, 'mgnMode': mgnMode, 'posSide': posSide, 'ccy': ccy}
        return self._request_with_params(POST, CLOSE_POSITION, params)

    # Get Order Details
    def get_orders(self, instId, ordId='', clOrdId=''):
        params = {'instId': instId, 'ordId': ordId, 'clOrdId': clOrdId}
        return self._request_with_params(GET, ORDER_INFO, params)

    # Get Order List
    def get_order_list(self, instType='', uly='', instId='', ordType='', state='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordType': ordType, 'state': state,
                  'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_PENDING, params)

    # Get Order History (last 7 days）
    def get_orders_history(self, instType, uly='', instId='', ordType='', state='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordType': ordType, 'state': state,
                  'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_HISTORY, params)

    # Get Order History (last 3 months)
    def orders_history_archive(self, instType, uly='', instId='', ordType='', state='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordType': ordType, 'state': state,
                  'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_HISTORY_ARCHIVE, params)

    # Get Transaction Details
    def get_fills(self, instType='', uly='', instId='', ordId='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordId': ordId, 'after': after, 'before': before,
                  'limit': limit}
        return self._request_with_params(GET, ORDER_FILLS, params)

    # Place Algo Order
    def place_algo_order(self, instId, tdMode, side, ordType, sz, ccy='', posSide='', reduceOnly='', tpTriggerPx='',
                         tpOrdPx='', slTriggerPx='', slOrdPx='', triggerPx='', orderPx=''):
        params = {'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': ordType, 'sz': sz, 'ccy': ccy,
                  'posSide': posSide, 'reduceOnly': reduceOnly, 'tpTriggerPx': tpTriggerPx, 'tpOrdPx': tpOrdPx,
                  'slTriggerPx': slTriggerPx, 'slOrdPx': slOrdPx, 'triggerPx': triggerPx, 'orderPx': orderPx}
        return self._request_with_params(POST, PLACE_ALGO_ORDER, params)

    # Cancel Algo Order
    def cancel_algo_order(self, algoId, instId):
        params = [{'algoId': algoId, 'instId': instId}]
        return self._request_with_params(POST, CANCEL_ALGOS, params)

    # Cancel Algo Order list
    def cancel_algo_order_list(self, list):
        return self._request_with_params(POST, CANCEL_ALGOS, list)


    # Get Algo Order List
    def order_algos_list(self, ordType, algoId='', instType='', instId='', after='', before='', limit=''):
        params = {'ordType': ordType, 'algoId': algoId, 'instType': instType, 'instId': instId, 'after': after,
                  'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_ALGO_PENDING, params)

    # Get Algo Order History
    def order_algos_history(self, ordType, state='', algoId='', instType='', instId='', after='', before='', limit=''):
        params = {'ordType': ordType, 'state': state, 'algoId': algoId, 'instType': instType, 'instId': instId,
                  'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_ALGO_HISTORY, params)

    # Get Transaction Details History
    def get_fills_history(self, instType, uly='', instId='', ordId='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordId': ordId, 'after': after, 'before': before,
                  'limit': limit}
        return self._request_with_params(GET, ORDERS_FILLS_HISTORY, params)

