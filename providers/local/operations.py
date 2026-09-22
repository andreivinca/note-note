"""Confirmed local mutations. A save includes asset staging and atomic commit."""
import json
import os
import stat
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
from fileio import MAX_PAYLOAD, write_atomic
from images import stage
import notefile
from readfile import read_document

MAX_NOTE_BYTES = 2 * 1024 * 1024


def inside(root, path):
    root = os.path.realpath(root)
    path = os.path.abspath(path)
    if os.path.commonpath([root, path]) != root or path == root:
        raise ValueError("path is outside the notebook")
    if os.path.realpath(path) != path:
        raise ValueError("symlinked notebooks and notes are not supported")
    return path


def execute(payload):
    root = os.path.realpath(payload["root"])
    action = payload["action"]
    if action == "section":
        path = inside(root, os.path.join(root, payload["key"]))
        os.makedirs(path, mode=0o700, exist_ok=True)
        return {"ok": True}
    if action == "create":
        directory = os.path.join(root, payload.get("key", ""))
        path = inside(root, os.path.join(directory, "note-" + uuid.uuid4().hex + ".md"))
        text = notefile.serialize("", "")
        version = write_atomic(path, text, exclusive=True)
        return {"ok": True, "file": path, "version": version, "bytes": len(text.encode("utf-8"))}
    path = inside(root, payload["file"])
    if action == "read":
        # The editor's copy: the note split the one way the format is split,
        # or the reader's own error (missing, too large, not text).
        document = read_document(path, MAX_NOTE_BYTES)
        if not document.get("ok"):
            return document
        title, body, _ = notefile.split(document["text"])
        return {"ok": True, "title": title, "body": body, "version": document["version"],
                "bytes": document["bytes"]}
    if action == "remove":
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ValueError("note is not a regular file")
        os.unlink(path)
        return {"ok": True}
    if action == "save":
        # Saving an existing note cannot recreate one deleted elsewhere.
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ValueError("note is not a regular file")
        body = stage(payload["body"], root, path)
        # Front-matter lines the app does not own go back where they were;
        # a file that cannot be read now is not written over on a guess.
        current = read_document(path, MAX_NOTE_BYTES)
        if not current.get("ok"):
            raise ValueError(current["error"])
        text = notefile.serialize(payload["title"], body, notefile.split(current["text"])[2])
        if len(text.encode("utf-8")) > MAX_NOTE_BYTES:
            raise ValueError("note exceeds the 2 MB limit")
        version = write_atomic(path, text)
        return {"ok": True, "body": body, "preview": notefile.preview(body), "version": version,
                "bytes": len(text.encode("utf-8"))}
    if action == "order":
        return {"ok": True, "version": write_atomic(path, payload["text"])}
    raise ValueError("unknown local operation")


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD + 1)
        if len(raw) > MAX_PAYLOAD:
            raise ValueError("note payload is too large")
        result = execute(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"error": str(error)}
    json.dump(result, sys.stdout)
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
