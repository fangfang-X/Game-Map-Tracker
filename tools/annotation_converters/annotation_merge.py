"""Merge two current annotation files with conservative de-duplication."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from pathlib import Path

from ui_island.services import resource_metadata

from .base import AnnotationConversionReport, UnsupportedAnnotationFormatError, read_json, write_json_atomic

_OUTPUT_PREFIX = "annotations_merged"
_COORDINATE_DUPLICATE_TOLERANCE = 3.0
_PAYLOAD_KEY_ORDER = (
    "id",
    "generatedAt",
    "format_version",
    "mapId",
    "types",
    "pointsByType",
)


def _format_version(payload: dict) -> str:
    return str(payload.get("format_version") or "").strip()


def _ordered_payload(payload: dict) -> dict:
    ordered = {key: payload[key] for key in _PAYLOAD_KEY_ORDER if key in payload}
    ordered.update((key, value) for key, value in payload.items() if key not in ordered)
    return ordered


def _finalize_payload(payload: dict) -> dict:
    output = dict(payload)
    output["generatedAt"] = datetime.now(timezone.utc).isoformat()
    output.pop("id", None)
    resource_metadata.ensure_metadata(output, include_id=True, enable_versions_policy="preserve")
    return _ordered_payload(output)


def _type_items_by_id(types: object) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not isinstance(types, list):
        return result
    for item in types:
        if not isinstance(item, dict):
            continue
        type_id = str(item.get("typeId") or "").strip()
        if type_id and type_id not in result:
            result[type_id] = dict(item)
    return result


def _point_type_id(bucket_type_id: object, point: dict) -> str:
    return str(point.get("typeId") or bucket_type_id or "").strip()


def _point_id(point: dict) -> str:
    raw_id = point.get("id")
    return "" if raw_id is None else str(raw_id).strip()


def _point_xy(point: dict) -> tuple[float, float] | None:
    try:
        x = float(point["x"])
        y = float(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return x, y


def _sync_type_counts(payload: dict, *, source_type_items: dict[str, dict] | None = None) -> None:
    points_by_type = payload.get("pointsByType")
    if not isinstance(points_by_type, dict):
        points_by_type = {}
        payload["pointsByType"] = points_by_type

    types = payload.get("types")
    if not isinstance(types, list):
        types = []
        payload["types"] = types

    source_type_items = source_type_items or {}
    type_items: dict[str, dict] = {}
    for item in types:
        if not isinstance(item, dict):
            continue
        type_id = str(item.get("typeId") or "").strip()
        if type_id and type_id not in type_items:
            type_items[type_id] = item
    for raw_type_id, points in points_by_type.items():
        type_id = str(raw_type_id or "").strip()
        if not type_id:
            continue
        item = type_items.get(type_id)
        if item is None:
            source_item = source_type_items.get(type_id)
            if source_item is not None:
                item = dict(source_item)
            else:
                first_point = points[0] if isinstance(points, list) and points and isinstance(points[0], dict) else {}
                item = {
                    "typeId": type_id,
                    "type": str(first_point.get("type") or type_id),
                    "groupId": "",
                    "group": "其他",
                    "iconPath": f"{type_id}.png",
                }
            item["typeId"] = type_id
            types.append(item)
            type_items[type_id] = item
        item["count"] = len(points) if isinstance(points, list) else 0

    for item in types:
        if not isinstance(item, dict):
            continue
        type_id = str(item.get("typeId") or "").strip()
        if type_id and type_id not in points_by_type:
            item["count"] = 0


def _has_near_coordinate(existing: list[tuple[float, float]], xy: tuple[float, float]) -> bool:
    for current_x, current_y in existing:
        if math.hypot(current_x - xy[0], current_y - xy[1]) <= _COORDINATE_DUPLICATE_TOLERANCE:
            return True
    return False


def merge_annotation_payloads(
    target_payload: dict,
    source_payload: dict,
    report: AnnotationConversionReport | None = None,
    *,
    require_matching_format_version: bool = True,
) -> dict:
    if not isinstance(target_payload, dict):
        raise ValueError("目标标注 JSON 顶层必须是对象")
    if not isinstance(source_payload, dict):
        raise ValueError("原标注 JSON 顶层必须是对象")

    if require_matching_format_version:
        target_version = _format_version(target_payload)
        source_version = _format_version(source_payload)
        if not target_version or not source_version:
            raise UnsupportedAnnotationFormatError("标注文件缺少 format_version，无法合并。")
        if target_version != source_version:
            raise UnsupportedAnnotationFormatError("格式版本不同，无法合并。")

    target_points = target_payload.get("pointsByType")
    source_points = source_payload.get("pointsByType")
    if not isinstance(target_points, dict):
        raise ValueError("目标标注 JSON 缺少 pointsByType 对象")
    if not isinstance(source_points, dict):
        raise ValueError("原标注 JSON 缺少 pointsByType 对象")

    report = report or AnnotationConversionReport()
    merged = dict(target_payload)
    merged["types"] = [dict(item) for item in target_payload.get("types", []) if isinstance(item, dict)]
    merged_points: dict[str, list[dict]] = {}
    existing_ids: set[str] = set()
    coordinate_index: dict[str, list[tuple[float, float]]] = {}

    for raw_type_id, points in target_points.items():
        type_id = str(raw_type_id or "").strip()
        if not isinstance(points, list):
            merged_points[type_id] = []
            continue
        copied_points: list[dict] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            copied_point = dict(point)
            copied_points.append(copied_point)
            point_id = _point_id(copied_point)
            if point_id:
                existing_ids.add(point_id)
            xy = _point_xy(copied_point)
            if xy is not None:
                coordinate_index.setdefault(_point_type_id(type_id, copied_point), []).append(xy)
        merged_points[type_id] = copied_points

    source_type_items = _type_items_by_id(source_payload.get("types"))
    target_type_items = _type_items_by_id(merged["types"])
    for raw_type_id, points in source_points.items():
        bucket_type_id = str(raw_type_id or "").strip()
        if not isinstance(points, list):
            report.skipped_points += 1
            continue
        for point in points:
            if not isinstance(point, dict):
                report.skipped_points += 1
                continue
            type_id = _point_type_id(bucket_type_id, point)
            if not type_id:
                report.skipped_points += 1
                continue

            point_id = _point_id(point)
            if point_id and point_id in existing_ids:
                report.deduplicated_points += 1
                continue

            xy = _point_xy(point)
            if xy is None:
                report.skipped_points += 1
                continue
            if _has_near_coordinate(coordinate_index.get(type_id, []), xy):
                report.deduplicated_points += 1
                continue

            if type_id not in target_type_items and type_id in source_type_items:
                copied_type = dict(source_type_items[type_id])
                merged["types"].append(copied_type)
                target_type_items[type_id] = copied_type

            copied_point = dict(point)
            copied_point["typeId"] = type_id
            merged_points.setdefault(type_id, []).append(copied_point)
            coordinate_index.setdefault(type_id, []).append(xy)
            if point_id:
                existing_ids.add(point_id)
            report.converted_points += 1

    merged["pointsByType"] = merged_points
    if "mapId" not in merged and "mapId" in source_payload:
        merged["mapId"] = source_payload["mapId"]
    _sync_type_counts(merged, source_type_items=source_type_items)
    return _finalize_payload(merged)


def convert_annotation_merge_file(
    source_file: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    *,
    merge_with: str | os.PathLike[str] | None,
) -> AnnotationConversionReport:
    source_path = Path(source_file).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise FileNotFoundError(f"原标注文件不存在：{source_path}")
    if merge_with is None:
        raise ValueError("标注文件合并需要选择目标标注文件")

    target_path = Path(merge_with).expanduser().resolve(strict=False)
    if not target_path.is_file():
        raise FileNotFoundError(f"目标标注文件不存在：{target_path}")

    source_payload = read_json(source_path)
    target_payload = read_json(target_path)
    report = AnnotationConversionReport()
    output_payload = merge_annotation_payloads(target_payload, source_payload, report)

    output_root = Path(output_dir).expanduser().resolve(strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / resource_metadata.annotation_output_name(output_root, prefix=_OUTPUT_PREFIX)
    write_json_atomic(output_path, output_payload)
    report.output_path = str(output_path)
    report.messages.append(f"[完成] 已写入：{output_path}")
    return report
