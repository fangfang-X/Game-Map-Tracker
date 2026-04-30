import json
import tempfile
import unittest
from pathlib import Path

from tools.fetch_17173_points import latlng_to_xy
from tools.route_format_converter import (
    convert_old_big_map_route_payload,
    convert_old_big_map_routes_in_place,
    convert_route_folder,
    normalize_route_payload,
    old_big_map_xy_to_17173_xy,
)

_MAP_HASH = "a" * 32


def _old_xy_from_latlng(latitude: float, longitude: float) -> tuple[float, float]:
    return 5824.0800 * longitude + 7217.5810, -5822.8413 * latitude + 6602.7721


class RouteFormatConverterTests(unittest.TestCase):
    def test_normalize_route_payload_removes_map_metadata_and_preserves_unknown_fields(self) -> None:
        payload = normalize_route_payload(
            {
                "id": "not-valid",
                "name": "路线",
                "notes": "说明",
                "loop": True,
                "map_hash": _MAP_HASH,
                "map_hashs": [_MAP_HASH],
                "map_info": {"map_id": "10003", "map_name": "卡洛西亚大陆"},
                "coordinate_space_id": "legacy_big_map_unmapped",
                "annotation_hash": "b" * 32,
                "custom": {"kept": True},
                "points": [{"x": 1, "y": 2}],
            }
        )

        keys = list(payload)
        self.assertEqual(payload["id"], "not-valid")
        self.assertEqual(payload["annotation_hash"], "b" * 32)
        self.assertEqual(payload["custom"], {"kept": True})
        self.assertNotIn("format_version", payload)
        self.assertNotIn("enable_versions", payload)
        self.assertNotIn("coordinate_space_id", payload)
        self.assertNotIn("map_hash", payload)
        self.assertNotIn("map_hashs", payload)
        self.assertNotIn("map_info", payload)
        self.assertLess(keys.index("notes"), keys.index("loop"))

    def test_convert_route_folder_writes_new_files_without_inventing_map_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "in"
            output_dir = root / "out"
            category = input_dir / "分类"
            category.mkdir(parents=True)
            (category / "route.json").write_text(
                json.dumps({"name": "路线", "points": [{"x": 1, "y": 2}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (input_dir / "progress.json").write_text("{}", encoding="utf-8")
            (input_dir / "metadata.json").write_text(json.dumps({"name": "not route"}), encoding="utf-8")

            report = convert_route_folder(input_dir, output_dir)

            self.assertEqual(report.converted, 1)
            self.assertEqual(report.ignored, 2)
            target = next((output_dir / "分类").glob("route_*.json"))
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertNotIn("map_info", payload)
            self.assertNotIn("map_hashs", payload)
            self.assertNotIn("coordinate_space_id", payload)
            self.assertEqual(payload["name"], "路线")

    def test_normalize_route_payload_keeps_existing_format_metadata(self) -> None:
        source_info = {"map_id": "source", "map_name": "源地图"}

        payload = normalize_route_payload(
            {
                "id": "f" * 32,
                "format_version": "old-format",
                "enable_versions": ["old-format"],
                "map_hashs": [_MAP_HASH],
                "map_info": source_info,
                "coordinate_space_id": "legacy_big_map_unmapped",
                "points": [],
            }
        )

        self.assertEqual(payload["id"], "f" * 32)
        self.assertEqual(payload["format_version"], "old-format")
        self.assertEqual(payload["enable_versions"], ["old-format"])
        self.assertNotIn("coordinate_space_id", payload)
        self.assertNotIn("map_info", payload)
        self.assertNotIn("map_hashs", payload)

    def test_old_big_map_xy_to_17173_xy_uses_reversed_fit_formula(self) -> None:
        old_x, old_y = _old_xy_from_latlng(1.2, -0.75)

        self.assertEqual(old_big_map_xy_to_17173_xy(old_x, old_y), latlng_to_xy(1.2, -0.75))

    def test_convert_old_big_map_route_payload_converts_points_and_removes_metadata(self) -> None:
        old_x, old_y = _old_xy_from_latlng(0.7, -0.4)
        expected_x, expected_y = latlng_to_xy(0.7, -0.4)

        payload, point_count = convert_old_big_map_route_payload(
            {
                "name": "旧路线",
                "map_hash": _MAP_HASH,
                "map_hashs": [_MAP_HASH],
                "map_info": {"map_id": "10003", "map_name": "卡洛西亚大陆"},
                "coordinate_space_id": "legacy_big_map_unmapped",
                "points": [
                    {"x": old_x, "y": old_y, "label": "A"},
                    {"label": "missing xy"},
                ],
            }
        )

        self.assertEqual(point_count, 1)
        self.assertEqual(payload["points"][0]["x"], expected_x)
        self.assertEqual(payload["points"][0]["y"], expected_y)
        self.assertEqual(payload["points"][0]["label"], "A")
        self.assertEqual(payload["points"][1], {"label": "missing xy"})
        self.assertNotIn("map_hash", payload)
        self.assertNotIn("map_hashs", payload)
        self.assertNotIn("map_info", payload)
        self.assertNotIn("coordinate_space_id", payload)

    def test_convert_old_big_map_routes_in_place_overwrites_source_and_skips_non_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            route_dir = root / "routes"
            route_dir.mkdir()
            old_x, old_y = _old_xy_from_latlng(0.5, -0.2)
            expected_x, expected_y = latlng_to_xy(0.5, -0.2)
            source = route_dir / "route.json"
            source.write_text(
                json.dumps(
                    {
                        "name": "旧路线",
                        "coordinate_space_id": "legacy_big_map_unmapped",
                        "points": [{"x": old_x, "y": old_y}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (route_dir / "progress.json").write_text("{}", encoding="utf-8")
            (route_dir / "metadata.json").write_text(json.dumps({"name": "not route"}), encoding="utf-8")

            report = convert_old_big_map_routes_in_place(route_dir)

            self.assertEqual(report.converted, 1)
            self.assertEqual(report.ignored, 2)
            self.assertEqual(report.points_converted, 1)
            self.assertFalse(any(route_dir.glob("*_新格式.json")))

            payload = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(payload["points"][0]["x"], expected_x)
            self.assertEqual(payload["points"][0]["y"], expected_y)
            self.assertNotIn("coordinate_space_id", payload)


if __name__ == "__main__":
    unittest.main()
