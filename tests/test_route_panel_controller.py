import unittest
from enum import Enum
from unittest.mock import patch

from ui_island.controllers.route_panel_controller import RoutePanelController
from ui_island.state import RouteDrawingState


class _Mode(Enum):
    PAUSED = "paused"
    MAXIMIZED = "maximized"
    TRACKING_STABLE = "tracking_stable"


class _FakeSearchInput:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        self._text = text


class _FakeSection:
    def __init__(self) -> None:
        self.visible: bool | None = None
        self.force_open: bool | None = None

    def setVisible(self, visible: bool) -> None:
        self.visible = bool(visible)

    def set_force_open(self, force_open: bool) -> None:
        self.force_open = bool(force_open)


class _FakeRouteItem:
    def __init__(self) -> None:
        self.visible: bool | None = None

    def setVisible(self, visible: bool) -> None:
        self.visible = bool(visible)


class _FakeCheckbox:
    def __init__(self) -> None:
        self.checked: bool | None = None
        self.blocked_states: list[bool] = []
        self.stylesheets: list[str] = []

    def blockSignals(self, blocked: bool) -> None:
        self.blocked_states.append(bool(blocked))

    def setChecked(self, checked: bool) -> None:
        self.checked = bool(checked)

    def setStyleSheet(self, stylesheet: str) -> None:
        self.stylesheets.append(stylesheet)


class _FakeSize:
    def __init__(self, width: int = 0, height: int = 0) -> None:
        self._width = width
        self._height = height

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class _FakeMargins:
    def __init__(self, top: int = 0, bottom: int = 0) -> None:
        self._top = top
        self._bottom = bottom

    def top(self) -> int:
        return self._top

    def bottom(self) -> int:
        return self._bottom


class _FakeTrackedLayout:
    def __init__(self) -> None:
        self._margins = _FakeMargins(top=2, bottom=3)

    def contentsMargins(self) -> _FakeMargins:
        return self._margins

    def spacing(self) -> int:
        return 4


class _FakeTrackedHeader:
    def sizeHint(self) -> _FakeSize:
        return _FakeSize(height=20)


class _FakeTrackedGrid:
    def verticalSpacing(self) -> int:
        return 6


class _FakeTrackedScroll:
    def __init__(self) -> None:
        self.visible = True
        self.fixed_height: int | None = None

    def hide(self) -> None:
        self.visible = False

    def show(self) -> None:
        self.visible = True

    def setFixedHeight(self, height: int) -> None:
        self.fixed_height = height


class _FakeTrackedCard:
    def __init__(self) -> None:
        self.minimum_height: int | None = None
        self.maximum_height: int | None = None

    def setMinimumHeight(self, height: int) -> None:
        self.minimum_height = height

    def setMaximumHeight(self, height: int) -> None:
        self.maximum_height = height


class _FakeButton:
    def __init__(self) -> None:
        self.text = ""
        self.tooltip = ""
        self.checked: bool | None = None
        self.visible: bool | None = None
        self.blocked_states: list[bool] = []

    def setText(self, text: str) -> None:
        self.text = text

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def setChecked(self, checked: bool) -> None:
        self.checked = bool(checked)

    def blockSignals(self, blocked: bool) -> None:
        self.blocked_states.append(bool(blocked))

    def setVisible(self, visible: bool) -> None:
        self.visible = bool(visible)


class _FakeToolbar:
    def __init__(self) -> None:
        self.shown = False
        self.raised = False

    def show(self) -> None:
        self.shown = True

    def raise_(self) -> None:
        self.raised = True


class _FakeWindowModeController:
    def __init__(self) -> None:
        self.layout_refresh_count = 0

    def schedule_layout_refresh(self) -> None:
        self.layout_refresh_count += 1


class _FakeMapView:
    def __init__(self) -> None:
        self.focus_calls: list[tuple[int, int]] = []
        self.refresh_count = 0

    def focus_map_position(self, x: int, y: int) -> None:
        self.focus_calls.append((x, y))

    def _refresh_from_last_frame(self) -> None:
        self.refresh_count += 1


