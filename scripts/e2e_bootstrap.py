"""Bootstrap a fresh Home Assistant instance for E2E tests via the REST
onboarding API instead of clicking through the UI wizard.

HA's onboarding has 4 steps that must ALL be completed before the frontend
stops redirecting every page to /onboarding.html, even for an already
logged-in user: user -> core_config -> integration -> analytics. The
"integration" step (POST /api/onboarding/integration) additionally mints
the actual browser-usable auth code — the one from the "user" step is only
good for finishing onboarding itself, not general API use.

Idempotent: if the user step is already done (e.g. instance was
bootstrapped by a previous run, or a human onboarded manually through the
UI), reuses the existing user via a normal password login and still
verifies/finishes any remaining steps.

Usage:
    python scripts/e2e_bootstrap.py [--base-url http://localhost:8123]
"""
from __future__ import annotations

import argparse
import sys

import requests

USERNAME = "e2e"
PASSWORD = "e2e-bootstrap-password-not-a-secret"


def _client_id(base_url: str) -> str:
    """HA validates client_id as a URL (matched against the instance's own
    origin), not an arbitrary string — mirrors what the onboarding UI sends."""
    return f"{base_url}/"


def _onboarding_status(base_url: str) -> list[dict] | None:
    """Return the per-step status list, or None once onboarding is fully
    complete — at that point HA stops registering the onboarding views
    entirely (including this status endpoint), rather than returning
    done=True for every step."""
    resp = requests.get(f"{base_url}/api/onboarding", timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _create_user(base_url: str) -> str | None:
    """Create the onboarding admin user. Returns an auth code, or None if
    the user step is already done (existing deployment)."""
    resp = requests.post(
        f"{base_url}/api/onboarding/users",
        json={
            "client_id": _client_id(base_url),
            "name": "E2E",
            "username": USERNAME,
            "password": PASSWORD,
            "language": "en",
        },
        timeout=10,
    )
    if resp.status_code == 403 and "already done" in resp.text.lower():
        return None
    if resp.status_code == 404:
        # Once ALL onboarding steps are done (not just "user"), HA tears
        # down the onboarding component's views entirely — the "already
        # done" 403 above only fires while onboarding is partially
        # complete; a fully-onboarded instance 404s here instead.
        return None
    resp.raise_for_status()
    return resp.json()["auth_code"]


def _exchange_code_for_token(base_url: str, auth_code: str) -> str:
    resp = requests.post(
        f"{base_url}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": _client_id(base_url),
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _login_for_token(base_url: str) -> str:
    """Fall back to a normal password login when the user step is already done."""
    flow = requests.post(
        f"{base_url}/auth/login_flow",
        json={
            "client_id": _client_id(base_url),
            "handler": ["homeassistant", None],
            "redirect_uri": f"{base_url}/",
        },
        timeout=10,
    )
    flow.raise_for_status()
    flow_id = flow.json()["flow_id"]

    step = requests.post(
        f"{base_url}/auth/login_flow/{flow_id}",
        json={
            "username": USERNAME,
            "password": PASSWORD,
            "client_id": _client_id(base_url),
        },
        timeout=10,
    )
    step.raise_for_status()
    auth_code = step.json()["result"]
    return _exchange_code_for_token(base_url, auth_code)


def _finish_remaining_onboarding_steps(base_url: str, access_token: str) -> str:
    """Complete whichever onboarding steps aren't done yet.

    Returns a (possibly updated) access token: the "integration" step mints
    its own fresh auth code, which must be exchanged again to get a token
    that's actually valid for general API/browser use going forward.
    """
    status = _onboarding_status(base_url)
    if status is None:
        return access_token

    headers = {"Authorization": f"Bearer {access_token}"}
    done = {s["step"] for s in status if s["done"]}

    if "core_config" not in done:
        requests.post(
            f"{base_url}/api/onboarding/core_config", headers=headers, timeout=10
        ).raise_for_status()

    if "integration" not in done:
        resp = requests.post(
            f"{base_url}/api/onboarding/integration",
            headers=headers,
            json={
                "client_id": _client_id(base_url),
                "redirect_uri": f"{base_url}/",
            },
            timeout=10,
        )
        resp.raise_for_status()
        access_token = _exchange_code_for_token(base_url, resp.json()["auth_code"])
        headers = {"Authorization": f"Bearer {access_token}"}

    if "analytics" not in done:
        requests.post(
            f"{base_url}/api/onboarding/analytics", headers=headers, timeout=10
        ).raise_for_status()

    return access_token


def bootstrap(base_url: str) -> str:
    """Return a bearer access token usable for subsequent E2E API/browser auth."""
    auth_code = _create_user(base_url)
    access_token = (
        _exchange_code_for_token(base_url, auth_code)
        if auth_code is not None
        else _login_for_token(base_url)
    )
    return _finish_remaining_onboarding_steps(base_url, access_token)


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
