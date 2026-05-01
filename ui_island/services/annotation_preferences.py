"""Helpers for annotation type selection."""

from __future__ import annotations

import uuid


def normalize_type_ids(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values:
        type_id = str(value or "").strip()
        if not type_id or type_id in seen:
            continue
        seen.add(type_id)
        result.append(type_id)
    return result


def normalize_annotation_presets(values: object) -> list[dict]:
    if not isinstance(values, list):
        return []
    result: list[dict] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        type_ids = normalize_type_ids(value.get("type_ids"))
        if not name or not type_ids or name in seen_names:
            continue
        preset_id = str(value.get("id") or "").strip()
        if not preset_id or preset_id in seen_ids:
            preset_id = f"preset_{uuid.uuid4().hex}"
        seen_ids.add(preset_id)
        seen_names.add(name)
        result.append({"id": preset_id, "name": name, "type_ids": type_ids})
    return result


def annotation_preset_names(presets: object, *, exclude_id: str = "") -> set[str]:
    excluded = str(exclude_id or "").strip()
    names: set[str] = set()
    for preset in normalize_annotation_presets(presets):
        if excluded and preset.get("id") == excluded:
            continue
        names.add(str(preset.get("name") or "").strip())
    return names
