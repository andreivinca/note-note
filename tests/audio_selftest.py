"""Exercise inline audio with real Qt playback, seeking and document layout.

Uses silent generated WAV audio and isolated application state. --recording
can verify a locally cached phone recording without contacting OneNote.
"""
import argparse
import os
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    harness = Path(os.environ.get("NOTE_NOTE_HARNESS", ROOT / "build/note-note-harness"))
    with tempfile.TemporaryDirectory(prefix="note-note-audio-test-") as directory:
        work = Path(directory)
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        (work / "app").symlink_to(ROOT)
        qml = work / "audio.qml"
        qml.write_text((ROOT / "tests/audio.qml").read_text())
        recording = args.recording
        if recording is None:
            recording = work / "silent.wav"
            with wave.open(str(recording), "wb") as output:
                output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                output.writeframes(bytes(8000 * 2 * 4))
        env = dict(os.environ, XDG_CONFIG_HOME=str(work / "config"), XDG_STATE_HOME=str(work / "state"),
                   XDG_CACHE_HOME=str(work / "cache"), XDG_RUNTIME_DIR=str(runtime),
                   QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic", QT_QUICK_BACKEND="software",
                   QT_FORCE_STDERR_LOGGING="1", NOTE_NOTE_AUDIO_FIXTURE=recording.resolve().as_uri(),
                   NOTE_NOTE_AUDIO_SCREENSHOT=str(args.screenshot.resolve()) if args.screenshot else "")
        try:
            result = subprocess.run([str(harness), "--data-dir", str(ROOT), "--qml", str(qml)],
                                    env=env, capture_output=True, text=True, timeout=40)
        except (OSError, subprocess.SubprocessError) as error:
            print("FAIL:", error)
            if isinstance(error, subprocess.TimeoutExpired):
                print(error.stdout, error.stderr)
            return 1
        output = result.stdout + result.stderr
        failures = ("FAIL!", "TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "Error:")
        if result.returncode or "<<<AUDIO_DONE>>>" not in output or any(marker in output for marker in failures):
            print(output)
            return 1
        print("PASS: audio playback, seek, stop, layout, note switch, editing, undo, copy/paste and save/reload")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
