// WS-4.4: the drawer pipeline selector is pure — no DOM, no raw subentry keys.
import test from 'node:test';
import assert from 'node:assert/strict';

import { pipelineStages } from '../../frontend/src/pipeline.js';

const ids = (stages) => stages.filter((stage) => stage.active).map((stage) => stage.id);

test('multi-source numeric row activates aggregation and its transforms', () => {
  const stages = pipelineStages({
    device_type: 'power',
    source_entity_ids: ['sensor.a', 'sensor.b'],
    spike_filter: true,
    invert: true,
    net_subtract_entity_id: 'sensor.grid',
    fallback_source_entity_id: 'sensor.backup',
  });
  assert.deepEqual(ids(stages), [
    'sources',
    'aggregation',
    'spike',
    'invert',
    'netSubtract',
    'fallback',
    'display',
  ]);
  assert.deepEqual(stages.map((stage) => stage.id), ['sources', 'aggregation', 'spike', 'invert', 'netSubtract', 'fallback', 'display']);
  assert.ok(stages.every((stage) => typeof stage.labelKey === 'string'));
});

test('single-source numeric row hides aggregation, spike and fallback', () => {
  const stages = pipelineStages({ device_type: 'energy', source_entity_ids: ['sensor.a'] });
  assert.deepEqual(ids(stages), ['sources', 'display']);
});

test('pass-through rows never claim numeric stages', () => {
  const stages = pipelineStages({
    device_type: 'switch_state',
    source_entity_ids: ['switch.a'],
    spike_filter: true,
    invert: true,
  });
  assert.deepEqual(ids(stages), ['sources', 'display']);
});

test('fallback_zero and fallback_on_zero both activate the fallback stage', () => {
  assert.ok(ids(pipelineStages({ device_type: 'water', source_entity_ids: ['sensor.a'], fallback_zero: true })).includes('fallback'));
  assert.ok(ids(pipelineStages({ device_type: 'water', source_entity_ids: ['sensor.a'], fallback_on_zero: true })).includes('fallback'));
});

test('empty rows still expose the ordered stage list with display only', () => {
  const stages = pipelineStages({});
  assert.deepEqual(ids(stages), ['display']);
});
