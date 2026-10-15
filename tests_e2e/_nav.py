"""Shared Playwright navigation helper for the Abstractor E2E suite."""
from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page


def goto_settled(page: Page, url: str, *, attempts: int = 3) -> None:
    """Navigate, retrying the SPA's client-side-navigation race.

    Creating or updating an Abstractor config entry fires a Home Assistant
    config-entry reload; the SPA can still be performing its own client-side
    navigation when a test navigates, which aborts the in-flight ``goto``
    (``net::ERR_ABORTED``). A plain ``page.goto`` then fails even though the
    target page is perfectly reachable. Retry until the navigation settles.
    """
    for attempt in range(attempts):
        try:
            page.goto(url)
            return
        except PlaywrightError:
            if attempt == attempts - 1:
                raise
            page.wait_for_timeout(1000)
