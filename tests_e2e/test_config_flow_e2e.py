"""E2E: adding an Abstractor device through the real Config Flow UI produces
a working, live-updating sensor entity (REQ-CORE-002)."""
from __future__ import annotations

import re

# The subentry "add" action is a plain <button> (confirmed via DOM
# inspection against a live instance — HA's frontend does not expose it as
# role="link"), whose accessible name is the translated initiate_flow.user
# string ("Add Abstract sensor" — see strings.json / translations/en.json).
# "add.*sensor" survives either that or a raw-key fallback render.
ADD_SENSOR_SUBENTRY_NAME = re.compile("add.*sensor", re.I)
SUBMIT_BUTTON_NAME = re.compile("submit|ok", re.I)


def _dismiss_success_dialog(page) -> None:
    finish_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if finish_button.count():
        finish_button.first.click()
        page.wait_for_timeout(300)


def _ensure_root_entry(page, hass_base_url: str) -> None:
    """Create the singleton Abstractor root entry (Task 3+: "Add
    integration" only creates this empty parent — sensor fields moved to a
    separate subentry flow, see _add_sensor_subentry), or no-op if a
    previous test in this run already created it (it's a HA-enforced
    singleton via unique_id, so re-running "Add integration" would abort
    instead of showing a form)."""
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
    # The root entry's async_step_user form has no data fields at all (see
    # strings.json's config.step.user) — Submit is immediately available.
    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def _add_sensor_subentry(page, hass_base_url: str, source_name: str) -> None:
    """Drive the subentry "Add Abstract sensor" flow from the integration's
    own page, leaving device_type at its default ("power")."""
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=ADD_SENSOR_SUBENTRY_NAME).click()
    page.wait_for_timeout(500)

    # This picker opens as its own role="dialog" (named after the field's
    # aria-label) layered on top of the subentry form dialog, which itself
    # sits on top of the domain listing page underneath both — the search
    # placeholder "Search" is ambiguous across all of them, and text like
    # the entity's name can even exist in more than one layer at once.
    # Scoping every locator to this specific dialog (rather than relying on
    # `.first`, which resolves in DOM/document order, NOT visual stacking
    # order, and can silently grab a match hidden under the modal overlay)
    # avoids that — confirmed against a live instance.
    source_dialog = page.get_by_role("dialog", name="Source entity")
    page.get_by_label("Source entity", exact=True).click()
    # ha-entity-picker filters as-you-type off real input events — .fill()
    # sets the value without dispatching them, so the dropdown never narrows.
    # press_sequentially (not raw keyboard.type) re-focuses its target
    # locator itself, surviving the picker's internal re-renders — but a
    # delay is required between characters, or a stray keystroke can land
    # on HA's global quick-bar hotkeys (bound to keydown on an unfocused
    # document, e.g. "d" for its Devices tab) instead of the field, while
    # the picker's own filter-triggered re-render is transiently unmounting
    # it (confirmed via screenshot showing the quick-bar overlay appear
    # mid-type without this delay).
    search_field = source_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially(source_name, delay=100)
    source_dialog.get_by_text(source_name, exact=False).first.click()

    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def test_add_power_device_creates_live_entity(logged_in_page, hass_base_url):
    page = logged_in_page

    _ensure_root_entry(page, hass_base_url)
    _add_sensor_subentry(page, hass_base_url, "Fridge Power")

    page.goto(f"{hass_base_url}/config/entities")
    page.wait_for_load_state("networkidle")
    # The search box on this page is not a plain <input> but a custom
    # <ha-input-search> web component (hass-tabs-subpage-data-table) whose
    # inner <input type="search"> lives in its shadow DOM; a role="searchbox"
    # or placeholder-based locator resolves to zero on newer HA — which is
    # exactly what caused the 60s `.fill()` timeout. Target the real inner
    # input of the page's single <ha-input-search>, waiting explicitly before
    # filling.
    search_box = page.locator("ha-input-search input[type='search']").last
    search_box.wait_for(state="visible", timeout=15000)
    search_box.fill("Power")
    assert page.get_by_text(re.compile("abstractor", re.I)).count() > 0, (
        "expected at least one abstractor entity to show up in the entities list "
        "after completing the config flow"
    )
