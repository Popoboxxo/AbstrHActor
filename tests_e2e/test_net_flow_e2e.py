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

    # Custom HA elements (ha-fab, mwc-button, ...) don't reliably expose an
    # accessible role="button" to Playwright's get_by_role — get_by_text is
    # what actually finds them (confirmed via manual DOM inspection).
    page = logged_in_page
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_text("Add integration", exact=False).click()
    # get_by_text("Abstractor") becomes ambiguous once a device already
    # exists (it then also matches the sidebar panel entry and the
    # already-installed integration card behind this dialog) — pressing
    # Enter on the filtered (single-result) brand search avoids relying on
    # text matching entirely, the same fix pattern as the entity picker.
    brand_search = page.get_by_placeholder(re.compile("search for a brand", re.I))
    brand_search.fill("Abstractor")
    brand_search.press("Enter")

    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    # ha-entity-picker filters as-you-type off real input events — .fill()
    # sets the value without dispatching them, so the dropdown never narrows.
    # get_by_placeholder("search") with a case-insensitive regex is ambiguous
    # (the prior brand-picker dialog leaves a "Search integrations" input in
    # the DOM) — exact=True disambiguates against that. press_sequentially
    # (not raw keyboard.type) is what's actually reliable here: it re-focuses
    # its target locator itself, so it survives the picker's internal
    # re-renders instead of silently typing into whatever last had OS focus.
    search_field = page.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Battery Charge Power")
    page.get_by_text("Battery Charge Power", exact=False).first.click()

    # get_by_text with an anchored regex (^...$) reliably matches 0 elements
    # for this button even though its own text is exactly "Submit" —
    # get_by_role is what actually works here (confirmed via DOM dump).
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)
    # get_by_text("finish|skip") can match a transient toast/snackbar
    # message instead of the real dialog button, and clicking it hangs for
    # the full timeout since the still-open dialog intercepts the pointer
    # event — scope to role=button like the Submit fix above.
    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()

    # Reconfigure to add the net-subtract source (Battery Discharge Power).
    # Once other tests in the suite have added their own devices, the
    # domain card shows "N devices" and HA renders it as a link to a
    # per-domain listing page rather than a button that pops a single
    # entry's menu directly — going straight to that page's URL sidesteps
    # both the card-click ambiguity (role=button vs role=link) and the
    # sidebar panel link pointing at the same domain slug.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    # Every config entry on this page renders with an identical generic
    # title ("Abstract power" / "Abstract Power") — there's no visible text
    # to distinguish our just-created entry from any other. Each entry's
    # gear icon is a <button aria-label="Configure"> (no visible text, so
    # get_by_text never matches it) in DOM order matching creation order —
    # ours is the most recently created, i.e. the last one.
    page.get_by_role("button", name="Configure", exact=True).last.click()
    page.wait_for_timeout(500)
    # Now that translations/en.json exists (see
    # docs/superpowers/specs/2026-08-07-translations-loading-design.md),
    # each picker's aria-label reflects the TRANSLATED field label, not the
    # raw schema key ("Subtract entity (net flow)" for net_subtract_entity_id
    # — confirmed via manual DOM inspection; the raw-key locator this test
    # used before now matches 0 elements). get_by_label never matches via a
    # proper <label> association here, but aria-label works regardless of
    # translation state — this is exactly what made the config-flow source
    # picker's get_by_label(...) reliable, so use the same approach with the
    # current (translated) text.
    page.get_by_label("Subtract entity (net flow)", exact=True).click()
    # Clicking a single-entity picker opens its own sub-dialog (same
    # pattern as the "Add entity" dialog for multi-select pickers), whose
    # search field shares the exact placeholder "Search" with the domain
    # listing page's own search box underneath — scope to the sub-dialog
    # specifically instead of the whole page.
    picker_dialog = page.get_by_role("dialog", name="Subtract entity (net flow)")
    search_field = picker_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Battery Discharge Power")
    page.wait_for_timeout(300)
    # Clicking the filtered result by text is unreliable here: this picker
    # renders as a wa-popover, whose own container can intercept the
    # pointer event meant for the list item inside it. Keyboard selection
    # sidesteps click-interception entirely (same approach already used
    # for the brand picker) — Enter selects the first (only) filtered
    # match and closes the sub-dialog on its own, same as a click would.
    page.keyboard.press("Enter")
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
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
