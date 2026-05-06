"""Resolve MapCoordinateAdapter via global / per-route / per-annotation overrides."""

from __future__ import annotations

import config

from ui_island.services.resource_metadata import (
    coord_transform_from_payload,
    is_identity_coord_transform,
)
from ui_island.views.map_coordinates import MapCoordinateAdapter


def global_coord_transform() -> dict:
    return {
        "scale_x": float(getattr(config, "COORD_SCALE_X", 1.0) or 1.0),
        "scale_y": float(getattr(config, "COORD_SCALE_Y", 1.0) or 1.0),
        "offset_x": float(getattr(config, "COORD_OFFSET_X", 0.0) or 0.0),
        "offset_y": float(getattr(config, "COORD_OFFSET_Y", 0.0) or 0.0),
    }


def _adapter_from_transform(transform: dict | None) -> MapCoordinateAdapter:
    return MapCoordinateAdapter.from_dict(transform)


def resolve_route_adapter(route_payload: object) -> MapCoordinateAdapter:
    """Per-route override (key present) wins; otherwise fall back to global."""
    explicit = coord_transform_from_payload(route_payload)
    if explicit is not None:
        return _adapter_from_transform(explicit)
    return _adapter_from_transform(global_coord_transform())


def resolve_annotation_adapter(annotation_payload: object) -> MapCoordinateAdapter:
    """Annotation-file override (key present) wins; otherwise fall back to global."""
    explicit = coord_transform_from_payload(annotation_payload)
    if explicit is not None:
        return _adapter_from_transform(explicit)
    return _adapter_from_transform(global_coord_transform())


def is_global_identity() -> bool:
    return is_identity_coord_transform(global_coord_transform())
