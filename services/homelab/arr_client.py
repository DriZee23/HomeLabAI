# services/homelab/arr_client.py
"""Shared HTTP client base for the Servarr-family apps (Radarr, Sonarr).

Both apps share the same auth scheme (`X-Api-Key` header) and the same
paged-response envelope (`{"records": [...], "totalRecords": N, ...}`) for
/api/v3/queue and /api/v3/history, confirmed against each app's actual
QueueResource/HistoryResource C# source. Field-level differences (Movie vs
Series/Episode) are handled by the RadarrClient/SonarrClient subclasses.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class ArrAccessError(RuntimeError):
    """The app isn't configured, is unreachable, or returned an HTTP error."""


class ArrClient:
    def __init__(self, url_env: str, api_key_env: str, service_name: str):
        self._service_name = service_name
        self._url_env = url_env
        self._api_key_env = api_key_env
        self._base_url = (os.getenv(url_env) or "").rstrip("/")
        self._api_key = os.getenv(api_key_env)
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))

    def _configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._configured():
            raise ArrAccessError(
                f"{self._service_name} isn't configured. Set {self._url_env} "
                f"(e.g. http://<host>:<port>) and {self._api_key_env} "
                f"(Settings -> General -> Security -> API Key in {self._service_name}) in .env."
            )
        try:
            resp = self._client.get(
                f"{self._base_url}{path}", params=params, headers={"X-Api-Key": self._api_key}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ArrAccessError(
                f"{self._service_name} returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise ArrAccessError(
                f"Could not reach {self._service_name} at {self._base_url}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise ArrAccessError(f"{self._service_name} returned a non-JSON response: {exc}") from exc

    def _paged_get(self, path: str, params: dict[str, Any] | None = None, page_size: int = 25) -> list[dict]:
        merged = {"pageSize": page_size, **(params or {})}
        data = self._get(path, params=merged)
        return data.get("records") or []


class RadarrClient(ArrClient):
    def __init__(self):
        super().__init__("RADARR_URL", "RADARR_API_KEY", "Radarr")

    def queue(self, page_size: int = 25) -> list[dict]:
        records = self._paged_get("/api/v3/queue", params={"includeMovie": True}, page_size=page_size)
        return [
            {
                "title": (r.get("movie") or {}).get("title") or r.get("title"),
                "size_bytes": r.get("size"),
                "status": r.get("status"),
                "download_client": r.get("downloadClient"),
                "indexer": r.get("indexer"),
                "error_message": r.get("errorMessage"),
                "estimated_completion": r.get("estimatedCompletionTime"),
            }
            for r in records
        ]

    def history(self, page_size: int = 25) -> list[dict]:
        records = self._paged_get("/api/v3/history", page_size=page_size)
        return [
            {
                "title": (r.get("movie") or {}).get("title") or r.get("sourceTitle"),
                "event_type": r.get("eventType"),
                "date": r.get("date"),
                "download_id": r.get("downloadId"),
            }
            for r in records
        ]


class SonarrClient(ArrClient):
    def __init__(self):
        super().__init__("SONARR_URL", "SONARR_API_KEY", "Sonarr")

    def queue(self, page_size: int = 25) -> list[dict]:
        records = self._paged_get(
            "/api/v3/queue", params={"includeSeries": True, "includeEpisode": True}, page_size=page_size
        )
        return [
            {
                "title": self._episode_title(r) or r.get("title"),
                "size_bytes": r.get("size"),
                "status": r.get("status"),
                "download_client": r.get("downloadClient"),
                "indexer": r.get("indexer"),
                "error_message": r.get("errorMessage"),
                "estimated_completion": r.get("estimatedCompletionTime"),
            }
            for r in records
        ]

    def history(self, page_size: int = 25) -> list[dict]:
        records = self._paged_get("/api/v3/history", page_size=page_size)
        return [
            {
                "title": (r.get("series") or {}).get("title") or r.get("sourceTitle"),
                "event_type": r.get("eventType"),
                "date": r.get("date"),
                "download_id": r.get("downloadId"),
            }
            for r in records
        ]

    @staticmethod
    def _episode_title(record: dict) -> str | None:
        series = (record.get("series") or {}).get("title")
        episode = record.get("episode") or {}
        season = record.get("seasonNumber")
        ep_num = episode.get("episodeNumber")
        ep_title = episode.get("title")
        if not series:
            return None
        if season is not None and ep_num is not None:
            tag = f"S{int(season):02d}E{int(ep_num):02d}"
            return f"{series} {tag}" + (f" - {ep_title}" if ep_title else "")
        return series
