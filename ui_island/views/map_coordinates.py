"""Linear coordinate adapter between stored (raw) coords and rendering pixels."""

from __future__ import annotations

from dataclasses import dataclass

import config


_DEFAULT_SCALE_X = 1.0
_DEFAULT_SCALE_Y = 1.0
_DEFAULT_OFFSET_X = 0.0
_DEFAULT_OFFSET_Y = 0.0
_MIN_SCALE_ABS = 1e-9


@dataclass(frozen=True)
class MapCoordinateAdapter:
    """Linear map between stored coords and the current map's pixel coords.

    Convention:
        to_current(x_internal, y_internal) -> rendering pixel (current map space)
        to_internal(x_current, y_current) -> stored coord (raw / user file space)

    With identity params (scale=1, offset=0) both directions are no-ops, which
    matches the historic behaviour for files that already store 17173 pixels.
    """

    map_file: str = config.DEFAULT_MAP_FILE
    scale_x: float = _DEFAULT_SCALE_X
    scale_y: float = _DEFAULT_SCALE_Y
    offset_x: float = _DEFAULT_OFFSET_X
    offset_y: float = _DEFAULT_OFFSET_Y

    @classmethod
    def for_map_file(cls, map_file: object) -> "MapCoordinateAdapter":
        base_dir = getattr(config, "BASE_DIR", None)
        return cls(map_file=config.normalize_map_file(map_file, base_dir))

    @classmethod
    def for_current_config(cls) -> "MapCoordinateAdapter":
        return cls.from_params(
            scale_x=_coerce_float(getattr(config, "COORD_SCALE_X", _DEFAULT_SCALE_X), _DEFAULT_SCALE_X),
            scale_y=_coerce_float(getattr(config, "COORD_SCALE_Y", _DEFAULT_SCALE_Y), _DEFAULT_SCALE_Y),
            offset_x=_coerce_float(getattr(config, "COORD_OFFSET_X", _DEFAULT_OFFSET_X), _DEFAULT_OFFSET_X),
            offset_y=_coerce_float(getattr(config, "COORD_OFFSET_Y", _DEFAULT_OFFSET_Y), _DEFAULT_OFFSET_Y),
            map_file=getattr(config, "MAP_FILE", config.DEFAULT_MAP_FILE),
        )

    @classmethod
    def from_params(
        cls,
        scale_x: float = _DEFAULT_SCALE_X,
        scale_y: float = _DEFAULT_SCALE_Y,
        offset_x: float = _DEFAULT_OFFSET_X,
        offset_y: float = _DEFAULT_OFFSET_Y,
        *,
        map_file: object = None,
    ) -> "MapCoordinateAdapter":
        sx = _sanitize_scale(scale_x, _DEFAULT_SCALE_X)
        sy = _sanitize_scale(scale_y, _DEFAULT_SCALE_Y)
        ox = _sanitize_offset(offset_x, _DEFAULT_OFFSET_X)
        oy = _sanitize_offset(offset_y, _DEFAULT_OFFSET_Y)
        if map_file is None:
            base_dir = getattr(config, "BASE_DIR", None)
            resolved_map = config.normalize_map_file(
                getattr(config, "MAP_FILE", config.DEFAULT_MAP_FILE),
                base_dir,
            )
        else:
            base_dir = getattr(config, "BASE_DIR", None)
            resolved_map = config.normalize_map_file(map_file, base_dir)
        return cls(
            map_file=resolved_map,
            scale_x=sx,
            scale_y=sy,
            offset_x=ox,
            offset_y=oy,
        )

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        map_file: object = None,
    ) -> "MapCoordinateAdapter":
        if not isinstance(payload, dict):
            return cls.from_params(map_file=map_file)
        return cls.from_params(
            scale_x=_coerce_float(payload.get("scale_x"), _DEFAULT_SCALE_X),
            scale_y=_coerce_float(payload.get("scale_y"), _DEFAULT_SCALE_Y),
            offset_x=_coerce_float(payload.get("offset_x"), _DEFAULT_OFFSET_X),
            offset_y=_coerce_float(payload.get("offset_y"), _DEFAULT_OFFSET_Y),
            map_file=map_file,
        )

    @property
    def is_identity(self) -> bool:
        return (
            self.scale_x == _DEFAULT_SCALE_X
            and self.scale_y == _DEFAULT_SCALE_Y
            and self.offset_x == _DEFAULT_OFFSET_X
            and self.offset_y == _DEFAULT_OFFSET_Y
        )

    @property
    def warning(self) -> str:
        return ""

    def to_current(self, x: float, y: float) -> tuple[float, float]:
        cx = float(x) * self.scale_x + self.offset_x
        cy = float(y) * self.scale_y + self.offset_y
        return cx, cy

    def to_internal(self, x: float, y: float) -> tuple[float, float]:
        ix = (float(x) - self.offset_x) / self.scale_x
        iy = (float(y) - self.offset_y) / self.scale_y
        return ix, iy

    def threshold_to_internal(self, threshold: float) -> float:
        avg_scale = (abs(self.scale_x) + abs(self.scale_y)) / 2.0
        if avg_scale < _MIN_SCALE_ABS:
            return float(threshold)
        return float(threshold) / avg_scale

    def to_dict(self) -> dict:
        return {
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }


def _coerce_float(value: object, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sanitize_scale(value: object, default: float) -> float:
    coerced = _coerce_float(value, default)
    if abs(coerced) < _MIN_SCALE_ABS:
        return default
    return coerced


def _sanitize_offset(value: object, default: float) -> float:
    return _coerce_float(value, default)


def current_adapter() -> MapCoordinateAdapter:
    return MapCoordinateAdapter.for_current_config()
