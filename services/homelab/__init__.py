# services/homelab/__init__.py
"""Homelab service layer — clients for the host system (Docker, Unraid, ...).

Everything here requires explicit, high-trust opt-in (see
src/host_docker_access.py) since it reaches outside the Odysseus container
into the host it runs on.
"""

from .docker_client import DockerHomelabClient, DockerAccessError
from .unraid_client import UnraidClient, UnraidAccessError
from .arr_client import RadarrClient, SonarrClient, ArrAccessError
from .prowlarr_client import ProwlarrClient
from .jellyfin_client import JellyfinClient, JellyfinAccessError
from .sabnzbd_client import SabnzbdClient, SabnzbdAccessError
from .qbittorrent_client import QbittorrentClient, QbittorrentAccessError
from .bazarr_client import BazarrClient, BazarrAccessError

__all__ = [
    "DockerHomelabClient",
    "DockerAccessError",
    "UnraidClient",
    "UnraidAccessError",
    "RadarrClient",
    "SonarrClient",
    "ArrAccessError",
    "ProwlarrClient",
    "JellyfinClient",
    "JellyfinAccessError",
    "SabnzbdClient",
    "SabnzbdAccessError",
    "QbittorrentClient",
    "QbittorrentAccessError",
    "BazarrClient",
    "BazarrAccessError",
]
