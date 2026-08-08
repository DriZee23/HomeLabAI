# src/agent_tools/homelab_tools.py
"""Read-only homelab tools: Docker container visibility + host system metrics.

All Docker calls route through services.homelab.docker_client.DockerHomelabClient,
which is itself gated by src.host_docker_access.host_docker_access_enabled().
When that gate is closed, DockerAccessError carries HOST_DOCKER_ACCESS_HINT
verbatim so the assistant can explain *why* to the user instead of failing
opaquely.
"""

import asyncio
import json

from src.constants import MAX_OUTPUT_CHARS
from services.homelab.docker_client import DockerHomelabClient, DockerAccessError

# One client instance reused across calls (docker.DockerClient is safe to
# reuse; it lazily connects on first real use, so import time stays cheap
# even when host Docker access is disabled).
_docker_client = DockerHomelabClient()


def _extract_json_field(content: str, field: str) -> str:
    """Mirrors the content-parsing convention in web_tools.py: accept either
    a raw string (the field's value directly) or a JSON object."""
    raw = (content or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return str(parsed.get(field) or "").strip()
        except json.JSONDecodeError:
            pass
    return raw.split("\n")[0].strip()


def _extract_tail(content: str, default: int = 100) -> int:
    raw = (content or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                tail = parsed.get("tail")
                if isinstance(tail, int) and tail > 0:
                    return tail
        except json.JSONDecodeError:
            pass
    return default


def _extract_all_flag(content: str, default: bool = True) -> bool:
    raw = (content or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "all" in parsed:
                return bool(parsed.get("all"))
        except json.JSONDecodeError:
            pass
    return default


def _fmt_bytes(n) -> str:
    if n is None:
        return "unknown"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _fmt_duration(seconds) -> str:
    if seconds is None:
        return "unknown"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


class DockerListContainersTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        include_stopped = _extract_all_flag(content, default=True)
        loop = asyncio.get_running_loop()
        try:
            containers = await loop.run_in_executor(
                None, lambda: _docker_client.list_containers(all=include_stopped)
            )
        except DockerAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"docker_list_containers failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not containers:
            return {"output": "No containers found.", "exit_code": 0}
        lines = [
            f"{c['name']} | image={c['image']} | status={c['status']} | "
            f"ports={', '.join(c['ports']) or '-'}"
            for c in containers
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class DockerContainerStatsTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        name = _extract_json_field(content, "name")
        if not name:
            return {"error": "docker_container_stats: provide a container name or id", "exit_code": 1}
        loop = asyncio.get_running_loop()
        try:
            stats = await loop.run_in_executor(None, lambda: _docker_client.container_stats(name))
        except DockerAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"docker_container_stats failed: {type(e).__name__}: {e}", "exit_code": 1}

        cpu = f"{stats['cpu_percent']}%" if stats["cpu_percent"] is not None else "unavailable (insufficient sample data)"
        mem = (
            f"{stats['mem_percent']}% ({_fmt_bytes(stats['mem_usage_bytes'])} / {_fmt_bytes(stats['mem_limit_bytes'])})"
            if stats["mem_percent"] is not None
            else "unavailable"
        )
        if stats.get("mem_note"):
            mem += f" [{stats['mem_note']}]"
        lines = [
            f"Container: {stats['name']}",
            f"CPU: {cpu}",
            f"Memory: {mem}",
            f"Network: rx={_fmt_bytes(stats['net_rx_bytes'])} tx={_fmt_bytes(stats['net_tx_bytes'])}",
            f"Disk I/O: read={_fmt_bytes(stats['block_read_bytes'])} write={_fmt_bytes(stats['block_write_bytes'])}",
        ]
        return {"output": "\n".join(lines), "exit_code": 0}


class DockerContainerLogsTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        name = _extract_json_field(content, "name")
        if not name:
            return {"error": "docker_container_logs: provide a container name or id", "exit_code": 1}
        tail = _extract_tail(content)
        loop = asyncio.get_running_loop()
        try:
            logs = await loop.run_in_executor(None, lambda: _docker_client.container_logs(name, tail=tail))
        except DockerAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"docker_container_logs failed: {type(e).__name__}: {e}", "exit_code": 1}

        output = logs[:MAX_OUTPUT_CHARS] if len(logs) > MAX_OUTPUT_CHARS else logs
        return {"output": output or "(no log output)", "exit_code": 0}


class DockerInspectContainerTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        name = _extract_json_field(content, "name")
        if not name:
            return {"error": "docker_inspect_container: provide a container name or id", "exit_code": 1}
        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, lambda: _docker_client.inspect_container(name))
        except DockerAccessError as e:
            return {"error": str(e), "exit_code": 1}
        except Exception as e:
            return {"error": f"docker_inspect_container failed: {type(e).__name__}: {e}", "exit_code": 1}

        return {"output": json.dumps(info, indent=2), "exit_code": 0}


class SystemMetricsTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.host_metrics import read_host_metrics

        loop = asyncio.get_running_loop()
        try:
            metrics = await loop.run_in_executor(None, read_host_metrics)
        except Exception as e:
            return {"error": f"system_metrics failed: {type(e).__name__}: {e}", "exit_code": 1}

        if not metrics.get("supported"):
            return {"output": metrics.get("reason", "system_metrics not supported on this platform"), "exit_code": 0}

        cpu_line = (
            f"CPU: {metrics['cpu_percent']}% across {metrics['cpu_count']} cores"
            if metrics["cpu_percent"] is not None
            else "CPU: unavailable"
        )
        mem_line = (
            f"Memory: {metrics['mem_percent']}% used "
            f"({_fmt_bytes(metrics['mem_total_bytes'] - metrics['mem_available_bytes'])} / "
            f"{_fmt_bytes(metrics['mem_total_bytes'])})"
            if metrics["mem_percent"] is not None
            else "Memory: unavailable"
        )
        disk_line = (
            f"Disk (Odysseus data dir): {metrics['disk_percent']}% used "
            f"({_fmt_bytes(metrics['disk_used_bytes'])} / {_fmt_bytes(metrics['disk_total_bytes'])})"
            if metrics["disk_percent"] is not None
            else "Disk: unavailable"
        )
        uptime_line = (
            f"Host uptime: {_fmt_duration(metrics['uptime_seconds'])}"
            if metrics["uptime_seconds"] is not None
            else "Uptime: unavailable"
        )
        lines = [
            cpu_line, mem_line, disk_line, uptime_line, "",
            f"Note: {metrics['scope_note']}",
            f"Note: {metrics['disk_scope_note']}",
            f"Note: {metrics['uptime_note']}",
        ]
        return {"output": "\n".join(lines), "exit_code": 0}
