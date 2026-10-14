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
    both the dialog and the inline combo-box presentations.

    The multi-select picker's search field does not expose a stable
    placeholder, so the search input is addressed as the dialog's first input.
    """
    field = panel.get_by_label("Source entities")
    field.click()

    dialog = page.get_by_role("dialog", name="Source entities")
    scope = dialog if dialog.count() else panel
    search = scope.locator("input").first
    search.wait_for(state="visible", timeout=5000)
    search.press_sequentially(name, delay=100)

    option = scope.get_by_text(name, exact=False)
    if option.count():
        option.first.click()
    else:
        search.press("Enter")

    # A multi-select picker can require an explicit confirm.
    confirm = scope.get_by_role(
        "button", name=re.compile(r"^(save|done|ok|close|add)$", re.IGNORECASE)
    )
    if confirm.count():
        confirm.first.click()


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
