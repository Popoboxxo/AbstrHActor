// Abstractor sidebar panel (Phase UI-1/UI-2).
// Management surface on top of the Abstractor websocket API. Base mode is
// read-only; an explicit, admin-gated "Edit mode" toggle exposes write
// affordances: an in-panel create/edit form (device type, sources, logical
// identity, numeric pipeline), delete-with-confirm, and per-card configure.
// Device-to-device moves stay in the native config flow on purpose (the
// registry-mapping transaction lives there; the panel must not duplicate it).
// Write commands are authorized server-side solely by HA admin privileges.
import {
  AGGREGATION_MODES,
  DEVICE_TYPES,
  buildPayload,
  hasErrors,
  isNumericType,
  subentryToFields,
  validateSensorForm,
} from './sensor-form.js';

const TABS = [
  { id: 'devices', key: 'tab.devices' },
  { id: 'health', key: 'tab.health' },
  { id: 'settings', key: 'tab.settings' },
  { id: 'migrate', key: 'tab.migrate' },
];

const I18N = {
  en: {
    'tab.devices': 'Devices',
    'tab.health': 'Health',
    'tab.settings': 'Settings',
    'tab.migrate': 'Migrate',
    'action.editMode': 'Edit mode',
    'action.disableEdit': 'Disable edit',
    'action.addSensor': 'Add sensor',
    'action.export': 'Export',
    'action.import': 'Import',
    'action.close': 'Close',
    'action.details': 'Details',
    'action.edit': 'Edit',
    'action.configure': 'Configure',
    'action.delete': 'Delete',
    'action.save': 'Save',
    'action.cancel': 'Cancel',
    'form.createTitle': 'Add Abstract sensor',
    'form.editTitle': 'Configure Abstract sensor',
    'form.deviceType': 'Device type',
    'form.sources': 'Source entities',
    'form.logicalName': 'Logical name',
    'form.objectId': 'Entity object id',
    'form.aggregation': 'Aggregation',
    'form.spikeFilter': 'Enable spike filter',
    'form.invert': 'Invert value',
    'form.fallbackZero': 'Fail soft to zero',
    'form.fallbackOnZero': 'Use fallback when zero',
    'form.netSubtract': 'Subtract entity (net flow)',
    'form.fallbackSource': 'Fallback source entity',
    'form.fallbackCondition': 'Fallback condition entity',
    'form.fallbackConditionState': 'Fallback condition state',
    'confirm.delete': 'Delete this Abstract sensor?',
    'status.sensors': 'sensors',
    'status.loading': 'Loading...',
    'title': 'Abstractor',
    'subtitle.readOnly': 'read-only base',
    'subtitle.editMode': 'EDIT MODE',
    'filter.all': 'all',
    'filter.power': 'power',
    'filter.energy': 'energy',
    'filter.water': 'water',
    'filter.door_contact': 'door contact',
    'filter.motion': 'motion',
    'filter.smoke': 'smoke',
    'filter.problems': 'problems',
    'empty.loading': 'Loading Abstractor sensors...',
    'empty.none': 'No matching Abstractor sensors.',
    'admin.required': 'Administrator access required',
    'common.sensor': 'Abstractor sensor',
    'field.entity': 'entity',
    'field.uniqueId': 'unique_id',
    'field.source': 'source',
    'health.bad': 'Bad',
    'health.warn': 'Warnings',
    'health.none': 'None',
    'health.total': 'Total',
    'health.noEvent': 'no event',
    'health.value': 'value',
    'settings.hint': 'Read-only base. Use Edit mode for Import/advanced actions; configuration stays in HA Settings -> Devices & Services.',
    'error.adminOnly': 'Edit mode is available to administrators only.',
    'migrate.title': 'Migrate',
    'migrate.empty': 'No YAML sensors detected.',
    'migrate.colSource': 'Source',
    'migrate.colStatus': 'Status',
  },
  de: {
    'tab.devices': 'Geraete',
    'tab.health': 'Status',
    'tab.settings': 'Einstellungen',
    'tab.migrate': 'Migration',
    'action.editMode': 'Bearbeiten',
    'action.disableEdit': 'Bearbeiten beenden',
    'action.addSensor': 'Sensor hinzufuegen',
    'action.export': 'Exportieren',
    'action.import': 'Importieren',
    'action.close': 'Schliessen',
    'action.details': 'Details',
    'action.edit': 'Bearbeiten',
    'action.configure': 'Konfigurieren',
    'action.delete': 'Loeschen',
    'action.save': 'Speichern',
    'action.cancel': 'Abbrechen',
    'form.createTitle': 'Abstract-Sensor hinzufuegen',
    'form.editTitle': 'Abstract-Sensor konfigurieren',
    'form.deviceType': 'Geraetetyp',
    'form.sources': 'Quell-Entitaeten',
    'form.logicalName': 'Logischer Name',
    'form.objectId': 'Entity-Object-Id',
    'form.aggregation': 'Aggregation',
    'form.spikeFilter': 'Spike-Filter aktivieren',
    'form.invert': 'Wert invertieren',
    'form.fallbackZero': 'Bei Fehler auf Null',
    'form.fallbackOnZero': 'Fallback bei Null verwenden',
    'form.netSubtract': 'Entitaet abziehen (Nettofluss)',
    'form.fallbackSource': 'Fallback-Quellentitaet',
    'form.fallbackCondition': 'Fallback-Bedingungsentitaet',
    'form.fallbackConditionState': 'Fallback-Bedingungszustand',
    'confirm.delete': 'Diesen Abstract-Sensor loeschen?',
    'status.sensors': 'Sensoren',
    'status.loading': 'Laedt...',
    'title': 'Abstractor',
    'subtitle.readOnly': 'schreibgeschuetzte Basis',
    'subtitle.editMode': 'EDIT-MODUS',
    'filter.all': 'alle',
    'filter.power': 'Leistung',
    'filter.energy': 'Energie',
    'filter.water': 'Wasser',
    'filter.door_contact': 'Tuerkontakt',
    'filter.motion': 'Bewegung',
    'filter.smoke': 'Rauch',
    'filter.problems': 'Probleme',
    'empty.loading': 'Abstractor-Sensoren werden geladen...',
    'empty.none': 'Keine passenden Abstractor-Sensoren.',
    'admin.required': 'Administratorzugriff erforderlich',
    'common.sensor': 'Abstractor-Sensor',
    'field.entity': 'Entity',
    'field.uniqueId': 'Unique-ID',
    'field.source': 'Quelle',
    'health.bad': 'Fehler',
    'health.warn': 'Warnungen',
    'health.none': 'Keine',
    'health.total': 'Gesamt',
    'health.noEvent': 'kein Ereignis',
    'health.value': 'Wert',
    'settings.hint': 'Schreibgeschuetzte Basis. Nutze den Bearbeiten-Modus fuer Import/erweiterte Aktionen; die Konfiguration bleibt unter HA Einstellungen -> Geraete & Dienste.',
    'error.adminOnly': 'Der Bearbeiten-Modus ist nur fuer Administratoren verfuegbar.',
    'migrate.title': 'Migration',
    'migrate.empty': 'Keine YAML-Sensoren gefunden.',
    'migrate.colSource': 'Quelle',
    'migrate.colStatus': 'Status',
  },
};

