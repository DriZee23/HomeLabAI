# services/homelab/__init__.py
"""Homelab service layer — clients for the host system (Docker, Unraid, ...).

Everything here requires explicit, high-trust opt-in (see
src/host_docker_access.py) since it reaches outside the Odysseus container
into the host it runs on.
"""

from .docker_client import DockerHomelabClient, DockerAccessError
from .unraid_client import UnraidClient, UnraidAccessError
from .arr_client import RadarrClient, SonarrClient, ArrAccessError

__all__ = [
    "DockerHomelabClient",
    "DockerAccessError",
    "UnraidClient",
    "UnraidAccessError",
    "RadarrClient",
    "SonarrClient",
    "ArrAccessError",
]
