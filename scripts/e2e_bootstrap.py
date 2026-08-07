"""Bootstrap a fresh Home Assistant instance for E2E tests via the REST
onboarding API instead of clicking through the UI wizard.

Idempotent: if onboarding is already done (e.g. instance was bootstrapped
by a previous run), reuses the existing user by logging in instead of
failing. Prints a short-lived OAuth access token on stdout as the only
output on success (good enough for a CI run's lifetime), so it composes
as:

    export HASS_TOKEN=$(python scripts/e2e_bootstrap.py)

Usage:
    python scripts/e2e_bootstrap.py [--base-url http://localhost:8123]
"""
from __future__ import annotations

import argparse
import sys

import requests

USERNAME = "e2e"
PASSWORD = "e2e-bootstrap-password-not-a-secret"
CLIENT_ID = "e2e-bootstrap"
LLAT_NAME = "e2e-bootstrap-token"


def _onboarding_status(base_url: str) -> list[dict]:
    resp = requests.get(f"{base_url}/api/onboarding", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _create_user(base_url: str) -> str | None:
    """Create the onboarding admin user. Returns an auth code, or None if
    the user step is already done (existing deployment)."""
    resp = requests.post(
        f"{base_url}/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "E2E",
            "username": USERNAME,
            "password": PASSWORD,
            "language": "en",
        },
        timeout=10,
    )
    if resp.status_code == 403 and "already done" in resp.text.lower():
        return None
    resp.raise_for_status()
    return resp.json()["auth_code"]


def _exchange_code_for_token(base_url: str, auth_code: str) -> str:
    resp = requests.post(
        f"{base_url}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _login_for_token(base_url: str) -> str:
    """Fall back to a normal password login when onboarding is already done."""
    flow = requests.post(
        f"{base_url}/auth/login_flow",
        json={
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": f"{base_url}/",
        },
        timeout=10,
    )
    flow.raise_for_status()
    flow_id = flow.json()["flow_id"]

    step = requests.post(
        f"{base_url}/auth/login_flow/{flow_id}",
        json={"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID},
        timeout=10,
    )
    step.raise_for_status()
    auth_code = step.json()["result"]
    return _exchange_code_for_token(base_url, auth_code)


def _finish_remaining_onboarding_steps(base_url: str, access_token: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    steps = _onboarding_status(base_url)
    done = {s["step"] for s in steps if s["done"]}

    if "core_config" not in done:
        requests.post(
            f"{base_url}/api/onboarding/core_config", headers=headers, timeout=10
        ).raise_for_status()

    if "analytics" not in done:
        requests.post(
            f"{base_url}/api/onboarding/analytics", headers=headers, timeout=10
        ).raise_for_status()


def bootstrap(base_url: str) -> str:
    """Return a bearer access token usable for subsequent E2E API/browser auth."""
    auth_code = _create_user(base_url)
    if auth_code is not None:
        access_token = _exchange_code_for_token(base_url, auth_code)
        _finish_remaining_onboarding_steps(base_url, access_token)
    else:
        access_token = _login_for_token(base_url)
    return access_token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8123")
    args = parser.parse_args()

    try:
        token = bootstrap(args.base_url)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"e2e_bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
