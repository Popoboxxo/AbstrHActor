"""Naming & identity resolution (REQ-NAME-001..006).

This module is HA-free so it can be exercised by fast unit tests
(REQ-NFA-002). It centralises every rule that turns a subentry's data plus the
active naming template into:

* the **device** display name,
* the entity **friendly name** (``None`` means "use the localized default"),
* the suggested ``object_id`` / ``entity_id``.

Hard rule (REQ-NAME-001): none of this ever influences a sensor's
``unique_id``. Identity stays in ``CONF_LEGACY_UNIQUE_ID`` and the source-derived
fallback in the platforms; names and addresses are cosmetic.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_NAME,
    CONF_ENTITY_NAME,
    CONF_LOGICAL_NAME,
    CONF_OBJECT_ID,
    DEFAULT_DEVICE_NAME,
)
from .specs import AbstractSpec

_SLUG_INVALID = re.compile(r"[^a-z0-9_]+")
_SLUG_RUNS = re.compile(r"_+")


class NamingTemplate(Protocol):
    """The slice of a naming template the resolver needs (Phase 2)."""

    def device_name(self, device_type: str) -> str | None: ...

    def entity_name(self, type_key: str) -> str | None: ...

    def object_id(self, type_key: str) -> str | None: ...


def slugify(text: str) -> str:
    """Return an HA-style object_id slug (lowercase, single underscores)."""
    slug = text.strip().lower().replace(" ", "_").replace("-", "_")
    slug = _SLUG_INVALID.sub("", slug)
    slug = _SLUG_RUNS.sub("_", slug)
    return slug.strip("_")


def render_device_template(raw: str, device_type: str) -> str:
    """Reproduce the legacy ``{device_type}`` substitution, unchanged.

    Kept byte-identical to the pre-templates behaviour so an install without
    any naming configuration keeps its exact device names.
    """
    return raw.replace("{device_type}", device_type.capitalize())


def effective_logical_name(
    data: Mapping[str, Any],
    group_subentries: Iterable[Mapping[str, Any]],
) -> str | None:
    """Return the device's logical name, shared across a device group.

    ``logical_name`` is a device property but is stored per subentry (the only
    snapshotted store). Members of one ``device_group_id`` therefore share the
    name: a member that does not carry it inherits it from a sibling so a group
    never shows two different device names (plan §3.6).
    """
    own = data.get(CONF_LOGICAL_NAME)
    if own and str(own).strip():
        return str(own).strip()
    group_id = data.get(CONF_DEVICE_GROUP_ID)
    if not group_id:
        return None
    for other in group_subentries:
        if other is data:
            continue
        if other.get(CONF_DEVICE_GROUP_ID) != group_id:
            continue
        candidate = other.get(CONF_LOGICAL_NAME)
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return None


def resolve_device_name(
    options: Mapping[str, Any],
    device_type: str,
    logical_name: str | None,
    template: NamingTemplate | None = None,
) -> str:
    """Resolve the device display name (REQ-NAME-002), highest precedence first."""
    if logical_name:
        return logical_name
    if template is not None:
        rendered = template.device_name(device_type)
        if rendered:
            return rendered
    raw = str(options.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME))
    return render_device_template(raw, device_type)


def resolve_entity_name(
    data: Mapping[str, Any],
    spec: AbstractSpec,
    template: NamingTemplate | None = None,
) -> str | None:
    """Resolve an explicit entity name, or ``None`` to use the default.

    ``None`` lets the platform fall back to its localized ``translation_key``
    default (REQ-NAME-003) instead of a hard-coded string.
    """
    override = data.get(CONF_ENTITY_NAME)
    if override and str(override).strip():
        return str(override).strip()
    if template is not None:
        rendered = template.entity_name(spec.type_key)
        if rendered:
            return rendered
    return None


def resolve_object_id(
    data: Mapping[str, Any],
    spec: AbstractSpec,
    template: NamingTemplate | None = None,
) -> str | None:
    """Resolve the suggested ``object_id`` (REQ-NAME-004), or ``None``.

    The value is slugified here so a friendly input (``"Kitchen Fridge"``)
    yields a valid entity id; an empty result counts as "not set".
    """
    raw = data.get(CONF_OBJECT_ID)
    if raw and str(raw).strip():
        return slugify(str(raw)) or None
    if template is not None:
        rendered = template.object_id(spec.type_key)
        if rendered:
            return slugify(rendered) or None
    return None
