import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from route_manager import NODE_TYPE_COLLECT, NODE_TYPE_TELEPORT, NODE_TYPE_VIRTUAL
from ui_island.dialogs.route_notes_dialog import (
    RouteNotesDialog,
    route_node_display_name,
    route_node_icon_pixmap,
    summarize_route_nodes,
)


class RouteNotesDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_route_node_display_name_falls_back_to_indexed_name(self) -> None:
        self.assertEqual(route_node_display_name({}, 2), "节点 3")
        self.assertEqual(route_node_display_name({"label": " 黑矿 "}, 0), "黑矿")

    def test_missing_icon_uses_route_color_fallback_pixmap(self) -> None:
        pixmap, fallback = route_node_icon_pixmap({"icon_path": "missing.png"}, "#123456")

        self.assertTrue(fallback)
        self.assertFalse(pixmap.isNull())

    def test_summary_counts_node_types_and_annotation_types(self) -> None:
        summary = summarize_route_nodes([
            {"node_type": "collect", "typeId": "ore", "type": "矿石"},
            {"node_type": "teleport"},
            {"node_type": "virtual", "typeId": "ore", "type": "矿石"},
            {"node_type": "invalid", "type": "宝箱"},
        ])

        self.assertEqual(summary["node_counts"][NODE_TYPE_COLLECT], 2)
        self.assertEqual(summary["node_counts"][NODE_TYPE_TELEPORT], 1)
        self.assertEqual(summary["node_counts"][NODE_TYPE_VIRTUAL], 1)
        self.assertEqual(
            [(item["label"], item["count"]) for item in summary["annotations"]],
            [("矿石", 2), ("宝箱", 1)],
        )

    def test_dialog_renders_node_rows_with_fallback_icons(self) -> None:
        dialog = RouteNotesDialog(
            None,
            "路线",
            "",
            (0x56, 0x34, 0x12),
            None,
            [{"x": 1, "y": 2}, {"label": "已命名", "icon_path": "missing.png"}],
        )

        names = [label.text() for label in dialog.findChildren(QLabel, "RouteNotesNodeName")]
        icons = dialog.findChildren(QLabel, "RouteNotesNodeIcon")

        self.assertEqual(names, ["节点 1", "已命名"])
        self.assertEqual([icon.property("fallbackIcon") for icon in icons], [True, True])

    def test_color_controls_share_notes_header_and_hide_hex_text(self) -> None:
        dialog = RouteNotesDialog(None, "路线", "", (0x56, 0x34, 0x12), None, [])

        header = dialog.findChild(QWidget, "RouteNotesHeaderRow")
        header_buttons = header.findChildren(QPushButton) if header is not None else []

        self.assertIsNotNone(header)
        self.assertIn(dialog.color_button, header_buttons)
        self.assertIn(dialog.reset_color_button, header_buttons)
        self.assertEqual(dialog.color_button.text(), "（当前路线颜色）")
        self.assertNotIn("#", dialog.color_button.text())

    def test_follow_global_button_is_enabled_only_for_custom_color(self) -> None:
        follow_dialog = RouteNotesDialog(None, "路线", "", (0x56, 0x34, 0x12), None, [])
        custom_dialog = RouteNotesDialog(None, "路线", "", (0x56, 0x34, 0x12), "#abcdef", [])

        self.assertFalse(follow_dialog.reset_color_button.isEnabled())
        self.assertTrue(custom_dialog.reset_color_button.isEnabled())

    def test_pick_color_uses_shared_styled_picker(self) -> None:
        dialog = RouteNotesDialog(None, "路线", "", (0x56, 0x34, 0x12), None, [])

        with patch(
            "ui_island.dialogs.route_notes_dialog.open_styled_color_picker",
            return_value=QColor("#abcdef"),
        ) as picker:
            dialog._pick_color()

        picker.assert_called_once()
        self.assertEqual(dialog.color_override(), "#abcdef")
        self.assertEqual(dialog.color_button.text(), "（当前路线颜色）")


if __name__ == "__main__":
    unittest.main()
