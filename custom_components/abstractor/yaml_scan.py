"""Read-only scan of hand-written ``template:`` sensor packages in the config.

The Migrate tab must show which YAML-defined template sensors a legacy setup
offers as migration candidates (UF-05: ``ws_yaml_scan`` was a placeholder that
always returned an empty list). This module is pure text parsing on purpose —
same line-based strategy as ``scripts/migrate_local_yaml.py`` (no PyYAML
dependency, YAML anchors/other config domains are ignored structurally).
"""

from __future__ import annotations

import re

_TOP_LEVEL_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):\s*(?:#.*)?$")
_TEMPLATE_ENTRY_RE = re.compile(r"^\s*-\s+name:\s*(?P<name>[^#,]+?)\s*(?:#.*)?$")
_UNIQUE_ID_RE = re.compile(r"^\s+unique_id:\s*(?P<uid>[^#,]+?)\s*(?:#.*)?$")
_UNIT_RE = re.compile(r"^\s+unit_of_measurement:\s*(?P<unit>[^#,]+?)\s*(?:#.*)?$")
_ENTITY_ID_RE = re.compile(r"^\s+entity_id:\s*(?P<eid>[\w.-]+)\s*(?:#.*)?$")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("_", name.lower()).strip("_")


def scan_template_sensors(text: str) -> list[dict]:
    """Parse one YAML text into template-sensor migration rows (pure).

    Only ``template:`` top-level sections are scanned (a top-level key at
    column zero ends the section), so ``utility_meter`` sources or
    ``sensor:`` entries never masquerade as templates.
    """
    rows: list[dict] = []
    in_template = False
    pending: dict | None = None

    def _flush() -> None:
        nonlocal pending
        if pending is not None:
            rows.append(pending)
            pending = None

    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top = _TOP_LEVEL_KEY_RE.match(line)
        if top:
            _flush()
            in_template = top.group("key") == "template"
            continue
        if not in_template:
            continue
        entry = _TEMPLATE_ENTRY_RE.match(line)
        if entry:
            _flush()
            pending = {
                "unique_id": None,
                "unit": None,
                "source_entities": [],
                "name": entry.group("name"),
            }
            continue
        if pending is None:
            continue
        uid = _UNIQUE_ID_RE.match(line)
        if uid:
            pending["unique_id"] = uid.group("uid")
            continue
        unit = _UNIT_RE.match(line)
        if unit:
            pending["unit"] = unit.group("unit")
            continue
        eid = _ENTITY_ID_RE.match(line)
        if eid and eid.group("eid") not in pending["source_entities"]:
            pending["source_entities"].append(eid.group("eid"))
    _flush()

    dupes = {uid for uid, count in _uid_counts(rows).items() if count > 1}
    out = []
    for row in rows:
        name = row["name"]
        uid = row["unique_id"]
        blockers: list[str] = []
        if uid is None:
            blockers.append("no unique_id: recorder history cannot be preserved")
        elif uid in dupes:
            blockers.append("duplicate unique_id")
        if not row["source_entities"]:
            blockers.append("no referenced entity_id: calculation source unclear")
        slug = _slugify(name)
        out.append(
            {
                "unique_id": uid,
                "suggested_logical_name": slug,
                "suggested_object_id": f"abstractor_{slug}",
                "source_entities": list(row["source_entities"]),
                "unit": row["unit"],
                "history_preservable": uid is not None and uid not in dupes,
                "blockers": blockers,
            }
        )
    return out


def _uid_counts(rows: list[dict]) -> dict[str, int]:
    """How often each unique_id appears across the scan."""
    counts: dict[str, int] = {}
    for row in rows:
        if row["unique_id"] is not None:
            counts[row["unique_id"]] = counts.get(row["unique_id"], 0) + 1
    return counts


def scan_config_dir(config_dir: str) -> tuple[list[dict], list[str]]:
    """Scan the top-level ``*.yaml`` config files of a HA config dir.

    Only the config root is scanned (never the ``data/`` or ``secrets_*``
    trees), keeping the read path free of any secret material. Unreadable
    files are skipped, not fatal.
    """
    from pathlib import Path

    rows: list[dict] = []
    scanned: list[str] = []
    for path in sorted(Path(config_dir).glob("*.yaml")):
        if path.name.startswith(".") or "secret" in path.name.lower():
            continue
        scanned.append(str(path))
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rows.extend(scan_template_sensors(text))
    return rows, scanned
