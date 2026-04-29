import tempfile
import unittest
from pathlib import Path

from tools.json_txt_converter import (
    MODE_AUTO,
    MODE_JSON_TO_TXT,
    MODE_TXT_TO_JSON,
    convert_files,
)


class JsonTxtConverterTests(unittest.TestCase):
    def test_json_to_txt_preserves_bytes(self) -> None:
        payload = b'\xef\xbb\xbf{"name":"demo"}\r\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "input"
            output_dir = root / "output"
            source_dir.mkdir()
            source = source_dir / "route.json"
            source.write_bytes(payload)

            report = convert_files(source_dir, output_dir, MODE_JSON_TO_TXT)

            self.assertEqual(report.converted, 1)
            self.assertEqual((output_dir / "route.txt").read_bytes(), payload)
            self.assertEqual(source.read_bytes(), payload)

    def test_txt_to_json_preserves_bytes(self) -> None:
        payload = b"plain text that might be json later"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "input"
            output_dir = root / "output"
            source_dir.mkdir()
            (source_dir / "route.txt").write_bytes(payload)

            report = convert_files(source_dir, output_dir, MODE_TXT_TO_JSON)

            self.assertEqual(report.converted, 1)
            self.assertEqual((output_dir / "route.json").read_bytes(), payload)

    def test_auto_mode_converts_json_and_txt_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "input"
            output_dir = root / "output"
            source_dir.mkdir()
            (source_dir / "a.json").write_bytes(b"json")
            (source_dir / "b.txt").write_bytes(b"txt")
            (source_dir / "c.md").write_bytes(b"ignored")

            report = convert_files(source_dir, output_dir, MODE_AUTO)

            self.assertEqual(report.converted, 2)
            self.assertEqual(report.ignored, 1)
            self.assertEqual((output_dir / "a.txt").read_bytes(), b"json")
            self.assertEqual((output_dir / "b.json").read_bytes(), b"txt")
            self.assertFalse((output_dir / "c.md").exists())

    def test_recursive_mode_preserves_relative_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "input"
            nested = source_dir / "sub" / "nested"
            output_dir = root / "output"
            nested.mkdir(parents=True)
            (nested / "route.json").write_bytes(b"payload")

            report = convert_files(source_dir, output_dir, MODE_JSON_TO_TXT)

            self.assertEqual(report.converted, 1)
            self.assertEqual((output_dir / "sub" / "nested" / "route.txt").read_bytes(), b"payload")

    def test_existing_output_is_skipped_unless_overwrite_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "input"
            output_dir = root / "output"
            source_dir.mkdir()
            output_dir.mkdir()
            (source_dir / "route.json").write_bytes(b"new")
            target = output_dir / "route.txt"
            target.write_bytes(b"old")

            skipped = convert_files(source_dir, output_dir, MODE_JSON_TO_TXT)
            overwritten = convert_files(source_dir, output_dir, MODE_JSON_TO_TXT, overwrite=True)

            self.assertEqual(skipped.skipped, 1)
            self.assertEqual(overwritten.converted, 1)
            self.assertEqual(target.read_bytes(), b"new")

    def test_input_and_output_directories_must_be_different(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                convert_files(root, root, MODE_JSON_TO_TXT)
