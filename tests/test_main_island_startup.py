import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np

import config
import main_island


class _FakeApplication:
    def __init__(self, _argv) -> None:
        pass

    def exec(self) -> int:
        return 0


class MainIslandStartupTests(unittest.TestCase):
    def test_minimap_configured_requires_complete_positive_region(self) -> None:
        valid = {"top": 1, "left": 2, "width": 150, "height": 151}
        invalid_cases = [
            None,
            {},
            {"top": 1, "left": 2, "width": 150},
            {"top": "x", "left": 2, "width": 150, "height": 150},
            {"top": 1, "left": 2, "width": 0, "height": 150},
            {"top": -1, "left": 2, "width": 150, "height": 150},
        ]

        with patch.dict(config.settings, {"MINIMAP": valid}, clear=False):
            self.assertTrue(main_island._minimap_is_configured())

        for value in invalid_cases:
            with self.subTest(value=value):
                with patch.dict(config.settings, {"MINIMAP": value}, clear=False):
                    self.assertFalse(main_island._minimap_is_configured())

    def test_selector_runs_for_missing_minimap_without_requiring_map(self) -> None:
        calls = []

        def calibrate():
            calls.append("selector")
            return False

        with (
            patch.object(sys, "argv", ["main_island.py"]),
            patch("main_island.QApplication", _FakeApplication),
            patch.dict(config.settings, {"MINIMAP": {}}, clear=False),
            patch("main_island.run_minimap_calibrator", side_effect=calibrate),
        ):
            self.assertEqual(main_island.main(), 0)

        self.assertEqual(calls, ["selector"])

    def test_no_selector_skips_missing_minimap_prompt(self) -> None:
        with (
            patch.object(sys, "argv", ["main_island.py", "--no-selector"]),
            patch("main_island.QApplication", _FakeApplication),
            patch.dict(config.settings, {"MINIMAP": {}}, clear=False),
            patch("main_island.run_minimap_calibrator") as calibrator,
            patch("main_island.build_tracker", return_value=(main_island.MissingMapTracker(""), None)),
            patch("main_island.RouteManager"),
            patch("main_island.IslandWindow") as window_cls,
        ):
            window_cls.return_value.show.return_value = None
            window_cls.return_value.start_deferred_tracker_load.return_value = None
            self.assertEqual(main_island.main(), 0)

        calibrator.assert_not_called()

    def test_force_selector_runs_even_with_valid_minimap(self) -> None:
        with (
            patch.object(sys, "argv", ["main_island.py", "--force-selector"]),
            patch("main_island.QApplication", _FakeApplication),
            patch.dict(
                config.settings,
                {"MINIMAP": {"top": 1, "left": 1, "width": 150, "height": 150}},
                clear=False,
            ),
            patch("main_island.run_minimap_calibrator", return_value=False) as calibrator,
        ):
            self.assertEqual(main_island.main(), 0)

        calibrator.assert_called_once()

    def test_build_tracker_defers_sift_when_cache_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_base_dir = config.BASE_DIR
            old_map_file = getattr(config, "MAP_FILE", "")
            try:
                config.BASE_DIR = tmp
                config.MAP_FILE = "maps/map.png"
                image_path = Path(tmp, "maps", "map.png")
                image_path.parent.mkdir()
                source = np.zeros((3, 4, 3), dtype=np.uint8)
                self.assertTrue(cv2.imwrite(str(image_path), source))

                with patch("Plan_SIFT.has_valid_descriptor_cache", return_value=False), patch(
                    "Plan_SIFT.SiftTracker"
                ) as tracker_cls:
                    tracker, factory = main_island.build_tracker()

                self.assertIsInstance(tracker, main_island.LoadingMapTracker)
                self.assertIs(factory, tracker_cls)
            finally:
                config.BASE_DIR = old_base_dir
                config.MAP_FILE = old_map_file


if __name__ == "__main__":
    unittest.main()
