// WS-4.5: the store only bumps its revision for real changes.
import test from 'node:test';
import assert from 'node:assert/strict';

import { AbstractorStore, sameState } from '../../frontend/src/store.js';

test('identical patches are a no-op (no revision, no notification)', () => {
  const store = new AbstractorStore({ subentries: [{ subentry_id: 'a', value: 1 }], loading: false });
  let calls = 0;
  store.subscribe(() => { calls += 1; });
  const initialRevision = store.revision;

  assert.equal(store.setState({ subentries: [{ subentry_id: 'a', value: 1 }], loading: false }), false);
  assert.equal(store.revision, initialRevision);
  assert.equal(calls, 0);
});

test('a real change bumps the revision and notifies subscribers', () => {
  const store = new AbstractorStore({ subentries: [{ subentry_id: 'a', value: 1 }] });
  let received = null;
  store.subscribe((state) => { received = state; });

  assert.equal(store.setState({ subentries: [{ subentry_id: 'a', value: 2 }] }), true);
  assert.equal(store.revision, 1);
  assert.equal(received.subentries[0].value, 2);
  assert.equal(store.shouldRender(0), true);
  assert.equal(store.shouldRender(1), false);
});

test('unsubscribe removes the subscriber without resetting state', () => {
  const store = new AbstractorStore();
  let calls = 0;
  const unsubscribe = store.subscribe(() => { calls += 1; });
  store.setState({ loaded: true });
  unsubscribe();
  store.setState({ loading: true });
  assert.equal(calls, 1);
  assert.equal(store.state.loaded, true);
  assert.equal(store.state.loading, true);
});

test('sameState compares nested arrays/objects by value', () => {
  assert.equal(sameState({ a: [1, { b: 2 }] }, { a: [1, { b: 2 }] }), true);
  assert.equal(sameState({ a: [1, { b: 2 }] }, { a: [1, { b: 3 }] }), false);
  assert.equal(sameState({ a: 1 }, { a: 1, b: undefined }), false);
});

test('the store does not expose a writable state setter', () => {
  const store = new AbstractorStore();
  assert.throws(() => {
    'use strict';
    store.state = { hacked: true };
  }, TypeError);
});
