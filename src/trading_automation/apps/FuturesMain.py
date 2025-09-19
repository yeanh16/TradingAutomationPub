import sys
import argparse
import sys

from trading_automation.apps.FuturesManager import FuturesFlushBuyManager
from trading_automation.clients.DiscordClient import DISCORD_TOKEN, DiscordNotificationService
from trading_automation.core.Utils import *
from trading_automation.websockets.PhemexWebSocketMaster import PhemexWebSocketMaster

# usage: FuturesMain.py [-h] [-blocking] [-stopLossTermination] [-shorts]
#                       [-recalcOnFill] [-postOnly] [-closePartialFills]
#                       interval symbol flushPercent squeezePercent numberOfFlushBars
#                       exitLookbackBars stopLossPercentageLong stopLossPercentageShort
#                       softSLPercentage softSLN takeProfitPercentage quantity fixedBalance
#                       balancePercent minBalance maxDrawdownPercentage
#       or include an @arg txt file with an arg on each line.
#       FuturesMain.py @arg_file.txt
#       nohup python3 FuturesMain.py @arg_file.txt &


def main(argv=None) -> int:
    raw_args = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Binance Bot", fromfile_prefix_chars='@')
    parser.add_argument('exchange', type=str)
    parser.add_argument('interval', type=str)
    parser.add_argument('symbol', type=str)
    parser.add_argument('flushPercent', type=float)
    parser.add_argument('squeezePercent', type=float, default=0)
    parser.add_argument('numberOfFlushBars', type=int)
    parser.add_argument('exitLookbackBars', type=int)
    parser.add_argument('stopLossPercentageLong', type=float, default=0)
    parser.add_argument('stopLossPercentageShort', type=float, default=0)
    parser.add_argument('softSLPercentage', type=float, default=0)
    parser.add_argument('softSLN', type=int, default=0)
    parser.add_argument('takeProfitPercentage', type=float, default=0)
    parser.add_argument('quantity', type=float, default=0)
    parser.add_argument('fixedBalance', type=float, default=0)
    parser.add_argument('balancePercent', type=float, default=0)
    parser.add_argument('minBalance', type=float, default=0)
    parser.add_argument('maxDrawdownPercentage', type=float, default=0)
    parser.add_argument('maxSingleTradeLossPercentage', type=float, default=0)
    parser.add_argument('maxNumOfPositions', type=int, default=0)
    parser.add_argument('shortsPositionMultiplier', type=float, default=1.0)
    parser.add_argument('-blocking', '-b', action='store_true')
    parser.add_argument('-stopLossTermination', '-t', action='store_true')
    parser.add_argument('-shorts', '-s', action='store_true')
    parser.add_argument('-recalcOnFill', '-r', action='store_true')
    parser.add_argument('-postOnly', '-p', action='store_true')
    parser.add_argument('-closePartialFills', '-c', action='store_true')
    parser.add_argument('-avoidMarketEntries', '-a', action='store_true')
    parser.add_argument('-close_position_only', '-x', action='store_true')
    parser.add_argument('-volumeBasedPosSize', '-v', action='store_true')
    parser.add_argument('-ignoreAbnormalVolume', '-n', action='store_true')
    args = parser.parse_args(raw_args)
    argfilename = raw_args[0][1:] if raw_args and raw_args[0].startswith('@') else None

        discord_service = DiscordNotificationService()
        phemex_input_q = None
        phemex_output_q = None
        if 'PHEMEX' in args.exchange:
            from queue import Queue

            phemex_input_q = Queue()
            phemex_output_q = Queue()
            pwsm = PhemexWebSocketMaster(phemex_input_q, phemex_output_q)
            pwsm.start()

    FuturesManager = FuturesFlushBuyManager(symbol=args.symbol,
                                            flushPercent=args.flushPercent,
                                            numberOfFlushBars=args.numberOfFlushBars,
                                            exitLookbackBars=args.exitLookbackBars,
                                            interval=args.interval, shorts=args.shorts,
                                            squeezePercent=args.squeezePercent,
                                            recalcOnFill=args.recalcOnFill, postOnly=args.postOnly,
                                            quantity=args.quantity,
                                            stopLossPercentageLong=args.stopLossPercentageLong,
                                            stopLossPercentageShort=args.stopLossPercentageShort,
                                            softSLPercentage=args.softSLPercentage,
                                            softSLN=args.softSLN, takeProfitPercentage=args.takeProfitPercentage,
                                            fixedBalance=args.fixedBalance, balancePercent=args.balancePercent,
                                            maxDrawdownPercentage=args.maxDrawdownPercentage,
                                            maxSingleTradeLossPercentage=args.maxSingleTradeLossPercentage,
                                            blocking=args.blocking,
                                            stopLossTermination=args.stopLossTermination,
                                            minBalance=args.minBalance, closePartialFills=args.closePartialFills,
                                            avoidMarketEntries=args.avoidMarketEntries, exchange=args.exchange,
                                            maxNumOfPositions=args.maxNumOfPositions,
                                            shortsPositionMultiplier=args.shortsPositionMultiplier,
                                            close_position_only=args.close_position_only,
                                            volumeBasedPosSize=args.volumeBasedPosSize,
                                            ignore_abnormal_volume=args.ignoreAbnormalVolume,
                                            discord_service=discord_service,
                                            argfilename=argfilename, phemex_input_q=phemex_input_q,
                                            phemex_output_q=phemex_output_q)
    FuturesManager.start()
    if DISCORD_TOKEN:
        discord_service.start()
    FuturesManager.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())