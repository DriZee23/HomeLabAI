# src/agent_tools/arr_setup_tools.py
"""Write tools that wire the *arr stack together: add qBittorrent as a
download client in Radarr/Sonarr, and add root folders. Each is
schema-driven (services.homelab.arr_client.ArrClient.add_qbittorrent_download_client/
add_root_folder) rather than hardcoding a POST body shape, confirmed against
the real Radarr/Sonarr C# source rather than guessed.

qBittorrent's host/port/username/password are read from .env server-side
(QBITTORRENT_URL/USERNAME/PASSWORD) and never taken as tool arguments —
consistent with HOMELABAI-SPEC.md's "secrets never exposed to the model"
rule (§3.5/§9). Root folder paths are not secrets, so those ARE a tool
argument (the model can't know the user's desired library layout otherwise).
"""

from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit

from services.homelab.arr_client import RadarrClient, SonarrClient, ArrAccessError

_radarr_client = RadarrClient()
_sonarr_client = SonarrClient()


def _parse_json(content: str) -> dict:
    raw = (content or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _qbittorrent_env() -> tuple[str, int, str | None, str | None]:
    url = os.getenv("QBITTORRENT_URL") or ""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or 8080
    return host, port, os.getenv("QBITTORRENT_USERNAME"), os.getenv("QBITTORRENT_PASSWORD")


class RadarrAddDownloadClientTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        args = _parse_json(content)
        host, port, username, password = _qbittorrent_env()
        if not host:
            return {
                "error": "QBITTORRENT_URL isn't set in .env, so there's no host/port to connect Radarr to. "
                "Set it up first (see the qbittorrent_queue tool's error for what's needed).",
                "exit_code": 1,
            }
        category = args.get("category") or "radarr"
        use_ssl = bool(args.get("use_ssl", False))
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _radarr_client.add_qbittorrent_download_client(
                    host, port, username, password, category, use_ssl
                ),
            )
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"radarr_add_download_client failed: {type(e).__name__}: {e}", "exit_code": 1}
        return {
            "output": f"Added qBittorrent as a download client in Radarr (id={result['id']}, category={category}).",
            "exit_code": 0,
        }


class SonarrAddDownloadClientTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        args = _parse_json(content)
        host, port, username, password = _qbittorrent_env()
        if not host:
            return {
                "error": "QBITTORRENT_URL isn't set in .env, so there's no host/port to connect Sonarr to. "
                "Set it up first (see the qbittorrent_queue tool's error for what's needed).",
                "exit_code": 1,
            }
        category = args.get("category") or "sonarr"
        use_ssl = bool(args.get("use_ssl", False))
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _sonarr_client.add_qbittorrent_download_client(
                    host, port, username, password, category, use_ssl
                ),
            )
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"sonarr_add_download_client failed: {type(e).__name__}: {e}", "exit_code": 1}
        return {
            "output": f"Added qBittorrent as a download client in Sonarr (id={result['id']}, category={category}).",
            "exit_code": 0,
        }


class RadarrAddRootFolderTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        path = (_parse_json(content).get("path") or "").strip()
        if not path:
            return {"error": "radarr_add_root_folder: 'path' is required (e.g. /movies).", "exit_code": 1}
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, lambda: _radarr_client.add_root_folder(path))
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"radarr_add_root_folder failed: {type(e).__name__}: {e}", "exit_code": 1}
        return {"output": f"Added Radarr root folder: {result['path']} (id={result['id']}).", "exit_code": 0}


class SonarrAddRootFolderTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        path = (_parse_json(content).get("path") or "").strip()
        if not path:
            return {"error": "sonarr_add_root_folder: 'path' is required (e.g. /tv).", "exit_code": 1}
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, lambda: _sonarr_client.add_root_folder(path))
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"sonarr_add_root_folder failed: {type(e).__name__}: {e}", "exit_code": 1}
        return {"output": f"Added Sonarr root folder: {result['path']} (id={result['id']}).", "exit_code": 0}
