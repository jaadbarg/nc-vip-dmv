from __future__ import annotations

from typing import List, Dict
from urllib.parse import urljoin

from playwright.async_api import async_playwright

BASE = "https://skiptheline.ncdot.gov/webapp/#/"


async def discover_offices_playwright() -> List[Dict[str, str]]:
    """Discover all office names and URLs by crawling the main listings.

    Returns a list of {"name": str, "url": str}.
    """
    results: dict[str, str] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            # Try common landing pages
            for path in ["", "locations"]:
                url = BASE + path
                await page.goto(url, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                anchors = await page.locator('a[href*="#/location/"]').all()
                for a in anchors:
                    href = await a.get_attribute("href")
                    name = (await a.inner_text() or "").strip()
                    if not href:
                        continue
                    if href.startswith("#/location/"):
                        full = urljoin(BASE, href)
                    elif "/location/" in href:
                        full = href
                    else:
                        continue
                    # Prefer meaningful text; fallback to last path segment
                    if not name:
                        name = full.rsplit("/", 1)[-1].replace("-", " ")
                    results[name] = full
        finally:
            await context.close()
            await browser.close()

    return [{"name": k, "url": v} for k, v in sorted(results.items())]
