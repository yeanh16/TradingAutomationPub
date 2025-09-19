import json
import os
import re
import sys
import threading
import traceback
from time import sleep

import requests
from requests_oauthlib import OAuth1Session

from typing import Optional

from trading_automation.clients.DiscordClient import DISCORD_TOKEN, DiscordNotificationService
from trading_automation.clients.UniversalClient import UniversalClient
from trading_automation.config.settings import get_settings
from trading_automation.core.Logger import Logger
from trading_automation.core.Utils import ARG_FILE_REGEX, clean_instrument_name, get_position_size

settings = get_settings()
bearer_token = settings.twitter_bearer_token
TWITTER_API_KEY = settings.twitter_api_key
TWITTER_API_SECRET = settings.twitter_api_secret
DISCORD_CHANNEL_ID = settings.discord_channel_id or 0
DISCORD_TERMINATIONS_CHANNEL_ID = settings.discord_terminations_channel_id or 0
DISCORD_SKIPPING_ORDERS_CHANNEL_ID = settings.discord_skipping_orders_channel_id or 0
DISCORD_TWITTER_HANDLING_CHANNEL_ID = settings.discord_twitter_handling_channel_id or 0


def bearer_oauth(r):
    """
    Method required by bearer token authentication.
    """

    r.headers["Authorization"] = f"Bearer {bearer_token}"
    r.headers["User-Agent"] = "v2FilteredStreamPython"
    return r


def get_rules():
    response = requests.get(
        "https://api.twitter.com/2/tweets/search/stream/rules", auth=bearer_oauth
    )
    if response.status_code != 200:
        raise Exception(
            "Cannot get rules (HTTP {}): {}".format(response.status_code, response.text)
        )
    print(json.dumps(response.json()))
    return response.json()


def delete_all_rules(rules):
    if rules is None or "data" not in rules:
        return None

    ids = list(map(lambda rule: rule["id"], rules["data"]))
    payload = {"delete": {"ids": ids}}
    response = requests.post(
        "https://api.twitter.com/2/tweets/search/stream/rules",
        auth=bearer_oauth,
        json=payload
    )
    if response.status_code != 200:
        raise Exception(
            "Cannot delete rules (HTTP {}): {}".format(
                response.status_code, response.text
            )
        )
    print(json.dumps(response.json()))


def set_rules():
    # You can adjust the rules if needed
    sample_rules = [
        {"value": "from:BeenYean -is:retweet", "tag": "from @BeenYean"},
        {"value": "from:binance OR from:coinbase -is:retweet", "tag": "from a big exchange"},
        {"value": "from:elonmusk", "tag": "from @elonmusk"},
    ]
    payload = {"add": sample_rules}
    response = requests.post(
        "https://api.twitter.com/2/tweets/search/stream/rules",
        auth=bearer_oauth,
        json=payload,
    )
    if response.status_code != 201:
        raise Exception(
            "Cannot add rules (HTTP {}): {}".format(response.status_code, response.text)
        )
    print(json.dumps(response.json()))


def send_tweet(text):
    payload = {"text": text}
    # Get request token
    request_token_url = "https://api.twitter.com/oauth/request_token?oauth_callback=oob&x_auth_access_type=write"
    oauth = OAuth1Session(TWITTER_API_KEY, client_secret=TWITTER_API_SECRET)

    try:
        fetch_response = oauth.fetch_request_token(request_token_url)
    except ValueError:
        print(
            "There may have been an issue with the consumer_key or consumer_secret you entered."
        )

    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")
    print("Got OAuth token: %s" % resource_owner_key)

    # Get authorization
    base_authorization_url = "https://api.twitter.com/oauth/authorize"
    authorization_url = oauth.authorization_url(base_authorization_url)
    print("Please go here and authorize: %s" % authorization_url)
    verifier = input("Paste the PIN here: ")

    # Get the access token
    access_token_url = "https://api.twitter.com/oauth/access_token"
    oauth = OAuth1Session(
        TWITTER_API_KEY,
        client_secret=TWITTER_API_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )
    oauth_tokens = oauth.fetch_access_token(access_token_url)

    access_token = oauth_tokens["oauth_token"]
    access_token_secret = oauth_tokens["oauth_token_secret"]

    # Make the request
    oauth = OAuth1Session(
        TWITTER_API_KEY,
        client_secret=TWITTER_API_SECRET,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )

    # Making the request
    response = oauth.post(
        "https://api.twitter.com/2/tweets",
        json=payload,
    )

    if response.status_code != 201:
        raise Exception(
            "Request returned an error: {} {}".format(response.status_code, response.text)
        )

    print("Response code: {}".format(response.status_code))

    # Saving the response as JSON
    json_response = response.json()
    print(json.dumps(json_response, indent=4, sort_keys=True))


