"""Identity coordinate helpers for map pixels."""

from __future__ import annotations

from dataclasses import dataclass

import config


@dataclass(frozen=True)
class MapCoordinateAdapter:
    """Treat every stored point as the current map's pixel coordinate."""

    map_file: str = config.DEFAULT_MAP_FILE

    @classmethod
    def for_map_file(cls, map_file: object) -> "MapCoordinateAdapter":
        base_dir = getattr(config, "BASE_DIR", None)
        return cls(map_file=config.normalize_map_file(map_file, base_dir))

    @classmethod
    def for_current_config(cls) -> "MapCoordinateAdapter":
        return cls.for_map_file(getattr(config, "MAP_FILE", config.DEFAULT_MAP_FILE))

    @property
    def is_identity(self) -> bool:
        return True

    @property
    def warning(self) -> str:
        return ""

    def to_current(self, x: float, y: float) -> tuple[float, float]:
        return float(x), float(y)

    def to_internal(self, x: float, y: float) -> tuple[float, float]:
        return float(x), float(y)

    def threshold_to_internal(self, threshold: float) -> float:
        return float(threshold)


def current_adapter() -> MapCoordinateAdapter:
    return MapCoordinateAdapter.for_current_config()
