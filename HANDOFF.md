# HomeLabAI v2 — Handoff / Resume Notes

> Working notes for picking this project back up. Not part of the shipped app — read this first, then `HOMELABAI-SPEC.md` for the full spec. `PROJECT.md` is an older draft; **`HOMELABAI-SPEC.md` is the canonical spec**, not `PROJECT.md` (they disagree on whether §13's decisions are resolved — spec is right, they're resolved).

Last updated: 2026-08-09 (evening), branch `homelabai`, latest commit `ec33968`, **pushed**. User is turning their PC off for the night — read "Resume here next" immediately below before anything else.

## Resume here next: qBittorrent VPN container is hung, root cause found but not fixed

The user replaced the working `binhex-qbittorrent` container with `binhex-qbittorrentvpn` (ProtonVPN via WireGuard) mid-session, wanting VPN-routed torrenting. **It never finishes starting** — the WebUI times out, and `qbittorrent-nox` never even launches (confirmed via `ps aux` inside the container: only `start.sh`/`watchdog.sh` are running, no qbittorrent process).

**Root cause, fully traced and confirmed** (not a guess): the container's startup chain is `start.sh` → sources `wireguard.sh` → sources `iptable.sh` → calls `watchdog()` → `watchdog.sh` (loops every 30s) → sources `preruncheck.sh` → calls `check_vpn_incoming_port()` in `/usr/local/bin/tools.sh` (line 560), which is:
```bash
while [ ! -f "/tmp/getvpnport" ]
do
    sleep 1s
done
```
This loop has **no timeout** and blocks forever. `/tmp/getvpnport` only gets written by the port-forward-assignment step, which the container's own log already showed being skipped:
```
[info] ProtonVPN username 'mazhar.t53@proton.me' does not contain the suffix '+pmp' and therefore is not enabled for port forwarding, skipping port forward assignment...
```
ProtonVPN's NAT-PMP/port-forwarding requires (a) a plan tier that supports it (Plus/Unlimited, not Free/Basic — **unconfirmed which tier this user has**), and (b) is normally requested via a `+pmp`-suffixed OpenVPN/IKEv2 username. **Unresolved question going into next session**: this container is configured for **WireGuard**, not OpenVPN — WireGuard auth is keypair-based, no username field, so it's unclear whether the `+pmp` trick even applies the same way here, or whether port-forwarding for WireGuard needs to be requested differently (e.g. regenerating the WireGuard config from ProtonVPN's dashboard with a "NAT-PMP (Port Forwarding)" checkbox, if one exists there). Was about to `grep -rn "Script started to assign incoming port"` across `/usr/local/bin/` and `/root/` inside the container to find the exact script that logs that line and see what it actually checks (probably a counterpart script, `prerunget.sh`, referenced in `preruncheck.sh`'s own header comment: *"read in values written by script /root/prerunget.sh"*) — that command was sent but the session ended before the user could run it and paste output. **Start there.**

User explicitly chose "enable ProtonVPN port forwarding" over "revert to the already-working non-VPN container" when asked, so don't silently revert — but if the +pmp/WireGuard investigation dead-ends, the fallback (their other stated-acceptable option) is: remove `binhex-qbittorrentvpn`, go back to plain `binhex-qbittorrent` (the one already fully fixed and verified working this session — see below), and drop VPN-routing as a goal, or pursue it later with more research into whether this specific image/ProtonVPN-WireGuard combination supports port forwarding at all.

**Practical side effect while this is unresolved**: HomeLabAI's own `.env` still has `QBITTORRENT_URL=http://192.168.178.49:8082` pointing at whichever container currently holds that port mapping — if `binhex-qbittorrentvpn` is squatting on it while hung, the `qbittorrent_queue` tool (and the new `radarr_add_download_client`/`sonarr_add_download_client` tools from this session, which read this same URL from `.env`) will likely time out too, not because of any HomeLabAI bug but because nothing is actually listening behind that port right now. Don't debug HomeLabAI-side qBittorrent tool failures without first checking `docker ps` for which qBittorrent container is actually up and healthy.

