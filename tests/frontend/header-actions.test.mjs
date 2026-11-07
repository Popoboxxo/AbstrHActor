// WS-3.4: header affordance visibility is a pure predicate — non-admins get
// nothing, base admins only the edit-mode toggle, edit mode all of them.
import assert from 'node:assert';
import test from 'node:test';
import { visibleHeaderActions } from '../../frontend/src/sensor-form.js';

test('non-admin sees no write affordances', () => {
  assert.deepEqual(visibleHeaderActions(false, false), []);
  assert.deepEqual(visibleHeaderActions(false, true), []);
});

test('base mode admin only gets the edit-mode toggle', () => {
  assert.deepEqual(visibleHeaderActions(true, false), ['editToggle']);
});

test('edit mode admin unlocks the write affordances', () => {
  assert.deepEqual(
    visibleHeaderActions(true, true),
    ['editToggle', 'addSensor', 'export', 'import'],
  );
});
