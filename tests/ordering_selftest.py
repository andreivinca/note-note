"""Run provider-defined note and tree drag interactions in an isolated host,
and the local provider's saved orders over a notes tree built here."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def local_notes(notes):
    """Notebooks named like the properties every JavaScript object has, next
    to two that are not: each holds notes, two keep a saved note order, and
    the saved notebook order names one of them. The fixture's provider reads
    this tree through NOTE_NOTE_DIR, never the user's own."""
    notebooks = {"Alpha": ["a.md"], "Work": ["w.md"], "constructor": ["first.md", "second.md"],
                 "toString": ["only.md"], "__proto__": ["first.md", "second.md"]}
    for key, names in notebooks.items():
        (notes / key).mkdir(parents=True)
        for name in names:
            (notes / key / name).write_text("---\ntitle: %s\n---\n" % name[:-3])
    for key in ("constructor", "__proto__"):
        (notes / key / ".order").write_text("second.md\nfirst.md\n")
    (notes / ".notebooks").write_text("toString\nWork\n")


def main():
    with tempfile.TemporaryDirectory(prefix="note-note-ordering-") as temporary:
        work = Path(temporary)
        (work / "app").symlink_to(ROOT, target_is_directory=True)
        fixture = work / "test.qml"
        fixture.write_text((ROOT / "tests/ordering.qml").read_text())
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        local_notes(work / "Notes")
        env = dict(os.environ, HOME=str(work), NOTE_NOTE_DIR=str(work / "Notes"),
                   XDG_CONFIG_HOME=str(work / "config"),
                   XDG_CACHE_HOME=str(work / "cache"), XDG_STATE_HOME=str(work / "state"),
                   XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM="offscreen",
                   QT_QPA_PLATFORMTHEME="generic", QT_QUICK_BACKEND="software",
                   QT_FORCE_STDERR_LOGGING="1", DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(work / "no-bus"))
        env.pop("WAYLAND_DISPLAY", None)
        command = [os.environ.get("NOTE_NOTE_HARNESS", str(ROOT / "build/note-note-harness")),
                   "--data-dir", str(ROOT), "--qml", str(fixture)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        errors = ("TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "FAIL!")
        if result.returncode or "<<<ORDERING_DONE>>>" not in output or any(error in output for error in errors):
            print(output[-12000:])
            return 1
        print("PASS provider-defined groups, subtree drags, pending writes, filtered results"
              " and local orders under any notebook name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
