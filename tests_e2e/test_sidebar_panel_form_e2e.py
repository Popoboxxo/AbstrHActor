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
    return {s["entity_id"] for s in resp.json() if s["entity_id"].startswith("sensor.abstract_power")}


def _set_source(panel, entity_id: str) -> None:
    """Set the source picker's value deterministically.

    The HA entity picker's dropdown is a separate overlay component; driving
    its search/option list is brittle on a shared instance (overlays intercept
    pointer events). The picker is HA-owned UI, so this test pins the panel's
    own contract: the form reads the picker value and submits it.
    """
    picker = panel.locator("ha-entity-picker").first
    picker.wait_for(state="attached", timeout=10000)
    picker.evaluate(
        """
        (el, value) => {
          el.value = [value];
          el.dispatchEvent(new CustomEvent("value-changed", {
            detail: { value: [value] },
            bubbles: true,
            composed: true,
          }));
        }
        """,
        entity_id,
    )


def test_panel_form_creates_live_entity(logged_in_page, hass_base_url, hass_bearer_token):
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

    _set_source(panel, "sun.sun")
    save.click()

    # Confirm through the states API (robust against panel/UI render timing).
    new_ids: set[str] = set()
    for _ in range(40):
        new_ids = _abstract_power_ids(hass_base_url, hass_bearer_token) - before
        if new_ids:
            break
        time.sleep(0.5)

    assert new_ids, "expected a new abstract_power entity after submitting the panel's create form"


def test_panel_ws_rejects_schema_violation_without_side_effects(logged_in_page, hass_base_url, hass_bearer_token):
    """A bad payload driven straight at the authenticated WS layer must be
    rejected by the shared schema (WS-1) and leave the installation untouched.
    """
    page = logged_in_page
    before = _abstract_power_ids(hass_base_url, hass_bearer_token)

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)

    rejected = page.evaluate(
        """
        (async () => {
          const h = document.querySelector("home-assistant").hass;
          if (!h || !h.callWS) {
            throw new Error("frontend hass object not exposed on the panel page");
          }
          try {
            await h.callWS({
              type: "abstractor/subentry/create",
              data: {
                device_type: "power",
                source_entity_ids: ["sensor.fridge_power"],
                aggregation: "banana",
              },
            });
            return false;
          } catch (e) {
            return true;
          }
        })()
        """
    )
    assert rejected is True, "expected the shared subentry schema to reject aggregation=banana"

    after = _abstract_power_ids(hass_base_url, hass_bearer_token)
    assert after == before, "a rejected payload must not create or modify any abstract entity"
