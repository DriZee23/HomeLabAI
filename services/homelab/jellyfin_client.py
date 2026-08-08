# services/homelab/jellyfin_client.py
"""Jellyfin REST API client for homelab media tools.

Auth: `X-Emby-Token` header carrying an API key generated in Jellyfin's
Dashboard -> API Keys (confirmed against Jellyfin's own
AuthorizationContext source, which also accepts X-MediaBrowser-Token/
api_key/ApiKey as aliases — X-Emby-Token is the most broadly compatible).
JELLYFIN_USER_ID is optional but recommended for continue_watching/
recently_added, which are meant to be personalized per-user; without it
those calls still work but reflect server-wide/unfiltered results.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class JellyfinAccessError(RuntimeError):
    """Jellyfin isn't configured, is unreachable, or returned an HTTP error."""


class JellyfinClient:
    def __init__(self):
        self._base_url = (os.getenv("JELLYFIN_URL") or "").rstrip("/")
        self._api_key = os.getenv("JELLYFIN_API_KEY")
        self._user_id = os.getenv("JELLYFIN_USER_ID")
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))

    def _configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._configured():
            raise JellyfinAccessError(
                "Jellyfin isn't configured. Set JELLYFIN_URL (e.g. http://<host>:8096) "
                "and JELLYFIN_API_KEY (Dashboard -> API Keys) in .env."
            )
        try:
            resp = self._client.get(
                f"{self._base_url}{path}", params=params, headers={"X-Emby-Token": self._api_key}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise JellyfinAccessError(
                f"Jellyfin returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise JellyfinAccessError(
                f"Could not reach Jellyfin at {self._base_url}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise JellyfinAccessError(f"Jellyfin returned a non-JSON response: {exc}") from exc

    def sessions(self) -> list[dict]:
        data = self._get("/Sessions", params={"activeWithinSeconds": 960})
        return [
            {
                "user": s.get("UserName"),
                "client": s.get("Client"),
                "device": s.get("DeviceName"),
                "playing": (s.get("NowPlayingItem") or {}).get("Name"),
                "playing_type": (s.get("NowPlayingItem") or {}).get("Type"),
            }
            for s in (data or [])
        ]

    def recently_added(self, limit: int = 20) -> list[dict]:
        params = {"Limit": limit}
        if self._user_id:
            params["userId"] = self._user_id
        data = self._get("/Items/Latest", params=params)
        return [{"name": i.get("Name"), "type": i.get("Type"), "date_added": i.get("DateCreated")} for i in (data or [])]

    def continue_watching(self, limit: int = 20) -> list[dict]:
        params = {"Limit": limit}
        if self._user_id:
            params["userId"] = self._user_id
        data = self._get("/UserItems/Resume", params=params)
        items = (data or {}).get("Items") or []
        return [
            {
                "name": i.get("Name"),
                "series": (i.get("SeriesName")),
                "type": i.get("Type"),
                "progress_percent": round(((i.get("UserData") or {}).get("PlayedPercentage") or 0), 1),
            }
            for i in items
        ]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        params = {"searchTerm": query, "Recursive": True, "Limit": limit}
        if self._user_id:
            params["userId"] = self._user_id
        data = self._get("/Items", params=params)
        items = (data or {}).get("Items") or []
        return [{"name": i.get("Name"), "type": i.get("Type"), "year": i.get("ProductionYear")} for i in items]

    def library_stats(self) -> dict:
        counts = {}
        for item_type in ("Movie", "Series", "Episode"):
            params = {"includeItemTypes": item_type, "Recursive": True, "Limit": 0}
            if self._user_id:
                params["userId"] = self._user_id
            data = self._get("/Items", params=params)
            counts[item_type.lower() + "_count"] = (data or {}).get("TotalRecordCount")
        return counts
