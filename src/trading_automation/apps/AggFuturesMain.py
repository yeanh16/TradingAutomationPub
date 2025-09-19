import os
import re
import sys
from typing import Dict

from trading_automation.apps.FuturesManager import FuturesFlushBuyManager
from trading_automation.clients.DiscordClient import DISCORD_TOKEN, DiscordNotificationService
from trading_automation.clients.UniversalClient import UniversalClient
from trading_automation.core.Utils import ARG_FILE_REGEX
from trading_automation.websockets.PhemexWebSocketMaster import PhemexWebSocketMaster


def main(argv=None) -> int:
    original_argv = sys.argv[:]
    if argv is not None:
        sys.argv = [sys.argv[0]] + list(argv)
    try:

        if '-t' in sys.argv[1:]:
            # -t 'transition' flag, swap strats in 'arglist.txt' to those in 'arglist2.txt'
            clients: Dict[str, UniversalClient] = {}
            # identify strats with open positions
            arg_files_with_open_positions = []
            runfile = open('arglist.txt', 'r')
            arg_file_names = []
            for line in runfile.readlines():
                r = re.search(ARG_FILE_REGEX, line.strip())
                if r:
                    arg_file_names.append(r.group(1))
            runfile.close()

            for arg_file in arg_file_names:
                file = open(arg_file, 'r')
                lines = list(map(str.strip, file.readlines()))
                params = lines[0:19]
                exchange = params[0]
                symbol = params[2]
                if exchange not in clients:
                    clients[exchange] = UniversalClient(exchange=exchange)
                position = clients[exchange].futures_get_position(symbol=symbol)
                if float(position[0]['positionAmt']) != 0.0:
                    arg_files_with_open_positions.append(arg_file)
                elif exchange != "BINANCE":
                    clients[exchange].futures_cancel_all_open_orders(symbol=symbol)
                    if float(clients[exchange].futures_get_position(symbol=symbol)[0]['positionAmt']) != 0.0:
                        arg_files_with_open_positions.append(arg_file)
            print(f"Still open positions {arg_files_with_open_positions}")
            # compare if these strats are in arglist2.txt
            runfile = open('arglist2.txt', 'r')
            arg_file2_names = []
            for line in runfile.readlines():
                r = re.search(ARG_FILE_REGEX, line.strip())
                if r:
                    arg_file2_names.append(r.group(1))
            runfile.close()
            close_only_list = [x for x in arg_files_with_open_positions if x not in arg_file2_names]
            print(f"close_only_list: {close_only_list}")
            # append close_only_list to arglist2.txt
            runfile = open('arglist2.txt', 'a')
            with runfile:
                runfile.write("\n")
                for file in close_only_list:
                    runfile.write(f"{file} -x\n")
            runfile.close()
            # rename arglist2.txt to be arglist.txt and vice versa
            os.rename('arglist.txt', 'arglist_temp.txt')
            os.rename('arglist2.txt', 'arglist.txt')
            os.rename('arglist_temp.txt', 'arglist2.txt')
            clients.clear()

        if '-x' in sys.argv[1:]:
            global_close_positions_only = True
        else:
            global_close_positions_only = False

        close_only_exchanges = []
        if '-binance' in sys.argv[1:]:
            close_only_exchanges.append("BINANCE")
        if '-okex' in sys.argv[1:]:
            close_only_exchanges.append("OKEX")
        if '-gate' in sys.argv[1:]:
            close_only_exchanges.append("GATE")
        if '-ftx' in sys.argv[1:]:
            close_only_exchanges.append("FTX")
        if '-mexc' in sys.argv[1:]:
            close_only_exchanges.append("MEXC")

        runfile = open('arglist.txt', 'r')
        arg_file_names = []
        close_only_arg_files = []
        ignore_abnormal_volume_files = []
        for line in runfile.readlines():
            r = re.search(ARG_FILE_REGEX, line.strip())
            if r:
                arg_file_names.append(r.group(1))
                if r.group(2):
                    if '-x' in r.group(2):
                        close_only_arg_files.append(r.group(1))
                    if '-n' in r.group(2):
                        ignore_abnormal_volume_files.append(r.group(1))
        runfile.close()

        discord_service = DiscordNotificationService()
        # check if PHEMEX is one of the exchanges, if so, start up web socket master
        exchanges = []
        for arg_file in arg_file_names:
            file = open(arg_file, 'r')
            lines = list(map(str.strip, file.readlines()))
            params = lines[0:20]
            exchanges.append(params[0])
            file.close()
        phemex_input_q = None
        phemex_output_q = None
        if 'PHEMEX' in exchanges:
            from queue import Queue

            phemex_input_q = Queue()
            phemex_output_q = Queue()
            pwsm = PhemexWebSocketMaster(phemex_input_q, phemex_output_q)
            pwsm.start()

        FutureManagerObjects = []
        for arg_file in arg_file_names:
            file = open(arg_file, 'r')
            lines = list(map(str.strip, file.readlines()))
            params = lines[0:20]
            optionals = lines[20:]
            blocking = True if '-b' in optionals else False
            stopLossTermination = True if '-t' in optionals else False
            shorts = True if '-s' in optionals else False
            recalcOnFill = True if '-r' in optionals else False
            postOnly = True if '-p' in optionals else False
            closePartialFills = True if '-c' in optionals else False
            avoidMarketEntries = True if '-a' in optionals else False
            close_position_only = True if '-x' in optionals or global_close_positions_only or \
                                          [x for x in close_only_exchanges if params[0] in x] or \
                                          arg_file in close_only_arg_files else False
            volumeBasedPosSize = True if '-v' in optionals else False
            ignore_abnormal_volume = True if ('-n' in optionals or arg_file in ignore_abnormal_volume_files) else False
            FutureManagerObjects.append(FuturesFlushBuyManager(exchange=params[0],
                                                               interval=params[1],
                                                               symbol=params[2],
                                                               flushPercent=float(params[3]),
                                                               squeezePercent=float(params[4]),
                                                               numberOfFlushBars=int(params[5]),
                                                               exitLookbackBars=int(params[6]),
                                                               stopLossPercentageLong=float(params[7]),
                                                               stopLossPercentageShort=float(params[8]),
                                                               softSLPercentage=float(params[9]),
                                                               softSLN=int(params[10]),
                                                               takeProfitPercentage=float(params[11]),
                                                               quantity=float(params[12]),
                                                               fixedBalance=float(params[13]),
                                                               balancePercent=float(params[14]),
                                                               minBalance=float(params[15]),
                                                               maxDrawdownPercentage=float(params[16]),
                                                               maxSingleTradeLossPercentage=float(params[17]),
                                                               maxNumOfPositions=int(params[18]),
                                                               shortsPositionMultiplier=float(params[19]),
                                                               blocking=blocking,
                                                               stopLossTermination=stopLossTermination,
                                                               shorts=shorts,
                                                               recalcOnFill=recalcOnFill,
                                                               postOnly=postOnly,
                                                               closePartialFills=closePartialFills,
                                                               avoidMarketEntries=avoidMarketEntries,
                                                               close_position_only=close_position_only,
                                                               volumeBasedPosSize=volumeBasedPosSize,
                                                               ignore_abnormal_volume=ignore_abnormal_volume,
                                                               discord_service=discord_service,
                                                               argfilename=arg_file, phemex_input_q=phemex_input_q,
                                                               phemex_output_q=phemex_output_q))
            file.close()

        for FutureManager in FutureManagerObjects:
            FutureManager.daemon = False
            FutureManager.start()

        if DISCORD_TOKEN:
            discord_service.start()
        for FutureManager in FutureManagerObjects:
            FutureManager.join()
        return 0
    finally:
        if argv is not None:
            sys.argv = original_argv


if __name__ == "__main__":
    sys.exit(main())
