# src/agent_tools/unraid_tools.py
"""Read-only Unraid array tools: array_status, disk_health.

Both route through services.homelab.unraid_client.UnraidClient, which is
gated by UNRAID_API_URL/UNRAID_API_KEY being set. When they aren't,
UnraidAccessError carries UNRAID_ACCESS_HINT verbatim so the assistant can
explain what's missing instead of failing opaquely.

Shares, cache-pool usage, and full SMART reports are intentionally not
covered — see services/homelab/unraid_client.py for why.
"""

import asyncio

from services.homelab.unraid_client import UnraidClient, UnraidAccessError

# Reused across calls, same rationale as the Docker client singleton in
# homelab_tools.py — lazy, cheap to hold, no per-call connection setup.
_unraid_client = UnraidClient()


def _fmt_bytes(n) -> str:
    if n is None:
        return "unknown"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


class UnraidArrayStatusTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            status = await loop.run_in_executor(None, _unraid_client.array_status)
        except UnraidAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"unraid_array_status failed: {type(e).__name__}: {e}", "exit_code": 1}

        lines = [
            f"Array state: {status['state']}",
            f"Disks in array: {status['disk_count']}",
            f"Capacity: {_fmt_bytes(status['capacity_used_bytes'])} used / "
            f"{_fmt_bytes(status['capacity_total_bytes'])} total "
            f"({_fmt_bytes(status['capacity_free_bytes'])} free)",
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class UnraidDiskHealthTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        loop = asyncio.get_running_loop()
        try:
            disks = await loop.run_in_executor(None, _unraid_client.disk_health)
        except UnraidAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"unraid_disk_health failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not disks:
            return {"output": "No disks reported by the array.", "exit_code": 0}
        lines = []
        for d in disks:
            temp = f"{d['temp_celsius']}°C" if d["temp_celsius"] is not None else "unknown"
            lines.append(
                f"{d['name']} ({d['role']}): status={d['status']}, size={_fmt_bytes(d['size_bytes'])}, temp={temp}"
            )
        return {"output": "\n".join(lines), "exit_code": 0}
