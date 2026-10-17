import test from 'node:test';
import assert from 'node:assert/strict';

import {
  AGGREGATION_MODES,
  DEVICE_TYPES,
  buildPayload,
  buildRenamePayload,
  hasErrors,
  isBinaryType,
  isNumericType,
  previewEntityId,
  subentryToFields,
  subentryToRenameFields,
  validateRenameForm,
  validateSensorForm,
} from '../../frontend/src/sensor-form.js';

test('type helpers classify numeric vs binary', () => {
  assert.equal(isNumericType('power'), true);
  assert.equal(isNumericType('water'), true);
  assert.equal(isNumericType('door_contact'), false);
  assert.equal(isBinaryType('motion'), true);
  assert.equal(isBinaryType('power'), false);
  assert.deepEqual(AGGREGATION_MODES, ['sum', 'max', 'min', 'first_available']);
  assert.ok(DEVICE_TYPES.includes('smoke'));
});

test('validateSensorForm requires a type and at least one source', () => {
  assert.deepEqual(validateSensorForm({}), {
    device_type: 'required',
    sources: 'at least one source entity is required',
  });
  assert.equal(hasErrors(validateSensorForm({})), true);
  assert.equal(hasErrors(validateSensorForm({ device_type: 'power', sources: ['sensor.a'] })), false);
});

test('validateSensorForm couples condition state to a condition entity', () => {
  const errors = validateSensorForm({
    device_type: 'power',
    sources: ['sensor.a'],
    fallback_condition_state: 'on',
  });
  assert.ok(errors.fallback_condition_entity_id);
});

test('validateRenameForm requires a logical name and a slug object_id', () => {
  assert.ok(validateRenameForm({}).logical_name);
  assert.ok(validateRenameForm({ logical_name: 'N', object_id: 'Bad Slug' }).object_id);
  assert.equal(hasErrors(validateRenameForm({ logical_name: 'Kitchen', object_id: 'kitchen' })), false);
  assert.equal(hasErrors(validateRenameForm({ logical_name: 'Kitchen' })), false);
});

test('buildRenamePayload trims the name and only includes object_id when set', () => {
  assert.deepEqual(buildRenamePayload({ logical_name: '  Kitchen  ', rename_entity: true }), {
    logical_name: 'Kitchen',
    rename_entity: true,
  });
  assert.deepEqual(buildRenamePayload({ logical_name: 'Kitchen', object_id: 'kitchen' }), {
    logical_name: 'Kitchen',
    rename_entity: false,
    object_id: 'kitchen',
  });
});

test('buildPayload: single source uses source_entity_id, multi uses source_entity_ids', () => {
  const single = buildPayload({ device_type: 'power', sources: ['sensor.a'] });
  assert.equal(single.source_entity_id, 'sensor.a');
  assert.equal('source_entity_ids' in single, false);

  const multi = buildPayload({ device_type: 'power', sources: ['sensor.b', 'sensor.a', ''] });
  assert.deepEqual(multi.source_entity_ids, ['sensor.b', 'sensor.a']);
  assert.equal('source_entity_id' in multi, false);
});

test('buildPayload: numeric type carries full pipeline, binary type does not', () => {
  const numeric = buildPayload({
    device_type: 'energy',
    sources: ['sensor.e'],
    aggregation: 'max',
    spike_filter: true,
    invert: true,
    fallback_zero: true,
    fallback_on_zero: true,
    net_subtract_entity_id: 'sensor.net',
  });
  assert.equal(numeric.aggregation, 'max');
  assert.equal(numeric.spike_filter, true);
  assert.equal(numeric.invert, true);
  assert.equal(numeric.fallback_zero, true);
  assert.equal(numeric.fallback_on_zero, true);
  assert.equal(numeric.net_subtract_entity_id, 'sensor.net');

  const binary = buildPayload({ device_type: 'door_contact', sources: ['binary_sensor.door'] });
  assert.equal('aggregation' in binary, false);
  assert.equal('spike_filter' in binary, false);
  assert.equal('net_subtract_entity_id' in binary, false);
});

test('buildPayload: invalid aggregation falls back to sum; empty optionals become null', () => {
  const data = buildPayload({
    device_type: 'power',
    sources: ['sensor.a'],
    aggregation: 'bogus',
    net_subtract_entity_id: '',
    fallback_condition_state: '',
  });
  assert.equal(data.aggregation, 'sum');
  assert.equal(data.net_subtract_entity_id, null);
  assert.equal(data.fallback_condition_state, null);
});

test('buildPayload never owns logical identity', () => {
  const data = buildPayload({ device_type: 'power', sources: ['sensor.a'], logical_name: 'X', object_id: 'x' });
  assert.equal('logical_name' in data, false);
  assert.equal('object_id' in data, false);
});

test('subentryToFields pre-fills config fields only', () => {
  const fields = subentryToFields({
    device_type: 'water',
    source_entity_ids: ['sensor.w1', 'sensor.w2'],
    logical_name: 'Tank',
    object_id: 'tank',
    aggregation: 'min',
    spike_filter: true,
  });
  assert.equal(fields.device_type, 'water');
  assert.deepEqual(fields.sources, ['sensor.w1', 'sensor.w2']);
  assert.equal(fields.aggregation, 'min');
  assert.equal(fields.spike_filter, true);
  assert.equal(fields.net_subtract_entity_id, '');
  assert.equal('logical_name' in fields, false);
  assert.equal('object_id' in fields, false);
});

test('previewEntityId keeps the current domain and validates the slug', () => {
  assert.equal(previewEntityId({ object_id: 'kitchen_power' }, 'sensor.old'), 'sensor.kitchen_power');
  assert.equal(previewEntityId({ object_id: 'kitchen' }, 'switch.old'), 'switch.kitchen');
  assert.equal(previewEntityId({ object_id: 'kitchen' }, undefined), 'sensor.kitchen');
  assert.equal(previewEntityId({ object_id: 'Bad Slug' }, 'sensor.old'), '');
  assert.equal(previewEntityId({ object_id: '' }, 'sensor.old'), '');
  assert.equal(previewEntityId({}, 'sensor.old'), '');
});

test('subentryToRenameFields pre-fills name and object id', () => {
  const fields = subentryToRenameFields({ logical_name: 'Tank', object_id: 'tank' });
  assert.deepEqual(fields, { logical_name: 'Tank', object_id: 'tank', rename_entity: false });
});
