"""Batch conversion helpers for route JSON files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_PROGRESS_FILE = "progress.json"
_VISIBILITY_FILE = "selected_routes.json"
_OUTPUT_SUFFIX = "_新格式"

_OLD_ROUTE_LON_SCALE = 5824.0800
_OLD_ROUTE_LON_OFFSET = 7217.5810
_OLD_ROUTE_LAT_SCALE = 5822.8413
_OLD_ROUTE_LAT_OFFSET = 6602.7721

_ROUTE_PAYLOAD_KEY_ORDER = (
    "id",
    "format_version",
    "enable_versions",
    "color",
    "name",
    "notes",
    "loop",
    "points",
    "nodes",
)


@dataclass
class RouteConversionReport:
    converted: int = 0
    skipped: int = 0
    ignored: int = 0
    errors: int = 0
    points_converted: int = 0
    messages: list[str] = field(default_factory=list)


def _ordered_route_payload(payload: dict) -> dict:
    ordered = {key: payload[key] for key in _ROUTE_PAYLOAD_KEY_ORDER if key in payload}
    ordered.update((key, value) for key, value in payload.items() if key not in ordered)
    return ordered


def _iter_source_files(input_dir: Path, recursive: bool) -> Iterable[Path]:
    pattern = "**/*.json" if recursive else "*.json"
    yield from sorted(path for path in input_dir.glob(pattern) if path.is_file())


def _target_path(source: Path, input_root: Path, output_root: Path) -> Path:
    relative = source.relative_to(input_root)
    target_name = relative.stem + _OUTPUT_SUFFIX + relative.suffix
    return output_root / relative.with_name(target_name)


def _is_route_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return isinstance(payload.get("points"), list) or isinstance(payload.get("nodes"), list)


def _clean_route_metadata(payload: dict) -> dict:
    output = dict(payload)
    output.pop("coordinate_space_id", None)
    output.pop("map_hash", None)
    output.pop("map_hashs", None)
    output.pop("map_info", None)
    return output


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def normalize_route_payload(
    payload: dict,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("路线 JSON 顶层必须是对象")
    return _ordered_route_payload(_clean_route_metadata(payload))


def old_big_map_xy_to_latlng(x: float, y: float) -> tuple[float, float]:
    """Reverse the old 17173 fitted pixel formula into latitude/longitude."""
    longitude = (float(x) - _OLD_ROUTE_LON_OFFSET) / _OLD_ROUTE_LON_SCALE
    latitude = (_OLD_ROUTE_LAT_OFFSET - float(y)) / _OLD_ROUTE_LAT_SCALE
    return latitude, longitude


def old_big_map_xy_to_17173_xy(x: float, y: float) -> tuple[int, int]:
    """Convert old big_map route pixels into big_map_17173.png pixels."""
    try:
        from tools.fetch_17173_points import latlng_to_xy
    except ImportError:  # pragma: no cover - supports running from tools/ directly.
        from fetch_17173_points import latlng_to_xy

    latitude, longitude = old_big_map_xy_to_latlng(x, y)
    return latlng_to_xy(latitude, longitude)


def convert_old_big_map_route_payload(payload: dict) -> tuple[dict, int]:
    if not isinstance(payload, dict):
        raise ValueError("路线 JSON 顶层必须是对象")

    output = _clean_route_metadata(payload)
    converted_points = 0
    for key in ("points", "nodes"):
        points = output.get(key)
        if not isinstance(points, list):
            continue
        converted: list[object] = []
        for point in points:
            if not isinstance(point, dict):
                converted.append(point)
                continue
            copied = dict(point)
            try:
                new_x, new_y = old_big_map_xy_to_17173_xy(copied["x"], copied["y"])
            except (KeyError, TypeError, ValueError, OverflowError):
                converted.append(copied)
                continue
            copied["x"] = new_x
            copied["y"] = new_y
            converted_points += 1
            converted.append(copied)
        output[key] = converted
    return _ordered_route_payload(output), converted_points


def convert_route_folder(
    input_dir: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    *,
    recursive: bool = True,
    overwrite: bool = False,
) -> RouteConversionReport:
    source_root = Path(input_dir).expanduser().resolve(strict=False)
    target_root = Path(output_dir).expanduser().resolve(strict=False)
    if not source_root.is_dir():
        raise ValueError(f"输入目录不存在：{source_root}")

    report = RouteConversionReport()
    target_root.mkdir(parents=True, exist_ok=True)

    for source in _iter_source_files(source_root, recursive):
        if source.name in {_PROGRESS_FILE, _VISIBILITY_FILE} or source.stem.endswith(_OUTPUT_SUFFIX):
            report.ignored += 1
            continue

        target = _target_path(source, source_root, target_root)
        if target.exists() and not overwrite:
            report.skipped += 1
            report.messages.append(f"[跳过] 输出已存在：{target}")
            continue

        try:
            with source.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            if not _is_route_payload(payload):
                report.ignored += 1
                report.messages.append(f"[忽略] 非路线文件：{source}")
                continue
            converted = normalize_route_payload(payload)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as handle:
                json.dump(converted, handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            report.errors += 1
            report.messages.append(f"[错误] {source}: {exc}")
            continue

        report.converted += 1
        report.messages.append(f"[完成] {source} -> {target}")

    return report


def convert_old_big_map_routes_in_place(
    input_dir: str | os.PathLike[str],
    *,
    recursive: bool = True,
) -> RouteConversionReport:
    source_root = Path(input_dir).expanduser().resolve(strict=False)
    if not source_root.is_dir():
        raise ValueError(f"输入目录不存在：{source_root}")

    report = RouteConversionReport()
    for source in _iter_source_files(source_root, recursive):
        if source.name in {_PROGRESS_FILE, _VISIBILITY_FILE} or source.stem.endswith(_OUTPUT_SUFFIX):
            report.ignored += 1
            continue

        try:
            with source.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            if not _is_route_payload(payload):
                report.ignored += 1
                report.messages.append(f"[忽略] 非路线文件：{source}")
                continue
            converted, point_count = convert_old_big_map_route_payload(payload)
            if point_count <= 0:
                report.skipped += 1
                report.messages.append(f"[跳过] 没有可转换的 x/y 点位：{source}")
                continue
            _write_json_atomic(source, converted)
        except Exception as exc:
            report.errors += 1
            report.messages.append(f"[错误] {source}: {exc}")
            continue

        report.converted += 1
        report.points_converted += point_count
        report.messages.append(f"[完成] {source}，转换 {point_count} 个点")

    return report
