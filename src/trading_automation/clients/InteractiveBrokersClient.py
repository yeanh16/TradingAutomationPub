from os.path import exists

from ibapi.wrapper import *
from ibapi.client import *
from ibapi.contract import *
from ibapi.order import *
from ibapi.scanner import *
from ibTestbed.ScannerSubscriptionSamples import *
from threading import Thread
import queue
from datetime import datetime, timedelta
import time
import math
from trading_automation.core.Utils import *
from .UniversalClient import *


def printinstance(inst:Object):
    attrs = vars(inst)
    print(', '.join('{}:{}'.format(key, decimalMaxString(value) if type(value) is Decimal else
                                   floatMaxString(value) if type(value) is float else
                                   intMaxString(value) if type(value) is int else
                                   value) for key, value in attrs.items()))


class TestWrapper(EWrapper):
    # Receive messages, need to manually override each method from base class to return required data for use.

    def __init__(self):
        super().__init__()
        error_queue = queue.Queue()
        self.my_errors_queue = error_queue
        self.currently_receiving_klines_queue = queue.Queue()

    # error handling methods
    def init_error(self):
        error_queue = queue.Queue()
        self.my_errors_queue = error_queue

    def is_error(self):
        error_exist = not self.my_errors_queue.empty()
        return error_exist

    def get_error(self, timeout=6):
        if self.is_error():
            try:
                return self.my_errors_queue.get(timeout=timeout)
            except queue.Empty:
                return None
        return None

    def error(self, id, errorCode, errorString, advancedOrderRejectJson=""):
        # Overrides the native method
        if str(errorCode)[0] != "2":
            errormessage = "IB returns an error with reqid %d errorcode %d that says %s" % (id, errorCode, errorString)
            print(errormessage)
            self.my_errors_queue.put(errormessage)
            raise Exception(errormessage)

    def init_time(self):
        time_queue = queue.Queue()
        self.my_time_queue = time_queue
        return time_queue

    def currentTime(self, server_time):
        # Overriden method
        self.my_time_queue.put(server_time)

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        super().contractDetails(reqId, contractDetails)
        printinstance(contractDetails)

    def contractDetailsEnd(self, reqId: int):
        super().contractDetailsEnd(reqId)
        print("ContractDetailsEnd. ReqId:", reqId)

    def symbolSamples(self, reqId:int, contractDescriptions:ListOfContractDescription):
        super().symbolSamples(reqId, contractDescriptions)
        print("Symbol Samples. Request Id: ", reqId)
        for contractDescription in contractDescriptions:
            derivSecTypes = ""
            for derivSecType in contractDescription.derivativeSecTypes:
                derivSecTypes += " "
                derivSecTypes += derivSecType
            print("Contract: conId:%s, symbol:%s, secType:%s primExchange:%s, "
            "currency:%s, derivativeSecTypes:%s, description:%s, issuerId:%s" % (
                             contractDescription.contract.conId,
                             contractDescription.contract.symbol,
                             contractDescription.contract.secType,
                             contractDescription.contract.primaryExchange,
                             contractDescription.contract.currency, derivSecTypes,
                             contractDescription.contract.description,
                             contractDescription.contract.issuerId))

    def historicalData(self, reqId: int, bar: BarData):
        print("HistoricalData. ReqId:", reqId, "BarData.", bar)
        self.currently_receiving_klines_queue.put(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        super().historicalDataEnd(reqId, start, end)
        print("HistoricalDataEnd. ReqId:", reqId, "from", start, "to", end)
        # put False into queue to signal the end
        self.currently_receiving_klines_queue.put(False)

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        print("HistoricalDataUpdate. ReqId:", reqId, "BarData.", bar)

    def scannerData(self, reqId: int, rank: int, contractDetails: ContractDetails,
                    distance: str, benchmark: str, projection: str, legsStr: str):
        super().scannerData(reqId, rank, contractDetails, distance, benchmark,
                            projection, legsStr)
        #        print("ScannerData. ReqId:", reqId, "Rank:", rank, "Symbol:", contractDetails.contract.symbol,
        #              "SecType:", contractDetails.contract.secType,
        #              "Currency:", contractDetails.contract.currency,
        #              "Distance:", distance, "Benchmark:", benchmark,
        #              "Projection:", projection, "Legs String:", legsStr)
        print("ScannerData. ReqId:", reqId, ScanData(contractDetails.contract, rank, distance, benchmark, projection, legsStr))

    def scannerDataEnd(self, reqId: int):
        super().scannerDataEnd(reqId)
        print("ScannerDataEnd. ReqId:", reqId)


class TestClient(EClient):
    # sends messages

    def __init__(self, wrapper):
        EClient.__init__(self, wrapper)

    def server_clock(self):
        print("Asking server for Unix time")

        # Creates a queue to store the time
        time_storage = self.wrapper.init_time()

        # Sets up a request for unix time from the Eclient
        self.reqCurrentTime()
        # Specifies a max wait time if there is no connection
        max_wait_time = 10

        try:
            requested_time = time_storage.get(timeout=max_wait_time)
        except queue.Empty:
            print("The queue was empty or max time reached")
            requested_time = None

        while self.wrapper.is_error():
            print("Error:")
            print(self.get_error(timeout=5))

        return requested_time


class TestApp(TestWrapper, TestClient):
    #Intializes our main classes
    def __init__(self, ipaddress, portid, clientid, timeout=20):
        TestWrapper.__init__(self)
        TestClient.__init__(self, wrapper=self)
        self.timeout = timeout
        self.ipaddress = ipaddress
        self.portid = portid
        self.clientid = clientid

        #Connects to the server with the ipaddress, portid, and clientId specified in the program execution area
        self.connect(ipaddress, portid, clientid)

        #Initializes the threading
        thread = Thread(target=self.run)
        thread.start()
        setattr(self, "_thread", thread)

        #Starts listening for errors
        self.init_error()

        self.current_req_id_tracker = 0

    def error(self, id, errorCode, errorString, advancedOrderRejectJson=""):
        if str(errorCode)[0] != "2":
            errormessage = "IB returns an error with reqid %d errorcode %d that says %s" % (id, errorCode, errorString)
            print(errormessage)
            self.my_errors_queue.put(errormessage)
            if int(errorCode) == 1100 or int(errorCode) == 504:  # 1100: Connectivity between InteractiveBrokers and TWS has been lost
                self._reconnect()
                return
            # raise Exception(errormessage)

    def _reconnect(self):
        self.connect(self.ipaddress, self.portid, self.clientid)

    def _get_next_req_id(self):
        self.current_req_id_tracker += 1
        return self.current_req_id_tracker

    def get_klines(self, contract, endDateTime, durationStr, barSizeSetting, whatToShow="TRADES", useRTH=0, formatDate=2, keepUpToDate=False, chartOptions=None):
        if chartOptions is None:
            chartOptions = []
        request_id = self._get_next_req_id()
        self.reqHistoricalData(request_id, contract=contract, endDateTime=endDateTime, durationStr=durationStr,
                               barSizeSetting=barSizeSetting, whatToShow=whatToShow, useRTH=useRTH, formatDate=formatDate,
                               keepUpToDate=keepUpToDate, chartOptions=chartOptions)
        klines_list = []
        time.sleep(1)  # needed to wait for any error messages that might come up in the error queue. Perhaps there is a better solution?
        try:
            while True:
                # check error queue if there has been an error for this call
                if self.is_error():
                    error_msg = self.get_error(self.timeout)
                    if f"reqid {request_id} " in error_msg:
                        raise Exception(error_msg)
                    else:
                        print(f"get_klines looked at a not related error_msg '{error_msg}'. Placing back in error queue")
                        self.my_errors_queue.put(error_msg)
                requested_kline = self.currently_receiving_klines_queue.get(timeout=360)
                if requested_kline is False:
                    # hard coded in EWrapper historicalDataEnd override so if boolean False appears we are end of data
                    break
                klines_list.append(requested_kline)
            return klines_list
        except queue.Empty:
            raise Exception("get_klines failed, the queue was empty or max time reached")


if __name__ == '__main__':
    test_contract = Contract()
    test_contract.exchange = "LSE"
    test_contract.secType = "STK"

    contract = Contract()
    contract.symbol = "ROO"
    contract.secType = "STK"
    contract.currency = "GBP"
    contract.exchange = "SMART"
    contract.primaryExchange = "LSE"

    def london_stock_contract(symbol):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.currency = "GBP"
        contract.exchange = "SMART"
        contract.primaryExchange = "LSE"
        return contract

    def us_stock_contract(symbol):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.currency = "USD"
        contract.exchange = "SMART"
        # contract.primaryExchange = "ARCA"
        return contract

    uc = UniversalClient("GATE")
    stocks = [us_stock_contract(x[0]) for x in uc.logger.readcsv('us_stocks.csv')[1:]]

    # Specifies that we are on local host with port 7497 (paper trading port number)
    app = TestApp("127.0.0.1", 4002, 0)

    # A printout to show the program began
    print("The program has begun")

    #assigning the return from our clock method to a variable
    requested_time = app.server_clock()

    #printing the return from the server
    print("This is the current time from the server ")
    print(requested_time)

    # Optional disconnect. If keeping an open connection to the input don't disconnet
    # app.disconnect()

    queryTime = (datetime.today() - timedelta(days=0)).strftime("%Y%m%d-%H:%M:%S")
    # k = app.get_klines(contract, endDateTime=queryTime, durationStr="1 M", barSizeSetting="1 day", whatToShow="TRADES", useRTH=0, formatDate=2, keepUpToDate=False, chartOptions=[])

    def manual_download_ib_klines(contract):
        formatted_candles = []
        k = app.get_klines(contract, endDateTime=queryTime, durationStr="3 M", barSizeSetting="1 min", whatToShow="TRADES", useRTH=0, formatDate=2, keepUpToDate=False, chartOptions=[])
        print(f'k {k}')
        for kline in k:
            new_candle = [int(kline.date) * 1000, format_float_in_standard_form(kline.open),
                          format_float_in_standard_form(kline.high), format_float_in_standard_form(kline.low),
                          format_float_in_standard_form(kline.close), format_float_in_standard_form(kline.volume),
                          int(kline.date) * 1000 + int(60 * 1000) - 1,
                          format_float_in_standard_form(kline.close * float(kline.volume))]
            formatted_candles.append(new_candle)
        uc = UniversalClient("GATE")
        uc.logger.writecsvlines(lines=formatted_candles, path=f"klines/IB/{contract.symbol}/{contract.symbol}_1m.csv")
        return formatted_candles

    for stock in stocks:
        if exists(f"klines/IB/{stock.symbol}/{stock.symbol}_1m.csv"):
            print(f'skipping {stock.symbol}')
            continue
        print(f'downloading {stock.symbol}')
        try:

            manual_download_ib_klines(stock)
        except Exception as e:
            print(f'exception {e}')
            continue
