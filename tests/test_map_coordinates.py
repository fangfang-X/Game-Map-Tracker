import unittest

from ui_island.views.map_coordinates import MapCoordinateAdapter


class MapCoordinateAdapterTests(unittest.TestCase):
    def test_coordinates_are_raw_pixels(self) -> None:
        adapter = MapCoordinateAdapter.for_map_file("maps/卡洛西亚大陆/big_map_17173.png")

        self.assertTrue(adapter.is_identity)
        self.assertEqual(adapter.to_current(123, 456), (123.0, 456.0))
        self.assertEqual(adapter.to_internal(123, 456), (123.0, 456.0))
        self.assertEqual(adapter.threshold_to_internal(20), 20.0)
        self.assertEqual(adapter.warning, "")


if __name__ == "__main__":
    unittest.main()
