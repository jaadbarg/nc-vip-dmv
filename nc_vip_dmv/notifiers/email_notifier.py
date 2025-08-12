from __future__ import annotations

import os
from typing import Optional

import aiosmtplib
from email.message import EmailMessage


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "y"}


class EmailNotifier:
    def __init__(
        self,
        smtp_host_env: str = "SMTP_HOST",
        smtp_port_env: str = "SMTP_PORT",
        smtp_user_env: str = "SMTP_USERNAME",
        smtp_pass_env: str = "SMTP_PASSWORD",
        from_email_env: str = "SMTP_FROM_EMAIL",
        use_tls_env: str = "SMTP_USE_TLS",
        use_ssl_env: str = "SMTP_USE_SSL",
    ) -> None:
        self.smtp_host = os.getenv(smtp_host_env, "").strip()
        self.smtp_port = int(os.getenv(smtp_port_env, "587") or 587)
        self.smtp_username = os.getenv(smtp_user_env, "").strip()
        self.smtp_password = os.getenv(smtp_pass_env, "").strip()
        self.from_email = os.getenv(from_email_env, "").strip()
        self.use_tls = _env_bool(use_tls_env, default=True)
        self.use_ssl = _env_bool(use_ssl_env, default=False)

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.from_email)

    async def send_email(self, to_email: str, subject: str, body: str) -> None:
        if not self.is_configured():
            return

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        if self.use_ssl:
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username or None,
                password=self.smtp_password or None,
                use_tls=True,
            )
        else:
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username or None,
                password=self.smtp_password or None,
                start_tls=self.use_tls,
            )
