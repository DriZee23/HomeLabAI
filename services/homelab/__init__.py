# services/homelab/__init__.py
"""Homelab service layer — clients for the host system (Docker, Unraid, ...).

Everything here requires explicit, high-trust opt-in (see
src/host_docker_access.py) since it reaches outside the Odysseus container
into the host it runs on.
"""

from .docker_client import DockerHomelabClient, DockerAccessError

__all__ = [
    "DockerHomelabClient",
    "DockerAccessError",
]
