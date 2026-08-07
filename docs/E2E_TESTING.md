# E2E testing (ADR-008)

`tests/` are fast, isolated unit tests with mocked Home Assistant objects —
no real HA instance, no browser, milliseconds per test. They cover pipeline
logic (`filters.py`), coordinator behavior, and entity identity in
isolation.

`tests_e2e/` are a different, complementary layer: they drive a **real,
running Home Assistant instance** through an **actual browser**
(Playwright), covering the things unit tests structurally cannot —
Config Flow / Options Flow rendering, the sidebar panel's vanilla-JS Web
Component, and the full source-state → coordinator → filter pipeline →
entity chain end to end.

## Why a real HA instance instead of more mocking

Several of the bugs found in this project's own code review (e.g. the
config-flow field mismatch that silently dropped a source entity, and the
`InfluxExporter` timeout not being caught) are exactly the class of bug
that passes unit tests with mocked `hass`/`entry` objects but breaks
against real HA behavior. E2E tests are the only layer that would have
caught them.

## Running locally

```bash
bash docker/setup-demo.sh   # fetch hass-virtual once (not vendored, see docker/README.md)
docker compose -f docker-compose.e2e.yml up --build --abort-on-container-exit
docker compose -f docker-compose.e2e.yml down -v
```

Test results (screenshots on failure, etc.) land in `./test-results/`.

## Running against the manual demo instance

If `docker/docker-compose.demo.yml` is already up (see `docker/README.md`)
and onboarded, point the E2E runner at it directly instead of spinning up
a second instance:

```bash
pip install -r requirements_e2e.txt
playwright install --with-deps chromium
HASS_BASE_URL=http://localhost:8123 pytest tests_e2e/ -v
```

## What's covered

| Test file | Requirement/ADR |
|---|---|
| `test_config_flow_e2e.py` | REQ-CORE-002 — Config Flow produces a live entity |
| `test_unique_id_stability_e2e.py` | REQ-CORE-001 — reconfiguring the source keeps entity_id stable (live-browser counterpart to `tests/test_sensor.py`) |
| `test_sidebar_panel_e2e.py` | ADR-007 — sidebar panel renders real device data |
| `test_net_flow_e2e.py` | REQ-CORE-005 — net-flow subtraction, driven via `virtual.set` on hass-virtual sensors |

## CI

`.github/workflows/e2e.yaml` runs this suite on `workflow_dispatch`, a
weekly schedule, and PRs touching `custom_components/abstractor/`,
`tests_e2e/`, or the E2E compose/Dockerfile. It's deliberately **not** on
every push (unlike `validate.yaml`'s HACS/hassfest checks) — a full
browser + HA instance boot is too slow/heavy to gate every commit, but the
regressions it catches are important enough to run automatically on the
paths that could introduce them.

## Locators are English-only

`scripts/e2e_bootstrap.py` onboards with `language: "en"`, so all Playwright
locators in `tests_e2e/` target English HA UI text. If you run these tests
against a manually-onboarded instance set to a different language, they
will not find the expected buttons/labels.
