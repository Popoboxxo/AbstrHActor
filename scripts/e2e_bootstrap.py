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
import json
import os
import sys
from urllib.parse import urlparse

import requests
from websockets.sync.client import connect

# Overridable for shared instances that already have their own users (the
# defaults match a fresh `scripts/e2e_bootstrap.py` provisioning run).
USERNAME = os.environ.get("E2E_USERNAME", "e2e")
PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-bootstrap-password-not-a-secret")
READONLY_USERNAME = os.environ.get("E2E_READONLY_USERNAME", "e2e-reader")
READONLY_PASSWORD = os.environ.get("E2E_READONLY_PASSWORD", PASSWORD)


def _websocket_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/api/websocket"


def _list_usernames(base_url: str, access_token: str) -> set[str]:
    """List usernames through the core websocket API (`config/auth/list`).

    Uses the synchronous websocket client: the bootstrap runs from a plain
    (non-async) pytest fixture, and pytest-asyncio may already own the loop.
    The previous implementation used `/api/manager/config/users/get`, which is
    not part of Home Assistant core and 404s on a plain instance.
    """
    with connect(_websocket_url(base_url), max_size=None) as ws:
        ws.recv()
        ws.send(json.dumps({"type": "auth", "access_token": access_token}))
        auth = json.loads(ws.recv())
        if auth.get("type") != "auth_ok":
            raise RuntimeError(f"websocket auth failed: {auth}")
        ws.send(json.dumps({"id": 1, "type": "config/auth/list"}))
        response = json.loads(ws.recv())
        if not response.get("success"):
            raise RuntimeError(f"config/auth/list failed: {response}")
        return {user.get("username") for user in response["result"] if user.get("username")}


def _ensure_readonly_user(base_url: str, access_token: str) -> None:
    """Warn when the NON-admin user used by the admin-gate E2E tests is absent.

    Core Home Assistant has no API to create a password credential for a new
    user, so a fresh instance only has the onboarding admin. The reader must be
    provisioned externally (or the gate tests skip); this function never
    silently pretends the gate was exercised.
    """
    names = _list_usernames(base_url, access_token)
    if READONLY_USERNAME in names:
        return
    print(
        f"WARNING: non-admin E2E user {READONLY_USERNAME!r} is missing; "
        "admin-gate tests will be skipped. Set E2E_READONLY_USERNAME to an "
        "existing non-admin username or provision one first.",
        file=sys.stderr,
    )


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
        requests.post(f"{base_url}/api/onboarding/core_config", headers=headers, timeout=10).raise_for_status()

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
        requests.post(f"{base_url}/api/onboarding/analytics", headers=headers, timeout=10).raise_for_status()

    return access_token


def bootstrap(base_url: str) -> str:
    """Return a bearer access token usable for subsequent E2E API/browser auth."""
    auth_code = _create_user(base_url)
    access_token = (
        _exchange_code_for_token(base_url, auth_code) if auth_code is not None else _login_for_token(base_url)
    )
    access_token = _finish_remaining_onboarding_steps(base_url, access_token)
    _ensure_readonly_user(base_url, access_token)
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
