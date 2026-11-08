// UF-12/WS-4.6: both dictionaries carry the same vocabulary and German keeps
// its umlauts (nothing is transliterated to ae/oe/ue/ss).
import test from 'node:test';
import assert from 'node:assert/strict';

import { I18N, langFor, translate } from '../../frontend/src/i18n.js';

test('English and German define exactly the same keys', () => {
  const en = Object.keys(I18N.en).sort();
  const de = Object.keys(I18N.de).sort();
  assert.deepEqual(de, en);
});

test('German labels keep their umlauts', () => {
  assert.equal(I18N.de['tab.devices'], 'Geräte');
  assert.equal(I18N.de['action.delete'], 'Löschen');
  assert.equal(I18N.de['action.close'], 'Schließen');
  assert.equal(I18N.de['status.loading'], 'Lädt...');
  assert.equal(I18N.de['confirm.delete'], 'Diesen Abstract-Sensor wirklich löschen?');
  for (const value of Object.values(I18N.de)) {
    assert.doesNotMatch(value, /(Gerae|Loesch|Schliessen|Laedt)/, `stripped umlaut in: ${value}`);
  }
});

test('unknown language and unknown key fall back to English', () => {
  assert.equal(langFor({ language: 'fr' }), 'en');
  assert.equal(langFor({ language: 'de-DE' }), 'de');
  assert.equal(translate({ language: 'fr' }, 'title'), 'Abstractor');
  assert.equal(translate({ language: 'en' }, 'does.not.exist'), 'does.not.exist');
});
