# services/homelab/unraid_client.py
"""Unraid GraphQL API client for homelab tools.

Unraid 7.2+ ships a native GraphQL API (Settings -> Management Access -> API),
served at /graphql on the same host as the web UI, authenticated via an
`x-api-key` header. Older Unraid versions need the separate "Unraid Connect"
plugin instead — this client doesn't distinguish the two, since both expose
the same endpoint shape once enabled.

Only two queries are implemented so far (array_status, disk_health). The
query shape was corrected 2026-08-09 against a real server via the GraphQL
Sandbox after Unraid's own docs turned out incomplete on several points:

  1. Disks are NOT all under one `array.disks` list — Unraid splits them
     into three separate lists: `disks` (data), `parities`, `caches`.
     A cache-only array (no data/parity disks assigned) legitimately
     returns `disks: []`; that is not an error.
  2. All numeric size fields (`size`/`free`/`used`/`total`) come back as
     GraphQL strings (BigInt-safe serialization, e.g. `"3907018532"`), not
     native numbers — `int(value)` before use, don't assume a JSON number.
  3. `disks[].size` is in KiB, not bytes (confirmed: a real 4TB cache disk
     returned size="3907018532", which is exactly 3907018532 KiB ~= 3.64
     TiB, a real 4TB drive's actual formatted capacity — not bytes, which
     would be ~3.9MB and obviously wrong).
  4. `array.capacity` has TWO sibling sub-objects that are easy to
     conflate: `disks { free used total }` is a DISK SLOT COUNT (e.g.
     free=30/used=0/total=30 means "30 empty array disk slots", not any
     byte quantity), while `kilobytes { free used total }` is the real
     array capacity in KiB. Both are legitimately 0/tiny numbers on an
     array with no data/parity disks assigned — that's not a bug, it's an
     accurate reflection that Unraid's "array" concept excludes cache
     pools. For a useful "how much storage do I have" figure on
     cache-only setups, this module also computes a `total_storage_bytes`
     from summed disk/parity/cache sizes rather than relying on
     `capacity.kilobytes` alone.

Shares confirmed 2026-08-09 via a real server: there's a top-level `shares`
query (sibling to `array`, not nested under it), returning `free`/`used` in
KiB (same convention as everywhere else) — but these reflect the underlying
STORAGE POOL, not per-share usage (every share on the same pool reports
identical free/used; shares are logical folders, not fixed allocations).
No separate cache_usage query was added — shares() already reports
pool-level free/used space, so a second tool saying the same thing would
just be redundant (and riskier to get right for multi-pool setups this
user's box can't be used to verify against).

Full SMART reports are intentionally NOT implemented here yet — SMART
attribute data is more varied than anything confirmed so far and guessing
would silently produce broken queries. Add it once checked against the
GraphQL Sandbox at <UNRAID_API_URL minus /graphql>/graphql.
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
        capacity {
            disks { free used total }
            kilobytes { free used total }
        }
        disks { name size status temp type }
        parities { name size status temp type }
        caches { name size status temp type }
    }
}
"""

_SHARES_QUERY = """
query {
    shares {
        name
        comment
        free
        used
        size
    }
}
"""

_KIB = 1024


def _to_int(value):
    """Unraid's GraphQL API serializes numeric fields as strings (BigInt-safe).
    Returns None for anything that isn't a valid integer."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _kib_to_bytes(value):
    n = _to_int(value)
    return n * _KIB if n is not None else None


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

    @staticmethod
    def _extract_disks(array: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for role in ("disks", "parities", "caches"):
            for d in array.get(role) or []:
                result.append({
                    "name": d.get("name"),
                    "size_bytes": _kib_to_bytes(d.get("size")),
                    "status": d.get("status"),
                    "temp_celsius": _to_int(d.get("temp")),
                    "role": d.get("type") or role,
                })
        return result

    def array_status(self) -> dict[str, Any]:
        array = self._get_array()
        capacity = array.get("capacity") or {}
        slots = capacity.get("disks") or {}
        kb = capacity.get("kilobytes") or {}
        disks = self._extract_disks(array)

        return {
            "state": array.get("state"),
            "disk_count": len(disks),
            # Array disk-slot counts (NOT a byte quantity) — how many
            # data/parity disk slots are configured/free/used.
            "disk_slots_total": _to_int(slots.get("total")),
            "disk_slots_used": _to_int(slots.get("used")),
            "disk_slots_free": _to_int(slots.get("free")),
            # Real array (data+parity only, excludes cache pools) capacity
            # in bytes. Legitimately 0 on a cache-only setup.
            "array_capacity_total_bytes": _kib_to_bytes(kb.get("total")),
            "array_capacity_used_bytes": _kib_to_bytes(kb.get("used")),
            "array_capacity_free_bytes": _kib_to_bytes(kb.get("free")),
            # Sum of every attached disk/parity/cache's raw size — the
            # generally useful "how much storage do I have" figure,
            # especially for cache-only setups where array_capacity_* is 0.
            # This is raw capacity, not accounting for parity overhead or
            # how much of it is actually free.
            "total_storage_bytes": sum(
                d["size_bytes"] for d in disks if d.get("size_bytes") is not None
            ) or None,
        }

    def disk_health(self) -> list[dict[str, Any]]:
        array = self._get_array()
        return self._extract_disks(array)

    def shares(self) -> list[dict[str, Any]]:
        data = self._query(_SHARES_QUERY)
        shares_list = data.get("shares")
        if shares_list is None:
            raise UnraidAccessError("Unraid API response had no 'shares' field — schema may differ from expected.")
        return [
            {
                "name": s.get("name"),
                "comment": s.get("comment") or None,
                # size=0 means no per-share size quota is configured (the
                # share can grow to fill whatever's free on its pool).
                "size_bytes": _kib_to_bytes(s.get("size")) or None,
                "free_bytes": _kib_to_bytes(s.get("free")),
                "used_bytes": _kib_to_bytes(s.get("used")),
            }
            for s in shares_list
        ]
