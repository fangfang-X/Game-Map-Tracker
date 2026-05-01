import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from ui_island.dialogs.annotation_preset_dialog import AnnotationPresetDialog
from ui_island.widgets.annotation_type_widgets import AnnotationGroupSection


class _PresetParent(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.annotation_group_expanded: dict[str, bool] = {"Group A": False}
        self.saved_states: list[dict[str, bool]] = []

    def _on_annotation_group_expanded_changed(self, expanded: dict[str, bool]) -> None:
        self.saved_states.append(dict(expanded))


class AnnotationPresetDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _items(self) -> list[dict]:
        return [
            {"typeId": "a-1", "type": "Alpha", "group": "Group A", "count": 1},
            {"typeId": "a-2", "type": "Beta", "group": "Group A", "count": 2},
            {"typeId": "b-1", "type": "Gamma", "group": "Group B", "count": 3},
        ]

    def _sections(self, dialog: AnnotationPresetDialog) -> list[AnnotationGroupSection]:
        return dialog.findChildren(AnnotationGroupSection)

    def test_dialog_renders_multiselect_groups_with_existing_state(self) -> None:
        parent = _PresetParent()
        dialog = AnnotationPresetDialog(
            parent,
            self._items(),
            preset={"id": "preset-1", "name": "Preset A", "type_ids": ["a-2"]},
        )

        sections = self._sections(dialog)
        self.assertEqual([section.group_name for section in sections], ["Group A", "Group B"])
        self.assertEqual(sections[0].header.text(), "▸ Group A")
        self.assertTrue(sections[0].body.isHidden())
        self.assertEqual(dialog._name_edit.text(), "Preset A")
        self.assertTrue(dialog._buttons_by_type_id["a-2"].isChecked())

        sections[0].header.click()

        self.assertEqual(parent.saved_states[-1], {"Group A": True})

    def test_dialog_validates_name_duplicate_and_empty_selection(self) -> None:
        dialog = AnnotationPresetDialog(None, self._items(), existing_names={"Preset A"})

        dialog._save()
        self.assertIn("名称", dialog._error_label.text())

        dialog._name_edit.setText("Preset A")
        dialog._selected_type_ids.add("a-1")
        dialog._save()
        self.assertIn("同名", dialog._error_label.text())

        dialog._name_edit.setText("Preset B")
        dialog._selected_type_ids.clear()
        dialog._save()
        self.assertIn("至少选择", dialog._error_label.text())

    def test_dialog_saves_visible_order_and_keeps_unknown_existing_ids(self) -> None:
        dialog = AnnotationPresetDialog(
            None,
            self._items(),
            preset={"id": "preset-1", "name": "Preset A", "type_ids": ["missing", "a-2"]},
        )
        dialog._name_edit.setText("Preset B")
        dialog._buttons_by_type_id["a-1"].click()

        dialog._save()

        self.assertEqual(
            dialog.selected_preset(),
            {"id": "preset-1", "name": "Preset B", "type_ids": ["a-1", "a-2", "missing"]},
        )


if __name__ == "__main__":
    unittest.main()
