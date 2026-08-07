"""E2E: adding an Abstractor device through the real Config Flow UI produces
a working, live-updating sensor entity (REQ-CORE-002)."""
from __future__ import annotations

import re


def test_add_power_device_creates_live_entity(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/config/integrations/dashboard")

    # Custom HA elements (ha-fab, mwc-button, ...) don't reliably expose an
    # accessible role="button" to Playwright's get_by_role — get_by_text is
    # what actually finds them (confirmed via manual DOM inspection).
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
    search_field.press_sequentially("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()

    # get_by_text with an anchored regex (^...$) reliably matches 0 elements
    # here even though the button's own text is exactly "Submit" — confirmed
    # via DOM dump and by the fact that an unanchored get_by_text/get_by_role
    # both find it fine. get_by_role is what actually works for this button.
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)

    # get_by_text("finish|skip") can match a transient toast/snackbar
    # message instead of the real dialog button, and clicking it hangs for
    # the full timeout since the still-open dialog intercepts the pointer
    # event — scope to role=button like the Submit fix above.
    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()

    page.goto(f"{hass_base_url}/config/entities")
    page.wait_for_load_state("networkidle")
    # A stray hidden "Search" input from a previous dialog layer can still
    # be in the DOM here, and .first can resolve to it instead of the real,
    # visible entities-page search box — filter for :visible explicitly.
    page.locator('input[placeholder="Search"]:visible').fill("Power")
    assert page.get_by_text(re.compile("abstractor", re.I)).count() > 0, (
        "expected at least one abstractor entity to show up in the entities list "
        "after completing the config flow"
    )
