# services/homelab/docker_client.py
"""Docker host client for homelab tools.

Wraps the optional `docker` (docker-py) package. Every public method is
gated by src.host_docker_access.host_docker_access_enabled() — by default
Odysseus does not see the host Docker daemon at all (see
src/host_docker_access.py for why), so this client must never be called
directly by tool code without going through that gate.

Install the optional dependency with: pip install -r requirements-optional.txt
"""

from __future__ import annotations

import re
import time
from typing import Any

from src.host_docker_access import (
    HOST_DOCKER_ACCESS_HINT,
    HOST_DOCKER_SOCKET_PATH,
    host_docker_access_enabled,
)

DOCKER_SDK_MISSING_HINT = (
    "The `docker` Python package is not installed. Install optional "
    "dependencies with `pip install -r requirements-optional.txt`."
)

# Docker CLI's own convention: values are redacted by key name, not value
# shape, so an unusual-looking-but-non-secret value never gets flagged and a
# secret with an unexpected key naming convention is the one gap left open.
_SECRET_KEY_RE = re.compile(r"(SECRET|PASSWORD|TOKEN|KEY|PASS|CREDENTIAL|_PWD)", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

MAX_LOG_TAIL = 1000
DEFAULT_LOG_TAIL = 100


class DockerAccessError(RuntimeError):
    """Host Docker access is disabled, the SDK is missing, or the daemon is unreachable."""


class DockerHomelabClient:
    """Thin, gatekept wrapper around docker.DockerClient.

    Nothing else in the codebase should import the `docker` package
    directly — every access point (tool, route) goes through here so the
    access-policy check and the CPU%/memory math live in exactly one place.
    """

    def __init__(self, socket_path: str = HOST_DOCKER_SOCKET_PATH):
        self._socket_path = socket_path
        self._client = None
        self._docker_module = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not host_docker_access_enabled(self._socket_path):
            raise DockerAccessError(HOST_DOCKER_ACCESS_HINT)
        try:
            import docker  # optional dependency
        except ImportError as exc:
            raise DockerAccessError(DOCKER_SDK_MISSING_HINT) from exc
        try:
            client = docker.DockerClient(base_url=f"unix://{self._socket_path}")
            client.ping()
        except Exception as exc:
            raise DockerAccessError(
                f"Could not connect to the Docker daemon at {self._socket_path}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        self._docker_module = docker
        self._client = client
        return client

    def _get_container(self, name_or_id: str):
        client = self._ensure_client()
        docker_mod = self._docker_module
        try:
            return client.containers.get(name_or_id)
        except docker_mod.errors.NotFound as exc:
            raise DockerAccessError(
                f"No container named or matching id '{name_or_id}' was found."
            ) from exc
        except Exception as exc:
            raise DockerAccessError(
                f"Docker daemon error while looking up '{name_or_id}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def list_containers(self, all: bool = True) -> list[dict[str, Any]]:
        client = self._ensure_client()
        try:
            containers = client.containers.list(all=all)
        except Exception as exc:
            raise DockerAccessError(
                f"Failed to list containers: {type(exc).__name__}: {exc}"
            ) from exc

        result = []
        for c in containers:
            attrs = c.attrs
            result.append({
                "id": c.short_id,
                "name": c.name,
                "image": attrs.get("Config", {}).get("Image", ""),
                "status": c.status,
                "state": attrs.get("State", {}).get("Status", c.status),
                "ports": self._format_ports(attrs),
                "created": attrs.get("Created", ""),
            })
        return result

    @staticmethod
    def _format_ports(attrs: dict) -> list[str]:
        ports = (attrs.get("NetworkSettings") or {}).get("Ports") or {}
        formatted = []
        for container_port, bindings in ports.items():
            if not bindings:
                formatted.append(container_port)
                continue
            for binding in bindings:
                host_ip = binding.get("HostIp") or ""
                host_port = binding.get("HostPort") or ""
                if host_port:
                    formatted.append(f"{host_ip}:{host_port}->{container_port}")
                else:
                    formatted.append(container_port)
        return formatted

    def container_stats(self, name_or_id: str) -> dict[str, Any]:
        container = self._get_container(name_or_id)
        try:
            sample_1 = container.stats(stream=False)
            time.sleep(0.5)
            sample_2 = container.stats(stream=False)
        except Exception as exc:
            raise DockerAccessError(
                f"Failed to read stats for '{name_or_id}': {type(exc).__name__}: {exc}"
            ) from exc

        cpu_percent = self._compute_cpu_percent(sample_1, sample_2)
        mem_usage, mem_limit, mem_percent, mem_note = self._compute_memory(sample_2)
        net_rx, net_tx = self._sum_network(sample_2)
        block_read, block_write = self._sum_blkio(sample_2)

        return {
            "name": container.name,
            "cpu_percent": cpu_percent,
            "mem_usage_bytes": mem_usage,
            "mem_limit_bytes": mem_limit,
            "mem_percent": mem_percent,
            "mem_note": mem_note,
            "net_rx_bytes": net_rx,
            "net_tx_bytes": net_tx,
            "block_read_bytes": block_read,
            "block_write_bytes": block_write,
        }

    @staticmethod
    def _compute_cpu_percent(sample_1: dict, sample_2: dict) -> float | None:
        # Two explicit samples ~0.5s apart, computed ourselves — Docker's own
        # single-call `precpu_stats` is the prior sample the daemon happens to
        # have cached internally, which can be empty/zero right after a
        # container starts. Trusting it there silently produces a fake "0%"
        # instead of "insufficient data". Do not "simplify" this back to a
        # single stats() call.
        try:
            cpu_delta = (
                sample_2["cpu_stats"]["cpu_usage"]["total_usage"]
                - sample_1["cpu_stats"]["cpu_usage"]["total_usage"]
            )
            sys_delta = (
                sample_2["cpu_stats"]["system_cpu_usage"]
                - sample_1["cpu_stats"]["system_cpu_usage"]
            )
        except KeyError:
            return None
        if sys_delta <= 0 or cpu_delta < 0:
            return None
        online_cpus = (
            sample_2["cpu_stats"].get("online_cpus")
            or len(sample_2["cpu_stats"].get("cpu_usage", {}).get("percpu_usage") or [])
            or 1
        )
        return round((cpu_delta / sys_delta) * online_cpus * 100.0, 2)

    @staticmethod
    def _compute_memory(stats: dict) -> tuple[int | None, int | None, float | None, str | None]:
        mem = stats.get("memory_stats") or {}
        usage = mem.get("usage")
        limit = mem.get("limit")
        if usage is None or limit is None:
            return None, None, None, "memory stats unavailable"
        sub = mem.get("stats") or {}
        # cgroup v2 key is inactive_file; cgroup v1 is cache. Reclaimable page
        # cache inflates raw `usage` well beyond what the container is
        # actually using, same as `docker stats` subtracts it before display.
        cache = sub.get("inactive_file", sub.get("cache"))
        if cache is not None:
            adjusted = max(0, usage - cache)
            note = None
        else:
            adjusted = usage
            note = "may include reclaimable page cache (no cache stat available)"
        percent = round((adjusted / limit) * 100.0, 2) if limit else None
        return adjusted, limit, percent, note

    @staticmethod
    def _sum_network(stats: dict) -> tuple[int, int]:
        networks = stats.get("networks") or {}
        rx = sum(v.get("rx_bytes", 0) for v in networks.values())
        tx = sum(v.get("tx_bytes", 0) for v in networks.values())
        return rx, tx

    @staticmethod
    def _sum_blkio(stats: dict) -> tuple[int, int]:
        entries = (stats.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []
        read = sum(e.get("value", 0) for e in entries if str(e.get("op", "")).lower() == "read")
        write = sum(e.get("value", 0) for e in entries if str(e.get("op", "")).lower() == "write")
        return read, write

    def container_logs(self, name_or_id: str, tail: int = DEFAULT_LOG_TAIL) -> str:
        container = self._get_container(name_or_id)
        clamped_tail = max(1, min(int(tail or DEFAULT_LOG_TAIL), MAX_LOG_TAIL))
        try:
            raw = container.logs(tail=clamped_tail, stdout=True, stderr=True, timestamps=False)
        except Exception as exc:
            raise DockerAccessError(
                f"Failed to read logs for '{name_or_id}': {type(exc).__name__}: {exc}"
            ) from exc
        text = raw.decode("utf-8", errors="replace")
        return _ANSI_RE.sub("", text)

    def inspect_container(self, name_or_id: str) -> dict[str, Any]:
        container = self._get_container(name_or_id)
        attrs = container.attrs
        raw_env = (attrs.get("Config") or {}).get("Env") or []
        redacted_env = []
        for entry in raw_env:
            if "=" not in entry:
                redacted_env.append(entry)
                continue
            key, _, value = entry.partition("=")
            if _SECRET_KEY_RE.search(key):
                redacted_env.append(f"{key}=***redacted***")
            else:
                redacted_env.append(f"{key}={value}")

        networks = (attrs.get("NetworkSettings") or {}).get("Networks") or {}
        return {
            "name": container.name,
            "image": (attrs.get("Config") or {}).get("Image", ""),
            "command": (attrs.get("Config") or {}).get("Cmd"),
            "status": (attrs.get("State") or {}).get("Status"),
            "health": ((attrs.get("State") or {}).get("Health") or {}).get("Status"),
            "restart_policy": (attrs.get("HostConfig") or {}).get("RestartPolicy"),
            "mounts": [
                {
                    "source": m.get("Source"),
                    "destination": m.get("Destination"),
                    "mode": m.get("Mode"),
                    "type": m.get("Type"),
                }
                for m in attrs.get("Mounts") or []
            ],
            "network_settings": {
                name: {"ip_address": net.get("IPAddress"), "gateway": net.get("Gateway")}
                for name, net in networks.items()
            },
            "env": redacted_env,
        }
