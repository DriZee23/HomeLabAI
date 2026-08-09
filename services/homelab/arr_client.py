# services/homelab/arr_client.py
"""Shared HTTP client base for the Servarr-family apps (Radarr, Sonarr).

Both apps share the same auth scheme (`X-Api-Key` header) and the same
paged-response envelope (`{"records": [...], "totalRecords": N, ...}`) for
/api/v3/queue and /api/v3/history, confirmed against each app's actual
QueueResource/HistoryResource C# source. Field-level differences (Movie vs
Series/Episode) are handled by the RadarrClient/SonarrClient subclasses.

Write actions (add_qbittorrent_download_client, add_root_folder) use the
same "provider" pattern confirmed against ProviderControllerBase.cs and
SchemaBuilder.cs: rather than hardcoding a POST body shape (which is
implementation-specific and version-fragile), fetch the live schema
template for the target implementation from GET .../schema, then only
override the specific field values needed by name -- field names are the
camelCase form of the C# settings property (e.g. QBittorrentSettings.Host
-> "host"), confirmed via SchemaBuilder.GetCamelCaseName. This avoids
guessing the full field list/order/types, which differ per implementation
and app version.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class ArrAccessError(RuntimeError):
    """The app isn't configured, is unreachable, or returned an HTTP error."""


class ArrClient:
    # Overridden by RadarrClient/SonarrClient: the qBittorrent settings field
    # (confirmed via QBittorrentSettings.cs) that holds the download category,
    # and a sane default value for it.
    _qbt_category_field: str = "movieCategory"
    _qbt_default_category: str = "radarr"

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

    def _post(self, path: str, json_body: dict) -> Any:
        if not self._configured():
            raise ArrAccessError(
                f"{self._service_name} isn't configured. Set {self._url_env} "
                f"(e.g. http://<host>:<port>) and {self._api_key_env} "
                f"(Settings -> General -> Security -> API Key in {self._service_name}) in .env."
            )
        try:
            resp = self._client.post(
                f"{self._base_url}{path}", json=json_body, headers={"X-Api-Key": self._api_key}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ArrAccessError(
                f"{self._service_name} returned HTTP {exc.response.status_code}: {exc.response.text[:300]}"
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

    @staticmethod
    def _set_field(fields: list[dict], name: str, value: Any) -> None:
        for f in fields:
            if f.get("name") == name:
                f["value"] = value
                return

    def _provider_schema(self, resource: str, implementation: str) -> dict:
        templates = self._get(f"/api/v3/{resource}/schema")
        for template in templates or []:
            if template.get("implementation") == implementation:
                return template
        raise ArrAccessError(
            f"{self._service_name} has no '{implementation}' {resource} implementation available."
        )

    def add_qbittorrent_download_client(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        category: str | None = None,
        use_ssl: bool = False,
    ) -> dict:
        template = self._provider_schema("downloadclient", "QBittorrent")
        fields = [dict(f) for f in (template.get("fields") or [])]
        self._set_field(fields, "host", host)
        self._set_field(fields, "port", port)
        self._set_field(fields, "useSsl", use_ssl)
        if username:
            self._set_field(fields, "username", username)
        if password:
            self._set_field(fields, "password", password)
        self._set_field(fields, self._qbt_category_field, category or self._qbt_default_category)

        body = dict(template)
        body["name"] = "qBittorrent"
        body["enable"] = True
        body["fields"] = fields
        result = self._post("/api/v3/downloadclient", body)
        return {"id": result.get("id"), "name": result.get("name"), "enabled": result.get("enable")}

    def add_root_folder(self, path: str) -> dict:
        result = self._post("/api/v3/rootfolder", {"path": path})
        return {"id": result.get("id"), "path": result.get("path")}


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
    # Confirmed via Sonarr's own QBittorrentSettings.cs: the field is
    # "TvCategory" (-> "tvCategory"), not "MovieCategory" like Radarr's.
    _qbt_category_field = "tvCategory"
    _qbt_default_category = "sonarr"

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
