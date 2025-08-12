from __future__ import annotations

import os
from typing import Iterable, List, Optional

import httpx


class DiscordNotifier:
    def __init__(self, webhook_env: str = "DISCORD_WEBHOOK_URL") -> None:
        self.webhook_url = os.getenv(webhook_env, "").strip()

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    async def send_message(
        self,
        title: str,
        description: str,
        url: Optional[str] = None,
        fields: Optional[List[dict]] = None,
    ) -> None:
        if not self.is_configured():
            return

        embed = {
            "title": title,
            "description": description,
            "type": "rich",
        }
        if url:
            embed["url"] = url
        if fields:
            embed["fields"] = fields

        payload = {"embeds": [embed]}

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(self.webhook_url, json=payload)
