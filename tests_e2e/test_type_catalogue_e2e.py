"""E2E (WS-2.5): the server-served type catalogue drives the panel — no JS drift.

Drives the authenticated frontend WS layer directly: `abstractor/types` must
ship the actuator types (the old 6-type JS hardcode made them uncreatable and
unfilterable — UF-01) and must exclude roadmap specs like `riemann_energy`
(decision D-1). The assertion set is deliberately a subset/supersede pair so
the test documents the drift it guards instead of mirroring the registry.
"""

from __future__ import annotations


def test_panel_served_type_catalogue(logged_in_page, hass_base_url) -> None:
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)

    catalogue = page.evaluate(
        """
        (async () => {
          const h = document.querySelector("home-assistant").hass;
          if (!h || !h.callWS) {
            throw new Error("frontend hass object not exposed on the panel page");
          }
          return await h.callWS({ type: "abstractor/types" });
        })()
        """
    )

    device_types = set(catalogue["device_types"])
    assert {
        "switch_state",
        "light_state",
        "cover_position",
    } <= device_types, "actuator types must be part of the panel catalogue (UF-01 drift guard)"
    assert "riemann_energy" not in device_types, "roadmap-only specs must not be shipped to the panel (decision D-1)"
    assert {"power", "energy", "water"} <= set(catalogue["numeric_types"])
    assert catalogue["display_names"].get("cover_position") == "Cover position"


def test_create_form_offers_actuator_types(logged_in_page, hass_base_url) -> None:
    """WS-2.5: the create form must offer the server catalogue's non-sensor
    types — the old JS hardcode rejected them client-side (UF-01)."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")

    panel.get_by_role("button", name="Edit mode").click()
    panel.get_by_role("button", name="Add sensor").click()
    device_type = panel.locator(".drawer select").first
    device_type.wait_for(state="visible", timeout=10000)
    values = device_type.locator("option").evaluate_all("(nodes) => nodes.map((n) => n.value)")

    assert {"door_contact", "motion", "smoke", "switch_state", "light_state", "cover_position"} <= set(values)
    panel.get_by_role("button", name="Cancel").click()


def test_actuator_types_round_trip_through_create_and_filter(logged_in_page, hass_base_url) -> None:
    """WS-2.5: one binary, one switch and one cover subentry survive the WS
    create path and get a working filter chip in the device list."""
    page = logged_in_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)

    created = page.evaluate(
        """
        (async () => {
          const h = document.querySelector("home-assistant").hass;
          const ids = [];
          for (const [type, source] of [
            ["door_contact", "sun.sun"],
            ["switch_state", "sun.sun"],
            ["cover_position", "sun.sun"],
          ]) {
            const res = await h.callWS({
              type: "abstractor/subentry/create",
              data: { device_type: type, source_entity_id: source },
            });
            ids.push(res.subentry_id);
          }
          return ids;
        })()
        """
    )
    try:
        page.goto(f"{hass_base_url}/abstractor")
        panel = page.locator("abstractor-panel")
        for label in ("door contact", "switch", "cover position"):
            chip = panel.get_by_role("button", name=label, exact=True)
            chip.wait_for(state="visible", timeout=20000)
            chip.click()
            assert panel.locator(".device-card").count() >= 1
            panel.get_by_role("button", name="all", exact=True).click()
    finally:
        page.goto(f"{hass_base_url}/abstractor")
        page.wait_for_function(
            "() => { const e = document.querySelector('home-assistant'); return !!(e && e.hass); }",
            timeout=20000,
        )
        page.evaluate(
            """
            (async (ids) => {
              const h = document.querySelector("home-assistant").hass;
              for (const id of ids) {
                try { await h.callWS({ type: "abstractor/subentry/delete", subentry_id: id }); } catch (e) {}
              }
            })
            """,
            created,
        )
