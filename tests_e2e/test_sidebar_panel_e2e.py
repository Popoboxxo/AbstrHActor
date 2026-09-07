"""E2E: the Abstractor sidebar panel (ADR-007, custom_components/abstractor/
frontend.py + www/abstractor-panel.js) renders real device data — this is
the only practical way to verify the panel's vanilla-JS Web Component at
all, since it has no Python-side logic pytest can exercise directly.

The action-hub tests below (docs/plan-panel-action-hub.md) cover the
export/import/edit/add-sensor buttons the panel does not yet have. Export
and Import are asserted by capturing the real frontend websocket frame the
button click produces (the same transport `hass.callService` uses under the
hood) rather than by inspecting JS source — this is the only way to prove
the button is actually wired to the real service call, not just present in
the DOM. Edit/Add-sensor are asserted by real browser navigation.
"""
from __future__ import annotations

import json
import re


def test_panel_appears_in_sidebar(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(hass_base_url)
    # Once a device is configured, "Abstractor" also appears as an installed
    # integration card and page heading elsewhere — #sidebar-panel-abstractor
    # is the sidebar nav item's own stable id, unambiguous regardless of that.
    # .count() doesn't auto-wait like .click()/.fill() do, so wait explicitly
    # for the sidebar to have actually rendered before checking it.
    sidebar_entry = page.locator("#sidebar-panel-abstractor")
    sidebar_entry.wait_for(state="visible", timeout=10000)
    assert sidebar_entry.count() > 0, (
        "expected an 'Abstractor' entry in the sidebar once a device is configured"
    )


def test_panel_lists_configured_device_with_live_value(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    page.wait_for_timeout(500)

    # The panel is a closed-content-free open shadow root; Playwright's
    # locators pierce open shadow DOM automatically.
    panel = page.locator("abstractor-panel")
    assert panel.count() == 1, "expected the <abstractor-panel> custom element to mount"

    body_text = panel.inner_text()
    assert not re.search(r"no abstractor devices yet", body_text, re.IGNORECASE), (
        "panel shows the empty state; expected at least one configured device "
        "(run the config-flow E2E test first, or add one manually)"
    )


def test_export_button_calls_export_service_with_return_response(logged_in_page, hass_base_url):
    """[plan-panel-action-hub #2] "Export" must call abstractor.export_data
    over the frontend websocket with return_response, not just exist as a
    button — capturing the sent frame is the only way to prove that from
    outside the (build-step-free, unbundled) panel JS."""
    page = logged_in_page
    sent_frames: list[str] = []
    page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent_frames.append(payload)))

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    export_button = panel.get_by_role("button", name=re.compile("export", re.IGNORECASE))
    export_button.wait_for(state="visible", timeout=10000)
    export_button.click()
    page.wait_for_timeout(1000)

    calls = [f for f in sent_frames if '"export_data"' in f]
    assert calls, "expected the Export button to send a call_service websocket frame for abstractor.export_data"
    assert any('"return_response":true' in f.replace(" ", "") for f in calls), (
        "export_data must be called with return_response: true so the panel can "
        f"download the result; got frames: {calls}"
    )


def test_import_button_calls_import_service_with_parsed_file_contents(
    logged_in_page, hass_base_url, tmp_path
):
    """[plan-panel-action-hub #3] Picking a JSON file via "Import" must call
    abstractor.import_data with that file's *parsed* content — asserted via
    a marker value round-tripping through the real websocket frame, not via
    reading panel internals."""
    page = logged_in_page
    sent_frames: list[str] = []
    page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent_frames.append(payload)))

    marker_title = "E2E Import Marker Device 8f2c1a"
    snapshot_file = tmp_path / "snapshot.json"
    snapshot_file.write_text(
        json.dumps(
            {
                "format": "abstractor.snapshot",
                "version": 1,
                "entries": [
                    {
                        "entry_id": "marker-entry",
                        "data": {},
                        "options": {},
                        "title": marker_title,
                        "unique_id": None,
                        "version": 1,
                    }
                ],
                "values": {},
            }
        )
    )

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    file_input = panel.locator('input[type="file"]')
    file_input.wait_for(state="attached", timeout=10000)
    file_input.set_input_files(str(snapshot_file))
    page.wait_for_timeout(1000)

    calls = [f for f in sent_frames if '"import_data"' in f and marker_title in f]
    assert calls, (
        "expected picking a file to send a call_service websocket frame for "
        f"abstractor.import_data containing the parsed file content; got: {sent_frames}"
    )


def test_edit_button_navigates_to_the_device_page(logged_in_page, hass_base_url):
    """[plan-panel-action-hub #4] Each device card's "Edit" action must
    navigate to HA's native device page — no custom edit form in the
    panel."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    edit_button = panel.get_by_role("button", name=re.compile("edit", re.IGNORECASE)).first
    edit_button.wait_for(state="visible", timeout=10000)
    edit_button.click()
    page.wait_for_url(re.compile(r"/config/devices/device/"), timeout=10000)


def test_add_sensor_button_navigates_to_the_integration_page(logged_in_page, hass_base_url):
    """[plan-panel-action-hub #4] The panel header's "Add sensor" action must
    navigate to the Abstractor integration page (the guaranteed fallback
    target per the plan) so users can reach the add-subentry flow without
    hunting through the sidebar."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    add_button = panel.get_by_role("button", name=re.compile("add sensor", re.IGNORECASE))
    add_button.wait_for(state="visible", timeout=10000)
    add_button.click()
    page.wait_for_url(re.compile(r"/config/integrations/integration/abstractor"), timeout=10000)
