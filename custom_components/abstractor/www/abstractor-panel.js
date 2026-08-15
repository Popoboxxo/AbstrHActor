// abstractor-panel.js — Abstractor sidebar panel.
// Registers the <abstractor-panel> custom element. Read-only overview across
// all Abstractor devices; configuration itself stays on the standard HA
// Config Flow (Settings > Devices & Services) — this panel does not
// duplicate it. Dependency-free: no Lit, no build step, just the Web
// Components APIs Home Assistant's own frontend already relies on.
'use strict';

class AbstractorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._rendered = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  get hass() {
    return this._hass;
  }

  set narrow(_narrow) {
    this._render();
  }

  _abstractorDevices() {
    const hass = this._hass;
    if (!hass || !hass.devices || !hass.entities) return [];
    return Object.values(hass.devices)
      .filter((d) => d.identifiers.some((id) => id[0] === 'abstractor'))
      .map((device) => {
        const entities = Object.values(hass.entities)
          .filter((e) => e.device_id === device.id)
          .map((e) => {
            const state = hass.states[e.entity_id];
            return {
              entityId: e.entity_id,
              name: e.name || (state && state.attributes.friendly_name) || e.entity_id,
              value: state ? state.state : 'unknown',
              unit: (state && state.attributes.unit_of_measurement) || '',
            };
          });
        return {
          id: device.id,
          name: device.name_by_user || device.name,
          manufacturer: device.manufacturer || '',
          model: device.model || '',
          entities,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _styles() {
    return `
      :host { display: block; padding: 16px; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
      h1 { font-size: 1.5em; margin: 0 0 4px 0; color: var(--primary-text-color); }
      p.subtitle { color: var(--secondary-text-color); margin: 0 0 20px 0; }
      .empty { padding: 32px; text-align: center; color: var(--secondary-text-color); }
      .device-card {
        background: var(--card-background-color, white);
        border-radius: var(--ha-card-border-radius, 12px);
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
        padding: 16px; margin-bottom: 12px;
      }
      .device-card h2 { margin: 0 0 8px 0; font-size: 1.1em; color: var(--primary-text-color); }
      table { width: 100%; border-collapse: collapse; }
      td { padding: 4px 8px 4px 0; color: var(--primary-text-color); font-size: 0.95em; }
      td.value { text-align: right; font-weight: 500; }
      td.entity-id { color: var(--secondary-text-color); font-size: 0.85em; }
    `;
  }

  _render() {
    if (!this._hass) return;
    const devices = this._abstractorDevices();

    // Static shell (no user-controlled data) via innerHTML; every value that
    // originates from the HA registry/state (device/entity names, state
    // values) is inserted afterwards via textContent, never interpolated
    // into markup, so it can't be interpreted as HTML/script.
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <h1>Abstractor</h1>
      <p class="subtitle"></p>
      <div class="body"></div>
    `;

    this.shadowRoot.querySelector('.subtitle').textContent =
      `${devices.length} abstract device${devices.length === 1 ? '' : 's'} — ` +
      'read-only overview. Configure via Settings → Devices & Services.';

    const bodyEl = this.shadowRoot.querySelector('.body');
    if (!devices.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent =
        'No Abstractor devices yet. Add one via Settings → Devices & Services → Add Integration → Abstractor.';
      bodyEl.appendChild(empty);
      return;
    }

    for (const d of devices) {
      const card = document.createElement('div');
      card.className = 'device-card';

      const h2 = document.createElement('h2');
      h2.textContent = d.name;
      card.appendChild(h2);

      const details = document.createElement('p');
      details.textContent = [d.manufacturer, d.model].filter(Boolean).join(' · ');
      card.appendChild(details);

      const table = document.createElement('table');
      for (const e of d.entities) {
        const row = table.insertRow();
        row.insertCell().className = 'entity-id';
        row.cells[0].textContent = e.entityId;
        row.insertCell().className = 'value';
        row.cells[1].textContent = e.unit ? `${e.value} ${e.unit}` : e.value;
      }
      card.appendChild(table);
      bodyEl.appendChild(card);
    }
  }
}

customElements.define('abstractor-panel', AbstractorPanel);
