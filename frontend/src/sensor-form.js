// Pure form logic for the Abstractor panel's sensor create/edit and rename
// dialogs.
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

// Client-side validation for the config form (device type, sources, numeric
// pipeline). Returns a map of field -> message; empty means OK. The server
// remains authoritative; this only gives fast feedback.
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

  const conditionState = f.fallback_condition_state;
  if (conditionState && !f.fallback_condition_entity_id) {
    errors.fallback_condition_entity_id = 'a condition entity is required when a condition state is set';
  }

  return errors;
}

// Client-side validation for the rename dialog (logical name + object id).
export function validateRenameForm(fields) {
  const errors = {};
  const f = fields || {};

  if (!f.logical_name || !String(f.logical_name).trim()) {
    errors.logical_name = 'a logical name is required';
  }
  if (f.object_id && !SLUG_RE.test(String(f.object_id))) {
    errors.object_id = 'object_id must be a lowercase slug ([a-z0-9_]+)';
  }

  return errors;
}

export function hasErrors(errors) {
  return !!errors && Object.keys(errors).length > 0;
}

// Build the `data` payload for `abstractor/subentry/create` /
// `abstractor/subentry/update`. Optional entity/text fields are emitted as
// null when empty so the update path can clear a previously set value; the
// backend treats null/absent as "unset". Logical identity (name/object_id) is
// owned by the rename command, not this payload.
export function buildPayload(fields) {
  const f = fields || {};
  const sources = (f.sources || []).map((s) => String(s || '').trim()).filter(Boolean);

  const data = { device_type: f.device_type };

  if (sources.length > 1) {
    data.source_entity_ids = sources;
  } else if (sources.length === 1) {
    data.source_entity_id = sources[0];
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

// Build the payload for `abstractor/logical_rename`.
export function buildRenamePayload(fields) {
  const f = fields || {};
  const data = {
    logical_name: String(f.logical_name || '').trim(),
    rename_entity: !!f.rename_entity,
  };
  if (f.object_id) {
    data.object_id = String(f.object_id).trim();
  }
  return data;
}

// Map a subentry (as returned by `abstractor/subentries`) back to config-form
// fields so the edit dialog can be pre-filled.
export function subentryToFields(subentry) {
  const s = subentry || {};
  const sources = Array.isArray(s.source_entity_ids)
    ? s.source_entity_ids.filter(Boolean)
    : [];
  return {
    device_type: s.device_type || 'power',
    sources,
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

// Map a subentry back to rename-form fields.
export function subentryToRenameFields(subentry) {
  const s = subentry || {};
  return {
    logical_name: s.logical_name || '',
    object_id: s.object_id || '',
    rename_entity: false,
  };
}
