# services/homelab/prowlarr_client.py
"""Prowlarr client — same Servarr family as Radarr/Sonarr (X-Api-Key auth),
reuses ArrClient's HTTP/auth boilerplate. Prowlarr's API is versioned v1,
not v3 (confirmed: [V1ApiController] on IndexerController), and its
resource route is singular `/api/v1/indexer`, matching the singular-route
convention already confirmed for Radarr/Sonarr's QueueController.
"""

from __future__ import annotations

from .arr_client import ArrClient


class ProwlarrClient(ArrClient):
    def __init__(self):
        super().__init__("PROWLARR_URL", "PROWLARR_API_KEY", "Prowlarr")

    def indexer_status(self) -> list[dict]:
        indexers = self._get("/api/v1/indexer") or []
        return [
            {
                "name": i.get("name"),
                "enabled": i.get("enable"),
                "protocol": i.get("protocol"),
                "priority": i.get("priority"),
            }
            for i in indexers
        ]
