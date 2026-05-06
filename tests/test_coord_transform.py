import unittest
from unittest.mock import patch

import config
from ui_island.services import coord_transform
from ui_island.services.resource_metadata import (
    apply_coord_transform_to_payload,
    coord_transform_from_payload,
    is_identity_coord_transform,
)


class CoordTransformResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patches = [
            patch.object(config, "COORD_SCALE_X", 1.0),
            patch.object(config, "COORD_SCALE_Y", 1.0),
            patch.object(config, "COORD_OFFSET_X", 0.0),
            patch.object(config, "COORD_OFFSET_Y", 0.0),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._stop_patches)

    def _stop_patches(self) -> None:
        for p in self._patches:
            p.stop()

    def test_no_payload_no_global_returns_identity(self) -> None:
        adapter = coord_transform.resolve_route_adapter({})
        self.assertTrue(adapter.is_identity)

    def test_global_override_applies_when_payload_absent(self) -> None:
        with patch.object(config, "COORD_OFFSET_X", 100.0):
            adapter = coord_transform.resolve_route_adapter({})
        self.assertEqual(adapter.offset_x, 100.0)
        self.assertFalse(adapter.is_identity)

    def test_payload_override_beats_global(self) -> None:
        payload = {
            "coord_transform": {
                "scale_x": 2.0,
                "scale_y": 1.0,
                "offset_x": 0.0,
                "offset_y": 0.0,
            }
        }
        with patch.object(config, "COORD_OFFSET_X", 999.0):
            adapter = coord_transform.resolve_route_adapter(payload)
        self.assertEqual(adapter.scale_x, 2.0)
        self.assertEqual(adapter.offset_x, 0.0)

    def test_annotation_resolver_uses_same_logic(self) -> None:
        payload = {"coord_transform": {"offset_y": 50.0}}
        adapter = coord_transform.resolve_annotation_adapter(payload)
        self.assertEqual(adapter.offset_y, 50.0)
        self.assertEqual(adapter.scale_x, 1.0)


class CoordTransformPayloadHelpersTests(unittest.TestCase):
    def test_coord_transform_from_payload_missing(self) -> None:
        self.assertIsNone(coord_transform_from_payload({}))
        self.assertIsNone(coord_transform_from_payload(None))
        self.assertIsNone(coord_transform_from_payload({"coord_transform": "not a dict"}))

    def test_coord_transform_from_payload_valid(self) -> None:
        result = coord_transform_from_payload(
            {"coord_transform": {"scale_x": 2, "offset_y": "5"}}
        )
        self.assertEqual(result, {"scale_x": 2.0, "scale_y": 1.0, "offset_x": 0.0, "offset_y": 5.0})

    def test_apply_strips_identity(self) -> None:
        payload = {"coord_transform": {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 0.0, "offset_y": 0.0}}
        apply_coord_transform_to_payload(payload, payload["coord_transform"])
        self.assertNotIn("coord_transform", payload)

    def test_apply_writes_non_identity(self) -> None:
        payload = {}
        apply_coord_transform_to_payload(
            payload, {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 50.0, "offset_y": 0.0}
        )
        self.assertEqual(payload["coord_transform"]["offset_x"], 50.0)

    def test_is_identity(self) -> None:
        self.assertTrue(is_identity_coord_transform(None))
        self.assertTrue(is_identity_coord_transform({}))
        self.assertTrue(is_identity_coord_transform(
            {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 0.0, "offset_y": 0.0}
        ))
        self.assertFalse(is_identity_coord_transform({"scale_x": 2.0}))


if __name__ == "__main__":
    unittest.main()
