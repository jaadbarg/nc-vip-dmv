from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PWTimeout

BASE_URL = "https://skiptheline.ncdot.gov/"


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
            text = await self._visit_and_snapshot_spa(page, office_name, office_url)
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

    async def _visit_and_snapshot_spa(self, page: Page, office_name: str, office_url: Optional[str]) -> str:
        # Open root only (UUID flow must be created by the site)
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # Click "Make an Appointment" (or similar) to start a fresh session (UUID route)
        start_clicked = False
        start_selectors = [
            "role=link[name*='Make an Appointment' i]",
            "role=button[name*='Make an Appointment' i]",
            "text=/Make an Appointment/i",
            "role=link[name*='Start' i]",
            "text=/Start/i",
        ]
        for sel in start_selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(timeout=3000)
                await el.click()
                start_clicked = True
                break
            except Exception:
                continue

        # Accept/lightweight consent if present
        if start_clicked:
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            for consent_sel in [
                "role=button[name=/I (agree|accept)/i]",
                "text=/I (agree|accept)/i",
                "role=button[name=/Continue/i]",
                "text=/Continue/i",
            ]:
                try:
                    el = page.locator(consent_sel).first
                    await el.wait_for(timeout=1500)
                    await el.click()
                except Exception:
                    continue

        # Find and open the office by name
        normalized = office_name.strip().lower()

        # Try typing into a search field first
        tried_search = False
        try:
            input_candidates = [
                "input[placeholder*='search' i]",
                "input[aria-label*='search' i]",
                "input[type='search']",
            ]
            for inp_sel in input_candidates:
                inp = page.locator(inp_sel).first
                await inp.wait_for(timeout=2000)
                await inp.fill(office_name)
                await inp.press("Enter")
                tried_search = True
                break
        except Exception:
            pass

        # If no search or no result click, try clicking a matching element directly
        clicked = False
        candidates = [
            f"role=link[name*='{office_name}']",
            f"role=button[name*='{office_name}']",
            f"text=/{re.escape(office_name)}/i",
        ]
        for sel in candidates:
            try:
                el = page.locator(sel).first
                await el.wait_for(timeout=3000)
                await el.click()
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            # Fallback: scan all clickable-like elements and fuzzy-match text
            elements = page.locator("a, button, div, li").all()
            for el in elements:
                try:
                    t = (await el.inner_text()).strip()
                except Exception:
                    continue
                if not t:
                    continue
                if normalized in t.lower():
                    try:
                        await el.click()
                        clicked = True
                        break
                    except Exception:
                        continue

        # Wait a moment for appointment times to render, then snapshot
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        try:
            text = await page.evaluate("() => document.body.innerText")
        except Exception:
            text = ""
        try:
            html = await page.content()
        except Exception:
            html = ""
        return f"{text}\n\n---\nHTML_SNIPPET:\n{html[:5000]}"

    def _extract_slots(self, text: str) -> List[Slot]:
        if not text:
            return []
        time_pattern = re.compile(r"\b(\d{1,2}):(\d{2})\s?(AM|PM)\b", re.IGNORECASE)
        lines = text.splitlines()
        slots: List[Slot] = []
        for idx, line in enumerate(lines):
            if time_pattern.search(line):
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