class _FakeRouteManager:
    def __init__(self, routes: dict[str, dict] | None = None) -> None:
        self.routes = routes or {}
        self.visibility: dict[str, bool] = {}
        self.save_visibility_count = 0
        self.colors: dict[str, tuple[int, int, int]] = {}
        self.saved_points_calls: list[tuple[str, list[dict], bool | None]] = []
        self.saved_notes_calls: list[tuple[str, str, str, str | None]] = []
        self._new_point_id = 0

    @staticmethod
    def route_id(route: dict | None) -> str:
        return str(route.get("id") or "") if isinstance(route, dict) else ""

    def iter_routes(self):
        for route in self.routes.values():
            yield str(route.get("category") or "category"), route

    def route_for_id(self, route_id: str) -> dict | None:
        return self.routes.get(route_id)

    def route_name_for_id(self, route_id: str) -> str:
        route = self.routes.get(route_id)
        return str(route.get("display_name") or route_id) if route is not None else ""

    def save_visibility(self) -> None:
        self.save_visibility_count += 1

    def visible_routes(self) -> list[dict]:
        return [
            route
            for route_id, route in self.routes.items()
            if self.visibility.get(route_id, False)
        ]

    def has_progress(self, _route_id: str) -> bool:
        return False

    def color_for(self, route_id: str) -> tuple[int, int, int]:
        return self.colors.get(route_id, (10, 20, 30))

    def route_color_override(self, route_id: str) -> str:
        route = self.routes.get(route_id)
        return str(route.get("color") or "") if route is not None else ""

    def point_icon_path_for(self, _type_id: str) -> str:
        return ""

    def get_route_notes(self, category: str, name: str) -> str:
        route = self._route_by_category_name(category, name)
        return str(route.get("notes") or "") if route is not None else ""

    def update_route_notes_and_color(self, category: str, name: str, notes: str, color: str | None) -> bool:
        route = self._route_by_category_name(category, name)
        if route is None:
            return False
        route["notes"] = notes
        if color is None:
            route.pop("color", None)
        else:
            route["color"] = color
            raw = color[1:] if color.startswith("#") else color
            self.colors[str(route.get("id") or "")] = (int(raw[4:6], 16), int(raw[2:4], 16), int(raw[0:2], 16))
        self.saved_notes_calls.append((category, name, notes, color))
        return True

    def new_route_point_id(self) -> str:
        self._new_point_id += 1
        return f"point-{self._new_point_id}"

    def save_route_points(self, route_id: str, points: list[dict], loop: bool | None = None) -> bool:
        route = self.routes.get(route_id)
        if route is None:
            return False
        saved_points = [dict(point) for point in points]
        route["points"] = saved_points
        if loop is not None:
            route["loop"] = bool(loop)
        self.saved_points_calls.append((route_id, [dict(point) for point in saved_points], loop))
        return True

    def _route_by_category_name(self, category: str, name: str) -> dict | None:
        return next(
            (
                route
                for known_category, route in self.iter_routes()
                if known_category == category and route.get("display_name") == name
            ),
            None,
        )


class _FakeWindow:
    def __init__(self, search_text: str = "") -> None:
        self.search_input = _FakeSearchInput(search_text)
        self._route_sections: dict[str, _FakeSection] = {}
        self._route_widgets_by_category: dict[str, list[tuple[str, str, _FakeRouteItem]]] = {}
        self._route_checkboxes: dict[str, list[_FakeCheckbox]] = {}
        self.tracked_refreshed_count = 0
        self._mode = _Mode.PAUSED
        self.route_mgr = _FakeRouteManager()
        self.map_view = _FakeMapView()
        self.relocate_calls: list[tuple[int, int]] = []

    def _on_relocate(self, x: int, y: int) -> None:
        self.relocate_calls.append((x, y))


