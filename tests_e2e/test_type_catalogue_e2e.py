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
          const h = window.hass;
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
