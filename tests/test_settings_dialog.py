import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import config
from ui_island.dialogs.settings_dialog import SettingsDialog


class SettingsDialogMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_existing_unregistered_map_remains_selectable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_base_dir = config.BASE_DIR
            old_map_file = getattr(config, "MAP_FILE", "")
            try:
                config.BASE_DIR = tmp
                config.MAP_FILE = "maps/custom/big_map.png"
                path = Path(tmp, "maps", "custom", "big_map.png")
                path.parent.mkdir(parents=True)
                path.write_bytes(b"user map")

                dialog = SettingsDialog(None)
                self._app.processEvents()

                combo = dialog._map_file_combo
                self.assertIsNotNone(combo)
                self.assertTrue(combo.isEnabled())
                self.assertEqual(combo.currentData(), "maps/custom/big_map.png")
                self.assertIn("可能导致路线/标注偏移", combo.toolTip())
                dialog.close()
            finally:
                config.BASE_DIR = old_base_dir
                config.MAP_FILE = old_map_file


if __name__ == "__main__":
    unittest.main()
