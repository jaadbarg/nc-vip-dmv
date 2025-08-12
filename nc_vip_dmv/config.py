from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


class DiscordConfig(BaseModel):
    enabled: bool = True
    webhook_env: str = Field(default="DISCORD_WEBHOOK_URL")


class SMSConfig(BaseModel):
    enabled: bool = False
    account_sid_env: str = Field(default="TWILIO_ACCOUNT_SID")
    auth_token_env: str = Field(default="TWILIO_AUTH_TOKEN")
    from_number_env: str = Field(default="TWILIO_FROM_NUMBER")
    test_to_number_env: str = Field(default="TWILIO_TEST_TO_NUMBER")


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host_env: str = Field(default="SMTP_HOST")
    smtp_port_env: str = Field(default="SMTP_PORT")
    smtp_user_env: str = Field(default="SMTP_USERNAME")
    smtp_pass_env: str = Field(default="SMTP_PASSWORD")
    from_email_env: str = Field(default="SMTP_FROM_EMAIL")
    test_to_email_env: str = Field(default="SMTP_TEST_TO_EMAIL")
    use_tls_env: str = Field(default="SMTP_USE_TLS")
    use_ssl_env: str = Field(default="SMTP_USE_SSL")


class NotifiersConfig(BaseModel):
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    sms: SMSConfig = Field(default_factory=SMSConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


class OfficeConfig(BaseModel):
    name: str
    url: Optional[str] = None


class SettingsConfig(BaseModel):
    check_interval_seconds: int = 5
    max_concurrent_checks: int = 3
    headless: bool = True
    timezone: str = "America/New_York"
    state_file: str = "state.json"
    state_ttl_hours: int = 12
    subscriptions_file: str = "subscriptions.json"


class AppConfig(BaseModel):
    checker: str = Field(default="playwright")
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    notifiers: NotifiersConfig = Field(default_factory=NotifiersConfig)
    offices: List[OfficeConfig] = Field(default_factory=list)
    admin_token_env: str = Field(default="NCVIP_ADMIN_TOKEN")


def load_config(path: str | Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig.model_validate(data)
