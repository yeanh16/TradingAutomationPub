import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from trading_automation.core.Utils import *
from time import sleep
from datetime import datetime
from binance.streams import BinanceSocketManager
from trading_automation.core.Logger import Logger

logger = Logger(client=None, logpath="logs/arbitrage.txt")
assets = ["BTC", "ETH", "XRP", "USDT", "LTC", "BCH", "LINK", "ADA", "DOT", "BNB", "EOS", "ETC", "XMR", "DASH", "UNI",
          "TRX", "XLM", "NEO", "YFI", "ZEC", "AAVE", "COMP", "SUSHI", "VET", "BUSD","EGLD","UNFI","IOST","ZIL","SKL",
          "HARD", "ROSE", "DNT", "CVC", "WBTC", "VIA","LTO","AE","THETA","PNT","ALGO","REP","OMG","CRV","ATOM","XTZ",
          "BEL","SXP","AKRO","RUNE","VIDT","IRIS","SNX","YFII","RSR","OCEAN","MANA","DIA"]
obts = get_symbol_order_book_tickers()
FEE = 0.1 * 0.01

# order book ticker web socket
symbolDict = {} # for better efficiency use a dict with the symbols as keys with the info condensed in an array as the values
for obt in obts:
    key = obt.get("symbol")
    value = [float(obt.get("bidPrice")), float(obt.get("bidQty")), float(obt.get("askPrice")), float(obt.get("askQty"))]
    symbolDict[key] = value


def process_message(msg):
    global symbolDict
    symbol = msg.get('s')
    bbp = msg.get('b')
    bbq = msg.get('B')
    bap = msg.get('a')
    baq = msg.get('A')
    symbolDict[symbol] = [bbp, bbq, bap, baq]


bm = BinanceSocketManager(client)
conn_key = bm.start_book_ticker_socket(process_message)
bm.start()
# order book ticker web socket END


def update_obts():
    get_symbol_order_book_tickers()


def get_symbol_from_obts(symbol):
    return [obt for obt in obts if obt.get('symbol') == symbol]


def get_symbol_from_symbolDict(symbol, symbolDictSnapshot=None):
    try:
        if not symbolDictSnapshot:
            values = symbolDict[symbol]
        else:
            values = symbolDictSnapshot[symbol]
    except KeyError:
        return None
    return [{"bidPrice": values[0], "bidQty": values[1], "askPrice": values[2], "askQty": values[3]}]


def exchange(amount, asset_1, asset_2, symbolDictSnapshot=None):
    """
    returns what would amount of asset_1 would get for asset_2
    :param symbolDictSnapshot:
    :param amount:
    :param asset_1:
    :param asset_2:
    :return:
    """
    if not asset_1 or not asset_2 or not amount:
        return 0
    forwards = get_symbol_from_symbolDict(asset_1+asset_2, symbolDictSnapshot=symbolDictSnapshot)
    backwards = get_symbol_from_symbolDict(asset_2+asset_1, symbolDictSnapshot=symbolDictSnapshot)
    if forwards:
        bidPrice = float(forwards[0].get('bidPrice'))
        return amount * bidPrice
    elif backwards:
        askPrice = Decimal(backwards[0].get('askPrice'))
        if askPrice:
            return float(Decimal(amount) / askPrice)

    return 0


def get_exchange_rate(asset_1, asset_2, symbolDictSnapshot=None):
    """
    :param amount:
    :param asset_1:
    :param asset_2:
    :param symbolDictSnapshot:
    :return: exchangeRate, buy/sell
    """
    if not asset_1 or not asset_2:
        return 0
    forwards = get_symbol_from_symbolDict(asset_1+asset_2, symbolDictSnapshot=symbolDictSnapshot)
    backwards = get_symbol_from_symbolDict(asset_2+asset_1, symbolDictSnapshot=symbolDictSnapshot)
    if forwards:
        bidPrice = float(forwards[0].get('bidPrice'))
        return bidPrice, "sell"
    elif backwards:
        askPrice = float(backwards[0].get('askPrice'))
        if askPrice:
            return askPrice, "buy"
    return 0


def triangle_arbitrage(baseAsset, amount):
    symbolDictSnapshot = symbolDict
    firstPass = {}
    for asset in assets:
        if asset == baseAsset:
            continue
        exchangeVal = exchange(amount, baseAsset, asset, symbolDictSnapshot)
        if exchangeVal:
            firstPass[asset] = exchangeVal * (1-FEE)

    secondPass = {}
    for symbol, value in firstPass.items():
        for asset in assets:
            if asset == symbol or asset == baseAsset:
                continue
            exchangeVal = exchange(value, symbol, asset, symbolDictSnapshot)
            if exchangeVal:
                secondPass[symbol+'/'+asset] = exchangeVal * (1-FEE)

    lastPass = {}
    for symbol, value in secondPass.items():
        lastAsset = symbol.split('/')[1]
        finalValue = exchange(value, lastAsset, baseAsset, symbolDictSnapshot) * (1-FEE)
        if finalValue > amount:
            exchangeRate1, action1 = get_exchange_rate(baseAsset, symbol.split('/')[0], symbolDictSnapshot)
            exchangeRate2, action2 = get_exchange_rate(symbol.split('/')[0], symbol.split('/')[1], symbolDictSnapshot)
            exchangeRate3, action3 = get_exchange_rate(symbol.split('/')[1], baseAsset, symbolDictSnapshot)
            logger.writeline(
                f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} {baseAsset} -> {action1} {symbol.split('/')[0]} @ {exchangeRate1}  "
                f"-> {action2} {symbol.split('/')[1]} @ {exchangeRate2}  -> {action3} {baseAsset} @ {exchangeRate3}")
            lastPass[symbol] = finalValue
    #print(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} done")
    return lastPass


while True:
    try:
        opportunities = triangle_arbitrage("USDT", 10000)
        if opportunities:
            logger.writeline(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} {opportunities}")
    except Exception as e:
        print(e)
        pass

#a = triangle_arbitrage("USDT", 10000)

# for asset in assets:
#     print(f"19000 USDT would get {exchange(19000, 'USDT', asset)} of {asset}")
