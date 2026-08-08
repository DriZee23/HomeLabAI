# src/host_metrics.py
"""Read-only host system metrics (CPU/RAM/disk/uptime) via stdlib /proc parsing.

Deliberately does NOT use psutil — core/platform_compat.py documents a
"stdlib + ctypes only, no psutil" rule for this codebase, so this mirrors
that constraint rather than reintroducing the dependency it avoids.

Linux-only: /proc doesn't exist on macOS/Windows. Temperatures, SMART data,
and UPS status are intentionally NOT covered here — none of those are
readable via /proc and all need real Unraid-API or lm-sensors/smartctl
access, which is a later, separate integration.
"""

from __future__ import annotations

import shutil
import sys
import time
from typing import Any

from src.constants import DATA_DIR

IS_LINUX = sys.platform.startswith("linux")

_SCOPE_NOTE = (
    "Read from the container's /proc; usually reflects true host-wide "
    "CPU/RAM since this container has no cgroup CPU/memory limits set, but "
    "that depends on the host's kernel/cgroup setup and has not been "
    "independently verified against `free`/`nproc` run directly on the "
    "host — treat as approximate, not authoritative."
)
_DISK_SCOPE_NOTE = (
    "Covers only the disk/partition backing Odysseus's own data directory, "
    "not the full host storage (e.g. an Unraid array) — that needs a "
    "separate Unraid API integration."
)
_UPTIME_NOTE = (
    "This is the host's boot-relative uptime (not namespaced per-container "
    "in a standard Docker setup), not how long the Odysseus container has "
    "been running."
)


def read_host_metrics(data_dir: str = DATA_DIR) -> dict[str, Any]:
    if not IS_LINUX:
        return {
            "supported": False,
            "reason": "system_metrics is Linux-only (reads /proc); not available on this platform",
        }

    try:
        cpu_percent, cpu_count = _cpu_percent()
    except OSError:
        cpu_percent, cpu_count = None, None

    try:
        mem_total, mem_used = _mem_info()
        mem_available = mem_total - mem_used
        mem_percent = round((mem_used / mem_total) * 100.0, 2) if mem_total else None
    except OSError:
        mem_total, mem_available, mem_percent = None, None, None

    try:
        disk_total, disk_used = _disk_info(data_dir)
        disk_percent = round((disk_used / disk_total) * 100.0, 2) if disk_total else None
    except OSError:
        disk_total, disk_used, disk_percent = None, None, None

    try:
        uptime_seconds = _uptime_seconds()
    except OSError:
        uptime_seconds = None

    return {
        "supported": True,
        "cpu_percent": cpu_percent,
        "cpu_count": cpu_count,
        "mem_total_bytes": mem_total,
        "mem_available_bytes": mem_available,
        "mem_percent": mem_percent,
        "disk_total_bytes": disk_total,
        "disk_used_bytes": disk_used,
        "disk_percent": disk_percent,
        "uptime_seconds": uptime_seconds,
        "scope_note": _SCOPE_NOTE,
        "disk_scope_note": _DISK_SCOPE_NOTE,
        "uptime_note": _UPTIME_NOTE,
    }


def _read_proc_stat_cpu_line() -> list[int]:
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("cpu "):
                return [int(x) for x in line.split()[1:]]
    raise OSError("no aggregate 'cpu ' line found in /proc/stat")


def _cpu_percent(sample_interval: float = 0.2) -> tuple[float, int]:
    fields_1 = _read_proc_stat_cpu_line()
    time.sleep(sample_interval)
    fields_2 = _read_proc_stat_cpu_line()

    total_1, total_2 = sum(fields_1), sum(fields_2)
    idle_1, idle_2 = fields_1[3], fields_2[3]  # index 3 = idle, per /proc/stat's fixed field order

    total_delta = total_2 - total_1
    idle_delta = idle_2 - idle_1
    if total_delta <= 0:
        raise OSError("no time elapsed between /proc/stat samples")

    cpu_percent = round((1 - idle_delta / total_delta) * 100.0, 2)

    try:
        import os as _os
        cpu_count = _os.cpu_count() or 1
    except Exception:
        cpu_count = 1

    return cpu_percent, cpu_count


def _mem_info() -> tuple[int, int]:
    values = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                values[key] = int(rest.strip().split()[0]) * 1024  # kB -> bytes
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise OSError("MemTotal/MemAvailable not found in /proc/meminfo")
    return values["MemTotal"], values["MemTotal"] - values["MemAvailable"]


def _disk_info(path: str) -> tuple[int, int]:
    usage = shutil.disk_usage(path)
    return usage.total, usage.used


def _uptime_seconds() -> float:
    with open("/proc/uptime", "r", encoding="utf-8") as handle:
        return float(handle.read().split()[0])
