import unittest
from unittest.mock import patch

from ui_island.controllers.map_interaction_controller import MapInteractionController
from ui_island.state import RouteDrawingState


class _FakeMapView:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.undo_available_values: list[bool] = []

    def _refresh_from_last_frame(self) -> None:
        self.refresh_count += 1

    def set_route_point_move_undo_available(self, available: bool) -> None:
        self.undo_available_values.append(bool(available))


class _FakeRoutePanelController:
    def __init__(self, window=None) -> None:
        self.window = window
        self.refresh_count = 0
        self.append_calls: list[tuple[int, int, dict | None]] = []
        self.change_order_calls: list[int] = []

    def refresh_tracked_routes(self) -> None:
        self.refresh_count += 1

    def append_drawing_point_from_context_menu(self, x: int, y: int, point_fields: dict | None = None) -> None:
        drawing = getattr(self.window, "route_drawing_state", None)
        if drawing is not None and drawing.active and not drawing.paused:
            self.append_calls.append((x, y, dict(point_fields or {})))

    def change_drawing_point_order(self, point_index: int) -> None:
        self.change_order_calls.append(int(point_index))


class _FakeRouteManager:
    def __init__(self) -> None:
        self.routes = {
            "route-1": {
                "display_name": "Route 1",
                "points": [{"x": 1, "y": 2}, {"x": 10, "y": 20}],
            }
        }
        self.position_calls: list[tuple[str, int, int, int, bool]] = []
        self.fail_persist = False
        self.delete_outcomes = {"route-1": [0]}
        self.insert_outcomes = {"route-1": 1}
        self.visible_ids = ["route-1"]
        self.annotation_items = [{"typeId": "flower", "type": "Sunflower"}]
        self.annotation_points = {
            ("flower", 0): {
                "x": 12,
                "y": 34,
                "typeId": "flower",
                "type": "Sunflower",
                "label": "Field Flower",
                "radius": 25,
            }
        }
        self.insert_calls: list[dict] = []
        self.reorder_calls: list[tuple[str, int, int]] = []
        self.fail_reorder = False

    def set_point_position(self, route_id: str, point_index: int, x: int, y: int, persist: bool = True) -> bool:
        self.position_calls.append((route_id, point_index, int(x), int(y), bool(persist)))
        if persist and self.fail_persist:
            return False
        route = self.routes.get(route_id)
        points = route.get("points", []) if route is not None else []
        if not (0 <= point_index < len(points)):
            return False
        points[point_index]["x"] = int(x)
        points[point_index]["y"] = int(y)
        return True

    def route_for_id(self, route_id: str) -> dict | None:
        return self.routes.get(route_id)

    def summarize_route(self, route_id: str) -> dict | None:
        route = self.routes.get(route_id)
        if route is None:
            return None
        return {
            "display_label": route.get("display_name", ""),
            "points_count": len(route.get("points", [])),
        }

    def delete_points_from_routes(self, _deletions: dict[str, list[int]]) -> dict[str, list[int]]:
        return self.delete_outcomes

    def visible_route_ids(self) -> list[str]:
        return list(self.visible_ids)

    def annotation_type_items(self) -> list[dict]:
        return [dict(item) for item in self.annotation_items]

    def annotation_point(self, type_id: str, point_index: int) -> dict | None:
        point = self.annotation_points.get((type_id, point_index))
        return dict(point) if point is not None else None

    def suggest_insertion_index(self, _route_id: str, _x: int, _y: int) -> int:
        return 1

    def insert_point_into_routes(
        self,
        x: int,
        y: int,
        route_ids: list[str],
        overrides: dict[str, int] | None = None,
        point_fields: dict | None = None,
    ) -> dict[str, int | None]:
        self.insert_calls.append({
            "x": x,
            "y": y,
            "route_ids": list(route_ids),
            "overrides": dict(overrides or {}),
            "point_fields": dict(point_fields or {}),
        })
        return self.insert_outcomes

    def reorder_route_point(self, route_id: str, from_index: int, to_index: int) -> bool:
        self.reorder_calls.append((route_id, int(from_index), int(to_index)))
        if self.fail_reorder:
            return False
        route = self.routes.get(route_id)
        points = route.get("points", []) if route is not None else []
        if not (0 <= from_index < len(points)):
            return False
        target = max(0, min(len(points) - 1, int(to_index)))
        if from_index == target:
            return False
        point = points.pop(from_index)
        points.insert(target, point)
        return True


