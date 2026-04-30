import json
import unittest
from pathlib import Path

from tools.fetch_17173_points import MAP_PIXEL_SIZE, latlng_to_xy


class Fetch17173PointsTests(unittest.TestCase):
    def test_latlng_to_xy_projects_to_big_map_17173_bounds(self) -> None:
        self.assertEqual(latlng_to_xy(1.4, -1.4), (36, 36))
        self.assertEqual(latlng_to_xy(0.0, 0.0), (8191, 8191))

    def test_latlng_to_xy_clamps_to_map_pixels(self) -> None:
        for latitude, longitude in ((0.0, 0.1), (-0.1, 0.0), (90.0, -180.0)):
            x, y = latlng_to_xy(latitude, longitude)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLess(x, MAP_PIXEL_SIZE)
            self.assertLess(y, MAP_PIXEL_SIZE)

    def test_generated_points_17173_uses_8192_coordinate_range(self) -> None:
        path = Path("annotations/points_17173.json")
        if not path.exists():
            self.skipTest("annotations/points_17173.json is not available")

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        points = [
            point
            for entries in (payload.get("pointsByType") or {}).values()
            for point in entries
            if isinstance(point, dict) and "x" in point and "y" in point
        ]

        self.assertTrue(points)
        self.assertGreater(max(point["x"] for point in points), 6400)
        self.assertGreater(max(point["y"] for point in points), 6400)
        self.assertTrue(all(0 <= point["x"] < MAP_PIXEL_SIZE for point in points))
        self.assertTrue(all(0 <= point["y"] < MAP_PIXEL_SIZE for point in points))


if __name__ == "__main__":
    unittest.main()
