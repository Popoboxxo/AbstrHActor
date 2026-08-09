"""E2E regression test: Config/Options Flow fields must show their
translated label and help text (from strings.json, loaded at runtime via
translations/en.json), not the raw schema key. See
docs/superpowers/specs/2026-08-07-translations-loading-design.md for the
root cause (HA's frontend reads translations/<lang>.json at runtime, not
strings.json directly — this integration never shipped that file)."""
from __future__ import annotations

import re

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

    source_dialog = page.get_by_role("dialog", name="Source entity")
    page.get_by_label("Source entity", exact=True).click()
    search_field = source_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially(source_name, delay=100)
    source_dialog.get_by_text(source_name, exact=False).first.click()

    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def test_options_dialog_shows_translated_labels(logged_in_page, hass_base_url):
    page = logged_in_page

    _ensure_root_entry(page, hass_base_url)
    _add_sensor_subentry(page, hass_base_url, "Fridge Power")

    # Open this sensor's own Reconfigure dialog — the subentry-scoped
    # equivalent of the old per-config-entry Options dialog (Task 3+:
    # sensor settings live on the subentry, not the parent config entry,
    # so there's no more single "Configure" gear per integration entry to
    # click — each subentry gets its own, whose accessible name is exactly
    # the translated config_subentries.sensor.initiate_flow.reconfigure
    # string, confirmed via DOM inspection against a live instance).
    # Every subentry's Reconfigure button shares that exact same
    # accessible name (not distinguished by device or sensor type), so
    # once other tests in a full-suite run have added their own sensors
    # against this shared HA container, more than one can match — ours is
    # the most recently created, i.e. the last one.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Reconfigure Abstract sensor").last.click()
    page.wait_for_timeout(500)

    # Locks in the fix: assert the TRANSLATED heading is visible and the
    # raw schema key is not — without translations/en.json, HA falls back
    # to showing the raw key as the field heading (see
    # docs/superpowers/specs/2026-08-07-translations-loading-design.md).
    assert page.get_by_text("Source entities", exact=True).count() > 0, (
        "expected the translated field label 'Source entities' in the "
        "Reconfigure dialog — got raw key instead, translations/en.json is "
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
        "Reconfigure dialog"
    )
