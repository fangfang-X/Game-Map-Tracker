"""Dialog for viewing and editing route notes, color, and node summary."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from route_manager import NODE_TYPE_COLLECT, NODE_TYPE_TELEPORT, NODE_TYPE_VIRTUAL, NODE_TYPES

from .base import StyledDialogBase, center_dialog
from .color_picker import open_styled_color_picker
from ..design import strings
from ..widgets.factory import make_scroll_area

_NODE_ICON_SIZE = 22
_STAT_COLUMNS = 3
_COLOR_BUTTON_TEXT = "（当前路线颜色）"


def normalize_color_hex(value: object) -> str | None:
    color = QColor(str(value or "").strip())
    if not color.isValid():
        return None
    return color.name(QColor.HexRgb)


def route_color_to_hex(route_color: tuple[int, int, int]) -> str:
    try:
        b, g, r = [max(0, min(255, int(channel))) for channel in route_color]
    except (TypeError, ValueError):
        return "#1ad1ff"
    return QColor(r, g, b).name(QColor.HexRgb)


def route_node_display_name(point: dict, index: int) -> str:
    label = str(point.get("label") or "").strip() if isinstance(point, dict) else ""
    return label or f"节点 {index + 1}"


def normalize_route_node_type(point: dict) -> str:
    value = str(point.get("node_type") or NODE_TYPE_COLLECT).strip().casefold() if isinstance(point, dict) else ""
    return value if value in NODE_TYPES else NODE_TYPE_COLLECT


def route_node_annotation(point: dict) -> tuple[str, str] | None:
    if not isinstance(point, dict):
        return None
    type_id = str(point.get("typeId") or "").strip()
    type_name = str(point.get("type") or "").strip()
    if not type_id and not type_name:
        return None
    return type_id or type_name, type_name or type_id


def summarize_route_nodes(points: list[dict]) -> dict:
    node_counts = {
        NODE_TYPE_COLLECT: 0,
        NODE_TYPE_TELEPORT: 0,
        NODE_TYPE_VIRTUAL: 0,
    }
    annotations: list[dict] = []
    annotation_indexes: dict[str, int] = {}

    for point in points:
        node_type = normalize_route_node_type(point)
        node_counts[node_type] = node_counts.get(node_type, 0) + 1

        annotation = route_node_annotation(point)
        if annotation is None:
            continue
        annotation_key, annotation_label = annotation
        if annotation_key not in annotation_indexes:
            annotation_indexes[annotation_key] = len(annotations)
            annotations.append({
                "key": annotation_key,
                "label": annotation_label,
                "count": 0,
            })
        annotations[annotation_indexes[annotation_key]]["count"] += 1

    return {
        "node_counts": node_counts,
        "annotations": annotations,
    }


def route_node_icon_pixmap(point: dict, route_color_hex: str, size: int = _NODE_ICON_SIZE) -> tuple[QPixmap, bool]:
    icon_path = str(point.get("icon_path") or "").strip() if isinstance(point, dict) else ""
    if icon_path and Path(icon_path).exists():
        icon = QIcon(icon_path)
        pixmap = icon.pixmap(size, size)
        if not pixmap.isNull():
            return pixmap, False

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(route_color_hex)
    painter.setBrush(color)
    painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
    margin = 3
    painter.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)
    painter.end()
    return pixmap, True


class RouteNotesDialog(StyledDialogBase):
    def __init__(
        self,
        parent,
        route_name: str,
        notes: str,
        route_color: tuple[int, int, int],
        color_override: str | None,
        nodes: list[dict],
    ) -> None:
        super().__init__(parent, strings.ROUTE_NOTES_TITLE, min_width=760, max_width=980)
        self._route_name = route_name
        self._notes = notes
        self._route_color_hex = route_color_to_hex(route_color)
        self._color_override = normalize_color_hex(color_override) if color_override else None
        self._nodes = [dict(point) for point in nodes if isinstance(point, dict)]

        content = QWidget(self)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        left = QWidget(content)
        left.setMinimumWidth(340)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self._build_notes_column(left_layout)
        content_layout.addWidget(left, stretch=3)

        right = QWidget(content)
        right.setMinimumWidth(300)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        self._build_nodes_column(right_layout)
        content_layout.addWidget(right, stretch=2)

        self.shell_layout.addWidget(content, stretch=1)
        self.add_action_row(confirm_text=strings.ROUTE_NOTES_CONFIRM, cancel_text=strings.ROUTE_NOTES_CANCEL)
        self.resize(840, 460)

    def _build_notes_column(self, layout: QVBoxLayout) -> None:
        subtitle = QLabel(f"路线：{self._route_name}")
        subtitle.setObjectName("StatLabel")
        subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(subtitle)

        notes_header = QWidget(self)
        notes_header.setObjectName("RouteNotesHeaderRow")
        header_layout = QHBoxLayout(notes_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        notes_label = QLabel(strings.ROUTE_NOTES_NOTES_LABEL, notes_header)
        notes_label.setObjectName("FieldLabel")
        header_layout.addWidget(notes_label)

        self.color_button = QPushButton(self)
        self.color_button.clicked.connect(self._pick_color)
        self.color_button.setFixedHeight(26)
        self.color_button.setMinimumWidth(112)
        header_layout.addWidget(self.color_button)

        self.reset_color_button = QPushButton(strings.ROUTE_NOTES_COLOR_RESET, self)
        self.reset_color_button.clicked.connect(self._reset_color)
        self.reset_color_button.setFixedHeight(26)
        header_layout.addWidget(self.reset_color_button)
        header_layout.addStretch()
        layout.addWidget(notes_header)

        self.editor = QPlainTextEdit(self)
        self.editor.setPlaceholderText(strings.ROUTE_NOTES_PLACEHOLDER)
        self.editor.setPlainText(self._notes)
        self.editor.setMinimumHeight(240)
        self.editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.editor, stretch=1)
        self._sync_color_controls()

    def _build_nodes_column(self, layout: QVBoxLayout) -> None:
        stats_title = QLabel(strings.ROUTE_NOTES_STATS_TITLE)
        stats_title.setObjectName("FieldLabel")
        layout.addWidget(stats_title)

        stats = QFrame(self)
        stats.setObjectName("RouteNotesStatsPanel")
        stats_layout = QGridLayout(stats)
        stats_layout.setContentsMargins(8, 8, 8, 8)
        stats_layout.setHorizontalSpacing(6)
        stats_layout.setVerticalSpacing(6)
        summary = summarize_route_nodes(self._nodes)
        stat_items = [
            (strings.ROUTE_NOTES_NODE_COLLECT, summary["node_counts"].get(NODE_TYPE_COLLECT, 0)),
            (strings.ROUTE_NOTES_NODE_TELEPORT, summary["node_counts"].get(NODE_TYPE_TELEPORT, 0)),
            (strings.ROUTE_NOTES_NODE_GUIDE, summary["node_counts"].get(NODE_TYPE_VIRTUAL, 0)),
        ]
        stat_items.extend((item["label"], item["count"]) for item in summary["annotations"])
        for index, (label, count) in enumerate(stat_items):
            chip = QLabel(f"{label} {count}")
            chip.setObjectName("RouteNotesStatChip")
            chip.setToolTip(f"{label}：{count}")
            stats_layout.addWidget(chip, index // _STAT_COLUMNS, index % _STAT_COLUMNS)
        layout.addWidget(stats)

        nodes_title = QLabel(strings.ROUTE_NOTES_NODE_LIST)
        nodes_title.setObjectName("FieldLabel")
        layout.addWidget(nodes_title)

        scroll = make_scroll_area(
            object_name="AnnotationPanelScroll",
            horizontal_policy=Qt.ScrollBarAlwaysOff,
            min_height=220,
            max_height=320,
        )
        host = QWidget()
        host.setObjectName("AnnotationPanelInner")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(2, 2, 2, 2)
        host_layout.setSpacing(6)
        if not self._nodes:
            empty = QLabel(strings.ROUTE_NOTES_NODE_EMPTY)
            empty.setObjectName("DimLabel")
            empty.setWordWrap(True)
            host_layout.addWidget(empty)
        else:
            for index, point in enumerate(self._nodes):
                host_layout.addWidget(self._build_node_row(point, index))
        host_layout.addStretch(1)
        scroll.setWidget(host)
        layout.addWidget(scroll, stretch=1)

    def _build_node_row(self, point: dict, index: int) -> QWidget:
        row = QWidget()
        row.setObjectName("RouteNotesNodeRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 4, 6, 4)
        row_layout.setSpacing(8)

        icon_label = QLabel(row)
        icon_label.setObjectName("RouteNotesNodeIcon")
        icon_label.setFixedSize(_NODE_ICON_SIZE, _NODE_ICON_SIZE)
        pixmap, fallback = route_node_icon_pixmap(point, self.effective_color_hex())
        icon_label.setPixmap(pixmap)
        icon_label.setProperty("fallbackIcon", fallback)
        row_layout.addWidget(icon_label)

        name_label = QLabel(route_node_display_name(point, index), row)
        name_label.setObjectName("RouteNotesNodeName")
        name_label.setToolTip(name_label.text())
        row_layout.addWidget(name_label, stretch=1)
        return row

    def _pick_color(self) -> None:
        color = open_styled_color_picker(
            self,
            strings.ROUTE_NOTES_COLOR_PICK,
            self.effective_color_hex(),
        )
        if color is None or not color.isValid():
            return
        self._color_override = color.name(QColor.HexRgb)
        self._sync_color_controls()

    def _reset_color(self) -> None:
        self._color_override = None
        self._sync_color_controls()

    def _sync_color_controls(self) -> None:
        effective = self.effective_color_hex()
        color = QColor(effective)
        text_color = "#000000" if color.lightness() > 150 else "#ffffff"
        if self._color_override:
            tooltip = strings.ROUTE_NOTES_COLOR_CUSTOM_TOOLTIP
        else:
            tooltip = strings.ROUTE_NOTES_COLOR_FOLLOW_TOOLTIP
        self.color_button.setText(_COLOR_BUTTON_TEXT)
        self.color_button.setToolTip(tooltip)
        self.color_button.setStyleSheet(
            f"background: {effective}; color: {text_color}; border: 1px solid rgba(255, 255, 255, 0.35);"
        )
        self.reset_color_button.setEnabled(self._color_override is not None)
        self.reset_color_button.setToolTip(strings.ROUTE_NOTES_COLOR_RESET_TOOLTIP)

    def effective_color_hex(self) -> str:
        return self._color_override or self._route_color_hex

    def notes_text(self) -> str:
        return self.editor.toPlainText()

    def color_override(self) -> str | None:
        return self._color_override


def edit_route_notes(
    parent,
    route_name: str,
    notes: str,
    route_color: tuple[int, int, int],
    color_override: str | None,
    nodes: list[dict],
) -> tuple[bool, str, str | None]:
    dialog = RouteNotesDialog(parent, route_name, notes, route_color, color_override, nodes)
    center_dialog(dialog, parent)
    accepted = dialog.exec() == QDialog.Accepted
    return accepted, dialog.notes_text(), dialog.color_override()
