# HomeLabAI v2 — Handoff / Resume Notes

> Working notes for picking this project back up. Not part of the shipped app — read this first, then `HOMELABAI-SPEC.md` for the full spec. `PROJECT.md` is an older draft; **`HOMELABAI-SPEC.md` is the canonical spec**, not `PROJECT.md` (they disagree on whether §13's decisions are resolved — spec is right, they're resolved).

Last updated: 2026-08-09, branch `homelabai`, latest commit `05e9bdd` (plus an uncommitted Media-tab UI slice on top, see below).

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
| SABnzbd | `sabnzbd_queue` | Implemented, **not yet tested live** |
| qBittorrent | `qbittorrent_queue` | Implemented, **not yet tested live** (only integration using cookie-session login, not an API key) |
| UI | "Homelab" sidebar modal, tabs: Dashboard / Server / Docker / Media | Implemented, syntax-checked only (no browser in the dev sandbox) — Dashboard/Server/Docker confirmed rendering live by the user; the new **Media** tab (Jellyfin now-playing/library/continue-watching/recently-added, merged Radarr+Sonarr queue/history, Prowlarr indexers, SABnzbd, qBittorrent, Bazarr missing subtitles) is unverified — needs a pull+rebuild+restart and the media containers actually running with their env vars set |

**Phase 2 (safe write actions)** and **Phase 3 (dangerous actions + confirmation/RBAC/audit)** — not started. **Media/Storage/Logs/Settings UI surfaces** beyond the Homelab modal (per HOMELABAI-SPEC.md §7) — not started.

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

1. Have the user start the Radarr/Sonarr/Jellyfin/Prowlarr/Bazarr/SABnzbd/qBittorrent containers and set their env vars, then live-verify each tool the same way Docker/Unraid were verified — this now also verifies the new Media UI tab (see below). Expect at least one schema surprise per new external API — don't assume the code is right until it's tested against the real service.
2. `unraid_smart_report` — the one deliberately-deferred Unraid tool. Same approach: ask the user to check the GraphQL Sandbox's Disk type fields before writing the query.
3. ~~Extend the Homelab UI's tabs to cover the media stack~~ — done (uncommitted as of this note): added a **Media** tab to the Homelab modal (`static/js/homelab.js` `_renderMedia()`, `static/index.html`, `static/style.css` `.homelab-list-row`/`.homelab-list-primary`/`.homelab-list-secondary`). Cards: Now Playing, Jellyfin Library, Continue Watching, Recently Added, Download Queue (Radarr+Sonarr merged, tagged by service), Recent Activity (Radarr+Sonarr history merged, sorted newest-first), Indexers (Prowlarr), SABnzbd, qBittorrent, Missing Subtitles (Bazarr). Same fetch → template-string → innerHTML pattern as the existing tabs, `node --check`-clean, but **not seen rendering in a real browser** — needs the user's pull+rebuild+restart plus the media containers actually up to verify.
4. Phase 2 (write actions) once the user wants to move past read-only.

## Working conventions established during this build

- Push to `origin/homelabai` after finishing each slice, without being asked — the user pulls this onto Unraid separately.
- Verify external APIs against real source/docs/live Sandbox queries before writing client code — this repo has been burned twice (Unraid, and nearly on Radarr/Sonarr) by trusting incomplete docs.
- Scope big asks into slices and state the scoping decision rather than always asking permission — the user wants forward motion, but flag real ambiguity when it appears (e.g. "which service's env vars are you unsure about" is worth asking; "should this be one modal or three" was fine to just decide).
