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
import time

import requests

ADD_SENSOR_SUBENTRY_NAME = re.compile("add.*sensor", re.I)
SUBMIT_BUTTON_NAME = re.compile("submit|ok", re.I)


def _dismiss_success_dialog(page) -> None:
    finish_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if finish_button.count():
        finish_button.first.click()
        page.wait_for_timeout(300)


def _ensure_root_entry(page, hass_base_url: str) -> None:
    """Create the singleton Abstractor root entry (Task 3+: "Add
    integration" only creates this empty parent now), or no-op if a
    previous test in this run already created it."""
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    if page.get_by_role("button", name=ADD_SENSOR_SUBENTRY_NAME).count():
        return

    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    # Custom HA elements (ha-fab, mwc-button, ...) don't reliably expose an
    # accessible role="button" to Playwright's get_by_role — get_by_text is
    # what actually finds them (confirmed via manual DOM inspection).
    page.get_by_text("Add integration", exact=False).click()
    brand_search = page.get_by_placeholder(re.compile("search for a brand", re.I))
    brand_search.fill("Abstractor")
    brand_search.press("Enter")
    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def _add_sensor_subentry(page, hass_base_url: str, source_name: str) -> None:
    """Drive the subentry "Add Abstract sensor" flow — same pattern as
    tests_e2e/test_config_flow_e2e.py."""
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=ADD_SENSOR_SUBENTRY_NAME).click()
    page.wait_for_timeout(500)

    # This picker opens as its own role="dialog" (named after the field's
    # aria-label) layered on top of the subentry form dialog, which itself
    # sits on top of the domain listing page underneath both — scoping to
    # it avoids both the shared "Search" placeholder ambiguity and
    # get_by_text(...).first silently matching a same-named element hidden
    # under the modal overlay (DOM/document order, not visual stacking
    # order) instead of the one actually in this dialog — confirmed
    # against a live instance.
    source_dialog = page.get_by_role("dialog", name="Source entity")
    page.get_by_label("Source entity", exact=True).click()
    # ha-entity-picker filters as-you-type off real input events — .fill()
    # sets the value without dispatching them, so the dropdown never narrows.
    # press_sequentially (not raw keyboard.type) re-focuses its target
    # locator itself, surviving the picker's internal re-renders — but a
    # delay is required between characters, or a stray keystroke can land
    # on HA's global quick-bar hotkeys (bound to keydown on an unfocused
    # document, e.g. "d" for its Devices tab) instead of the field.
    search_field = source_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially(source_name, delay=100)
    source_dialog.get_by_text(source_name, exact=False).first.click()

    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def _call_virtual_set(hass_base_url: str, token: str, entity_id: str, value: float) -> None:
    resp = requests.post(
        f"{hass_base_url}/api/services/virtual/set",
        headers={"Authorization": f"Bearer {token}"},
        json={"entity_id": entity_id, "value": str(value)},
        timeout=10,
    )
    resp.raise_for_status()


def _abstract_power_entity_ids(hass_base_url: str, token: str) -> set[str]:
    resp = requests.get(
        f"{hass_base_url}/api/states",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return {
        s["entity_id"] for s in resp.json()
        if s["entity_id"].startswith("sensor.abstract_power")
    }


def test_net_flow_subtracts_discharge_from_charge(
    logged_in_page, hass_base_url, hass_bearer_token
):
    _call_virtual_set(
        hass_base_url, hass_bearer_token, "sensor.virtual_battery_charge_power", 500
    )
    _call_virtual_set(
        hass_base_url, hass_bearer_token, "sensor.virtual_battery_discharge_power", 120
    )
    entity_ids_before = _abstract_power_entity_ids(hass_base_url, hass_bearer_token)

    page = logged_in_page
    _ensure_root_entry(page, hass_base_url)
    _add_sensor_subentry(page, hass_base_url, "Battery Charge Power")

    # Reconfigure to add the net-subtract source (Battery Discharge Power)
    # via this sensor's own subentry Reconfigure flow. Task 3+ moved
    # sensor settings off the parent config entry onto a per-sensor
    # subentry, so there's no more single "Configure" gear per integration
    # entry to click; each subentry gets its own, whose accessible name is
    # exactly the translated
    # config_subentries.sensor.initiate_flow.reconfigure string (confirmed
    # via DOM inspection against a live instance). Once other tests in the
    # suite have added their own sensors, there may be more than one such
    # button — ours is the most recently created, i.e. the last one.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role(
        "button", name=re.compile("reconfigure abstract sensor", re.I)
    ).last.click()
    page.wait_for_timeout(500)
    # Each picker's aria-label works regardless of translation state, but
    # WHICH text it holds depends on whether translations/en.json loaded —
    # raw schema key if not, translated label ("Subtract entity (net flow)")
    # if so. Scoped to this field's own dialog for the same reason as
    # _add_sensor_subentry above (shared "Search" placeholder + possible
    # same-name matches hidden under the modal overlay elsewhere on the
    # page).
    net_subtract_label = re.compile("net_subtract_entity_id|Subtract entity", re.I)
    page.get_by_label(net_subtract_label).click()
    picker_dialog = page.get_by_role("dialog", name=net_subtract_label)
    search_field = picker_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Battery Discharge Power", delay=100)
    picker_dialog.get_by_text("Battery Discharge Power", exact=False).first.click()
    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(1000)

    # Reading the value back through the entities UI (search + row text)
    # proved flaky under load — a search box that's visible one run and
    # not-yet-rendered the next, timing races with the coordinator's own
    # update cycle, etc. The REST API is what the UI itself reads from
    # anyway, so poll the actual entity's state directly: identify our
    # entity via the set difference against the baseline captured before
    # this test added anything, then wait for the coordinator to catch up
    # to the virtual sensor values set at the top of this test.
    # The entity registry can take a moment to catch up with the states API
    # after submitting the config flow — poll instead of a one-shot check.
    new_entity_ids = set()
    for _ in range(20):
        entity_ids_after = _abstract_power_entity_ids(hass_base_url, hass_bearer_token)
        new_entity_ids = entity_ids_after - entity_ids_before
        if len(new_entity_ids) == 1:
            break
        time.sleep(0.5)
    assert len(new_entity_ids) == 1, (
        f"expected exactly one new abstract_power entity, got {new_entity_ids}"
    )
    net_flow_entity_id = next(iter(new_entity_ids))

    state = None
    for _ in range(20):
        resp = requests.get(
            f"{hass_base_url}/api/states/{net_flow_entity_id}",
            headers={"Authorization": f"Bearer {hass_bearer_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        state = resp.json()["state"]
        try:
            if float(state) == 380:
                break
        except ValueError:
            pass
        time.sleep(0.5)

    assert state is not None and float(state) == 380, (
        "expected the net-flow entity to show 500 - 120 = 380 W after setting "
        f"the two virtual sources; {net_flow_entity_id} state was {state!r}"
    )
