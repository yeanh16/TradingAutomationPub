"""Centralised configuration management for the trading platform."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application wide settings loaded from the environment and ``.env`` file."""

    # Exchange credentials -------------------------------------------------
    binance_api_key: Optional[str] = Field(default=None, env="BINANCE_API_KEY")
    binance_api_secret: Optional[str] = Field(default=None, env="BINANCE_API_SECRET")

    ftx_api_key: Optional[str] = Field(default=None, env="FTX_API_KEY")
    ftx_api_secret: Optional[str] = Field(default=None, env="FTX_API_SECRET")

    okex_api_key: Optional[str] = Field(default=None, env="OKEX_API_KEY")
    okex_api_secret: Optional[str] = Field(default=None, env="OKEX_API_SECRET")
    okex_passphrase: Optional[str] = Field(default=None, env="OKEX_PASSPHRASE")
    okex_api_key_second: Optional[str] = Field(default=None, env="OKEX_API_KEY_SECOND")
    okex_api_secret_second: Optional[str] = Field(default=None, env="OKEX_API_SECRET_SECOND")
    okex_passphrase_second: Optional[str] = Field(default=None, env="OKEX_PASSPHRASE_SECOND")
    okex_api_key_demo: Optional[str] = Field(default=None, env="OKEX_API_KEY_DEMO")
    okex_api_secret_demo: Optional[str] = Field(default=None, env="OKEX_API_SECRET_DEMO")
    okex_passphrase_demo: Optional[str] = Field(default=None, env="OKEX_PASSPHRASE_DEMO")

    gateio_api_key: Optional[str] = Field(default=None, env="GATEIO_API_KEY")
    gateio_api_secret: Optional[str] = Field(default=None, env="GATEIO_API_SECRET")
    gateio_user_id: Optional[str] = Field(default=None, env="GATEIO_USER_ID")
    gateio_api_key_second: Optional[str] = Field(default=None, env="GATEIO_API_KEY_SECOND")
    gateio_api_secret_second: Optional[str] = Field(default=None, env="GATEIO_API_SECRET_SECOND")
    gateio_user_id_second: Optional[str] = Field(default=None, env="GATEIO_USER_ID_SECOND")
    gateio_api_key_third: Optional[str] = Field(default=None, env="GATEIO_API_KEY_THIRD")
    gateio_api_secret_third: Optional[str] = Field(default=None, env="GATEIO_API_SECRET_THIRD")
    gateio_user_id_third: Optional[str] = Field(default=None, env="GATEIO_USER_ID_THIRD")
    gateio_api_key_fourth: Optional[str] = Field(default=None, env="GATEIO_API_KEY_FOURTH")
    gateio_api_secret_fourth: Optional[str] = Field(default=None, env="GATEIO_API_SECRET_FOURTH")
    gateio_user_id_fourth: Optional[str] = Field(default=None, env="GATEIO_USER_ID_FOURTH")

    bybit_api_key: Optional[str] = Field(default=None, env="BYBIT_API_KEY")
    bybit_api_secret: Optional[str] = Field(default=None, env="BYBIT_API_SECRET")
    bybit_api_key_second: Optional[str] = Field(default=None, env="BYBIT_API_KEY_SECOND")
    bybit_api_secret_second: Optional[str] = Field(default=None, env="BYBIT_API_SECRET_SECOND")
    bybit_api_key_third: Optional[str] = Field(default=None, env="BYBIT_API_KEY_THIRD")
    bybit_api_secret_third: Optional[str] = Field(default=None, env="BYBIT_API_SECRET_THIRD")

    mexc_api_key: Optional[str] = Field(default=None, env="MEXC_API_KEY")
    mexc_api_secret: Optional[str] = Field(default=None, env="MEXC_API_SECRET")

    kucoin_api_key: Optional[str] = Field(default=None, env="KUCOIN_API_KEY")
    kucoin_api_secret: Optional[str] = Field(default=None, env="KUCOIN_API_SECRET")
    kucoin_api_passphrase: Optional[str] = Field(default=None, env="KUCOIN_API_PASSPHRASE")

    ig_api_key: Optional[str] = Field(default=None, env="IG_API_KEY")
    ig_username: Optional[str] = Field(default=None, env="IG_USERNAME")
    ig_password: Optional[str] = Field(default=None, env="IG_PASSWORD")
    ig_api_key_demo: Optional[str] = Field(default=None, env="IG_API_KEY_DEMO")
    ig_username_demo: Optional[str] = Field(default=None, env="IG_USERNAME_DEMO")
    ig_password_demo: Optional[str] = Field(default=None, env="IG_PASSWORD_DEMO")

    capitaldotcom_api_key: Optional[str] = Field(default=None, env="CAPITALDOTCOM_API_KEY")
    capitaldotcom_username: Optional[str] = Field(default=None, env="CAPITALDOTCOM_USERNAME")
    capitaldotcom_password: Optional[str] = Field(default=None, env="CAPITALDOTCOM_PASSWORD")

    phemex_api_id: Optional[str] = Field(default=None, env="PHEMEX_API_ID")
    phemex_api_secret: Optional[str] = Field(default=None, env="PHEMEX_API_SECRET")

    bingx_api_key: Optional[str] = Field(default=None, env="BINGX_API_KEY")
    bingx_api_secret: Optional[str] = Field(default=None, env="BINGX_API_SECRET")

    xt_api_key: Optional[str] = Field(default=None, env="XT_API_KEY")
    xt_api_secret: Optional[str] = Field(default=None, env="XT_API_SECRET")

    # Behaviour flags ------------------------------------------------------
    print_console: bool = Field(default=True, env="PRINT_CONSOLE")
    log_traceback: bool = Field(default=True, env="LOG_TRACEBACK")
    timeout: float = Field(default=30.0, env="TIMEOUT")
    tries: int = Field(default=3, env="TRIES")
    default_recvwindow: int = Field(default=5000, env="DEFAULT_RECVWINDOW")
    okex_use_demo: bool = Field(default=False, env="OKEX_USE_DEMO")
    stagger_bybit_client_inits: bool = Field(default=False, env="STAGGER_BYBIT_CLIENT_INITS")
    ig_use_demo: bool = Field(default=False, env="IG_USE_DEMO")
    phemex_use_high_rate_api_endpoint: bool = Field(
        default=False, env="PHEMEX_USE_HIGH_RATE_API_ENDPOINT"
    )
    capital_account_currency: str = Field(default="GBP", env="CAPITAL_ACCOUNT_CURRENCY")

    # Discord / notifications ---------------------------------------------
    discord_token: Optional[str] = Field(default=None, env="DISCORD_TOKEN")
    discord_client_id: Optional[str] = Field(default=None, env="DISCORD_CLIENT_ID")
    discord_error_messages_channel_id: Optional[int] = Field(
        default=None, env="DISCORD_ERROR_MESSAGES_CHANNEL_ID"
    )
    discord_channel_id: Optional[int] = Field(default=None, env="DISCORD_CHANNEL_ID")
    discord_terminations_channel_id: Optional[int] = Field(
        default=None, env="DISCORD_TERMINATIONS_CHANNEL_ID"
    )
    discord_skipping_orders_channel_id: Optional[int] = Field(
        default=None, env="DISCORD_SKIPPING_ORDERS_CHANNEL_ID"
    )
    discord_twitter_handling_channel_id: Optional[int] = Field(
        default=None, env="DISCORD_TWITTER_HANDLING_CHANNEL_ID"
    )

    twitter_bearer_token: Optional[str] = Field(default=None, env="TWITTER_BEARER_TOKEN")
    twitter_api_key: Optional[str] = Field(default=None, env="TWITTER_API_KEY")
    twitter_api_secret: Optional[str] = Field(default=None, env="TWITTER_API_SECRET")

    # Risk management ------------------------------------------------------
    close_best_price_min_value: float = Field(default=0.0, env="CLOSE_BEST_PRICE_MIN_VALUE")
    unrealised_pnl_drawdown_to_stop_new_orders: float = Field(
        default=0.0, env="UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS"
    )
    unrealised_pnl_drawdown_to_stop_new_orders_bybit: float = Field(
        default=0.0, env="UNREALISED_PNL_DRAWDOWN_TO_STOP_NEW_ORDERS_BYBIT"
    )
    abnormal_volume_spike_multiplier_threshold: float = Field(
        default=0.0, env="ABNORMAL_VOLUME_SPIKE_MULTIPLIER_THRESHOLD"
    )
    abnormal_volume_spike_average_number_of_days: int = Field(
        default=0, env="ABNORMAL_VOLUME_SPIKE_AVERAGE_NUMBER_OF_DAYS"
    )
    btc_price_upper_bound: float = Field(default=0.0, env="BTC_PRICE_UPPER_BOUND")
    btc_price_lower_bound: float = Field(default=0.0, env="BTC_PRICE_LOWER_BOUND")

    okex_pos_mode: Optional[str] = Field(default=None, env="OKEX_POS_MODE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def require(self, *field_names: str) -> None:
        """Ensure that the specified fields are populated."""

        missing = [name for name in field_names if getattr(self, name) in (None, "")]
        if missing:
            raise ValueError(f"Missing required configuration values: {', '.join(missing)}")


@lru_cache()
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""

    return Settings()
