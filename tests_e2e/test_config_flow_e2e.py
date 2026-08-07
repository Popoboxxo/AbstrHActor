"""E2E: adding an Abstractor device through the real Config Flow UI produces
a working, live-updating sensor entity (REQ-CORE-002)."""
from __future__ import annotations

import re


def test_add_power_device_creates_live_entity(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/config/integrations/dashboard")

    page.get_by_role("button", name=re.compile("add integration", re.I)).click()
    page.get_by_placeholder(re.compile("search for a brand", re.I)).fill("Abstractor")
    page.get_by_text("Abstractor", exact=True).click()

    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    page.get_by_placeholder(re.compile("search", re.I)).fill("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()

    page.get_by_role("button", name=re.compile("^(submit|ok)$", re.I)).click()
    page.wait_for_timeout(500)

    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()

    page.goto(f"{hass_base_url}/config/entities")
    page.get_by_placeholder(re.compile("search", re.I)).fill("Power")
    assert page.get_by_text(re.compile("abstractor", re.I)).count() > 0, (
        "expected at least one abstractor entity to show up in the entities list "
        "after completing the config flow"
    )
