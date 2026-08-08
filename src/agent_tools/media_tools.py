# src/agent_tools/media_tools.py
"""Read-only media-queue tools: radarr_queue/history, sonarr_queue/history.

Both route through services.homelab.arr_client, gated by RADARR_URL/
RADARR_API_KEY and SONARR_URL/SONARR_API_KEY respectively. When unset,
ArrAccessError carries an actionable message so the assistant can explain
what's missing instead of failing opaquely.
"""

import asyncio

from services.homelab.arr_client import RadarrClient, SonarrClient, ArrAccessError

_radarr_client = RadarrClient()
_sonarr_client = SonarrClient()


def _fmt_bytes(n) -> str:
    if n is None:
        return "unknown"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


class RadarrQueueTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _radarr_client.queue)
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"radarr_queue failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "Radarr's download queue is empty.", "exit_code": 0}
        lines = [
            f"{i['title']} | status={i['status']} | size={_fmt_bytes(i['size_bytes'])} | "
            f"client={i['download_client']}" + (f" | error={i['error_message']}" if i.get("error_message") else "")
            for i in items
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class RadarrHistoryTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _radarr_client.history)
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"radarr_history failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "Radarr has no history yet.", "exit_code": 0}
        lines = [f"{i['title']} | {i['event_type']} | {i['date']}" for i in items]
        return {"output": "\n".join(lines), "exit_code": 0}


class SonarrQueueTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _sonarr_client.queue)
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"sonarr_queue failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "Sonarr's download queue is empty.", "exit_code": 0}
        lines = [
            f"{i['title']} | status={i['status']} | size={_fmt_bytes(i['size_bytes'])} | "
            f"client={i['download_client']}" + (f" | error={i['error_message']}" if i.get("error_message") else "")
            for i in items
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class SonarrHistoryTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _sonarr_client.history)
        except ArrAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"sonarr_history failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "Sonarr has no history yet.", "exit_code": 0}
        lines = [f"{i['title']} | {i['event_type']} | {i['date']}" for i in items]
        return {"output": "\n".join(lines), "exit_code": 0}
