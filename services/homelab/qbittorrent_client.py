# services/homelab/qbittorrent_client.py
"""qBittorrent WebUI API client — confirmed against the qBittorrent wiki
(WebUI API v2). Unlike every other homelab integration so far, this one is
NOT API-key based: auth is a session cookie obtained by POSTing credentials
to /api/v2/auth/login. The client logs in lazily on first use and re-logs
in once if a call comes back unauthorized (session expired).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class QbittorrentAccessError(RuntimeError):
    """qBittorrent isn't configured, is unreachable, or login/query failed."""


class QbittorrentClient:
    def __init__(self):
        self._base_url = (os.getenv("QBITTORRENT_URL") or "").rstrip("/")
        self._username = os.getenv("QBITTORRENT_USERNAME")
        self._password = os.getenv("QBITTORRENT_PASSWORD")
        self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0))
        self._logged_in = False

    def _configured(self) -> bool:
        return bool(self._base_url and self._username and self._password)

    def _login(self) -> None:
        try:
            resp = self._client.post(
                f"{self._base_url}/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
                headers={"Referer": self._base_url},
            )
            resp.raise_for_status()
        except httpx.RequestError as exc:
            raise QbittorrentAccessError(
                f"Could not reach qBittorrent at {self._base_url}: {type(exc).__name__}: {exc}"
            ) from exc
        if resp.text.strip() != "Ok.":
            raise QbittorrentAccessError("qBittorrent login rejected — check QBITTORRENT_USERNAME/PASSWORD.")
        self._logged_in = True

    def queue(self) -> list[dict]:
        if not self._configured():
            raise QbittorrentAccessError(
                "qBittorrent isn't configured. Set QBITTORRENT_URL (e.g. http://<host>:8080), "
                "QBITTORRENT_USERNAME, and QBITTORRENT_PASSWORD (WebUI login credentials) in .env."
            )
        if not self._logged_in:
            self._login()

        try:
            resp = self._client.get(f"{self._base_url}/api/v2/torrents/info")
            if resp.status_code == 403:
                # Session expired — log in once more before giving up.
                self._login()
                resp = self._client.get(f"{self._base_url}/api/v2/torrents/info")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise QbittorrentAccessError(
                f"qBittorrent returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise QbittorrentAccessError(
                f"Could not reach qBittorrent at {self._base_url}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise QbittorrentAccessError(f"qBittorrent returned a non-JSON response: {exc}") from exc

        return [
            {
                "name": t.get("name"),
                "state": t.get("state"),
                "progress_percent": round((t.get("progress") or 0) * 100, 1),
                "size": t.get("size"),
                "dl_speed": t.get("dlspeed"),
                "eta_seconds": t.get("eta"),
                "category": t.get("category"),
            }
            for t in (data or [])
        ]
