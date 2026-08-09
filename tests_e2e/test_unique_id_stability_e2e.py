"""E2E regression test for REQ-CORE-001 / ADR: reconfiguring a device's
source entity through the Options Flow (a hardware swap) must NOT change
the abstracted sensor's entity_id — that's the whole point of deriving
identity from entry.data instead of entry.options (see
custom_components/abstractor/sensor.py). This is the live-browser
counterpart to tests/test_sensor.py::test_unique_id_ignores_reconfigured_source_in_options,
proving the fix holds through the real Config Flow + Options Flow UI, not
just the unit-level entry.data/entry.options plumbing.
"""
from __future__ import annotations

import re

import pytest
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


def _add_device(page, hass_base_url: str, source_name: str) -> None:
    """Drive the subentry "Add Abstract sensor" flow — same pattern as
    tests_e2e/test_config_flow_e2e.py (Task 3+ replaced the single-step
    "Add integration" + sensor-fields flow this helper used to drive with
    a two-step one: create the singleton root entry once, then a subentry
    per sensor)."""
    _ensure_root_entry(page, hass_base_url)

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


def _current_entity_ids(hass_base_url: str, token: str) -> set[str]:
    # The entities UI table doesn't render entity_id as visible text at all
    # (only the friendly name/device/platform columns) — scraping the DOM
    # for a "sensor.*" pattern can never find anything there. Read the
    # actual entity_ids straight from the REST API instead. Also, searching
    # by the chosen source_name (e.g. "Fallback Power Source") wouldn't
    # have worked either way: this integration's device/entity naming is
    # generic ("Abstract Power" / "Power"), not derived from the picked
    # source entity's name.
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "GH#19: reconfiguring a subentry's source entity through the live "
        "Config/Reconfigure Flow UI does not keep the abstracted sensor's "
        "entity_id stable on current Home Assistant (2026.8.0), unlike the "
        "unit-level entry.data/entry.options plumbing this mirrors (see "
        "tests/test_sensor.py::test_unique_id_ignores_reconfigured_source_in_options, "
        "which does pass). This test documents that live-UI regression and "
        "must stay xfail until GH#19 is actually fixed, at which point the "
        "marker itself starts failing and must be removed."
    ),
)
def test_reconfiguring_source_keeps_same_entity_id(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page

    _add_device(page, hass_base_url, "Fallback Power Source")
    entity_ids_before = _current_entity_ids(hass_base_url, hass_bearer_token)
    assert entity_ids_before, "expected the newly added device's entity to be listed"

    # Reconfigure: swap the source entity via this sensor's own subentry
    # Reconfigure flow — the real-world equivalent of replacing the
    # physical hardware sensor. Task 3+ moved sensor settings off the
    # parent config entry onto a per-sensor subentry, so there's no more
    # single "Configure" gear per integration entry to click; each
    # subentry gets its own, whose accessible name is exactly the
    # translated config_subentries.sensor.initiate_flow.reconfigure string
    # (confirmed via DOM inspection against a live instance). Every
    # subentry's Reconfigure button shares that exact same accessible name
    # (not distinguished by device or sensor type), so once other tests in
    # a full-suite run have added their own sensors against this shared HA
    # container, more than one can match — ours is the most recently
    # created, i.e. the last one.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Reconfigure Abstract sensor").last.click()
    page.wait_for_timeout(500)

    # The current source now renders as a single-select "Source entity"
    # field pre-filled with a chip (not the old multi-select "Add entity"
    # affordance this test used to drive) — clicking the field itself
    # reopens its picker to choose a REPLACEMENT (standard combobox
    # behaviour: picking a new entity swaps the existing single value
    # rather than requiring it to be cleared first), which is what a
    # hardware swap actually looks like now. Not using the field's own
    # "Clear" (X) button: that aria-label is shared with an unrelated
    # field on the same form (the "Legacy unique ID" text selector's
    # built-in clear/reveal icons render with the same generic
    # "Clear"/"Show password" labels, with no field-specific text to
    # disambiguate — confirmed via DOM inspection against a live instance)
    # and picking the wrong one would silently no-op instead of swapping
    # the source.
    source_dialog = page.get_by_role("dialog", name="Source entity")
    page.get_by_label("Source entity", exact=True).click()
    search_field = source_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Fridge Power", delay=100)
    source_dialog.get_by_text("Fridge Power", exact=False).first.click()
    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(1000)  # entry reload after options update

    entity_ids_after = _current_entity_ids(hass_base_url, hass_bearer_token)

    assert entity_ids_after == entity_ids_before, (
        "reconfiguring the source entity must not change the abstracted "
        f"sensor's entity_id (REQ-CORE-001): before={entity_ids_before} "
        f"after={entity_ids_after}"
    )

    # The entity_id-stability assertion above is trivially true if the
    # reconfigure submission silently failed to apply at all (same
    # entity_id because nothing actually changed) — so also confirm the
    # swap itself took effect, by polling the entity's own state for the
    # NEW source's value. "Fallback Power Source" and "Fridge Power" are
    # deliberately different virtual-sensor values (30 vs 42, see
    # docker/ha_config_e2e/virtual_sensors.yaml) specifically so this is a
    # reliable discriminator between "source actually swapped" and
    # "reconfigure was a no-op".
    entity_id = next(iter(entity_ids_after))
    state = None
    for _ in range(20):
        resp = requests.get(
            f"{hass_base_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {hass_bearer_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        state = resp.json()["state"]
        try:
            if float(state) == 42:
                break
        except ValueError:
            pass
        page.wait_for_timeout(500)

    assert state is not None and float(state) == 42, (
        "expected the reconfigured sensor to report Fridge Power's value "
        f"(42 W) after the source swap actually took effect; {entity_id} "
        f"state was {state!r} (still 30 would mean the Reconfigure submit "
        "silently failed to apply, masked by the entity_id-only check above)"
    )
