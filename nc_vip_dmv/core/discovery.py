from __future__ import annotations

from typing import List, Dict
from urllib.parse import urljoin

from playwright.async_api import async_playwright

BASE = "https://skiptheline.ncdot.gov/"


async def discover_offices_playwright() -> List[Dict[str, str]]:
    """Discover office names (and URLs if available) from the SPA locations page.

    Returns a list of {"name": str, "url": str | ""}.
    """
    results: dict[str, str] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            url = BASE
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            # From the root, click into making an appointment / locations flow
            started = False
            for sel in [
                "role=link[name*='Make an Appointment' i]",
                "role=button[name*='Make an Appointment' i]",
                "text=/Make an Appointment/i",
                "role=link[name*='Start' i]",
                "text=/Start/i",
            ]:
                try:
                    el = page.locator(sel).first
                    await el.wait_for(timeout=2000)
                    await el.click()
                    started = True
                    break
                except Exception:
                    continue

            if started:
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

            # Cards are rendered in a grid; collect visible text and hrefs (if any exist)
            cards = await page.locator('a[href*="#/location/"]').all()
            if cards:
                for a in cards:
                    try:
                        href = await a.get_attribute("href")
                        name = (await a.inner_text() or "").strip()
                    except Exception:
                        continue
                    if not name:
                        continue
                    full = urljoin(BASE, href) if href else ""
                    results[name] = full
            else:
                # Fallback: read any card-like containers and pull their titles
                containers = page.locator("div, a, button").all()
                for el in containers:
                    try:
                        t = (await el.inner_text()).strip()
                    except Exception:
                        continue
                    if not t or len(t) > 120:
                        continue
                    # Heuristic: title case single-line likely is the office name
                    if "\n" not in t and t[:1].isupper():
                        results.setdefault(t, "")
        finally:
            await context.close()
            await browser.close()

    return [{"name": k, "url": v} for k, v in sorted(results.items())]
