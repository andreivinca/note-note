"""Run every required suite; runtime failures and missing dependencies fail.

Use --host on a Wayland desktop to include host compilation and startup.
All fixtures use temporary files or scripted network responses.
"""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    "lib/notemerge/selftest.py",
    "plugins/org.note-note.local/selftest.py",
    "plugins/org.note-note.notion/selftest.py",
    "plugins/org.note-note.sticky/selftest.py",
    "plugins/org.note-note.onenote/selftest.py",
    "plugins/org.note-note.onenote/merge_selftest.py",
    "plugins/org.note-note.onenote/search_selftest.py",
    "plugins/org.note-note.onenote/order_selftest.py",
    "services/microsoft/selftest.py",
    "lib/ratelimit_selftest.py",
    "services/requests/selftest.py",
    "services/settings/selftest.py",
    "services/extensions/selftest.py",
    "services/markdown/qthtml/selftest.py",
    "cpp/selftest.py",
    "tests/test_regressions.py",
    "tests/statusbar_selftest.py",
    "tests/transition_selftest.py",
    "tests/extensions_selftest.py",
]


def main():
    failures = []
    env = dict(os.environ, QT_QPA_PLATFORMTHEME="generic")
    for suite in SUITES:
        command = [sys.executable, suite]
        if suite == "tests/extensions_selftest.py":
            command.append("--shell")
        if suite == "tests/transition_selftest.py" and "--host" in sys.argv:
            command.append("--host")
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
            passed = result.returncode == 0
            output = result.stdout + result.stderr
        except (OSError, subprocess.SubprocessError) as error:
            passed, output = False, str(error)
        print(("PASS " if passed else "FAIL ") + suite, flush=True)
        if not passed:
            failures.append(suite)
            print(output, flush=True)
    print("%d/%d suites passed" % (len(SUITES) - len(failures), len(SUITES)))
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
