# services/homelab/bazarr_client.py
"""Bazarr API client — confirmed against Bazarr's own source
(bazarr/api/utils.py's `authenticate` decorator, bazarr/api/movies/wanted.py).

Auth: `X-API-KEY` header (apikey query/form param also accepted server-side,
header is cleanest for a GET-only client).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class BazarrAccessError(RuntimeError):
    """Bazarr isn't configured, is unreachable, or returned an HTTP error."""


class BazarrClient:
    def __init__(self):
        self._base_url = (os.getenv("BAZARR_URL") or "").rstrip("/")
        self._api_key = os.getenv("BAZARR_API_KEY")
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))

    def _configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._configured():
            raise BazarrAccessError(
                "Bazarr isn't configured. Set BAZARR_URL (e.g. http://<host>:6767) "
                "and BAZARR_API_KEY (Settings -> General -> Security -> API Key) in .env."
            )
        try:
            resp = self._client.get(
                f"{self._base_url}{path}", params=params, headers={"X-API-KEY": self._api_key}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise BazarrAccessError(
                f"Bazarr returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise BazarrAccessError(
                f"Could not reach Bazarr at {self._base_url}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise BazarrAccessError(f"Bazarr returned a non-JSON response: {exc}") from exc

    def missing_subtitles(self) -> list[dict]:
        movies = (self._get("/api/movies/wanted") or {}).get("data") or []
        episodes = (self._get("/api/episodes/wanted") or {}).get("data") or []
        result = [
            {"title": m.get("title"), "type": "movie", "missing_languages": m.get("missing_subtitles")}
            for m in movies
        ]
        result += [
            {
                "title": f"{e.get('seriesTitle')} S{e.get('season', 0):02d}E{e.get('episode', 0):02d}",
                "type": "episode",
                "missing_languages": e.get("missing_subtitles"),
            }
            for e in episodes
        ]
        return result
