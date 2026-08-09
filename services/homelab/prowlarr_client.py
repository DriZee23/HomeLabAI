# services/homelab/prowlarr_client.py
"""Prowlarr client — same Servarr family as Radarr/Sonarr (X-Api-Key auth),
reuses ArrClient's HTTP/auth boilerplate. Prowlarr's API is versioned v1,
not v3 (confirmed: [V1ApiController] on IndexerController), and its
resource route is singular `/api/v1/indexer`, matching the singular-route
convention already confirmed for Radarr/Sonarr's QueueController.

connect_application() wires Prowlarr's indexers to Radarr/Sonarr via
Prowlarr's "Applications" sync (confirmed against
NzbDrone.Core.Applications.Radarr.RadarrSettings/SonarrSettings and
Prowlarr.Api.V1.Applications.ApplicationController/ApplicationResource) —
same schema-driven pattern as ArrClient.add_qbittorrent_download_client:
fetch the live template from .../applications/schema, override only the
fields that connect the two apps (prowlarrUrl/baseUrl/apiKey), and set the
top-level syncLevel. Route is plural "applications" here (confirmed via
[V1ApiController("applications")]), unlike Radarr/Sonarr's v3 "provider"
routes ArrClient._provider_schema targets — kept separate rather than
generalizing further.
"""

from __future__ import annotations

from .arr_client import ArrClient, ArrAccessError


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

    def connect_application(
        self,
        implementation: str,
        target_base_url: str,
        target_api_key: str,
        sync_level: str = "fullSync",
    ) -> dict:
        templates = self._get("/api/v1/applications/schema")
        template = next(
            (t for t in (templates or []) if t.get("implementation") == implementation), None
        )
        if template is None:
            raise ArrAccessError(f"Prowlarr has no '{implementation}' application implementation available.")

        fields = [dict(f) for f in (template.get("fields") or [])]
        self._set_field(fields, "prowlarrUrl", self._base_url)
        self._set_field(fields, "baseUrl", target_base_url)
        self._set_field(fields, "apiKey", target_api_key)

        body = dict(template)
        body["name"] = implementation
        body["syncLevel"] = sync_level
        body["fields"] = fields
        result = self._post("/api/v1/applications", body)
        return {"id": result.get("id"), "name": result.get("name"), "sync_level": result.get("syncLevel")}
