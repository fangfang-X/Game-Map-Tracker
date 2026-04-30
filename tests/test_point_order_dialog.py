import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSpinBox

from ui_island.dialogs.point_order_dialog import PointOrderDialog, _ORDER_SPIN_MAX_WIDTH


class PointOrderDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_spinbox_uses_current_position_and_full_range(self) -> None:
        dialog = PointOrderDialog(None, "Route 1", current_index=2, total_count=5)

        self.assertIsInstance(dialog.spin, QSpinBox)
        self.assertEqual(dialog.spin.minimum(), 1)
        self.assertEqual(dialog.spin.maximum(), 5)
        self.assertEqual(dialog.spin.value(), 3)
        self.assertEqual(dialog.spin.maximumWidth(), _ORDER_SPIN_MAX_WIDTH)

    def test_target_index_is_zero_based_and_clamped(self) -> None:
        dialog = PointOrderDialog(None, "Route 1", current_index=0, total_count=3)

        dialog.spin.setValue(3)

        self.assertEqual(dialog.target_index(), 2)


if __name__ == "__main__":
    unittest.main()
