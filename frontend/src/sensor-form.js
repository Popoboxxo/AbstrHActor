// Pure form logic for the Abstractor panel's sensor create/edit dialogs.
//
// Deliberately DOM-free and websocket-free so it can be unit-tested with
// `node --test` (no browser, no build) and reused by the bundled panel.
// The panel owns rendering; this module owns the field -> payload contract
// and the client-side validation that mirrors the backend schema.

export const DEVICE_TYPES = ['power', 'energy', 'water', 'door_contact', 'motion', 'smoke'];
export const NUMERIC_TYPES = ['power', 'energy', 'water'];
export const AGGREGATION_MODES = ['sum', 'max', 'min', 'first_available'];

export function isNumericType(deviceType) {
  return NUMERIC_TYPES.indexOf(deviceType) !== -1;
}

export function isBinaryType(deviceType) {
  return DEVICE_TYPES.indexOf(deviceType) !== -1 && !isNumericType(deviceType);
}

const SLUG_RE = /^[a-z0-9_]+$/;

// Client-side validation. Returns a map of field -> message; empty means OK.
// The server remains authoritative (it re-runs the config-flow checks); this
// only gives fast feedback and avoids obviously-doomed round trips.
export function validateSensorForm(fields) {
  const errors = {};
  const f = fields || {};

  if (DEVICE_TYPES.indexOf(f.device_type) === -1) {
    errors.device_type = 'required';
  }

  const sources = (f.sources || []).map((s) => String(s || '').trim()).filter(Boolean);
  if (sources.length === 0) {
    errors.sources = 'at least one source entity is required';
  }

  if (f.object_id && !SLUG_RE.test(String(f.object_id))) {
    errors.object_id = 'object_id must be a lowercase slug ([a-z0-9_]+)';
  }

  const conditionState = f.fallback_condition_state;
  if (conditionState && !f.fallback_condition_entity_id) {
    errors.fallback_condition_entity_id = 'a condition entity is required when a condition state is set';
  }

  return errors;
}

export function hasErrors(errors) {
  return !!errors && Object.keys(errors).length > 0;
}

// Build the `data` payload for `abstractor/subentry/create` /
// `abstractor/subentry/update`. Optional entity/text fields are emitted as
// null when empty so the update path can clear a previously set value; the
// backend treats null/absent as "unset".
export function buildPayload(fields) {
  const f = fields || {};
  const sources = (f.sources || []).map((s) => String(s || '').trim()).filter(Boolean);

  const data = { device_type: f.device_type };

  if (sources.length > 1) {
    data.source_entity_ids = sources;
  } else if (sources.length === 1) {
    data.source_entity_id = sources[0];
  }

  data.logical_name = f.logical_name ? String(f.logical_name).trim() : '';
  data.object_id = f.object_id ? String(f.object_id).trim() : null;
  if (f.legacy_unique_id) {
    data.legacy_unique_id = String(f.legacy_unique_id).trim();
  }

  if (isNumericType(f.device_type)) {
    data.aggregation = AGGREGATION_MODES.indexOf(f.aggregation) !== -1 ? f.aggregation : 'sum';
    data.spike_filter = !!f.spike_filter;
    data.invert = !!f.invert;
    data.fallback_zero = !!f.fallback_zero;
    data.fallback_on_zero = !!f.fallback_on_zero;
    data.net_subtract_entity_id = f.net_subtract_entity_id || null;
    data.fallback_source_entity_id = f.fallback_source_entity_id || null;
    data.fallback_condition_entity_id = f.fallback_condition_entity_id || null;
    data.fallback_condition_state = f.fallback_condition_state
      ? String(f.fallback_condition_state).trim()
      : null;
  }

  return data;
}

// Map a subentry (as returned by `abstractor/subentries`) back to form fields
// so the edit dialog can be pre-filled.
export function subentryToFields(subentry) {
  const s = subentry || {};
  const sources = Array.isArray(s.source_entity_ids)
    ? s.source_entity_ids.filter(Boolean)
    : [];
  return {
    device_type: s.device_type || 'power',
    sources,
    logical_name: s.logical_name || '',
    object_id: s.object_id || '',
    aggregation: s.aggregation || 'sum',
    spike_filter: !!s.spike_filter,
    invert: !!s.invert,
    fallback_zero: !!s.fallback_zero,
    fallback_on_zero: !!s.fallback_on_zero,
    net_subtract_entity_id: s.net_subtract_entity_id || '',
    fallback_source_entity_id: s.fallback_source_entity_id || '',
    fallback_condition_entity_id: s.fallback_condition_entity_id || '',
    fallback_condition_state: s.fallback_condition_state || '',
  };
}
