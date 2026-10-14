"""E2E: creating an Abstract sensor through the panel's in-panel form (UI-2).

Unlike test_config_flow_e2e.py (which drives HA's native config flow), this
exercises the sidebar panel's own admin-gated form: enable Edit mode, add a
sensor, pick a live source entity, save, and confirm the real entity appears.
"""
from __future__ import annotations

import re
import time

import requests


def _abstract_power_ids(hass_base_url: str, token: str) -> set[str]:
    resp = requests.get(
        f"{hass_base_url}/api/states",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return {
        s["entity_id"]
        for s in resp.json()
        if s["entity_id"].startswith("sensor.abstract_power")
    }


def _pick_source(page, panel, name: str) -> None:
    """Select a source entity through the labelled entity picker, tolerating
    both the dialog and the inline combo-box presentations."""
    field = panel.get_by_label("Source entities")
    field.click()

    source_dialog = page.get_by_role("dialog", name="Source entities")
    if source_dialog.count():
        search = source_dialog.get_by_placeholder("Search", exact=True)
        search.wait_for(state="visible", timeout=5000)
        search.press_sequentially(name, delay=100)
        source_dialog.get_by_text(name, exact=False).first.click()
        # A multi-select picker may require an explicit confirm.
        confirm = source_dialog.get_by_role(
            "button", name=re.compile(r"^(save|done|close)$", re.IGNORECASE)
        )
        if confirm.count():
            confirm.first.click()
    else:
        field.press_sequentially(name, delay=100)
        page.get_by_text(name, exact=False).first.click()


def test_panel_form_creates_live_entity(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page
    before = _abstract_power_ids(hass_base_url, hass_bearer_token)

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)

    # Admin-gated Edit mode exposes the create form.
    panel.get_by_role("button", name=re.compile(r"^edit mode$", re.IGNORECASE)).click()
    panel.get_by_role("button", name=re.compile(r"^add sensor$", re.IGNORECASE)).click()

    save = panel.get_by_role("button", name=re.compile(r"^save$", re.IGNORECASE))
    save.wait_for(state="visible", timeout=10000)

    _pick_source(page, panel, "Fridge Power")
    save.click()

    # Confirm through the states API (robust against panel/UI render timing).
    new_ids: set[str] = set()
    for _ in range(40):
        new_ids = _abstract_power_ids(hass_base_url, hass_bearer_token) - before
        if new_ids:
            break
        time.sleep(0.5)

    assert new_ids, (
        "expected a new abstract_power entity after submitting the panel's "
        "create form"
    )
