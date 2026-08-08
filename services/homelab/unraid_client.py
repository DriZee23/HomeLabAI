# services/homelab/unraid_client.py
"""Unraid GraphQL API client for homelab tools.

Unraid 7.2+ ships a native GraphQL API (Settings -> Management Access -> API),
served at /graphql on the same host as the web UI, authenticated via an
`x-api-key` header. Older Unraid versions need the separate "Unraid Connect"
plugin instead — this client doesn't distinguish the two, since both expose
the same endpoint shape once enabled.

Only two queries are implemented so far (array_status, disk_health), using
the query shape confirmed in Unraid's own docs
(https://docs.unraid.net/API/how-to-use-the-api/):

    query {
        array {
            state
            capacity { disks { free used total } }
            disks { name size status temp }
        }
    }

Shares, cache-pool-specific usage, and full SMART reports are intentionally
NOT implemented here yet — Unraid's docs don't confirm those field names,
and guessing would silently produce broken queries against a real server.
Add them once the API is live and the actual schema can be checked (e.g. via
the GraphQL Sandbox at <UNRAID_API_URL minus /graphql>/graphql).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

UNRAID_API_URL_ENV = "UNRAID_API_URL"
UNRAID_API_KEY_ENV = "UNRAID_API_KEY"

UNRAID_ACCESS_HINT = (
    "The Unraid API isn't configured yet. Enable it on the Unraid host "
    "(Settings -> Management Access -> API), generate an API key, and set "
    f"{UNRAID_API_URL_ENV} (e.g. http://<unraid-host>/graphql) and "
    f"{UNRAID_API_KEY_ENV} in .env."
)

_ARRAY_QUERY = """
query {
    array {
        state
        capacity { disks { free used total } }
        disks { name size status temp }
    }
}
"""


class UnraidAccessError(RuntimeError):
    """The Unraid API isn't configured, is unreachable, or returned a GraphQL error."""


def unraid_api_configured(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get(UNRAID_API_URL_ENV, "").strip() and env.get(UNRAID_API_KEY_ENV, "").strip())


class UnraidClient:
    """Thin, gatekept wrapper around the Unraid GraphQL API.

    Nothing else in the codebase should call the Unraid API directly —
    everything routes through here so the access-policy check and query
    shapes live in exactly one place.
    """

    def __init__(self, url: str | None = None, api_key: str | None = None):
        self._url = url or os.getenv(UNRAID_API_URL_ENV)
        self._api_key = api_key or os.getenv(UNRAID_API_KEY_ENV)
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))

    def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._url or not self._api_key:
            raise UnraidAccessError(UNRAID_ACCESS_HINT)
        try:
            resp = self._client.post(
                self._url,
                json={"query": query, "variables": variables or {}},
                headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as exc:
            raise UnraidAccessError(
                f"Unraid API returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise UnraidAccessError(
                f"Could not reach the Unraid API at {self._url}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise UnraidAccessError(f"Unraid API returned a non-JSON response: {exc}") from exc

        if payload.get("errors"):
            messages = "; ".join(e.get("message", str(e)) for e in payload["errors"])
            raise UnraidAccessError(f"Unraid API returned GraphQL errors: {messages}")
        return payload.get("data") or {}

    def _get_array(self) -> dict[str, Any]:
        data = self._query(_ARRAY_QUERY)
        array = data.get("array")
        if array is None:
            raise UnraidAccessError("Unraid API response had no 'array' field — schema may differ from expected.")
        return array

    def array_status(self) -> dict[str, Any]:
        array = self._get_array()
        capacity = (array.get("capacity") or {}).get("disks") or {}
        return {
            "state": array.get("state"),
            "disk_count": len(array.get("disks") or []),
            "capacity_free_bytes": capacity.get("free"),
            "capacity_used_bytes": capacity.get("used"),
            "capacity_total_bytes": capacity.get("total"),
        }

    def disk_health(self) -> list[dict[str, Any]]:
        array = self._get_array()
        return [
            {
                "name": d.get("name"),
                "size_bytes": d.get("size"),
                "status": d.get("status"),
                "temp_celsius": d.get("temp"),
            }
            for d in (array.get("disks") or [])
        ]
