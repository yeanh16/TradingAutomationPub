import os
import sys
import threading
import traceback
from typing import Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from pytz import utc

from trading_automation.clients.DiscordClient import DiscordNotificationService
from trading_automation.clients.UniversalClient import UniversalClient
from trading_automation.config.settings import get_settings
from trading_automation.core.UniversalClientWebsocket import UniversalClientWebsocket
from trading_automation.core.Utils import *

settings = get_settings()
CLOSE_BEST_PRICE_MIN_VALUE = settings.close_best_price_min_value
UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS = settings.unrealised_pnl_drawdown_to_stop_new_orders
UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS_BYBIT = settings.unrealised_pnl_drawdown_to_stop_new_orders_bybit
ABNORMAL_VOLUME_SPIKE_MULTIPLIER_THRESHOLD = settings.abnormal_volume_spike_multiplier_threshold
ABNORMAL_VOLUME_SPIKE_AVERAGE_NUMBER_OF_DAYS = settings.abnormal_volume_spike_average_number_of_days
DISCORD_CHANNEL_ID = settings.discord_channel_id or 0
DISCORD_TERMINATIONS_CHANNEL_ID = settings.discord_terminations_channel_id or 0
DISCORD_SKIPPING_ORDERS_CHANNEL_ID = settings.discord_skipping_orders_channel_id or 0
DISCORD_ERROR_MESSAGES_CHANNEL_ID = settings.discord_error_messages_channel_id or 0
BTC_PRICE_UPPER_BOUND = settings.btc_price_upper_bound
BTC_PRICE_LOWER_BOUND = settings.btc_price_lower_bound
RANGE_LIMIT_DAYS = 21
VOLATILITY_LIMIT = 25  # percentage of change within 1 hour to stop orders


