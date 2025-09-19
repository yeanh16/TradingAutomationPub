import sys
import os
import threading
import traceback
from typing import Optional

import numpy as np
import pandas
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from pytz import utc

from trading_automation.clients.DiscordClient import DiscordNotificationService
from trading_automation.clients.UniversalClient import UniversalClient
from trading_automation.config.settings import get_settings
from trading_automation.core.Logger import *
from trading_automation.core.Utils import *
from trading_automation.data.DownloadKlinesOneTime import run as download_klines

settings = get_settings()
CLOSE_BEST_PRICE_MIN_VALUE = settings.close_best_price_min_value
UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS = settings.unrealised_pnl_drawdown_to_stop_new_orders
UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS_BYBIT = settings.unrealised_pnl_drawdown_to_stop_new_orders_bybit
ABNORMAL_VOLUME_SPIKE_MULTIPLIER_THRESHOLD = settings.abnormal_volume_spike_multiplier_threshold
ABNORMAL_VOLUME_SPIKE_AVERAGE_NUMBER_OF_DAYS = settings.abnormal_volume_spike_average_number_of_days
DISCORD_CHANNEL_ID = settings.discord_channel_id or 0
DISCORD_TERMINATIONS_CHANNEL_ID = settings.discord_terminations_channel_id or 0
DISCORD_SKIPPING_ORDERS_CHANNEL_ID = settings.discord_skipping_orders_channel_id or 0
RANGE_LIMIT_DAYS = 21


