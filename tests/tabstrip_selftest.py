"""Exercise tab curve clearance, pointer regions and overflow at several scales."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="note-note-tabstrip-") as temporary:
        work = Path(temporary)
        (work / "app").symlink_to(ROOT, target_is_directory=True)
        fixture = work / "test.qml"
        fixture.write_text((ROOT / "tests/tabstrip.qml").read_text())
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(work), XDG_CONFIG_HOME=str(work / "config"),
                   XDG_CACHE_HOME=str(work / "cache"), XDG_STATE_HOME=str(work / "state"),
                   XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM="offscreen",
                   QT_QPA_PLATFORMTHEME="generic", QT_QUICK_BACKEND="software",
                   QT_FORCE_STDERR_LOGGING="1",
                   DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(work / "no-bus"))
        env.pop("WAYLAND_DISPLAY", None)
        if args.shell:
            command = ["qs", "-p", str(fixture), "--no-color"]
        else:
            command = [os.environ.get("NOTE_NOTE_HARNESS", str(ROOT / "build/note-note-harness")),
                       "--data-dir", str(ROOT), "--qml", str(fixture)]
        for scale in ("1", "1.5", "2"):
            try:
                result = subprocess.run(command, env=dict(env, QT_SCALE_FACTOR=scale),
                                        capture_output=True, text=True, timeout=25)
            except (OSError, subprocess.SubprocessError) as error:
                print("FAIL tabstrip scale", scale, error)
                return 1
            output = result.stdout + result.stderr
            errors = ("TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "FAIL!")
            if result.returncode or "<<<TABSTRIP_DONE>>>" not in output or any(error in output for error in errors):
                print("FAIL tabstrip scale", scale, "\n" + output[-12000:])
                return 1
            print("PASS tab curves, stable faces, shaped clicks and overflow; scale", scale)
    return 0


if __name__ == "__main__":
    sys.exit(main())
