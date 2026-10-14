"""Minimal smoke E2E test for the Abstractor sidebar panel (UI phase 0)."""
from __future__ import annotations

import re


def test_panel_mounts(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)
    assert panel.count() == 1


def test_tabs_render(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)
    for label in ("Devices", "Health", "Settings"):
        btn = panel.get_by_role("button", name=label)
        btn.wait_for(state="visible", timeout=10000)
        assert btn.count() >= 1


def test_export_button_calls_export_data(logged_in_page, hass_base_url):
    page = logged_in_page
    sent_frames: list[str] = []
    page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent_frames.append(payload)))

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    export_button = panel.get_by_role("button", name=re.compile("export", re.IGNORECASE))
    export_button.wait_for(state="visible", timeout=10000)
    export_button.click()
    page.wait_for_timeout(1000)

    calls = [f for f in sent_frames if '"export_data"' in f]
    assert calls, "expected Export to send an abstractor.export_data websocket frame"
    assert any('"return_response":true' in f.replace(" ", "") for f in calls), calls


def test_edit_button_navigates_to_device_page(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    # Anchor to the card's exact "Edit" label: the header also has an
    # "Edit mode" toggle whose accessible name contains "edit".
    edit_button = panel.get_by_role("button", name=re.compile(r"^edit$", re.IGNORECASE)).first
    edit_button.wait_for(state="visible", timeout=10000)
    edit_button.click()
    page.wait_for_url(re.compile(r"/config/devices/device/"), timeout=10000)
