"""Auth verification test for the IBM Maximo connector.

Makes a minimal live GET against the mxapiwodetail object structure
(oslc.pageSize=1) using credentials from dev_config.json (or
CONNECTOR_TEST_CONFIG_PATH / CONNECTOR_TEST_CONFIG_JSON env vars).

Run:
    CONNECTOR_TEST_CONFIG_PATH=tests/unit/sources/ibm_maximo/configs/dev_config.json \
        python tests/unit/sources/ibm_maximo/test_auth_verify.py

Reports whether auth passed or failed, including HTTP status / error detail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Resolve repo root so relative imports work when executed as a script.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT))

from tests.unit.sources.test_utils import load_config  # noqa: E402

_DEV_CONFIG_PATH = Path(__file__).parent / "configs" / "dev_config.json"

# Object structure used for the probe — almost every Maximo instance has
# Work Orders, making it the most reliable probe target.
_PROBE_OS = "mxapiwodetail"
# Attempt routes in this order so MAS Manage sandbox trials (which need /api)
# are tried first.
_ROUTES = ["api", "oslc"]
_PAGE_SIZE = 1


def _build_headers(config: dict) -> dict:
    headers = {
        "apikey": config["api_key"],
        "Accept": "application/json",
    }
    x_public_uri = config.get("x_public_uri")
    if x_public_uri:
        headers["x-public-uri"] = x_public_uri
    return headers


def _probe(base_url: str, route: str, headers: dict) -> requests.Response:
    url = f"{base_url.rstrip('/')}/maximo/{route}/os/{_PROBE_OS}"
    params = {
        "lean": "1",
        "oslc.pageSize": str(_PAGE_SIZE),
        "oslc.select": "wonum,description,status",
    }
    return requests.get(url, headers=headers, params=params, timeout=30)


def run_auth_check() -> None:
    config = load_config(default_path=_DEV_CONFIG_PATH)
    base_url: str = config.get("base_url") or config.get("host", "")
    api_key: str = config.get("api_key", "")

    if not base_url:
        print("FAIL  — config missing 'base_url' / 'host'")
        sys.exit(1)
    if not api_key:
        print("FAIL  — config missing 'api_key'")
        sys.exit(1)

    print(f"Target : {base_url}")
    print(f"API key: {'*' * max(0, len(api_key) - 4)}{api_key[-4:]}")

    # Determine which route(s) to try.
    explicit_route = config.get("api_route", "").strip().lower()
    routes = [explicit_route] if explicit_route in ("oslc", "api") else _ROUTES

    headers = _build_headers(config)
    x_public_uri = config.get("x_public_uri")
    if x_public_uri:
        print(f"x-public-uri header: {x_public_uri}")

    last_status: int | None = None
    last_body: str = ""
    for route in routes:
        url_display = f"{base_url.rstrip('/')}/maximo/{route}/os/{_PROBE_OS}"
        print(f"\nProbing [{route}]: {url_display} ...")
        try:
            resp = _probe(base_url, route, headers)
        except requests.exceptions.SSLError as exc:
            print(f"  SSL error: {exc}")
            last_body = str(exc)
            continue
        except requests.exceptions.ConnectionError as exc:
            print(f"  Connection error: {exc}")
            last_body = str(exc)
            continue
        except requests.exceptions.Timeout:
            print("  Request timed out after 30 s")
            last_body = "Timeout"
            continue

        last_status = resp.status_code
        last_body = resp.text[:500]

        print(f"  HTTP {resp.status_code}")

        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "")
            # A 200 with an HTML body is a SAML/SSO redirect — the server
            # ignored the API key and is bouncing to an identity provider.
            # That is an auth failure, not a success.
            if "text/html" in content_type or resp.text.lstrip().startswith("<"):
                print(
                    "  Body is HTML (SAML/SSO redirect) — API key was not "
                    "accepted; server redirected to identity provider."
                )
                print(f"  Body excerpt: {resp.text[:200]}")
                last_body = resp.text[:500]
                continue
            try:
                body = resp.json()
                members = body.get("member") or []
                print(f"  Response: {len(members)} record(s) returned in first page")
                if members:
                    print(f"  Sample record keys: {list(members[0].keys())[:8]}")
            except json.JSONDecodeError:
                print(f"  Response body (non-JSON, not HTML): {resp.text[:200]}")
                last_body = resp.text[:500]
                continue
            print(f"\nPASS  — auth succeeded via route '{route}'")
            sys.exit(0)

        # 401 / 403 are definitive auth failures — no need to try next route.
        if resp.status_code in (401, 403):
            print(f"  Body: {resp.text[:300]}")
            print(f"\nFAIL  — authentication rejected (HTTP {resp.status_code})")
            sys.exit(1)

        print(f"  Body: {resp.text[:300]}")

    # All routes exhausted without a 200.
    print(
        f"\nFAIL  — no route returned HTTP 200 "
        f"(last status: {last_status}, body excerpt: {last_body[:200]})"
    )
    sys.exit(1)


if __name__ == "__main__":
    run_auth_check()
