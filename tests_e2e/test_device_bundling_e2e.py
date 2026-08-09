"""E2E: adding a second Abstract sensor to an already-existing device
results in both sensors appearing under one Home Assistant device — the
core deliverable of docs/superpowers/specs/2026-08-08-device-bundling-design.md.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import websockets

# The subentry "add" action is a plain <button> (NOT an <a>/role="link" —
# verified by DOM inspection against a live instance; the brief's draft
# guessed role="link"), whose accessible name is the translated
# initiate_flow.user string ("Add Abstract sensor" — see strings.json /
# translations/en.json), not the generic "Add sensor"/"Add entry" guessed
# in the brief either. "add.*sensor" still survives a raw-key-fallback
# render (unlikely here since translations/en.json is confirmed loading —
# see test_translations_e2e.py) the same way every other picker in this
# suite hedges for that.
ADD_SENSOR_SUBENTRY_NAME = re.compile("add.*sensor", re.I)
SUBMIT_BUTTON_NAME = re.compile("submit|ok", re.I)


def _ensure_root_entry(page, hass_base_url: str) -> None:
    """Create the singleton Abstractor root entry if it doesn't already exist.

    The root entry has no config fields (see config_flow.py's async_step_user)
    and is a HA-enforced singleton via unique_id — once any earlier test in
    this run (or a fresh run's own first call) has created it, going through
    "Add integration" again would abort with "already configured" instead of
    showing a form. Checking for the subentry "add" link on the entry's own
    page first (which only exists once the root entry is there) avoids that
    entirely instead of trying to parse an abort dialog.
    """
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
    # strings.json's config.step.user) — Submit is immediately available,
    # no picker interaction needed here.
    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def _add_sensor_subentry(
    page,
    hass_base_url: str,
    *,
    source_name: str,
    device_type: str | None = None,
    target_device_name: str | None = None,
) -> None:
    """Drive the subentry "Add Abstract sensor" flow from the integration's
    own page. `device_type` selects a non-default sensor type (the schema's
    first option, "power", is pre-selected otherwise). `target_device_name`
    picks an existing device by its exact display name (see sensor.py's
    DeviceInfo — a fresh device's name is always "Abstract {Type}") via the
    device selector's own search dialog."""
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=ADD_SENSOR_SUBENTRY_NAME).click()
    page.wait_for_timeout(500)

    if device_type:
        # The select's aria-label is exactly "Device Type" (title-cased,
        # per strings.json's data.device_type) — the option list items
        # themselves render SENSOR_TYPES' raw (lowercase) values ("power",
        # "energy", "water"), not a title-cased display string, confirmed
        # by DOM inspection. get_by_label("Source entity", non-exact) would
        # also ambiguously match "Fallback source entity" on this same
        # form, so exact=True is required here and below.
        page.get_by_label("Device Type", exact=True).click()
        page.wait_for_timeout(300)
        page.get_by_text(device_type.lower(), exact=True).click()

    # Both this picker and the device picker below open as their own
    # role="dialog" (named after the field's own aria-label — confirmed via
    # a Playwright strict-mode violation message naming
    # get_by_role("dialog", name="Device") as one of the matches) layered
    # on top of the subentry form dialog, which itself sits on top of the
    # domain listing page underneath both. Text like an entity's or
    # device's name can exist in more than one of those layers at once
    # (e.g. a device already shown in an earlier-created, now-background
    # subentry row) — get_by_text(...).first resolves to DOM/document
    # order, NOT visual stacking order, so it can silently grab a match
    # that's actually hidden under the modal overlay, and then hang
    # forever on "<dialog-data-entry-flow> intercepts pointer events"
    # (reproduced against a live instance). Scoping every locator to the
    # specific picker dialog avoids that ambiguity entirely.
    source_dialog = page.get_by_role("dialog", name="Source entity")
    page.get_by_label("Source entity", exact=True).click()
    # ha-entity-picker filters as-you-type off real input events — .fill()
    # sets the value without dispatching them, so the dropdown never narrows.
    # press_sequentially (not raw keyboard.type) re-focuses its target
    # locator itself so it survives the picker's internal re-renders — but
    # with NO per-character delay, typing fast enough could still transiently
    # blur the field between the picker's own filter-triggered re-renders,
    # and HA's global quick-bar hotkeys (bound to keydown on an unfocused
    # document, e.g. "d" for its Devices tab) hijack that stray keystroke
    # instead of it reaching the field — confirmed via screenshot showing
    # the quick-bar overlay appear mid-type. delay=100 gives each re-render
    # time to settle before the next character, avoiding it.
    search_field = source_dialog.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially(source_name, delay=100)
    source_dialog.get_by_text(source_name, exact=False).first.click()

    if target_device_name:
        device_dialog = page.get_by_role("dialog", name="Device")
        page.get_by_label("Device", exact=True).click()
        device_search = device_dialog.get_by_placeholder("Search", exact=True)
        device_search.wait_for(state="visible", timeout=5000)
        # Clicking the matched device by its exact display name (a real
        # mouse click on a specific element) rather than blindly pressing
        # Enter: Enter on this field intermittently submitted the WHOLE
        # subentry form instead of just picking the device — reproduced
        # against a live instance (the Submit button was already mid
        # "loading" transition by the time this function's own later,
        # explicit Submit click ran, which then hung waiting on an
        # element stuck detaching/reattaching). A targeted, dialog-scoped
        # click avoids both that keyboard-focus race and the
        # hidden-duplicate-text problem described above.
        device_dialog.get_by_text(target_device_name, exact=False).first.click()

    page.get_by_role("button", name=SUBMIT_BUTTON_NAME).click()
    page.wait_for_timeout(500)
    _dismiss_success_dialog(page)


def _dismiss_success_dialog(page) -> None:
    """Close the "Success ... Created configuration for ..." dialog HA shows
    after a create_entry step, if one appeared (same "finish|skip" pattern
    already used by every other config-flow test in this suite)."""
    finish_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if finish_button.count():
        finish_button.first.click()
        page.wait_for_timeout(300)


def test_second_sensor_bundles_onto_existing_device(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page

    # First-ever setup: adds the singleton root entry (no sensor fields),
    # or is a no-op if a previous test in this run already created it.
    _ensure_root_entry(page, hass_base_url)

    # Baseline BEFORE adding anything — other tests in a full-suite run may
    # already have created their own (unrelated) sensor.abstract_* entities
    # against this shared HA container, so absolute counts aren't safe to
    # assert on; only the delta this test itself causes is.
    baseline_count = len(_abstract_entities(hass_base_url, hass_bearer_token))

    # Add the first sensor via the subentry "add" action on the root entry.
    # "Battery Discharge Power" (rather than "Fridge Power", used as the
    # PRIMARY source elsewhere in this suite — test_config_flow_e2e.py,
    # test_translations_e2e.py) — unique_id is derived purely from
    # source_entity_id + device_type (see sensor.py), so reusing the same
    # source+type pair as another test would collide onto the SAME
    # existing entity/device when this suite runs as a whole against one
    # shared HA container, instead of creating a genuinely new one (this
    # test's own `baseline_count`-relative assertions below would then
    # spuriously fail) — confirmed by reproducing exactly that failure
    # against a live instance.
    _add_sensor_subentry(page, hass_base_url, source_name="Battery Discharge Power")

    # The entity registry lags the UI's own "Success" dialog: the
    # subentry's create_entry step (and the config-entry storage write it
    # causes) completes before the sensor platform has actually finished
    # setting up the new entity in the in-memory entity registry — a
    # one-shot query right after the dialog closes can observe zero new
    # entities yet (confirmed by comparing a one-shot query's result
    # against the on-disk entity registry moments later). Poll instead of
    # a fixed sleep.
    entities_after_first = _wait_for_entity_count(
        hass_base_url, hass_bearer_token, min_count=baseline_count + 1
    )
    devices_before = {e["device_id"] for e in entities_after_first if e.get("device_id")}
    assert len(entities_after_first) >= baseline_count + 1, (
        "expected at least one new sensor.abstract_* entity after the first "
        f"sensor, got {entities_after_first}"
    )
    assert len(devices_before) >= 1, (
        f"expected at least one abstractor device after the first sensor, got {devices_before}"
    )

    # Add the second sensor, targeting the same device this time. The first
    # sensor used the default device_type ("power", the schema's first
    # option) with no target device, so it created a fresh device named
    # "Abstract Power" (see sensor.py's DeviceInfo) — that's the device
    # this second sensor targets to prove bundling.
    _add_sensor_subentry(
        page,
        hass_base_url,
        source_name="Fridge Energy",
        device_type="Energy",
        target_device_name="Abstract Power",
    )

    entities_after_second = _wait_for_entity_count(
        hass_base_url, hass_bearer_token, min_count=baseline_count + 2
    )
    devices_after = {e["device_id"] for e in entities_after_second if e.get("device_id")}
    assert len(entities_after_second) >= baseline_count + 2, (
        "expected a second new sensor.abstract_* entity after the second "
        f"sensor, got {entities_after_second}"
    )
    assert devices_after == devices_before, (
        "expected the second sensor to join an existing device "
        f"{devices_before}, but a new device appeared: {devices_after}"
    )


def _abstract_entities(hass_base_url: str, token: str) -> list[dict]:
    """All sensor.abstract_* entity registry rows, via HA's WebSocket API.

    The entity registry (entity_id -> device_id mapping) is only exposed
    over HA's WebSocket API ("config/entity_registry/list" — see
    homeassistant/components/config/entity_registry.py, registered purely
    as a websocket_command with no REST view); there is no
    /api/config/entity_registry/list REST endpoint to call with `requests`
    (confirmed against a live instance — the plan this test was written
    from assumed one existed).

    Run inside a fresh worker thread (not `asyncio.run` directly): the
    pytest-playwright sync API already drives its own asyncio event loop
    on this (main) thread, so `asyncio.run` here would hit "cannot be
    called from a running event loop" (also confirmed live).
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        entities = executor.submit(
            lambda: asyncio.run(_fetch_entity_registry(hass_base_url, token))
        ).result()
    return [e for e in entities if e["entity_id"].startswith("sensor.abstract_")]


def _wait_for_entity_count(
    hass_base_url: str, token: str, *, min_count: int, timeout: float = 15.0
) -> list[dict]:
    """Poll the entity registry until at least `min_count` sensor.abstract_*
    rows exist (see `_abstract_entities`'s docstring for why a one-shot
    query right after the UI's "Success" dialog isn't reliable), instead of
    a fixed sleep."""
    deadline = time.monotonic() + timeout
    entities: list[dict] = []
    while time.monotonic() < deadline:
        entities = _abstract_entities(hass_base_url, token)
        if len(entities) >= min_count:
            return entities
        time.sleep(0.5)
    return entities


async def _fetch_entity_registry(hass_base_url: str, token: str) -> list[dict]:
    ws_url = hass_base_url.replace("http://", "ws://").replace("https://", "wss://")
    async with websockets.connect(f"{ws_url}/api/websocket") as ws:
        await ws.recv()  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth_result = json.loads(await ws.recv())
        assert auth_result["type"] == "auth_ok", auth_result

        await ws.send(json.dumps({"id": 1, "type": "config/entity_registry/list"}))
        while True:
            message = json.loads(await ws.recv())
            if message.get("id") == 1 and message["type"] == "result":
                assert message["success"], message
                return message["result"]
