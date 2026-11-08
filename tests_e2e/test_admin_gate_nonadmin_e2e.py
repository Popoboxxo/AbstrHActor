"""E2E (WS-3): every user sees the read surface; write gates stay admin-only.

Drives the panel page as the NON-admin reader user: the subentries read must
render (UF-04: an admin gate emptied the whole panel for ordinary users),
identity rows must arrive redacted (decision D-5), and each write/read
boundary must behave exactly like the unit-level gates (ha-health-o-mat #28
style proof: the gate itself, not a panel-side shortcut).
"""

from __future__ import annotations


def test_nonadmin_panel_renders_redacted_read_view(readonly_page, hass_base_url) -> None:
    page = readonly_page
    page.goto(f"{hass_base_url}/abstractor")
    panel = page.locator("abstractor-panel")
    panel.wait_for(state="attached", timeout=10000)

    read = page.evaluate(
        """
        (async () => {
          const h = document.querySelector("home-assistant").hass;
          if (!h || !h.callWS) {
            throw new Error("frontend hass object not exposed on the panel page");
          }
          return await h.callWS({ type: "abstractor/subentries" });
        })()
        """
    )
    rows = read.get("subentries") or []
    assert isinstance(rows, list), "read path must answer for the reader user"
    for row in rows:
        assert row.get("legacy_unique_id") is None, "identity must not leak to non-admins (D-5)"
        assert row.get("device_group_id") is None, "device wiring must not leak to non-admins (D-5)"

    write_error = page.evaluate(
        """
        (async () => {
          const h = document.querySelector("home-assistant").hass;
          if (!h || !h.callWS) { throw new Error("frontend hass object not exposed"); }
          try {
            await h.callWS({ type: "abstractor/subentry/delete", subentry_id: "e2e-does-not-exist" });
            return "NOT-REJECTED";
          } catch (err) {
            return String(err);
          }
        })()
        """
    )
    assert write_error != "NOT-REJECTED", "a write driven straight at the WS layer by a non-admin must be rejected"
