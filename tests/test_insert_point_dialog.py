import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSpinBox

from ui_island.dialogs.insert_point_dialog import (
    InsertPointDialog,
    _POSITION_SPIN_MAX_WIDTH,
    _ROUTE_NAME_MAX_WIDTH,
    _ROUTE_NAME_MIN_WIDTH,
)
from ui_island.widgets.route_widgets import ElidedCheckBox


class InsertPointDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _dialog(self, candidates: list[dict]) -> InsertPointDialog:
        return InsertPointDialog(None, 12, 34, candidates)

    def test_single_route_uses_suggested_position_as_editable_default(self) -> None:
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": "Route 1", "points_count": 4, "suggested_index": 2}
        ])

        row = dialog._rows[0]

        self.assertIsInstance(row["spin"], QSpinBox)
        self.assertEqual(row["spin"].minimum(), 1)
        self.assertEqual(row["spin"].maximum(), 5)
        self.assertEqual(row["spin"].value(), 3)

    def test_long_route_name_is_elided_with_bounded_width(self) -> None:
        long_name = "Very Long Route Name " * 20
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": long_name, "points_count": 4, "suggested_index": 2}
        ])

        checkbox = dialog._rows[0]["checkbox"]

        self.assertIsInstance(checkbox, ElidedCheckBox)
        self.assertEqual(checkbox.full_text(), long_name)
        self.assertEqual(checkbox.toolTip(), long_name)
        self.assertEqual(checkbox.minimumWidth(), _ROUTE_NAME_MIN_WIDTH)
        self.assertEqual(checkbox.maximumWidth(), _ROUTE_NAME_MAX_WIDTH)

    def test_position_spinbox_uses_bounded_width(self) -> None:
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": "Route 1", "points_count": 40, "suggested_index": 20}
        ])

        spin = dialog._rows[0]["spin"]

        self.assertEqual(spin.maximumWidth(), _POSITION_SPIN_MAX_WIDTH)

    def test_multi_route_rows_are_all_editable(self) -> None:
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": "Route 1", "points_count": 4, "suggested_index": 2},
            {"route_id": "route-2", "display_label": "Route 2", "points_count": 9, "suggested_index": 0},
        ])

        self.assertTrue(all(isinstance(row["spin"], QSpinBox) for row in dialog._rows))
        self.assertEqual([row["spin"].value() for row in dialog._rows], [3, 1])
        self.assertEqual([row["spin"].maximum() for row in dialog._rows], [5, 10])

    def test_unchanged_positions_return_no_overrides(self) -> None:
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": "Route 1", "points_count": 4, "suggested_index": 2},
            {"route_id": "route-2", "display_label": "Route 2", "points_count": 9, "suggested_index": 0},
        ])

        self.assertEqual(dialog.overrides(), {})

    def test_changed_position_returns_zero_based_override_for_that_route_only(self) -> None:
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": "Route 1", "points_count": 4, "suggested_index": 2},
            {"route_id": "route-2", "display_label": "Route 2", "points_count": 9, "suggested_index": 0},
        ])

        dialog._rows[1]["spin"].setValue(4)

        self.assertEqual(dialog.overrides(), {"route-2": 3})

    def test_unchecked_route_is_excluded_from_selection_and_overrides(self) -> None:
        dialog = self._dialog([
            {"route_id": "route-1", "display_label": "Route 1", "points_count": 4, "suggested_index": 2},
            {"route_id": "route-2", "display_label": "Route 2", "points_count": 9, "suggested_index": 0},
        ])

        dialog._rows[0]["checkbox"].setChecked(False)
        dialog._rows[0]["spin"].setValue(1)
        dialog._rows[1]["spin"].setValue(4)

        self.assertEqual(dialog.selected_route_ids(), ["route-2"])
        self.assertEqual(dialog.overrides(), {"route-2": 3})


if __name__ == "__main__":
    unittest.main()
