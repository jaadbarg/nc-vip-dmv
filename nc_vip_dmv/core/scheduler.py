from __future__ import annotations

import asyncio
from typing import Callable, Awaitable, Optional, List

from colorama import Fore, Style, init as colorama_init

from nc_vip_dmv.config import AppConfig
from nc_vip_dmv.core.state import StateStore
from nc_vip_dmv.notifiers.discord_notifier import DiscordNotifier
from nc_vip_dmv.notifiers.sms_notifier import SMSNotifier
from nc_vip_dmv.notifiers.email_notifier import EmailNotifier
from nc_vip_dmv.checkers.playwright_checker import PlaywrightChecker
from nc_vip_dmv.checkers.browseruse_checker import check_with_browser_use


colorama_init(autoreset=True)


class Scheduler:
    def __init__(self, config: AppConfig, notifications_enabled: bool = True) -> None:
        self.config = config
        self.state = StateStore(
            path=config.settings.state_file,
            ttl_hours=config.settings.state_ttl_hours,
        )
        # public latest results for UI
        self.latest_results: list[dict] = []
        # Optional subscriptions store (attached by the server)
        self._subscriptions = None  # type: ignore[var-annotated]
        # Global notifications switch (CLI) combined with config flag
        self.notifications_enabled = bool(notifications_enabled)
        self.discord = DiscordNotifier(webhook_env=config.notifiers.discord.webhook_env)
        self.sms = SMSNotifier(
            account_sid_env=config.notifiers.sms.account_sid_env,
            auth_token_env=config.notifiers.sms.auth_token_env,
            from_number_env=config.notifiers.sms.from_number_env,
        )
        self.email = EmailNotifier(
            smtp_host_env=config.notifiers.email.smtp_host_env,
            smtp_port_env=config.notifiers.email.smtp_port_env,
            smtp_user_env=config.notifiers.email.smtp_user_env,
            smtp_pass_env=config.notifiers.email.smtp_pass_env,
            from_email_env=config.notifiers.email.from_email_env,
            use_tls_env=config.notifiers.email.use_tls_env,
            use_ssl_env=config.notifiers.email.use_ssl_env,
        )

    def attach_subscriptions(self, store) -> None:
        self._subscriptions = store

    def _get_subscribed_emails(self, office_name: str) -> List[str]:
        if not self._subscriptions:
            return []
        # _subscriptions._data is a dict {email: [offices]}
        try:
            mapping = self._subscriptions._data  # type: ignore[attr-defined]
            emails = [email for email, offices in mapping.items() if office_name in (offices or [])]
            return emails
        except Exception:
            return []

    async def run(self, checker_override: Optional[str] = None, run_once: bool = False) -> None:
        checker_type = checker_override or self.config.checker
        interval = max(1, self.config.settings.check_interval_seconds)
        concurrency = max(1, self.config.settings.max_concurrent_checks)

        print(f"Using checker: {checker_type} | interval: {interval}s | concurrency: {concurrency}")
        if not self.notifications_enabled:
            print(Style.DIM + "Notifications disabled (console only)")

        if checker_type == "playwright":
            await self._run_with_playwright(interval, concurrency, run_once)
        elif checker_type == "browseruse":
            await self._run_with_browser_use(interval, concurrency, run_once)
        else:
            raise ValueError(f"Unknown checker type: {checker_type}")

    async def _run_with_playwright(self, interval: int, concurrency: int, run_once: bool) -> None:
        sem = asyncio.Semaphore(concurrency)
        async with PlaywrightChecker(headless=self.config.settings.headless) as checker:
            while True:
                await self._iteration_playwright(sem, checker)
                if run_once:
                    break
                await asyncio.sleep(interval)

    async def _iteration_playwright(self, sem: asyncio.Semaphore, checker: PlaywrightChecker) -> None:
        self.state.purge_expired()
        tasks = []
        results: list[dict] = []
        for office in self.config.offices:
            tasks.append(self._check_office_playwright(sem, checker, office.name, office.url, results))
        await asyncio.gather(*tasks)
        self.latest_results = results

    async def _check_office_playwright(self, sem: asyncio.Semaphore, checker: PlaywrightChecker, office_name: str, office_url: Optional[str], results_accumulator: list[dict]) -> None:
        async with sem:
            try:
                result = await checker.check_office(office_name, office_url)
                signatures = [s.signature() for s in result.slots]
                results_accumulator.append({
                    "office": office_name,
                    "url": office_url,
                    "available": result.available,
                    "count": len(signatures),
                    "samples": signatures[:5],
                })
                self._handle_result(result.office_name, result.office_url, result.available, signatures)
            except Exception as e:
                print(Fore.RED + f"[{office_name}] Error: {e}")

    async def _run_with_browser_use(self, interval: int, concurrency: int, run_once: bool) -> None:
        sem = asyncio.Semaphore(concurrency)
        while True:
            self.state.purge_expired()
            tasks = []
            results: list[dict] = []
            for office in self.config.offices:
                tasks.append(self._check_office_browser_use(sem, office.name, office.url, results))
            await asyncio.gather(*tasks)
            self.latest_results = results
            if run_once:
                break
            await asyncio.sleep(interval)

    async def _check_office_browser_use(self, sem: asyncio.Semaphore, office_name: str, office_url: Optional[str], results_accumulator: list[dict]) -> None:
        async with sem:
            try:
                result = await check_with_browser_use(office_name, office_url)
                signatures = [s.signature() for s in result.slots]
                results_accumulator.append({
                    "office": office_name,
                    "url": office_url,
                    "available": result.available,
                    "count": len(signatures),
                    "samples": signatures[:5],
                })
                self._handle_result(result.office_name, result.office_url, result.available, signatures)
            except Exception as e:
                print(Fore.RED + f"[{office_name}] Error: {e}")

    def _handle_result(self, office_name: str, office_url: Optional[str], available: bool, signatures: list[str]) -> None:
        if available:
            print(Fore.GREEN + f"[{office_name}] Slots detected: {len(signatures)}")
            for sig in (signatures[:5] if signatures else ["AVAILABLE"]):
                print(Fore.GREEN + f"  - {sig}")
            if self.notifications_enabled:
                # Discord
                if self.config.notifiers.discord.enabled:
                    for sig in signatures or ["AVAILABLE"]:
                        if not self.state.was_seen(office_name, sig):
                            self.state.mark_seen(office_name, sig)
                            asyncio.create_task(self._notify_discord(office_name, office_url, sig))
                # SMS (single test recipient)
                if self.config.notifiers.sms.enabled and self.sms.is_configured():
                    for sig in signatures or ["AVAILABLE"]:
                        if not self.state.was_seen(office_name, f"SMS|{sig}"):
                            self.state.mark_seen(office_name, f"SMS|{sig}")
                            asyncio.create_task(self._notify_sms(office_name, office_url, sig))
                # Email (fan out to subscribers)
                if self.config.notifiers.email.enabled and self.email.is_configured():
                    recipients = self._get_subscribed_emails(office_name)
                    # Fallback to test email if no subscribers
                    if not recipients:
                        import os
                        fallback = os.getenv(self.config.notifiers.email.test_to_email_env, "").strip()
                        recipients = [fallback] if fallback else []
                    for to_email in recipients:
                        for sig in signatures or ["AVAILABLE"]:
                            if not self.state.was_seen(office_name, f"EMAIL|{to_email}|{sig}"):
                                self.state.mark_seen(office_name, f"EMAIL|{to_email}|{sig}")
                                asyncio.create_task(self._notify_email_to(to_email, office_name, office_url, sig))
        else:
            print(Style.DIM + f"[{office_name}] No availability")

    async def _notify_discord(self, office_name: str, office_url: Optional[str], signature: str) -> None:
        if not self.notifications_enabled:
            return
        if not self.config.notifiers.discord.enabled:
            return
        if self.discord.is_configured():
            await self.discord.send_message(
                title=f"NC DMV availability at {office_name}",
                description=f"New slot detected: {signature}",
                url=office_url,
            )

    async def _notify_sms(self, office_name: str, office_url: Optional[str], signature: str) -> None:
        if not self.notifications_enabled:
            return
        if not (self.config.notifiers.sms.enabled and self.sms.is_configured()):
            return
        import os
        to_number = os.getenv(self.config.notifiers.sms.test_to_number_env, "").strip()
        if not to_number:
            return
        message = f"NC DMV availability at {office_name}: {signature}\n{office_url or ''}"
        await self.sms.send_sms(to_number=to_number, message=message)

    async def _notify_email_to(self, to_email: str, office_name: str, office_url: Optional[str], signature: str) -> None:
        if not self.notifications_enabled:
            return
        if not (self.config.notifiers.email.enabled and self.email.is_configured()):
            return
        subject = f"NC DMV availability at {office_name}"
        body = f"New slot detected: {signature}\n{office_url or ''}"
        await self.email.send_email(to_email=to_email, subject=subject, body=body)
