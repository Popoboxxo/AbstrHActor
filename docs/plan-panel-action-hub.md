# Panel action-hub: init / edit / export / import via UI

## Decision

Keep the panel a **thin orchestrator**, not a second config engine. Every
write still goes through the existing, tested surfaces:

* Add/Edit → deep-link into HA's native Settings → Devices & Services UI
  (the ConfigFlow/ConfigSubentryFlow already implements this correctly,
  including the GH#18 device-mapping safety checks from
  `docs/device-mapping-ui-design.md`).
* Export/Import → the existing `export_data`/`import_data` services, called
  from the panel instead of Developer Tools → Actions.

No form logic, no registry-transaction logic, no validation logic is
duplicated in JS. This extends ADR-007, it doesn't reverse it: the panel
still isn't a second way to *configure fields*, it's a faster way to *reach*
the one way that already exists, plus a working export/import UX.

## Verified starting state

* Installed HA: `2026.2.3`. `homeassistant.core.SupportsResponse.ONLY` exists
  and is unused today — `export_data_service`/`import_data_service`
  (`__init__.py:587-598`) take no `supports_response`, so a service call
  today cannot hand data back to a caller.
* `export_data_service` only writes to the integration's `Store` — it never
  returns the snapshot. There is no HTTP view serving it either. A panel
  "Export" button has nothing to download today.
* `import_data_service` already accepts the full snapshot as `data` in the
  service call (`IMPORT_SERVICE_SCHEMA`, voluptuous-validated via
  `validate_snapshot`). This direction needs **no backend change** — the
  panel just needs to get a JSON file's content into that call.
* Snapshots never contain secrets: `_async_snapshot_entries` hardcodes
  `options={}` per subentry (`__init__.py:567`), so the root entry's
  `influx_token` is structurally excluded from export. Confirmed safe to
  let users download the file.
* Device pages (`/config/devices/device/<device_id>`) are a stable native HA
  route — device-level "Edit" can deep-link there today.
* The exact deep-link for "open the *add sensor* subentry dialog" from
  outside the integration page is not yet verified against 2026.2.3's
  frontend (frontend JS ships prebuilt, not inspectable from the Python
  package). Treat `/config/integrations/integration/abstractor` (stable,
  documented) as the guaranteed fallback target; verify during
  implementation whether a subentry-add URL fragment also works and use it
  if it does.

## Work items

### 1. Export — make the service return data

* `custom_components/abstractor/__init__.py`: register `export_data_service`
  with `supports_response=SupportsResponse.ONLY`; have it return
  `{"snapshot": snapshot}` in addition to the existing `_save_snapshot` write
  (keep the persist-to-Store side effect — diagnostics/restore still need it).
* `services.yaml`: no change needed — hassfest's `services.yaml` schema
  (`CORE_INTEGRATION_SERVICES_SCHEMA`/`CUSTOM_INTEGRATION_SERVICES_SCHEMA` in
  `script/hassfest/services.py`) has no `response` key at all; it only
  documents `fields`/`target`. Declaring one fails CI validation
  ("not a valid option at 'export_data.response'"). `supports_response` is a
  Python-only registration, nothing to add here.
* `tests/test_services.py`: assert the service call with
  `return_response=True` returns the built snapshot dict.

### 2. Panel — export button

* `www/abstractor-panel.js`: "Export" button calls
  `hass.callService("abstractor", "export_data", {}, undefined, false, true)`
  (`return_response: true`), then builds a `Blob` from the JSON response and
  triggers a download via a temporary `<a download>` element — standard
  browser download, no new dependency.

### 3. Panel — import button

* `www/abstractor-panel.js`: "Import" button opens a hidden
  `<input type="file" accept="application/json">`, reads the picked file with
  `FileReader`/`file.text()`, `JSON.parse`s it client-side (catch and show a
  parse error inline — server-side `validate_snapshot` remains the real
  gate), then calls `hass.callService("abstractor", "import_data", {data: parsed})`.
  Show the service-call error (`device_mapping_conflict`-style translated
  errors don't apply here, but voluptuous `Invalid` messages surface through
  the WS error) in the panel instead of letting it vanish into the log.
* No backend change needed for this direction — confirmed above.

### 4. Panel — init/add and edit buttons

* Per-device card: "Edit" button → `navigate(this, "/config/devices/device/" + d.id)`.
  Existing native page, no new code needed beyond the button/handler.
* Panel header: "Add sensor" button → `navigate(this, "/config/integrations/integration/abstractor")`
  as the guaranteed target. During implementation, check whether HA 2026.2.3
  supports a more direct subentry-add deep link (e.g. a query param the
  integrations page reads to auto-open "Add sensor"); if it does, use it —
  if not, the one-extra-click fallback stands, it's still fully in-panel
  navigation instead of hunting through the sidebar.

### 5. Tests

* `tests/test_frontend.py` / `tests_e2e/test_sidebar_panel_e2e.py`: extend
  for the new buttons — export triggers a service call with
  `return_response`, import round-trips a snapshot, edit/add buttons call
  `navigate()` with the expected path. Keep existing read-only-overview
  assertions untouched.
* `tests/test_services.py`: new `export_data` response-shape test (see #1).

## Explicitly out of scope

* No custom add/edit forms in the panel (would duplicate `config_flow.py`
  validation and the GH#18 ownership-safety transaction).
* No new HTTP endpoints (`SupportsResponse.ONLY` is a smaller diff than a
  registered `HomeAssistantView` and reuses the existing service).
* No change to `import_data`'s server-side contract — it already does what's
  needed.

## Files touched

* `custom_components/abstractor/__init__.py`
* `custom_components/abstractor/services.yaml`
* `custom_components/abstractor/www/abstractor-panel.js`
* `tests/test_services.py`
* `tests/test_frontend.py`
* `tests_e2e/test_sidebar_panel_e2e.py`
