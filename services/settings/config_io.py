"""Revision-checked application config transactions; notes use fileio directly.

This helper owns the file: bounded strict JSON, its revision, the lock and the
atomic write. What a field may hold is the application's own rule
(services/settings/settings.js) and is stated there alone.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from fileio import write_atomic
from readfile import read_document
import jsondata

MAX_BYTES = 1024 * 1024
LOCK_TIMEOUT = 2.0


def parse(text):
    """Strict JSON with an object at its root."""
    if not isinstance(text, str):
        raise ValueError("settings text must be a string")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("configuration exceeds the byte limit")
    value = jsondata.parse(text)
    if not isinstance(value, dict):
        raise ValueError("settings must be a JSON object")
    return value


def revision_of(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot(path):
    result = read_document(path, MAX_BYTES)
    if result.get("kind") == "missing":
        return {"ok": True, "revision": "missing", "config": {}, "unwritten": True}
    if result.get("error"):
        return result
    text = result["text"]
    try:
        config = parse(text) if text.strip() else {}
        return {"ok": True, "revision": revision_of(text), "config": config, "unwritten": not text.strip()}
    except (ValueError, RecursionError) as error:
        return {"error": str(error), "kind": "invalid", "revision": revision_of(text)}


@contextlib.contextmanager
def config_lock(path, timeout=LOCK_TIMEOUT):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd = os.open(path + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("configuration lock is not a regular file")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("another process is saving settings; try again")
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)


def with_theme(config, theme):
    if not isinstance(theme, str) or not theme:
        raise ValueError("invalid theme ID")
    if not isinstance(config.get("appearance"), dict):
        config["appearance"] = {}
    config["appearance"]["theme"] = theme
    return config


def refusal(operation, request, current):
    """Why this write may not start from the file as it is, or nothing."""
    if operation == "create":
        # Another writer made the file first: the caller adopts theirs.
        return None if current.get("unwritten") else current
    if current["revision"] != request.get("revision"):
        return {"error": "Settings changed in another window or program. Restart to load them before saving.",
                "kind": "stale", "revision": current["revision"]}
    # Explicit Settings Save may repair malformed JSON; theme patches cannot.
    if operation == "theme" and current.get("error"):
        return current
    return None


def write(path, value, revision):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("configuration exceeds the byte limit")
    # Detect ordinary uncooperative edits as late as possible; advisory
    # locks cannot make an external editor participate in this transaction.
    if snapshot(path).get("revision") != revision:
        return {"error": "Settings changed while saving; restart before retrying.", "kind": "stale"}
    write_atomic(path, text)
    return {"ok": True, "config": value, "revision": revision_of(text), "unwritten": False}


def transact(request):
    path = request["path"]
    if not isinstance(path, str):
        raise ValueError("configuration path must be a string")
    operation = request["operation"]
    if operation == "validate":
        return {"ok": True, "config": parse(request["text"])}
    if operation == "read":
        return snapshot(path)
    if operation not in ("create", "replace", "theme"):
        raise ValueError("unknown configuration operation")
    with config_lock(path):
        current = snapshot(path)
        if not current.get("revision"):
            return current
        refused = refusal(operation, request, current)
        if refused:
            return refused
        if operation == "theme":
            value = with_theme(current["config"], request["theme"])
        else:
            value = parse(request["text"])
        return write(path, value, current["revision"])


if __name__ == "__main__":
    jsondata.answer(transact, MAX_BYTES * 2)
