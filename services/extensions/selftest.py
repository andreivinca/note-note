"""Package discovery, ownership, resource boundaries, and theme validation."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import manifest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "themes"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import theme
import packagefiles

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
        self.assertEqual([item["id"] for item in result["providers"]], ["local", "sticky", "onenote", "notion"],
                         "tabs keep the order the application ships, not the order of directory names")
        self.assertEqual(result["commands"][0]["id"], "org.note-note.appearance/select-theme")
        actions = {item["localId"]: item["workspaceAction"] for item in result["commands"]
                   if item["packageId"] == "org.note-note.workspace"}
        self.assertEqual(actions, {"new-note": "newNote", "new-notebook": "newNotebook",
                                   "open-settings": "openSettings", "toggle-sidebar": "toggleList", "delete-note": "deleteNote"})
        self.assertFalse([item for item in result["commands"] if item["workspaceAction"] and "url" in item],
                         "a workspace action is the host's to run; it ships no handler")
        self.assertEqual([(item["packageId"], item["id"]) for item in result["tools"]],
                         [("org.note-note.calendar", tool) for tool in
                          ("insertMonth", "currentMonth", "nextMonth", "customMonth")])
        self.assertTrue(all(item["builtin"] and item["url"].endswith(".qml") for item in result["tools"]))
        self.assertFalse(list((ROOT / "ui/tools").glob("*Month.qml")), "the calendar is its package's to supply")
        self.assertFalse((ROOT / "providers").exists())

    def test_tools_are_named_by_their_action_id(self):
        path = self.package("greeting")
        value = json.loads((path / "plugin.json").read_text())
        accepted = manifest.validate(value, path)["tools"][0]
        self.assertEqual((accepted["id"], accepted["localId"]), ("insertHello", "insertHello"),
                         "toolbar settings, shortcuts and editorTool name a tool unqualified")
        self.assertTrue(accepted["url"].endswith("/InsertHello.qml"))
        tool = value["contributes"]["tools"][0]
        for changes in ({"id": "insert-hello"}, {"id": "InsertHello"}, {"id": "a" * 65}, {"id": None},
                        {"path": None}, {"path": "../InsertHello.qml"}):
            value["contributes"]["tools"] = [dict(tool, **changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                manifest.validate(value, path)
        value["contributes"] = {"tools": [tool]}
        self.assertTrue(manifest.validate(value, path)["executable"], "a tool is code the user must enable")

    def test_workspace_action_reference_validation(self):
        path = self.package("greeting")
        value = json.loads((path / "plugin.json").read_text())
        command = value["contributes"]["commands"][0]
        command["workspaceAction"] = "newNote"
        with self.assertRaises(ValueError, msg="a handler and a workspace action together"):
            manifest.validate(value, path)
        handler = command.pop("handler")
        accepted = manifest.validate(value, path)["commands"][0]
        self.assertEqual(accepted["workspaceAction"], "newNote")
        self.assertNotIn("url", accepted)
        for action in (None, 42, "", "newNote()", "../newNote", "a" * 65):
            command["workspaceAction"] = action
            with self.subTest(action=action), self.assertRaises(ValueError):
                manifest.validate(value, path)
        del command["workspaceAction"]
        with self.assertRaises(ValueError, msg="neither a handler nor a workspace action"):
            manifest.validate(value, path)
        command["handler"] = handler
        self.assertTrue(manifest.validate(value, path)["commands"][0]["url"].endswith("/Greeting.qml"))

    def test_plugin_keybindings_are_owned_without_loading_code(self):
        path = self.package("greeting")
        value = json.loads((path / "plugin.json").read_text())
        self.assertEqual(manifest.validate(value, path)["keybindings"], [
            {"command": "org.example.greeting/greet", "key": "Ctrl+Alt+G", "context": "notes"}])
        original = value["contributes"]["keybindings"][0]
        for changes in ({"command": "other.plugin/run"}, {"command": "missing"}, {"key": ""}, {"key": 7},
                        {"key": "k" * 65}, {"context": ""}, {"context": None}):
            value["contributes"]["keybindings"] = [dict(original, **changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                manifest.validate(value, path)
        # The key grammar is the shortcut resolver's (services/shortcuts): a
        # key it cannot use costs that binding, reported there, not the package.
        value["contributes"]["keybindings"] = [dict(original, key="Ctrl+Unknown", context="modal")]
        self.assertEqual(manifest.validate(value, path)["keybindings"][0]["key"], "Ctrl+Unknown")
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
        self.assertEqual(result["tools"], [])
        self.request["settings"] = {"plugins": {"org.example.greeting": {"enabled": True}}}
        result = manifest.discover(self.request)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual([item["id"] for item in result["tools"]], ["insertHello"])
        descriptor = result["commands"][0]
        self.assertIn("Hello!", packagefiles.read_resource(descriptor["root"], "greetings.json"))

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
        (path / "huge").write_text("a" * (packagefiles.MAX_RESOURCE + 1))
        for name in ("../escape", "/absolute", "file:theme", "link", "directory/midnight.json", "pipe", "huge"):
            with self.subTest(name=name), self.assertRaises((OSError, ValueError)):
                packagefiles.read_resource(path, name)
            with self.subTest(located=name), self.assertRaises((OSError, ValueError)):
                if name != "huge":
                    packagefiles.resource_path(path, name)
                else:
                    raise ValueError("a path is not read, so size is the reader's to refuse")

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
        self.request["builtinRoot"] = str(ROOT / "plugins")
        result = manifest.discover(self.request)
        self.assertFalse([item for item in result["themes"] if not item["builtin"]])
        self.assertIn("entry limit", result["diagnostics"][0]["message"])
        self.assertEqual(len(result["providers"]), 4, "what the application ships is not the user directory's to lose")

    def test_a_limit_costs_the_package_that_crosses_it(self):
        self.request["builtinRoot"] = str(ROOT / "plugins")
        builtin = manifest.discover(self.request)
        shipped = sum(len(builtin[kind]) for kind in manifest.KINDS)
        self.package()
        path = self.package("greeting", "two")
        self.request["settings"] = {"plugins": {"org.example.greeting": {"enabled": True}}}
        limit = manifest.MAX_CONTRIBUTIONS
        self.addCleanup(setattr, manifest, "MAX_CONTRIBUTIONS", limit)
        manifest.MAX_CONTRIBUTIONS = shipped + 1
        result = manifest.discover(self.request)
        self.assertEqual(sum(len(result[kind]) for kind in manifest.KINDS), shipped + 1)
        self.assertEqual([item["id"] for item in result["providers"]], ["local", "sticky", "onenote", "notion"])
        self.assertEqual([item["packageId"] for item in result["themes"] if not item["builtin"]], ["org.example.colors"])
        left_out = [item for item in result["diagnostics"] if item["level"] == "error"]
        self.assertEqual([(item["packageId"], item["path"]) for item in left_out], [("org.example.greeting", str(path))])
        self.assertIn("contribution limit", left_out[0]["message"])

    def test_one_badly_named_loose_theme_hides_no_other(self):
        themes = Path(self.request["themesRoot"])
        for name in ("alpha.json", "My Theme.json", "zulu.json", "notes.txt"):
            (themes / name).write_text("{}")
        result = manifest.discover(self.request)
        self.assertEqual([item["id"] for item in result["themes"]], ["user.themes/alpha", "user.themes/zulu"])
        self.assertEqual([Path(item["path"]).name for item in result["diagnostics"]], ["My Theme.json"])

    def test_legacy_providers_load_as_they_were_installed(self):
        legacy = Path(self.request["legacyRoot"])
        shutil.copytree(ROOT / "examples/hello", legacy / "copied", ignore=shutil.ignore_patterns("plugin.json"))
        (legacy / "linked").symlink_to(ROOT / "examples/hello", target_is_directory=True)
        (legacy / "Not An Id").mkdir()
        (legacy / "empty").mkdir()
        result = manifest.discover(self.request)
        self.assertEqual({item["id"]: item["url"] for item in result["providers"]},
                         {"copied": (legacy / "copied/Provider.qml").as_uri(),
                          "linked": (legacy / "linked/Provider.qml").as_uri()})
        self.assertEqual({item["packageId"] for item in result["diagnostics"]}, {"legacy.Not An Id", "legacy.empty"})

    def test_a_contested_provider_names_each_claimant(self):
        first = self.package("greeting", "one")
        second = self.package("greeting", "two")
        for path, package_id in ((first, "org.example.first"), (second, "org.example.second")):
            (path / "Provider.qml").write_text("import QtQuick\nItem {}\n")
            (path / "plugin.json").write_text(json.dumps({
                "schemaVersion": 1, "id": package_id, "name": "Claimant", "version": "1.0.0", "apiVersion": 1,
                "contributes": {"providers": [{"id": "shared", "path": "Provider.qml"}]}}))
        self.request["settings"] = {"plugins": {"org.example.first": {"enabled": True},
                                                "org.example.second": {"enabled": True}}}
        result = manifest.discover(self.request)
        self.assertFalse(result["providers"])
        self.assertEqual({(item["packageId"], item["path"]) for item in result["diagnostics"]},
                         {("org.example.first", str(first)), ("org.example.second", str(second))})
        self.request["builtinRoot"] = str(ROOT / "plugins")
        (first / "plugin.json").write_text((first / "plugin.json").read_text().replace('"shared"', '"local"'))
        result = manifest.discover(self.request)
        self.assertEqual([item["packageId"] for item in result["providers"] if item["id"] == "local"],
                         ["org.note-note.local"], "a built-in keeps its identity")

    def test_a_malformed_request_is_answered_not_crashed(self):
        scripts = ("services/extensions/manifest.py", "services/themes/theme.py", "services/settings/config_io.py")
        for script in scripts:
            for request in ("42", "[]", '"read"', "null", "{", '{"a":1,"a":2}'):
                with self.subTest(script=script, request=request):
                    result = subprocess.run([sys.executable, str(ROOT / script)], input=request, text=True,
                                            capture_output=True, timeout=20, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(json.loads(result.stdout)["error"])


class Themes(unittest.TestCase):
    # The application names the tokens (design/tokens.js, checked against the
    # System file in tests/extensions.qml); the validator takes what it is sent.
    TOKENS = {"surface.background": {"overlay": False}, "text.primary": {"overlay": False},
              "accent.primary": {"overlay": False}, "overlay.scrim": {"overlay": True}}

    def test_shipped_themes_state_only_what_a_theme_may(self):
        for path in sorted((ROOT / "plugins/org.note-note.appearance/themes").glob("*.json")):
            value = json.loads(path.read_text())
            tokens = {name: {"overlay": True} for name in value["colors"]}
            with self.subTest(theme=path.name):
                self.assertEqual(theme.validate(value, path.stem, tokens), value)

    def test_a_request_names_the_tokens(self):
        for tokens in (None, {}, [], {"text.primary": {}}, {"text.primary": {"overlay": "no"}}):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                theme.respond({"descriptors": [], "tokens": tokens})
        self.assertEqual(theme.respond({"descriptors": [], "tokens": self.TOKENS}), {"themes": [], "diagnostics": []})

    def test_partial_alpha_mixed_and_invalid_themes(self):
        tokens = self.TOKENS
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
