"""Check rollback in a temporary project; never touch the live frontend."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ui_snapshot


class SnapshotTests(unittest.TestCase):
    def test_preview_restore_and_preserve_current_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app").mkdir()
            page = root / "app" / "page.tsx"
            page.write_text("original", encoding="utf-8")
            (root / "app" / ".env.local").write_text("private", encoding="utf-8")
            with patch.object(ui_snapshot, "ROOT", root), patch.object(ui_snapshot, "STORE", root / "output" / "ui-versions"), contextlib.redirect_stdout(io.StringIO()):
                before = ui_snapshot.create("before-redesign")
                self.assertFalse((before / "files" / "app" / ".env.local").exists())
                page.write_text("new interface", encoding="utf-8")
                ui_snapshot.restore(str(before), False)
                self.assertEqual(page.read_text(), "new interface")
                ui_snapshot.restore(str(before), True)
                self.assertEqual(page.read_text(), "original")
                checkpoint = next((root / "output" / "ui-versions").glob("*-before-restore"))
                self.assertEqual((checkpoint / "files" / "app" / "page.tsx").read_text(), "new interface")

    def test_corrupt_snapshot_is_rejected_before_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app").mkdir()
            (root / "app" / "page.tsx").write_text("original")
            with patch.object(ui_snapshot, "ROOT", root), patch.object(ui_snapshot, "STORE", root / "output" / "ui-versions"), contextlib.redirect_stdout(io.StringIO()):
                before = ui_snapshot.create("manual")
                (before / "files" / "app" / "page.tsx").write_text("corrupted")
                with self.assertRaises(SystemExit):
                    ui_snapshot.restore(str(before), True)
                self.assertEqual((root / "app" / "page.tsx").read_text(), "original")

    def test_unsafe_manifest_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(ui_snapshot, "ROOT", root), patch.object(ui_snapshot, "STORE", root / "output" / "ui-versions"), contextlib.redirect_stdout(io.StringIO()):
                before = ui_snapshot.create("manual")
                (before / "manifest.json").write_text(json.dumps({"files": [{"path": "../outside", "sha256": "invalid"}]}))
                with self.assertRaises(SystemExit):
                    ui_snapshot.restore(str(before), True)


if __name__ == "__main__":
    unittest.main()
