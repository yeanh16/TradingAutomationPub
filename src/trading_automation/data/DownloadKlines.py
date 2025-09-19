from trading_automation.core.Utils import *
from trading_automation.core.Logger import *
from apscheduler.schedulers.blocking import BlockingScheduler
#from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor


class DownloadKlines:
    def __init__(self):
        self.TRIES = 4
        self.scheduler = BlockingScheduler(executors={
            'default': ThreadPoolExecutor(500),
            'processpool': ProcessPoolExecutor(61)
        })
        change_tries(self.TRIES)
        self.symbols = []
        prices = futures_get_mark_price()
        for price in prices:
            self.symbols.append(price.get("symbol"))
        for s in self.symbols:
            self.scheduler_add_jobs_for_symbol(s)

    def download_klines(self, symbol, interval, limit):
        logger.writeline(f"Downloading klines for {symbol}_{interval}")
        candles = futures_get_candlesticks(symbol, interval=interval, limit=limit)
        if candles and len(candles) > 1:
            candles = candles[:-1]
            logger.writecsvlines(lines=candles, path=f"klines/{symbol}/{symbol}_{interval}.csv")

    def scheduler_add_jobs_for_symbol(self, symbol):
        logger.writeline(f"Adding symbol {symbol} to DownloadKlines download list")
        self.scheduler.add_job(self.download_klines, 'interval', args=(symbol, "1m", 1441), hours=24,
                               start_date='2020-01-12 00:00:05', coalesce=True, misfire_grace_time=54,
                               id=symbol + "_1m")
        self.scheduler.add_job(self.download_klines, 'interval', args=(symbol, "3m", 1441), hours=48,
                               start_date='2020-01-12 00:01:10', coalesce=True, misfire_grace_time=60,
                               id=symbol + "_3m")
        self.scheduler.add_job(self.download_klines, 'interval', args=(symbol, "5m", 1441), hours=120,
                               start_date='2020-01-12 00:02:15', coalesce=True, misfire_grace_time=60,
                               id=symbol + "_5m")
        self.scheduler.add_job(self.download_klines, 'interval', args=(symbol, "15m", 1441), hours=360,
                               start_date='2020-01-12 00:03:20', coalesce=True, misfire_grace_time=60,
                               id=symbol + "_15m")
        self.scheduler.add_job(self.download_klines, 'interval', args=(symbol, "1h", 721), hours=720,
                               start_date='2020-01-12 00:04:25', coalesce=True, misfire_grace_time=60,
                               id=symbol + "_1h")

    def scheduler_remove_jobs_for_symbol(self, symbol):
        logger.writeline(f"Removing symbol {symbol} from DownloadKlines download list")
        self.scheduler.remove_job(symbol + "_1m")
        self.scheduler.remove_job(symbol + "_3m")
        self.scheduler.remove_job(symbol + "_5m")
        self.scheduler.remove_job(symbol + "_15m")
        self.scheduler.remove_job(symbol + "_1h")

    def update_symbols(self):
        current_prices = futures_get_mark_price()
        current_symbols = []
        for current_price in current_prices:
            current_symbols.append(current_price.get("symbol"))
        # add new symbols from the current list to master list
        for symbol in current_symbols:
            if symbol not in self.symbols:
                self.scheduler_add_jobs_for_symbol(symbol)
                self.symbols.append(symbol)
        # remove symbols from master list that is not found in the current list
        for symbol in self.symbols:
            if symbol not in current_symbols:
                self.scheduler_remove_jobs_for_symbol(symbol)
                self.symbols.remove(symbol)

    def run(self):
        self.scheduler.add_job(self.update_symbols, 'interval', hours=24, start_date='2020-01-12 00:00:00')
        self.scheduler.start()


dlk = DownloadKlines()
dlk.run()