class FuturesFlushBuyManager(threading.Thread):

    def __init__(self, symbol, flushPercent, numberOfFlushBars, exitLookbackBars,
                 interval=UniversalClient.KLINE_INTERVAL_5MINUTE, shorts=False, squeezePercent=0, quantity=None,
                 fixedBalance=None, balancePercent=0, maxDrawdownPercentage=None, maxSingleTradeLossPercentage=0,
                 recalcOnFill=False, stopLossPercentageLong=0, stopLossPercentageShort=0, softSLPercentage=0, softSLN=0,
                 postOnly=False, takeProfitPercentage=0, blocking=False, stopLossTermination=False, minBalance=0,
                 closePartialFills=False, avoidMarketEntries=False, exchange="BINANCE", maxNumOfPositions=0, close_position_only=False,
                 volumeBasedPosSize=False, ignore_abnormal_volume=False, discord_service: Optional[DiscordNotificationService] = None, argfilename=None,
                 phemex_input_q=None, phemex_output_q=None, reverse_mode=False, shortsPositionMultiplier=1.0):
        """
        :param symbol:
        :param flushPercent:
        :param numberOfFlushBars:
        :param exitLookbackBars:
        :param interval:
        :param shorts:
        :param squeezePercent:
        :param quantity:
        :param fixedBalance:
        :param balancePercent:
        :param maxDrawdownPercentage:
        :param recalcOnFill:
        :param stopLossPercentageLong:
        :param stopLossPercentageShort:
        :param softSLPercentage:
        :param softSLN:
        :param takeProfitPercentage:
        :param stopLossTermination:
        :param minBalance:
        :param closePartialFills:
        :param postOnly: Makes it so that all limit orders at entry are post only so that limit orders are never
                        executed immediately. Any invalid orders are set to expired.
        :param blocking: Use blocking scheduler?
        :param avoidMarketEntries: If a limit entry order would become a market entry order because of current price,
                                   avoidMarketEntries will make sure that the entry order will be at the bid/ask instead
                                   . postOnly and avoidMarketEntries needs to me mutually exclusive because postOnly
                                   implies that the order should be cancelled if it is a market order (and not altered
                                   to be at bid/ask like avoidMarketEntries does)
        :param shortsPositionMultiplier: multiply any short position sizes made by this value
        """
        threading.Thread.__init__(self)
        if (quantity and balancePercent) or (quantity and fixedBalance) or (balancePercent and fixedBalance) or \
                (not quantity and not balancePercent and not fixedBalance):
            print("ERROR: Only specify one of quantity, balancePercent or fixedBalance!")
            exit(2)
        self.argfilename = argfilename
        self.volumeBasedPosSize = volumeBasedPosSize
        self.exchange = exchange
        self.symbol = symbol
        self.flushPercent = input_to_percentage(flushPercent)
        self.numberOfFlushBars = numberOfFlushBars  # + 1  # api call counts the current bar as 1 so need to get 1 more
        self.exitLookbackBars = exitLookbackBars  # + 1
        self.interval = interval
        self.shorts = shorts
        self.softSLN = softSLN
        self.client = UniversalClientWebsocket(self.exchange, self.symbol, self.interval,
                                               candles_limit=max(self.numberOfFlushBars, self.softSLN,
                                                                 self.exitLookbackBars) + 1, discord_service=discord_service,
                                               phemex_input_q=phemex_input_q, phemex_output_q=phemex_output_q)
        self.logger = self.client.logger
        self.sql_log_trades = False
        if self.shorts and squeezePercent:
            self.squeezePercent = input_to_percentage(squeezePercent)
        elif self.shorts and not squeezePercent:
            print("squeezePercent value needed!")
            exit(2)
        else:
            self.squeezePercent = 0
        if quantity and quantity > 0:
            self.quantity = quantity
        else:
            self.quantity = None
        # recalculate_on_fill is equivalent to "Recalculate on order fills" on tradingview, this makes it so that
        # there is always an order made after a position is exited in the middle of a candle
        self.recalcOnFill = recalcOnFill
        self.maxNumOfPositions = maxNumOfPositions
        self.currentBuyOrder = self.get_open_current_buy_order()
        self.currentSellOrder = self.get_open_current_sell_order()
        if stopLossPercentageLong:
            self.stopLossPercentageLong = input_to_percentage(stopLossPercentageLong)
        else:
            self.stopLossPercentageLong = 0
        if stopLossPercentageShort:
            self.stopLossPercentageShort = input_to_percentage(stopLossPercentageShort)
        else:
            self.stopLossPercentageShort = 0
        self.postOnly = postOnly
        if self.postOnly:
            self.avoidMarketEntries = False
            # postOnly and avoidMarketEntries needs to me mutually exclusive because postOnly
            # implies that the order should be cancelled if it is a market order (and not altered
            # to be at bid/ask like avoidMarketEntries does)
        else:
            self.avoidMarketEntries = avoidMarketEntries
        self.ignore_abnormal_volume = ignore_abnormal_volume
        self.reverse_mode = reverse_mode
        self.RANGE_LIMIT_DAYS = RANGE_LIMIT_DAYS
        # Special case for CAPITAL, we usually want certain params so hardcoding this in
        if "CAPITAL" in self.exchange:
            self.volumeBasedPosSize = False
            self.reverse_mode = True
            self.ignore_abnormal_volume = True
        if self.reverse_mode:  # range limit was designed to not create orders against breakouts but reverse mode sometimes trades breakouts or momentum
            self.RANGE_LIMIT_DAYS = 0
        if takeProfitPercentage:
            self.takeProfitPercentage = input_to_percentage(takeProfitPercentage)
        else:
            self.takeProfitPercentage = 0
        if fixedBalance and fixedBalance > 0:
            self.fixedBalance = fixedBalance
        else:
            self.fixedBalance = None
        self.blocking = blocking
        if balancePercent:
            self.balancePercent = input_to_percentage(balancePercent)
        else:
            self.balancePercent = 0
        if maxSingleTradeLossPercentage:
            self.maxSingleTradeLossPercentage = input_to_percentage(maxSingleTradeLossPercentage)
        else:
            self.maxSingleTradeLossPercentage = None
        self.stopLossOrder = None
        if softSLPercentage:
            self.softSLPercentage = input_to_percentage(softSLPercentage)
        else:
            self.softSLPercentage = 0
        if softSLPercentage and not softSLN:
            print("ERROR: If using soft stop loss need to specify softSLN!")
            exit(2)
        if self.blocking:
            self.scheduler = BlockingScheduler(executors={'default': ThreadPoolExecutor(1)}, timezone=utc)
        else:
            self.scheduler = BackgroundScheduler(executors={'default': ThreadPoolExecutor(1)}, timezone=utc)
        self.currentPosition = self.client.position
        self.maxDrawdownPercentage = min(input_to_percentage(maxDrawdownPercentage), 1.0) if maxDrawdownPercentage is not None else 1.0
        internal_wallet_stored_values = self.logger.get_internal_wallet_balance_and_drawdown_value_and_last_trade_id(str(self))
        if internal_wallet_stored_values:
            self.internal_wallet = internal_wallet_stored_values[0]  # Used to calculate the drawdown of this running strat
            self.maxDrawdownValue = internal_wallet_stored_values[1]
            # keep track of what trade id record to update when closing trades
            self.trade_id_tracker = None if get_position_size(self.currentPosition) == 0 else internal_wallet_stored_values[2]
            # Note: If the maxDrawdownPercentage has changed since last run, then the maxDrawdownValue may not be accurate
        else:
            self.internal_wallet = 100
            self.maxDrawdownValue = self.internal_wallet * (1 - self.maxDrawdownPercentage)
            self.logger.log_internal_wallet(str(self), self.internal_wallet, self.maxDrawdownValue)
            self.trade_id_tracker = None
        self.stopLossTermination = stopLossTermination
        self.minBalance = minBalance
        self.closePartialFills = closePartialFills
        self.unrealised_pnl_drawdown_to_stop_new_orders = UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS if "BYBIT" not in self.exchange else UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS_BYBIT
        # set below to 'True' whenever on TV we have exited the position but have not in live trading
        # use to track how often after a bar finishes we are not able to exit the position as in the strategy
        # may also be used in the future to know when to force close a position before the bar finishes to match TV
        self.exceeded_profit_still_in_position = False
        # set below to 'True' when an at bid/ask post only order is made for an entry and we are
        # waiting for it to be filled. Used to track success rate of at bid/ask post only entries
        self.at_bidask_post_only_entry_attempt = False
        # below values used to track draw-downs
        self.entryPrice = get_entry_price(self.currentPosition)
        self.full_pos_qty = abs(get_position_size(self.currentPosition))  # what the peak position size was for current trade, should always be positive
        self.current_partial_filled_order = None  # used to keep track of when partial filled orders need updating
        self.close_position_only = close_position_only
        self.shortsPositionMultiplier = shortsPositionMultiplier
        self.btcpricelowerbound = BTC_PRICE_LOWER_BOUND
        self.btcpriceupperbound = BTC_PRICE_UPPER_BOUND

        self.market_currently_open_flag = True
        if "CAPITAL" in self.exchange:
            market_status = self.client.client_capital.get_market(self.symbol)['snapshot']['marketStatus']
            self.market_currently_open_flag = False if market_status == "CLOSED" or market_status == "SUSPENDED" else True

    def __str__(self):
        return f"{self.exchange} {self.symbol} {self.interval} {percentage_to_input(self.flushPercent)} {percentage_to_input(self.squeezePercent)} {self.numberOfFlushBars} {self.exitLookbackBars} {percentage_to_input(self.stopLossPercentageLong)} {percentage_to_input(self.stopLossPercentageShort)} {percentage_to_input(self.softSLPercentage)} {self.softSLN} {percentage_to_input(self.takeProfitPercentage)}"

    def stop(self):
        self.cancel_all_orders()
        self.client.futures_close_best_price(self.symbol, CLOSE_BEST_PRICE_MIN_VALUE,
                                             self.client.get_position_api_first())
        self.logger.writeline(f"{self.symbol} Exiting Program...")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        sys.exit(0)

    def get_open_current_buy_order(self):
        self.currentBuyOrder = self.client.futures_get_open_buy_limit_orders(self.symbol)
        if self.currentBuyOrder:
            self.currentBuyOrder = self.currentBuyOrder[0]
        return self.currentBuyOrder

    def get_open_current_sell_order(self):
        self.currentSellOrder = self.client.futures_get_open_sell_limit_orders(self.symbol)
        if self.currentSellOrder:
            self.currentSellOrder = self.currentSellOrder[0]
        return self.currentSellOrder

    def soft_stop_loss_check(self, position, entryPrice):
        """
        Checks if the close price has remained past the stop loss threshold for self.softSLN number of bars. If so
        then we need to exit the position. The idea behind this method is to prevent losses from stop loss hunting.
        position: bool for position direction, True for long
        :returns True if the closing price has remained past threshold for self.softSLN number of bars
        """
        if 0.0 < self.softSLPercentage < 1.0:
            # candles = futures_get_candlesticks(symbol=self.symbol, limit=self.softSLN,
            #                                   interval=self.interval)
            candles = self.client.get_candlesticks_api_first(self.softSLN)
            if position is True:
                threshold = round_interval_nearest(entryPrice * (1 - self.softSLPercentage),
                                                   self.client.precisionPriceDict.get(self.symbol))
                self.logger.writeline(f"{self.symbol} soft SL @{threshold}")
                for candle in reversed(candles):
                    if threshold < float(candle[4]):
                        return False
            else:
                threshold = round_interval_nearest(entryPrice * (1 + self.softSLPercentage),
                                                   self.client.precisionPriceDict.get(self.symbol))
                self.logger.writeline(f"{self.symbol} soft SL @{threshold}")
                for candle in reversed(candles):
                    if threshold > float(candle[4]):
                        return False

            self.logger.writeline(f"{self.symbol} Soft stop loss condition met. Closing position...")
            self.client.futures_close_best_price(self.symbol, CLOSE_BEST_PRICE_MIN_VALUE,
                                                 self.client.get_position_api_first())
            # TODO: sql trade logging and maxDrawdownPercentage check on positions closed by soft stop loss mechanism
            if self.stopLossTermination or (
                    self.maxSingleTradeLossPercentage and (self.maxSingleTradeLossPercentage <= self.softSLPercentage)):
                self.stop()
            return True
        return False

    def log_entry_trade(self, order=None):
        """
        Provide an order in cases when partial filled or to log a post only entry attempt.
        If no order is provided, assume that client.get_position_api_first() is sufficient to log trade
        :param order:
        :return:
        """
        if not self.sql_log_trades:
            return
        try:
            if order and is_order_filled_partial(order):
                if not self.trade_id_tracker and not self.at_bidask_post_only_entry_attempt:
                    # log new trade from partial filled order
                    self.trade_id_tracker = self.logger.write_new_trade(str(self), order=order)
                elif not self.trade_id_tracker and self.at_bidask_post_only_entry_attempt:
                    # log new trade from a post only partial filled order
                    self.trade_id_tracker = self.logger.write_new_trade(str(self), order=order, post_only_entry=True)
                elif self.trade_id_tracker or (self.trade_id_tracker and self.at_bidask_post_only_entry_attempt):
                    # update (post only) trade from a partial filled order (but use position to update table)
                    self.logger.update_trade_entry(self.trade_id_tracker,
                                                   position=self.client.get_position_api_first()[0])
            elif order and is_order_filled(
                    order) and not self.trade_id_tracker and self.at_bidask_post_only_entry_attempt:
                # log new post only entry trade
                self.trade_id_tracker = self.logger.write_new_trade(str(self), position=
                self.client.get_position_api_first()[0], post_only_entry=True)
            elif order and self.at_bidask_post_only_entry_attempt and not self.trade_id_tracker:
                # log new post only entry attempt
                self.trade_id_tracker = self.logger.write_new_trade(str(self), order=order, post_only_entry=True)

            # below assumes that entry order has been filled and we can get info from position
            if not order:
                if self.trade_id_tracker:
                    # update entry from position
                    self.logger.update_trade_entry(self.trade_id_tracker,
                                                   position=self.client.get_position_api_first()[0])
                elif not self.trade_id_tracker:
                    # log new trade triggered normally
                    self.trade_id_tracker = self.logger.write_new_trade(str(self), position=
                                                                        self.client.get_position_api_first()[0])
        except Exception as e:
            self.logger.writeline(f"{self.symbol} ERROR: log_entry_trade {e} \n {traceback.format_exc()}")

    def log_exit_trade(self, order=None, position=None, increase_post_only_exit_count=False,
                       increase_post_only_exit_failed_count=False):
        """
        updates a trade with exit information
        if order is provided, we can update table with this information
        also responsible for increasing counts:
            increase_post_only_exit_count,
            increase_post_only_exit_failed_count
        when these booleans are provided
        if increase_post_only_exit_count, advise to also provide position
        :param order:
        :param position:
        :param increase_post_only_exit_count:
        :return:
        """
        if not self.sql_log_trades:
            return
        try:
            if increase_post_only_exit_count:
                # increase the count (will log the actual order only when it gets filled)
                self.logger.increase_post_only_exit_count(self.trade_id_tracker, position)
                return
            if increase_post_only_exit_failed_count:
                self.logger.increase_post_only_exit_failed_count(self.trade_id_tracker)
                return
            if order and self.trade_id_tracker:
                self.logger.close_trade_update(self.trade_id_tracker, order)
                if is_order_filled(order):
                    self.trade_id_tracker = None
            else:
                self.logger.writeline(f"{self.symbol} WARNING: trade logger unable to complete a trade!")
                self.logger.trades_log_failed_entry(self.symbol)
        except Exception as e:
            self.logger.writeline(f"{self.symbol} ERROR: log_exit_trade {e} \n {traceback.format_exc()}")

    def check_filled(self):
        """
        checks if any order has been filled at all
        If using long & short this function needs to cancel the other leg if one order is (partially) filled
        :return: if an order has been filled
        """
        # Special case, for CAPITAL exchange, we cannot get past filled/cancelled orders, only active (unfilled) ones
        if "CAPITAL" in self.exchange:
            previously_known_position = self.currentPosition
            previous_position_size = get_position_size(previously_known_position)
            current_position = self.client.get_position_api_first()
            current_position_size = get_position_size(current_position)
            if previous_position_size == current_position_size:
                return
            current_open_orders = self.client.futures_get_open_orders(symbol=self.symbol)
            if previous_position_size == 0:
                if current_position_size > 0:
                    if [x for x in current_open_orders if x['side'] == "BUY"]:
                        self.logger.writeline(f"{self.symbol} Buy entry order partially filled current pos size {current_position_size}", discord_channel_id=DISCORD_CHANNEL_ID)
                    else:
                        self.logger.writeline(f"{self.symbol} Buy entry order filled for {current_position_size} @{current_position[0]['entryPrice']} (${round(Decimal(current_position_size) * Decimal(current_position[0]['entryPrice']),3)})", discord_channel_id=DISCORD_CHANNEL_ID)
                    self.client.futures_cancel_open_sell_orders(symbol=self.symbol)
                    self.currentSellOrder = None
                elif current_position_size < 0:
                    if [x for x in current_open_orders if x['side'] == "SELL"]:
                        self.logger.writeline(f"{self.symbol} Sell entry order partially filled current pos size {current_position_size}", discord_channel_id=DISCORD_CHANNEL_ID)
                    else:
                        self.logger.writeline(f"{self.symbol} Sell entry order filled for {abs(current_position_size)} @{current_position[0]['entryPrice']} (${round(abs(Decimal(current_position_size)) * Decimal(current_position[0]['entryPrice']),3)})", discord_channel_id=DISCORD_CHANNEL_ID)
                    self.client.futures_cancel_open_buy_orders(symbol=self.symbol)
                    self.currentBuyOrder = None
            elif previous_position_size > 0:
                if current_position_size == 0:
                    self.logger.writeline(f"{self.symbol} long position closed", discord_channel_id=DISCORD_CHANNEL_ID)
                elif abs(current_position_size) < abs(previous_position_size):
                    self.logger.writeline(f"{self.symbol} long position partial exit", discord_channel_id=DISCORD_CHANNEL_ID)
                elif current_position_size < 0:
                    self.logger.writeline(f"{self.symbol} WARNING long position flipped?", discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
            elif previous_position_size < 0:
                if current_position_size == 0:
                    self.logger.writeline(f"{self.symbol} short position closed", discord_channel_id=DISCORD_CHANNEL_ID)
                elif abs(current_position_size) < abs(previous_position_size):
                    self.logger.writeline(f"{self.symbol} short position partial exit", discord_channel_id=DISCORD_CHANNEL_ID)
                elif current_position_size > 0:
                    self.logger.writeline(f"{self.symbol} WARNING short position flipped?", discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)

            self.currentPosition = current_position
            return

        buy_filled = False
        buy_filled_partial = False
        sell_filled = False
        sell_filled_partial = False
        stop_loss_filled = False
        # check stop loss order
        if self.stopLossOrder:
            sl_order = self.client.get_order_api_first(self.stopLossOrder.get('orderId'))
            if sl_order and is_order_filled(sl_order):
                self.logger.writeline(f"Stop loss order hit for {self.symbol}")
                stop_loss_filled = True
                self.log_exit_trade(sl_order)
                stop_loss_percentage_lost = self.stopLossPercentageShort if get_order_side(sl_order) == "BUY" else self.stopLossPercentageLong
                self.internal_wallet = self.internal_wallet * (1 - stop_loss_percentage_lost)
                self.logger.log_internal_wallet(str(self), self.internal_wallet, self.maxDrawdownValue)
                if self.internal_wallet < self.maxDrawdownValue:
                    self.logger.writeline(f"{self.symbol} maxDrawdownPercentage exceeded, exiting program")
                    self.stop()
                if self.maxSingleTradeLossPercentage and self.maxSingleTradeLossPercentage <= stop_loss_percentage_lost:
                    self.logger.writeline(f"{self.symbol} maxSingleTradeLossPercentage exceeded, exiting program")
                    self.stop()
                if self.stopLossTermination:
                    self.stop()
                self.stopLossOrder = None

        if self.currentBuyOrder:
            buy_order = self.client.get_order_api_first(self.currentBuyOrder['orderId'])
            buy_filled = is_order_filled(buy_order)
            buy_filled_partial = is_order_filled_partial(buy_order)

        if self.currentSellOrder:
            sell_order = self.client.get_order_api_first(self.currentSellOrder['orderId'])
            sell_filled = is_order_filled(sell_order)
            sell_filled_partial = is_order_filled_partial(sell_order)

        if buy_filled:
            if not buy_order.get('reduceOnly'):
                self.logger.writeline(
                    f"{self.symbol} Buy entry order {buy_order.get('orderId')} filled @{buy_order.get('avgPrice')} (${round(float(buy_order.get('avgPrice')) * float(buy_order.get('origQty')), 3)})")
                self.entryPrice = buy_order.get('avgPrice')
                self.at_bidask_post_only_entry_attempt = False
                self.log_entry_trade()
            else:
                self.log_exit_trade(buy_order)
                exit_price = buy_order.get('avgPrice')
                pnl_percentage = calculate_pnl_percentage(self.entryPrice, exit_price, "short")
                self.logger.writeline(
                    f"{self.symbol} Buy exit order {buy_order.get('orderId')} filled @{exit_price} (${round(float(exit_price) * self.full_pos_qty, 3)}, gain: ${round((float(self.entryPrice) - float(exit_price)) * self.full_pos_qty, 3)}, pnl%: {round(pnl_percentage*100,2)})", discord_channel_id=DISCORD_CHANNEL_ID)
                self.internal_wallet = self.internal_wallet * (1 + pnl_percentage)
                new_drawdown = self.internal_wallet * (1 - self.maxDrawdownPercentage)
                if new_drawdown > self.maxDrawdownValue:
                    self.maxDrawdownValue = new_drawdown
                self.logger.log_internal_wallet(str(self), self.internal_wallet, self.maxDrawdownValue)
                if self.internal_wallet < self.maxDrawdownValue:
                    self.logger.writeline(f"{self.symbol} Max drawdown reached")
                    self.stop()
                # check if realised loss is greater than maxSingleTradeLossPercentage
                if self.maxSingleTradeLossPercentage and pnl_percentage < -self.maxSingleTradeLossPercentage:
                    self.logger.writeline(
                        f"{self.symbol} maxSingleTradeLossPercentage drawdown exceeded, exiting program")
                    self.stop()
                if self.exceeded_profit_still_in_position:
                    self.exceeded_profit_still_in_position = False
                self.entryPrice = 0
            self.currentBuyOrder = None

        elif sell_filled:
            if not sell_order.get('reduceOnly'):
                self.logger.writeline(
                    f"{self.symbol} Sell entry order {sell_order.get('orderId')} filled @{sell_order.get('avgPrice')} (${round(float(sell_order.get('avgPrice')) * float(sell_order.get('origQty')), 3)})")
                self.entryPrice = sell_order.get('avgPrice')
                self.at_bidask_post_only_entry_attempt = False
                self.log_entry_trade()
            else:
                self.log_exit_trade(sell_order)
                exit_price = sell_order.get('avgPrice')
                pnl_percentage = calculate_pnl_percentage(self.entryPrice, exit_price, "long")
                self.logger.writeline(
                    f"{self.symbol} Sell exit order {sell_order.get('orderId')} filled @{exit_price} (${round(float(exit_price) * self.full_pos_qty, 3)}, gain: ${round((float(exit_price) - float(self.entryPrice)) * self.full_pos_qty, 3)}, pnl%: {round(pnl_percentage*100,2)})", discord_channel_id=DISCORD_CHANNEL_ID)
                self.internal_wallet = self.internal_wallet * (1 + pnl_percentage)
                new_drawdown = self.internal_wallet * (1 - self.maxDrawdownPercentage)
                if new_drawdown > self.maxDrawdownValue:
                    self.maxDrawdownValue = new_drawdown
                self.logger.log_internal_wallet(str(self), self.internal_wallet, self.maxDrawdownValue)
                if self.internal_wallet < self.maxDrawdownValue:
                    self.logger.writeline(f"{self.symbol} Max drawdown reached")
                    self.stop()
                # check if realised loss is greater than maxSingleTradeLossPercentage
                if self.maxSingleTradeLossPercentage and pnl_percentage < -self.maxSingleTradeLossPercentage:
                    self.logger.writeline(
                        f"{self.symbol} maxSingleTradeLossPercentage exceeded, exiting program")
                    self.stop()
                if self.exceeded_profit_still_in_position:
                    self.exceeded_profit_still_in_position = False
                self.entryPrice = 0
            self.currentSellOrder = None

        elif buy_filled_partial and self.current_partial_filled_order != buy_order:
            if not buy_order.get('reduceOnly'):
                self.logger.writeline(
                    f"{self.symbol} Buy entry order {buy_order.get('orderId')} partial fill {buy_order.get('executedQty')}/{buy_order.get('origQty')}")
                self.entryPrice = buy_order.get('avgPrice')
                self.current_partial_filled_order = buy_order
                self.log_entry_trade(buy_order)
            elif buy_order.get('reduceOnly'):
                self.logger.writeline(
                    f"{self.symbol} Buy exit order {buy_order.get('orderId')} partial fill {buy_order.get('executedQty')}/{buy_order.get('origQty')}")
                self.current_partial_filled_order = buy_order
                self.log_exit_trade(buy_order)
                if self.closePartialFills:
                    self.logger.writeline(f"Exit limit order only partially filled, exiting position fully... ")
                    self.client.futures_close_best_price(self.symbol, CLOSE_BEST_PRICE_MIN_VALUE,
                                                         self.client.get_position_api_first())
        elif sell_filled_partial and self.current_partial_filled_order != sell_order:
            if not sell_order.get('reduceOnly'):
                self.logger.writeline(
                    f"{self.symbol} Sell entry order {sell_order.get('orderId')} partial fill {sell_order.get('executedQty')}/{sell_order.get('origQty')}")
                self.entryPrice = sell_order.get('avgPrice')
                self.current_partial_filled_order = sell_order
                self.log_entry_trade(sell_order)
            elif sell_order.get('reduceOnly'):
                self.logger.writeline(
                    f"{self.symbol} Sell exit order {sell_order.get('orderId')} partial fill {sell_order.get('executedQty')}/{sell_order.get('origQty')}")
                self.current_partial_filled_order = sell_order
                self.log_exit_trade(sell_order)
                if self.closePartialFills:
                    self.logger.writeline(f"Exit limit order only partially filled, exiting position fully... ")
                    self.client.futures_close_best_price(self.symbol, CLOSE_BEST_PRICE_MIN_VALUE,
                                                         self.client.get_position_api_first())

        if (buy_filled or buy_filled_partial) and self.currentSellOrder:
            self.client.futures_cancel_order(self.symbol, self.currentSellOrder.get('orderId'))
            self.currentSellOrder = None

        if (sell_filled or sell_filled_partial) and self.currentBuyOrder:
            self.client.futures_cancel_order(self.symbol, self.currentBuyOrder.get('orderId'))
            self.currentBuyOrder = None

        return buy_filled or sell_filled or stop_loss_filled

    def max_positions_check(self, all_positions=None, wallet_balance=None):
        """
        If there is a position open for current strategy, always return True
        :return: True if max positions size + pending order sizes is not reached
        """
        if self.maxNumOfPositions == 0:
            return True

        if all_positions is None:
            all_positions = self.client.futures_get_position()
        if wallet_balance is None:
            wallet_balance = float(self.client.futures_get_total_balance())

        position = [x for x in all_positions if x['symbol'] == self.symbol]
        position_sizes_sum = float(sum([Decimal(x['entryPrice']) * abs(Decimal(x['positionAmt'])) for x in all_positions]))
        max_positions_size = self.maxNumOfPositions * float(wallet_balance)

        # if over position sizes limit pause all strats
        if position_sizes_sum * 0.99 > max_positions_size and not self.close_position_only:
            self.logger.writeline(f"WARNING: {self.exchange} currently has over the set limit account size positions opened! changing to close only mode, reactivate manually! {self.symbol} position: {position} wallet_balance: {wallet_balance} postion_sizes_sum: {position_sizes_sum}", discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
            self.close_position_only = True
            if position and position_sizes_sum > ((self.maxNumOfPositions + 1) * wallet_balance):
                # if we have a position and the total position size is +1 bigger than set limit assume that
                # there is a big market crash event and more positions opened than planned so we market close position for safety
                self.logger.writeline(
                    f"WARNING: {self.exchange} currently has over the set limit ({self.maxNumOfPositions}+1) of ({position_sizes_sum / float(wallet_balance)}) account size positions opened! market closing {self.symbol} position for safety!",
                    discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                self.client.futures_close_position(symbol=self.symbol)

        # need to add in the potential of if the current buy/sell orders being filled will make the max positions size
        # check to be over
        buy_order_size, sell_order_size = 0, 0
        if self.currentBuyOrder:
            buy_order = self.currentBuyOrder  # self.client.get_order_api_first(self.currentBuyOrder['orderId'])
            buy_order_size = abs(Decimal(buy_order['origQty'])) * Decimal(buy_order['price'])
        if self.currentSellOrder:
            sell_order = self.currentSellOrder  # self.client.get_order_api_first(self.currentSellOrder['orderId'])
            sell_order_size = abs(Decimal(sell_order['origQty'])) * Decimal(sell_order['price'])
        potential_order_size_usd = float(max(buy_order_size, sell_order_size)) * 0.98

        if position:
            # check if there are pending orders that will increase the position size over the limit and cancel them
            position_side_is_long = False if position[0]['positionAmt'][0] == '-' else True
            position_size = float(Decimal(position[0]['entryPrice']) * abs(Decimal(position[0]['positionAmt'])))
            if (position_side_is_long and buy_order_size > 0 and (position_sizes_sum - position_size) + float(buy_order_size) * 0.99 > max_positions_size) or \
                    (not position_side_is_long and sell_order_size > 0 and (position_sizes_sum - position_size) + float(sell_order_size) * 0.99 > max_positions_size):
                self.logger.writeline(
                    f"WARNING: {self.exchange} {self.symbol} open orders would increase current position over the set limit of max positions size, cancelling pending orders. current positions sum {position_sizes_sum}",
                    discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                self.cancel_all_orders()
            return True

        total_position_size_usd = potential_order_size_usd + position_sizes_sum
        if total_position_size_usd >= max_positions_size:
            return False
        else:
            return True

    def regular_check(self):
        """
        Function that should be run regularly to check orders and positions. Is where recalcOnFill is also implemented.
        recalcOnFill: used to match behavior seen on tradingview when recalculating, the current candle is included
        """
        try:
            filled = self.check_filled()
            if self.recalcOnFill:
                if filled:
                    self.set_orders()
                elif not self.client.futures_get_open_orders(self.symbol):  # TODO: if using recalc on fill with websockets
                    self.logger.writeline(f"{self.symbol} Creating new orders")
                    self.set_orders()
            if self.maxNumOfPositions > 0:
                all_positions = self.client.futures_get_position()
                maxPosCheckFlag = self.max_positions_check(all_positions=all_positions)
                if not maxPosCheckFlag and (self.currentBuyOrder or self.currentSellOrder):
                    self.logger.writeline(f"{self.symbol} Max positions sizes detected, cancelling pending orders for this strategy")
                    self.cancel_all_orders()
                # If the following section is to be added, need to figure a way to only place orders when a position hasn't
                # been closed recently in the interval (so not to replicate recalc on fill unnecessarily
                # elif maxPosCheckFlag and (self.currentBuyOrder is None and self.currentSellOrder is None) and get_position_size(current_position) == 0:
                #     self.logger.writeline(f"{self.symbol} Position limit not reached, placing orders")
                #     self.set_orders()
            # if self.currentBuyOrder is not None or self.currentSellOrder is not None:
            #     position = self.client.get_position_api_first() if current_position is None else current_position
            #     positionSize = get_position_size(position)
            #     if positionSize == 0:
            #         equity = float(self.client.futures_get_balance())
            #         wallet_balance = float(self.client.futures_get_total_balance())
            #         if equity < wallet_balance * (1 - self.unrealised_pnl_drawdown_to_stop_new_orders*0.01):
            #             self.logger.writeline(f"{self.symbol} Cancelling open orders as max unrealised balance drawdown reached", discord_channel_id=DISCORD_SKIPPING_ORDERS_CHANNEL_ID)
            #             self.cancel_all_orders()
            if "CAPITAL" in self.exchange:
                # check for duplicate orders and cancel them
                orders = self.client.futures_get_open_orders(self.symbol)
                duplicate_orders = []
                for order in orders:
                    rest = [x['price'] for x in orders if x['side'] == order['side'] and Decimal(x['origQty']) == Decimal(order['origQty'])]
                    rest.remove(order['price'])
                    if Decimal(order['price']) in [Decimal(x) for x in rest]:
                        if Decimal(order['price']) not in [Decimal(x['price']) for x in duplicate_orders]:
                            duplicate_orders.append(order)
                for duplicate_order in duplicate_orders:
                    self.logger.writeline(f"Found duplicate order {duplicate_order}", discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                    self.client.futures_cancel_order(symbol=self.symbol, orderID=duplicate_order['orderId'])
            # check env file for changes to the BTC range
            envfile = open('.env', 'r')
            for line in envfile.readlines():
                r = re.search(r'BTC_PRICE_LOWER_BOUND = (\d*.?\d*)', line.strip())
                if r:
                    lowerbound = float(r.group(1))
                    self.btcpricelowerbound = lowerbound
                r = re.search(r'BTC_PRICE_UPPER_BOUND = (\d*.?\d*)', line.strip())
                if r:
                    upperbound = float(r.group(1))
                    self.btcpriceupperbound = upperbound
            envfile.close()
            if self.btcpricelowerbound > 0 and self.btcpricelowerbound > 0 and self.close_position_only is False:
                btc_exchange_names = [n for n in self.client.precisionPriceDict.keys() if "BTC" in n]
                if len(btc_exchange_names) == 1:
                    btc_exchange_name = btc_exchange_names[0]
                else:
                    # put exchanges with multiple 'BTC' symbol entries here and specify which one is used
                    if "BYBIT" in self.client.exchange:
                        btc_exchange_name = "BTCUSDT"
                    else:
                        raise Exception(f"Need to specify the BTC symbol name on this exchange {self.exchange}")
                btc_price = self.client.futures_get_symbol_price(btc_exchange_name)
                if btc_price > self.btcpriceupperbound or btc_price < self.btcpricelowerbound:
                    self.logger.writeline(f"BTC price {btc_price} is outside of bounds [{self.btcpricelowerbound}, {self.btcpriceupperbound}]! {self.exchange} {self.symbol} changing to close only mode", discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                    self.close_position_only = True
                    position = self.client.futures_get_position(self.symbol)
                    positionSize = get_position_size(position)
                    if positionSize == 0:
                        self.cancel_all_orders()
                        
        except Exception as e:
            self.logger.writeline(f"{self.symbol} ERROR unable to run regular check {e}")

    def cancel_all_orders(self):
        self.client.futures_cancel_all_orders(self.symbol)
        self.currentBuyOrder = None
        self.currentSellOrder = None
        self.stopLossOrder = None

    def set_orders(self):
        """
        Function that sets orders.
        """
        all_positions = self.client.futures_get_position()
        position = [x for x in all_positions if x['symbol'] == self.symbol]
        if not position:
            # sometimes BYBIT when getting all positions would not get specific symbols even though
            # there is an open position open for it so need to specify it just in case
            position = self.client.futures_get_position(self.symbol)
            if not position:
                position = [{"entryPrice": '0',
                            "positionAmt": '0', "symbol": self.symbol,
                            "unRealizedProfit": '0'}]
        positionSize = get_position_size(position)
        # check local arglist files to see if optionals such as close_position_only has changed
        if self.argfilename is not None:
            # check for changes in master arglist file first
            runfile = open('arglist.txt', 'r')
            for line in runfile.readlines():
                r = re.search(ARG_FILE_REGEX, line.strip())
                if r and self.argfilename == r.group(1):
                    if r.group(2):
                        self.close_position_only = True if '-x' in r.group(2) else False
                        self.ignore_abnormal_volume = True if '-n' in r.group(2) else False
                        if '-f' in r.group(2):
                            self.logger.writeline(f"{self.symbol} force closing FuturesManager...",
                                                  discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                            self.client.futures_close_best_price(symbol=self.symbol)
                            sys.exit(0)
                        if '-w' in r.group(2):
                            self.logger.writeline(f"{self.symbol} waiting...")
                            return
                    break
            runfile.close()
            # TODO: check for changes in individual arg files

        if self.close_position_only and positionSize == 0:
            self.stop()
        equity = float(self.client.futures_get_balance())
        wallet_balance = float(self.client.futures_get_total_balance())
        max_size_remaining = 0.0
        if self.maxNumOfPositions > 0:
            if not self.max_positions_check(all_positions=all_positions, wallet_balance=wallet_balance):
                self.logger.writeline(f"{self.symbol} Skipping placing orders as max positions sizes reached")
                self.cancel_all_orders()
                return
            total_position_size_usd = sum([Decimal(x['entryPrice']) * abs(Decimal(x['positionAmt'])) for x in all_positions])
            max_size = wallet_balance * self.maxNumOfPositions
            max_size_remaining = Decimal(str(max_size)) - Decimal(str(total_position_size_usd))
        if positionSize == 0:
            if equity < wallet_balance * (1 - self.unrealised_pnl_drawdown_to_stop_new_orders * 0.01):
                self.logger.writeline(
                    f"{self.symbol} Skipping placing orders as max unrealised balance drawdown reached",
                    discord_channel_id=DISCORD_SKIPPING_ORDERS_CHANNEL_ID)
                self.cancel_all_orders()
                return
        if not self.ignore_abnormal_volume and ABNORMAL_VOLUME_SPIKE_MULTIPLIER_THRESHOLD > 0 and not self.close_position_only and self.client.abnormal_volume_check(
                symbol=self.symbol,
                abnormal_volume_spike_average_number_of_days=ABNORMAL_VOLUME_SPIKE_AVERAGE_NUMBER_OF_DAYS,
                abnormal_volume_spike_multiplier_threshold=ABNORMAL_VOLUME_SPIKE_MULTIPLIER_THRESHOLD):
            if positionSize == 0:
                self.logger.writeline(f"{self.symbol} Abnormal volume detected, stopping...",
                                      discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                self.stop()
            else:
                self.close_position_only = True
                self.logger.writeline(
                    f"{self.symbol} Abnormal volume detected, once position is closed, stopping...",
                    discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
        try:
            # volatility check
            if self.interval == "1m":
                number_of_volatility_candles_needed_to_check = 60
            elif self.interval == "2m":
                number_of_volatility_candles_needed_to_check = 30
            elif self.interval == "5m":
                number_of_volatility_candles_needed_to_check = 12
            else:
                raise Exception("number_of_volatility_candles_needed_to_check not defined in FuturesManager.py, need to add for this interval!")

            candles = self.client.get_candlesticks_api_first(max(self.numberOfFlushBars,
                                                                 self.exitLookbackBars, number_of_volatility_candles_needed_to_check) + 1)

            if not candles:
                self.logger.writeline(f"ERROR set_order: {self.symbol} Unable to get candles!")
                return

            # volatility check
            highest_price = max(Decimal(candle[2]) for candle in candles)
            lowest_price = min(Decimal(candle[3]) for candle in candles)
            long_change = calculate_pnl_percentage(lowest_price, highest_price, 'long') * 100
            short_change = calculate_pnl_percentage(highest_price, lowest_price, 'short') * 100
            if max(long_change, short_change) > VOLATILITY_LIMIT:
                if positionSize == 0:
                    self.logger.writeline(f"{self.symbol} volatility more than {VOLATILITY_LIMIT}% past hour, stopping",
                                          discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                    self.stop()
                elif positionSize != 0 and self.close_position_only is False:
                    self.logger.writeline(f"WARNING: {self.symbol} volatility more than {VOLATILITY_LIMIT}% past hour with an open position! Monitor this position, stopping after position is closed naturally",
                                          discord_channel_id=DISCORD_TERMINATIONS_CHANNEL_ID)
                    self.close_position_only = True

            if isinstance(candles, tuple):
                ask_bid_candles = True
            else:
                ask_bid_candles = False
            # set_orders running after interval: check if the latest candle is past interval - if so then we need to
            # truncate this candle. If not then we need to truncate the first candle since it's unneeded
            if not ask_bid_candles:
                latest_candle_open_time = int(candles[-1][0])
            else:
                latest_candle_open_time = int(candles[0][-1][0])
            if latest_candle_open_time + binance_intervals_to_seconds(self.interval) * 1000 > int(
                    time.time() * 1000):
                if not ask_bid_candles:
                    candles = candles[:-1]
                else:
                    candles = (candles[0][:-1], candles[1][:-1])
            else:
                if not ask_bid_candles:
                    candles = candles[1:]
                else:
                    candles = (candles[0][1:], candles[1][1:])

            def get_current_price(order_side_is_buy: bool = True):
                """
                Used mainly for CFDs. On normal markets just return last traded price.
                On CFDs, returns current price depending on what the intended order action needs.
                e.g. if we are looking to BUY then we need to know what the current ASK price is to buy from or
                to know if the order would become a market order to avoid.
                :return:
                no ask bid candles:
                -> last traded price (last kline close)
                ask bid candles:
                order_side_is_buy -> ASK_PRICE
                !order_side_is_buy -> BID_PIRCE
                """
                if not ask_bid_candles:
                    return Decimal(str(get_last_close_price_from_candles(candles)))
                else:
                    ask_price = candles[1][-1][4]
                    bid_price = candles[0][-1][4]
                    if order_side_is_buy:
                        return Decimal(ask_price)
                    else:
                        return Decimal(bid_price)

            def get_orderbook_side_for_order_side(order_side_is_buy: bool = True):
                """
                When trading CFDs, if we wish to place an order at the best bid/ask we place aggressively on the other
                side when compared to normal trading because CFD brokers takes spread so if we place order on other
                usual side of orderbook, we are unlikely to get filled straight away unlike in normal trading when
                placing at the best bid/ask chances are even to be filled straight away.
                Examples:
                    when not using ask_bid_candles (normal trading):
                        order_side_is_buy -> we place BUY order on the BID side with the highest BID price
                        order_side_is_sell -> we place SELL order on the ASK side with the lowest ASK price
                    when using ask_bid_candles (CFD trading):
                        order_side_is_buy -> we place BUY order on the ASK side with the lost ASK price
                        order_side_is_sell -> we place SELL order on the BID side with the highest BID price
                :return: orderbook_side: str, atBid: bool, atAsk: bool
                """
                if (not ask_bid_candles and order_side_is_buy) or (ask_bid_candles and not order_side_is_buy):
                    return "BID", True, False
                else:
                    return "ASK", False, True

            self.check_filled()
            if not position:
                self.logger.writeline(f"ERROR set_order: {self.symbol} Unable to get position!")
                return
            # check if we were looking to exit last candle but failed
            if self.exceeded_profit_still_in_position:
                self.logger.writeline(f"WARNING: {self.symbol} did not manage to exit position")
                self.exceeded_profit_still_in_position = False
                self.log_exit_trade(increase_post_only_exit_failed_count=True)
            if positionSize == 0:
                if not self.market_currently_open_flag:
                    self.cancel_all_orders()
                    return
                self.full_pos_qty = 0
                # check if we were looking to enter last candle but failed
                if self.at_bidask_post_only_entry_attempt:
                    self.logger.writeline(f"WARNING: {self.symbol} did not manage to enter position")
                    self.at_bidask_post_only_entry_attempt = False
                    if self.sql_log_trades:
                        self.logger.update_last_trade_id(self.trade_id_tracker, None)
                    self.trade_id_tracker = None
                if not ask_bid_candles:
                    candlesEntry = candles[
                                   -self.numberOfFlushBars:]  # get the last numberOfFlushBars candles from candles
                else:
                    candlesEntry = (candles[0][-self.numberOfFlushBars:], candles[1][-self.numberOfFlushBars:])
                self.cancel_all_orders()
                # check that cancelled orders have not created a position before creating new ones
                if get_position_size(self.client.get_position_api_first()) != 0:
                    self.logger.writeline(
                        f"{self.symbol} WARNING: Attempt to cancel orders but a position was created")
                    self.log_entry_trade()
                    self.set_orders()
                    return
                if float(wallet_balance) < self.minBalance:
                    self.logger.writeline(f"{self.symbol} Balance is below min threshold")
                    self.stop()
                if not ask_bid_candles:
                    highestEntry = max(Decimal(candle[2]) for candle in candlesEntry)
                    lowestEntry = min(Decimal(candle[3]) for candle in candlesEntry)
                else:
                    highestEntry = max(Decimal(candle[2]) for candle in candlesEntry[1])  # look at ask prices to determine the high price to BUY from when flushing
                    lowestEntry = min(Decimal(candle[3]) for candle in candlesEntry[0])
                if self.numberOfFlushBars == 0:
                    flushEntry = get_current_price(order_side_is_buy=True) * (1 - Decimal(str(self.flushPercent)))
                    squeezeEntry = get_current_price(order_side_is_buy=False) * (1 + Decimal(str(self.squeezePercent)))
                else:
                    flushEntry = highestEntry * (1 - Decimal(str(self.flushPercent)))
                    squeezeEntry = lowestEntry * (1 + Decimal(str(self.squeezePercent)))
                if self.reverse_mode:
                    temp = flushEntry
                    flushEntry = squeezeEntry
                    squeezeEntry = temp
                range_limit_buy_flag = True
                range_limit_sell_flag = True
                if self.RANGE_LIMIT_DAYS > 0:
                    daily_candles = self.client.futures_klines(symbol=self.symbol, interval='1d',
                                                               limit=self.RANGE_LIMIT_DAYS)
                    if not isinstance(daily_candles, tuple):
                        upper_limit = max(max(Decimal(candle[2]) for candle in daily_candles), highestEntry)
                        lower_limit = min(min(Decimal(candle[3]) for candle in daily_candles), lowestEntry)
                    else:
                        upper_limit = max(max(Decimal(candle[2]) for candle in daily_candles[0]), highestEntry)
                        lower_limit = min(min(Decimal(candle[3]) for candle in daily_candles[1]), lowestEntry)
                    if (flushEntry < lower_limit) or (get_current_price(order_side_is_buy=True) < lower_limit):
                        range_limit_buy_flag = False
                    if (squeezeEntry > upper_limit) or (get_current_price(order_side_is_buy=False) > upper_limit):
                        range_limit_sell_flag = False
                if range_limit_buy_flag:
                    if self.reverse_mode or self.postOnly or self.avoidMarketEntries is False or get_current_price(order_side_is_buy=True) >= flushEntry:
                        if self.reverse_mode:
                            #  gap up checks so we don't enter a bigger position than expected if price gaps up
                            orderbook_ticker_info = self.client.futures_orderbook_ticker(symbol=self.symbol)
                            current_ask_price = orderbook_ticker_info['askPrice']
                            if Decimal(current_ask_price) > Decimal(flushEntry) * Decimal('1.05'):
                                self.logger.writeline(f"WARNING {self.symbol} price gapped up. Was placing buy entry order @{flushEntry} but current price @{current_ask_price}. Updating to be current price instead", discord_channel_id=DISCORD_SKIPPING_ORDERS_CHANNEL_ID)
                                flushEntry = Decimal(current_ask_price)
                        stop = None if not self.reverse_mode else flushEntry
                        self.currentBuyOrder = self.client.futures_create_limit_order(symbol=self.symbol,
                                                                                      limit=flushEntry,
                                                                                      quantity=self.quantity,
                                                                                      postOnly=self.postOnly,
                                                                                      fixedBalance=self.fixedBalance,
                                                                                      balancePercent=self.balancePercent,
                                                                                      balance=wallet_balance,
                                                                                      volume_based_max_usdt_pos_size=self.volumeBasedPosSize,
                                                                                      stop=stop,
                                                                                      side="BUY",
                                                                                      absoluteMaxUsdtPosSize=max_size_remaining)
                    elif self.avoidMarketEntries and get_current_price(order_side_is_buy=True) < flushEntry:
                        self.logger.writeline(
                            f"{self.symbol} current price {get_current_price(order_side_is_buy=True)} < {flushEntry} flushEntry, not placing any orders...", discord_channel_id=DISCORD_ERROR_MESSAGES_CHANNEL_ID)
                        # # below section is old behaviour where we create an order at bid/ask to enter market when volatity high but
                        # # is quite risky and led to a liquidation because of multiple positions opened at the same time, see 12/04/24 trading log
                        # price_entry_side, atBid, atAsk = get_orderbook_side_for_order_side(order_side_is_buy=True)
                        # self.logger.writeline(
                        #     f"{self.symbol} current price {get_current_price(order_side_is_buy=True)} < {flushEntry} flushEntry, placing buy entry order at {price_entry_side} instead...")
                        # self.currentBuyOrder = self.client.futures_create_limit_order(symbol=self.symbol,
                        #                                                               limit=flushEntry,
                        #                                                               quantity=self.quantity,
                        #                                                               postOnly=self.postOnly,
                        #                                                               fixedBalance=self.fixedBalance,
                        #                                                               balancePercent=self.balancePercent,
                        #                                                               balance=wallet_balance,
                        #                                                               atBid=atBid,
                        #                                                               atAsk=atAsk,
                        #                                                               volume_based_max_usdt_pos_size=self.volumeBasedPosSize,
                        #                                                               side="BUY",
                        #                                                               absoluteMaxUsdtPosSize=max_size_remaining)
                        # self.at_bidask_post_only_entry_attempt = True
                        # # log trade that we attempted to enter
                        # self.log_entry_trade(self.currentBuyOrder)
                        # return  # don't need to process short orders as TV assumes we are already in with a long position
                else:
                    self.logger.writeline(
                        f"{self.symbol} Skipping buy order @{min(flushEntry, get_current_price(order_side_is_buy=True))} because it falls below the {self.RANGE_LIMIT_DAYS} day range limit @{lower_limit}")
                if self.shorts:
                    if flushEntry > squeezeEntry and not self.reverse_mode:
                        self.logger.writeline(
                            f"WARNING:{self.symbol} Buy limit @ {flushEntry} > Sell limit @{squeezeEntry}), next orders will guarantee a position")
                        if flushEntry > get_current_price(order_side_is_buy=False) > squeezeEntry:
                            self.logger.writeline(
                                f"WARNING: AND flushEntry > current price @{get_current_price(order_side_is_buy=False)} > squeezeEntry! Skipping sell order...")
                            return
                            # the reason why we ignore the sell order if current price < flushEntry is because this will
                            # cause a conflict with both buy and sell orders being valid when the above is true, we pick
                            # to only go long in this case.
                    if range_limit_sell_flag:
                        if self.reverse_mode or self.postOnly or self.avoidMarketEntries is False or get_current_price(order_side_is_buy=False) <= squeezeEntry:
                            if self.reverse_mode:
                                #  gap down checks so we don't enter a smaller position than expected if price gaps down
                                current_bid_price = orderbook_ticker_info['bidPrice']
                                if Decimal(current_bid_price) < Decimal(squeezeEntry) * Decimal('0.95'):
                                    self.logger.writeline(
                                        f"WARNING {self.symbol} price gapped down. Was placing sell entry order @{squeezeEntry} but current price @{current_bid_price}. Updating to be current price instead",
                                        discord_channel_id=DISCORD_SKIPPING_ORDERS_CHANNEL_ID)
                                    squeezeEntry = Decimal(current_bid_price)
                            stop = None if not self.reverse_mode else squeezeEntry
                            self.currentSellOrder = self.client.futures_create_limit_order(symbol=self.symbol,
                                                                                           limit=squeezeEntry,
                                                                                           quantity=self.quantity,
                                                                                           postOnly=self.postOnly,
                                                                                           fixedBalance=self.fixedBalance if self.fixedBalance is None else self.fixedBalance * self.shortsPositionMultiplier,
                                                                                           balancePercent=self.balancePercent * self.shortsPositionMultiplier,
                                                                                           balance=wallet_balance,
                                                                                           volume_based_max_usdt_pos_size=self.volumeBasedPosSize,
                                                                                           stop=stop,
                                                                                           side="SELL",
                                                                                           absoluteMaxUsdtPosSize=max_size_remaining)
                        elif self.avoidMarketEntries and get_current_price(order_side_is_buy=False) > squeezeEntry:
                            self.logger.writeline(
                                f"{self.symbol} current price {get_current_price(order_side_is_buy=False)} > {squeezeEntry} squeezeEntry, skipping placing order...", discord_channel_id=DISCORD_ERROR_MESSAGES_CHANNEL_ID)
                            # price_entry_side, atBid, atAsk = get_orderbook_side_for_order_side(order_side_is_buy=False)
                            # self.logger.writeline(
                            #     f"{self.symbol} current price {get_current_price(order_side_is_buy=False)} > {squeezeEntry} squeezeEntry, placing sell entry order at {price_entry_side} instead...")
                            # # also need to cancel the above long order as TV assumes we are already in a short position
                            # self.cancel_all_orders()
                            # self.currentSellOrder = self.client.futures_create_limit_order(symbol=self.symbol,
                            #                                                                limit=squeezeEntry,
                            #                                                                quantity=self.quantity,
                            #                                                                postOnly=self.postOnly,
                            #                                                                fixedBalance=self.fixedBalance if self.fixedBalance is None else self.fixedBalance * self.shortsPositionMultiplier,
                            #                                                                balancePercent=self.balancePercent * self.shortsPositionMultiplier,
                            #                                                                balance=wallet_balance,
                            #                                                                atAsk=atAsk,
                            #                                                                atBid=atBid,
                            #                                                                volume_based_max_usdt_pos_size=self.volumeBasedPosSize,
                            #                                                                side="SELL",
                            #                                                                absoluteMaxUsdtPosSize=max_size_remaining)
                            # self.at_bidask_post_only_entry_attempt = True
                            # # log trade that we attempted to enter
                            # self.log_entry_trade(self.currentSellOrder)
                            # return
                    else:
                        self.logger.writeline(
                            f"{self.symbol} Skipping sell order @{max(squeezeEntry, get_current_price(order_side_is_buy=False))} because it's above the {self.RANGE_LIMIT_DAYS} day range limit @{upper_limit}")
        except Exception as e:
            # if there was a problem setting orders and there is no position,
            # cancel all previous orders as these would be out of date
            position = self.client.get_position_api_first()
            positionSize = get_position_size(position)
            if positionSize == 0:
                self.cancel_all_orders()
            print(f"{self.symbol} Something went wrong when placing orders \n{traceback.format_exc()}")
            return

        if positionSize > 0:
            if positionSize > self.full_pos_qty:
                self.full_pos_qty = positionSize
            entryPrice = get_entry_price(position)
            # check soft stop loss
            if self.soft_stop_loss_check(position=True, entryPrice=entryPrice):
                self.currentBuyOrder = None
                return
            if not ask_bid_candles:
                candlesLookback = candles[-self.exitLookbackBars:]
            else:
                candlesLookback = candles[0][
                                  -self.exitLookbackBars:]  # position size > 0  so we look to sell using the BID prices
            highestLookback = max(Decimal(candle[2]) for candle in candlesLookback)
            stop = None
            if self.stopLossPercentageLong:
                stop = Decimal(Decimal(str(entryPrice)) * (1 - Decimal(str(self.stopLossPercentageLong))))
            if self.takeProfitPercentage:
                limit = min(highestLookback, Decimal(
                    round_interval_up(Decimal(str(entryPrice)) * (1 + Decimal(str(self.takeProfitPercentage))),
                                      self.client.precisionPriceDict.get(self.symbol))))
            else:
                limit = highestLookback
            self.get_open_current_sell_order()
            if "CAPITAL" in self.exchange or not self.currentSellOrder or (
                    self.currentSellOrder and (Decimal(self.currentSellOrder.get("price")) != limit)) or ((abs(
                Decimal(self.currentSellOrder.get("origQty"))) - abs(
                Decimal(self.currentSellOrder.get("executedQty")))) != abs(Decimal(str(positionSize)))):
                self.cancel_all_orders()
                if not self.avoidMarketEntries or get_current_price(order_side_is_buy=False) < limit:
                    self.currentSellOrder = self.client.futures_create_limit_order(symbol=self.symbol, limit=limit,
                                                                                   quantity=positionSize,
                                                                                   reduceOnly=True, side="SELL")
                    if stop:
                        self.stopLossOrder = self.client.futures_long_stop_loss(symbol=self.symbol,
                                                                                quantity=positionSize, stop=stop)
                else:
                    # # when the current price > limit the order would normally become a market exit. Instead we use
                    # # the close_best_price function so that it becomes a limit exit
                    # self.logger.writeline(f"{self.symbol} take profit exceeded, closing at best price")
                    # futures_close_best_price(self.symbol, CLOSE_BEST_PRICE_MIN_VALUE, position=position)
                    price_entry_side, atBid, atAsk = get_orderbook_side_for_order_side(order_side_is_buy=False)
                    self.logger.writeline(
                        f"{self.symbol} long take profit (@{limit}) exceeded (current price: {get_current_price(order_side_is_buy=False)}), placing limit exit at {price_entry_side}")
                    # total, pnl, avPrice, slippage = market_close_now_profit(self.symbol, position)
                    # self.logger.writeline(
                    #     f"{self.symbol} if close at market now: total ${total} pnl {pnl}, avPrice {avPrice}, slippage {slippage}")
                    self.log_exit_trade(position=position, increase_post_only_exit_count=True)
                    self.currentSellOrder = self.client.futures_create_limit_order(symbol=self.symbol, limit=limit,
                                                                                   quantity=positionSize,
                                                                                   reduceOnly=True,
                                                                                   atAsk=atAsk,
                                                                                   atBid=atBid,
                                                                                   side="SELL")
                    self.exceeded_profit_still_in_position = True
            else:
                self.logger.writeline(f"{self.symbol} Current sell limit @{limit} exit doesnt need updating")

        if positionSize < 0:
            if abs(positionSize) > self.full_pos_qty:
                self.full_pos_qty = abs(positionSize)
            entryPrice = get_entry_price(position)
            # check soft stop loss
            if self.soft_stop_loss_check(position=False, entryPrice=entryPrice):
                self.currentSellOrder = None
                return
            if not ask_bid_candles:
                candlesLookback = candles[-self.exitLookbackBars:]
            else:
                candlesLookback = candles[1][-self.exitLookbackBars:]
            lowestLookback = min(Decimal(candle[3]) for candle in candlesLookback)
            stop = None
            if self.stopLossPercentageShort:
                stop = Decimal(Decimal(str(entryPrice)) * (1 + Decimal(str(self.stopLossPercentageShort))))
            if self.takeProfitPercentage:
                limit = max(lowestLookback, Decimal(
                    round_interval_down(Decimal(str(entryPrice)) * (1 - Decimal(str(self.takeProfitPercentage))),
                                        self.client.precisionPriceDict.get(self.symbol))))
            else:
                limit = lowestLookback
                self.get_open_current_buy_order()
            if "CAPITAL" in self.exchange or not self.currentBuyOrder or (
                    self.currentBuyOrder and (Decimal(self.currentBuyOrder.get("price")) != limit)) or ((abs(
                Decimal(self.currentBuyOrder.get("origQty"))) - abs(
                Decimal(self.currentBuyOrder.get("executedQty")))) != abs(Decimal(str(positionSize)))):
                self.cancel_all_orders()
                if not self.avoidMarketEntries or get_current_price(order_side_is_buy=True) > limit:
                    self.currentBuyOrder = self.client.futures_create_limit_order(symbol=self.symbol, limit=limit,
                                                                                  quantity=abs(positionSize),
                                                                                  reduceOnly=True, side="BUY")
                    if stop:
                        self.stopLossOrder = self.client.futures_short_stop_loss(symbol=self.symbol,
                                                                                 quantity=abs(positionSize),
                                                                                 stop=stop)
                else:
                    # self.logger.writeline(f"{self.symbol} take profit exceeded, closing at best price")
                    # futures_close_best_price(self.symbol, CLOSE_BEST_PRICE_MIN_VALUE, position=position)
                    price_entry_side, atBid, atAsk = get_orderbook_side_for_order_side(order_side_is_buy=True)
                    self.logger.writeline(
                        f"{self.symbol} short take profit (@{limit}) exceeded (current price: {get_current_price(order_side_is_buy=True)}), placing limit exit at {price_entry_side}")
                    # total, pnl, avPrice, slippage = market_close_now_profit(self.symbol, position)
                    # self.logger.writeline(
                    #     f"{self.symbol} if close at market now: total ${total} pnl {pnl}, avPrice {avPrice}, slippage {slippage}")
                    self.log_exit_trade(position=position, increase_post_only_exit_count=True)
                    self.currentBuyOrder = self.client.futures_create_limit_order(symbol=self.symbol, limit=limit,
                                                                                  quantity=abs(positionSize),
                                                                                  reduceOnly=True, atBid=atBid,
                                                                                  atAsk=atAsk,
                                                                                  side="BUY")
                    self.exceeded_profit_still_in_position = True
            else:
                self.logger.writeline(f"{self.symbol} Current buy limit @{limit} exit doesnt need updating")

    def handle_market_open_and_close_times(self, is_open: bool):
        self.market_currently_open_flag = is_open

    def run(self):
        if self.internal_wallet < self.maxDrawdownValue:
            self.logger.writeline(
                f"{self.symbol} Stored internal wallet values indicate previous drawdown exit, stopping...")
            self.stop()
        if self.close_position_only and get_position_size(self.client.get_position_api_first()) == 0:
            self.stop()

        maxDrawdownPercentStr = "None" if self.maxDrawdownPercentage == 1.0 else str(self.maxDrawdownPercentage * 100)
        maxSingleLossPercentStr = "None" if self.maxSingleTradeLossPercentage is None else str(
            self.maxSingleTradeLossPercentage * 100)
        self.logger.writeline(
            f"Running Flush Buy Manager with settings: "
            f"exchange: {self.exchange}, "
            f"interval: {self.interval}, "
            f"symbol: {self.symbol}, "
            f"flushPercent: {percentage_to_input(self.flushPercent)}, "
            f"squeezePercent: {percentage_to_input(self.squeezePercent)}, "
            f"noOfBars: {self.numberOfFlushBars}, "
            f"exitLookbackBars: {self.exitLookbackBars}, "
            f"stopLossPercentageLong: {percentage_to_input(self.stopLossPercentageLong)}, "
            f"stopLossPercentageShort: {percentage_to_input(self.stopLossPercentageShort)}, "
            f"softSLPercentage: {percentage_to_input(self.softSLPercentage)}, "
            f"softSLN: {self.softSLN}, "
            f"takeProfitPercentage: {percentage_to_input(self.takeProfitPercentage)}, "
            f"quantity: {self.quantity}, "
            f"fixedBalance: {self.fixedBalance}, "
            f"balancePercent: {percentage_to_input(self.balancePercent)}, "
            f"minBalance: {self.minBalance} ,"
            f"maxDrawdownPercent: {maxDrawdownPercentStr} ,"
            f"maxSingleTradeLossPercentage: {maxSingleLossPercentStr} ,"
            f"maxNumOfPositions: {self.maxNumOfPositions} ,"
            f"shorts: {self.shorts}, "
            f"recalcOnFill: {self.recalcOnFill}, "
            f"postOnly: {self.postOnly}, "
            f"stopLossTermination: {self.stopLossTermination}, "
            f"closePartialFills: {self.closePartialFills}, "
            f"avoidMarketEntries: {self.avoidMarketEntries},"
            f"shortsPositionMultiplier: {self.shortsPositionMultiplier}"
        )
        if self.interval == "5m":
            self.scheduler.add_job(self.set_orders, 'cron', minute='*/5', second='01')
        elif self.interval == "1m":
            self.scheduler.add_job(self.set_orders, 'cron', second='01')
        elif self.interval == "2m":
            self.scheduler.add_job(self.set_orders, 'cron', minute='*/2', second='01')
        elif self.interval == "3m":
            self.scheduler.add_job(self.set_orders, 'cron', minute='*/3', second='01')
        elif self.interval == "15m":
            self.scheduler.add_job(self.set_orders, 'cron', minute='*/15', second='01')
        elif self.interval == "1h":
            self.scheduler.add_job(self.set_orders, 'cron', hour='*/1', minute='0', second='01', misfire_grace_time=360)
        self.scheduler.add_job(self.regular_check, 'cron', second='*/5', misfire_grace_time=3)

        if "CAPITAL" in self.exchange:
            opening_times_str = self.client.client_capital.get_market(self.symbol)['instrument']['openingHours']
            opening_times_pattern = r'((([0-1]{0,1}[0-9])|(2[0-3])):[0-5]{0,1}[0-9]) -'
            closing_times_pattern = r'- ((([0-1]{0,1}[0-9])|(2[0-3])):[0-5]{0,1}[0-9])'
            opening_times_str_list = list(set([x[0] for x in re.findall(opening_times_pattern, opening_times_str)]))
            closing_times_str_list = list(set([x[0] for x in re.findall(closing_times_pattern, opening_times_str)]))
            for opening_time in opening_times_str_list:
                opening_time_hour = opening_time[:2]
                opening_time_minute = opening_time[-2:]
                # add extra calls to scheduler to set_orders() every time market opens
                self.scheduler.add_job(self.set_orders, 'cron', hour=opening_time_hour, minute=opening_time_minute, second='02')
                self.scheduler.add_job(self.handle_market_open_and_close_times, trigger='cron', args=(True,), hour=opening_time_hour, minute=opening_time_minute, second='00')
            for closing_time in closing_times_str_list:
                closing_time_hour = closing_time[:2]
                closing_time_minute = closing_time[-2:]
                self.scheduler.add_job(self.handle_market_open_and_close_times, trigger='cron', args=(False,), hour=closing_time_hour, minute=closing_time_minute, second='00')

        self.scheduler.start()
