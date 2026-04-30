import unittest
from unittest.mock import patch

from ui_island.services import resource_metadata


class ResourceMetadataTests(unittest.TestCase):
    def test_ensure_metadata_merges_runtime_enable_versions(self) -> None:
        payload = {}
        with patch("config.APP_ENABLE_ROUTE_VERSIONS", ["0.1.2", "0.1.3"], create=True):
            resource_metadata.ensure_metadata(payload, include_route_defaults=True)

        self.assertEqual(payload["enable_versions"][:2], ["0.1.2", "0.1.3"])
        self.assertIn(resource_metadata.APP_FORMAT_VERSION, payload["enable_versions"])

    def test_ensure_metadata_keeps_route_defaults_only(self) -> None:
        payload = {"loop": "yes", "notes": 123}

        resource_metadata.ensure_metadata(payload, include_route_defaults=True)

        self.assertTrue(payload["loop"])
        self.assertEqual(payload["notes"], "123")


if __name__ == "__main__":
    unittest.main()