## Where things stand

**Phase 0 (fork & baseline)** — done. Odysseus runs on the user's Unraid box, local model backend (Ollama, `gpt-oss:20b`) working.

**Phase 1 (read-only homelab)** — tool catalog is done and mostly live-verified on the user's actual server:

| Domain | Tools | Status |
|---|---|---|
| Docker | `docker_list_containers`, `docker_container_stats/logs/inspect_container` | **Verified live** — real native tool calls confirmed via container logs |
| System metrics | `system_metrics` | Implemented, not separately re-verified after the compact-prompt fix, but shares the same code path as Docker |
| Unraid array | `unraid_array_status`, `unraid_disk_health`, `unraid_shares` | **Verified live** — went through several rounds of schema corrections (see "Unraid API gotchas" below), user confirmed clean output |
| Unraid SMART | *(not built)* | Deferred — needs a live schema check (SMART attribute fields), same discipline as everything else. Do NOT guess field names. |
| Radarr/Sonarr | `radarr_queue/history`, `sonarr_queue/history` | Implemented (verified against real Radarr/Sonarr C# source), **not yet tested live** — those containers were `Exited` last checked |
| Jellyfin | `jellyfin_sessions/recently_added/continue_watching/search/library_stats` | Implemented, **not yet tested live** |
| Prowlarr | `prowlarr_indexer_status` | Implemented, **not yet tested live** |
| Bazarr | `bazarr_missing_subtitles` | Implemented, **not yet tested live** |
| SABnzbd | `sabnzbd_queue` | Implemented, **not yet tested live** — WebUI reachability fixed (see below), but the Usenet host/server itself still needs configuring in SABnzbd before the queue tool is meaningfully testable |
| qBittorrent | `qbittorrent_queue` | **Was verified live (commit `091223e`)** against `binhex-qbittorrent` (non-VPN) — see "qBittorrent live-verification saga" in project memory. User then swapped to `binhex-qbittorrentvpn` mid-session, which is currently **hung and not serving anything** — see "Resume here next" at the top of this file before touching qBittorrent again. |
| UI | "Homelab" sidebar modal, tabs: Dashboard / Server / Docker / Media | Implemented, syntax-checked only (no browser in the dev sandbox) — Dashboard/Server/Docker confirmed rendering live by the user; the **Media** tab (commit `a9b028b`, pushed) is unverified — needs the media containers actually running with their env vars set |

**Phase 2 (safe write actions)** and **Phase 3 (dangerous actions + confirmation/RBAC/audit)** — not started. **Media/Storage/Logs/Settings UI surfaces** beyond the Homelab modal (per HOMELABAI-SPEC.md §7) — not started.

## Off-spec: arr-stack setup tools (not in HOMELABAI-SPEC.md — built at the user's direct request, 2026-08-09, commit `ec33968`, pushed)

The user asked for the AI to perform the *initial wiring* of the *arr stack (connect qBittorrent as a download client, sync Prowlarr's indexers, add root folders) rather than day-to-day actions. **This is not in HOMELABAI-SPEC.md's tool catalog (§5) or Phase 2 at all** — Phase 2 there is scoped to day-to-day write actions on an already-wired stack (`add_movie`, `retry_download`, `pause`/`resume`, etc.). Flagged this distinction to the user directly before building; they chose to proceed with the off-spec setup tools first.

**New tools** (pushed but **not live-tested at all yet** — the qBittorrent VPN detour above happened before this could be tried live; test this next once qBittorrent itself is sorted):
- `radarr_add_download_client` / `sonarr_add_download_client` — connect qBittorrent as the download client. Take **no host/port/credential arguments**; those are read server-side from `QBITTORRENT_URL`/`USERNAME`/`PASSWORD` in `.env` and never passed through the model, per HOMELABAI-SPEC.md's "secrets never exposed to the model" rule (§3.5/§9). Only `category`/`use_ssl` are model-controlled.
- `radarr_add_root_folder` / `sonarr_add_root_folder` — take a `path` argument (not a secret, has to come from the user).
- `prowlarr_connect_radarr` / `prowlarr_connect_sonarr` — sync Prowlarr's indexers via its "Applications" feature. Same pattern: `RADARR_URL`/`API_KEY` (or Sonarr's) read server-side, only `sync_level` is model-controlled.

**Implementation approach**: schema-driven, not hardcoded POST bodies. Confirmed live via `curl`/`gh api` against the real Radarr, Sonarr, and Prowlarr C# source (`ProviderControllerBase.cs`'s `GET .../schema` route, `SchemaBuilder.cs`'s camelCase field-naming convention, `QBittorrentSettings.cs` for both apps, `RadarrSettings.cs`/`SonarrSettings.cs` in Prowlarr's Applications module) — each write method fetches the live default-template schema for the target implementation (`QBittorrent`, `Radarr`, `Sonarr`) from the real server, then only overrides the specific field values needed by name, rather than guessing the full field list/order/types. This should be far more version-resilient than a hardcoded body, but **has not been live-tested** (no network access to the user's Unraid box from this dev sandbox) — treat as implemented-but-unverified, same as every other integration before its first live test. Expect at least one surprise (e.g. a field name or enum string that doesn't match) — don't assume it's right until the user actually runs it.

New file: `src/agent_tools/arr_setup_tools.py`. Extended: `services/homelab/arr_client.py` (`ArrClient.add_qbittorrent_download_client`/`add_root_folder`/`_provider_schema`/`_post`/`_set_field`, `SonarrClient`'s `_qbt_category_field`/`_qbt_default_category` override), `services/homelab/prowlarr_client.py` (`connect_application`), `src/agent_tools/media_extras_tools.py` (`ProwlarrConnectRadarrTool`/`ProwlarrConnectSonarrTool`). Registered across all 6 tool touchpoints (see [[feedback-tool-registration-touchpoints]]) — `tool_security.py`'s `PLAN_MODE_READONLY_TOOLS` deliberately **excludes** these (they're write tools, should stay blocked in plan mode).

## If the user reports something's not working, check these first (in order)

Three separate classes of bugs bit us repeatedly during this build — check the cheap ones before writing new code:

1. **Did they actually redeploy?** `static/` and all Python source are baked into the Docker image at build time (`COPY . .`), not bind-mounted. `docker compose up -d` alone does NOT pick up new code — needs:
   ```bash
   git pull origin homelabai
   docker compose build --build-arg INSTALL_OPTIONAL=true odysseus
   docker compose up -d
   ```
2. **Is the env var actually reaching the container?** `.env` is NOT auto-injected — only vars explicitly listed under `docker-compose.yml`'s `environment:` block reach the container (this bit every single new integration the first time). If a new integration is added, its env vars must be added there too, not just documented in `.env.example`.
3. **Is the model actually calling the tool, or narrating/hallucinating?** Check `docker compose logs --tail 100 odysseus` for `[agent-debug] round=1 ... tools_sent=N`. If `tools_sent=0`, native schemas aren't being sent (check `ModelEndpoint.supports_tools` for that endpoint — this user's Ollama endpoint id is `76f0a020`, already set to `True`). If the model still emits a `tool_call` for something that doesn't exist, that's the model hallucinating, not a registration bug.

See the Claude memory files under `feedback_tool_registration_touchpoints.md`, `feedback_env_vars_need_compose_entry.md`, and `project_compact_prompt_bugfix.md` for the full stories — worth reading before assuming a new bug is novel.

## Unraid API gotchas (already paid for — don't re-discover these)

Unraid's own docs are too thin to trust; everything here was confirmed live via the user's GraphQL Sandbox:

- Disks are split into **three** separate array fields: `disks` (data), `parities`, `caches` — not one unified list. A cache-only array (this user's setup) legitimately has `disks: []`.
- All numeric fields come back as **GraphQL strings** (`"3907018532"`), not native JSON numbers — coerce with `int()`, don't `isinstance(x, int)` check.
- `disks[].size` and `shares[].free/used` are in **KiB**, not bytes.
- `array.capacity.disks{free,used,total}` is a **disk SLOT COUNT** (e.g. "30 free slots"), not a byte quantity — easy to confuse with the sibling `array.capacity.kilobytes{...}`, which IS the real (data+parity only, excludes cache pools) byte capacity.
- `shares` is a **top-level** query (sibling to `array`, not nested under it). `free`/`used` reflect the underlying storage **pool**, not per-share usage — every share on the same pool reports identical numbers.

This user's Unraid endpoint id in their DB: docker group GID `281` (real value, not the `963` doc default), docker GID for the sandbox test environment was `950` — don't confuse the two, only `281` is real.

## Tool registration checklist (6 touchpoints, not 4)

Every new tool needs ALL of these or it silently doesn't work for some models:

1. `src/agent_tools/<domain>_tools.py` — the tool class(es)
2. `src/agent_tools/__init__.py` — import + `TOOL_HANDLERS` + `TOOL_TAGS`
3. `src/tool_schemas.py` — `FUNCTION_TOOL_SCHEMAS` entry (+ `_REQUIRED_NATIVE_TOOL_ARGS` if it takes required args)
4. `src/tool_security.py` — `PLAN_MODE_READONLY_TOOLS` (if read-only)
5. `src/agent_loop.py` — `TOOL_SECTIONS` entry (fenced-block prompt text — **easy to forget, breaks local/Ollama models specifically**)
6. `src/tool_index.py` — `BUILTIN_TOOL_DESCRIPTIONS` entry + optionally `_KEYWORD_HINTS`

Plus, for any new external service integration specifically: add its env vars to `docker-compose.yml`'s `environment:` block (not just `.env.example`).

## Suggested next steps, roughly in order of value

1. **Resolve the qBittorrentVPN hang** (see "Resume here next" at the top) — either get ProtonVPN port-forwarding actually working for this WireGuard setup, or revert to the plain `binhex-qbittorrent` container that was already fully verified working. Until this is resolved, `QBITTORRENT_URL` in `.env` may be pointing at a dead container.
2. Once qBittorrent is sorted, **live-test the new arr-setup tools** (`radarr_add_download_client`, `sonarr_add_download_client`, `radarr_add_root_folder`, `sonarr_add_root_folder`, `prowlarr_connect_radarr`, `prowlarr_connect_sonarr`) — completely untested against real Radarr/Sonarr/Prowlarr instances. Expect at least one field-name or enum-string surprise despite the schema-driven approach; don't assume it's right until it's actually run.
3. Continue live-verifying the rest of Phase 1's read tools (Radarr/Sonarr/Jellyfin/Prowlarr/Bazarr/SABnzbd) the same way Docker/Unraid/qBittorrent were verified — this now also verifies the Media UI tab. SABnzbd's WebUI is reachable now but its Usenet host/server still isn't configured.
4. `unraid_smart_report` — the one deliberately-deferred Unraid tool. Same approach: ask the user to check the GraphQL Sandbox's Disk type fields before writing the query.
5. The actual spec'd Phase 2 (day-to-day write actions: restart/start/stop containers, add_movie/add_show, retry_download, pause/resume, request_media, search_subtitles) — deferred in favor of the off-spec arr-setup tools per the user's explicit choice this session; still not started.

## Working conventions established during this build

- Push to `origin/homelabai` after finishing each slice, without being asked — the user pulls this onto Unraid separately.
- Verify external APIs against real source/docs/live Sandbox queries before writing client code — this repo has been burned twice (Unraid, and nearly on Radarr/Sonarr) by trusting incomplete docs.
- Scope big asks into slices and state the scoping decision rather than always asking permission — the user wants forward motion, but flag real ambiguity when it appears (e.g. "which service's env vars are you unsure about" is worth asking; "should this be one modal or three" was fine to just decide).