class _FakeWindow:
    def __init__(self) -> None:
        self.route_mgr = _FakeRouteManager()
        self.map_view = _FakeMapView()
        self.route_drawing_state = RouteDrawingState()
        self.route_panel_controller = _FakeRoutePanelController(self)


class MapInteractionControllerTests(unittest.TestCase):
    def _controller(self) -> tuple[MapInteractionController, _FakeWindow]:
        window = _FakeWindow()
        return MapInteractionController(window), window

    def test_move_route_point_preview_updates_memory_without_persisting(self) -> None:
        controller, window = self._controller()

        controller.move_route_point_preview("route-1", 0, 5, 6)

        self.assertEqual(window.route_mgr.routes["route-1"]["points"][0], {"x": 5, "y": 6})
        self.assertEqual(window.route_mgr.position_calls, [("route-1", 0, 5, 6, False)])
        self.assertEqual(window.map_view.refresh_count, 1)
        self.assertEqual(window.route_panel_controller.refresh_count, 1)

    def test_add_annotated_point_selects_annotation_then_reuses_route_insert_flow(self) -> None:
        controller, window = self._controller()

        with (
            patch(
                "ui_island.controllers.map_interaction_controller.open_annotation_type_picker",
                return_value={"typeId": "flower", "type": "Sunflower", "label": "ignored"},
            ) as picker,
            patch.object(controller, "add_point_to_routes") as add_point_to_routes,
        ):
            controller.add_annotated_point_to_routes(12, 34)

        picker.assert_called_once_with(window, window.route_mgr.annotation_items, "")
        add_point_to_routes.assert_called_once_with(
            12,
            34,
            point_fields={"typeId": "flower", "type": "Sunflower"},
        )

    def test_add_annotated_point_cancel_does_not_insert(self) -> None:
        controller, window = self._controller()

        with patch("ui_island.controllers.map_interaction_controller.open_annotation_type_picker", return_value=None):
            controller.add_annotated_point_to_routes(12, 34)

        self.assertEqual(window.route_mgr.insert_calls, [])

    def test_add_annotated_point_without_annotation_types_shows_info_before_insert(self) -> None:
        controller, window = self._controller()
        window.route_mgr.annotation_items = []

        with (
            patch("ui_island.controllers.map_interaction_controller.open_annotation_type_picker") as picker,
            patch("ui_island.controllers.map_interaction_controller.styled_info") as styled_info,
        ):
            controller.add_annotated_point_to_routes(12, 34)

        picker.assert_not_called()
        styled_info.assert_called_once()
        self.assertEqual(window.route_mgr.insert_calls, [])

    def test_add_annotated_point_without_visible_routes_does_not_open_picker(self) -> None:
        controller, window = self._controller()
        window.route_mgr.visible_ids = []

        with (
            patch("ui_island.controllers.map_interaction_controller.open_annotation_type_picker") as picker,
            patch("ui_island.controllers.map_interaction_controller.styled_info") as styled_info,
        ):
            controller.add_annotated_point_to_routes(12, 34)

        picker.assert_not_called()
        styled_info.assert_called_once()
        self.assertEqual(window.route_mgr.insert_calls, [])

    def test_add_annotation_to_route_uses_drawing_draft_when_pure_drawing_active(self) -> None:
        controller, window = self._controller()
        window.route_drawing_state.begin(route_id="route-1", category="routes", name="Route 1", points=[])

        with patch.object(controller, "add_point_to_routes") as add_point_to_routes:
            controller.add_annotation_to_route("flower", 0)

        add_point_to_routes.assert_not_called()
        self.assertEqual(len(window.route_panel_controller.append_calls), 1)
        x, y, point_fields = window.route_panel_controller.append_calls[0]
        self.assertEqual((x, y), (12, 34))
        self.assertEqual(point_fields["typeId"], "flower")
        self.assertEqual(point_fields["type"], "Sunflower")
        self.assertEqual(point_fields["label"], "Field Flower")

    def test_add_annotation_to_route_does_not_write_json_when_pure_drawing_paused(self) -> None:
        controller, window = self._controller()
        window.route_drawing_state.begin(route_id="route-1", category="routes", name="Route 1", points=[])
        window.route_drawing_state.paused = True

        with patch.object(controller, "add_point_to_routes") as add_point_to_routes:
            controller.add_annotation_to_route("flower", 0)

        add_point_to_routes.assert_not_called()
        self.assertEqual(window.route_panel_controller.append_calls, [])
        self.assertEqual(window.route_mgr.insert_calls, [])

    def test_add_annotation_to_route_keeps_json_flow_outside_pure_drawing(self) -> None:
        controller, window = self._controller()

        with patch.object(controller, "add_point_to_routes") as add_point_to_routes:
            controller.add_annotation_to_route("flower", 0)

        add_point_to_routes.assert_called_once()
        args, kwargs = add_point_to_routes.call_args
        self.assertEqual(args, (12, 34))
        self.assertEqual(kwargs["point_fields"]["typeId"], "flower")

    def test_finish_move_route_point_persists_and_records_single_undo(self) -> None:
        controller, window = self._controller()

        with patch("ui_island.controllers.map_interaction_controller.toast") as toast:
            controller.finish_move_route_point("route-1", 0, 1, 2, 7, 8)

        self.assertEqual(window.route_mgr.routes["route-1"]["points"][0], {"x": 7, "y": 8})
        self.assertEqual(window.route_mgr.position_calls[-2:], [
            ("route-1", 0, 1, 2, False),
            ("route-1", 0, 7, 8, True),
        ])
        self.assertTrue(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values[-1], True)
        toast.assert_called_once()

    def test_finish_move_route_point_ignores_unchanged_coordinates(self) -> None:
        controller, window = self._controller()

        controller.finish_move_route_point("route-1", 0, 1, 2, 1, 2)

        self.assertEqual(window.route_mgr.position_calls, [])
        self.assertFalse(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values, [])

    def test_finish_move_route_point_failure_restores_before_position(self) -> None:
        controller, window = self._controller()
        window.route_mgr.routes["route-1"]["points"][0] = {"x": 7, "y": 8}
        window.route_mgr.fail_persist = True

        with patch("ui_island.controllers.map_interaction_controller.styled_info") as styled_info:
            controller.finish_move_route_point("route-1", 0, 1, 2, 7, 8)

        self.assertEqual(window.route_mgr.routes["route-1"]["points"][0], {"x": 1, "y": 2})
        self.assertFalse(controller.has_route_point_move_undo())
        styled_info.assert_called_once()

    def test_undo_route_point_move_restores_before_position_and_clears_undo(self) -> None:
        controller, window = self._controller()
        with patch("ui_island.controllers.map_interaction_controller.toast"):
            controller.finish_move_route_point("route-1", 0, 1, 2, 7, 8)

        with patch("ui_island.controllers.map_interaction_controller.toast") as toast:
            controller.undo_route_point_move()

        self.assertEqual(window.route_mgr.routes["route-1"]["points"][0], {"x": 1, "y": 2})
        self.assertEqual(window.route_mgr.position_calls[-1], ("route-1", 0, 1, 2, True))
        self.assertFalse(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values[-1], False)
        toast.assert_called_once()

    def test_change_point_order_uses_drawing_branch_without_json_write(self) -> None:
        controller, window = self._controller()
        window.route_drawing_state.begin(route_id="route-1", category="routes", name="Route 1", points=[
            {"x": 1, "y": 2},
            {"x": 10, "y": 20},
        ])

        with patch("ui_island.controllers.map_interaction_controller.open_point_order_dialog") as dialog:
            controller.change_point_order("route-1", 1)

        dialog.assert_not_called()
        self.assertEqual(window.route_panel_controller.change_order_calls, [1])
        self.assertEqual(window.route_mgr.reorder_calls, [])

    def test_change_point_order_reorders_route_and_records_undo(self) -> None:
        controller, window = self._controller()
        window.route_mgr.routes["route-1"]["points"] = [
            {"id": "a", "x": 1, "y": 2},
            {"id": "b", "x": 10, "y": 20},
            {"id": "c", "x": 30, "y": 40},
        ]

        with (
            patch("ui_island.controllers.map_interaction_controller.open_point_order_dialog", return_value=2) as dialog,
            patch("ui_island.controllers.map_interaction_controller.toast") as toast,
        ):
            controller.change_point_order("route-1", 0)

        dialog.assert_called_once_with(window, "Route 1", 0, 3)
        self.assertEqual(window.route_mgr.reorder_calls, [("route-1", 0, 2)])
        self.assertEqual([point["id"] for point in window.route_mgr.routes["route-1"]["points"]], ["b", "c", "a"])
        self.assertTrue(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values[-1], True)
        self.assertEqual(window.map_view.refresh_count, 1)
        self.assertEqual(window.route_panel_controller.refresh_count, 1)
        toast.assert_called_once()

    def test_change_point_order_cancel_or_same_position_is_noop(self) -> None:
        controller, window = self._controller()

        with patch("ui_island.controllers.map_interaction_controller.open_point_order_dialog", return_value=None):
            controller.change_point_order("route-1", 0)
        with patch("ui_island.controllers.map_interaction_controller.open_point_order_dialog", return_value=0):
            controller.change_point_order("route-1", 0)

        self.assertEqual(window.route_mgr.reorder_calls, [])
        self.assertFalse(controller.has_route_point_move_undo())

    def test_undo_route_point_order_restores_previous_order_and_clears_undo(self) -> None:
        controller, window = self._controller()
        window.route_mgr.routes["route-1"]["points"] = [
            {"id": "a", "x": 1, "y": 2},
            {"id": "b", "x": 10, "y": 20},
            {"id": "c", "x": 30, "y": 40},
        ]
        with (
            patch("ui_island.controllers.map_interaction_controller.open_point_order_dialog", return_value=2),
            patch("ui_island.controllers.map_interaction_controller.toast"),
        ):
            controller.change_point_order("route-1", 0)

        with patch("ui_island.controllers.map_interaction_controller.toast") as toast:
            controller.undo_route_point_move()

        self.assertEqual(window.route_mgr.reorder_calls[-1], ("route-1", 2, 0))
        self.assertEqual([point["id"] for point in window.route_mgr.routes["route-1"]["points"]], ["a", "b", "c"])
        self.assertFalse(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values[-1], False)
        toast.assert_called_once()

    def test_change_point_order_failure_shows_info_without_undo(self) -> None:
        controller, window = self._controller()
        window.route_mgr.fail_reorder = True

        with (
            patch("ui_island.controllers.map_interaction_controller.open_point_order_dialog", return_value=1),
            patch("ui_island.controllers.map_interaction_controller.styled_info") as styled_info,
        ):
            controller.change_point_order("route-1", 0)

        styled_info.assert_called_once()
        self.assertFalse(controller.has_route_point_move_undo())

    def test_successful_delete_clears_point_move_undo(self) -> None:
        controller, window = self._controller()
        controller._set_point_move_undo({
            "route_id": "route-1",
            "point_index": 0,
            "before": (1, 2),
            "after": (7, 8),
        })

        with (
            patch("ui_island.controllers.map_interaction_controller.styled_confirm", return_value=True),
            patch("ui_island.controllers.map_interaction_controller.toast"),
        ):
            controller.delete_points_from_routes({"route-1": [0]})

        self.assertFalse(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values[-1], False)

    def test_successful_insert_clears_point_move_undo(self) -> None:
        controller, window = self._controller()
        controller._set_point_move_undo({
            "route_id": "route-1",
            "point_index": 0,
            "before": (1, 2),
            "after": (7, 8),
        })

        with patch("ui_island.controllers.map_interaction_controller.toast"):
            controller.add_point_to_routes(3, 4, show_dialog=False)

        self.assertFalse(controller.has_route_point_move_undo())
        self.assertEqual(window.map_view.undo_available_values[-1], False)


if __name__ == "__main__":
    unittest.main()
