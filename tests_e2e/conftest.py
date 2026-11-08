"""Fixtures for Abstractor E2E tests.

These tests drive a REAL, running Home Assistant instance (see
docker-compose.e2e.yml / docker/docker-compose.demo.yml) through an actual
browser via Playwright — unlike tests/ (fast, isolated unit tests with no
HA instance at all). Requires the instance to already be reachable and
onboarded; see scripts/e2e_bootstrap.py.
"""
from __future__ import annotations

import os

import pytest

from scripts.e2e_bootstrap import (
    PASSWORD,
    READONLY_PASSWORD,
    READONLY_USERNAME,
    USERNAME,
    bootstrap,
)


def _enable_sockets() -> None:
    """Best-effort re-enable of `socket.socket` (pytest-socket optional)."""
    try:
        import pytest_socket
    except ImportError:  # E2E image does not install the HA unit-test plugin
        return
    pytest_socket.enable_socket()


def pytest_configure(config):
    """Re-enable sockets before session fixtures run.

    The HA pytest plugin disables socket creation in its per-test setup hook;
    the session-scoped bootstrap fixture runs before the function-scoped
    `_enable_network_sockets` fixture, so enable once here (and again per test
    through the autouse fixture below).
    """
    _enable_sockets()


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """Re-enable sockets after the HA plugin's unconditional disable hook."""
    _enable_sockets()


@pytest.fixture(autouse=True)
def _enable_network_sockets():
    """E2E drives a real HA instance over HTTP/websocket."""
    _enable_sockets()
    yield


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Force English + a wide viewport.

    HA's frontend picks its UI language from the browser's Accept-Language
    header (independent of the "language" field sent to the onboarding API,
    which only sets the backend's hass.config.language) — without this the
    UI renders in whatever locale the container's default Accept-Language
    resolves to, breaking every English-text locator in tests_e2e/.
    """
    return {**browser_context_args, "locale": "en-US", "viewport": {"width": 1600, "height": 900}}


@pytest.fixture(scope="session")
def hass_base_url() -> str:
    return os.environ.get("HASS_BASE_URL", "http://localhost:8123")


@pytest.fixture(scope="session")
def hass_credentials() -> tuple[str, str]:
    return USERNAME, PASSWORD


@pytest.fixture(scope="session")
def hass_bearer_token(hass_base_url: str) -> str:
    """Bootstrap onboarding (idempotent) and return an API bearer token."""
    # The HA pytest plugin disables socket.socket in its runtest hook; this
    # session fixture is created before function-scoped fixtures can undo it.
    _enable_sockets()
    return bootstrap(hass_base_url)


@pytest.fixture
def logged_in_page(page, hass_base_url, hass_credentials, hass_bearer_token):
    """A Playwright page already authenticated against the HA instance.

    Depends on hass_bearer_token (rather than just hass_base_url) purely to
    force onboarding to have run before the browser ever loads the page —
    the token itself isn't used here, only by tests that call the REST API
    directly (see test_net_flow_e2e.py).
    """
    # Under load (running the full suite back-to-back against a shared HA
    # container), the frontend's own render/filter cycles can take
    # noticeably longer than in an isolated single-test run — bump the
    # default action timeout well past Playwright's stock 30s so slow
    # renders don't get misdiagnosed as missing elements.
    page.set_default_timeout(60000)

    _enable_sockets()
    username, password = hass_credentials
    page.goto(hass_base_url)

    # Every test gets a fresh browser context (no shared cookies), so the
    # login form is always expected here — auto-wait on the locator itself
    # (rather than an upfront .count() check right after networkidle, which
    # races the SPA's client-side render and silently skips login if the
    # form hasn't painted yet) is what makes this reliable.
    username_field = page.locator("input[name='username']")
    username_field.wait_for(state="visible", timeout=15000)
    username_field.fill(username)
    password_field = page.locator("input[name='password']")
    password_field.fill(password)
    # The login button is a custom element that doesn't reliably expose
    # role="button" to Playwright's get_by_role — pressing Enter in the
    # password field submits the form the same way a real user's Enter
    # keypress would, and is what actually works here.
    password_field.press("Enter")
    page.wait_for_load_state("networkidle")

    return page


@pytest.fixture
def readonly_page(page, hass_base_url, hass_bearer_token):
    """A Playwright page authenticated as the NON-admin reader user (WS-3).

    Depends on hass_bearer_token so onboarding/bootstrapping is guaranteed to
    have run before the first browser navigation (this file is collected
    before the admin-page tests).

    Mirrors logged_in_page but with the second user the bootstrap creates.
    Tests that request this fixture must NOT also request logged_in_page:
    both share the per-test plugin `page`, so logging in twice in one test
    would fight over a single browser context.
    """
    page.set_default_timeout(60000)

    _enable_sockets()
    page.goto(hass_base_url)
    username_field = page.locator("input[name='username']")
    username_field.wait_for(state="visible", timeout=15000)
    username_field.fill(READONLY_USERNAME)
    password_field = page.locator("input[name='password']")
    password_field.fill(READONLY_PASSWORD)
    password_field.press("Enter")
    page.wait_for_load_state("networkidle")

    if page.locator("input[name='username']").count():
        pytest.skip(
            f"non-admin E2E user {READONLY_USERNAME!r} is not provisioned on this instance"
        )
    return page
