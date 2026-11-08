"""Minimal smoke E2E test for the Abstractor sidebar panel (UI phase 0)."""
from __future__ import annotations

import re


def test_panel_mounts(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)
    assert panel.count() == 1


def test_tabs_render(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)
    for label in ("Devices", "Health", "Settings"):
        btn = panel.get_by_role("button", name=label)
        btn.wait_for(state="visible", timeout=10000)
        assert btn.count() >= 1


def test_export_button_calls_export_data(logged_in_page, hass_base_url):
    page = logged_in_page
    sent_frames: list[str] = []
    page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent_frames.append(payload)))

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.get_by_role("button", name=re.compile(r"^edit mode$", re.IGNORECASE)).click()
    export_button = panel.get_by_role("button", name=re.compile(r"^export$", re.IGNORECASE))
    export_button.wait_for(state="visible", timeout=10000)
    export_button.click()
    page.wait_for_timeout(1000)

    calls = [f for f in sent_frames if '"export_data"' in f]
    assert calls, "expected Export to send an abstractor.export_data websocket frame"
    assert any('"return_response":true' in f.replace(" ", "") for f in calls), calls


def test_edit_button_navigates_to_device_page(logged_in_page, hass_base_url):
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)
    created = page.evaluate(
        """
        (async () => {
          const h = document.querySelector("home-assistant").hass;
          const res = await h.callWS({
            type: "abstractor/subentry/create",
            data: { device_type: "power", source_entity_id: "sensor.e2e_edit_probe" },
          });
          return res.subentry_id;
        })()
        """
    )
    try:
        page.wait_for_timeout(2000)
        page.goto(f"{hass_base_url}/abstractor")
        panel = page.locator("abstractor-panel")
        panel.locator(".device-card").first.wait_for(state="visible", timeout=30000)
        # Anchor to the card's exact "Edit" label: the header also has an
        # "Edit mode" toggle whose accessible name contains "edit".
        edit_button = panel.get_by_role("button", name=re.compile(r"^edit$", re.IGNORECASE)).first
        edit_button.wait_for(state="visible", timeout=20000)
        edit_button.click()
        page.wait_for_url(re.compile(r"/config/(devices/device|integrations/integration/abstractor)"), timeout=10000)
    finally:
        page.goto(f"{hass_base_url}/abstractor")
        page.wait_for_function(
            "() => { const e = document.querySelector('home-assistant'); return !!(e && e.hass); }",
            timeout=20000,
        )
        page.evaluate(
            """
            (async (id) => {
              const h = document.querySelector("home-assistant").hass;
              try { await h.callWS({ type: "abstractor/subentry/delete", subentry_id: id }); } catch (e) {}
            })
            """,
            created,
        )


def test_create_form_opens_in_edit_mode(logged_in_page, hass_base_url):
    """[UI-2] Enabling edit mode exposes the in-panel create form; Cancel
    closes it without writing (a write path is covered by the unit tests and
    the websocket command tests)."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")

    edit_toggle = panel.get_by_role("button", name=re.compile(r"^edit mode$", re.IGNORECASE))
    edit_toggle.wait_for(state="visible", timeout=10000)
    edit_toggle.click()

    panel.get_by_role("button", name=re.compile(r"^add sensor$", re.IGNORECASE)).click()

    save_button = panel.get_by_role("button", name=re.compile(r"^save$", re.IGNORECASE))
    save_button.wait_for(state="visible", timeout=10000)
    panel.get_by_role("button", name=re.compile(r"^cancel$", re.IGNORECASE)).click()
    page.wait_for_timeout(300)

    assert panel.get_by_role("button", name=re.compile(r"^save$", re.IGNORECASE)).count() == 0


def test_settings_tab_renders_redacted_options(logged_in_page, hass_base_url):
    """WS-3.6/E9: Settings renders the resolved options and never a credential."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.get_by_role("button", name="Settings", exact=True).click()
    panel.get_by_text(re.compile("Poll interval", re.IGNORECASE)).first.wait_for(state="visible", timeout=15000)
    assert panel.get_by_text(re.compile("influx_host|influx_token|influx_org", re.IGNORECASE)).count() == 0


def test_health_tab_lists_rejected_samples(logged_in_page, hass_base_url):
    """WS-5.5: the Health tab exposes the rejected-sample section per sensor."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)
    created = page.evaluate(
        """
        (async () => {
          const res = await document.querySelector("home-assistant").hass.callWS({
            type: "abstractor/subentry/create",
            data: { device_type: "power", source_entity_id: "sensor.e2e_health_probe" },
          });
          return res.subentry_id;
        })()
        """
    )
    try:
        page.wait_for_timeout(2000)
        page.goto(f"{hass_base_url}/abstractor")
        panel = page.locator("abstractor-panel")
        panel.wait_for(state="attached", timeout=30000)
        health_tab = panel.get_by_role("button", name="Health", exact=True)
        health_tab.wait_for(state="visible", timeout=30000)
        health_tab.click()
        panel.get_by_text(re.compile("Rejected samples", re.IGNORECASE)).first.wait_for(
            state="visible", timeout=20000
        )
    finally:
        page.goto(f"{hass_base_url}/abstractor")
        page.wait_for_function(
            "() => { const e = document.querySelector('home-assistant'); return !!(e && e.hass); }",
            timeout=20000,
        )
        page.evaluate(
            """
            (async (id) => {
              try { await document.querySelector("home-assistant").hass.callWS({ type: "abstractor/subentry/delete", subentry_id: id }); } catch (e) {}
            })
            """,
            created,
        )


def test_settings_csv_export_calls_export_csv_service(logged_in_page, hass_base_url):
    """WS-6.4: the Settings tab exposes the CSV export and it must call the
    real service with return_response (same frame-proof pattern as JSON)."""
    page = logged_in_page
    sent_frames: list[str] = []
    page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent_frames.append(payload)))

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.get_by_role("button", name=re.compile(r"^edit mode$", re.IGNORECASE)).click()
    panel.get_by_role("button", name="Settings", exact=True).click()
    panel.get_by_role("button", name="Export CSV", exact=True).click()
    page.wait_for_timeout(1500)

    calls = [f for f in sent_frames if '"export_csv"' in f]
    assert calls, "expected Settings > Export CSV to call abstractor.export_csv"
    assert any('"return_response":true' in f.replace(" ", "") for f in calls), calls


def test_settings_summary_calls_summary_service(logged_in_page, hass_base_url):
    """WS-6.4/E8: the summary button asks the service for its response and
    renders the per-sensor contract instead of failing silently."""
    page = logged_in_page
    sent_frames: list[str] = []
    page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent_frames.append(payload)))

    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.get_by_role("button", name=re.compile(r"^edit mode$", re.IGNORECASE)).click()
    panel.get_by_role("button", name="Settings", exact=True).click()
    panel.get_by_role("button", name="Summary", exact=True).click()
    page.wait_for_timeout(1500)

    calls = [f for f in sent_frames if '"summary"' in f and '"abstractor"' in f]
    assert calls, "expected Settings > Summary to call abstractor.summary"
    assert any('"return_response":true' in f.replace(" ", "") for f in calls), calls
