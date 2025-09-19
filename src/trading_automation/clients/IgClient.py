from trading_ig.rest import IGService
# ABANDONED since there is a 10,000 candle request limit per week


class IgClient(IGService):

    def __init__(self, username, password, api_key, timeout=0.5, subaccount=None, acc_type='demo'):
        super().__init__(username, password, api_key)
        IGService(username, password, api_key, acc_type=acc_type)
        self.create_session()
        self.subaccount = subaccount

        if subaccount:
            accounts = self.fetch_accounts()['accounts']
            for account in accounts:
                if account['accountName'] == self.subaccount:
                    accountId = account['accountId']
            self._req('update', '/session/', params={'accountId': accountId})

    def browse_markets(self, hierarchy_id=''):
        response = self._req('read', f'/marketnavigation/{hierarchy_id}', params={}, session=None)
        return self.parse_response(response.text)

    def get_markets_list(self, epics):
        master_list = []
        while len(epics) > 0:
            response = self._req('read', f'/markets/', params={'epics': str(epics[:50])[2:-2].replace(" ", "").replace("'", "")}, session=None)
            data = response.json()
            master_list += data['marketDetails']
            epics = epics[50:]
        return {'marketDetails': master_list}

    def get_klines(self, epic, resolution, start=None, end=None, limit=None):
        assert resolution in ['MINUTE', 'MINUTE_5', 'MINUTE_10', 'MINUTE_15', 'MINUTE_30', 'HOUR', 'HOUR_4', 'DAY', 'WEEK']
        if start is not None and end is not None:
            response = self._req('read', f'/prices/{epic}/{resolution}/{start}/{end}', params={}, session=None, version='2')
        elif limit is not None and start is None and end is None:
            if limit > 2000:
                limit = 2000
            response = self._req('read', f'/prices/{epic}/{resolution}/{limit}', params={}, session=None)
        else:
            raise Exception("Needs start & end time or limit")
        return response.json()