class thread_with_trace(threading.Thread):

    def __init__(self, *args, **keywords):
        threading.Thread.__init__(self, *args, **keywords)
        self.killed = False

    def start(self):
        self.__run_backup = self.run
        self.run = self.__run
        threading.Thread.start(self)

    def __run(self):
        sys.settrace(self.globaltrace)
        self.__run_backup()
        self.run = self.__run_backup

    def globaltrace(self, frame, event, arg):
        if event == 'call':
          return self.localtrace
        else:
          return None

    def localtrace(self, frame, event, arg):
        if self.killed:
          if event == 'line':
            raise SystemExit()
        return self.localtrace

    def kill(self):
        self.killed = True


class TwitterStream(threading.Thread):
    ARGLIST_FILENAME = 'arglist.txt'

    def __init__(self, exchanges=None, discord_service: Optional[DiscordNotificationService] = None):
        super().__init__()
        if exchanges is None:
            exchanges = ['OKEX', 'BYBIT', 'GATE', 'OKEX_2', 'BYBIT_2', 'GATE_2', 'GATE_3', 'GATE_4', 'BINGX']
        self.exchanges = exchanges
        self.clients = {}
        self.discord_service = discord_service or DiscordNotificationService()
        self.logger = Logger(client=None, discord_service=self.discord_service)
        for exchange in exchanges:
            self.clients[exchange] = UniversalClient(exchange)
        self.lock = threading.Lock()
        self.argfilenames = []
        self.running_symbols = []  # the symbols currently are being traded
        runfile = open(self.ARGLIST_FILENAME, 'r', newline='\n')
        for line in runfile.readlines():
            r = re.search(ARG_FILE_REGEX, line.strip())
            if r:
                self.argfilenames.append(r.group(1))
        runfile.close()
        for arg_file in self.argfilenames:
            file = open(arg_file, 'r')
            lines = list(map(str.strip, file.readlines()))
            params = lines[0:19]
            self.running_symbols.append(clean_instrument_name(params[2]))
            file.close()
        self.running_symbols = list(set(self.running_symbols))
        self.currently_processing_argfiles = []
        self.currently_processing_argfiles_lock = threading.Lock()
        self.initialised_message_given = False

    def change_params_of_arglist_entry(self, argfilename, to_add=None, to_remove=None):
        if to_remove is None:
            to_remove = []
        if to_add is None:
            to_add = []
        self.lock.acquire()
        runfile = open(self.ARGLIST_FILENAME, 'r')
        updated_text = ""
        for line in runfile.readlines():
            newline = line.strip()
            r = re.search(ARG_FILE_REGEX, line.strip())
            if r and argfilename == r.group(1):
                if r.group(2):
                    for param in to_add:
                        if f'-{param}' not in r.group(2):
                            newline = newline + f' -{param}'
                    for param in to_remove:
                        if f'-{param}' in r.group(2):
                            newline = newline.replace(f'-{param}', '')
                elif to_add:
                    for param in to_add:
                        newline = newline + f' -{param}'
            updated_text += newline + '\n'
        runfile.close()
        updated_file = open(self.ARGLIST_FILENAME, 'w')
        updated_file.write(updated_text)
        updated_file.close()
        self.lock.release()

    def check_if_param_already_exists_for_arglist_entry(self, argfilename, param):
        result = False
        runfile = open(self.ARGLIST_FILENAME, 'r')
        for line in runfile.readlines():
            r = re.search(ARG_FILE_REGEX, line.strip())
            if r and argfilename == r.group(1):
                if r.group(2):
                    if f'-{param}' in r.group(2):
                        result = True
        runfile.close()
        return result

    def handle_found_case(self, argfilename, clean_symbol, tweet_text):

        if self.check_if_param_already_exists_for_arglist_entry(argfilename=argfilename, param='w'):
            self.logger.writeline(f"{argfilename} has already been paused", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
            self.currently_processing_argfiles_lock.acquire()
            self.currently_processing_argfiles.remove(argfilename)
            self.currently_processing_argfiles_lock.release()
            return

        # mark the argfilename with the optional param to 'wait'
        self.change_params_of_arglist_entry(argfilename=argfilename, to_add=['w'])
        file = open(argfilename, 'r')
        lines = list(map(str.strip, file.readlines()))
        params = lines[0:19]
        exchange = params[0]
        symbol = params[2]
        file.close()

        if exchange not in self.clients.keys():
            self.clients[exchange] = UniversalClient(exchange)

        def volume_spike_check(recent_number_of_candles=3, prior_number_of_candles=197, spike_multiplier_threshold=3):
            candles = self.clients[exchange].futures_klines(symbol=symbol, interval="1m", limit=recent_number_of_candles+prior_number_of_candles)
            recent_volume = 0
            for candle in candles[-recent_number_of_candles:]:
                if len(candle) == 7:
                    # FTX candles, volume is index 5
                    recent_volume += float(candle[5])
                else:
                    recent_volume += float(candle[7])
            av_recent_volume = recent_volume/(recent_number_of_candles-1)
            prior_volume = 0
            for candle in candles[:prior_number_of_candles]:
                if len(candle) == 7:
                    # FTX candles, volume is index 5
                    prior_volume += float(candle[5])
                else:
                    prior_volume += float(candle[7])
            av_prior_volume = prior_volume/prior_number_of_candles
            if av_recent_volume > av_prior_volume * spike_multiplier_threshold :
                return True
            else:
                return False

        position = self.clients[exchange].futures_get_position(symbol=symbol)
        if get_position_size(position) == 0:
            self.logger.writeline(f"No position to close for {exchange} {symbol}", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
            self.clients[exchange].futures_cancel_all_orders(symbol=symbol)
        else:
            if volume_spike_check(recent_number_of_candles=2, prior_number_of_candles=198, spike_multiplier_threshold=3):
                self.logger.writeline(f"{exchange} {symbol} Position open and volume spike detected, closing at best price then pausing strat", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
                self.clients[exchange].futures_close_best_price(symbol=symbol)
                self.currently_processing_argfiles_lock.acquire()
                self.currently_processing_argfiles.remove(argfilename)
                self.currently_processing_argfiles_lock.release()
                return
            else:
                highly_likely_direct_mention_regexes = [fr'\${clean_symbol}\W',  # a symbol with '$' in front and non word character to the right mentions the coin directly e.g. '$BTC'
                                                        fr'\W{clean_symbol}\W',  # symbol with non word characters either side e.g. 'yada yada BTC yada yada'
                                                        fr'^{clean_symbol}\W',  # same as above but at start of tweet and non word character to the right e.g. 'BTC yada yada'
                                                        ]
                for regex in highly_likely_direct_mention_regexes:
                    r = re.search(regex, tweet_text)
                    if r:
                        self.logger.writeline(f"{exchange} {symbol} Position open and found highly likely direct mention of symbol ('{r.group()}') in tweet. Closing at best price and pausing strat", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
                        self.clients[exchange].futures_close_best_price(symbol=symbol)
                        self.currently_processing_argfiles_lock.acquire()
                        self.currently_processing_argfiles.remove(argfilename)
                        self.currently_processing_argfiles_lock.release()
                        return
            self.logger.writeline(f"{exchange} {symbol} Position open but no volume spike or direct mention of symbol found. No actions taken for now, checking volume again in 2 minutes for confirmation...", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
        # wait 2 minutes, check if the volume is normal to determine if false alarm
        sleep(120)
        if volume_spike_check():
            self.logger.writeline(f"Volume spike detected for {exchange} {symbol}, pausing strat", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
            self.clients[exchange].futures_close_best_price(symbol=symbol)
        else:
            self.logger.writeline(f"False alarm, no volume spike detected for {exchange} {symbol}, restarting strat", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
            self.change_params_of_arglist_entry(argfilename=argfilename, to_remove=['w'])
        self.currently_processing_argfiles_lock.acquire()
        self.currently_processing_argfiles.remove(argfilename)
        self.currently_processing_argfiles_lock.release()
        return

    def handle_tweet(self, json_response):
        text = json_response['data']['text']
        tag = json_response['matching_rules'][0]['tag']
        for symbol in self.running_symbols:
            if symbol in text:
                self.logger.writeline(f"Found '{symbol}' in tweet\n'{text}'\n {tag}", discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
                argfilenames_to_be_handled = []
                for arg_file in self.argfilenames:
                    file = open(arg_file, 'r')
                    lines = list(map(str.strip, file.readlines()))
                    params = lines[0:19]
                    if clean_instrument_name(params[2]) == symbol:
                        argfilenames_to_be_handled.append(arg_file)
                    file.close()
                for argfilename in argfilenames_to_be_handled:
                    if argfilename not in self.currently_processing_argfiles:
                        self.currently_processing_argfiles.append(argfilename)
                        threading.Thread(target=self.handle_found_case, args=(argfilename, symbol, text, )).start()

    def initiate_stream(self, response):
        try:
            if not self.initialised_message_given:
                self.logger.writeline(f"Twitter scanner looking for tweets that contain {self.running_symbols}",
                                      discord_channel_id=DISCORD_TWITTER_HANDLING_CHANNEL_ID)
                self.initialised_message_given = True
            for response_line in response.iter_lines():
                if response_line:
                    json_response = json.loads(response_line)
                    # print(json.dumps(json_response, indent=4, sort_keys=True))
                    if 'errors' in json_response:
                        raise Exception(f"Error in response {json_response['errors']}")
                    self.handle_tweet(json_response)
        except Exception as e:
            print(f"Exception in initiate_stream {e} {traceback.format_exc()}")

    def get_stream(self):
        try:
            response = requests.get(
                "https://api.twitter.com/2/tweets/search/stream", auth=bearer_oauth, stream=True,
            )
            if response.status_code == 429:  # Error code for "This stream is currently at the maximum allowed connection limit."
                # print('stream already in use')
                return None
            elif response.status_code == 200:
                # print('got new stream')
                return response
            else:
                raise Exception("Error in get_stream response (HTTP {}): {}".format(response.status_code, response.text))
        except Exception as e:
            print(f"Exception in get_stream {e} {traceback.format_exc()}")
            return None

    def run(self):
        t1 = None
        while True:
            try:
                stream = self.get_stream()
                if stream:
                    if t1 is not None:
                        t1.kill()
                        t1.join()
                    t1 = thread_with_trace(target=self.initiate_stream, args=(stream, ))
                    t1.start()
                sleep(60)  # allowed 50 connecting requests per 15 minutes
            except Exception as e:
                print(f"Exception in TwitterStream.run {e} {traceback.format_exc()}")
                sleep(60)


def start_stream(discord_service: Optional[DiscordNotificationService] = None):
    stream = TwitterStream(discord_service=discord_service)
    stream.start()
    if DISCORD_TOKEN:
        stream.discord_service.start()
    return stream


if __name__ == "__main__":
    service = DiscordNotificationService()
    stream_thread = start_stream(service)
    stream_thread.join()
