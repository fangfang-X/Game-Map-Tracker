import json
import tempfile
import unittest
from pathlib import Path

from tools.annotation_format_converter import (
    convert_annotation_file,
    convert_old_big_map_annotation_payload,
)
from tools.fetch_17173_points import latlng_to_xy


def _old_xy_from_latlng(latitude: float, longitude: float) -> tuple[float, float]:
    return 5824.0800 * longitude + 7217.5810, -5822.8413 * latitude + 6602.7721


class AnnotationFormatConverterTests(unittest.TestCase):
    def test_convert_old_big_map_annotation_payload_converts_points_and_metadata(self) -> None:
        old_x, old_y = _old_xy_from_latlng(0.7, -0.4)
        expected_x, expected_y = latlng_to_xy(0.7, -0.4)

        payload, report = convert_old_big_map_annotation_payload(
            {
                "mapId": 4010,
                "types": [{"typeId": "flower", "type": "向阳花", "count": 99}],
                "pointsByType": {
                    "flower": [
                        {"x": old_x, "y": old_y, "label": "旧点", "type": "向阳花", "typeId": "flower"},
                        {"label": "缺坐标", "typeId": "flower"},
                    ]
                },
            }
        )

        self.assertEqual(report.converted_points, 1)
        self.assertEqual(report.skipped_points, 1)
        point = payload["pointsByType"]["flower"][0]
        self.assertEqual(point["x"], expected_x)
        self.assertEqual(point["y"], expected_y)
        self.assertEqual(point["label"], "旧点")
        self.assertEqual(payload["types"][0]["count"], 1)
        self.assertIn("id", payload)
        self.assertIn("format_version", payload)
        self.assertIn("enable_versions", payload)

    def test_convert_annotation_file_writes_converted_file_without_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_x, old_y = _old_xy_from_latlng(0.2, -0.3)
            old_file = root / "old.json"
            old_file.write_text(
                json.dumps(
                    {
                        "types": [{"typeId": "chest", "type": "宝箱"}],
                        "pointsByType": {"chest": [{"x": old_x, "y": old_y, "typeId": "chest"}]},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_dir = root / "annotations"

            report = convert_annotation_file(old_file, output_dir, merge=False)

            self.assertEqual(report.converted_points, 1)
            output_path = Path(report.output_path)
            self.assertTrue(output_path.is_file())
            self.assertEqual(output_path.parent, output_dir)
            self.assertRegex(output_path.name, r"^old_\d{8}01\.json$")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["pointsByType"]["chest"]), 1)
            self.assertEqual(payload["types"][0]["count"], 1)

    def test_convert_annotation_file_without_merge_increments_dated_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_x, old_y = _old_xy_from_latlng(0.2, -0.3)
            old_file = root / "old.json"
            old_file.write_text(
                json.dumps({"pointsByType": {"chest": [{"x": old_x, "y": old_y, "typeId": "chest"}]}}),
                encoding="utf-8",
            )
            output_dir = root / "annotations"
            output_dir.mkdir()
            first_report = convert_annotation_file(old_file, output_dir, merge=False)
            second_report = convert_annotation_file(old_file, output_dir, merge=False)

            self.assertRegex(Path(first_report.output_path).name, r"^old_\d{8}01\.json$")
            self.assertRegex(Path(second_report.output_path).name, r"^old_\d{8}02\.json$")

    def test_convert_annotation_file_merges_and_deduplicates_by_type_and_xy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate_old_x, duplicate_old_y = _old_xy_from_latlng(0.1, -0.1)
            duplicate_x, duplicate_y = latlng_to_xy(0.1, -0.1)
            ore_old_x, ore_old_y = _old_xy_from_latlng(0.4, -0.2)
            old_file = root / "old.json"
            old_file.write_text(
                json.dumps(
                    {
                        "types": [
                            {"typeId": "flower", "type": "向阳花", "count": 1},
                            {"typeId": "ore", "type": "矿石", "count": 1},
                        ],
                        "pointsByType": {
                            "flower": [
                                {
                                    "x": duplicate_old_x,
                                    "y": duplicate_old_y,
                                    "label": "旧重复点",
                                    "typeId": "flower",
                                }
                            ],
                            "ore": [{"x": ore_old_x, "y": ore_old_y, "label": "旧矿石", "typeId": "ore"}],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            new_file = root / "new.json"
            new_file.write_text(
                json.dumps(
                    {
                        "types": [{"typeId": "flower", "type": "向阳花", "count": 1}],
                        "pointsByType": {
                            "flower": [
                                {
                                    "x": duplicate_x,
                                    "y": duplicate_y,
                                    "label": "新推送点",
                                    "typeId": "flower",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = convert_annotation_file(old_file, root / "annotations", merge=True, merge_with=new_file)

            self.assertEqual(report.converted_points, 2)
            self.assertEqual(report.deduplicated_points, 1)
            payload = json.loads(Path(report.output_path).read_text(encoding="utf-8"))
            self.assertEqual([point["label"] for point in payload["pointsByType"]["flower"]], ["新推送点"])
            self.assertEqual(payload["pointsByType"]["ore"][0]["label"], "旧矿石")
            counts = {item["typeId"]: item["count"] for item in payload["types"]}
            self.assertEqual(counts["flower"], 1)
            self.assertEqual(counts["ore"], 1)


if __name__ == "__main__":
    unittest.main()
