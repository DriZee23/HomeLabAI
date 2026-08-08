# services/homelab/sabnzbd_client.py
"""SABnzbd API client — confirmed against sabnzbd.org/wiki/configuration/5.0/api.

Auth: `apikey` query parameter (not a header) on the single `/api` endpoint,
dispatched by `mode`.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class SabnzbdAccessError(RuntimeError):
    """SABnzbd isn't configured, is unreachable, or returned an error."""


class SabnzbdClient:
    def __init__(self):
        self._base_url = (os.getenv("SABNZBD_URL") or "").rstrip("/")
        self._api_key = os.getenv("SABNZBD_API_KEY")
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))

    def _configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    def queue(self) -> list[dict]:
        if not self._configured():
            raise SabnzbdAccessError(
                "SABnzbd isn't configured. Set SABNZBD_URL (e.g. http://<host>:8080) "
                "and SABNZBD_API_KEY (Settings -> General -> API Key) in .env."
            )
        try:
            resp = self._client.get(
                f"{self._base_url}/api",
                params={"mode": "queue", "output": "json", "apikey": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise SabnzbdAccessError(
                f"SABnzbd returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise SabnzbdAccessError(
                f"Could not reach SABnzbd at {self._base_url}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise SabnzbdAccessError(f"SABnzbd returned a non-JSON response: {exc}") from exc

        if isinstance(data, dict) and data.get("error"):
            raise SabnzbdAccessError(f"SABnzbd API error: {data['error']}")

        slots = ((data or {}).get("queue") or {}).get("slots") or []
        return [
            {
                "name": s.get("filename"),
                "status": s.get("status"),
                "size": s.get("size"),
                "size_left": s.get("sizeleft"),
                "percentage": s.get("percentage"),
                "time_left": s.get("timeleft"),
                "category": s.get("cat"),
            }
            for s in slots
        ]
