# src/agent_tools/jellyfin_tools.py
"""Read-only Jellyfin tools: sessions, recently_added, continue_watching,
search, library_stats. All route through services.homelab.jellyfin_client,
gated by JELLYFIN_URL/JELLYFIN_API_KEY.
"""

import asyncio
import json

from services.homelab.jellyfin_client import JellyfinClient, JellyfinAccessError

_jellyfin_client = JellyfinClient()


class JellyfinSessionsTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            sessions = await loop.run_in_executor(None, _jellyfin_client.sessions)
        except JellyfinAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"jellyfin_sessions failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not sessions:
            return {"output": "No active Jellyfin sessions.", "exit_code": 0}
        lines = []
        for s in sessions:
            playing = f" — playing {s['playing']} ({s['playing_type']})" if s.get("playing") else " — idle"
            lines.append(f"{s['user']} on {s['device']} ({s['client']}){playing}")
        return {"output": "\n".join(lines), "exit_code": 0}


class JellyfinRecentlyAddedTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _jellyfin_client.recently_added)
        except JellyfinAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"jellyfin_recently_added failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "Nothing recently added.", "exit_code": 0}
        lines = [f"{i['name']} ({i['type']}) — added {i['date_added']}" for i in items]
        return {"output": "\n".join(lines), "exit_code": 0}


class JellyfinContinueWatchingTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, _jellyfin_client.continue_watching)
        except JellyfinAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"jellyfin_continue_watching failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": "Nothing in progress.", "exit_code": 0}
        lines = []
        for i in items:
            label = f"{i['series']} — {i['name']}" if i.get("series") else i["name"]
            lines.append(f"{label} ({i['progress_percent']}% watched)")
        return {"output": "\n".join(lines), "exit_code": 0}


class JellyfinSearchTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        raw = (content or "").strip()
        query = raw
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    query = str(parsed.get("query") or "").strip()
            except json.JSONDecodeError:
                pass
        if not query:
            return {"error": "jellyfin_search: provide a search query", "exit_code": 1}

        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, lambda: _jellyfin_client.search(query))
        except JellyfinAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"jellyfin_search failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not items:
            return {"output": f"No Jellyfin library items match '{query}'.", "exit_code": 0}
        lines = [f"{i['name']} ({i['type']}, {i['year']})" for i in items]
        return {"output": "\n".join(lines), "exit_code": 0}


class JellyfinLibraryStatsTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            counts = await loop.run_in_executor(None, _jellyfin_client.library_stats)
        except JellyfinAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"jellyfin_library_stats failed: {type(e).__name__}: {e}", "exit_code": 1}

        lines = [f"{k.replace('_count', '').capitalize()}s: {v}" for k, v in counts.items() if v is not None]
        return {"output": "\n".join(lines) if lines else "No library stats available.", "exit_code": 0}
