"""Package discovery, ownership, resource boundaries, and theme validation."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import manifest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "themes"))
import theme

ROOT = Path(__file__).resolve().parents[2]


class Catalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = {key: str(self.root / key) for key in ("builtinRoot", "userRoot", "themesRoot", "legacyRoot")}
        for path in self.request.values():
            Path(path).mkdir()
        self.request["settings"] = {}

    def package(self, name="colors", directory="one"):
        path = Path(self.request["userRoot"]) / directory
        shutil.copytree(ROOT / "examples/plugins" / name, path)
        return path

    def test_builtin_packages_are_self_contained(self):
        self.request["builtinRoot"] = str(ROOT / "plugins")
        result = manifest.discover(self.request)
        self.assertFalse(result["diagnostics"])
        self.assertEqual({item["id"] for item in result["providers"]}, {"local", "sticky", "onenote", "notion"})
        self.assertEqual(result["commands"][0]["id"], "org.note-note.appearance/select-theme")
        actions = {item["localId"]: item["workspaceAction"] for item in result["commands"]
                   if item["packageId"] == "org.note-note.workspace"}
        self.assertEqual(actions, {"new-note": "newNote", "new-notebook": "newNotebook",
                                   "open-settings": "openSettings", "toggle-sidebar": "toggleList", "delete-note": "deleteNote"})
        self.assertFalse((ROOT / "providers").exists())

    def test_workspace_action_reference_validation(self):
        path = self.package("greeting")
        value = json.loads((path / "plugin.json").read_text())
        command = value["contributes"]["commands"][0]
        command["workspaceAction"] = "newNote"
        self.assertEqual(manifest.validate(value, path)["commands"][0]["workspaceAction"], "newNote")
        for action in (None, 42, "", "newNote()", "../newNote", "a" * 65):
            command["workspaceAction"] = action
            with self.subTest(action=action), self.assertRaises(ValueError):
                manifest.validate(value, path)

    def test_plugin_keybindings_are_owned_and_validated_without_loading_code(self):
        path = self.package("greeting")
        value = json.loads((path / "plugin.json").read_text())
        self.assertEqual(manifest.validate(value, path)["keybindings"], [
            {"command": "org.example.greeting/greet", "key": "Ctrl+Alt+G", "context": "notes"}])
        original = value["contributes"]["keybindings"][0]
        for changes in ({"command": "other.plugin/run"}, {"command": "missing"}, {"key": "Ctrl+V"},
                        {"key": "Ctrl+Ctrl+G"}, {"key": "g"}, {"key": "Ctrl+Unknown"}, {"context": "modal"}):
            value["contributes"]["keybindings"] = [dict(original, **changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                manifest.validate(value, path)
        self.assertFalse(manifest.discover(self.request)["keybindings"], "disabled plugin must have no bindings")
        self.request["settings"] = {"plugins": {"org.example.greeting": {"enabled": True}}}
        self.assertEqual(len(manifest.discover(self.request)["keybindings"]), 1)
        self.request["settings"]["plugins"]["org.example.greeting"]["enabled"] = False
        self.assertFalse(manifest.discover(self.request)["keybindings"])
        shutil.rmtree(path)
        self.assertFalse(manifest.discover(self.request)["keybindings"])

    def test_data_only_enabled_code_disabled_and_explicit_enable(self):
        self.package()
        self.package("greeting", "two")
        result = manifest.discover(self.request)
        self.assertEqual(len(result["themes"]), 1)
        self.assertEqual(result["commands"], [])
        self.request["settings"] = {"plugins": {"org.example.greeting": {"enabled": True}}}
        result = manifest.discover(self.request)
        self.assertEqual(len(result["commands"]), 1)
        descriptor = result["commands"][0]
        self.assertIn("Hello!", manifest.resource(descriptor["root"], "greetings.json"))

    def test_duplicates_reject_both_and_removal_has_no_orphans(self):
        first = self.package()
        second = self.package(directory="two")
        result = manifest.discover(self.request)
        self.assertFalse(result["themes"])
        self.assertEqual(len(result["diagnostics"]), 2)
        shutil.rmtree(second)
        self.assertEqual(len(manifest.discover(self.request)["themes"]), 1)
        shutil.rmtree(first)
        self.assertFalse(manifest.discover(self.request)["themes"])

    def test_resources_reject_traversal_symlinks_special_and_oversize(self):
        path = self.package()
        (path / "link").symlink_to(path / "midnight.json")
        (path / "directory").symlink_to(path, target_is_directory=True)
        os.mkfifo(path / "pipe")
        (path / "huge").write_text("a" * (manifest.MAX_RESOURCE + 1))
        for name in ("../escape", "/absolute", "file:theme", "link", "directory/midnight.json", "pipe", "huge"):
            with self.subTest(name=name), self.assertRaises((OSError, ValueError)):
                manifest.resource(path, name)

    def test_manifest_validation_is_atomic(self):
        path = self.package()
        value = json.loads((path / "plugin.json").read_text())
        for modify in (lambda v: v.update(apiVersion=2),
                       lambda v: v.update(id="org.note-note.fake"),
                       lambda v: v["contributes"].update(widgets=[]),
                       lambda v: v["contributes"]["themes"].append(v["contributes"]["themes"][0]),
                       lambda v: v["contributes"]["themes"][0].update(path="../midnight.json")):
            invalid = copy.deepcopy(value)
            modify(invalid)
            with self.assertRaises(ValueError):
                manifest.validate(invalid, path)
        (path / "plugin.json").write_text('{"id":"one","id":"two"}')
        self.assertFalse(manifest.discover(self.request)["themes"])

    def test_oversized_directory_is_rejected_without_partial_catalog(self):
        self.package()
        for i in range(manifest.MAX_PACKAGES):
            (Path(self.request["userRoot"]) / ("entry" + str(i))).mkdir()
        result = manifest.discover(self.request)
        self.assertFalse(result["themes"])
        self.assertIn("entry limit", result["diagnostics"][0]["message"])


class Themes(unittest.TestCase):
    def test_system_covers_every_token(self):
        tokens = theme.specification()
        value = json.loads((ROOT / "plugins/org.note-note.appearance/themes/system.json").read_text())
        theme.validate(value, "system", tokens)
        self.assertEqual(set(value["colors"]), set(tokens))
        self.assertEqual(set(value["colors"].values()), {"system"})
        seen = set()
        for key, token in tokens.items():
            self.assertTrue(set(token["inputs"]).issubset(seen), key)
            seen.add(key)

    def test_partial_alpha_mixed_and_invalid_themes(self):
        tokens = theme.specification()
        value = {"schemaVersion": 1, "id": "custom", "name": "Custom",
                 "colors": {"text.primary": "system", "overlay.scrim": "#80345678"}}
        theme.validate(value, "custom", tokens)
        for key, color in (("surface.background", "transparent"), ("text.primary", "#80112233"),
                           ("unknown", "#112233"), ("accent.primary", "red"), ("accent.primary", 2)):
            invalid = copy.deepcopy(value)
            invalid["colors"][key] = color
            with self.subTest(key=key, color=color), self.assertRaises(ValueError):
                theme.validate(invalid, "custom", tokens)
        with self.assertRaises(ValueError):
            theme.validate(value, "mismatch", tokens)


if __name__ == "__main__":
    unittest.main()
