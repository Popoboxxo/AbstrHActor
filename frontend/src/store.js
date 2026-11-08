// Minimal external store for the Abstractor panel.
//
// The panel renders only when the store *revision* changes. Subscription
// pings that carry an identical payload therefore cost one deep comparison
// instead of a full shadow-DOM rebuild (UF-10 / WS-4.5). Kept DOM-free so the
// revision/subscriber contract is unit-testable with `node --test`.

export const INITIAL_STATE = {
  subentries: [],
  loaded: false,
  loading: false,
  error: '',
  activeTab: 'devices',
  lastFetchAt: 0,
  editMode: false,
  admin: false,
};

function _sameValue(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((value, index) => _sameValue(value, b[index]));
  }
  if (a && b && typeof a === 'object') {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) return false;
    return aKeys.every(
      (key) => Object.prototype.hasOwnProperty.call(b, key) && _sameValue(a[key], b[key]),
    );
  }
  return false;
}

export function sameState(a, b) {
  const aState = a || {};
  const bState = b || {};
  const aKeys = Object.keys(aState);
  const bKeys = Object.keys(bState);
  if (aKeys.length !== bKeys.length) return false;
  for (const key of aKeys) {
    if (!Object.prototype.hasOwnProperty.call(bState, key)) return false;
    if (!_sameValue(aState[key], bState[key])) return false;
  }
  return true;
}

export class AbstractorStore {
  constructor(initial) {
    this._state = Object.assign({}, INITIAL_STATE, initial || {});
    this.subscribers = new Set();
    this.revision = 0;
  }

  get state() {
    return this._state;
  }

  subscribe(fn) {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

  /**
   * Merge a patch into the state. Returns true when the state actually
   * changed (and subscribers were notified); identical patches are a no-op.
   */
  setState(patch) {
    const next = Object.assign({}, this._state, patch || {});
    if (sameState(this._state, next)) return false;
    this._state = next;
    this.revision += 1;
    this.subscribers.forEach((fn) => fn(this._state));
    return true;
  }

  /** Render decision: a revision that was already painted must not repaint. */
  shouldRender(lastRevision) {
    return this.revision !== lastRevision;
  }
}
