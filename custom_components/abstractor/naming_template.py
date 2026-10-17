"""Local, declarative naming templates (REQ-NAME-005/006).

Templates are YAML files in ``<config>/abstractor/templates/*.yaml``. They only
ever influence *display* names and the suggested ``object_id`` — never a
sensor's ``unique_id`` (REQ-NAME-001).

Design constraints (see ``docs/plan-naming-identity-templates.md`` §4/§9):

* data, never code — a restricted placeholder engine, no ``eval``/Jinja/
  ``str.format``, so a template cannot reach into objects or run anything;
* unknown tokens/filters are rejected at load time and the template is skipped
  with a warning instead of being applied partially (REQ-NAME-006);
* broken/missing templates never block setup — the caller falls back to the
  built-in behaviour.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

import yaml
from homeassistant.core import HomeAssistant

from .const import DEFAULT_NAMING_TEMPLATE
from .naming import slugify
from .specs import SPEC_REGISTRY

_LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION: Final = 1
TEMPLATES_SUBDIR: Final = ("abstractor", "templates")
MAX_TEMPLATE_BYTES: Final = 64 * 1024
MAX_INHERITANCE_DEPTH: Final = 10

_BUILTIN_TOKENS: Final = frozenset(
    {"device_type", "device_type_label", "spec_display_name", "device_name"}
)
_FILTERS = {
    "slug": slugify,
    "lower": str.lower,
    "upper": str.upper,
    "title": str.title,
}

_TOKEN_RE = re.compile(r"\{([^{}]+)\}")


class NamingTemplateError(ValueError):
    """Raised when a template is malformed or uses an unknown placeholder."""


def _templates_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.config_dir).joinpath(*TEMPLATES_SUBDIR)


def _parse_expr(expr: str) -> tuple[str | None, str]:
    """Split ``filter(token)`` or ``token`` into (filter, token)."""
    expr = expr.strip()
    if expr.endswith(")") and "(" in expr:
        filter_name, _, inner = expr.partition("(")
        return filter_name.strip(), inner[:-1].strip()
    return None, expr


def _validate_tokens(text: Any, allowed_tokens: set[str]) -> None:
    if not isinstance(text, str):
        raise NamingTemplateError("template value must be a string")
    for match in _TOKEN_RE.finditer(text):
        filter_name, token = _parse_expr(match.group(1))
        if token not in allowed_tokens:
            raise NamingTemplateError(f"unknown placeholder {{{token}}}")
        if filter_name is not None and filter_name not in _FILTERS:
            raise NamingTemplateError(f"unknown filter {filter_name}()")


def _render(text: str, context: dict[str, str]) -> str:
    """Substitute whitelisted placeholders; context is already validated."""

    def _sub(match: re.Match[str]) -> str:
        filter_name, token = _parse_expr(match.group(1))
        value = context[token]
        if filter_name is not None:
            value = _FILTERS[filter_name](value)
        return value

    return _TOKEN_RE.sub(_sub, text)


class NamingTemplate:
    """A parsed, validated naming template."""

    def __init__(self, template_id: str, raw: dict[str, Any]) -> None:
        self.id = template_id
        self.description = raw.get("description")
        self._raw = raw
        self._device_name = raw.get("device_name")
        self._entity_name = raw.get("entity_name") or {}
        self._object_id = raw.get("object_id")
        self._variables = {
            str(k): str(v) for k, v in (raw.get("variables") or {}).items()
        }

    def _context(self, type_key: str) -> dict[str, str]:
        spec = SPEC_REGISTRY.try_get(type_key)
        display = (
            spec.display_name
            if spec is not None
            else type_key.replace("_", " ").title()
        )
        context = dict(self._variables)
        context.update(
            {
                "device_type": type_key,
                "device_type_label": type_key.capitalize(),
                "spec_display_name": display,
            }
        )
        # `device_name` is the resolved device name, so an object_id scheme can
        # derive from it (e.g. "{slug(device_name)}_{device_type}"). Rendering
        # it uses the context *without* this key, so it cannot recurse.
        context["device_name"] = (
            _render(self._device_name, context) if self._device_name else display
        )
        return context

    def device_name(self, device_type: str) -> str | None:
        if not self._device_name:
            return None
        return _render(self._device_name, self._context(device_type))

    def entity_name(self, type_key: str) -> str | None:
        raw = self._entity_name.get(type_key) or self._entity_name.get("default")
        if not raw:
            return None
        return _render(str(raw), self._context(type_key))

    def object_id(self, type_key: str) -> str | None:
        if not self._object_id:
            return None
        return _render(self._object_id, self._context(type_key))


def _merge(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in child.items():
        if key in ("entity_name", "variables") and isinstance(value, dict):
            merged[key] = {**(base.get(key) or {}), **value}
        else:
            merged[key] = value
    return merged


def _load_file(path: Path) -> tuple[str, dict[str, Any]] | None:
    try:
        if path.stat().st_size > MAX_TEMPLATE_BYTES:
            _LOGGER.warning("Naming template %s exceeds size limit; skipped", path)
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        _LOGGER.warning("Naming template %s could not be read: %s", path, err)
        return None
    if not isinstance(data, dict):
        _LOGGER.warning("Naming template %s is not a mapping; skipped", path)
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        _LOGGER.warning(
            "Naming template %s has unsupported schema_version %r; skipped",
            path,
            data.get("schema_version"),
        )
        return None
    template_id = str(data.get("id") or path.stem)
    return template_id, data


def _validate(template_id: str, raw: dict[str, Any]) -> None:
    variables = raw.get("variables") or {}
    if not isinstance(variables, dict):
        raise NamingTemplateError("variables must be a mapping")
    allowed = set(_BUILTIN_TOKENS) | {str(k) for k in variables}
    for key in ("device_name", "object_id"):
        if key in raw and raw[key] is not None:
            _validate_tokens(raw[key], allowed)
    entity_name = raw.get("entity_name") or {}
    if not isinstance(entity_name, dict):
        raise NamingTemplateError("entity_name must be a mapping")
    for value in entity_name.values():
        if value is not None:
            _validate_tokens(value, allowed)


def _load_templates_sync(path: Path) -> dict[str, NamingTemplate]:
    if not path.is_dir():
        return {}
    raw: dict[str, dict[str, Any]] = {}
    for file in sorted(path.glob("*.yaml")):
        loaded = _load_file(file)
        if loaded is None:
            continue
        template_id, data = loaded
        try:
            _validate(template_id, data)
        except NamingTemplateError as err:
            _LOGGER.warning("Naming template %s is invalid: %s; skipped", file, err)
            continue
        raw[template_id] = data

    resolved: dict[str, NamingTemplate] = {}

    def resolve(template_id: str, seen: frozenset[str]) -> NamingTemplate | None:
        if template_id in resolved:
            return resolved[template_id]
        if template_id not in raw or template_id in seen:
            return None
        if len(seen) >= MAX_INHERITANCE_DEPTH:
            _LOGGER.warning(
                "Naming template %s inheritance chain too deep; skipped", template_id
            )
            return None
        data = raw[template_id]
        merged: dict[str, Any] = {}
        parent_id = data.get("extends")
        if parent_id and parent_id != template_id:
            parent = resolve(str(parent_id), seen | {template_id})
            if parent is not None:
                merged = dict(parent._raw)
        merged = _merge(merged, data)
        try:
            _validate(template_id, merged)
        except NamingTemplateError as err:
            _LOGGER.warning(
                "Naming template %s is invalid after inheritance: %s; skipped",
                template_id,
                err,
            )
            return None
        template = NamingTemplate(template_id, merged)
        resolved[template_id] = template
        return template

    for template_id in list(raw):
        resolve(template_id, frozenset())
    return resolved


async def async_load_templates(hass: HomeAssistant) -> dict[str, NamingTemplate]:
    """Load every valid template; never raises (REQ-NAME-006)."""
    try:
        return await hass.async_add_executor_job(_load_templates_sync, _templates_dir(hass))
    except Exception as err:  # noqa: BLE001 - fail soft, never block setup
        _LOGGER.warning("Could not load naming templates: %s", err)
        return {}


async def async_template_ids(hass: HomeAssistant) -> list[str]:
    """Return the selectable template ids (always includes ``default``)."""
    templates = await async_load_templates(hass)
    return [DEFAULT_NAMING_TEMPLATE, *sorted(templates)]


async def async_get_template(
    hass: HomeAssistant, template_id: str | None
) -> NamingTemplate | None:
    """Resolve the active template, or ``None`` for built-in behaviour."""
    if not template_id or template_id == DEFAULT_NAMING_TEMPLATE:
        return None
    templates = await async_load_templates(hass)
    template = templates.get(template_id)
    if template is None:
        _LOGGER.warning(
            "Naming template %r not found; falling back to built-in defaults",
            template_id,
        )
    return template
