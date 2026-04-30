import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

from ui_island.services.route_manager import NODE_TYPE_COLLECT, NODE_TYPE_TELEPORT, NODE_TYPE_VIRTUAL
from ui_island.dialogs.route_notes_dialog import (
    _NODE_PANEL_SPACING,
    _NODE_SCROLL_MIN_HEIGHT,
    _TITLE_ROW_HEIGHT,
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

    def test_dialog_title_uses_route_name_without_duplicate_subtitle(self) -> None:
        route_name = "Long Route Name"
        dialog = RouteNotesDialog(None, route_name, "", (0x56, 0x34, 0x12), None, [])

        self.assertEqual(dialog.title_label.text(), route_name)
        self.assertEqual(dialog.title_label.toolTip(), route_name)
        self.assertEqual(dialog.title_bar.toolTip(), route_name)
        self.assertFalse(any(label.text() == f"路线：{route_name}" for label in dialog.findChildren(QLabel)))

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

    def test_stats_panel_moves_below_shorter_notes_editor(self) -> None:
        dialog = RouteNotesDialog(
            None,
            "璺嚎",
            "",
            (0x56, 0x34, 0x12),
            None,
            [{"node_type": "collect", "typeId": "ore", "type": "鐭跨煶"}],
        )

        left = dialog.findChild(QWidget, "RouteNotesLeftColumn")
        right = dialog.findChild(QWidget, "RouteNotesRightColumn")
        stats = dialog.findChild(QWidget, "RouteNotesStatsPanel")
        editor = dialog.findChild(QPlainTextEdit)
        stats_scroll = dialog.findChild(QScrollArea, "RouteNotesStatsScroll")
        nodes_title = right.findChildren(QLabel, "FieldLabel")[0] if right is not None else None
        notes_header = dialog.findChild(QWidget, "RouteNotesHeaderRow")

        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        self.assertIsNotNone(stats)
        self.assertIsNotNone(editor)
        self.assertIsNotNone(stats_scroll)
        self.assertIsNotNone(nodes_title)
        self.assertIsNotNone(notes_header)
        self.assertIs(stats_scroll.widget(), stats)
        self.assertNotIn(stats, right.findChildren(QWidget))
        self.assertEqual(editor.minimumHeight(), 120)
        self.assertEqual(stats_scroll.minimumHeight(), 72)
        self.assertEqual(stats_scroll.maximumHeight(), 72)
        self.assertEqual(nodes_title.minimumHeight(), notes_header.minimumHeight())
        self.assertEqual(nodes_title.maximumHeight(), notes_header.maximumHeight())

        dialog.show()
        self._app.processEvents()
        self.assertEqual(stats_scroll.verticalScrollBar().maximum(), 0)

    def test_node_panel_geometry_fills_between_notes_title_and_stats_bottom(self) -> None:
        def panel_geometry_for(nodes: list[dict]) -> tuple[int, int, int, int, int, int, int, int, int]:
            dialog = RouteNotesDialog(None, "Route", "", (0x56, 0x34, 0x12), None, nodes)
            dialog.show()
            self._app.processEvents()
            left = dialog.findChild(QWidget, "RouteNotesLeftColumn")
            right = dialog.findChild(QWidget, "RouteNotesRightColumn")
            scroll = dialog.findChild(QScrollArea, "RouteNotesNodeScroll")
            self.assertIsNotNone(left)
            self.assertIsNotNone(right)
            self.assertIsNotNone(scroll)
            title = right.findChildren(QLabel, "FieldLabel")[0]
            bottom_blank = right.height() - (scroll.geometry().y() + scroll.height())
            bottom_gap = left.height() - (right.geometry().y() + right.height())
            geometry = (
                left.height(),
                right.height(),
                right.geometry().y(),
                title.geometry().y(),
                title.height(),
                scroll.geometry().y(),
                scroll.height(),
                bottom_blank,
                bottom_gap,
            )
            dialog.close()
            return geometry

        small_geometry = panel_geometry_for([
            {"node_type": "collect", "typeId": "ore", "type": "Ore"}
        ])
        large_geometry = panel_geometry_for([
            {"node_type": "collect", "typeId": f"type-{index}", "type": f"Type {index}"}
            for index in range(80)
        ])

        for geometry in (small_geometry, large_geometry):
            left_height, right_height, right_y, title_y, title_height, scroll_y, scroll_height, bottom_blank, bottom_gap = geometry
            self.assertEqual(right_y, 0)
            self.assertEqual(right_height, left_height)
            self.assertEqual(title_y, 0)
            self.assertEqual(title_height, _TITLE_ROW_HEIGHT)
            self.assertEqual(scroll_y, _TITLE_ROW_HEIGHT + _NODE_PANEL_SPACING)
            self.assertEqual(scroll_height, right_height - scroll_y)
            self.assertGreaterEqual(scroll_height, _NODE_SCROLL_MIN_HEIGHT)
            self.assertEqual(bottom_blank, 0)
            self.assertEqual(bottom_gap, 0)

        self.assertGreaterEqual(large_geometry[6], small_geometry[6])

    def test_large_stats_panel_grows_to_max_then_scrolls(self) -> None:
        nodes = [
            {"node_type": "collect", "typeId": f"type-{index}", "type": f"Type {index}"}
            for index in range(80)
        ]
        dialog = RouteNotesDialog(None, "Route", "", (0x56, 0x34, 0x12), None, nodes)
        dialog.show()
        self._app.processEvents()

        stats_scroll = dialog.findChild(QScrollArea, "RouteNotesStatsScroll")
        self.assertIsNotNone(stats_scroll)
        self.assertEqual(stats_scroll.minimumHeight(), 150)
        self.assertEqual(stats_scroll.maximumHeight(), 150)

        scrollbar = stats_scroll.verticalScrollBar()
        self.assertTrue(scrollbar.isVisible())
        self.assertGreater(scrollbar.maximum(), 0)

        option = QStyleOptionSlider()
        scrollbar.initStyleOption(option)
        handle = scrollbar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, scrollbar)
        self.assertGreaterEqual(handle.height(), 24)
        self.assertGreaterEqual(scrollbar.width(), 10)

        start = handle.center()
        end = QPoint(start.x(), scrollbar.rect().bottom() - 4)
        before = scrollbar.value()
        QTest.mousePress(scrollbar, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(scrollbar, end, 50)
        QTest.mouseRelease(scrollbar, Qt.LeftButton, Qt.NoModifier, end)
        self._app.processEvents()

        self.assertGreater(scrollbar.value(), before)

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

    def test_node_scrollbar_has_draggable_handle_and_changes_value_when_dragged(self) -> None:
        nodes = [{"label": f"Node {index}", "x": index, "y": index} for index in range(400)]
        dialog = RouteNotesDialog(None, "璺嚎", "", (0x56, 0x34, 0x12), None, nodes)
        dialog.show()
        self._app.processEvents()

        scroll = dialog.findChild(QScrollArea, "RouteNotesNodeScroll")
        self.assertIsNotNone(scroll)
        scrollbar = scroll.verticalScrollBar()
        self.assertTrue(scrollbar.isVisible())
        self.assertGreater(scrollbar.maximum(), 0)

        option = QStyleOptionSlider()
        scrollbar.initStyleOption(option)
        handle = scrollbar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, scrollbar)
        self.assertGreaterEqual(handle.height(), 24)
        self.assertGreaterEqual(scrollbar.width(), 10)

        start = handle.center()
        end = QPoint(start.x(), scrollbar.rect().bottom() - 4)
        before = scrollbar.value()
        QTest.mousePress(scrollbar, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(scrollbar, end, 50)
        QTest.mouseRelease(scrollbar, Qt.LeftButton, Qt.NoModifier, end)
        self._app.processEvents()

        self.assertGreater(scrollbar.value(), before)


if __name__ == "__main__":
    unittest.main()
