# src/agent_tools/media_extras_tools.py
"""Tools for the smaller pieces of the media stack: SABnzbd/qBittorrent
download queues, Bazarr missing subtitles, Prowlarr indexer status (all
read-only), plus Prowlarr's Radarr/Sonarr application sync (write — see
ProwlarrConnectRadarrTool/ProwlarrConnectSonarrTool). Each gated by its own
service's config env vars.
"""

import asyncio
import json
import os

from services.homelab.sabnzbd_client import SabnzbdClient, SabnzbdAccessError
from services.homelab.qbittorrent_client import QbittorrentClient, QbittorrentAccessError
from services.homelab.bazarr_client import BazarrClient, BazarrAccessError
from services.homelab.prowlarr_client import ProwlarrClient
from services.homelab.arr_client import ArrAccessError

_sabnzbd_client = SabnzbdClient()
_qbittorrent_client = QbittorrentClient()
_bazarr_client = BazarrClient()
_prowlarr_client = ProwlarrClient()


def _fmt_bytes(n) -> str:
    if n is None:
        return "unknown"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


class SabnzbdQueueTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            jobs = await loop.run_in_executor(None, _sabnzbd_client.queue)
        except SabnzbdAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"sabnzbd_queue failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not jobs:
            return {"output": "SABnzbd's queue is empty.", "exit_code": 0}
        lines = [
            f"{j['name']} | status={j['status']} | {j['percentage']}% | time_left={j['time_left']} | "
            f"category={j['category']}"
            for j in jobs
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class QbittorrentQueueTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            torrents = await loop.run_in_executor(None, _qbittorrent_client.queue)
        except QbittorrentAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"qbittorrent_queue failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not torrents:
            return {"output": "qBittorrent's queue is empty.", "exit_code": 0}
        lines = [
            f"{t['name']} | state={t['state']} | {t['progress_percent']}% | "
            f"size={_fmt_bytes(t['size'])} | dl_speed={_fmt_bytes(t['dl_speed'])}/s"
            for t in torrents
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class BazarrMissingSubtitlesTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _bazarr_client.missing_subtitles)
        except BazarrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"bazarr_missing_subtitles failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "No missing subtitles.", "exit_code": 0}
        lines = [f"{i['title']} ({i['type']}) — missing: {i['missing_languages']}" for i in items]
        return {"output": "\n".join(lines), "exit_code": 0}


class ProwlarrIndexerStatusTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            indexers = await loop.run_in_executor(None, _prowlarr_client.indexer_status)
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"prowlarr_indexer_status failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not indexers:
            return {"output": "No indexers configured in Prowlarr.", "exit_code": 0}
        lines = [
            f"{i['name']} | enabled={i['enabled']} | protocol={i['protocol']} | priority={i['priority']}"
            for i in indexers
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


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


class ProwlarrConnectRadarrTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        sync_level = (_parse_json(content).get("sync_level") or "fullSync").strip()
        radarr_url = os.getenv("RADARR_URL")
        radarr_api_key = os.getenv("RADARR_API_KEY")
        if not radarr_url or not radarr_api_key:
            return {
                "error": "RADARR_URL/RADARR_API_KEY aren't set in .env, so Prowlarr has nothing to connect to.",
                "exit_code": 1,
            }
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _prowlarr_client.connect_application("Radarr", radarr_url, radarr_api_key, sync_level),
            )
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"prowlarr_connect_radarr failed: {type(e).__name__}: {e}", "exit_code": 1}
        return {
            "output": f"Connected Prowlarr to Radarr (id={result['id']}, sync_level={result['sync_level']}). "
            "Prowlarr's indexers will now sync to Radarr.",
            "exit_code": 0,
        }


class ProwlarrConnectSonarrTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        sync_level = (_parse_json(content).get("sync_level") or "fullSync").strip()
        sonarr_url = os.getenv("SONARR_URL")
        sonarr_api_key = os.getenv("SONARR_API_KEY")
        if not sonarr_url or not sonarr_api_key:
            return {
                "error": "SONARR_URL/SONARR_API_KEY aren't set in .env, so Prowlarr has nothing to connect to.",
                "exit_code": 1,
            }
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _prowlarr_client.connect_application("Sonarr", sonarr_url, sonarr_api_key, sync_level),
            )
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"prowlarr_connect_sonarr failed: {type(e).__name__}: {e}", "exit_code": 1}
        return {
            "output": f"Connected Prowlarr to Sonarr (id={result['id']}, sync_level={result['sync_level']}). "
            "Prowlarr's indexers will now sync to Sonarr.",
            "exit_code": 0,
        }
