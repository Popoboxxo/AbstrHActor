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

import requests


def _add_device(page, hass_base_url: str, source_name: str) -> None:
    # Custom HA elements (ha-fab, mwc-button, ...) don't reliably expose an
    # accessible role="button" to Playwright's get_by_role — get_by_text is
    # what actually finds them (confirmed via manual DOM inspection).
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
    search_field.press_sequentially(source_name)
    page.get_by_text(source_name, exact=False).first.click()
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


def test_reconfiguring_source_keeps_same_entity_id(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page

    _add_device(page, hass_base_url, "Fallback Power Source")
    entity_ids_before = _current_entity_ids(hass_base_url, hass_bearer_token)
    assert entity_ids_before, "expected the newly added device's entity to be listed"

    # Reconfigure: swap the source entity via the Options Flow — the
    # real-world equivalent of replacing the physical hardware sensor.
    # Once the domain card shows multiple config entries ("N devices"), HA
    # renders it as a link to a per-domain listing page instead of a
    # button that pops a single entry's menu directly — role=button (which
    # worked for the single-entry case in test_net_flow) matches nothing
    # here. Going straight to that page's URL sidesteps the card click
    # entirely (also avoids the ambiguity with the sidebar panel link,
    # which points at the same domain slug).
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
    # This dialog's field labels render as raw internal names
    # (source_entity_ids, spike_filter, ...) instead of the translated text
    # from strings.json — a real (separate) UI bug, not a locator issue.
    # get_by_label never matches because these aren't proper <label>
    # associations. The source_entity_ids field already shows our current
    # source as a chip; "Add entity" is the visible, unambiguous affordance
    # for changing it, so use that instead of trying to label-match the
    # field itself.
    page.get_by_text("Add entity", exact=False).click()
    # "Add entity" opens its own "Select option" dialog layered on top of
    # the options dialog — its search field shares the exact placeholder
    # "Search" with the domain listing page's own search box underneath,
    # so scope to the new dialog specifically instead of the whole page.
    add_entity_dialog = page.get_by_role("dialog", name="Select option")
    search_field = add_entity_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()
    page.keyboard.press("Escape")  # close the entity-picker dropdown, not the dialog
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(1000)  # entry reload after options update

    entity_ids_after = _current_entity_ids(hass_base_url, hass_bearer_token)

    assert entity_ids_after == entity_ids_before, (
        "reconfiguring the source entity must not change the abstracted "
        f"sensor's entity_id (REQ-CORE-001): before={entity_ids_before} "
        f"after={entity_ids_after}"
    )
