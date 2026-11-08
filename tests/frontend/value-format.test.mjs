// WS-4.3: pure value formatters shared by the panel and these tests.
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  deltaWithSign,
  formatValue,
  relativeTime,
  sparklinePath,
} from '../../frontend/src/sensor-form.js';

test('formatValue renders unavailable values as an em dash', () => {
  assert.equal(formatValue({ value: null }), '—');
  assert.equal(formatValue({ value: undefined }), '—');
});

test('formatValue honours display precision and unit precedence', () => {
  assert.equal(formatValue({ value: 12.3456, display_precision: 2, unit: 'kWh' }), '12.35 kWh');
  assert.equal(formatValue({ value: 12.3456, display_unit: 'MWh', unit: 'kWh' }), '12.3456 MWh');
  assert.equal(formatValue({ value: 3, precision: 2 }), '3');
});

test('formatValue passes non-numeric states through untouched', () => {
  assert.equal(formatValue({ value: 'unavailable' }), 'unavailable');
  assert.equal(formatValue({ value: 'on' }), 'on');
  assert.equal(formatValue({ value: Number.NaN }), 'NaN');
});

test('deltaWithSign is null when either sample is not numeric', () => {
  assert.equal(deltaWithSign(10, null), null);
  assert.equal(deltaWithSign('10', 5), null);
  assert.equal(deltaWithSign(10, 5), '+5');
  assert.equal(deltaWithSign(5, 10), '-5');
  assert.equal(deltaWithSign(5, 5), '0');
  assert.equal(deltaWithSign(5.01, 5), '+0.01');
});

test('relativeTime is deterministic for a fixed reference', () => {
  const now = Date.parse('2026-11-08T12:00:00Z');
  assert.equal(relativeTime('2026-11-08T11:59:58Z', now), 'just now');
  assert.equal(relativeTime('2026-11-08T11:59:30Z', now), '30s ago');
  assert.equal(relativeTime('2026-11-08T11:55:00Z', now), '5m ago');
  assert.equal(relativeTime('2026-11-08T09:00:00Z', now), '3h ago');
  assert.equal(relativeTime('2026-11-06T12:00:00Z', now), '2d ago');
  assert.equal(relativeTime('', now), '');
  assert.equal(relativeTime('not-a-date', now), '');
});

test('sparklinePath needs two finite numeric samples', () => {
  assert.equal(sparklinePath([], 120, 26), null);
  assert.equal(sparklinePath([1], 120, 26), null);
  assert.equal(sparklinePath(['unavailable', 'unknown'], 120, 26), null);
  assert.equal(sparklinePath([null, undefined, Number.NaN], 120, 26), null);
});

test('sparklinePath maps the numeric window to viewBox coordinates', () => {
  const points = sparklinePath([0, 5, 10], 100, 20);
  const pairs = points.split(' ');
  assert.equal(pairs.length, 3);
  assert.equal(pairs[0], '0.0,18.0');
  assert.equal(pairs[1], '50.0,10.0');
  assert.equal(pairs[2], '100.0,2.0');
  // Non-numeric samples are skipped, not zero-filled.
  assert.equal(sparklinePath([0, 'unknown', 10], 100, 20).split(' ').length, 2);
});
