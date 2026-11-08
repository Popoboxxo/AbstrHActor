// WS-6.4: pure response formatters for the service buttons.
import test from 'node:test';
import assert from 'node:assert/strict';

import { importSummary, summaryCard } from '../../frontend/src/sensor-form.js';

test('importSummary reports all four flat-contract buckets', () => {
  const rows = importSummary({
    recreated: ['a', 'b'],
    kept: ['c'],
    skipped: [],
    errors: ['boom'],
  });
  assert.deepEqual(rows.map((row) => [row.labelKey, row.count]), [
    ['import.recreated', 2],
    ['import.kept', 1],
    ['import.skipped', 0],
    ['import.errors', 1],
  ]);
});

test('importSummary tolerates a partial/empty response', () => {
  const rows = importSummary({});
  assert.equal(rows.length, 4);
  assert.ok(rows.every((row) => row.count === 0 && Array.isArray(row.values)));
});

test('summaryCard keeps the documented sensor fields and drops extras', () => {
  const card = summaryCard({
    generated_at: '2026-11-08T12:00:00Z',
    window_days: 7,
    sensors: [
      {
        logical_name: 'Grid power',
        entity_id: 'sensor.grid_power',
        device_type: 'power',
        value: 42.5,
        unit: 'W',
        updated_at: '2026-11-08T11:59:00Z',
        min: 10,
        max: 100,
        avg: 50.83,
        spike_rejections: 2,
        fallbacks: 1,
        health: 'ok',
        private_field: 'never rendered',
      },
    ],
  });
  assert.equal(card.window_days, 7);
  assert.equal(card.rows.length, 1);
  const row = card.rows[0];
  assert.deepEqual(Object.keys(row).sort(), [
    'avg',
    'device_type',
    'entity_id',
    'fallbacks',
    'health',
    'logical_name',
    'max',
    'min',
    'spike_rejections',
    'unit',
    'updated_at',
    'value',
  ]);
  assert.equal(row.private_field, undefined);
});

test('summaryCard handles an empty/absent payload', () => {
  assert.deepEqual(summaryCard(undefined), { generated_at: '', window_days: undefined, rows: [] });
});
