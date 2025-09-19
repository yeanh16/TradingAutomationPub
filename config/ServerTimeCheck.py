from binance.client import Client
import time
import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables

load_dotenv(find_dotenv())

# Load API credentials from environment variables
binance_api_key = os.environ.get("BINANCE_API_KEY")
binance_api_secret = os.environ.get("BINANCE_API_SECRET")

if not binance_api_key or not binance_api_secret:
    print("Error: BINANCE_API_KEY and BINANCE_API_SECRET environment variables must be set")
    exit(1)

client = Client(binance_api_key, binance_api_secret)

while True:
    local_time1 = int(time.time() * 1000)
    server_time = client.get_server_time()
    diff1 = server_time['serverTime'] - local_time1
    local_time2 = int(time.time() * 1000)
    diff2 = local_time2 - server_time['serverTime']
    print("local1: %s server:%s local2: %s diff1:%s diff2:%s" % (local_time1, server_time['serverTime'], local_time2, diff1, diff2))
    time.sleep(1)
