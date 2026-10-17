"""Unit tests for local naming templates (REQ-NAME-005/006)."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.abstractor import naming_template as nt


class _FakeConfig:
    def __init__(self, config_dir: str) -> None:
        self.config_dir = config_dir


class _FakeHass:
    def __init__(self, config_dir: str) -> None:
        self.config = _FakeConfig(config_dir)

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _write(tmp_path: Path, name: str, content: str) -> None:
    d = tmp_path / "abstractor" / "templates"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content)


def test_load_valid_template(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "household.yaml",
        """
schema_version: 1
id: household
variables:
  prefix: Home
device_name: "{prefix} {spec_display_name}"
entity_name:
  default: "{spec_display_name}"
  power: "Leistung"
object_id: "{slug(device_name)}_{device_type}"
""",
    )
    templates = nt._load_templates_sync(tmp_path / "abstractor" / "templates")
    assert set(templates) == {"household"}
    tpl = templates["household"]
    assert tpl.device_name("power") == "Home Power"
    assert tpl.entity_name("power") == "Leistung"
    assert tpl.entity_name("energy") == "Energy"
    assert tpl.object_id("power") == "home_power_power"


def test_inheritance_merges_entity_names(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "base.yaml",
        """
schema_version: 1
id: base
device_name: "Base {device_type}"
entity_name:
  power: "P"
""",
    )
    _write(
        tmp_path,
        "child.yaml",
        """
schema_version: 1
id: child
extends: base
entity_name:
  energy: "E"
""",
    )
    templates = nt._load_templates_sync(tmp_path / "abstractor" / "templates")
    child = templates["child"]
    assert child.device_name("power") == "Base power"
    assert child.entity_name("power") == "P"
    assert child.entity_name("energy") == "E"


def test_unknown_placeholder_is_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.yaml",
        "schema_version: 1\nid: bad\ndevice_name: \"{nope}\"\n",
    )
    templates = nt._load_templates_sync(tmp_path / "abstractor" / "templates")
    assert templates == {}


def test_unknown_filter_is_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.yaml",
        "schema_version: 1\nid: bad\ndevice_name: \"{nope(token)}\"\n",
    )
    templates = nt._load_templates_sync(tmp_path / "abstractor" / "templates")
    assert templates == {}


def test_wrong_schema_version_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "old.yaml", "schema_version: 2\nid: old\n")
    assert nt._load_templates_sync(tmp_path / "abstractor" / "templates") == {}


def test_oversize_file_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "big.yaml", "x" * (nt.MAX_TEMPLATE_BYTES + 10))
    assert nt._load_templates_sync(tmp_path / "abstractor" / "templates") == {}


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert nt._load_templates_sync(tmp_path / "nope") == {}


@pytest.mark.asyncio
async def test_async_get_template_default_is_none(tmp_path: Path) -> None:
    hass = _FakeHass(str(tmp_path))
    assert await nt.async_get_template(hass, None) is None
    assert await nt.async_get_template(hass, "default") is None


@pytest.mark.asyncio
async def test_async_get_template_unknown_is_none(tmp_path: Path) -> None:
    hass = _FakeHass(str(tmp_path))
    assert await nt.async_get_template(hass, "does_not_exist") is None


@pytest.mark.asyncio
async def test_async_template_ids_always_lists_default(tmp_path: Path) -> None:
    _write(tmp_path, "a.yaml", "schema_version: 1\nid: a\ndevice_name: \"A\"\n")
    hass = _FakeHass(str(tmp_path))
    assert await nt.async_template_ids(hass) == ["default", "a"]
