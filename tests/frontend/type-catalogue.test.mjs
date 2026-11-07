import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEVICE_TYPES,
  buildPayload,
  getCatalogue,
  setCatalogue,
  validateSensorForm,
} from '../../frontend/src/sensor-form.js';

test('fallback catalogue is only a bootstrap, never a second registry', () => {
  assert.ok(DEVICE_TYPES.includes('switch_state'));
  assert.equal(DEVICE_TYPES.includes('riemann_energy'), false);
});

test('setCatalogue installs the server catalogue live in place', () => {
  const server = {
    device_types: ['power', 'energy', 'switch_state', 'cover_position'],
    numeric_types: ['power', 'energy'],
    aggregation_modes: ['sum', 'first_available'],
    display_names: { power: 'Power', switch_state: 'Switch', cover_position: 'Cover position' },
  };
  setCatalogue(server);
  assert.deepEqual([...DEVICE_TYPES], server.device_types);
  assert.deepEqual([...getCatalogue().numeric_types], server.numeric_types);

  const ok = validateSensorForm({ device_type: 'switch_state', sources: ['switch.a'] });
  assert.equal(ok.device_type, undefined);

  const payload = buildPayload({ device_type: 'switch_state', sources: ['switch.a'], aggregation: 'sum' });
  assert.equal('aggregation' in payload, false);
  const cover = buildPayload({ device_type: 'cover_position', sources: ['cover.c'] });
  assert.equal('spike_filter' in cover, false);

  const stale = validateSensorForm({ device_type: 'light_state', sources: ['light.l'] });
  assert.equal(stale.device_type, 'required');
});
