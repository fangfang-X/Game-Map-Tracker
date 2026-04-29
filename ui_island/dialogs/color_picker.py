"""Shared styled color picker dialog helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox

from .base import StyledDialogBase, center_dialog
from ..design import qss


def localize_color_dialog(dialog: QColorDialog) -> None:
    label_map = {
        "&Basic colors": "基础颜色",
        "&Custom colors": "自定义颜色",
        "Hu&e:": "色相:",
        "&Sat:": "饱和度:",
        "&Val:": "明度:",
        "&Red:": "红:",
        "&Green:": "绿:",
        "Bl&ue:": "蓝:",
        "A&lpha channel:": "透明度:",
        "&HTML:": "HTML:",
    }
    button_map = {
        "&Pick Screen Color": "吸取屏幕颜色",
        "&Add to Custom Colors": "添加到自定义颜色",
        "OK": "确认",
        "Cancel": "取消",
    }
    for label in dialog.findChildren(QLabel):
        text = label.text()
        if text in label_map:
            label.setText(label_map[text])
    for button in dialog.findChildren(QPushButton):
        text = button.text()
        if text in button_map:
            button.setText(button_map[text])


def open_styled_color_picker(
    parent,
    title: str,
    current_color: QColor | str,
    *,
    reset_color: QColor | str | None = None,
    reset_text: str = "恢复默认颜色",
) -> QColor | None:
    current = QColor(current_color)
    if not current.isValid():
        return None

    dialog = StyledDialogBase(parent, title, min_width=560, max_width=720)
    picker = QColorDialog(current, dialog)
    picker.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    picker.setOption(QColorDialog.ColorDialogOption.NoButtons, True)
    picker.setAttribute(Qt.WA_StyledBackground, True)
    picker.setStyleSheet(qss.COLOR_DIALOG_QSS)
    picker.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    localize_color_dialog(picker)

    for spin in picker.findChildren(QSpinBox):
        spin.setFixedWidth(56)
    for editor in picker.findChildren(QLineEdit):
        editor.setMaximumWidth(96)

    dialog.shell_layout.addWidget(picker)

    button_row = QHBoxLayout()
    if reset_color is not None:
        known_reset_color = QColor(reset_color)
        reset_btn = QPushButton(reset_text, dialog)
        reset_btn.clicked.connect(lambda: picker.setCurrentColor(known_reset_color))
        button_row.addWidget(reset_btn)
    button_row.addStretch()

    cancel_btn = QPushButton("取消", dialog)
    cancel_btn.clicked.connect(dialog.reject)
    button_row.addWidget(cancel_btn)

    confirm_btn = QPushButton("确认", dialog)
    confirm_btn.setDefault(True)
    confirm_btn.clicked.connect(dialog.accept)
    button_row.addWidget(confirm_btn)
    dialog.shell_layout.addLayout(button_row)

    center_dialog(dialog, parent)
    if dialog.exec() != QDialog.Accepted:
        return None
    color = picker.currentColor()
    return color if color.isValid() else None
