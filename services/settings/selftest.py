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
        for text in ('{"providers":', '{"a":1,"a":2}', '[]'):
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

    def test_preparation_rejects_what_is_not_strict_json(self):
        for text in ('{"providers":{},"providers":{}}', '{"number":1e999}', '[]', '{"a":', 42, None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                config.transact({"path": self.path, "operation": "validate", "text": text})
        self.assertFalse(Path(self.path).exists())

    def test_fields_are_the_applications_to_judge(self):
        # services/settings/settings.js owns what a field may hold; a field it
        # would refuse still reads, so the rest of the file stays in force.
        value = {"providers": {"local": {"enabled": 0, "notesDir": "/example"}}, "appearance": None,
                 "keybindings": [{"command": "app/newNote", "keys": ["Ctrl+V"]}]}
        revision = self.write(value)
        self.assertEqual(config.snapshot(self.path)["config"], value)
        result = self.theme(revision)
        self.assertTrue(result["ok"])
        saved = json.loads(Path(self.path).read_text())
        self.assertEqual(saved["appearance"], {"theme": "example.colors/dark"})
        self.assertEqual(saved["providers"], value["providers"])
        self.assertEqual(saved["keybindings"], value["keybindings"], "theme changes preserve overrides")
        for theme in ("", None, 7):
            with self.subTest(theme=theme), self.assertRaises(ValueError):
                self.theme(result["revision"], theme)

    def test_first_write_adopts_a_file_another_host_made(self):
        create = {"path": self.path, "operation": "create", "text": '{"providers": {}}'}
        made = config.transact(create)
        self.assertTrue(made["ok"])
        self.assertEqual(json.loads(Path(self.path).read_text()), {"providers": {}})
        theirs = self.write({"providers": {"local": {"notesDir": "/theirs"}}})
        adopted = config.transact(dict(create, text='{"providers": {"local": {"notesDir": "/mine"}}}'))
        self.assertEqual(adopted["revision"], theirs)
        self.assertEqual(adopted["config"]["providers"]["local"]["notesDir"], "/theirs")
        self.assertEqual(config.snapshot(self.path)["revision"], theirs)

    def test_a_request_names_its_file_and_text_as_strings(self):
        # The envelope (lib/jsondata.answer) turns these into the answer's error.
        for request in ({"path": 7, "operation": "read"}, {"operation": "read"},
                        {"path": self.path, "operation": "replace", "revision": "missing", "text": 42}):
            with self.subTest(request=request), self.assertRaises((ValueError, KeyError)):
                config.transact(request)
        self.assertFalse(Path(self.path).exists())


if __name__ == "__main__":
    unittest.main()
