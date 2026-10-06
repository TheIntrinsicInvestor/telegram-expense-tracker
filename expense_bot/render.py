"""Turns card HTML into a PNG with headless Chromium. One browser is kept and reused."""

import asyncio

from playwright.async_api import Browser, Playwright, async_playwright

PAGE_WIDTH = 752
SCALE = 2  # retina-sharp in Telegram


class CardRenderer:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch()
        return self._browser

    async def render(self, html: str) -> bytes:
        async with self._lock:
            browser = await self._ensure_browser()
            page = await browser.new_page(viewport={"width": PAGE_WIDTH, "height": 600}, device_scale_factor=SCALE)
            try:
                await page.set_content(html, wait_until="load")
                await page.evaluate("document.fonts.ready")
                return await page.locator(".page").screenshot(type="png")
            finally:
                await page.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
