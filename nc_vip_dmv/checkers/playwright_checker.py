from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


@dataclass
class Slot:
    label: str
    date: Optional[str]
    time: Optional[str]

    def signature(self) -> str:
        return f"{self.date or ''}|{self.time or ''}|{self.label}"


@dataclass
class AvailabilityResult:
    office_name: str
    office_url: Optional[str]
    available: bool
    slots: List[Slot]
    raw_snapshot_text: Optional[str] = None


class PlaywrightChecker:
    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "PlaywrightChecker":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        await self._pw.stop()

    async def check_office(self, office_name: str, office_url: Optional[str]) -> AvailabilityResult:
        if not self._context:
            raise RuntimeError("PlaywrightChecker used before initialization")

        page = await self._context.new_page()
        try:
            text = await self._visit_and_snapshot(page, office_url)
            slots = self._extract_slots(text)
            available = len(slots) > 0 and ("no appointments" not in text.lower())
            return AvailabilityResult(
                office_name=office_name,
                office_url=office_url,
                available=available,
                slots=slots,
                raw_snapshot_text=text[:4000] if text else None,
            )
        finally:
            await page.close()

    async def _visit_and_snapshot(self, page: Page, url: Optional[str]) -> str:
        if not url:
            # If no direct URL provided, fall back to a neutral page
            return ""

        # Retry a few times in case of flakiness
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True
        ):
            with attempt:
                await page.goto(url, wait_until="domcontentloaded")
                # Give single-page apps time to fetch data
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                # Grab visible text content from the page
                content = await page.content()
                # Also try evaluating document.body.innerText for readable text
                try:
                    text = await page.evaluate("() => document.body.innerText")
                except Exception:
                    text = ""
                return f"{text}\n\n---\nHTML_SNIPPET:\n{content[:5000]}"

        return ""

    def _extract_slots(self, text: str) -> List[Slot]:
        if not text:
            return []

        # Heuristic: find typical time patterns; capture lines around them as labels
        time_pattern = re.compile(r"\b(\d{1,2}):(\d{2})\s?(AM|PM)\b", re.IGNORECASE)
        lines = text.splitlines()
        slots: List[Slot] = []
        for idx, line in enumerate(lines):
            if time_pattern.search(line):
                # Try to assemble a nearby date label
                window = " ".join(lines[max(0, idx - 2) : min(len(lines), idx + 3)])
                date_match = re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*?\b(\d{1,2}/\d{1,2}/\d{2,4}|\w+\s+\d{1,2},\s*\d{4})", window, re.IGNORECASE)
                time_match = time_pattern.search(line)
                label = window.strip()[:120]
                slots.append(
                    Slot(
                        label=label,
                        date=date_match.group(0) if date_match else None,
                        time=time_match.group(0) if time_match else None,
                    )
                )
        return slots
