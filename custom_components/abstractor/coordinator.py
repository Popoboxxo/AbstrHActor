"""DataUpdateCoordinator for Abstractor."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    AGGREGATION_SUM,
    CONF_AGGREGATION,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_UPDATE_MODE,
    CONF_WARN_ABOVE,
    CONF_WARN_BELOW,
    CONF_WARN_CONDITION_ENTITY_ID,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SUBENTRY_POLL_INTERVAL,
    DOMAIN,
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    REJECTED_RING_LIMIT,
    UPDATE_MODE_EVENT,
    UPDATE_MODE_POLLING,
    VALUE_HISTORY_LIMIT,
)
from .filters import AbstractorFilterPipeline
from .specs import SPEC_REGISTRY

_LOGGER = logging.getLogger(__name__)

# Distinguishes "this subentry has no source configured" (leave it out of the
# data dict) from a genuine `None` value (source unavailable / rejected).
_NO_SOURCE = object()


def _numeric_delta(current, previous) -> float | None:
    """current - previous if both are real numbers (bools excluded), else None.

    Pure helper (WS-4 UF-07): feeds the panel's delta display; pass-through
    string states simply yield None.
    """

    def _as_number(value):
        if isinstance(value, bool):
            return None
        return float(value) if isinstance(value, (int, float)) else None

    current_number = _as_number(current)
    previous_number = _as_number(previous)
    if current_number is None or previous_number is None:
        return None
    return current_number - previous_number


@dataclass
class SubentryMeta:
    """Runtime-only health metadata for a single subentry (never persisted).

    ``updated_at``/``delta`` close the UF-07 read gap (the panel could show
    neither freshness nor change); ``stale`` (previously a dead field) now
    actually marks polls that delivered no value.
    """

    last_event: str | None = None
    event_at: datetime | None = None
    spike_rejections: int = 0
    fallbacks: int = 0
    unavailable_samples: int = 0
    source_states: dict[str, str] = field(default_factory=dict)
    stale: bool = False
    updated_at: datetime | None = None
    previous_value: float | str | None = None
    delta: float | None = None
    warn_hit: bool = False


class AbstractorDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Abstractor data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize.

        `config_entry=None` is passed explicitly (instead of leaving it
        undefined) to opt this coordinator OUT of HA's own automatic
        "shut down when the current config entry unloads" behaviour
        (`DataUpdateCoordinator.__init__` registers `self.async_shutdown` via
        `config_entry.async_on_unload` for whichever entry the ContextVar
        `config_entries.current_entry` resolves to at construction time —
        here, the singleton root entry, since this is instantiated from
        inside its own async_setup_entry).

        This coordinator's shutdown is managed manually by __init__.py's
        async_unload_entry instead, gated on `coordinator.subentry_data`
        being empty: a plain reconfigure/subentry-add/-remove reload also
        unloads and re-sets-up the SAME (singleton) entry, and the
        coordinator is meant to survive that — only a full domain teardown
        (see async_unload_entry) should actually shut it down. Leaving
        `config_entry` undefined would shut it down via HA's own hook on
        EVERY such reload regardless of that check, permanently — the base
        class's `_async_refresh` silently no-ops forever once
        `_shutdown_requested` is set, so every subentry's data would go
        stale after the very first reload of any kind.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=None,
            name=DOMAIN,
            # No global polling timer: every sensor owns its update trigger
            # (event subscription or per-sensor timer). The initial full
            # refresh is still driven explicitly by __init__.py.
            update_interval=None,
        )
        self.legacy_poll_interval = DEFAULT_POLL_INTERVAL
        self._trigger_unsubs: dict[str, Callable[[], None]] = {}
        self._pending_refreshes: set[str] = set()
        self._update_lock = asyncio.Lock()
        self.subentry_data: dict[str, dict] = {}
        self.pipelines: dict[str, AbstractorFilterPipeline] = {}
        self.meta: dict[str, SubentryMeta] = {}
        self.influx_exporter = None
        self._last_notified_events: dict[str, str] = {}
        # WS-5 sample control: the rejected-sample ring makes the spike filter
        # auditable (which raw value dropped, why); void_sample_ids marks
        # ring entries the user declared expected (persisted in root options,
        # applied on setup by __init__.py).
        self.rejected_samples: dict[str, list[dict]] = {}
        self._ring_seq: dict[str, int] = {}
        self.void_sample_ids: set[str] = set()
        # WS-6: bounded (ts, value) windows feeding the summary service — the
        # newest VALUE_HISTORY_LIMIT accepted samples per subentry, the single
        # source of min/max/avg aggregates (recorder internals are not read).
        self.value_history: dict[str, list[tuple[datetime, Any]]] = {}
        # Debug notification targets, applied from the root entry's options on
        # every setup (see __init__.py). Both None = the debug notify path is
        # silently off; nothing here may fail when the referenced entities do
        # not exist.
        self.debug_switch_entity_id: str | None = None
        self.notify_entity_id: str | None = None

    def _sources_for(self, config: dict[str, Any]) -> list[str]:
        """Return the configured source entity ids (multi-source or single)."""
        source_ids = config.get(CONF_SOURCE_ENTITY_IDS) or [
            config.get(CONF_SOURCE_ENTITY_ID)
        ]
        return [source_id for source_id in source_ids if source_id]

    def _update_mode_for(self, config: dict[str, Any]) -> str:
        """Resolve a subentry's update mode, defaulting legacy ones to polling."""
        configured = config.get(CONF_UPDATE_MODE)
        if configured in (UPDATE_MODE_EVENT, UPDATE_MODE_POLLING):
            return configured
        return UPDATE_MODE_POLLING

    def _interval_for(self, config: dict[str, Any]) -> int:
        """Resolve a polling subentry's interval in seconds, bounded."""
        raw = config.get(
            CONF_POLL_INTERVAL,
            getattr(self, "legacy_poll_interval", DEFAULT_POLL_INTERVAL),
        )
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = DEFAULT_SUBENTRY_POLL_INTERVAL
        return min(max(value, POLL_INTERVAL_MIN), POLL_INTERVAL_MAX)

    def _get_lock(self) -> asyncio.Lock:
        """Lazy lock: unit tests build coordinators via ``object.__new__``."""
        lock = getattr(self, "_update_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._update_lock = lock
        return lock

    @callback
    def _queue_refresh(self, subentry_id: str) -> None:
        """Coalesce bursts of triggers for the same sensor into one refresh."""
        pending = getattr(self, "_pending_refreshes", None)
        if pending is None:
            pending = self._pending_refreshes = set()
        if subentry_id in pending:
            return
        pending.add(subentry_id)
        self.hass.async_create_task(self._async_refresh_queued(subentry_id))

    async def _async_refresh_queued(self, subentry_id: str) -> None:
        try:
            await self.async_refresh_subentry(subentry_id)
        finally:
            getattr(self, "_pending_refreshes", set()).discard(subentry_id)

    def _reset_trigger(self, subentry_id: str) -> None:
        """Unsubscribe this sensor's previous trigger, if any."""
        unsubs = getattr(self, "_trigger_unsubs", None)
        if unsubs is None:
            unsubs = self._trigger_unsubs = {}
        unsubscribe = unsubs.pop(subentry_id, None)
        if unsubscribe is not None:
            unsubscribe()

    def _setup_trigger(self, subentry_id: str, config: dict[str, Any]) -> None:
        """Register the sensor's event subscription or its own polling timer."""
        self._reset_trigger(subentry_id)
        sources = self._sources_for(config)
        if not sources:
            return

        @callback
        def _trigger(event: Any = None) -> None:
            if event is not None:
                # HA also fires state-changed events for attribute-only updates;
                # those cannot change the forwarded value, so ignore them.
                old_state = event.data.get("old_state")
                new_state = event.data.get("new_state")
                if (
                    old_state is not None
                    and new_state is not None
                    and old_state.state == new_state.state
                ):
                    return
            self._queue_refresh(subentry_id)

        mode = self._update_mode_for(config)
        try:
            if mode == UPDATE_MODE_EVENT:
                unsubscribe = async_track_state_change_event(
                    self.hass, sources, _trigger
                )
            else:
                unsubscribe = async_track_time_interval(
                    self.hass,
                    _trigger,
                    timedelta(seconds=self._interval_for(config)),
                )
        except Exception:
            # A broken trigger must never take down the whole integration;
            # explicit per-sensor updates simply stop until the next reload.
            _LOGGER.exception(
                "Could not register %s update trigger for subentry %s",
                mode,
                subentry_id,
            )
            return
        self._trigger_unsubs[subentry_id] = unsubscribe

    async def async_refresh_subentry(self, subentry_id: str) -> None:
        """Recompute one sensor and push it to its entities and the panel.

        This is the event/timer path: unlike the full ``async_refresh``, it
        touches only the triggered sensor's cached value but notifies all
        listeners so the UI and recorder see the new state immediately.
        """
        config = self.subentry_data.get(subentry_id)
        if config is None:
            return
        async with self._get_lock():
            value = await self._compute_subentry(subentry_id, config)
            if value is _NO_SOURCE:
                return
            updated = dict(self.data or {})
            updated[subentry_id] = value
            self.async_set_updated_data(updated)

    def add_subentry(
        self,
        subentry_id: str,
        subentry_data: dict,
        initial_last_valid_state: float | None = None,
    ) -> None:
        """Add a subentry to central polling.

        ``initial_last_valid_state`` seeds the new pipeline's spike-filter
        guard, typically from the last value persisted in the snapshot Store
        (see __init__.py). Without it, a coordinator rebuild — which happens
        on every reload, including one triggered by editing an unrelated
        subentry — would otherwise let one unguarded low reading through on
        the very next poll (REQ-COMP-001).
        """
        config = dict(subentry_data)
        if not config.get("device_type"):
            _LOGGER.warning(
                "Subentry %s has no device_type configured; defaulting to "
                "'power' for polling",
                subentry_id,
            )
            config["device_type"] = "power"
        # Subentries stored before aggregation modes existed (B2) carry no
        # mode; every pipeline config gets an explicit one so the filter
        # pipeline never has to guess. The pipeline still defends itself
        # against a missing/invalid key when constructed directly.
        config.setdefault(CONF_AGGREGATION, AGGREGATION_SUM)
        self.subentry_data[subentry_id] = config
        # Re-registering on every reload (add/remove of any sensor triggers a
        # root-entry reload) is safe: _setup_trigger first removes the old
        # listener for this subentry, so no duplicate timers accumulate.
        self._setup_trigger(subentry_id, config)
        # A sensor added after startup would otherwise stay empty until its
        # first source event / timer tick. Ask for one immediate update; on a
        # fresh setup this duplicates the initial full refresh harmlessly.
        if isinstance(self.hass, HomeAssistant):
            self._queue_refresh(subentry_id)
        spec = SPEC_REGISTRY.try_get(config.get("device_type", "power"))
        if spec is not None and spec.numeric:
            self.pipelines[subentry_id] = AbstractorFilterPipeline(
                config, initial_last_valid_state
            )
        else:
            self.pipelines.pop(subentry_id, None)
        self.meta.setdefault(subentry_id, SubentryMeta())

    def remove_subentry(self, subentry_id: str) -> None:
        """Remove a subentry and unsubscribe its update trigger."""
        self._reset_trigger(subentry_id)
        self.subentry_data.pop(subentry_id, None)
        self.pipelines.pop(subentry_id, None)
        self.meta.pop(subentry_id, None)
        self._last_notified_events.pop(subentry_id, None)
        self.rejected_samples.pop(subentry_id, None)
        self._ring_seq.pop(subentry_id, None)
        self.value_history.pop(subentry_id, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Read every sensor once (startup / explicit full refresh only)."""
        data: dict[str, float | str | None] = {}
        async with self._get_lock():
            for subentry_id, config in list(self.subentry_data.items()):
                value = await self._compute_subentry(subentry_id, config)
                if value is not _NO_SOURCE:
                    data[subentry_id] = value
        return data

    async def _compute_subentry(
        self, subentry_id: str, config: dict[str, Any]
    ) -> float | str | None:
        """Compute and cache one subentry's value.

        Shared by the initial full refresh and the per-sensor event/timer path
        so both produce identical data and metadata for a given source state.
        """
        source_ids = self._sources_for(config)
        if not source_ids:
            return _NO_SOURCE

        raw_states = [
            (
                state_obj.state
                if (state_obj := self.hass.states.get(source_id))
                else None
            )
            for source_id in source_ids
        ]

        pipeline = self.pipelines.get(subentry_id)
        if pipeline is None:
            # Pass-through spec (binary sensor / switch / cover): forward the
            # raw source state string unchanged.
            primary = source_ids[0]
            raw_val = self._read_state(primary)
            self._record_value_sample(subentry_id, raw_val)
            await self._async_notify_debug(subentry_id, None)
            previous = self.meta.get(subentry_id, SubentryMeta())
            self.meta[subentry_id] = SubentryMeta(
                last_event=previous.last_event,
                event_at=previous.event_at,
                spike_rejections=previous.spike_rejections,
                fallbacks=previous.fallbacks,
                unavailable_samples=previous.unavailable_samples
                + (1 if raw_val is None else 0),
                source_states={primary: raw_val}
                if raw_val is not None
                else {},
                stale=raw_val is None,
                updated_at=datetime.now(UTC),
                previous_value=raw_val,
                delta=_numeric_delta(raw_val, previous.previous_value),
                warn_hit=False,
            )
            return raw_val

        net_subtract_raw = self._read_state(config.get(CONF_NET_SUBTRACT_ENTITY_ID))
        fallback_raw = self._read_state(config.get(CONF_FALLBACK_SOURCE_ENTITY_ID))
        fallback_condition_met = self._fallback_condition_met(config)
        val = pipeline.process_sources(
            raw_states,
            net_subtract_raw=net_subtract_raw,
            fallback_raw=fallback_raw,
            fallback_condition_met=fallback_condition_met,
        )
        self._record_value_sample(subentry_id, val)
        previous = self.meta.get(subentry_id, SubentryMeta())
        spike_hits = previous.spike_rejections
        fallback_hits = previous.fallbacks
        unavailable_samples = previous.unavailable_samples
        if (pipeline.last_event or "").lower().startswith("spike"):
            spike_hits += 1
            self._record_rejected_sample(subentry_id, raw_states, pipeline.last_event)
        if (pipeline.last_event or "").lower().startswith("fallback"):
            fallback_hits += 1
        if val is None:
            unavailable_samples += 1
        source_states = {
            source_id: (raw_states[i] if i < len(raw_states) else None)
            for i, source_id in enumerate(source_ids)
        }
        self.meta[subentry_id] = SubentryMeta(
            last_event=pipeline.last_event,
            event_at=datetime.now(UTC)
            if pipeline.last_event is not None
            else previous.event_at,
            spike_rejections=spike_hits,
            fallbacks=fallback_hits,
            unavailable_samples=unavailable_samples,
            source_states={k: v for k, v in source_states.items() if v is not None},
            stale=val is None,
            updated_at=datetime.now(UTC),
            previous_value=val,
            delta=_numeric_delta(val, previous.previous_value),
            warn_hit=self._warn_hit(config, val),
        )
        await self._async_notify_debug(subentry_id, pipeline.last_event)

        if self.influx_exporter and val is not None:
            await self.influx_exporter.async_push(source_ids[0], val)
        return val

    def _record_rejected_sample(
        self, subentry_id: str, raw_states: list[str | None], reason: str
    ) -> None:
        """Append the rejected sample (raw value + reason) to the ring (WS-5).

        ids stay stable across polls (per-subentry sequence) so the panel can
        void a specific sample across reloads.
        """
        seq = self._ring_seq.get(subentry_id, 0) + 1
        self._ring_seq[subentry_id] = seq
        ring = self.rejected_samples.setdefault(subentry_id, [])
        ring.append(
            {
                "id": f"{subentry_id}#{seq}",
                "at": datetime.now(UTC).isoformat(),
                "value": raw_states[0] if raw_states else None,
                "reason": reason,
            }
        )
        while len(ring) > REJECTED_RING_LIMIT:
            ring.pop(0)

    def _record_value_sample(self, subentry_id: str, value: Any) -> None:
        """Append an accepted sample to the bounded per-subentry value window (WS-6).

        Only non-None values enter the window. The window keeps the newest
        ``VALUE_HISTORY_LIMIT`` samples; aggregates for the summary service
        are computed over exactly what this window retained — the recorder's
        internals are never read (documented source per field, E8).
        """
        if value is None:
            return
        history = self.value_history.setdefault(subentry_id, [])
        history.append((datetime.now(UTC), value))
        while len(history) > VALUE_HISTORY_LIMIT:
            history.pop(0)

    def _health_for(self, subentry_id: str, value: Any, last_event: str | None) -> str:
        """Single health mapping shared by the WS payload and summary service.

        ``bad`` when coordinator polling itself failed, ``idle`` while the
        subentry has no value, ``warn`` when the last pipeline event or a
        configured warn threshold hit applies, otherwise ``ok``.
        """
        if not self.last_update_success:
            return "bad"
        if value is None:
            return "idle"
        if last_event or self.meta.get(subentry_id, SubentryMeta()).warn_hit:
            return "warn"
        return "ok"

    def _warn_hit(self, config: dict[str, Any], value: float | str | None) -> bool:
        """Threshold decision for the WS-5 warn_above/warn_below options.

        Only numeric values can hit. A configured ``warn_condition_entity_id``
        gates the check like the debug switch: while that entity is not "on",
        thresholds never report.
        """
        if value is None or isinstance(value, (str, bool)):
            return False
        above = config.get(CONF_WARN_ABOVE)
        below = config.get(CONF_WARN_BELOW)
        hit = (above is not None and value > above) or (
            below is not None and value < below
        )
        if not hit:
            return False
        condition = config.get(CONF_WARN_CONDITION_ENTITY_ID)
        if condition:
            return self.hass.states.is_state(condition, "on")
        return True

    def _read_state(self, entity_id: str | None) -> str | None:
        """Read a raw HA state string for an optional entity_id."""
        if not entity_id:
            return None
        state_obj = self.hass.states.get(entity_id)
        return state_obj.state if state_obj else None

    def _fallback_condition_met(self, config: dict[str, Any]) -> bool:
        """Evaluate the REQ-COMP-004 fallback condition.

        No fallback source configured -> never eligible. A fallback source
        without a condition entity is always eligible when the primary is
        unavailable. With a condition entity, the fallback is only eligible
        while that entity's state matches the configured expected state.
        """
        if not config.get(CONF_FALLBACK_SOURCE_ENTITY_ID):
            return False
        condition_entity_id = config.get(CONF_FALLBACK_CONDITION_ENTITY_ID)
        if not condition_entity_id:
            return True
        expected_state = config.get(CONF_FALLBACK_CONDITION_STATE)
        return self._read_state(condition_entity_id) == expected_state

    async def _async_notify_debug(self, subentry_id: str, event: str | None) -> None:
        """Send deduplicated debug events to the configured notify target.

        The targets come from the root entry's options (applied on every
        setup in __init__.py): an `input_boolean` gate and a `notify`
        entity. When either option is unset the whole path is a silent
        no-op — this is diagnostics plumbing, never a reason for a poll
        cycle to fail. A referenced entity that does not (or no longer)
        exists simply fails its checks here (`is_state` is False for a
        missing entity, `has_service` guards the call), it never raises.
        """
        if event is None:
            self._last_notified_events.pop(subentry_id, None)
            return
        if self._last_notified_events.get(subentry_id) == event:
            return
        debug_switch = self.debug_switch_entity_id
        notify_entity_id = self.notify_entity_id
        if not debug_switch or not notify_entity_id:
            return
        if not self.hass.states.is_state(debug_switch, "on"):
            return
        if not notify_entity_id.startswith("notify."):
            _LOGGER.debug(
                "Abstractor debug notify target %s is not a notify entity; skipping",
                notify_entity_id,
            )
            return
        service = notify_entity_id.removeprefix("notify.")
        if not self.hass.services.has_service("notify", service):
            return
        await self.hass.services.async_call(
            "notify",
            service,
            {"message": f"Abstractor {subentry_id}: {event}"},
            blocking=False,
        )
        self._last_notified_events[subentry_id] = event
