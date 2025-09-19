"""Normalized order conversion helpers used by UniversalClient."""
from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from gate_api import FuturesOrder, FuturesPriceTriggeredOrder

from trading_automation.core.Utils import (
    format_float_in_standard_form,
    round_interval_nearest,
)

if TYPE_CHECKING:
    from trading_automation.clients.UniversalClient import UniversalClient


def process_ftx_order_to_binance(order: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize an FTX order payload to the Binance-style structure."""
    if not order:
        return None
    if 'triggerPrice' in order:
        if order['status'] == 'open':
            status = "NEW"
        elif order['status'] == 'cancelled':
            status = "CANCELLED"
        elif order['filledSize'] == order['size']:
            status = "FILLED"
        elif order['status'] == 'triggered':
            status = "PARTIALLY_FILLED"
        clientOrderId = None
        price = format_float_in_standard_form(order['orderPrice'])
    else:
        if order['status'] == 'new' or (order['status'] == 'open' and order['filledSize'] == 0):
            status = "NEW"
        elif order['remainingSize'] == 0 and order['filledSize'] == order['size'] and order['status'] == 'closed':
            status = "FILLED"
        elif order['filledSize'] > 0 and order['remainingSize'] > 0 and order['status'] == 'open':
            status = "PARTIALLY_FILLED"
        else:
            status = "EXPIRED"
        clientOrderId = order['clientId']
        price = format_float_in_standard_form(order['price'])
    return {
        "clientOrderId": clientOrderId,
        "orderId": order['id'],
        "symbol": order['market'],
        "price": price,
        "side": order['side'].upper(),
        "type": order['type'].upper(),
        "status": status,
        "reduceOnly": order['reduceOnly'],
        "origQty": format_float_in_standard_form(order['size']),
        "avgPrice": format_float_in_standard_form(order['avgFillPrice']),
        "executedQty": format_float_in_standard_form(order['filledSize']),
    }


def process_okex_order_to_binance(client: 'UniversalClient', order: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    if order['state'] == 'effective' or order['state'] == 'filled':
        status = "FILLED"
    elif order['state'] == 'partially_filled':
        status = "PARTIALLY_FILLED"
    elif order['state'] == 'canceled' or order['state'] == 'cancelled':
        status = "CANCELLED"
    elif order['state'] == 'live':
        status = "NEW"
    else:
        status = "EXPIRED"
    if 'algoId' in order and order['algoId'] != '':
        clientOrderId = ''
        orderId = order['algoId']
        price = order['ordPx']
        executedQty = str(Decimal(order['actualSz']) * client.precisionQuantityDict[order['instId']])
        if order['slOrdPx'] == '-1' or order['tpOrdPx'] == '-1':
            ordType = client.ORDER_TYPE_STOP_MARKET
        else:
            ordType = client.ORDER_TYPE_STOP
        avgPrice = order['actualPx']
    else:
        clientOrderId = order['clOrdId']
        orderId = order['ordId']
        price = order['px']
        executedQty = str(Decimal(order['accFillSz']) * client.precisionQuantityDict[order['instId']])
        if order['ordType'] == 'market':
            ordType = client.ORDER_TYPE_MARKET
        else:
            ordType = client.ORDER_TYPE_LIMIT
        avgPrice = order['avgPx']
    symbol = order['instId']
    if client.okex_pos_mode == 'long/short':
        if (order['side'] == 'buy' and order['posSide'] == 'long') or (order['side'] == 'sell' and order['posSide'] == 'short'):
            reduceOnly = False
        else:
            reduceOnly = True
    else:
        if orderId in client.reduce_only_orders.keys():
            reduceOnly = True
        else:
            reduceOnly = False
        current_time = int(time.time())
        to_delete = []
        for oid, added_time in client.reduce_only_orders.items():
            if added_time < current_time - 172800:
                to_delete.append(oid)
        for oid in to_delete:
            client.reduce_only_orders.pop(oid)
    if 'USDT' in symbol:
        origQty = str(Decimal(order['sz']) * client.precisionQuantityDict[symbol])
    elif order['ordType'] == 'limit' or order['type'] == 'post_only':
        origQty = str((Decimal(order['sz']) * client.precisionQuantityDict[symbol]) / Decimal(price))
    elif order['ordType'] == 'market':
        origQty = str((Decimal(order['sz']) * client.precisionQuantityDict[symbol]) / Decimal(avgPrice))
    return {
        "clientOrderId": clientOrderId,
        "orderId": orderId,
        "symbol": symbol,
        "price": price,
        "side": order['side'].upper(),
        "type": ordType,
        "status": status,
        "reduceOnly": reduceOnly,
        "origQty": origQty,
        "avgPrice": avgPrice,
        "executedQty": executedQty,
    }


def process_gate_order_to_binance(client: 'UniversalClient', order: Optional[Any]) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    if isinstance(order, FuturesOrder):
        clientOrderId = order.text
        orderId = order.id
        symbol = order.contract
        price = order.price
        origQty = str(abs(Decimal(order.size) * client.precisionQuantityDict[symbol]))
        side = client.SIDE_BUY if int(order.size) > 0 else client.SIDE_SELL
        ordType = client.ORDER_TYPE_LIMIT if Decimal(price) != 0 else client.ORDER_TYPE_MARKET
        if order.status == 'open':
            if 0 < abs(order.left) < abs(order.size):
                status = 'PARTIALLY_FILLED'
            else:
                status = 'NEW'
        elif order.status == 'finished':
            if order.finish_as == 'filled':
                status = 'FILLED'
            elif order.finish_as == 'cancelled':
                status = 'CANCELLED'
            else:
                status = 'EXPIRED'
        else:
            status = 'EXPIRED'
        reduceOnly = order.is_reduce_only
        executedQty = str(Decimal(abs(order.size) - abs(order.left)) * client.precisionQuantityDict[symbol])
        avgPrice = order.fill_price
        return {
            "clientOrderId": clientOrderId,
            "orderId": orderId,
            "symbol": symbol,
            "price": price,
            "side": side,
            "type": ordType,
            "status": status,
            "reduceOnly": reduceOnly,
            "origQty": origQty,
            "avgPrice": avgPrice,
            "executedQty": executedQty,
        }
    if isinstance(order, FuturesPriceTriggeredOrder):
        orderId = order.id
        symbol = order.initial['contract']
        price = order.initial['price']
        origQty = str(abs(Decimal(order.initial['size']) * client.precisionQuantityDict[symbol]))
        side = client.SIDE_BUY if int(order.initial['size']) > 0 else client.SIDE_SELL
        ordType = client.ORDER_TYPE_STOP if Decimal(price) != 0 else client.ORDER_TYPE_STOP_MARKET
        if order.status == 'open':
            status = 'NEW'
        elif order.status == 'finished':
            if order.finish_as == 'succeeded':
                status = 'FILLED'
            elif order.finish_as == 'cancelled':
                status = 'CANCELLED'
            else:
                status = 'EXPIRED'
        else:
            status = 'EXPIRED'
        reduceOnly = order.initial['is_reduce_only']
        avgPrice = None
        executedQty = None
        return {
            "clientOrderId": orderId,
            "orderId": orderId,
            "symbol": symbol,
            "price": price,
            "side": side,
            "type": ordType,
            "status": status,
            "reduceOnly": reduceOnly,
            "origQty": origQty,
            "avgPrice": avgPrice,
            "executedQty": executedQty,
        }
    return None


def process_mexc_order_to_binance(client: 'UniversalClient', order: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    clientOrderId = order['externalOid']
    orderId = order['orderId']
    symbol = order['symbol']
    price = format_float_in_standard_form(order['price'])
    if order['side'] == 1:
        side = client.SIDE_BUY
        reduceOnly = False
    elif order['side'] == 2:
        side = client.SIDE_BUY
        reduceOnly = True
    elif order['side'] == 3:
        side = client.SIDE_SELL
        reduceOnly = False
    elif order['side'] == 4:
        side = client.SIDE_SELL
        reduceOnly = True
    else:
        side = client.SIDE_BUY
        reduceOnly = False
    if order['orderType'] == 1 or order['orderType'] == 2:
        ordType = client.ORDER_TYPE_LIMIT
    elif order['orderType'] == 5:
        ordType = client.ORDER_TYPE_MARKET
    else:
        ordType = client.ORDER_TYPE_LIMIT
    if order['state'] == 1:
        status = 'NEW'
    elif order['state'] == 2:
        status = 'NEW'
    elif order['state'] == 3:
        status = 'FILLED'
    elif order['state'] == 4:
        status = 'CANCELLED'
    elif order['state'] == 5:
        status = 'EXPIRED'
    else:
        status = 'EXPIRED'
    origQty = abs(Decimal(str(order['vol'])) * client.precisionQuantityDict[symbol])
    avgPrice = order['dealAvgPrice']
    executedQty = abs(Decimal(str(order['dealVol'])) * client.precisionQuantityDict[symbol])
    if origQty > executedQty > 0:
        status = 'PARTIALLY_FILLED'
    return {
        "clientOrderId": clientOrderId,
        "orderId": orderId,
        "symbol": symbol,
        "price": price,
        "side": side,
        "type": ordType,
        "status": status,
        "reduceOnly": reduceOnly,
        "origQty": str(origQty),
        "avgPrice": str(avgPrice),
        "executedQty": str(executedQty),
    }


def process_bybit_order_to_binance(client: 'UniversalClient', order: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    clientOrderId = order['orderLinkId']
    orderId = order['orderId']
    symbol = order['symbol']
    price = str(order['price'])
    side = order['side'].upper()
    ordType = order['orderType'].upper()
    status = order['orderStatus'].upper()
    if status == 'PARTIALLYFILLED':
        status = 'PARTIALLY_FILLED'
    elif status == 'REJECTED':
        status = 'EXPIRED'
    elif status == 'PENDINGCANCEL' or status == 'CREATED':
        status = 'NEW'
    reduceOnly = order['reduceOnly']
    origQty = order['qty']
    if order['cumExecQty'] == '0':
        avgPrice = 0
    else:
        avgPrice = round_interval_nearest(
            Decimal(str(order['cumExecValue'])) / Decimal(str(order['cumExecQty'])),
            client.precisionPriceDict[symbol],
        )
    executedQty = order['cumExecQty']
    return {
        "clientOrderId": clientOrderId,
        "orderId": orderId,
        "symbol": symbol,
        "price": price,
        "side": side,
        "type": ordType,
        "status": status,
        "reduceOnly": reduceOnly,
        "origQty": str(origQty),
        "avgPrice": str(avgPrice),
        "executedQty": str(executedQty),
    }


def process_phemex_order_to_binance(client: 'UniversalClient', order: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    if order['ordStatus'] in {'New', 'Untriggered', 'Created'}:
        status = 'NEW'
    elif order['ordStatus'] == 'PartiallyFilled':
        status = 'PARTIALLY_FILLED'
    elif order['ordStatus'] == 'Filled':
        status = 'FILLED'
    elif order['ordStatus'] == 'Canceled':
        status = 'CANCELLED'
    elif order['ordStatus'] == 'Rejected':
        status = 'EXPIRED'
    elif order['ordStatus'] == 'Triggered':
        status = 'FILLED'
    else:
        raise Exception(f"process_phemex_order_to_binance unknown order status '{order['ordStatus']}'")
    if 'price' in order and order['price'] is not None:
        price = format_float_in_standard_form(order['price'])
    else:
        price = format_float_in_standard_form(Decimal(str(order['priceEp'])) * Decimal('0.0001'))
    order_type_string = 'orderType' if 'orderType' in order else 'ordType'
    if 'reduceOnly' in order:
        reduceOnly = order['reduceOnly']
    elif 'execInst' in order and order['execInst'] == 'ReduceOnly':
        reduceOnly = True
    else:
        reduceOnly = False
    symbol = order['symbol']
    if order[order_type_string] in ('Market', 'MarketByValue'):
        ordType = client.ORDER_TYPE_MARKET
    elif order[order_type_string] == 'LimitIfTouched':
        ordType = client.ORDER_TYPE_STOP
    elif order[order_type_string] == 'Stop':
        ordType = client.ORDER_TYPE_STOP_MARKET
    else:
        ordType = client.ORDER_TYPE_LIMIT
    orderQty = Decimal(str(order['orderQty']))
    qty_precision = client.precisionQuantityDict[symbol]
    origQty = orderQty * qty_precision
    cumQty = Decimal(str(order['cumQty'])) * qty_precision
    avgPrice = Decimal(str(order['avgPx'])) if 'avgPx' in order else Decimal('0')
    executedQty = cumQty
    if origQty > executedQty > 0:
        status = 'PARTIALLY_FILLED'
    return {
        "clientOrderId": order['clOrdID'] if 'clOrdID' in order else order.get('clOrdId'),
        "orderId": order['orderID'] if 'orderID' in order else order['orderId'],
        "symbol": symbol,
        "price": str(price),
        "side": order['side'].upper(),
        "type": ordType,
        "status": status,
        "reduceOnly": reduceOnly,
        "origQty": str(origQty),
        "avgPrice": str(avgPrice),
        "executedQty": str(executedQty),
    }



def process_bingx_order_to_binance(client: 'UniversalClient', order: Optional[Dict[str, Any]], symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    if isinstance(order, list):
        order = order[0]
    resolved_symbol = symbol or order.get('symbol') or order.get('symbolName')

    raw_status = order.get('status')
    if raw_status is not None:
        status_map = {
            'Pending': 'NEW',
            'PartiallyFilled': 'PARTIALLY_FILLED',
            'Filled': 'FILLED',
            'Cancelled': 'CANCELLED',
            'Failed': 'EXPIRED',
        }
        status = status_map.get(str(raw_status), 'EXPIRED')
    else:
        filled_volume = Decimal(str(order.get('filledVolume', order.get('executedQty', order.get('executedVolume', 0)) or 0)))
        status = 'PARTIALLY_FILLED' if filled_volume > 0 else 'NEW'

    price = order.get('entrustPrice', order.get('price', order.get('avgPrice', 0)))
    reduce_only = order.get('reduceOnly')
    if reduce_only is None:
        action = order.get('action')
        reduce_only = bool(action and str(action).lower() == 'close')

    side_raw = order.get('side', '')
    if isinstance(side_raw, str):
        side_map = {'bid': 'BUY', 'ask': 'SELL'}
        side = side_map.get(side_raw.lower(), side_raw.upper())
    else:
        side = str(side_raw).upper()

    ord_type_raw = order.get('tradeType', order.get('origType', order.get('type', '')))
    ord_type = ord_type_raw.upper() if isinstance(ord_type_raw, str) else str(ord_type_raw)

    orig_qty = order.get('entrustVolume', order.get('origQty', order.get('qty', 0)))
    avg_price = order.get('avgFilledPrice', order.get('avgPrice', price))
    executed_qty = order.get('filledVolume', order.get('executedQty', order.get('executedVolume', 0)))

    def _format(value):
        if isinstance(value, (float, int, Decimal)):
            return str(format_float_in_standard_form(value))
        return str(value)

    return {
        'clientOrderId': order.get('clientOrderId'),
        'orderId': order.get('orderId'),
        'symbol': resolved_symbol,
        'price': _format(price),
        'side': side,
        'type': ord_type,
        'status': status,
        'reduceOnly': reduce_only,
        'origQty': _format(orig_qty),
        'avgPrice': _format(avg_price),
        'executedQty': _format(executed_qty),
    }