function _langFor(hass) {
  const raw = hass && hass.language ? String(hass.language) : 'en';
  const code = raw.toLowerCase().slice(0, 2);
  return I18N[code] ? code : 'en';
}

function _t(hass, key) {
  const dict = I18N[_langFor(hass)];
  if (dict && Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
  const fallback = I18N.en;
  if (fallback && Object.prototype.hasOwnProperty.call(fallback, key)) return fallback[key];
  return key;
}

try { if (typeof window !== 'undefined') window.AbstractorI18n = { languages: I18N, translate: _t, defaultLanguage: 'en' }; } catch (e) {}


class AbstractorStore {
  constructor() {
    this.state = {
      subentries: [],
      loaded: false,
      loading: false,
      error: '',
      activeTab: 'devices',
      lastFetchAt: 0,
      editMode: false,
      admin: false,
    };
    this.subscribers = [];
  }
  subscribe(fn) { this.subscribers.push(fn); }
  get state() { return this._state; }
  set state(v) { this._state = v; }
  setState(patch) {
    this.state = Object.assign({}, this.state, patch);
    this.subscribers.forEach((fn) => fn(this.state));
  }
}

class AbstractorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._store = new AbstractorStore();
    this._signature = '';
    this._fetchPromise = null;
    this._detail = null;
    this._filterOverride = null;
    this._migrateLoaded = false;
    this._migrateSensors = [];
    this._modalEl = null;
    this._modalForm = null;
    this._modalPickers = [];
    this._subscribed = false;
    this._unsub = null;
    this._store.subscribe(() => this._render());
  }

  set hass(hass) {
    this._hass = hass;
    if (hass && hass.user) {
      this._store.setState({ admin: !!hass.user.is_admin });
    }
    this._modalPickers.forEach((picker) => { picker.hass = hass; });
    this._ensureSubscription();
    this._maybeFetch();
    this._render();
  }
  get hass() { return this._hass; }
  set narrow(_narrow) { this._render(); }

  _navigate(path) {
    history.pushState(null, '', path);
    window.dispatchEvent(new CustomEvent('location-changed', { bubbles: true, composed: true }));
  }

  _showError(message) {
    this._store.setState({ error: message || '' });
  }

  async _callService(service, data) {
    return this._hass.callService('abstractor', service, data || {}, undefined, false, /export/.test(service));
  }

  async _fetchSubentries(force) {
    if (!this._hass || !this._hass.callWS) return;
    if (!this._store.state.admin) return;
    const now = Date.now();
    if (!force && this._store.state.loading) return;
    if (!force && this._store.state.loaded && now - this._store.state.lastFetchAt < 1500) return;
    this._store.setState({ loading: true, error: '' });
    try {
      const result = await this._hass.callWS({ type: 'abstractor/subentries' });
      const list = (result && Array.isArray(result.subentries)) ? result.subentries : [];
      this._store.setState({ subentries: list, loaded: true, loading: false, lastFetchAt: Date.now() });
    } catch (err) {
      this._store.setState({ loading: false, error: 'Load failed: ' + (err && err.message ? err.message : err) });
    }
  }

  _maybeFetch() {
    if (this._subscribed) return; // the live subscription keeps data fresh
    if (!this._hass || !this._hass.user || !this._hass.user.is_admin) return;
    const s = this._store.state;
    const stale = Date.now() - s.lastFetchAt > 10000;
    if (!s.loading && (!s.loaded || stale)) {
      this._fetchSubentries(false);
    }
  }

  _ensureSubscription() {
    if (this._subscribed) return;
    if (!this._hass || !this._hass.user || !this._hass.user.is_admin) return;
    if (!this._hass.connection || !this._hass.connection.subscribeMessage) return;
    this._subscribed = true;
    this._store.setState({ loading: true, error: '' });
    this._hass.connection
      .subscribeMessage(
        (event) => {
          const list = (event && Array.isArray(event.subentries)) ? event.subentries : [];
          this._store.setState({
            subentries: list,
            loaded: true,
            loading: false,
            lastFetchAt: Date.now(),
          });
        },
        { type: 'abstractor/subentries/subscribe' }
      )
      .then((unsub) => { this._unsub = unsub; })
      .catch((err) => {
        this._subscribed = false;
        this._store.setState({
          loading: false,
          error: 'Load failed: ' + (err && err.message ? err.message : err),
        });
      });
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    this._subscribed = false;
  }

  _toggleEditMode() {
    const s = this._store.state;
    if (!s.admin) {
      this._showError(this._t('error.adminOnly'));
      return;
    }
    this._showError('');
    this._store.setState({ editMode: !s.editMode });
  }

  _filteredSubentries() {
    const chip = this._activeFilter();
    const all = this._store.state.subentries || [];
    if (chip === 'problems') return all.filter((s) => s.health === 'warn' || s.health === 'bad');
    if (chip === 'all') return all;
    return all.filter((s) => (s.device_type || '') === chip);
  }


  _healthDot(health) {
    const map = { ok: '\u2713', warn: '!', bad: '\u2715', idle: '\u25CB' };
    return map[health] || '\u25CB';
  }

  _t(key) {
    return _t(this._hass, key);
  }

  _styles() {
    return `
      :host { display:block; padding:16px; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
      h1 { font-size:1.5em; margin:0 0 4px 0; color:var(--primary-text-color); }
      p.subtitle { color:var(--secondary-text-color); margin:0 0 20px 0; }
      .header { display:flex; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; gap:8px; }
      .actions { display:flex; gap:8px; flex-wrap:wrap; }
      button {
        font:inherit; cursor:pointer; border-radius:4px; padding:8px 12px;
        border:1px solid var(--divider-color,#ccc);
        background:var(--card-background-color,white);
        color:var(--primary-color,#03a9f4);
      }
      button:hover { background:var(--secondary-background-color,#f0f0f0); }
      button:disabled { opacity:.5; cursor:not-allowed; }
      .tabs { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 12px 0; border-bottom:1px solid var(--divider-color,#eee); padding-bottom:8px; }
      .tab { border:none; background:none; padding:6px 10px; border-radius:4px; }
      .tab.active { background:var(--secondary-background-color,#eef); font-weight:600; }
      .filter-chip { border:1px solid var(--divider-color,#ccc); background:var(--card-background-color,white); }
      .filter-chip.active { background:var(--primary-color,#03a9f4); color:var(--text-primary-color,white); }
      .error { margin:8px 0 0 0; padding:8px 12px; border-radius:4px; background:var(--error-color,#db4437); color:var(--text-primary-color,white); }
      .empty { padding:32px; text-align:center; color:var(--secondary-text-color); }
      .device-card { background:var(--card-background-color,white); border-radius:var(--ha-card-border-radius,12px); box-shadow:var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,0.1)); padding:16px; margin-bottom:12px; }
      .card-header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
      .health { font-weight:700; padding:2px 8px; border-radius:999px; border:1px solid var(--divider-color,#ccc); }
      .health.ok { color:#2e7d32; }
      .health.warn { color:#f9a825; }
      .health.bad { color:#c62828; }
      table { width:100%; border-collapse:collapse; }
      td { padding:4px 8px 4px 0; color:var(--primary-text-color); font-size:.95em; }
      td.value { text-align:right; font-weight:500; }
      td.entity-id { color:var(--secondary-text-color); font-size:.85em; }
      .row-health { margin-left:6px; }
      .hint { color:var(--secondary-text-color); font-size:.85em; margin:6px 0; }
      .drawer-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.4); display:flex; justify-content:flex-end; z-index:1000; }
      .drawer { width:min(480px,90vw); height:100%; background:var(--card-background-color,white); overflow:auto; padding:16px; box-shadow:-2px 0 10px rgba(0,0,0,.2); }
      .drawer h2 { margin-top:0; }
      .drawer .close { float:right; }
      .drawer .field { margin:8px 0; }
      .drawer .field b { display:block; font-size:.85em; color:var(--secondary-text-color); }
      .toast { margin:8px 0; padding:8px 12px; border-radius:4px; background:var(--primary-color,#03a9f4); color:var(--text-primary-color,white); }
    `;
  }

  _render() {
    if (!this._hass) return;
    const s = this._store.state;
    const statusText = (!s.admin)
      ? this._t('admin.required')
      : (s.loaded ? `${s.subentries.length} ${this._t('status.sensors')}` : this._t('status.loading'));
    const html = `
      <style>${this._styles()}</style>
      <div class="header">
        <div>
          <h1>${this._t('title')}</h1>
          <p class="subtitle">${statusText} · ${this._t('subtitle.readOnly')}${s.editMode ? ' · ' + this._t('subtitle.editMode') : ''}</p>
        </div>
        <div class="actions">
          <button type="button" class="tab-toggle">${s.editMode ? this._t('action.disableEdit') : this._t('action.editMode')}</button>
          <button type="button" class="add-sensor-button">${this._t('action.addSensor')}</button>
          <button type="button" class="export-button">${this._t('action.export')}</button>
          <button type="button" class="import-button">${this._t('action.import')}</button>
          <input type="file" accept="application/json" class="import-file-input" hidden>
        </div>
      </div>
      <div class="tabs">
        ${TABS.map((t) => `<button type="button" class="tab ${s.activeTab===t.id?'active':''}" data-tab="${t.id}">${this._t(t.key)}</button>`).join('')}
      </div>
      <div class="body"></div>
    `;
    this.shadowRoot.innerHTML = html;

    // Error text may carry server-provided strings (str(exc)); never inject it
    // via innerHTML — build the node with textContent instead.
    if (s.error) {
      const errorEl = document.createElement('div');
      errorEl.className = 'error';
      errorEl.setAttribute('role', 'alert');
      errorEl.setAttribute('aria-live', 'assertive');
      errorEl.textContent = s.error;
      const headerEl = this.shadowRoot.querySelector('.header');
      if (headerEl) headerEl.after(errorEl);
      else this.shadowRoot.appendChild(errorEl);
    }


    // wire header
    this.shadowRoot.querySelector('.tab-toggle').addEventListener('click', () => this._toggleEditMode());
    this.shadowRoot.querySelector('.add-sensor-button').addEventListener('click', () => {
      if (this._store.state.editMode) this._openSensorForm(null);
      else this._navigate('/config/integrations/integration/abstractor');
    });
    this.shadowRoot.querySelector('.export-button').addEventListener('click', () => this._handleExport());
    const fileInput = this.shadowRoot.querySelector('.import-file-input');
    this.shadowRoot.querySelector('.import-button').addEventListener('click', () => { if (fileInput) fileInput.click(); });
    if (fileInput) {
      fileInput.addEventListener('change', () => {
        const file = fileInput.files && fileInput.files[0];
        fileInput.value = '';
        if (file) this._handleImportFile(file);
      });
    }
    // tabs
    this.shadowRoot.querySelectorAll('.tab').forEach((b) => {
      b.addEventListener('click', () => this._store.setState({ activeTab: b.getAttribute('data-tab') }));
    });

    const bodyEl = this.shadowRoot.querySelector('.body');
    if (s.activeTab === 'devices') this._renderDevices(bodyEl);
    else if (s.activeTab === 'health') this._renderHealth(bodyEl);
    else if (s.activeTab === 'migrate') this._renderMigrate(bodyEl);
    else this._renderSettings(bodyEl);

    if (s.activeTab === 'migrate' && !this._migrateLoaded) {
      this._fetchYamlScan();
    }

    if (this._detail) {
      const backdrop = document.createElement('div');
      backdrop.className = 'drawer-backdrop';
      backdrop.setAttribute('role','dialog');
      backdrop.setAttribute('aria-modal','true');
      const drawer = document.createElement('div');
      drawer.className = 'drawer';
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'close';
      close.textContent = this._t('action.close');
      close.addEventListener('click', () => { this._detail = null; this._render(); });
      drawer.appendChild(close);
      const h = document.createElement('h2');
      h.textContent = this._detail.logical_name || this._detail.title;
      drawer.appendChild(h);
      for (const [k,v] of Object.entries(this._detail)) {
        const f = document.createElement('div');
        f.className = 'field';
        const b = document.createElement('b');
        b.textContent = k;
        f.appendChild(b);
        const span = document.createElement('span');
        span.textContent = (v === null || v === undefined) ? '—' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
        f.appendChild(span);
        drawer.appendChild(f);
      }
      backdrop.addEventListener('click', (e) => { if (e.target === backdrop) { this._detail = null; this._render(); } });
      backdrop.appendChild(drawer);
      this.shadowRoot.appendChild(backdrop);
      const focusSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
      close.focus();
      backdrop.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); this._detail = null; this._render(); return; }
        if (e.key !== 'Tab') return;
        const items = Array.from(drawer.querySelectorAll(focusSelector));
        if (!items.length) return;
        const active = this.shadowRoot.activeElement || document.activeElement;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
      });
    }

    if (this._modalEl) this.shadowRoot.appendChild(this._modalEl);
  }

  _deviceIdFor(entry) {
    if (!this._hass || !this._hass.devices) return null;
    const found = Object.values(this._hass.devices).find((d) =>
      Array.isArray(d.identifiers) &&
      d.identifiers.some((id) => id && id[0] === 'abstractor' &&
        (id[1] === entry.subentry_id || (entry.device_group_id && id[1] === entry.device_group_id)))
    );
    return (found && found.id) || null;
  }

  _renderDevices(bodyEl) {
    const s = this._store.state;
    const filter = this._activeFilter() || 'all';
    const present = new Set((s.subentries || []).map((e) => e.device_type).filter(Boolean));
    const chips = ['all', ...DEVICE_TYPES.filter((t) => present.has(t)), 'problems'];
    bodyEl.innerHTML = `
      <div class="filter-row">
        ${chips.map((f) => `<button type="button" class="filter-chip ${filter===f?'active':''}" data-filter="${f}">${this._t('filter.' + f)}</button>`).join('')}
      </div>
    `;
    bodyEl.querySelectorAll('.filter-chip').forEach((b) => {
      b.addEventListener('click', () => {
        // re-render by toggling a small state token
        this._filterOverride = b.getAttribute('data-filter');
        this._render();
      });
    });
    const activeFilter = this._filterOverride || 'all';
    const list = (s.subentries || []).filter((e) => {
      if (activeFilter === 'all') return true;
      if (activeFilter === 'problems') return e.health === 'warn' || e.health === 'bad';
      return (e.device_type || '') === activeFilter;
    });
    if (!s.admin) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = this._t('admin.required');
      bodyEl.appendChild(empty);
      return;
    }
    if (!s.loaded) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = this._t('empty.loading');
      bodyEl.appendChild(empty);
      return;
    }
    if (!list.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = this._t('empty.none');
      bodyEl.appendChild(empty);
      return;
    }
    // group by logical_name / device (light grouping)
    for (const e of list) {
      const card = document.createElement('div');
      card.className = 'device-card';
      const header = document.createElement('div');
      header.className = 'card-header';
      const h = document.createElement('h2');
      h.textContent = (e.logical_name || e.title || this._t('common.sensor'));
      header.appendChild(h);
      const health = document.createElement('span');
      health.className = 'health ' + (e.health || 'idle');
      health.textContent = this._healthDot(e.health) + ' ' + (e.health || 'idle');
      header.appendChild(health);
      card.appendChild(header);

      const details = document.createElement('p');
      details.className = 'hint';
      const sources = Array.isArray(e.source_entity_ids) ? e.source_entity_ids.filter(Boolean).join(', ') : '';
      details.textContent = [
        e.object_id ? `${this._t('field.entity')}: ${e.object_id}` : '',
        e.legacy_unique_id ? `${this._t('field.uniqueId')}: ${e.legacy_unique_id}` : '',
        sources ? `${this._t('field.source')}: ${sources}` : '',
      ].filter(Boolean).join(' · ');
      card.appendChild(details);

      const detailsButton = document.createElement('button');
      detailsButton.type = 'button';
      detailsButton.textContent = this._t('action.details');
      detailsButton.style.margin = '8px 8px 8px 0';
      detailsButton.addEventListener('click', () => {
        this._detail = e;
        this._render();
      });
      card.appendChild(detailsButton);

      const editButton = document.createElement('button');
      editButton.type = 'button';
      editButton.textContent = this._t('action.edit');
      editButton.style.marginTop = '8px';
      const deviceId = this._deviceIdFor(e);
      editButton.addEventListener('click', () => {
        if (deviceId) this._navigate(`/config/devices/device/${deviceId}`);
        else this._navigate('/config/integrations/integration/abstractor');
      });
      card.appendChild(editButton);

      if (s.editMode) {
        const configureButton = document.createElement('button');
        configureButton.type = 'button';
        configureButton.textContent = this._t('action.configure');
        configureButton.style.marginTop = '8px';
        configureButton.style.marginLeft = '8px';
        configureButton.addEventListener('click', () => this._openSensorForm(e));
        card.appendChild(configureButton);

        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.textContent = this._t('action.delete');
        deleteButton.style.marginTop = '8px';
        deleteButton.style.marginLeft = '8px';
        deleteButton.addEventListener('click', () => this._confirmDelete(e));
        card.appendChild(deleteButton);
      }

      const table = document.createElement('table');
      const row = table.insertRow();
      row.insertCell().textContent = e.device_type || '';
      row.insertCell().className = 'value';
      row.cells[1].textContent = (e.value === null || e.value === undefined) ? '—' : String(e.value);
      card.appendChild(table);
      bodyEl.appendChild(card);
    }
  }

  _renderHealth(bodyEl) {
    const s = this._store.state;
    const bad = (s.subentries || []).filter((e) => e.health === 'bad');
    const warn = (s.subentries || []).filter((e) => e.health === 'warn');
    bodyEl.innerHTML = '';
    const summary = document.createElement('p');
    summary.className = 'hint';
    summary.textContent = `${this._t('health.bad')}: ${bad.length} · ${this._t('health.warn')}: ${warn.length} · ${this._t('health.total')}: ${(s.subentries || []).length}`;
    bodyEl.appendChild(summary);
    const renderList = (title, list) => {
      const h = document.createElement('h2');
      h.textContent = title;
      bodyEl.appendChild(h);
      if (!list.length) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = this._t('health.none');
        bodyEl.appendChild(empty);
        return;
      }
      for (const e of list) {
        const line = document.createElement('div');
        line.className = 'hint';
        line.textContent = `${this._healthDot(e.health)} ${e.logical_name || e.title} — ${e.last_event || this._t('health.noEvent')} — ${this._t('health.value')}: ${e.value}`;
        bodyEl.appendChild(line);
      }
    };
    renderList(this._t('health.bad'), bad);
    renderList(this._t('health.warn'), warn);
  }

  _renderSettings(bodyEl) {
    bodyEl.innerHTML = '';
    const hint = document.createElement('p');
    hint.className = 'hint';
    hint.textContent = this._t('settings.hint');
    bodyEl.appendChild(hint);
    const actions = document.createElement('div');
    actions.className = 'actions';
    actions.style.marginTop = '8px';
    const exportBtn = document.createElement('button');
    exportBtn.type = 'button';
    exportBtn.textContent = this._t('action.export');
    exportBtn.addEventListener('click', () => this._handleExport());
    actions.appendChild(exportBtn);
    const importBtn = document.createElement('button');
    importBtn.type = 'button';
    importBtn.textContent = this._t('action.import');
    importBtn.disabled = !this._store.state.editMode;
    importBtn.addEventListener('click', () => this._triggerImport());
    actions.appendChild(importBtn);
    bodyEl.appendChild(actions);
  }

  _renderMigrate(bodyEl) {
    bodyEl.innerHTML = '';
    const title = document.createElement('h2');
    title.textContent = this._t('migrate.title');
    bodyEl.appendChild(title);
    const table = document.createElement('table');
    const head = table.createTHead();
    const hr = head.insertRow();
    const th1 = document.createElement('th');
    th1.textContent = this._t('migrate.colSource');
    hr.appendChild(th1);
    const th2 = document.createElement('th');
    th2.textContent = this._t('migrate.colStatus');
    hr.appendChild(th2);
    const tb = document.createElement('tbody');
    table.appendChild(tb);
    bodyEl.appendChild(table);
    const sensors = this._migrateSensors || [];
    if (!sensors.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = this._t('migrate.empty');
      bodyEl.appendChild(empty);
    } else {
      for (const e of sensors) {
        const row = tb.insertRow();
        row.insertCell().textContent = String((e && (e.source || e.entity_id)) || '');
        row.insertCell().textContent = String((e && e.status) || 'pending');
      }
    }
  }

  async _fetchYamlScan() {
    if (!this._hass || !this._hass.callWS) return;
    try {
      const res = await this._hass.callWS({ type: 'abstractor/yaml_scan' });
      this._migrateSensors = (res && Array.isArray(res.sensors)) ? res.sensors : [];
      this._migrateLoaded = true;
      this._render();
    } catch (err) {
      this._showError('YAML scan failed: ' + (err && err.message ? err.message : err));
      this._migrateLoaded = true;
    }
  }

  _triggerImport() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json';
    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (file) this._handleImportFile(file);
    });
    input.click();
  }

  _activeFilter() {
    return this._filterOverride || 'all';
  }

  _field(labelKey, inputEl) {
    const wrap = document.createElement('div');
    wrap.className = 'field';
    const label = document.createElement('b');
    label.textContent = this._t(labelKey);
    wrap.appendChild(label);
    wrap.appendChild(inputEl);
    return wrap;
  }

  _textInput(value, type) {
    const input = document.createElement('input');
    input.type = type || 'text';
    input.value = value == null ? '' : String(value);
    input.style.width = '100%';
    return input;
  }

  _checkbox(checked) {
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = !!checked;
    return input;
  }

  _checkboxField(labelKey, inputEl) {
    const wrap = document.createElement('div');
    wrap.className = 'field';
    const label = document.createElement('label');
    const text = document.createElement('span');
    text.textContent = ' ' + this._t(labelKey);
    label.appendChild(inputEl);
    label.appendChild(text);
    wrap.appendChild(label);
    return wrap;
  }

  _entityPicker(values, multiple) {
    const picker = document.createElement('ha-entity-picker');
    picker.hass = this._hass;
    picker.allowCustomEntity = true;
    picker.multiple = !!multiple;
    picker.value = multiple ? (values || []) : ((values && values[0]) || '');
    this._modalPickers.push(picker);
    return picker;
  }

  _pickerValue(picker, multiple) {
    const value = picker ? picker.value : (multiple ? [] : '');
    if (multiple) return Array.isArray(value) ? value : (value ? [value] : []);
    return value || '';
  }

  _readForm(refs) {
    return {
      device_type: refs.device_type.value,
      sources: this._pickerValue(refs.sources, true),
      logical_name: refs.logical_name.value,
      object_id: refs.object_id.value,
      aggregation: refs.aggregation.value,
      spike_filter: refs.spike_filter.checked,
      invert: refs.invert.checked,
      fallback_zero: refs.fallback_zero.checked,
      fallback_on_zero: refs.fallback_on_zero.checked,
      net_subtract_entity_id: this._pickerValue(refs.net_subtract_entity_id, false),
      fallback_source_entity_id: this._pickerValue(refs.fallback_source_entity_id, false),
      fallback_condition_entity_id: this._pickerValue(refs.fallback_condition_entity_id, false),
      fallback_condition_state: refs.fallback_condition_state.value,
    };
  }

  _openSensorForm(existing) {
    if (!this._store.state.editMode) {
      this._showError(this._t('error.adminOnly'));
      return;
    }
    this._closeModal();
    const fields = existing ? subentryToFields(existing) : subentryToFields({ device_type: 'power' });

    const backdrop = document.createElement('div');
    backdrop.className = 'drawer-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');

    const form = document.createElement('div');
    form.className = 'drawer';
    form.style.width = 'min(560px, 94vw)';

    const title = document.createElement('h2');
    title.textContent = existing ? this._t('form.editTitle') : this._t('form.createTitle');
    form.appendChild(title);

    const refs = {};

    refs.device_type = document.createElement('select');
    DEVICE_TYPES.forEach((type) => {
      const opt = document.createElement('option');
      opt.value = type;
      opt.textContent = type;
      refs.device_type.appendChild(opt);
    });
    refs.device_type.value = fields.device_type;
    form.appendChild(this._field('form.deviceType', refs.device_type));

    refs.sources = this._entityPicker(fields.sources, true);
    form.appendChild(this._field('form.sources', refs.sources));

    refs.logical_name = this._textInput(fields.logical_name, 'text');
    form.appendChild(this._field('form.logicalName', refs.logical_name));

    refs.object_id = this._textInput(fields.object_id, 'text');
    form.appendChild(this._field('form.objectId', refs.object_id));

    const numeric = document.createElement('div');
    refs.aggregation = document.createElement('select');
    AGGREGATION_MODES.forEach((mode) => {
      const opt = document.createElement('option');
      opt.value = mode;
      opt.textContent = mode;
      refs.aggregation.appendChild(opt);
    });
    refs.aggregation.value = fields.aggregation;
    numeric.appendChild(this._field('form.aggregation', refs.aggregation));

    refs.spike_filter = this._checkbox(fields.spike_filter);
    numeric.appendChild(this._checkboxField('form.spikeFilter', refs.spike_filter));
    refs.invert = this._checkbox(fields.invert);
    numeric.appendChild(this._checkboxField('form.invert', refs.invert));
    refs.fallback_zero = this._checkbox(fields.fallback_zero);
    numeric.appendChild(this._checkboxField('form.fallbackZero', refs.fallback_zero));
    refs.fallback_on_zero = this._checkbox(fields.fallback_on_zero);
    numeric.appendChild(this._checkboxField('form.fallbackOnZero', refs.fallback_on_zero));

    refs.net_subtract_entity_id = this._entityPicker(
      fields.net_subtract_entity_id ? [fields.net_subtract_entity_id] : [], false
    );
    numeric.appendChild(this._field('form.netSubtract', refs.net_subtract_entity_id));
    refs.fallback_source_entity_id = this._entityPicker(
      fields.fallback_source_entity_id ? [fields.fallback_source_entity_id] : [], false
    );
    numeric.appendChild(this._field('form.fallbackSource', refs.fallback_source_entity_id));
    refs.fallback_condition_entity_id = this._entityPicker(
      fields.fallback_condition_entity_id ? [fields.fallback_condition_entity_id] : [], false
    );
    numeric.appendChild(this._field('form.fallbackCondition', refs.fallback_condition_entity_id));
    refs.fallback_condition_state = this._textInput(fields.fallback_condition_state, 'text');
    numeric.appendChild(this._field('form.fallbackConditionState', refs.fallback_condition_state));

    form.appendChild(numeric);

    const syncNumeric = () => {
      numeric.style.display = isNumericType(refs.device_type.value) ? '' : 'none';
    };
    refs.device_type.addEventListener('change', syncNumeric);
    syncNumeric();

    const errEl = document.createElement('div');
    errEl.className = 'error';
    errEl.setAttribute('role', 'alert');
    errEl.style.display = 'none';
    form.appendChild(errEl);

    const actions = document.createElement('div');
    actions.className = 'actions';
    actions.style.marginTop = '12px';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = this._t('action.cancel');
    cancelBtn.addEventListener('click', () => this._closeModal());
    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.textContent = this._t('action.save');
    saveBtn.addEventListener('click', () => this._submitSensorForm(existing, refs, errEl, saveBtn));
    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
    form.appendChild(actions);

    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) this._closeModal(); });
    backdrop.appendChild(form);
    this._modalEl = backdrop;
    this._modalForm = form;
    this.shadowRoot.appendChild(backdrop);
    if (refs.device_type.focus) refs.device_type.focus();
  }

  async _submitSensorForm(existing, refs, errEl, saveBtn) {
    const fields = this._readForm(refs);
    const errors = validateSensorForm(fields);
    if (hasErrors(errors)) {
      errEl.textContent = Object.values(errors).join('; ');
      errEl.style.display = '';
      return;
    }
    const data = buildPayload(fields);
    saveBtn.disabled = true;
    try {
      if (existing) {
        await this._hass.callWS({
          type: 'abstractor/subentry/update',
          subentry_id: existing.subentry_id,
          data,
        });
      } else {
        await this._hass.callWS({ type: 'abstractor/subentry/create', data });
      }
      this._closeModal();
      this._showError('');
      await this._fetchSubentries(true);
    } catch (err) {
      errEl.textContent = `Save failed: ${err && err.message ? err.message : err}`;
      errEl.style.display = '';
      saveBtn.disabled = false;
    }
  }

  async _confirmDelete(entry) {
    if (!this._store.state.editMode) return;
    if (!window.confirm(this._t('confirm.delete'))) return;
    try {
      await this._hass.callWS({ type: 'abstractor/subentry/delete', subentry_id: entry.subentry_id });
      await this._fetchSubentries(true);
    } catch (err) {
      this._showError(`Delete failed: ${err && err.message ? err.message : err}`);
    }
  }

  _closeModal() {
    if (this._modalEl && this._modalEl.parentNode) {
      this._modalEl.parentNode.removeChild(this._modalEl);
    }
    this._modalEl = null;
    this._modalForm = null;
    this._modalPickers = [];
  }

  async _handleExport() {
    this._showError('');
    try {
      const result = await this._hass.callService('abstractor', 'export_data', {}, undefined, false, true);
      const snapshot = (result && result.response && result.response.snapshot) || (result && result.snapshot);
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'abstractor-snapshot.json';
      this.shadowRoot.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      this._showError(`Export failed: ${err && err.message ? err.message : err}`);
    }
  }

  async _handleImportFile(file) {
    this._showError('');
    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch (err) {
      this._showError(`Import failed: file is not valid JSON (${err.message})`);
      return;
    }
    try {
      await this._hass.callService('abstractor', 'import_data', { data: parsed });
      this._showError('');
      this._fetchSubentries(true);
    } catch (err) {
      this._showError(`Import failed: ${err && err.message ? err.message : err}`);
    }
  }
}

customElements.define('abstractor-panel', AbstractorPanel);
