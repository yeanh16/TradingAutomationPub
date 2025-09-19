import abc


class WebsocketInterface(metaclass=abc.ABCMeta):
    @classmethod
    def __subclasshook__(cls, subclass):
        return (hasattr(subclass, 'get_order_api_first') and
                callable(subclass.get_order_api_first) and
                hasattr(subclass, 'get_candlesticks_api_first') and
                callable(subclass.get_candlesticks_api_first) and
                hasattr(subclass, 'get_position_api_first') and
                callable(subclass.get_position_api_first) and
                hasattr(subclass, 'get_wallet_balance_api_first') and
                callable(subclass.get_wallet_balance_api_first) and
                hasattr(subclass, 'get_latest_price_api_first') and
                callable(subclass.get_latest_price_api_first)
                or
                NotImplemented)

    @abc.abstractmethod
    def get_order_api_first(self, orderId):
        raise NotImplementedError

    @abc.abstractmethod
    def get_candlesticks_api_first(self, limit):
        raise NotImplementedError

    @abc.abstractmethod
    def get_position_api_first(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_wallet_balance_api_first(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_latest_price_api_first(self):
        raise NotImplementedError
