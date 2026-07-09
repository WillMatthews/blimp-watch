"""Pluggable push notifications: ntfy (default), Telegram, or a generic webhook.

Which backend is used is decided purely by which environment variables are set.
Configure zero backends and transitions are just logged (handy for a dry run).
"""
from __future__ import annotations

import logging
import os

import aiohttp

log = logging.getLogger("blimp.notify")


class Notifier:
    def __init__(self) -> None:
        # ntfy: set NTFY_TOPIC (uses NTFY_SERVER, default https://ntfy.sh)
        self.ntfy_topic = os.getenv("NTFY_TOPIC")
        self.ntfy_server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        self.ntfy_token = os.getenv("NTFY_TOKEN")  # optional bearer for protected servers
        # Telegram: set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat = os.getenv("TELEGRAM_CHAT_ID")
        # Generic webhook: set WEBHOOK_URL (receives JSON {title, message, priority, tags, url})
        self.webhook = os.getenv("WEBHOOK_URL")

    @property
    def backends(self) -> list[str]:
        b = []
        if self.ntfy_topic:
            b.append(f"ntfy({self.ntfy_server}/{self.ntfy_topic})")
        if self.tg_token and self.tg_chat:
            b.append("telegram")
        if self.webhook:
            b.append("webhook")
        return b

    async def send(
        self,
        session: aiohttp.ClientSession,
        title: str,
        message: str,
        *,
        priority: str = "default",  # ntfy: min|low|default|high|urgent
        tags: list[str] | None = None,
        click: str | None = None,
    ) -> None:
        tags = tags or []
        log.info("NOTIFY [%s] %s — %s", priority, title, message)
        if self.ntfy_topic:
            await self._ntfy(session, title, message, priority, tags, click)
        if self.tg_token and self.tg_chat:
            await self._telegram(session, title, message, click)
        if self.webhook:
            await self._webhook(session, title, message, priority, tags, click)

    async def _ntfy(self, session, title, message, priority, tags, click) -> None:
        headers = {
            "Title": title,
            "Priority": priority,
            "Tags": ",".join(tags) if tags else "airplane",
        }
        if click:
            headers["Click"] = click
        if self.ntfy_token:
            headers["Authorization"] = f"Bearer {self.ntfy_token}"
        url = f"{self.ntfy_server}/{self.ntfy_topic}"
        try:
            async with session.post(url, data=message.encode("utf-8"), headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status >= 300:
                    log.warning("ntfy -> HTTP %s: %s", r.status, await r.text())
        except Exception as e:  # noqa: BLE001
            log.warning("ntfy send failed: %s", e)

    async def _telegram(self, session, title, message, click) -> None:
        text = f"*{title}*\n{message}"
        if click:
            text += f"\n{click}"
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {"chat_id": self.tg_chat, "text": text, "parse_mode": "Markdown",
                   "disable_web_page_preview": False}
        try:
            async with session.post(url, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status >= 300:
                    log.warning("telegram -> HTTP %s: %s", r.status, await r.text())
        except Exception as e:  # noqa: BLE001
            log.warning("telegram send failed: %s", e)

    async def _webhook(self, session, title, message, priority, tags, click) -> None:
        payload = {"title": title, "message": message, "priority": priority,
                   "tags": tags, "url": click}
        try:
            async with session.post(self.webhook, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status >= 300:
                    log.warning("webhook -> HTTP %s: %s", r.status, await r.text())
        except Exception as e:  # noqa: BLE001
            log.warning("webhook send failed: %s", e)
