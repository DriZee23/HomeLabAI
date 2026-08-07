# HomeLabAI v2 — AI-First Homelab Operating System

> **Spec version:** 2.1 (decisions in §13 resolved 2026-08-07)
> **Build partner:** Claude Code (agent builds, Mazhar reviews)
> **Base project:** fork of [Odysseus](https://github.com/odysseus-dev/odysseus) (AGPL-3.0-or-later) — this fork lives at [DriZee23/HomeLabAI](https://github.com/DriZee23/HomeLabAI). Note: the upstream project moved from `pewdiepie-archdaemon/odysseus` to the `odysseus-dev` org at some point before this fork was made; `odysseus-dev/odysseus` is the current canonical repo.
> **Separate from:** the existing HomelabAI v1 project (`DriZee23/Homeserver-Jarvis`), which stays running unchanged. This is a new, parallel project, not a replacement.

---

## 1. Vision

HomeLabAI is an **AI-first operating system for a homelab**. The benchmark is not Homepage or any dashboard aggregator — it is an AI-powered OS that *happens* to control a homelab.

Instead of navigating dozens of web UIs, the user talks to one assistant that understands the whole server:

> "Download Interstellar" · "Restart Jellyfin" · "Why is my CPU high?" · "Why didn't this movie download?" · "Update every container except Jellyfin" · "What's using my cache drive?" · "Recommend a movie for my parents"

The assistant continuously monitors the server, explains problems, recommends fixes, automates repetitive work, and safely executes approved actions. It **never invents server state** — every fact comes from a real API or tool call. Every dangerous action is explained first and confirmed before execution.

The AI is the heart of the product. Every other surface (dashboards, cards, logs) exists to support and visualise what the AI already understands.

---

## 2. Relationship to Odysseus

Odysseus is a self-hosted AI *workspace* (chat + agents + research + documents + local models). It already ships the exact runtime HomeLabAI needs:

| HomeLabAI needs | Odysseus already provides |
|---|---|
| Chat-first "Jarvis" UX | Chat + agent UI, themes, streaming responses |
| Agent that plans over tools | Agent loop built on opencode, tool schemas, planning |
| Modular tool system | `TOOL_HANDLERS` registry of Python tool classes |
| Pluggable integrations | Runtime **MCP manager** + shipped MCP servers |
| Confirmation for dangerous actions | `ask_user` tool + tool-security permission layer |
| Auth, sessions, multi-user | Built-in auth, 2FA, session manager, SQLite |
| Memory / preferences | Memory MCP server + memory service |

**Strategy: fork Odysseus as the shell, build HomeLabAI as a domain layer.**

Odysseus contributes the *interaction model* (chat, agent, tools, MCP, auth, memory, themes). HomeLabAI contributes the *domain* (homelab tools, integrations, dashboards). This collapses the original "build Jarvis from scratch" scope into "add homelab tools + homelab surfaces to an existing agent runtime."

### License note (AGPL-3.0-or-later) — resolved, see §13.3
Single-operator deployment, no other logins → AGPL's network-use source-offer obligation does not trigger. Re-check this if that ever changes (e.g. giving family members their own login).

### Verified architecture (2026-08-07)
Confirmed directly against the real repo before committing to this plan:
- Real repo, real license: `odysseus-dev/odysseus`, AGPL-3.0, ~85k stars, actively maintained (hundreds of commits since this fork's June-2026 predecessor attempt).
- Root layout matches the claims below: `app.py`, `routes/`, `core/`, `services/`, `mcp_servers/`, `static/`.
- Language breakdown confirms a genuine vanilla-JS + FastAPI stack, not a hidden React/TS app (Python ~8.9M bytes, JavaScript ~6.3M bytes, TypeScript ~4K bytes — negligible).
- **UI reality check:** the current Odysseus UI (see `docs/odysseus-browser.jpg` in the repo) is a clean, minimal, dark chat-sidebar layout — functional, but a basic dev-tool aesthetic, not the glassmorphism/gradient "Apple+Linear+Vercel" premium look §12 describes. None of §7's new homelab surfaces (Dashboard, Media, Docker, Server, Storage, Logs) exist yet — they get built from scratch regardless of frontend choice. This directly informed the §13.1 resolution below.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  HomeLabAI (fork of Odysseus)                                  │
│                                                                │
│  ┌────────────┐   ┌──────────────────────────────────────┐    │
│  │  Frontend  │   │  Backend (FastAPI, app.py + routes/)  │    │
│  │  SPA       │◄─►│                                       │    │
│  │  (chat +   │   │  ┌────────────────────────────────┐  │    │
│  │  dashboards│   │  │  Agent runtime                 │  │    │
│  │  + cards)  │   │  │  - planner / tool loop         │  │    │
│  └────────────┘   │  │  - TOOL_HANDLERS registry      │  │    │
│                   │  │  - tool schemas + permissions  │  │    │
│                   │  │  - MCP manager                 │  │    │
│                   │  └───────────────┬────────────────┘  │    │
│                   │                  │                     │    │
│  ┌────────────────┼──────────────────┼─────────────────┐  │    │
│  │  Homelab tools │  MCP servers      │  Integration     │  │    │
│  │  (src/tools/   │  (mcp_servers/    │  clients         │  │    │
│  │   homelab/)    │   homelab_*)      │  (services/)     │  │    │
│  └────────────────┼──────────────────┼─────────────────┘  │    │
│                   │                  │                      │    │
│  ┌────────────┐   │  ┌───────────────▼──────────────────┐  │    │
│  │  SQLite    │◄──┘  │  Background workers (monitoring,  │  │    │
│  │  (state,   │      │  suggestions, scheduled agents)   │  │    │
│  │  audit,    │      └───────────────────────────────────┘  │    │
│  │  prefs)    │                                              │    │
│  └────────────┘                                              │    │
└──────────────────────────────────────────────────────────────┘
        │            │            │            │           │
     Docker       Unraid      *arr stack   Jellyfin    Scrutiny /
     socket/API    API      (Radarr, …)   Jellyseerr   Uptime Kuma
```

### 3.1 Backend
- **Python + FastAPI**, inheriting Odysseus's `app.py` + modular `routes/`.
- **SQLite** for app state, preferences, audit log, cached metrics, and suggestion history.
- **WebSockets** for live dashboard/metric streaming and streaming agent responses.
- **Background workers** for continuous monitoring, suggestion generation, and scheduled/automated agent tasks.
- Strong typing, modular services, one integration client per external system (`services/`).

### 3.2 Frontend / UX — resolved, see §13.1
**Vanilla JS, extending Odysseus's existing frontend in place** (not a separate React/Next rebuild). Chat-first SPA inherited from Odysseus (streaming, themes, sessions). New homelab surfaces added as views/routes: Dashboard, Media, Docker, Server, Storage, Monitoring, Logs, Settings. The AI chat remains **globally accessible** from every view (persistent panel or command-bar overlay). Design language per §12 — hand-rolled in plain CSS/JS since Odysseus's current design doesn't already provide it (see architecture verification above).

### 3.3 Agent & tool runtime (the heart)
This is the most important subsystem and is largely reused from Odysseus.

**The AI never runs shell commands directly.** It selects from a registry of typed tools. Each tool is a Python class exposing:

- **name** — stable identifier the model calls
- **description** — what it does + when to use it (the model reasons over this)
- **parameters** — JSON schema, validated before execution
- **permissions** — read / write / dangerous tier (drives confirmation, see §9)
- **return type** — structured result the model and UI both consume

Registration follows the existing Odysseus pattern:

```python
# src/agent_tools/homelab/docker_tools.py
class RestartContainerTool:
    name = "docker_restart_container"
    description = "Restart a Docker container by name. Write action."
    permission = "write"          # read | write | dangerous
    parameters = {                # JSON schema
        "type": "object",
        "properties": {"container": {"type": "string"}},
        "required": ["container"],
    }
    async def execute(self, container: str) -> dict:
        ...  # calls the Docker client, returns structured result

# registered in the TOOL_HANDLERS dict, same as native Odysseus tools
TOOL_HANDLERS["docker_restart_container"] = RestartContainerTool().execute
```

Adding a future integration = add tool classes (or an MCP server) + register them. No changes to the agent loop.

### 3.4 MCP & integrations — split resolved, see §13.2
Odysseus consumes MCP at runtime (`do_manage_mcp`) and ships its own MCP servers (`mcp_servers/`). HomeLabAI uses **both patterns**, split like this:

- **In-process tool classes**: Docker, Unraid (array/shares/disks), system/health (Scrutiny, Uptime Kuma, temps/metrics) — fast, frequent round-trips for live dashboard polling; no benefit from process isolation.
- **One dedicated MCP server** (`homelab_media`): the whole media ecosystem — Radarr, Sonarr, Prowlarr, Bazarr, SABnzbd, qBittorrent, Jellyfin, Jellyseerr. Coherent, self-contained, and generic enough to be reusable by other Odysseus users.

Each integration is a client in `services/` with credentials from config (§3.5), wrapped by either tool classes or the MCP server.

### 3.5 Data, config & secrets
- All integration endpoints + API keys live in env/config (`.env`, per Odysseus's `.env.example` pattern) — **never** in code, logs, or the DB in plaintext.
- Secrets are redacted from all logs and never surfaced to the model or UI.
- SQLite holds non-secret state: preferences, audit trail, cached metrics, suggestion history, watch data.

---

## 4. The AI assistant

### 4.1 Behaviour contract
- **Grounded:** every server fact comes from a tool call. If unsure, it checks the server rather than guessing.
- **Explains before acting:** states what it will do (and why) before write/dangerous actions.
- **Reasons over tools:** picks tools deliberately; shows reasoning only when it adds value.
- **Concise:** answers directly, expands only when useful.

### 4.2 Personality
Professional · helpful · technical · friendly · calm. Never verbose, sarcastic, or falsely confident.

### 4.3 Confirmation model
Tied to tool permission tier (§9). Read → runs freely. Write → runs, clearly reported. Dangerous → **always** explained and explicitly confirmed before execution.

### 4.4 Proactive suggestions
Background workers monitor the system and raise suggestions. Examples:
- "Cache usage reached 90%."
- "Docker updates available for 4 containers."
- "SMART warning detected on disk 3."
- "Jellyfin hardware transcoding appears disabled."
- "German dual audio became available for *Dune*."
- "Appdata backup hasn't run in 12 days."

Every suggestion carries a fixed shape:

| Field | Content |
|---|---|
| **Explanation** | What was observed |
| **Impact** | Why it matters |
| **Recommended fix** | Concrete action the AI can take |
| **Actions** | `Fix` · `Ignore` · `Learn More` |

`Fix` runs the associated tool(s), passing through the confirmation model if the fix is a dangerous action.

---

## 5. Homelab tool catalog

Organised by domain. Each is a tool class (or MCP tool) with the schema/permission shape from §3.3. `[R]` read, `[W]` write, `[D]` dangerous.

**Docker**
`list_containers` [R] · `container_stats` [R] · `container_logs` [R] · `inspect_container` [R] · `start_container` [W] · `restart_container` [W] · `stop_container` [W] · `update_container` [W] · `remove_container` [D]

**Unraid**
`array_status` [R] · `disk_health` [R] · `shares` [R] · `cache_usage` [R] · `smart_report` [R] · `start_array` [W] · `stop_array` [D] · `parity_check` [W] · `spin_down_disk` [W]

**Media — Radarr / Sonarr**
`search_movie` / `search_show` [R] · `add_movie` / `add_show` [W] · `queue` [R] · `history` [R] · `retry_download` [W] · `delete_media` [D]

**Media — Jellyfin / Jellyseerr**
`library_stats` [R] · `continue_watching` [R] · `recently_added` [R] · `search` [R] · `request_media` [W] · `sessions` [R]

**Downloads — SABnzbd / qBittorrent**
`queue` [R] · `pause` [W] · `resume` [W] · `set_speed_limit` [W] · `remove_download` [W]

**Subtitles — Bazarr**
`missing_subtitles` [R] · `search_subtitles` [W] · `download_subtitle` [W]

**Indexers — Prowlarr**
`indexer_status` [R] · `test_indexer` [R]

**System / health**
`system_metrics` [R] · `temperatures` [R] · `smart_summary` [R] · `read_log` [R] · `ups_status` [R] · `network_speed` [R]

> The AI selects and chains these. "Why didn't *Interstellar* download?" → `radarr.history` → `radarr.queue` → `prowlarr.indexer_status` → `read_log`, then explains.

---

## 6. Integrations

First-class, each pluggable via tool class or MCP server:

Docker · Unraid · Jellyfin · Jellyseerr · Sonarr · Radarr · Prowlarr · Bazarr · SABnzbd · qBittorrent · Scrutiny (SMART) · Uptime Kuma.

**Future / pluggable:** Wake-on-LAN, Discord, Telegram, Home Assistant, additional *arr apps. New integrations require only a client + tool registration (or an MCP server) — no agent changes.

---

## 7. UI surfaces

Each view is a *visualisation* of state the AI also has via tools. Everything updates in real time (WebSockets).

### Dashboard
At-a-glance server health in large animated cards: **Server Health · CPU · RAM · GPU · Cache · Array · Network · Internet · Docker · Downloads**, plus **Recently Added · Continue Watching · Suggestions · Recent Events · Containers · Notifications**.

### Media
Continue Watching · Recently Added · Upcoming Episodes · Download Queue · Trending · Recommendations · Library Statistics · Storage Usage · Missing Subtitles · Failed Downloads · Media Health. The AI understands the full media ecosystem across the *arr stack + Jellyfin.

### Docker
Each container is an interactive card: **Status · CPU · RAM · Network · Uptime · Health · Updates**, with **Restart · Stop · Start · Logs · Update · Inspect** (dangerous ops confirmed).

### Server
CPU · RAM · GPU · Motherboard · Temperatures · Fans · Power · Disks · Array · Parity · Cache · UPS · Network · Internet Speed · History Graphs. Live.

### Storage
Disk Usage · Shares · Cache · Parity · SMART · Read/Write Speed · Largest Folders · Duplicate Files · AI Suggestions.

### Logs
Browse Docker · System · Jellyfin · Download · Sonarr · Radarr logs. The AI reads logs on request and explains issues.

### Settings
Integrations & credentials, users & roles, AI/model config, themes, notifications, automations, audit log.

---

## 8. User profiles & personalization

Multiple users, each with: preferred language · preferred audio · subtitle preferences · favourite genres · watch history · recommendations.

> Mazhar → English audio. Parents → German audio.

The AI recalls these (via the memory service) when recommending or requesting media, e.g. surfacing German-dual-audio releases for the parents' profile automatically.

**Note on §13.3:** these profiles are for the AI's own personalization/recommendation logic (single operator using different profiles for different family members' media), not separate network logins — no one else actually authenticates into the system. Re-check the AGPL note above if that changes.

---

## 9. Security & safety

### Confirmation tiers (drive the whole safety model)
- **Read** — runs freely.
- **Write** — runs, clearly reported (restart container, add movie, pause download).
- **Dangerous** — **always** explained + explicitly confirmed before execution: delete/format, stop array, remove container, restart/shutdown server, destructive Docker ops.

### Controls
- **RBAC** — role-based tool permissions per user.
- **Audit log** — every write/dangerous action recorded (who, what, when, result).
- **Auth** — inherited Odysseus auth + 2FA; never expose raw model/service ports publicly.
- **Secrets** — API keys/secrets never exposed to the model, UI, or logs.

---

## 10. Performance
Lazy loading · streaming agent responses · virtualized tables (logs, containers, media) · real-time WebSocket updates · caching of expensive metrics · optimistic UI for actions · minimal/batched API requests.

---

## 11. Build plan (phased)

**Phase 0 — Fork & baseline.** Fork Odysseus, get it running on Unraid (Docker Compose, port 7000), auth + one model backend (local Qwen) working. Confirm agent loop + tool runtime healthy. *(in progress — see below)*

**Phase 1 — Read-only homelab.** Add read tools: Docker list/stats/logs, Unraid array/disks, system metrics, media queues. AI can *answer* questions and *explain* state. No mutations yet. Add Dashboard + Server + Docker (read) surfaces.

**Phase 2 — Safe actions.** Add write tools (restart/start/stop containers, add movie/show, pause/resume downloads, search subtitles) behind the write tier. Add action buttons to cards.

**Phase 3 — Dangerous actions + confirmation.** Add dangerous tools (array stop, delete media, remove container, server power) gated by explicit confirmation + audit log + RBAC.

**Phase 4 — Proactive brain.** Background monitoring workers → suggestion engine (Explanation/Impact/Fix/actions) → scheduled agent tasks + natural-language automations.

**Future.** Voice mode · push/Discord/Telegram notifications · Wake-on-LAN · AI diagnostics & scheduling · remote access · plugin marketplace · custom AI skills.

---

## 12. Design language

Odysseus-inspired (inspiration only — no copied branding/assets beyond what AGPL permits):

Beautiful dark interface · premium · minimal · generous whitespace · glassmorphism · subtle gradients · rounded cards · blur effects · smooth polished transitions · modern typography · responsive, desktop-first. Apple + Linear + Vercel quality. No clutter, no old-fashioned admin panels — every page feels handcrafted.

---

## 13. Decisions (resolved 2026-08-07)

1. **Frontend stack.** ~~Open~~ **Resolved: fork Odysseus's vanilla-JS frontend, extend in place.** Confirmed after checking the actual current Odysseus UI (see architecture verification above) — it's basic, not premium, so every new surface in §7 gets built from scratch either way. Extending in place wins because it inherits chat/agent/MCP/auth/themes for free with zero session-bridging work, at the cost of hand-rolling design polish in plain CSS/JS instead of using shadcn/Framer Motion.
2. **In-process tools vs MCP per integration.** ~~Open~~ **Resolved, see §3.4.** In-process for Docker/Unraid/system-health (latency-sensitive, dashboard-polled); one `homelab_media` MCP server for the whole *arr + Jellyfin ecosystem.
3. **AGPL exposure.** ~~Open~~ **Resolved: single-operator only, no other real logins.** Network-use source-offer obligation doesn't trigger. Re-check if that ever changes.
4. **Local model.** ~~Open~~ **Resolved: CPU-only, no GPU** — same hardware constraint as the existing HomelabAI v1 project on this box. Model choice needs to target CPU inference (e.g. similar quantization tier to the Qwen3-14B Q4_K_M already in use for v1) rather than assuming GPU-accelerated serving.
