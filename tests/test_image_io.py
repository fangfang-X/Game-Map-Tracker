import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from ui_island.services.image_io import imread_unicode


class ImageIoTests(unittest.TestCase):
    def test_imread_unicode_reads_image_from_chinese_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp, "卡洛西亚大陆")
            image_dir.mkdir()
            image_path = image_dir / "底图.png"
            source = np.zeros((3, 4, 3), dtype=np.uint8)
            source[:, :] = (10, 20, 30)
            ok, encoded = cv2.imencode(".png", source)
            self.assertTrue(ok)
            image_path.write_bytes(encoded.tobytes())

            loaded = imread_unicode(image_path)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.shape, source.shape)
            np.testing.assert_array_equal(loaded, source)

    def test_imread_unicode_returns_none_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(imread_unicode(Path(tmp, "卡洛西亚大陆", "missing.png")))

    def test_imread_unicode_returns_none_for_invalid_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp, "卡洛西亚大陆", "broken.png")
            image_path.parent.mkdir()
            image_path.write_bytes(b"not an image")

            self.assertIsNone(imread_unicode(image_path))


if __name__ == "__main__":
    unittest.main()
