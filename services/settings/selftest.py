"""Config transactions preserve data and reject stale/concurrent writers."""
import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config_io as config


class Transactions(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "config.json")

    def write(self, value):
        Path(self.path).write_text(json.dumps(value))
        return config.snapshot(self.path)["revision"]

    def theme(self, revision, theme="example.colors/dark"):
        return config.transact({"path": self.path, "operation": "theme", "revision": revision, "theme": theme})

    def test_patch_preserves_order_and_unknown_fields(self):
        value = {"providers": {"sticky": {"enabled": False}, "local": {"notesDir": "/example"}},
                 "future": {"nested": [1, "unicode 漢"]}, "appearance": {"future": True}}
        result = self.theme(self.write(value))
        self.assertTrue(result["ok"])
        saved = json.loads(Path(self.path).read_text())
        self.assertEqual(list(saved["providers"]), ["sticky", "local"])
        self.assertEqual(saved["providers"], value["providers"])
        self.assertEqual(saved["future"], value["future"])
        self.assertTrue(saved["appearance"]["future"])
        self.assertEqual(config.snapshot(self.path)["revision"], result["revision"])

    def test_concurrent_writers_have_one_winner(self):
        revision = self.write({})
        with concurrent.futures.ProcessPoolExecutor(2) as pool:
            requests = [{"path": self.path, "operation": "theme", "revision": revision,
                         "theme": "example.colors/" + theme} for theme in ("dark", "light")]
            results = list(pool.map(config.transact, requests))
        self.assertEqual(sum(bool(result.get("ok")) for result in results), 1)
        self.assertEqual(sum(result.get("kind") == "stale" for result in results), 1)

    def test_missing_and_failed_write(self):
        self.assertEqual(config.snapshot(self.path)["revision"], "missing")
        with patch.object(config, "write_atomic", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.theme("missing")
        self.assertFalse(Path(self.path).exists())
        self.assertTrue(self.theme("missing")["ok"])
        self.assertEqual(self.theme("missing")["kind"], "stale")

    def test_invalid_file_is_not_repaired_by_theme_patch(self):
        for text in ('{"providers":', '{"a":1,"a":2}', '[]', '{"appearance":null}'):
            Path(self.path).write_text(text)
            snapshot = config.snapshot(self.path)
            self.assertEqual(snapshot["kind"], "invalid")
            self.assertEqual(self.theme(snapshot["revision"])["kind"], "invalid")
            self.assertEqual(Path(self.path).read_text(), text)
            result = config.transact({"path": self.path, "operation": "replace",
                                      "revision": snapshot["revision"], "text": "{}"})
            self.assertTrue(result["ok"])

    def test_bounds_and_special_files(self):
        Path(self.path).write_text(" " * (config.MAX_BYTES + 1))
        self.assertEqual(config.snapshot(self.path)["kind"], "too-large")
        Path(self.path).unlink()
        os.mkfifo(self.path)
        self.assertEqual(config.snapshot(self.path)["kind"], "unreadable")
        Path(self.path).unlink()
        Path(self.path).symlink_to("elsewhere")
        self.assertEqual(config.snapshot(self.path)["kind"], "unreadable")

    def test_lock_timeout(self):
        with config.config_lock(self.path):
            with self.assertRaises(TimeoutError):
                with config.config_lock(self.path, timeout=0.03):
                    self.fail("a second lock was acquired")

    def test_preparation_rejects_invalid_shapes_without_writing(self):
        for text in ('{"providers":{},"providers":{}}', '{"appearance":{"theme":null}}',
                     '{"plugins":{"example.code":{"enabled":"yes"}}}', '{"number":1e999}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                config.transact({"path": self.path, "operation": "validate", "text": text})
        self.assertFalse(Path(self.path).exists())

    def test_keybinding_validation_and_persistence(self):
        bindings = [{"command": "app/newNote", "keys": ["Ctrl+Alt+N", "F6"]},
                    {"command": "org.example.greeting/greet", "keys": []}]
        self.assertEqual(config.parse(json.dumps({"keybindings": bindings}))["keybindings"], bindings)
        result = self.theme(self.write({"keybindings": bindings}))
        self.assertEqual(result["config"]["keybindings"], bindings, "theme changes preserve overrides")
        for invalid in (None, {}, [None], [{"command": "newNote", "keys": []}],
                        [{"command": "app/newNote", "keys": "Ctrl+N"}], bindings + bindings):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                config.parse(json.dumps({"keybindings": invalid}))
        for key in ("Ctrl+V", "Ctrl+Z", "Shift+A", "A", "Ctrl+Ctrl+N", "Ctrl+", "Ctrl+F36", "constructor+N"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                config.parse(json.dumps({"keybindings": [{"command": "app/newNote", "keys": [key]}]}))


if __name__ == "__main__":
    unittest.main()
