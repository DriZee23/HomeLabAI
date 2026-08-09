// static/js/homelab.js
// Homelab modal: Dashboard / Server / Docker / Media tabs, backed by
// /api/homelab/* (routes/homelab_routes.py). Follows the fetch ->
// template-string -> innerHTML pattern used elsewhere in this codebase (see
// admin.js's log viewer), with polling that self-cancels once the modal is
// hidden.

import { makeWindowDraggable } from './windowDrag.js';

const API = '/api/homelab';

let _isOpen = false;
let _pollTimer = null;
let _activeTab = 'dashboard';
let _initialized = false;
let _dockerContainers = [];
let _expandedContainer = null;

function _el(id) {
  return document.getElementById(id);
}

function _escape(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function _fmtBytes(n) {
  if (n === null || n === undefined) return 'unknown';
  n = Number(n);
  if (Number.isNaN(n)) return 'unknown';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)}${units[i]}`;
}

function _fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return 'unknown';
  seconds = Math.floor(seconds);
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d ? d + 'd ' : ''}${h}h ${m}m`;
}

async function _fetchJson(path) {
  const res = await fetch(`${API}${path}`, { credentials: 'same-origin' });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data && data.detail ? data.detail : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function _errorCard(label, err) {
  const msg = err && err.message ? err.message : String(err || 'Unknown error');
  return `<div class="admin-card homelab-error-card"><h2>${_escape(label)}</h2><div class="homelab-error-text">${_escape(msg)}</div></div>`;
}

// ── Dashboard tab ──

async function _renderDashboard() {
  const panel = _el('homelab-dashboard-panel');
  if (!panel) return;

  const [sysR, dockerR, arrayR, radarrR, sonarrR] = await Promise.allSettled([
    _fetchJson('/system'),
    _fetchJson('/containers'),
    _fetchJson('/unraid/array'),
    _fetchJson('/radarr/queue'),
    _fetchJson('/sonarr/queue'),
  ]);

  let html = '<div class="homelab-grid">';

  if (sysR.status === 'fulfilled' && sysR.value && sysR.value.supported) {
    const s = sysR.value;
    html += `<div class="admin-card homelab-stat-card">
      <h2>Server</h2>
      <div class="homelab-stat-row"><span>CPU</span><span>${s.cpu_percent ?? '—'}%</span></div>
      <div class="homelab-stat-row"><span>Memory</span><span>${s.mem_percent ?? '—'}%</span></div>
      <div class="homelab-stat-row"><span>Disk</span><span>${s.disk_percent ?? '—'}%</span></div>
    </div>`;
  } else if (sysR.status === 'rejected') {
    html += _errorCard('Server', sysR.reason);
  } else {
    html += `<div class="admin-card homelab-stat-card"><h2>Server</h2><div class="homelab-empty">Not supported on this host.</div></div>`;
  }

  if (dockerR.status === 'fulfilled') {
    const containers = (dockerR.value && dockerR.value.containers) || [];
    const running = containers.filter((c) => c.status === 'running').length;
    html += `<div class="admin-card homelab-stat-card">
      <h2>Docker</h2>
      <div class="homelab-stat-row"><span>Running</span><span>${running}</span></div>
      <div class="homelab-stat-row"><span>Total</span><span>${containers.length}</span></div>
    </div>`;
  } else {
    html += _errorCard('Docker', dockerR.reason);
  }

  if (arrayR.status === 'fulfilled') {
    const a = arrayR.value || {};
    html += `<div class="admin-card homelab-stat-card">
      <h2>Unraid Array</h2>
      <div class="homelab-stat-row"><span>State</span><span>${_escape(a.state)}</span></div>
      <div class="homelab-stat-row"><span>Disks</span><span>${a.disk_count ?? '—'}</span></div>
    </div>`;
  } else {
    html += _errorCard('Unraid Array', arrayR.reason);
  }

  const queueLen = (r) => (r.status === 'fulfilled' && r.value ? (r.value.queue || []).length : null);
  const radarrCount = queueLen(radarrR);
  const sonarrCount = queueLen(sonarrR);
  if (radarrCount !== null || sonarrCount !== null) {
    html += `<div class="admin-card homelab-stat-card">
      <h2>Media Queue</h2>
      <div class="homelab-stat-row"><span>Radarr</span><span>${radarrCount ?? 'n/a'}</span></div>
      <div class="homelab-stat-row"><span>Sonarr</span><span>${sonarrCount ?? 'n/a'}</span></div>
    </div>`;
  } else {
    html += _errorCard('Media Queue', radarrR.reason || sonarrR.reason);
  }

  html += '</div>';
  panel.innerHTML = html;
}

// ── Server tab ──

async function _renderServer() {
  const panel = _el('homelab-server-panel');
  if (!panel) return;

  const [sysR, arrayR, disksR] = await Promise.allSettled([
    _fetchJson('/system'),
    _fetchJson('/unraid/array'),
    _fetchJson('/unraid/disks'),
  ]);

  let html = '<div class="homelab-grid">';

  if (sysR.status === 'fulfilled' && sysR.value && sysR.value.supported) {
    const s = sysR.value;
    html += `<div class="admin-card">
      <h2>System</h2>
      <div class="homelab-stat-row"><span>CPU</span><span>${s.cpu_percent ?? '—'}% (${s.cpu_count ?? '—'} cores)</span></div>
      <div class="homelab-stat-row"><span>Memory</span><span>${s.mem_percent ?? '—'}%</span></div>
      <div class="homelab-stat-row"><span>Disk (data dir)</span><span>${s.disk_percent ?? '—'}%</span></div>
      <div class="homelab-stat-row"><span>Uptime</span><span>${_fmtDuration(s.uptime_seconds)}</span></div>
      <div class="homelab-note">${_escape(s.scope_note || '')}</div>
    </div>`;
  } else if (sysR.status === 'fulfilled') {
    html += `<div class="admin-card"><h2>System</h2><div class="homelab-empty">${_escape((sysR.value || {}).reason || 'Not supported on this host.')}</div></div>`;
  } else {
    html += _errorCard('System', sysR.reason);
  }

  if (arrayR.status === 'fulfilled') {
    const a = arrayR.value || {};
    html += `<div class="admin-card">
      <h2>Unraid Array</h2>
      <div class="homelab-stat-row"><span>State</span><span>${_escape(a.state)}</span></div>
      <div class="homelab-stat-row"><span>Disk slots</span><span>${a.disk_slots_used ?? '—'} used / ${a.disk_slots_total ?? '—'} total</span></div>
      <div class="homelab-stat-row"><span>Array capacity</span><span>${_fmtBytes(a.array_capacity_used_bytes)} / ${_fmtBytes(a.array_capacity_total_bytes)}</span></div>
      <div class="homelab-stat-row"><span>Total storage (all disks)</span><span>${_fmtBytes(a.total_storage_bytes)}</span></div>
      <div class="homelab-note">"Array capacity" is data+parity only and excludes cache pools — it's 0 if you have no array disks assigned.</div>
    </div>`;
  } else {
    html += _errorCard('Unraid Array', arrayR.reason);
  }

  if (disksR.status === 'fulfilled') {
    const disks = (disksR.value && disksR.value.disks) || [];
    const rows = disks
      .map(
        (d) =>
          `<div class="homelab-stat-row"><span>${_escape(d.name)} <span class="homelab-note" style="display:inline">(${_escape(d.role)})</span></span><span>${_escape(d.status)} — ${_fmtBytes(d.size_bytes)}${d.temp_celsius !== null && d.temp_celsius !== undefined ? ` — ${d.temp_celsius}°C` : ''}</span></div>`
      )
      .join('');
    html += `<div class="admin-card"><h2>Disk Health</h2>${rows || '<div class="homelab-empty">No disks reported.</div>'}</div>`;
  } else {
    html += _errorCard('Disk Health', disksR.reason);
  }

  html += '</div>';
  panel.innerHTML = html;
}

// ── Docker tab ──

function _safeId(name) {
  return String(name).replace(/[^a-zA-Z0-9_-]/g, '_');
}

function _statusClass(status) {
  if (status === 'running') return 'homelab-status-running';
  if (status === 'exited') return 'homelab-status-exited';
  return 'homelab-status-other';
}

function _containerCardHtml(c) {
  const expanded = _expandedContainer === c.name;
  return `<div class="admin-card homelab-container-card" id="homelab-container-${_safeId(c.name)}">
    <div class="homelab-container-header">
      <span class="homelab-status-dot ${_statusClass(c.status)}"></span>
      <span class="homelab-container-name">${_escape(c.name)}</span>
      <span class="homelab-container-image">${_escape(c.image)}</span>
      <span class="homelab-container-status">${_escape(c.status)}</span>
    </div>
    ${expanded ? `<div class="homelab-container-details" id="homelab-container-details-${_safeId(c.name)}">Loading…</div>` : ''}
  </div>`;
}

async function _renderDocker() {
  const panel = _el('homelab-docker-panel');
  if (!panel) return;

  try {
    const data = await _fetchJson('/containers');
    _dockerContainers = data.containers || [];
  } catch (err) {
    panel.innerHTML = _errorCard('Docker', err);
    return;
  }

  if (!_dockerContainers.length) {
    panel.innerHTML = '<div class="homelab-empty">No containers found.</div>';
    return;
  }

  panel.innerHTML = _dockerContainers.map((c) => _containerCardHtml(c)).join('');
  _dockerContainers.forEach((c) => {
    const card = _el(`homelab-container-${_safeId(c.name)}`);
    const header = card && card.querySelector('.homelab-container-header');
    if (header) header.addEventListener('click', () => _toggleContainer(c.name));
  });

  if (_expandedContainer) {
    _loadContainerDetails(_expandedContainer);
  }
}

async function _toggleContainer(name) {
  _expandedContainer = _expandedContainer === name ? null : name;
  await _renderDocker();
}

async function _loadContainerDetails(name) {
  const target = _el(`homelab-container-details-${_safeId(name)}`);
  if (!target) return;
  try {
    const [stats, logsData] = await Promise.all([
      _fetchJson(`/containers/${encodeURIComponent(name)}/stats`),
      _fetchJson(`/containers/${encodeURIComponent(name)}/logs?tail=30`),
    ]);
    target.innerHTML = `
      <div class="homelab-stat-row"><span>CPU</span><span>${stats.cpu_percent !== null && stats.cpu_percent !== undefined ? stats.cpu_percent + '%' : 'unavailable'}</span></div>
      <div class="homelab-stat-row"><span>Memory</span><span>${stats.mem_percent !== null && stats.mem_percent !== undefined ? stats.mem_percent + '%' : 'unavailable'} (${_fmtBytes(stats.mem_usage_bytes)} / ${_fmtBytes(stats.mem_limit_bytes)})</span></div>
      <div class="homelab-stat-row"><span>Network</span><span>rx ${_fmtBytes(stats.net_rx_bytes)} / tx ${_fmtBytes(stats.net_tx_bytes)}</span></div>
      <pre class="homelab-log-view">${_escape(logsData.logs || '')}</pre>
    `;
  } catch (err) {
    target.innerHTML = `<div class="homelab-error-text">${_escape((err && err.message) || String(err))}</div>`;
  }
}

// ── Media tab ──

function _listCard(title, items, primaryFn, secondaryFn, emptyText, limit = 6) {
  if (!items.length) {
    return `<div class="admin-card"><h2>${_escape(title)}</h2><div class="homelab-empty">${_escape(emptyText)}</div></div>`;
  }
  const rows = items
    .slice(0, limit)
    .map(
      (it) =>
        `<div class="homelab-list-row"><span class="homelab-list-primary">${primaryFn(it)}</span><span class="homelab-list-secondary">${secondaryFn ? secondaryFn(it) : ''}</span></div>`
    )
    .join('');
  const more = items.length > limit ? `<div class="homelab-note">+${items.length - limit} more</div>` : '';
  return `<div class="admin-card"><h2>${_escape(title)}</h2>${rows}${more}</div>`;
}

function _unwrap(result, key) {
  return result.status === 'fulfilled' ? (result.value && result.value[key]) || [] : null;
}

async function _renderMedia() {
  const panel = _el('homelab-media-panel');
  if (!panel) return;

  const [
    sessionsR,
    recentR,
    continueR,
    statsR,
    radarrQR,
    sonarrQR,
    radarrHR,
    sonarrHR,
    prowlarrR,
    sabR,
    qbitR,
    bazarrR,
  ] = await Promise.allSettled([
    _fetchJson('/jellyfin/sessions'),
    _fetchJson('/jellyfin/recently-added'),
    _fetchJson('/jellyfin/continue-watching'),
    _fetchJson('/jellyfin/stats'),
    _fetchJson('/radarr/queue'),
    _fetchJson('/sonarr/queue'),
    _fetchJson('/radarr/history'),
    _fetchJson('/sonarr/history'),
    _fetchJson('/prowlarr/indexers'),
    _fetchJson('/sabnzbd/queue'),
    _fetchJson('/qbittorrent/queue'),
    _fetchJson('/bazarr/missing-subtitles'),
  ]);

  let html = '<div class="homelab-grid">';

  // Now Playing
  if (sessionsR.status === 'fulfilled') {
    const sessions = ((sessionsR.value && sessionsR.value.sessions) || []).filter((s) => s.playing);
    html += _listCard(
      'Now Playing',
      sessions,
      (s) => `${_escape(s.playing)}`,
      (s) => `${_escape(s.user || 'unknown')} — ${_escape(s.device || s.client || '')}`,
      'Nothing playing right now.'
    );
  } else {
    html += _errorCard('Now Playing', sessionsR.reason);
  }

  // Jellyfin library stats
  if (statsR.status === 'fulfilled') {
    const s = statsR.value || {};
    html += `<div class="admin-card">
      <h2>Jellyfin Library</h2>
      <div class="homelab-stat-row"><span>Movies</span><span>${s.movie_count ?? '—'}</span></div>
      <div class="homelab-stat-row"><span>Series</span><span>${s.series_count ?? '—'}</span></div>
      <div class="homelab-stat-row"><span>Episodes</span><span>${s.episode_count ?? '—'}</span></div>
    </div>`;
  } else {
    html += _errorCard('Jellyfin Library', statsR.reason);
  }

  // Continue watching
  if (continueR.status === 'fulfilled') {
    const items = (continueR.value && continueR.value.items) || [];
    html += _listCard(
      'Continue Watching',
      items,
      (i) => `${_escape(i.series ? `${i.series} — ${i.name}` : i.name)}`,
      (i) => `${i.progress_percent ?? 0}%`,
      'Nothing in progress.'
    );
  } else {
    html += _errorCard('Continue Watching', continueR.reason);
  }

  // Recently added
  if (recentR.status === 'fulfilled') {
    const items = (recentR.value && recentR.value.items) || [];
    html += _listCard(
      'Recently Added',
      items,
      (i) => `${_escape(i.name)}`,
      (i) => `${_escape(i.type || '')}`,
      'Nothing added recently.'
    );
  } else {
    html += _errorCard('Recently Added', recentR.reason);
  }

  // Download queue — merged Radarr + Sonarr
  const queueItems = [
    ...(_unwrap(radarrQR, 'queue') || []).map((q) => ({ ...q, service: 'Radarr' })),
    ...(_unwrap(sonarrQR, 'queue') || []).map((q) => ({ ...q, service: 'Sonarr' })),
  ];
  if (radarrQR.status === 'fulfilled' || sonarrQR.status === 'fulfilled') {
    html += _listCard(
      'Download Queue',
      queueItems,
      (q) => `${_escape(q.title || 'unknown')}`,
      (q) => `${_escape(q.service)} — ${_escape(q.status || '')}`,
      'Queue is empty.'
    );
  } else {
    html += _errorCard('Download Queue', radarrQR.reason || sonarrQR.reason);
  }

  // Recent activity — merged Radarr + Sonarr history, newest first
  const historyItems = [
    ...(_unwrap(radarrHR, 'history') || []).map((h) => ({ ...h, service: 'Radarr' })),
    ...(_unwrap(sonarrHR, 'history') || []).map((h) => ({ ...h, service: 'Sonarr' })),
  ].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
  if (radarrHR.status === 'fulfilled' || sonarrHR.status === 'fulfilled') {
    html += _listCard(
      'Recent Activity',
      historyItems,
      (h) => `${_escape(h.title || 'unknown')}`,
      (h) => `${_escape(h.service)} — ${_escape(h.event_type || '')}`,
      'No recent activity.',
      8
    );
  } else {
    html += _errorCard('Recent Activity', radarrHR.reason || sonarrHR.reason);
  }

  // Prowlarr indexers
  if (prowlarrR.status === 'fulfilled') {
    const items = (prowlarrR.value && prowlarrR.value.indexers) || [];
    html += _listCard(
      'Indexers',
      items,
      (i) => `${_escape(i.name)}`,
      (i) => `${i.enabled ? 'enabled' : 'disabled'} — priority ${i.priority ?? '—'}`,
      'No indexers configured.'
    );
  } else {
    html += _errorCard('Indexers', prowlarrR.reason);
  }

  // SABnzbd queue
  if (sabR.status === 'fulfilled') {
    const items = (sabR.value && sabR.value.queue) || [];
    html += _listCard(
      'SABnzbd',
      items,
      (s) => `${_escape(s.name || 'unknown')}`,
      (s) => `${_escape(s.status || '')} — ${s.percentage ?? 0}%`,
      'Queue is empty.'
    );
  } else {
    html += _errorCard('SABnzbd', sabR.reason);
  }

  // qBittorrent queue
  if (qbitR.status === 'fulfilled') {
    const items = (qbitR.value && qbitR.value.queue) || [];
    html += _listCard(
      'qBittorrent',
      items,
      (t) => `${_escape(t.name || 'unknown')}`,
      (t) => `${_escape(t.state || '')} — ${t.progress_percent ?? 0}%`,
      'No torrents.'
    );
  } else {
    html += _errorCard('qBittorrent', qbitR.reason);
  }

  // Bazarr missing subtitles
  if (bazarrR.status === 'fulfilled') {
    const items = (bazarrR.value && bazarrR.value.missing) || [];
    html += _listCard(
      'Missing Subtitles',
      items,
      (m) => `${_escape(m.title || 'unknown')}`,
      (m) => `${_escape(m.type || '')} — ${(m.missing_languages || []).length} lang(s)`,
      'Nothing missing.'
    );
  } else {
    html += _errorCard('Missing Subtitles', bazarrR.reason);
  }

  html += '</div>';
  panel.innerHTML = html;
}

// ── Tabs, polling, open/close ──

function _loadActiveTab() {
  if (_activeTab === 'dashboard') _renderDashboard();
  else if (_activeTab === 'server') _renderServer();
  else if (_activeTab === 'docker') _renderDocker();
  else if (_activeTab === 'media') _renderMedia();
}

function _switchTab(tab) {
  _activeTab = tab;
  document.querySelectorAll('.homelab-tab-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.homelabTab === tab);
  });
  document.querySelectorAll('.homelab-tab-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.dataset.homelabPanel === tab);
  });
  _loadActiveTab();
}

