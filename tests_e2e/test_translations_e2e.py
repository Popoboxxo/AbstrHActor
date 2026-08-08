"""E2E regression test: Config/Options Flow fields must show their
translated label and help text (from strings.json, loaded at runtime via
translations/en.json), not the raw schema key. See
docs/superpowers/specs/2026-08-07-translations-loading-design.md for the
root cause (HA's frontend reads translations/<lang>.json at runtime, not
strings.json directly — this integration never shipped that file)."""
from __future__ import annotations

import re


def test_options_dialog_shows_translated_labels(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page

    # Add a device via the Config Flow — same pattern as
    # tests_e2e/test_unique_id_stability_e2e.py::_add_device.
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_text("Add integration", exact=False).click()
    brand_search = page.get_by_placeholder(re.compile("search for a brand", re.I))
    brand_search.fill("Abstractor")
    brand_search.press("Enter")
    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    search_field = page.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()
    page.keyboard.press("Escape")  # close the entity-picker dropdown
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)
    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()

    # Open this device's Options dialog — same navigation as
    # tests_e2e/test_unique_id_stability_e2e.py lines 90-106.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Configure", exact=True).last.click()
    page.wait_for_timeout(500)

    # The bug: without translations/en.json, HA falls back to showing the
    # raw schema key as the field heading. Assert the TRANSLATED heading is
    # visible, and the raw key is not — this fails today and passes once
    # translations/en.json exists (Task 2).
    assert page.get_by_text("Source entities", exact=True).count() > 0, (
        "expected the translated field label 'Source entities' in the "
        "Options dialog — got raw key instead, translations/en.json is "
        "missing or not being read"
    )
    assert page.get_by_text("source_entity_ids", exact=True).count() == 0, (
        "raw schema key 'source_entity_ids' is still visible as a field "
        "heading — translations aren't loading"
    )
    # exact=True (used above for the EntitySelector-based "Source entities"
    # field) does not match this field: spike_filter renders as a boolean
    # checkbox row (ha-formfield) whose label text is nested one level
    # deeper than the entity-picker's — confirmed via manual DOM inspection
    # that the label's rendered text is exactly "Enable spike filter" with
    # no extra whitespace, get_by_text just resolves to a different node
    # when exact-matching that structure. exact=False is safe here: the
    # string is distinctive enough not to collide with anything else on
    # this dialog (confirmed no other "filter"/"spike" text present).
    assert page.get_by_text("Enable spike filter", exact=False).count() > 0, (
        "expected the translated field label 'Enable spike filter' in the "
        "Options dialog"
    )
