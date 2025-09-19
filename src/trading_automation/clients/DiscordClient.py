"""Async Discord notification service used across the trading platform."""
from __future__ import annotations

import asyncio
from asyncio import QueueFull
from dataclasses import dataclass
from threading import Event, Thread
from typing import Optional

import discord

from trading_automation.config.settings import get_settings
from trading_automation.logging.config import get_logger


_settings = get_settings()
DISCORD_TOKEN = _settings.discord_token
DISCORD_CLIENT_ID = _settings.discord_client_id

_logger = get_logger("trading_automation.discord")


@dataclass
class DiscordMessage:
    """Represents a message to be sent to a Discord channel."""

    content: str
    channel_id: int


class DiscordNotificationService:
    """Background service that relays messages to Discord asynchronously."""

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        intents: Optional[discord.Intents] = None,
    ) -> None:
        self._token = token or DISCORD_TOKEN
        self._intents = intents or discord.Intents.default()
        self._client = discord.Client(intents=self._intents)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue[DiscordMessage]] = None
        self._thread: Optional[Thread] = None
        self._started = False
        self._ready = Event()
        self._pending_messages: list[DiscordMessage] = []

        @self._client.event
        async def on_ready() -> None:  # pragma: no cover - handled by Discord internals
            _logger.info("Discord client connected", extra={"user": str(self._client.user)})
            self._ready.set()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the background Discord client if a token is configured."""

        if self._started:
            return
        if not self._token:
            _logger.warning("Discord token not configured; notifications disabled")
            return
        self._thread = Thread(target=self._run, name="discord-client", daemon=True)
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        if not self._loop:
            return
        if self._queue:
            asyncio.run_coroutine_threadsafe(self._queue.put(None), self._loop)
        asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._queue = asyncio.Queue()
        for message in self._pending_messages:
            try:
                self._queue.put_nowait(message)
            except QueueFull:  # pragma: no cover - queue is unbounded
                _logger.warning(
                    "Unable to buffer pending Discord message", extra={"channel_id": message.channel_id}
                )
        self._pending_messages.clear()
        loop.create_task(self._dispatch_loop())
        try:
            loop.run_until_complete(self._client.start(self._token))
        except Exception as exc:  # pragma: no cover - difficult to simulate
            _logger.error("Discord client stopped unexpectedly", exc_info=exc)
        finally:
            if not self._client.is_closed():
                loop.run_until_complete(self._client.close())
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    # ------------------------------------------------------------------
    # Messaging API
    # ------------------------------------------------------------------
    async def _dispatch_loop(self) -> None:
        assert self._queue is not None
        await self._client.wait_until_ready()
        while True:
            message = await self._queue.get()
            if message is None:
                break
            channel = self._client.get_channel(message.channel_id)
            if channel is None:
                _logger.warning(
                    "Discord channel missing; dropping message", extra={"channel_id": message.channel_id}
                )
            else:
                try:
                    await channel.send(message.content)
                except Exception as exc:  # pragma: no cover - network errors
                    _logger.error("Failed to send Discord message", exc_info=exc)
            self._queue.task_done()

    def enqueue(self, content: str, channel_id: int) -> None:
        """Queue a message for asynchronous delivery."""

        if not channel_id:
            _logger.debug("Skipping Discord notification because no channel id was provided")
            return
        if not self._started:
            self.start()
        message = DiscordMessage(content=content, channel_id=channel_id)
        if not self._loop or not self._queue:
            self._pending_messages.append(message)
            return
        asyncio.run_coroutine_threadsafe(self._queue.put(message), self._loop)


class DiscordClient:
    """Compatibility wrapper used by legacy code paths."""

    def __init__(self, service: Optional[DiscordNotificationService] = None) -> None:
        self._service = service or DiscordNotificationService()

    def send_message(self, message: str, channel_id: int) -> None:
        self._service.enqueue(message, channel_id)
