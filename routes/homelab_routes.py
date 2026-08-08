# routes/homelab_routes.py
"""Homelab routes — /api/homelab/*. Read-only Docker/system-metrics/Unraid/
media-queue data, mirroring the docker_*/system_metrics/unraid_*/radarr_*/
sonarr_* chat tools (src/agent_tools/homelab_tools.py, unraid_tools.py,
media_tools.py) for direct REST/curl access and future dashboard-UI use.

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
from services.homelab.arr_client import RadarrClient, SonarrClient, ArrAccessError
from services.homelab.prowlarr_client import ProwlarrClient
from services.homelab.jellyfin_client import JellyfinClient, JellyfinAccessError
from services.homelab.sabnzbd_client import SabnzbdClient, SabnzbdAccessError
from services.homelab.qbittorrent_client import QbittorrentClient, QbittorrentAccessError
from services.homelab.bazarr_client import BazarrClient, BazarrAccessError

logger = logging.getLogger(__name__)

# Reused across requests — see src/agent_tools/homelab_tools.py for the same
# reuse rationale (docker.DockerClient is safe to share, lazily connects).
_docker_client = DockerHomelabClient()
_unraid_client = UnraidClient()
_radarr_client = RadarrClient()
_sonarr_client = SonarrClient()
_prowlarr_client = ProwlarrClient()
_jellyfin_client = JellyfinClient()
_sabnzbd_client = SabnzbdClient()
_qbittorrent_client = QbittorrentClient()
_bazarr_client = BazarrClient()


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

    @router.get("/radarr/queue")
    async def radarr_queue(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"queue": _radarr_client.queue()}
        except ArrAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/radarr/history")
    async def radarr_history(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"history": _radarr_client.history()}
        except ArrAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/sonarr/queue")
    async def sonarr_queue(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"queue": _sonarr_client.queue()}
        except ArrAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/sonarr/history")
    async def sonarr_history(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"history": _sonarr_client.history()}
        except ArrAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/prowlarr/indexers")
    async def prowlarr_indexers(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"indexers": _prowlarr_client.indexer_status()}
        except ArrAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/jellyfin/sessions")
    async def jellyfin_sessions(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"sessions": _jellyfin_client.sessions()}
        except JellyfinAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/jellyfin/recently-added")
    async def jellyfin_recently_added(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"items": _jellyfin_client.recently_added()}
        except JellyfinAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/jellyfin/continue-watching")
    async def jellyfin_continue_watching(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"items": _jellyfin_client.continue_watching()}
        except JellyfinAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/jellyfin/search")
    async def jellyfin_search(request: Request, query: str) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"items": _jellyfin_client.search(query)}
        except JellyfinAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/jellyfin/stats")
    async def jellyfin_library_stats(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return _jellyfin_client.library_stats()
        except JellyfinAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/sabnzbd/queue")
    async def sabnzbd_queue(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"queue": _sabnzbd_client.queue()}
        except SabnzbdAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/qbittorrent/queue")
    async def qbittorrent_queue(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"queue": _qbittorrent_client.queue()}
        except QbittorrentAccessError as e:
            raise HTTPException(503, str(e))

    @router.get("/bazarr/missing-subtitles")
    async def bazarr_missing_subtitles(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            return {"missing": _bazarr_client.missing_subtitles()}
        except BazarrAccessError as e:
            raise HTTPException(503, str(e))

    return router
