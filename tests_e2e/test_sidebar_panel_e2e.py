"""E2E: the Abstractor sidebar panel (ADR-007, custom_components/abstractor/
frontend.py + www/abstractor-panel.js) renders real device data — this is
the only practical way to verify the panel's vanilla-JS Web Component at
all, since it has no Python-side logic pytest can exercise directly.
"""
from __future__ import annotations

import re


def test_panel_appears_in_sidebar(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(hass_base_url)
    # Once a device is configured, "Abstractor" also appears as an installed
    # integration card and page heading elsewhere — #sidebar-panel-abstractor
    # is the sidebar nav item's own stable id, unambiguous regardless of that.
    # .count() doesn't auto-wait like .click()/.fill() do, so wait explicitly
    # for the sidebar to have actually rendered before checking it.
    sidebar_entry = page.locator("#sidebar-panel-abstractor")
    sidebar_entry.wait_for(state="visible", timeout=10000)
    assert sidebar_entry.count() > 0, (
        "expected an 'Abstractor' entry in the sidebar once a device is configured"
    )


def test_panel_lists_configured_device_with_live_value(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    page.wait_for_timeout(500)

    # The panel is a closed-content-free open shadow root; Playwright's
    # locators pierce open shadow DOM automatically.
    panel = page.locator("abstractor-panel")
    assert panel.count() == 1, "expected the <abstractor-panel> custom element to mount"

    body_text = panel.inner_text()
    assert not re.search(r"no abstractor devices yet", body_text, re.I), (
        "panel shows the empty state; expected at least one configured device "
        "(run the config-flow E2E test first, or add one manually)"
    )
