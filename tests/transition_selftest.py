"""Run the actual QML controllers, editor and local provider in an isolated shell.

The scenarios come in suites, each run by a harness of its own within its
own deadline. Every suite runs by default; --suite runs one.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# "core" is the controllers, providers and hosts (tests/transitions.qml); the
# others are groups of the real-key editor scenarios (tests/EditorKeys.qml).
SUITES = ("core", "tools", "lists", "blocks", "toolbar", "diacritics", "tables", "keys")
# Seconds, the same for every suite, and nested: the QML deadline reports
# what is unfinished, the process limit stops a harness that cannot, and the
# aggregate runners (tests/selftest.py, CTest) allow more than either. The
# longest suite takes about a minute on a loaded machine.
QML_DEADLINE = 150
PROCESS_LIMIT = 180


def arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", choices=SUITES, help="run this suite only")
    parser.add_argument("--standalone", action="store_true", help="run through the native harness, not Quickshell")
    parser.add_argument("--host", action="store_true",
                        help="also compile and instantiate the Omarchy host on Wayland (core suite)")
    parser.add_argument("--notes", action="store_true", help="only the note-session and OneNote cases (core suite)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print the end of the harness output")
    args = parser.parse_args()
    # The editor suites open their key-event window, which --host would put
    # on the desktop; --notes narrows the core suite only.
    if (args.host or args.notes) and args.suite not in (None, "core"):
        parser.error("--host and --notes run the core suite only")
    return args


def main():
    args = arguments()
    if args.suite:
        suites = [args.suite]
    elif args.host or args.notes:
        suites = ["core"]
    else:
        suites = list(SUITES)
    failures = [suite for suite in suites if run(suite, args)]
    return int(bool(failures))


def run(suite, args):
    standalone = args.standalone
    with tempfile.TemporaryDirectory(prefix="note-note-transitions-") as directory:
        work = Path(directory)
        (work / "app").symlink_to(ROOT, target_is_directory=True)
        (work / "design").symlink_to(ROOT / "design", target_is_directory=True)
        tool_ui = work / "ui"
        shutil.copytree(ROOT / "ui/tools", tool_ui / "tools")
        # QML singletons belong to an import URL. Copied tools must use the
        # host's platform instance, rather than a second one through a symlink.
        for path in (tool_ui / "tools").glob("*.qml"):
            source = path.read_text().replace('"../../services/platform"',
                                              '"' + (ROOT / "services/platform").as_uri() + '"')
            path.write_text(source)
        for path in (ROOT / "ui").iterdir():
            if path.name != "tools":
                (tool_ui / path.name).symlink_to(path, target_is_directory=path.is_dir())
        (work / "services").symlink_to(ROOT / "services", target_is_directory=True)
        greeting = (ROOT / "tests/InsertGreeting.qml").read_text().replace('"../ui/editing"', '"../editing"')
        (tool_ui / "tools/InsertGreeting.qml").write_text(greeting)
        invalid_tools = tool_ui / "invalid-tools"
        invalid_tools.mkdir()
        definitions = {
            "Good": 'toolId: "okay"; label: "Okay"',
            "DuplicateOne": 'toolId: "duplicate"; label: "First"',
            "DuplicateTwo": 'toolId: "duplicate"; label: "Second"',
            "ReservedShortcut": 'toolId: "reserved"; label: "Reserved"; shortcutKey: Qt.Key_N; '
                                'shortcutModifiers: Qt.ControlModifier',
            "ReservedUndo": 'toolId: "undo"; label: "Undo"; shortcutKey: Qt.Key_Z; '
                            'shortcutModifiers: Qt.ControlModifier',
            "MenuShortcut": 'toolId: "menuShortcut"; label: "Menu"; isMenu: true; '
                            'shortcutKey: Qt.Key_G',
            "Incomplete": 'label: "Incomplete"',
        }
        for name, properties in definitions.items():
            (invalid_tools / (name + ".qml")).write_text(
                'import QtQuick\nimport "../editing"\nTool {\n  ' + properties + '\n}\n')
        # What packages contribute beside that directory; the test gives
        # each its manifest ID and whether the application ships it.
        plugin_tools = tool_ui / "plugin-tools"
        plugin_tools.mkdir()
        contributions = {
            "External": 'toolId: "external"; label: "External"',
            "Claim": 'toolId: "okay"; label: "Claimed"',
            "Renamed": 'toolId: "renamed"; label: "Renamed"',
            "Packaged": 'toolId: "packaged"; label: "Packaged"',
            "PackagedAgain": 'toolId: "packaged"; label: "Packaged again"',
        }
        for name, properties in contributions.items():
            (plugin_tools / (name + ".qml")).write_text(
                'import QtQuick\nimport "../editing"\nTool {\n  ' + properties + '\n}\n')
        shell = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
        for name in (() if standalone else ("Commons", "Ui", "Services")):
            if (shell / name).is_dir():
                (work / name).symlink_to(shell / name, target_is_directory=True)
        source = (ROOT / "tests/transitions.qml").read_text()
        if standalone:
            source = source.replace("import Quickshell\n", "")
            source = source.replace('"app/hosts/omarchy" as Omarchy', '"app/hosts/standalone" as Native')
            source = source.replace("ShellRoot {", "Tests.TestRoot {")
            source = source.replace("Omarchy.Backend {", "Native.Backend {")
        source = source.replace('"app/', '"file:' + str(ROOT) + '/')
        (work / "shell.qml").write_text(source)
        config = work / "config/notenote"
        config.mkdir(parents=True)
        (config / "config.json").write_text(json.dumps({"providers": {
            name: {"enabled": False} for name in ("local", "notion", "onenote", "sticky")}}))
        (work / "notes").mkdir()
        # A stand-in for msgraph.py's `status`: what it answers is chosen by
        # the account's owner, so one stub covers every way a probe can end.
        (work / "status_stub.py").write_text(
            "import os, sys\n"
            "owner = os.environ.get('NOTE_NOTE_MS_ACCOUNT', '')\n"
            "answers = {'signed-in': '{\"configured\": true, \"signedIn\": true, \"account\": \"a\", \"scope\": \"s\"}',\n"
            "           'signed-out': '{\"configured\": true, \"signedIn\": false}',\n"
            "           'garbage': 'not json at all', 'error': '{\"error\": \"boom\"}'}\n"
            "sys.stdout.write(answers[owner])\n")
        # A stand-in for onenote.py as the provider drives it: a cached listing
        # that says a section-order pass is due, and the pass's answer.
        (work / "onenote_stub.py").write_text(
            "import json, sys\n"
            "b = {'id': 'b', 'name': 'B', 'notebookId': 'n', 'notebook': 'N'}\n"
            "a = {'id': 'a', 'name': 'A', 'notebookId': 'n', 'notebook': 'N'}\n"
            "answers = {'list': {'sections': [b, a], 'pages': [], 'cached': True, 'inventoryReady': True,\n"
            "                    'inventoryComplete': True, 'sectionOrderPending': True},\n"
            "           'section-order': {'sections': [a, b], 'sectionOrderWarnings': ['N: placed by the pass']}}\n"
            "sys.stdout.write(json.dumps(answers[sys.argv[1]]))\n")
        (work / "onenote_race_stub.py").write_text(
            "import json, sys, time\n"
            "if '--cached' in sys.argv:\n"
            "    sys.stdout.write(json.dumps({'sections': [], 'notebooks': [], 'pages': [], 'inventoryReady': False}))\n"
            "    sys.stdout.flush()\n"
            "    time.sleep(0.8)\n"
            "else:\n"
            "    sys.stdout.write(json.dumps({'sections': [{'id': 's', 'name': 'Section', 'notebookId': 'n', 'notebook': 'Notebook'}],\n"
            "                                'notebooks': [{'id': 'n', 'name': 'Notebook'}],\n"
            "                                'pages': [{'id': 'p', 'sectionId': 's', 'title': 'Loaded'}], 'inventoryComplete': True}))\n")
        (work / "notes/Broken").write_text("a file, not a notebook")
        (work / "notes/External.md").write_text("---\ntitle: External original\n---\noriginal")
        (work / "notes/Large.md").write_text("漢" * 700000, encoding="utf-8")
        staging = work / ("cache/notenote/note-note-paste" if standalone else "cache/omarchy/note-note-paste")
        staging.mkdir(parents=True)
        (staging / "image.png").write_bytes(b"synthetic image bytes")
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(work), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(work / "config"), XDG_CACHE_HOME=str(work / "cache"),
                   XDG_STATE_HOME=str(work / "state"), NOTE_NOTE_TEST_DIR=str(work / "notes"),
                   NOTE_NOTE_TEST_STATUS_SCRIPT=str(work / "status_stub.py"),
                   NOTE_NOTE_TEST_ONENOTE_SCRIPT=str(work / "onenote_stub.py"),
                   NOTE_NOTE_TEST_ONENOTE_RACE_SCRIPT=str(work / "onenote_race_stub.py"),
                   NOTE_NOTE_TEST_TOOLS=(tool_ui / "tools").as_uri(),
                   NOTE_NOTE_TEST_INVALID_TOOLS=invalid_tools.as_uri(),
                   NOTE_NOTE_TEST_PLUGIN_TOOLS=plugin_tools.as_uri(),
                   NOTE_NOTE_TEST_SUITE=suite,
                   NOTE_NOTE_TEST_DEADLINE_MS=str(QML_DEADLINE * 1000),
                   NOTE_NOTE_TEST_NOTES_ONLY="1" if args.notes else "",
                   NOTE_NOTE_TEST_STANDALONE="1" if standalone else "",
                   TZ="Europe/Bucharest",
                   QT_QUICK_BACKEND="software",
                   QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic", QT_FORCE_STDERR_LOGGING="1")
        env.pop("WAYLAND_DISPLAY", None)
        if standalone:
            env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(work / "no-session-bus")
            env["HOST_XDG_CONFIG_HOME"] = str(work / "config")
            env["HOST_XDG_STATE_HOME"] = str(work / "state")
        if args.host:
            display = os.environ.get("WAYLAND_DISPLAY")
            if not display:
                print("FAILED: --host requires a Wayland compositor")
                return 1
            env["WAYLAND_DISPLAY"] = str(Path(os.environ["XDG_RUNTIME_DIR"]) / display)
            env["QT_QPA_PLATFORM"] = "wayland"
            env["NOTE_NOTE_TEST_HOST"] = "1"
        try:
            command = ([os.environ.get("NOTE_NOTE_HARNESS", str(ROOT / "build/note-note-harness")), "--data-dir", str(ROOT),
                        "--qml", str(work / "shell.qml")] if standalone
                       else ["qs", "-p", str(work / "shell.qml"), "--no-color"])
            proc = subprocess.run(command,
                                  env=env, capture_output=True, text=True, timeout=PROCESS_LIMIT)
        except subprocess.TimeoutExpired as error:
            print("FAILED (%s suite):" % suite, error)
            for captured in (error.stdout, error.stderr):
                if captured:
                    text = captured.decode(errors="replace") if isinstance(captured, bytes) else captured
                    print(text[-8000:])
            return 1
        except (OSError, subprocess.SubprocessError) as error:
            print("FAILED (%s suite):" % suite, error)
            return 1
        output = proc.stdout + proc.stderr
        if proc.returncode or "<<<RESULT>>>" not in output:
            print("FAILED (%s suite): QML runtime\n" % suite + output[-8000:])
            return 1
        try:
            results = json.loads(output.split("<<<RESULT>>>")[1].split("<<<END>>>")[0])
        except (ValueError, IndexError) as error:
            print("FAILED (%s suite): invalid QML result" % suite, error)
            return 1
        failed = [result for result in results if not result["ok"]]
        for result in failed:
            print("FAIL:", result["name"], result["detail"])
        noise = [line for line in output.splitlines()
                 if any(marker in line for marker in ("TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "Error:", "ERROR"))
                 and "<<<RESULT>>>" not in line]
        if noise:
            failed.append({"name": "unexpected QML errors"})
            print("FAILED (%s suite): unexpected QML errors\n" % suite + "\n".join(noise))
        if failed or args.verbose:
            print(output[-8000:])
        print("%d/%d transition checks in the %s suite" % (len(results) - len(failed), len(results), suite))
        return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())