class CounterTrendStocksBot(threading.Thread):
    CAPITAL_COMMODITIES_AND_INDICES_LIST = ['ALUMINUM', 'AU200', 'CN50', 'COFFEEARABICA', 'COPPER', 'CORN', 'DE40',
                                            'DXY', 'ECFZ23', 'EU50', 'FR40', 'GOLD', 'HK50', 'IT40', 'J225', 'LEAD',
                                            'NATURALGAS', 'NICKEL', 'NIFTY50', 'NL25', 'OIL_BRENT', 'OIL_CRUDE',
                                            'ORANGEJUICE', 'PALLADIUM', 'PLATINUM', 'RTY', 'SG25', 'SILVER', 'SOYBEAN',
                                            'SP35', 'SW20', 'TSI', 'UK100', 'UKSUGAR', 'US100', 'US30', 'US500',
                                            'USCOCOA', 'USCOTTON', 'VIX', 'WHEAT']
    CAPITAL_LEVERAGED_ETFS = ['BNKD', 'BNKU', 'FAS', 'FNGD', 'FNGO', 'FNGU', 'GUSH', 'JNUG', 'NRGD', 'NRGU', 'NUGT',
                              'SDOW', 'SOXL', 'SPXL', 'SPXS', 'SPXU', 'SQQQ', 'TECL', 'TNA', 'TQQQ', 'TZA', 'UBOT',
                              'UDOW', 'UPRO', 'ERX', 'GUSH', 'JDST']
    CAPTIAL_FOREX = ['AUDCAD', 'AUDCHF', 'AUDCNH', 'AUDHKD', 'AUDJPY', 'AUDMXN', 'AUDNOK', 'AUDNZD', 'AUDPLN', 'AUDSGD',
                     'AUDTRY', 'AUDUSD', 'AUDZAR', 'CADCHF', 'CADCNH', 'CADHKD', 'CADJPY', 'CADMXN', 'CADNOK', 'CADPLN',
                     'CADSEK', 'CADSGD', 'CADTRY', 'CADZAR', 'CHFCNH', 'CHFCZK', 'CHFDKK', 'CHFHKD', 'CHFHUF', 'CHFJPY',
                     'CHFMXN', 'CHFNOK', 'CHFPLN', 'CHFSEK', 'CHFSGD', 'CHFTRY', 'CHFZAR', 'CNHHKD', 'CNHJPY', 'DKKJPY',
                     'DKKSEK', 'EURAUD', 'EURCAD', 'EURCHF', 'EURCNH', 'EURCZK', 'EURDKK', 'EURGBP', 'EURHKD', 'EURHUF',
                     'EURILS', 'EURJPY', 'EURMXN', 'EURNOK', 'EURNZD', 'EURPLN', 'EURRON', 'EURSEK', 'EURSGD', 'EURTRY',
                     'EURUSD', 'EURUSD_W', 'EURZAR', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPCNH', 'GBPCZK', 'GBPDKK',
                     'GBPHKD', 'GBPHUF', 'GBPJPY', 'GBPMXN', 'GBPNOK', 'GBPNZD', 'GBPPLN', 'GBPSEK', 'GBPSGD', 'GBPTRY',
                     'GBPUSD', 'GBPZAR', 'HKDMXN', 'HKDSEK', 'HKDTRY', 'MXNJPY', 'NOKDKK', 'NOKJPY', 'NOKSEK', 'NOKTRY',
                     'NZDCAD', 'NZDCHF', 'NZDCNH', 'NZDHKD', 'NZDJPY', 'NZDMXN', 'NZDPLN', 'NZDSEK', 'NZDSGD', 'NZDTRY',
                     'NZDUSD', 'PLNJPY', 'PLNSEK', 'PLNTRY', 'SEKJPY', 'SEKMXN', 'SEKTRY', 'SGDHKD', 'SGDJPY', 'SGDMXN',
                     'TRYJPY', 'USDCAD', 'USDCHF', 'USDCNH', 'USDCZK', 'USDDKK', 'USDHKD', 'USDHUF', 'USDILS', 'USDJPY',
                     'USDJPY_W', 'USDMXN', 'USDNOK', 'USDPLN', 'USDRON', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR',
                     'ZARJPY']
    CAPITAL_BLACKLIST = CAPITAL_LEVERAGED_ETFS + CAPITAL_COMMODITIES_AND_INDICES_LIST + CAPTIAL_FOREX
    TOTAL_ACCOUNTS_IN_USE = 1

    def __init__(
        self,
        lookback_number_of_bars,
        standard_deviation_range,
        wait_bars,
        consecutive_signal_bars,
        percent_balance,
        discord_service: Optional[DiscordNotificationService] = None,
    ):
        threading.Thread.__init__(self)
        self.scheduler = BlockingScheduler(executors={'default': ThreadPoolExecutor(1)}, timezone=utc)
        self.interval = "1d"
        self.exchange = "CAPITAL"
        self.lookback_number_of_bars = lookback_number_of_bars
        self.standard_deviation_range = standard_deviation_range
        self.wait_bars = wait_bars
        self.consecutive_signal_bars = consecutive_signal_bars
        self.percent_balance = percent_balance
        self.discord_service = discord_service or DiscordNotificationService()
        self.client = UniversalClient(self.exchange, discord_service=self.discord_service, use_local_tick_and_step_data=True, timeout=30)
        self.logger = self.client.logger
        self.folders = [name for name in
                        os.listdir(f'klines/{self.exchange}')
                        if os.path.isdir(os.path.join(f'klines/{self.exchange}', name)) and not re.fullmatch(r"20\d{6}", name) and "_ASK" not in name and "_COMBINED" not in name]
        self.open_instrument_trade_dates_tracker = {}

    def find_tradeable_instruments(self):
        tradeable_instruments = []
        for instrument_name in self.folders:
            if instrument_name in self.CAPITAL_BLACKLIST:
                continue
            path = str(f'klines/{self.exchange}/{instrument_name}/{instrument_name}_{self.interval}.csv')
            kline_list = readcsv(path)
            if len(kline_list) < self.lookback_number_of_bars:
                continue
            past_closes = [Decimal(x[4]) for x in kline_list[-self.lookback_number_of_bars:]]
            sd = Decimal(str(np.std(past_closes)))
            average_of_past_closes = Decimal(str(np.mean(past_closes)))
            previous_close = Decimal(kline_list[-1][4])
            s = pandas.Series([Decimal(x[4]) for x in kline_list])
            rolling_std_list = [x for x in list(s.rolling(self.lookback_number_of_bars).std(ddof=0)) if x > 0]
            rolling_av_list = [x for x in list(s.rolling(self.lookback_number_of_bars).mean()) if x > 0]
            if previous_close < average_of_past_closes - sd * self.standard_deviation_range:
                trade_flag = True
                full_past_closes = [Decimal(x[4]) for x in
                                    kline_list[-max(self.lookback_number_of_bars, self.consecutive_signal_bars):]]
                # print(f"{instrument_name} full_past_closes{full_past_closes} rolling_av_list{rolling_av_list} rolling_std_list{rolling_std_list}")
                for i in range(1, self.consecutive_signal_bars):
                    try:
                        if full_past_closes[-i] > rolling_av_list[-i] - rolling_std_list[-i] * self.standard_deviation_range:
                            trade_flag = False
                            break
                    except IndexError:
                        print(f"Index error on {instrument_name}")
                        trade_flag = False
                        break
                if trade_flag:
                    tradeable_instruments.append(instrument_name)
        return tradeable_instruments

    def download_klines(self):
        download_klines(self.exchange, intervals_list=[self.interval])

    def set_order(self, instrument, is_entry: bool):
        if is_entry:
            self.client.futures_create_limit_order(symbol=instrument, side="BUY", balancePercent=self.percent_balance,
                                                   atAsk=True, limit=None)
            self.open_instrument_trade_dates_tracker[instrument] = self.client.futures_klines(instrument, interval=self.interval, limit=1)[0][0]
        else:
            position_size = self.client.futures_position_size(instrument)
            self.client.futures_create_limit_order(symbol=instrument, side="SELL", quantity=position_size,
                                                   atBid=True, reduceOnly=True, limit=None)
            self.open_instrument_trade_dates_tracker.pop(instrument)

    def set_scheduled_orders(self):
        self.logger.writeline("Downloading latest candles")
        # self.download_klines()
        # handle opening of new trades
        tradeable_instruments = self.find_tradeable_instruments()
        self.logger.writeline(f"Found tradeable instruments {tradeable_instruments}")
        for instrument in tradeable_instruments:
            if instrument in self.open_instrument_trade_dates_tracker.keys():
                self.logger.writeline(f"{instrument} already being traded, skipping")
                continue
            self.client.client_capital.refresh_security_tokens()
            opening_times = self.client.client_capital.get_market(instrument)['instrument']['openingHours']
            day_keys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            opening_times_for_today = opening_times[day_keys[datetime.today().weekday()]]
            if opening_times_for_today:
                current_datetime = datetime.now()
                opening_time = opening_times_for_today[0].split(' - ')[0]
                opening_hour = int(opening_time.split(':')[0])
                opening_minute = int(opening_time.split(':')[1])
                if current_datetime.hour >= opening_hour and current_datetime.minute >= opening_minute:
                    self.logger.writeline(f"{instrument} market currently open, placing buy at ask...")
                    self.set_order(instrument, is_entry=True)
                else:
                    scheduled_time_for_order = datetime(current_datetime.year, current_datetime.month, current_datetime.day, opening_hour, opening_minute, 2)
                    self.logger.writeline(f"{instrument} scheduling order to be placed today on open at {scheduled_time_for_order}...")
                    self.scheduler.add_job(self.set_order, args=(instrument, True, ), trigger='date', run_date=scheduled_time_for_order)
        # handle closing of positions after wait_bars
        for instrument in self.open_instrument_trade_dates_tracker.keys():
            self.client.client_capital.refresh_security_tokens()
            opening_times = self.client.client_capital.get_market(instrument)['instrument']['openingHours']
            day_keys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            opening_times_for_today = opening_times[day_keys[datetime.today().weekday()]]
            if opening_times_for_today:
                current_datetime = datetime.now()
                opening_time = opening_times_for_today[0].split(' - ')[0]
                opening_hour = int(opening_time.split(':')[0])
                opening_minute = int(opening_time.split(':')[1])
                path = str(f'klines/{self.exchange}/{instrument}/{instrument}_{self.interval}.csv')
                candles = readcsv(path)[-self.wait_bars:]
                if [int(x[0]) for x in candles].index(int(self.open_instrument_trade_dates_tracker[instrument])) == 0:
                    if current_datetime.hour >= opening_hour and current_datetime.minute >= opening_minute:
                        self.logger.writeline(f"{instrument} market currently open, placing sell exit at bid...")
                        self.set_order(instrument, is_entry=False)
                    else:
                        scheduled_time_for_order = datetime(current_datetime.year, current_datetime.month, current_datetime.day, opening_hour, opening_minute, 2)
                        self.logger.writeline(f"{instrument} scheduling exit order to be placed today on open at {scheduled_time_for_order}...")
                        self.scheduler.add_job(self.set_order, args=(instrument, False, ), trigger='date', run_date=scheduled_time_for_order)

    def run(self):
        self.logger.writeline("Running CounterTrendStocksBot")
        self.set_scheduled_orders()
        if self.interval == '1d':
            self.scheduler.add_job(self.set_scheduled_orders, 'cron', hour='0', minute='0', second='01', misfire_grace_time=60*60*24)
        self.scheduler.start()


if __name__ == '__main__':
    a = CounterTrendStocksBot(20, 1, 15, 20, percent_balance=0.10)
    print(a.find_tradeable_instruments())
