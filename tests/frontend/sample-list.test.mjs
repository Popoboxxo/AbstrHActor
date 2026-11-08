// WS-5.5: the Health tab's rejected-sample rows are built by a pure helper.
import test from 'node:test';
import assert from 'node:assert/strict';

import { sampleRows } from '../../frontend/src/sensor-form.js';

const rows = [
  { id: 'sub-1_1', at: '2026-11-08T10:00:00Z', value: 1234.5, reason: 'spike', voided: false },
  { id: 'sub-1_2', at: '2026-11-08T10:00:30Z', value: null, reason: 'unavailable', voided: true },
];

test('rows are actionable only for an admin in edit mode', () => {
  assert.equal(sampleRows(rows, false, true)[0].actionable, false);
  assert.equal(sampleRows(rows, true, false)[0].actionable, false);
  assert.equal(sampleRows(rows, true, true)[0].actionable, true);
});

test('missing raw values render as a question mark', () => {
  const mapped = sampleRows(rows, true, true);
  assert.equal(mapped[0].value, 1234.5);
  assert.equal(mapped[1].value, '?');
});

test('void state and reason are preserved verbatim', () => {
  const mapped = sampleRows(rows, true, true);
  assert.equal(mapped[1].voided, true);
  assert.equal(mapped[1].reason, 'unavailable');
  assert.deepEqual(mapped.map((row) => row.id), ['sub-1_1', 'sub-1_2']);
});

test('empty input yields an empty list', () => {
  assert.deepEqual(sampleRows(null, true, true), []);
});
