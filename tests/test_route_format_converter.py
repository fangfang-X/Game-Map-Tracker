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
from ui_island.services import resource_metadata

_MAP_HASH = "a" * 32


def _old_xy_from_latlng(latitude: float, longitude: float) -> tuple[float, float]:
    return 5824.0800 * longitude + 7217.5810, -5822.8413 * latitude + 6602.7721


def _write_route(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_x, old_y = _old_xy_from_latlng(0.3, -0.2)
    path.write_text(
        json.dumps({"name": "路线", "points": [{"x": old_x, "y": old_y}]}, ensure_ascii=False),
        encoding="utf-8",
    )


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
        self.assertTrue(resource_metadata.HASH_RE.fullmatch(payload["id"]))
        self.assertEqual(payload["format_version"], resource_metadata.APP_FORMAT_VERSION)
        self.assertIn(resource_metadata.APP_FORMAT_VERSION, payload["enable_versions"])
        self.assertEqual(payload["annotation_hash"], "b" * 32)
        self.assertEqual(payload["custom"], {"kept": True})
        self.assertNotIn("color", payload)
        self.assertNotIn("coordinate_space_id", payload)
        self.assertNotIn("map_hash", payload)
        self.assertNotIn("map_hashs", payload)
        self.assertNotIn("map_info", payload)
        self.assertLess(keys.index("enable_versions"), keys.index("name"))
        self.assertLess(keys.index("notes"), keys.index("loop"))

    def test_convert_route_folder_writes_new_files_without_inventing_map_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "in"
            output_dir = root / "out"
            category = input_dir / "分类"
            category.mkdir(parents=True)
            old_x, old_y = _old_xy_from_latlng(0.3, -0.2)
            expected_x, expected_y = latlng_to_xy(0.3, -0.2)
            (category / "route.json").write_text(
                json.dumps({"name": "路线", "points": [{"x": old_x, "y": old_y}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (input_dir / "progress.json").write_text("{}", encoding="utf-8")
            (input_dir / "metadata.json").write_text(json.dumps({"name": "not route"}), encoding="utf-8")

            report = convert_route_folder(input_dir, output_dir)

            self.assertEqual(report.converted, 1)
            self.assertEqual(report.ignored, 2)
            self.assertEqual(report.points_converted, 1)
            target = next((output_dir / "分类").glob("route_*.json"))
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertNotIn("map_info", payload)
            self.assertNotIn("map_hashs", payload)
            self.assertNotIn("coordinate_space_id", payload)
            self.assertNotIn("color", payload)
            self.assertEqual(payload["name"], "路线")
            self.assertTrue(resource_metadata.HASH_RE.fullmatch(payload["id"]))
            self.assertEqual(payload["format_version"], resource_metadata.APP_FORMAT_VERSION)
            self.assertIn(resource_metadata.APP_FORMAT_VERSION, payload["enable_versions"])
            self.assertEqual(payload["points"][0]["x"], expected_x)
            self.assertEqual(payload["points"][0]["y"], expected_y)

    def test_convert_route_folder_rejects_same_input_and_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_route(root / "route.json")

            with self.assertRaisesRegex(ValueError, "输出目录不能和输入目录相同"):
                convert_route_folder(root, root)

    def test_convert_route_folder_rejects_recursive_output_inside_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "in"
            output_dir = input_dir / "converted"
            _write_route(input_dir / "route.json")

            with self.assertRaisesRegex(ValueError, "输出目录不能位于输入目录内部"):
                convert_route_folder(input_dir, output_dir, recursive=True)

    def test_convert_route_folder_allows_sibling_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "in"
            output_dir = root / "converted"
            _write_route(input_dir / "route.json")

            report = convert_route_folder(input_dir, output_dir, recursive=True)

            self.assertEqual(report.converted, 1)
            self.assertTrue((output_dir / "route_新格式.json").is_file())

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
        self.assertEqual(payload["format_version"], resource_metadata.APP_FORMAT_VERSION)
        self.assertEqual(payload["enable_versions"], ["old-format", resource_metadata.APP_FORMAT_VERSION])
        self.assertNotIn("coordinate_space_id", payload)
        self.assertNotIn("map_info", payload)
        self.assertNotIn("map_hashs", payload)

    def test_normalize_route_payload_keeps_valid_numeric_id(self) -> None:
        payload = normalize_route_payload({"id": "2026041913", "name": "路线", "points": []})

        self.assertEqual(payload["id"], "2026041913")
        self.assertEqual(payload["format_version"], resource_metadata.APP_FORMAT_VERSION)

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
        self.assertTrue(resource_metadata.HASH_RE.fullmatch(payload["id"]))
        self.assertEqual(payload["format_version"], resource_metadata.APP_FORMAT_VERSION)
        self.assertIn(resource_metadata.APP_FORMAT_VERSION, payload["enable_versions"])
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
            self.assertTrue(resource_metadata.HASH_RE.fullmatch(payload["id"]))
            self.assertEqual(payload["format_version"], resource_metadata.APP_FORMAT_VERSION)
            self.assertIn(resource_metadata.APP_FORMAT_VERSION, payload["enable_versions"])
            self.assertNotIn("coordinate_space_id", payload)


if __name__ == "__main__":
    unittest.main()
