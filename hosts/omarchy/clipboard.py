"""The Omarchy host's clipboard, read through `wl-paste` — the transport
behind Backend.readClipboard, answering the same shapes the native host's
QClipboard reader does (hosts/standalone/runtime.cpp):

    python3 clipboard.py types   -> {"types": ["image/png", …], "image": "image/png" | ""}
    python3 clipboard.py text    -> {"text": "…"}      ("" when no text is on offer)
    python3 clipboard.py html    -> {"html": "…"}      ("" when no HTML is on offer)
    python3 clipboard.py image   -> {"mime": …, "data": <base64>}

Staging a picture where the editor can show it is the clipboard service's
policy, shared by both hosts (services/clipboard/clipboard.py); this only
carries the bytes, bounded.
"""
import base64
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "services", "clipboard"))
from clipboard import MIME_SUFFIX, MAX_CLIPBOARD, MAX_TEXT  # noqa: E402


def out(obj):
    sys.stdout.write(json.dumps(obj))


def types():
    try:
        listed = subprocess.run(["wl-paste", "--list-types"], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    return [t.strip() for t in listed.stdout.decode("utf-8", "replace").split("\n") if t.strip()]


def image_type(available):
    for mime in MIME_SUFFIX:
        if mime in available:
            return mime
    return ""


def clipboard_image():
    mime = image_type(types())
    if not mime:
        return {"error": "the clipboard holds no image"}
    try:
        proc = subprocess.run(["wl-paste", "--type", mime], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as error:
        return {"error": "could not read the clipboard: %s" % error}
    if len(proc.stdout) > MAX_CLIPBOARD:
        return {"error": "the clipboard image is too large"}
    return {"mime": mime, "data": base64.b64encode(proc.stdout).decode("ascii")}


def clipboard_text():
    """The clipboard's text flavour, for the plain paste (Ctrl+Shift+V).
    "text" is wl-paste's own shorthand for any text type on offer; a
    clipboard holding none (an image, nothing) answers with empty text —
    the ordinary case, not a failure."""
    available = types()
    if not any(t.startswith("text/") or t in ("TEXT", "STRING", "UTF8_STRING") for t in available):
        return {"text": ""}
    return flavour("text", "text")


def clipboard_html():
    """The clipboard's rich flavour, for the editor's own paste
    (NoteEditor.pasteRich). No HTML on offer answers empty — the ordinary
    case, not a failure — and the paste falls back to Qt's own."""
    if "text/html" not in types():
        return {"html": ""}
    return flavour("html", "text/html")


def flavour(key, mime):
    try:
        proc = subprocess.run(["wl-paste", "--no-newline", "--type", mime], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        return {"error": "could not read the clipboard: %s" % error}
    if len(proc.stdout) > MAX_TEXT:
        return {"error": "the clipboard text is too large"}
    return {key: proc.stdout.decode("utf-8", "replace")}


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "types":
        available = types()
        out({"types": available, "image": image_type(available)})
    elif command == "text":
        out(clipboard_text())
    elif command == "html":
        out(clipboard_html())
    elif command == "image":
        out(clipboard_image())
    else:
        out({"error": "usage: clipboard.py types | text | html | image"})
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
