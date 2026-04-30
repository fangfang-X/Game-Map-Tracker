"""Shared helpers for route/annotation resource metadata."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from ui_island.app.app_info import APP_ENABLE_ROUTE_VERSIONS, APP_FORMAT_VERSION

HASH_RE = re.compile(r"^[0-9a-f]{32}$")


def md5_file(path: str | os.PathLike[str] | None) -> str:
    if not path:
        return ""
    digest = hashlib.md5()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def default_enable_versions() -> list[str]:
    values = APP_ENABLE_ROUTE_VERSIONS
    try:
        import config

        runtime_values = getattr(config, "APP_ENABLE_ROUTE_VERSIONS", None)
        if isinstance(runtime_values, list) and runtime_values:
            values = runtime_values
    except Exception:
        pass
    return [str(item) for item in values if str(item or "").strip()]


def ensure_metadata(
    payload: dict,
    *,
    include_id: bool = False,
    include_route_defaults: bool = False,
) -> dict:
    payload["format_version"] = APP_FORMAT_VERSION

    enable_versions = [
        str(item).strip()
        for item in payload.get("enable_versions", [])
        if str(item or "").strip()
    ]
    for item in default_enable_versions():
        if item not in enable_versions:
            enable_versions.append(item)
    if APP_FORMAT_VERSION not in enable_versions:
        enable_versions.append(APP_FORMAT_VERSION)
    payload["enable_versions"] = enable_versions

    if include_route_defaults:
        raw_loop = payload.get("loop", False)
        if isinstance(raw_loop, bool):
            payload["loop"] = raw_loop
        elif isinstance(raw_loop, str):
            payload["loop"] = raw_loop.strip().casefold() in {"1", "true", "yes", "on"}
        else:
            payload["loop"] = bool(raw_loop)
        notes = payload.get("notes", "")
        payload["notes"] = "" if notes is None else (notes if isinstance(notes, str) else str(notes))

    if include_id:
        raw_id = str(payload.get("id") or "").strip().lower()
        if not HASH_RE.fullmatch(raw_id):
            payload["id"] = uuid.uuid4().hex
        else:
            payload["id"] = raw_id
    return payload


def annotation_output_name(root: str | os.PathLike[str], *, prefix: str = "17173points") -> str:
    from datetime import datetime

    today = datetime.now().strftime("%Y%m%d")
    directory = Path(root)
    for index in range(1, 100):
        name = f"{prefix}_{today}{index:02d}.json"
        if not (directory / name).exists():
            return name
    return f"{prefix}_{today}99.json"
