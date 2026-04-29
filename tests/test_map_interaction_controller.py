import unittest
from unittest.mock import patch

from ui_island.controllers.map_interaction_controller import MapInteractionController


class _FakeMapView:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.undo_available_values: list[bool] = []

    def _refresh_from_last_frame(self) -> None:
        self.refresh_count += 1

    def set_route_point_move_undo_available(self, available: bool) -> None:
        self.undo_available_values.append(bool(available))


class _FakeRoutePanelController:
    def __init__(self) -> None:
        self.refresh_count = 0

    def refresh_tracked_routes(self) -> None:
        self.refresh_count += 1


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
        self.insert_calls: list[dict] = []

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


class _FakeWindow:
    def __init__(self) -> None:
        self.route_mgr = _FakeRouteManager()
        self.map_view = _FakeMapView()
        self.route_panel_controller = _FakeRoutePanelController()


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
