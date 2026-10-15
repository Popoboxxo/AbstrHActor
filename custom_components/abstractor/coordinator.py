"""DataUpdateCoordinator for Abstractor."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    AGGREGATION_SUM,
    CONF_AGGREGATION,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .filters import AbstractorFilterPipeline
from .specs import SPEC_REGISTRY

_LOGGER = logging.getLogger(__name__)

@dataclass
class SubentryMeta:
    """Runtime-only health metadata for a single subentry (never persisted)."""

    last_event: str | None = None
    event_at: datetime | None = None
    spike_rejections: int = 0
    fallbacks: int = 0
    unavailable_samples: int = 0
    source_states: dict[str, str] = field(default_factory=dict)
    stale: bool = False


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
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.subentry_data: dict[str, dict] = {}
        self.pipelines: dict[str, AbstractorFilterPipeline] = {}
        self.meta: dict[str, SubentryMeta] = {}
        self.influx_exporter = None
        self._last_notified_events: dict[str, str] = {}
        # Debug notification targets, applied from the root entry's options on
        # every setup (see __init__.py). Both None = the debug notify path is
        # silently off; nothing here may fail when the referenced entities do
        # not exist.
        self.debug_switch_entity_id: str | None = None
        self.notify_entity_id: str | None = None

    def set_update_interval(self, seconds: int) -> None:
        """Update and reschedule the coordinator's periodic refresh timer.

        HA exposes no public timer-rescheduling API. The installed coordinator
        implementation owns `_unsub_refresh` and `_schedule_refresh`; using
        those in-class seams avoids creating a second coordinator. The
        fallback keeps the new interval and requests an immediate refresh on
        HA versions where either private seam is unavailable.
        """
        self.update_interval = timedelta(seconds=seconds)
        unsubscribe = getattr(self, "_unsub_refresh", None)
        schedule_refresh = getattr(self, "_schedule_refresh", None)
        if unsubscribe is not None and schedule_refresh is not None:
            unsubscribe()
            schedule_refresh()
            return
        self.hass.async_create_task(self.async_request_refresh())

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
        spec = SPEC_REGISTRY.try_get(config.get("device_type", "power"))
        if spec is not None and spec.numeric:
            self.pipelines[subentry_id] = AbstractorFilterPipeline(
                config, initial_last_valid_state
            )
        else:
            self.pipelines.pop(subentry_id, None)
        self.meta.setdefault(subentry_id, SubentryMeta())

    def remove_subentry(self, subentry_id: str) -> None:
        """Remove a subentry from central polling."""
        self.subentry_data.pop(subentry_id, None)
        self.pipelines.pop(subentry_id, None)
        self.meta.pop(subentry_id, None)
        self._last_notified_events.pop(subentry_id, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via central polling."""
        # Values are numeric for sensor specs but raw state strings for
        # pass-through specs (e.g. binary_sensor / switch / cover), hence the
        # union.
        data: dict[str, float | str | None] = {}
        for subentry_id, config in self.subentry_data.items():
            source_ids = config.get(CONF_SOURCE_ENTITY_IDS) or [
                config.get(CONF_SOURCE_ENTITY_ID)
            ]
            source_ids = [source_id for source_id in source_ids if source_id]
            if not source_ids:
                continue

            raw_states = [
                (state_obj.state if (state_obj := self.hass.states.get(source_id)) else None)
                for source_id in source_ids
            ]

            pipeline = self.pipelines.get(subentry_id)
            if pipeline is None:
                primary = source_ids[0] if source_ids else None
                raw_val = self._read_state(primary)
                data[subentry_id] = raw_val
                await self._async_notify_debug(subentry_id, None)
                previous = self.meta.get(subentry_id, SubentryMeta())
                self.meta[subentry_id] = SubentryMeta(
                    last_event=previous.last_event,
                    event_at=previous.event_at,
                    spike_rejections=previous.spike_rejections,
                    fallbacks=previous.fallbacks,
                    unavailable_samples=previous.unavailable_samples + (1 if raw_val is None else 0),
                    source_states={primary: raw_val} if primary and raw_val is not None else {},
                    stale=False,
                )
                continue
            if pipeline:
                net_subtract_raw = self._read_state(config.get(CONF_NET_SUBTRACT_ENTITY_ID))
                fallback_raw = self._read_state(config.get(CONF_FALLBACK_SOURCE_ENTITY_ID))
                fallback_condition_met = self._fallback_condition_met(config)
                val = pipeline.process_sources(
                    raw_states,
                    net_subtract_raw=net_subtract_raw,
                    fallback_raw=fallback_raw,
                    fallback_condition_met=fallback_condition_met,
                )
                data[subentry_id] = val
                previous = self.meta.get(subentry_id, SubentryMeta())
                spike_hits = previous.spike_rejections
                fallback_hits = previous.fallbacks
                unavailable_samples = previous.unavailable_samples
                if (pipeline.last_event or "").lower().startswith("spike"):
                    spike_hits += 1
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
                    source_states={
                        k: v for k, v in source_states.items() if v is not None
                    },
                    stale=False,
                )
                await self._async_notify_debug(subentry_id, pipeline.last_event)

                if self.influx_exporter and val is not None:
                    await self.influx_exporter.async_push(source_ids[0], val)
        return data

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
