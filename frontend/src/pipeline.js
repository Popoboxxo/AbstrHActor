// Pure value-pipeline selector for the detail drawer (WS-4.4 / E6).
//
// Returns the ordered stages the coordinator applies for one subentry and
// whether each stage actually participates. The panel only paints this list —
// no raw subentry keys, no JSON.stringify.

const STAGES = [
  ['sources', 'drawer.stage.sources'],
  ['aggregation', 'drawer.stage.aggregation'],
  ['spike', 'drawer.stage.spike'],
  ['invert', 'drawer.stage.invert'],
  ['netSubtract', 'drawer.stage.netSubtract'],
  ['fallback', 'drawer.stage.fallback'],
  ['display', 'drawer.stage.display'],
];

const NUMERIC_TYPES = new Set(['power', 'energy', 'water']);

export function pipelineStages(row) {
  const r = row || {};
  const numeric = NUMERIC_TYPES.has(r.device_type);
  const sources = Array.isArray(r.source_entity_ids)
    ? r.source_entity_ids.filter(Boolean)
    : (r.source_entity_id ? [r.source_entity_id] : []);
  const active = {
    sources: sources.length > 0,
    aggregation: numeric && sources.length > 1,
    spike: numeric && !!r.spike_filter,
    invert: numeric && !!r.invert,
    netSubtract: numeric && !!r.net_subtract_entity_id,
    fallback: numeric && !!(
      r.fallback_source_entity_id
      || r.fallback_on_zero
      || r.fallback_zero
      || r.fallback_condition_entity_id
    ),
    display: true,
  };
  return STAGES.map(([id, labelKey]) => ({ id, labelKey, active: !!active[id] }));
}
