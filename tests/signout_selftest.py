"""Run the sign-out checks (tests/signout.qml) in the native harness, against
stand-ins for msgraph.py and notion.py: only a confirmed sign-out signs out."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# msgraph.py as the account drives it; what `logout` answers is chosen by the
# account's owner, so one stand-in covers every way a sign-out can end.
MSGRAPH = """\
import json, os, sys
owner = os.environ.get("NOTE_NOTE_MS_ACCOUNT", "")
if sys.argv[1] == "status":
    print(json.dumps({"configured": True, "signedIn": True, "account": owner, "scope": "", "cacheSession": owner}))
elif sys.argv[1] == "logout" and owner == "removable":
    print(json.dumps({"ok": True}))
elif sys.argv[1] == "logout" and owner == "crashing":
    sys.exit(2)
elif sys.argv[1] == "logout" and owner == "silent":
    print("{}")
else:
    print(json.dumps({"error": "the sign-in could not be removed: Permission denied"}))
    sys.exit(1)
"""

# notion.py as the provider drives it: set up until a sign-out says otherwise.
NOTION = """\
import json, os, sys
signed_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notion-signed-out")
if sys.argv[1] == "status":
    print(json.dumps({"configured": not os.path.exists(signed_out), "workspace": "Test"}))
elif sys.argv[1] == "list":
    print(json.dumps({"pages": [], "cached": True}))
elif sys.argv[1] == "logout" and %(removed)r:
    open(signed_out, "w").close()
    print(json.dumps({"ok": True, "warning": "the cached page list could not be removed: Permission denied"}))
else:
    print(json.dumps({"error": "the integration secret could not be removed: Permission denied"}))
    sys.exit(1)
"""


def main():
    with tempfile.TemporaryDirectory(prefix="note-note-signout-") as temporary:
        work = Path(temporary)
        (work / "app").symlink_to(ROOT, target_is_directory=True)
        stubs = work / "stubs"
        stubs.mkdir()
        (stubs / "msgraph_stub.py").write_text(MSGRAPH)
        (stubs / "notion_undeletable.py").write_text(NOTION % {"removed": False})
        (stubs / "notion_cache_stays.py").write_text(NOTION % {"removed": True})
        fixture = work / "test.qml"
        fixture.write_text((ROOT / "tests/signout.qml").read_text())
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(work), XDG_CONFIG_HOME=str(work / "config"),
                   XDG_CACHE_HOME=str(work / "cache"), XDG_STATE_HOME=str(work / "state"),
                   XDG_RUNTIME_DIR=str(runtime), NOTE_NOTE_TEST_SIGNOUT_DIR=str(stubs),
                   QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic",
                   QT_QUICK_BACKEND="software", QT_FORCE_STDERR_LOGGING="1",
                   DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(work / "no-bus"))
        env.pop("WAYLAND_DISPLAY", None)
        command = [os.environ.get("NOTE_NOTE_HARNESS", str(ROOT / "build/note-note-harness")),
                   "--data-dir", str(ROOT), "--qml", str(fixture)]
        try:
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as error:
            print("FAIL sign-out:", error)
            return 1
        output = result.stdout + result.stderr
        errors = ("TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "FAIL!")
        if result.returncode or "<<<SIGNOUT_DONE>>>" not in output or any(error in output for error in errors):
            print(output[-12000:])
            return 1
        print("PASS a sign-out that was not confirmed keeps the sign-in and says why")
    return 0


if __name__ == "__main__":
    sys.exit(main())