function _startPolling() {
  if (_pollTimer) return;
  _pollTimer = setInterval(() => {
    const modal = _el('homelab-modal');
    if (!modal || modal.classList.contains('hidden')) {
      _stopPolling();
      return;
    }
    _loadActiveTab();
  }, 5000);
}

function _stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

function _init() {
  if (_initialized) return;
  _initialized = true;
  document.querySelectorAll('.homelab-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => _switchTab(btn.dataset.homelabTab));
  });
  const closeBtn = _el('close-homelab-modal');
  if (closeBtn) closeBtn.addEventListener('click', close);

  // Same pattern as gallery.js/cookbook.js/etc — drag the window by its header.
  const modal = _el('homelab-modal');
  const content = modal && modal.querySelector('.modal-content');
  const header = content && content.querySelector('.modal-header');
  if (modal && content && header) makeWindowDraggable(modal, { content, header });
}

function open() {
  _init();
  const modal = _el('homelab-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  _isOpen = true;
  _loadActiveTab();
  _startPolling();
}

function close() {
  const modal = _el('homelab-modal');
  if (modal) modal.classList.add('hidden');
  _isOpen = false;
  _stopPolling();
}

function isOpen() {
  return _isOpen;
}

const homelabModule = { open, close, isOpen };
export default homelabModule;
