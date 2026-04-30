"""Dialog for moving an existing route point to a different order."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QSpinBox

from ..design import strings
from ..widgets.factory import make_label
from . import StyledDialogBase, center_dialog

_ORDER_SPIN_MAX_WIDTH = 100


class PointOrderDialog(StyledDialogBase):
    def __init__(self, parent, route_name: str, current_index: int, total_count: int) -> None:
        total = max(1, int(total_count))
        current = max(0, min(total - 1, int(current_index)))
        super().__init__(parent, strings.POINT_ORDER_DIALOG_TITLE, min_width=360, max_width=460)

        self._current_index = current
        self._total_count = total

        route_label = make_label(
            strings.POINT_ORDER_ROUTE_FMT.format(name=str(route_name or "")),
            object_name="BodyLabel",
            word_wrap=True,
        )
        self.shell_layout.addWidget(route_label)

        current_label = make_label(
            strings.POINT_ORDER_CURRENT_FMT.format(pos=current + 1, total=total),
            object_name="DimLabel",
        )
        self.shell_layout.addWidget(current_label)

        row = QHBoxLayout()
        row.addWidget(make_label(strings.POINT_ORDER_TARGET_LABEL, object_name="DimLabel"))
        self.spin = QSpinBox(self)
        self.spin.setRange(1, total)
        self.spin.setValue(current + 1)
        self.spin.setSuffix(f" / {total}")
        self.spin.setMaximumWidth(_ORDER_SPIN_MAX_WIDTH)
        row.addWidget(self.spin)
        row.addStretch(1)
        self.shell_layout.addLayout(row)

        self.add_action_row(
            confirm_text=strings.POINT_ORDER_CONFIRM,
            cancel_text=strings.POINT_ORDER_CANCEL,
        )
        self.adjustSize()

    def target_index(self) -> int:
        return max(0, min(self._total_count - 1, int(self.spin.value()) - 1))


def open_point_order_dialog(parent, route_name: str, current_index: int, total_count: int) -> int | None:
    dialog = PointOrderDialog(parent, route_name, current_index, total_count)
    center_dialog(dialog, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.target_index()
    return None
