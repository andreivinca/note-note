"""Exercise inline audio with real Qt playback, seeking and document layout.

Uses silent generated WAV audio and isolated application state. --recording
can verify a locally cached phone recording without contacting OneNote. A
second run removes Qt Multimedia from the player and checks that notes with
recordings still open and edit.
"""
import argparse
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES = ("FAIL!", "TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "Error:")


def application(app):
    app.symlink_to(ROOT)


def application_without_multimedia(app):
    """The application with a playback component that cannot load, as on a
    system without the Qt Multimedia QML module. Qt finds an installed module
    past any stand-in on the import path, so the component itself fails; that
    nothing else imports the module is test_regressions.py's check."""
    app.mkdir()
    for entry in ROOT.iterdir():
        if entry.name != "ui":
            (app / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    shutil.copytree(ROOT / "ui", app / "ui")
    (app / "ui/AudioPlayback.qml").write_text("import QtQuick\nimport NoteNoteMissingMultimedia\nMediaPlayer {}\n")


def run(harness, work, build, env, label):
    work.mkdir()
    build(work / "app")
    runtime = work / "runtime"
    runtime.mkdir(mode=0o700)
    qml = work / "audio.qml"
    qml.write_text((ROOT / "tests/audio.qml").read_text())
    env = dict(env, XDG_CONFIG_HOME=str(work / "config"), XDG_STATE_HOME=str(work / "state"),
               XDG_CACHE_HOME=str(work / "cache"), XDG_RUNTIME_DIR=str(runtime))
    try:
        result = subprocess.run([str(harness), "--data-dir", str(ROOT), "--qml", str(qml)],
                                env=env, capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.SubprocessError) as error:
        print("FAIL:", label, error)
        if isinstance(error, subprocess.TimeoutExpired):
            print(error.stdout, error.stderr)
        return False
    output = result.stdout + result.stderr
    if result.returncode or "<<<AUDIO_DONE>>>" not in output or any(marker in output for marker in FAILURES):
        print("FAIL:", label)
        print(output)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    harness = Path(os.environ.get("NOTE_NOTE_HARNESS", ROOT / "build/note-note-harness"))
    with tempfile.TemporaryDirectory(prefix="note-note-audio-test-") as directory:
        work = Path(directory)
        recording = args.recording
        if recording is None:
            recording = work / "silent.wav"
            with wave.open(str(recording), "wb") as output:
                output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                output.writeframes(bytes(8000 * 2 * 4))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic",
                   QT_QUICK_BACKEND="software", QT_FORCE_STDERR_LOGGING="1",
                   NOTE_NOTE_AUDIO_FIXTURE=recording.resolve().as_uri(),
                   NOTE_NOTE_AUDIO_SCREENSHOT=str(args.screenshot.resolve()) if args.screenshot else "")
        if not run(harness, work / "playback", application, env, "playback"):
            return 1
        print("PASS: audio playback, seek, stop, layout, note switch, editing, undo, copy, move and save/reload")
        if not run(harness, work / "without-multimedia", application_without_multimedia,
                   dict(env, NOTE_NOTE_AUDIO_WITHOUT_MULTIMEDIA="1"), "without Qt Multimedia"):
            return 1
        print("PASS: without Qt Multimedia, notes with recordings open, explain playback and edit")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
