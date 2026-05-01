import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import config
from Plan_SIFT import sift_tracker


class SiftTrackerCacheTests(unittest.TestCase):
    def test_has_valid_descriptor_cache_returns_false_without_cache_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp, "map.png")
            map_path.write_bytes(b"map")

            with patch.object(sift_tracker, "_CACHE_DIR", Path(tmp, "cache")):
                self.assertFalse(sift_tracker.has_valid_descriptor_cache(str(map_path)))

    def test_has_valid_descriptor_cache_accepts_saved_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp, "map.png")
            map_path.write_bytes(b"map")
            keypoints = [cv2.KeyPoint(x=1.0, y=2.0, size=3.0)]
            descriptors = np.zeros((1, 128), dtype=np.float32)

            with patch.object(sift_tracker, "_CACHE_DIR", Path(tmp, "cache")):
                sift_tracker._save_descriptor_cache(str(map_path), keypoints, descriptors)
                self.assertTrue(sift_tracker.has_valid_descriptor_cache(str(map_path)))

    def test_has_valid_descriptor_cache_rejects_changed_map_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp, "map.png")
            map_path.write_bytes(b"map")
            keypoints = [cv2.KeyPoint(x=1.0, y=2.0, size=3.0)]
            descriptors = np.zeros((1, 128), dtype=np.float32)

            with patch.object(sift_tracker, "_CACHE_DIR", Path(tmp, "cache")):
                sift_tracker._save_descriptor_cache(str(map_path), keypoints, descriptors)
                map_path.write_bytes(b"changed map")
                self.assertFalse(sift_tracker.has_valid_descriptor_cache(str(map_path)))

    def test_has_valid_descriptor_cache_rejects_changed_clahe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp, "map.png")
            map_path.write_bytes(b"map")
            keypoints = [cv2.KeyPoint(x=1.0, y=2.0, size=3.0)]
            descriptors = np.zeros((1, 128), dtype=np.float32)

            with patch.object(sift_tracker, "_CACHE_DIR", Path(tmp, "cache")):
                old_clahe = config.SIFT_CLAHE_LIMIT
                try:
                    config.SIFT_CLAHE_LIMIT = 3.0
                    sift_tracker._save_descriptor_cache(str(map_path), keypoints, descriptors)
                    config.SIFT_CLAHE_LIMIT = 4.0
                    self.assertFalse(sift_tracker.has_valid_descriptor_cache(str(map_path)))
                finally:
                    config.SIFT_CLAHE_LIMIT = old_clahe

    def test_has_valid_descriptor_cache_rejects_changed_cache_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp, "map.png")
            map_path.write_bytes(b"map")
            keypoints = [cv2.KeyPoint(x=1.0, y=2.0, size=3.0)]
            descriptors = np.zeros((1, 128), dtype=np.float32)

            with patch.object(sift_tracker, "_CACHE_DIR", Path(tmp, "cache")):
                old_version = sift_tracker._CACHE_VERSION
                try:
                    sift_tracker._CACHE_VERSION = 1
                    sift_tracker._save_descriptor_cache(str(map_path), keypoints, descriptors)
                    sift_tracker._CACHE_VERSION = 2
                    self.assertFalse(sift_tracker.has_valid_descriptor_cache(str(map_path)))
                finally:
                    sift_tracker._CACHE_VERSION = old_version


if __name__ == "__main__":
    unittest.main()
