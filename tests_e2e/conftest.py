"""Fixtures for Abstractor E2E tests.

These tests drive a REAL, running Home Assistant instance (see
docker-compose.e2e.yml / docker/docker-compose.demo.yml) through an actual
browser via Playwright — unlike tests/ (fast, isolated unit tests with no
HA instance at all). Requires the instance to already be reachable and
onboarded; see scripts/e2e_bootstrap.py.
"""
from __future__ import annotations

import os
import re

import pytest

from scripts.e2e_bootstrap import USERNAME, PASSWORD, bootstrap


@pytest.fixture(scope="session")
def hass_base_url() -> str:
    return os.environ.get("HASS_BASE_URL", "http://localhost:8123")


@pytest.fixture(scope="session")
def hass_credentials() -> tuple[str, str]:
    return USERNAME, PASSWORD


@pytest.fixture(scope="session")
def hass_bearer_token(hass_base_url: str) -> str:
    """Bootstrap onboarding (idempotent) and return an API bearer token."""
    return bootstrap(hass_base_url)


@pytest.fixture
def logged_in_page(page, hass_base_url, hass_credentials, hass_bearer_token):
    """A Playwright page already authenticated against the HA instance.

    Depends on hass_bearer_token (rather than just hass_base_url) purely to
    force onboarding to have run before the browser ever loads the page —
    the token itself isn't used here, only by tests that call the REST API
    directly (see test_net_flow_e2e.py).
    """
    username, password = hass_credentials
    page.goto(hass_base_url)
    page.wait_for_load_state("networkidle")

    username_field = page.locator("input[name='username']")
    if username_field.count():
        username_field.fill(username)
        page.locator("input[name='password']").fill(password)
        page.get_by_role("button", name=re.compile("log ?in|anmelden", re.I)).click()
        page.wait_for_load_state("networkidle")

    return page
