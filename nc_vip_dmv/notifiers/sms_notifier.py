from __future__ import annotations

import os
from typing import Optional

from twilio.rest import Client


class SMSNotifier:
    def __init__(
        self,
        account_sid_env: str = "TWILIO_ACCOUNT_SID",
        auth_token_env: str = "TWILIO_AUTH_TOKEN",
        from_number_env: str = "TWILIO_FROM_NUMBER",
    ) -> None:
        self.account_sid = os.getenv(account_sid_env, "").strip()
        self.auth_token = os.getenv(auth_token_env, "").strip()
        self.from_number = os.getenv(from_number_env, "").strip()
        self._client: Optional[Client] = None

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    async def send_sms(self, to_number: str, message: str) -> None:
        if not self.is_configured():
            return
        # Twilio client is sync; run in thread to avoid blocking
        from anyio.to_thread import run_sync

        def _send():
            client = self._get_client()
            client.messages.create(to=to_number, from_=self.from_number, body=message)

        await run_sync(_send)
