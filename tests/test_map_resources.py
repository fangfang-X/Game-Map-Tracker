import tempfile
import unittest
from pathlib import Path

import config


class ConfigMapResourcesTests(unittest.TestCase):
    def test_default_map_file_is_unselected(self) -> None:
        self.assertEqual(config.DEFAULT_MAP_FILE, "")
        self.assertEqual(config.DEFAULT_CONFIG["MAP_FILE"], "")
        self.assertNotIn("LOGIC_MAP_PATH", config.DEFAULT_CONFIG)

    def test_iter_map_files_lists_all_user_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Path(root, "maps", "big_map.png").parent.mkdir(parents=True)
            Path(root, "maps", "big_map.png").write_bytes(b"user root maps")
            Path(root, "maps", "卡洛西亚大陆").mkdir()
            Path(root, "maps", "卡洛西亚大陆", "big_map.png").write_bytes(b"user nested")
            Path(root, "maps", "卡洛西亚大陆", "big_map_17173.png").write_bytes(b"17173")
            Path(root, "maps", "卡洛西亚大陆", "map_gmt_small.jpg").write_bytes(b"small")
            Path(root, "maps", "ignored.txt").write_text("not an image", encoding="utf-8")

            self.assertEqual(
                config.iter_map_files(str(root)),
                [
                    "maps/big_map.png",
                    "maps/卡洛西亚大陆/big_map.png",
                    "maps/卡洛西亚大陆/big_map_17173.png",
                    "maps/卡洛西亚大陆/map_gmt_small.jpg",
                ],
            )
            self.assertEqual(config.iter_map_files_in_directory(str(root), "maps"), ["maps/big_map.png"])

    def test_import_map_file_copies_without_registry_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Path(tmp, "source.png")
            source.write_bytes(b"map payload")

            rel = config.import_map_file(str(source), destination_dir="maps/custom", base_dir=str(root))

            self.assertEqual(rel, "maps/custom/source.png")
            self.assertTrue(Path(root, rel).exists())
            self.assertFalse(Path(root, "maps", "custom", "source_2.png").exists())

if __name__ == "__main__":
    unittest.main()
