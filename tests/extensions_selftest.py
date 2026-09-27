"""Exercise external packages, live theme previews and persistence in both hosts."""
import json
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--resources", type=Path, default=ROOT)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    shell = args.shell
    resources = args.resources.resolve()
    with tempfile.TemporaryDirectory(prefix="note-note-extensions-") as temporary:
        work = Path(temporary)
        config = work / "config/notenote"
        config.mkdir(parents=True)
        for name in ("greeting", "colors"):
            shutil.copytree(ROOT / "examples/plugins" / name, config / "plugins" / name)
        notes = work / "notes"
        notes.mkdir()
        note = "---\ntitle: Theme fixture\n---\nText ==marker== and `code`.\n\n> Quote and [link](https://example.org).\n\n| A | B |\n| --- | --- |\n| cell | nested |\n"
        (notes / "Theme.md").write_text(note)
        settings = {"providers": {name: {"enabled": name == "local"} for name in ("local", "sticky", "onenote", "notion")},
                    "plugins": {"org.example.greeting": {"enabled": True}}, "unknown": {"keep": [1, 2]}}
        settings["providers"]["local"]["notesDir"] = str(notes)
        (config / "config.json").write_text(json.dumps(settings))
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        shortcut_checks = (ROOT / "tests/ShortcutChecks.js").read_text()
        shortcut_checks = shortcut_checks.replace('.import "../', '.import "' + resources.as_uri() + '/')
        (work / "ShortcutChecks.js").write_text(shortcut_checks)
        source = (ROOT / "tests/extensions.qml").read_text()
        source = source.replace('"app/tests/ShortcutChecks.js"', '"ShortcutChecks.js"')
        source = source.replace('import "app"', 'import "' + resources.as_uri() + '"')
        source = source.replace('import "app/', 'import "' + resources.as_uri() + '/')
        if shell:
            source = source.replace('/hosts/standalone" as Native', '/hosts/omarchy" as Native')
        fixture = work / "test.qml"
        fixture.write_text(source)
        env = dict(os.environ, HOME=str(work), XDG_CONFIG_HOME=str(work / "config"),
                   XDG_CACHE_HOME=str(work / "cache"), XDG_STATE_HOME=str(work / "state"),
                   XDG_RUNTIME_DIR=str(runtime), HOST_XDG_CONFIG_HOME=str(work / "config"),
                   HOST_XDG_STATE_HOME=str(work / "state"), QT_QPA_PLATFORM="offscreen",
                   QT_QPA_PLATFORMTHEME="generic", QT_QUICK_BACKEND="software",
                   QT_FORCE_STDERR_LOGGING="1",
                   DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(work / "no-bus"))
        env.pop("WAYLAND_DISPLAY", None)
        if args.screenshot:
            env["NOTE_NOTE_TEST_SCREENSHOT"] = str(args.screenshot.resolve())
        if shell:
            shell_root = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
            for name in ("Commons", "Ui", "Services"):
                (work / name).symlink_to(shell_root / name, target_is_directory=True)
            command = ["qs", "-p", str(fixture), "--no-color"]
        else:
            command = [os.environ.get("NOTE_NOTE_HARNESS", str(ROOT / "build/note-note-harness")),
                       "--data-dir", str(resources), "--qml", str(fixture)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=100)
        output = result.stdout + result.stderr
        errors = [line for line in output.splitlines() if any(word in line for word in
                  ("TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "FAIL!"))]
        if result.returncode or "<<<EXTENSIONS_DONE>>>" not in output or errors:
            print(output[-14000:])
            return 1
        saved = json.loads((config / "config.json").read_text())
        assert saved["appearance"]["theme"] == "org.example.colors/midnight"
        assert saved["unknown"] == settings["unknown"]
        assert saved["foreign"] is True
        assert (notes / "Theme.md").read_text().endswith("x\n")
        assert len(list(notes.glob("*.md"))) == 1, "the new note must be removed only after confirmation"
        assert len(list((notes / "Commandbook").glob("*.md"))) == 1
        restart = (ROOT / "tests/extensions_restart.qml").read_text()
        restart = restart.replace('import "app"', 'import "' + resources.as_uri() + '"')
        restart = restart.replace('import "app/', 'import "' + resources.as_uri() + '/')
        if shell:
            restart = restart.replace('/hosts/standalone" as Native', '/hosts/omarchy" as Native')
        fixture.write_text(restart)
        for theme_id, color in (("org.example.colors/midnight", "#181A20"), ("user.themes/missing", "")):
            saved["appearance"]["theme"] = theme_id
            original = json.dumps(saved)
            (config / "config.json").write_text(original)
            launch = subprocess.run(command, env=dict(env, NOTE_NOTE_EXPECT_THEME=theme_id, NOTE_NOTE_EXPECT_COLOR=color),
                                    capture_output=True, text=True, timeout=20)
            if launch.returncode or "<<<RESTART_DONE>>>" not in launch.stdout + launch.stderr:
                print(launch.stdout + launch.stderr)
                return 1
            assert (config / "config.json").read_text() == original
        print("PASS shortcut resolution/rebinding, workspace and plugin commands, themes, settings, and note integrity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
