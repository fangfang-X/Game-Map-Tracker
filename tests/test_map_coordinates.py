import unittest

from ui_island.views.map_coordinates import MapCoordinateAdapter


class MapCoordinateAdapterTests(unittest.TestCase):
    def test_default_adapter_is_identity(self) -> None:
        adapter = MapCoordinateAdapter.for_map_file("maps/卡洛西亚大陆/big_map_17173.png")

        self.assertTrue(adapter.is_identity)
        self.assertEqual(adapter.to_current(123, 456), (123.0, 456.0))
        self.assertEqual(adapter.to_internal(123, 456), (123.0, 456.0))
        self.assertEqual(adapter.threshold_to_internal(20), 20.0)
        self.assertEqual(adapter.warning, "")

    def test_from_dict_with_none_or_empty_returns_identity(self) -> None:
        for payload in (None, {}, "not a dict"):
            adapter = MapCoordinateAdapter.from_dict(payload)
            self.assertTrue(adapter.is_identity)

    def test_from_dict_reads_linear_params(self) -> None:
        adapter = MapCoordinateAdapter.from_dict(
            {"scale_x": 2.0, "scale_y": 0.5, "offset_x": 10.0, "offset_y": -20.0}
        )
        self.assertFalse(adapter.is_identity)
        self.assertEqual(adapter.to_current(100, 100), (210.0, 30.0))

    def test_round_trip_is_invertible(self) -> None:
        adapter = MapCoordinateAdapter.from_params(
            scale_x=1.5, scale_y=0.8, offset_x=37.5, offset_y=-12.25
        )
        for x, y in [(0, 0), (123.4, 567.8), (-50, 200), (8191, 8191)]:
            cx, cy = adapter.to_current(x, y)
            ix, iy = adapter.to_internal(cx, cy)
            self.assertAlmostEqual(ix, x, places=6)
            self.assertAlmostEqual(iy, y, places=6)

    def test_zero_scale_falls_back_to_default(self) -> None:
        adapter = MapCoordinateAdapter.from_params(scale_x=0.0, scale_y=0.0)
        self.assertEqual(adapter.scale_x, 1.0)
        self.assertEqual(adapter.scale_y, 1.0)

    def test_threshold_scales_with_average(self) -> None:
        adapter = MapCoordinateAdapter.from_params(scale_x=2.0, scale_y=4.0)
        self.assertEqual(adapter.threshold_to_internal(30), 10.0)


if __name__ == "__main__":
    unittest.main()
