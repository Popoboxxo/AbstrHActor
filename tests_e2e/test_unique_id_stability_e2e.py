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


def _add_device(page, hass_base_url: str, source_name: str) -> None:
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_role("button", name=re.compile("add integration", re.I)).click()
    page.get_by_placeholder(re.compile("search for a brand", re.I)).fill("Abstractor")
    page.get_by_text("Abstractor", exact=True).click()
    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    page.get_by_placeholder(re.compile("search", re.I)).fill(source_name)
    page.get_by_text(source_name, exact=False).first.click()
    page.get_by_role("button", name=re.compile("^(submit|ok)$", re.I)).click()
    page.wait_for_timeout(500)
    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()


def _current_entity_ids(page, hass_base_url: str) -> set[str]:
    page.goto(f"{hass_base_url}/config/entities")
    page.get_by_placeholder(re.compile("search", re.I)).fill("Fallback")
    page.wait_for_timeout(300)
    rows = page.locator("[role='row']")
    return {
        m.group(0)
        for text in rows.all_inner_texts()
        if (m := re.search(r"sensor\.[a-z0-9_]+", text))
    }


def test_reconfiguring_source_keeps_same_entity_id(logged_in_page, hass_base_url):
    page = logged_in_page

    _add_device(page, hass_base_url, "Fallback Power Source")
    entity_ids_before = _current_entity_ids(page, hass_base_url)
    assert entity_ids_before, "expected the newly added device's entity to be listed"

    # Reconfigure: swap the source entity via the Options Flow — the
    # real-world equivalent of replacing the physical hardware sensor.
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_text("Abstractor", exact=True).first.click()
    page.get_by_role("button", name=re.compile("configure", re.I)).click()

    page.get_by_label(re.compile("source_entity_ids|source entities", re.I)).click()
    page.get_by_placeholder(re.compile("search", re.I)).fill("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()
    page.keyboard.press("Escape")  # close the entity-picker dropdown, not the dialog
    page.get_by_role("button", name=re.compile("^submit$", re.I)).click()
    page.wait_for_timeout(1000)  # entry reload after options update

    entity_ids_after = _current_entity_ids(page, hass_base_url)

    assert entity_ids_after == entity_ids_before, (
        "reconfiguring the source entity must not change the abstracted "
        f"sensor's entity_id (REQ-CORE-001): before={entity_ids_before} "
        f"after={entity_ids_after}"
    )
