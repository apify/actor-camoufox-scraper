from collections.abc import Coroutine
from typing import Any

from playwright.async_api import Page, FloatRect, TimeoutError as PlaywrightTimeoutError


async def is_cloudflare(page: Page) -> bool:
    return bool(await page.get_by_text("Cloudflare").first.all_inner_texts())


async def get_challenge_bounding_box(
    page: Page,
) -> Coroutine[Any, Any, FloatRect | None]:
    try:
        return await page.locator("css=.main-content div").first.bounding_box(
            timeout=1000
        )
    except PlaywrightTimeoutError:
        return None
