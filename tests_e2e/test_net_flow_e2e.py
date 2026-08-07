"""E2E: REQ-CORE-005 net-flow subtraction against live, controllable
virtual sensors (github.com/twrecked/hass-virtual). Values are set via the
`virtual.set` service through the real HA REST API — the same mechanism an
automation would use — then the abstracted sensor's displayed value is
read back from the entities UI to prove the whole pipeline (source states
-> coordinator -> filter pipeline -> entity) works end to end, not just
filters.py in isolation.
"""
from __future__ import annotations

import re

import requests


def _call_virtual_set(hass_base_url: str, token: str, entity_id: str, value: float) -> None:
    resp = requests.post(
        f"{hass_base_url}/api/services/virtual/set",
        headers={"Authorization": f"Bearer {token}"},
        json={"entity_id": entity_id, "value": str(value)},
        timeout=10,
    )
    resp.raise_for_status()


def _entity_state_text(page, hass_base_url: str, entity_id: str) -> str:
    page.goto(f"{hass_base_url}/config/entities")
    page.get_by_placeholder(re.compile("search", re.I)).fill(entity_id)
    page.wait_for_timeout(300)
    row = page.locator("[role='row']", has_text=entity_id).first
    return row.inner_text()


def test_net_flow_subtracts_discharge_from_charge(
    logged_in_page, hass_base_url, hass_bearer_token
):
    _call_virtual_set(
        hass_base_url, hass_bearer_token, "sensor.battery_charge_power", 500
    )
    _call_virtual_set(
        hass_base_url, hass_bearer_token, "sensor.battery_discharge_power", 120
    )

    page = logged_in_page
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_role("button", name=re.compile("add integration", re.I)).click()
    page.get_by_placeholder(re.compile("search for a brand", re.I)).fill("Abstractor")
    page.get_by_text("Abstractor", exact=True).click()

    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    page.get_by_placeholder(re.compile("search", re.I)).fill("Battery Charge Power")
    page.get_by_text("Battery Charge Power", exact=False).first.click()

    page.get_by_role("button", name=re.compile("^(submit|ok)$", re.I)).click()
    page.wait_for_timeout(500)
    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()

    # Reconfigure to add the net-subtract source (Battery Discharge Power).
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_text("Abstractor", exact=True).first.click()
    page.get_by_role("button", name=re.compile("configure", re.I)).click()
    page.get_by_label(re.compile("subtract entity", re.I)).click()
    page.get_by_placeholder(re.compile("search", re.I)).fill("Battery Discharge Power")
    page.get_by_text("Battery Discharge Power", exact=False).first.click()
    page.keyboard.press("Escape")
    page.get_by_role("button", name=re.compile("^submit$", re.I)).click()
    page.wait_for_timeout(1000)

    page.goto(f"{hass_base_url}/config/entities")
    page.get_by_placeholder(re.compile("search", re.I)).fill("Power")
    body = page.inner_text("body")
    assert "380" in body, (
        "expected the net-flow entity to show 500 - 120 = 380 W after setting "
        f"the two virtual sources; entities page did not contain '380'"
    )
