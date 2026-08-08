# routes/homelab_routes.py
"""Homelab routes — /api/homelab/*. Read-only Docker + system metrics data,
mirroring the docker_*/system_metrics chat tools (src/agent_tools/homelab_tools.py)
for direct REST/curl access and future dashboard-UI consumption.

Gated by require_admin like routes/diagnostics_routes.py, since container
inspect/stats output is comparable infra-sensitive data and no UI consumes
this yet.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from core.middleware import require_admin
from services.homelab.docker_client import DockerHomelabClient, DockerAccessError
from services.homelab.unraid_client import UnraidClient, UnraidAccessError

logger = logging.getLogger(__name__)

# Reused across requests — see src/agent_tools/homelab_tools.py for the same
# reuse rationale (docker.DockerClient is safe to share, lazily connects).
_docker_client = DockerHomelabClient()
_unraid_client = UnraidClient()


def setup_homelab_routes() -> APIRouter:
    router = APIRouter(prefix="/api/homelab", tags=["homelab"])

    @router.get("/containers")
    async def list_containers(request: Request, all: bool = True) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"containers": _docker_client.list_containers(all=all)}
        except DockerAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/containers/{name}/stats")
    async def container_stats(name: str, request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return _docker_client.container_stats(name)
        except DockerAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/containers/{name}/logs")
    async def container_logs(name: str, request: Request, tail: int = 100) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"logs": _docker_client.container_logs(name, tail=tail)}
        except DockerAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/containers/{name}/inspect")
    async def inspect_container(name: str, request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return _docker_client.inspect_container(name)
        except DockerAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/system")
    async def system_metrics(request: Request) -> Dict[str, Any]:
        require_admin(request)
        from src.host_metrics import read_host_metrics
        return read_host_metrics()

    @router.get("/unraid/array")
    async def unraid_array_status(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return _unraid_client.array_status()
        except UnraidAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/unraid/disks")
    async def unraid_disk_health(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"disks": _unraid_client.disk_health()}
        except UnraidAccessError as e:
            raise HTTPException(503, str(e))

    return router