class RoutePanelFilterTests(unittest.TestCase):
    def _controller_for(self, window: _FakeWindow) -> RoutePanelController:
        controller = RoutePanelController.__new__(RoutePanelController)
        controller.window = window
        controller.refresh_tracked_routes = lambda: setattr(
            window,
            "tracked_refreshed_count",
            window.tracked_refreshed_count + 1,
        )
        controller.confirm_exit_route_drawing = lambda: True
        return controller

    def test_empty_category_stays_visible_without_search_term(self) -> None:
        window = _FakeWindow("")
        section = _FakeSection()
        window._route_sections["空分类"] = section
        window._route_widgets_by_category["空分类"] = []

        self._controller_for(window).apply_route_filter()

        self.assertTrue(section.visible)
        self.assertFalse(section.force_open)

    def test_empty_category_hides_when_searching(self) -> None:
        window = _FakeWindow("采集")
        section = _FakeSection()
        window._route_sections["空分类"] = section
        window._route_widgets_by_category["空分类"] = []

        self._controller_for(window).apply_route_filter()

        self.assertFalse(section.visible)
        self.assertFalse(section.force_open)

    def test_matching_category_shows_and_force_opens_when_searching(self) -> None:
        window = _FakeWindow("矿")
        section = _FakeSection()
        route_item = _FakeRouteItem()
        window._route_sections["资源"] = section
        window._route_widgets_by_category["资源"] = [("route-1", "矿物采集", route_item)]

        self._controller_for(window).apply_route_filter()

        self.assertTrue(route_item.visible)
        self.assertTrue(section.visible)
        self.assertTrue(section.force_open)

    def test_route_checkbox_stylesheet_uses_route_color_as_rgb(self) -> None:
        stylesheet = RoutePanelController.route_checkbox_stylesheet((10, 20, 30))

        self.assertIn("rgb(30, 20, 10)", stylesheet)

    def test_refresh_route_checkbox_colors_updates_registered_widgets(self) -> None:
        window = _FakeWindow("")
        checkbox_a = _FakeCheckbox()
        checkbox_b = _FakeCheckbox()
        checkbox_other = _FakeCheckbox()
        window._route_checkboxes = {
            "route-1": [checkbox_a, checkbox_b],
            "route-2": [checkbox_other],
        }
        window.route_mgr.colors = {
            "route-1": (1, 2, 3),
            "route-2": (40, 50, 60),
        }

        self._controller_for(window).refresh_route_checkbox_colors()

        self.assertIn("rgb(3, 2, 1)", checkbox_a.stylesheets[-1])
        self.assertIn("rgb(3, 2, 1)", checkbox_b.stylesheets[-1])
        self.assertIn("rgb(60, 50, 40)", checkbox_other.stylesheets[-1])

    def test_route_notes_dialog_saves_color_only_change_and_refreshes_display(self) -> None:
        window = _FakeWindow("")
        window.route_mgr = _FakeRouteManager({
            "route-1": {
                "id": "route-1",
                "category": "矿物",
                "display_name": "矿线",
                "notes": "old",
                "points": [{"x": 1, "y": 2, "typeId": "ore", "type": "矿石"}],
            }
        })
        checkbox = _FakeCheckbox()
        window._route_checkboxes = {"route-1": [checkbox]}
        controller = self._controller_for(window)

        with (
            patch("ui_island.controllers.route_panel_controller.edit_route_notes", return_value=(True, "old", "#112233")),
            patch("ui_island.controllers.route_panel_controller.toast"),
        ):
            controller.show_route_notes_dialog("矿物", "矿线")

        self.assertEqual(window.route_mgr.saved_notes_calls, [("矿物", "矿线", "old", "#112233")])
        self.assertIn("rgb(17, 34, 51)", checkbox.stylesheets[-1])
        self.assertEqual(window.map_view.refresh_count, 1)

    def test_route_notes_dialog_saves_notes_change_even_when_color_is_unchanged(self) -> None:
        window = _FakeWindow("")
        window.route_mgr = _FakeRouteManager({
            "route-1": {
                "id": "route-1",
                "category": "矿物",
                "display_name": "矿线",
                "notes": "old",
                "color": "#112233",
                "points": [],
            }
        })
        controller = self._controller_for(window)

        with (
            patch("ui_island.controllers.route_panel_controller.edit_route_notes", return_value=(True, "new", "#112233")),
            patch("ui_island.controllers.route_panel_controller.toast"),
        ):
            controller.show_route_notes_dialog("矿物", "矿线")

        self.assertEqual(window.route_mgr.saved_notes_calls, [("矿物", "矿线", "new", "#112233")])
        self.assertEqual(window.map_view.refresh_count, 1)

    def test_category_select_all_selects_only_category_and_saves_once(self) -> None:
        window = _FakeWindow("")
        window.route_mgr.visibility = {"route-1": False, "route-2": True, "other": False}
        route_1_checkbox = _FakeCheckbox()
        route_2_checkbox = _FakeCheckbox()
        other_checkbox = _FakeCheckbox()
        window._route_checkboxes = {
            "route-1": [route_1_checkbox],
            "route-2": [route_2_checkbox],
            "other": [other_checkbox],
        }
        window._route_widgets_by_category = {
            "cat-a": [
                ("route-1", "Route 1", _FakeRouteItem()),
                ("route-2", "Route 2", _FakeRouteItem()),
            ],
            "cat-b": [("other", "Other", _FakeRouteItem())],
        }

        self._controller_for(window).set_category_routes_visibility("cat-a", "select_all")

        self.assertEqual(window.route_mgr.visibility, {"route-1": True, "route-2": True, "other": False})
        self.assertEqual(window.route_mgr.save_visibility_count, 1)
        self.assertTrue(route_1_checkbox.checked)
        self.assertIsNone(other_checkbox.checked)
        self.assertEqual(window.tracked_refreshed_count, 1)
        self.assertEqual(window.map_view.refresh_count, 1)

    def test_category_invert_flips_only_category_and_saves_once(self) -> None:
        window = _FakeWindow("")
        window.route_mgr.visibility = {"route-1": True, "route-2": False, "other": True}
        route_1_checkbox = _FakeCheckbox()
        route_2_checkbox = _FakeCheckbox()
        other_checkbox = _FakeCheckbox()
        window._route_checkboxes = {
            "route-1": [route_1_checkbox],
            "route-2": [route_2_checkbox],
            "other": [other_checkbox],
        }
        window._route_widgets_by_category = {
            "cat-a": [
                ("route-1", "Route 1", _FakeRouteItem()),
                ("route-2", "Route 2", _FakeRouteItem()),
            ],
            "cat-b": [("other", "Other", _FakeRouteItem())],
        }

        self._controller_for(window).set_category_routes_visibility("cat-a", "invert")

        self.assertEqual(window.route_mgr.visibility, {"route-1": False, "route-2": True, "other": True})
        self.assertEqual(window.route_mgr.save_visibility_count, 1)
        self.assertFalse(route_1_checkbox.checked)
        self.assertTrue(route_2_checkbox.checked)
        self.assertIsNone(other_checkbox.checked)
        self.assertEqual(window.tracked_refreshed_count, 1)
        self.assertEqual(window.map_view.refresh_count, 1)

    def test_tracked_routes_collapse_hides_scroll_and_restores_height(self) -> None:
        window = _FakeWindow("")
        window.route_mgr.routes = {"route-1": {"display_name": "Route 1"}}
        window.route_mgr.visibility = {"route-1": True}
        window.tracked_routes_collapsed = False
        window.tracked_routes_toggle_btn = _FakeButton()
        window.tracked_routes_scroll = _FakeTrackedScroll()
        window.tracked_routes_layout = _FakeTrackedLayout()
        window.tracked_routes_header = _FakeTrackedHeader()
        window.tracked_routes_grid = _FakeTrackedGrid()
        window.tracked_routes_card = _FakeTrackedCard()
        window.window_mode_controller = _FakeWindowModeController()
        controller = self._controller_for(window)

        controller.set_tracked_routes_collapsed(True)

        self.assertTrue(window.tracked_routes_collapsed)
        self.assertEqual(window.tracked_routes_toggle_btn.text, "▸")
        self.assertEqual(window.tracked_routes_toggle_btn.tooltip, "展开当前追踪路线")
        self.assertFalse(window.tracked_routes_scroll.visible)
        self.assertEqual(window.tracked_routes_scroll.fixed_height, 0)
        self.assertEqual(window.tracked_routes_card.minimum_height, 25)
        self.assertEqual(window.window_mode_controller.layout_refresh_count, 1)

        controller.set_tracked_routes_collapsed(False)

        self.assertFalse(window.tracked_routes_collapsed)
        self.assertEqual(window.tracked_routes_toggle_btn.text, "▾")
        self.assertEqual(window.tracked_routes_toggle_btn.tooltip, "收起当前追踪路线")
        self.assertTrue(window.tracked_routes_scroll.visible)
        self.assertGreater(window.tracked_routes_scroll.fixed_height, 0)
        self.assertGreater(window.tracked_routes_card.minimum_height, 25)
        self.assertEqual(window.window_mode_controller.layout_refresh_count, 2)

    def test_route_drawing_loop_change_marks_state_dirty(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="采集",
            name="路线",
            points=[{"x": 1, "y": 2}, {"x": 3, "y": 4}, {"x": 5, "y": 6}],
            loop=False,
        )
        controller = self._controller_for(window)

        controller._mark_drawing_dirty()
        self.assertFalse(window.route_drawing_state.dirty)

        window.route_drawing_state.loop = True
        controller._mark_drawing_dirty()

        self.assertTrue(window.route_drawing_state.dirty)

    def test_drawing_point_node_type_change_marks_dirty_and_undo_restores(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 1, "y": 2, "node_type": "collect"}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        self.assertTrue(controller.set_drawing_point_node_type(0, "teleport"))
        self.assertEqual(window.route_drawing_state.draft_points[0]["node_type"], "teleport")
        self.assertTrue(window.route_drawing_state.dirty)

        controller.undo_route_drawing()

        self.assertEqual(window.route_drawing_state.draft_points[0]["node_type"], "collect")
        self.assertFalse(window.route_drawing_state.dirty)

    def test_drawing_point_node_type_defaults_missing_type_to_collect(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 1, "y": 2}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        self.assertTrue(controller.set_drawing_point_node_type(0, ""))
        self.assertEqual(window.route_drawing_state.draft_points[0]["node_type"], "collect")
        self.assertTrue(window.route_drawing_state.dirty)

        controller.undo_route_drawing()

        self.assertNotIn("node_type", window.route_drawing_state.draft_points[0])
        self.assertFalse(window.route_drawing_state.dirty)

    def test_move_drawing_point_updates_draft_and_marks_dirty(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 1, "y": 2}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        self.assertTrue(controller.move_drawing_point(0, 10, 20))

        self.assertEqual(window.route_drawing_state.draft_points[0]["x"], 10)
        self.assertEqual(window.route_drawing_state.draft_points[0]["y"], 20)
        self.assertTrue(window.route_drawing_state.dirty)
        self.assertEqual(window.route_drawing_state.undo_stack, [])

    def test_finish_move_drawing_point_records_undo_and_undo_restores(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 1, "y": 2, "node_type": "collect"}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        self.assertTrue(controller.move_drawing_point(0, 10, 20, sync=False))
        self.assertTrue(controller.finish_move_drawing_point(0, 1, 2, 10, 20))

        self.assertEqual(window.route_drawing_state.undo_stack[-1]["op"], "move")
        self.assertTrue(window.route_drawing_state.dirty)

        controller.undo_route_drawing()

        point = window.route_drawing_state.draft_points[0]
        self.assertEqual(point["x"], 1)
        self.assertEqual(point["y"], 2)
        self.assertEqual(point["node_type"], "collect")
        self.assertFalse(window.route_drawing_state.dirty)

    def test_finish_move_drawing_point_ignores_unchanged_position(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 1, "y": 2}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        self.assertFalse(controller.finish_move_drawing_point(0, 1, 2, 1, 2))

        self.assertEqual(window.route_drawing_state.undo_stack, [])
        self.assertFalse(window.route_drawing_state.dirty)

    def test_append_drawing_point_defaults_to_end(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(10, 0)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (100, 0),
            (10, 0),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 2)

    def test_append_drawing_point_can_insert_after_nearest_node(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 200, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(110, 0)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (100, 0),
            (110, 0),
            (200, 0),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 2)

    def test_append_drawing_point_can_use_explicit_index_override(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(10, 0, index_override=0)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (10, 0),
            (0, 0),
            (100, 0),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 0)

    def test_append_drawing_point_clamps_explicit_index_override(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(10, 0, index_override=99)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (10, 0),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 1)

    def test_append_drawing_point_tie_uses_earlier_nearest_node(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 10, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(5, 0)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (5, 0),
            (10, 0),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 1)

    def test_append_drawing_point_handles_empty_and_single_point_routes(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(route_id="2026010101", category="routes", name="route", points=[])
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(1, 2)
        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [(1, 2)])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 0)

        controller.append_drawing_point(3, 4)
        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (1, 2),
            (3, 4),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 1)

    def test_undo_removes_auto_inserted_point_from_recorded_index(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        controller.append_drawing_point(10, 0)
        controller.undo_route_drawing()

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (100, 0),
        ])
        self.assertFalse(window.route_drawing_state.dirty)

    def test_context_menu_drawing_point_insert_at_end_skips_position_dialog(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        )
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        with patch("ui_island.controllers.route_panel_controller.open_insert_point_dialog") as dialog:
            controller.append_drawing_point_from_context_menu(10, 0)

        dialog.assert_not_called()
        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (100, 0),
            (10, 0),
        ])

    def test_context_menu_drawing_point_uses_default_suggestion_when_dialog_unchanged(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 200, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        with patch(
            "ui_island.controllers.route_panel_controller.open_insert_point_dialog",
            return_value=(["2026010101"], {}),
        ) as dialog:
            controller.append_drawing_point_from_context_menu(110, 0)

        dialog.assert_called_once()
        args = dialog.call_args.args
        self.assertEqual(args[1:3], (110, 0))
        self.assertEqual(args[3][0]["suggested_index"], 2)
        self.assertEqual(args[3][0]["points_count"], 3)
        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (100, 0),
            (110, 0),
            (200, 0),
        ])

    def test_context_menu_drawing_point_uses_dialog_override(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        with patch(
            "ui_island.controllers.route_panel_controller.open_insert_point_dialog",
            return_value=(["2026010101"], {"2026010101": 0}),
        ):
            controller.append_drawing_point_from_context_menu(10, 0)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (10, 0),
            (0, 0),
            (100, 0),
        ])
        self.assertEqual(window.route_drawing_state.undo_stack[-1]["index"], 0)

    def test_context_menu_drawing_point_cancel_or_unselected_does_not_insert(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        with patch("ui_island.controllers.route_panel_controller.open_insert_point_dialog", return_value=None):
            controller.append_drawing_point_from_context_menu(10, 0)
        with patch(
            "ui_island.controllers.route_panel_controller.open_insert_point_dialog",
            return_value=([], {}),
        ):
            controller.append_drawing_point_from_context_menu(20, 0)

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [(0, 0)])
        self.assertEqual(window.route_drawing_state.undo_stack, [])

    def test_undo_removes_context_menu_inserted_point_from_recorded_index(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        with patch(
            "ui_island.controllers.route_panel_controller.open_insert_point_dialog",
            return_value=(["2026010101"], {"2026010101": 0}),
        ):
            controller.append_drawing_point_from_context_menu(10, 0)
        controller.undo_route_drawing()

        self.assertEqual([(point["x"], point["y"]) for point in window.route_drawing_state.draft_points], [
            (0, 0),
            (100, 0),
        ])
        self.assertFalse(window.route_drawing_state.dirty)

    def test_save_route_drawing_preserves_insert_at_end_without_writing_route_field(self) -> None:
        window = _FakeWindow("")
        window.route_mgr = _FakeRouteManager({
            "2026010101": {
                "points": [{"x": 1, "y": 2}],
                "loop": False,
            }
        })
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(
            route_id="2026010101",
            category="routes",
            name="route",
            points=[{"x": 1, "y": 2}],
        )
        window.route_drawing_state.insert_at_end = False
        controller = self._controller_for(window)
        controller._sync_route_drawing_ui = lambda: None

        with patch("ui_island.controllers.route_panel_controller.toast"):
            self.assertTrue(controller.save_route_drawing())

        self.assertFalse(window.route_drawing_state.insert_at_end)
        self.assertNotIn("insert_at_end", window.route_mgr.routes["2026010101"])
        self.assertNotIn("insert_at_end", window.route_mgr.saved_points_calls[-1][1][0])

    def test_update_route_drawing_toolbar_syncs_insert_at_end_checkbox(self) -> None:
        window = _FakeWindow("")
        window.route_drawing_state = RouteDrawingState()
        window.route_drawing_state.begin(route_id="2026010101", category="routes", name="route", points=[])
        window.route_drawing_state.insert_at_end = False
        window.route_drawing_toolbar = _FakeToolbar()
        window.route_drawing_toolbar_buttons = {
            "pause": _FakeButton(),
            "collect": _FakeButton(),
            "insert_at_end": _FakeButton(),
            "add_annotation": _FakeButton(),
            "same_annotation": _FakeButton(),
            "hide_other_routes": _FakeButton(),
            "loop": _FakeButton(),
            "select_annotation": _FakeButton(),
        }
        controller = self._controller_for(window)
        controller.position_route_drawing_toolbar = lambda: None

        controller._update_route_drawing_toolbar()

        self.assertFalse(window.route_drawing_toolbar_buttons["insert_at_end"].checked)
        self.assertEqual(window.route_drawing_toolbar_buttons["insert_at_end"].blocked_states, [True, False])
        self.assertTrue(window.route_drawing_toolbar.shown)

    def test_jump_to_route_node_paused_relocates_to_first_valid_node(self) -> None:
        window = _FakeWindow("")
        window._mode = _Mode.PAUSED
        window.route_mgr = _FakeRouteManager({
            "route-1": {
                "points": [
                    {"x": "bad", "y": 2},
                    {"x": 10, "y": 20, "visited": True},
                    {"x": 30, "y": 40, "visited": False},
                ],
            }
        })
        controller = self._controller_for(window)

        with patch("ui_island.controllers.route_panel_controller.toast"):
            controller.jump_to_route_node("route-1")

        self.assertEqual(window.relocate_calls, [(10, 20)])
        self.assertEqual(window.map_view.focus_calls, [])

    def test_jump_to_route_node_navigation_focuses_first_unvisited_without_relocating(self) -> None:
        window = _FakeWindow("")
        window._mode = _Mode.TRACKING_STABLE
        window.route_mgr = _FakeRouteManager({
            "route-1": {
                "points": [
                    {"x": 10, "y": 20, "visited": True},
                    {"x": 30, "y": 40, "visited": False},
                    {"x": 50, "y": 60, "visited": False},
                ],
            }
        })
        controller = self._controller_for(window)

        with patch("ui_island.controllers.route_panel_controller.toast"):
            controller.jump_to_route_node("route-1")

        self.assertEqual(window.map_view.focus_calls, [(30, 40)])
        self.assertEqual(window.relocate_calls, [])

    def test_jump_to_route_node_navigation_completed_falls_back_to_first_node(self) -> None:
        window = _FakeWindow("")
        window._mode = _Mode.TRACKING_STABLE
        window.route_mgr = _FakeRouteManager({
            "route-1": {
                "points": [
                    {"x": 10, "y": 20, "visited": True},
                    {"x": 30, "y": 40, "visited": True},
                ],
            }
        })
        controller = self._controller_for(window)

        with patch("ui_island.controllers.route_panel_controller.toast") as toast_mock:
            controller.jump_to_route_node("route-1")

        self.assertEqual(window.map_view.focus_calls, [(10, 20)])
        self.assertEqual(window.relocate_calls, [])
        self.assertIn("1", toast_mock.call_args.args[1])

    def test_jump_to_route_node_empty_route_shows_info_without_moving(self) -> None:
        window = _FakeWindow("")
        window._mode = _Mode.TRACKING_STABLE
        window.route_mgr = _FakeRouteManager({"route-1": {"points": [{"x": "bad"}]}})
        controller = self._controller_for(window)

        with patch("ui_island.controllers.route_panel_controller.styled_info") as info_mock:
            controller.jump_to_route_node("route-1")

        self.assertTrue(info_mock.called)
        self.assertEqual(window.map_view.focus_calls, [])
        self.assertEqual(window.relocate_calls, [])


if __name__ == "__main__":
    unittest.main()
