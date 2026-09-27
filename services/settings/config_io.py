"""Revision-checked application config transactions; notes use fileio directly."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from fileio import write_atomic
from readfile import read_document
import jsondata
import keybindings

MAX_BYTES = 1024 * 1024
LOCK_TIMEOUT = 2.0
THEME_ID = re.compile(r"[a-z][a-z0-9.-]*/[a-z][a-z0-9-]*\Z")


def parse(text):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("configuration exceeds the byte limit")
    value = jsondata.parse(text)
    if not isinstance(value, dict):
        raise ValueError("settings must be a JSON object")
    for key in ("providers", "editor", "appearance", "plugins"):
        if key in value and not isinstance(value[key], dict):
            raise ValueError(key + " must be an object")
    for key in ("providers", "plugins"):
        for entry in value.get(key, {}).values():
            if not isinstance(entry, dict):
                raise ValueError(key + " entries must be objects")
            if "enabled" in entry and not isinstance(entry["enabled"], bool):
                raise ValueError(key + ".enabled must be a boolean")
    appearance = value.get("appearance", {})
    theme = appearance.get("theme")
    if "theme" in appearance and (not isinstance(theme, str) or not THEME_ID.fullmatch(theme)):
        raise ValueError("appearance.theme must be a qualified theme ID")
    keybindings.validate_overrides(value.get("keybindings", []))
    return value


def snapshot(path):
    result = read_document(path, MAX_BYTES)
    if result.get("kind") == "missing":
        return {"ok": True, "revision": "missing", "config": {}, "unwritten": True}
    if result.get("error"):
        return result
    text = result["text"]
    revision = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        config = parse(text) if text.strip() else {}
        return {"ok": True, "revision": revision, "config": config, "unwritten": not text.strip()}
    except (ValueError, RecursionError) as error:
        return {"error": str(error), "kind": "invalid", "revision": revision}


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


def transact(request):
    path = request["path"]
    operation = request["operation"]
    if operation == "validate":
        return {"ok": True, "config": parse(request["text"])}
    if operation == "read":
        return snapshot(path)
    if operation not in ("replace", "theme"):
        raise ValueError("unknown configuration operation")
    with config_lock(path):
        current = snapshot(path)
        if not current.get("revision"):
            return current
        if current["revision"] != request.get("revision"):
            return {"error": "Settings changed in another window or program. Restart to load them before saving.",
                    "kind": "stale", "revision": current["revision"]}
        if operation == "replace":
            # Explicit Settings Save may repair malformed JSON; theme patches cannot.
            value = parse(request["text"])
        else:
            if current.get("error"):
                return current
            theme = request["theme"]
            if not isinstance(theme, str) or not THEME_ID.fullmatch(theme):
                raise ValueError("invalid theme ID")
            value = current["config"]
            value.setdefault("appearance", {})["theme"] = theme
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("configuration exceeds the byte limit")
        # Detect ordinary uncooperative edits as late as possible; advisory
        # locks cannot make an external editor participate in this transaction.
        if snapshot(path).get("revision") != current["revision"]:
            return {"error": "Settings changed while saving; restart before retrying.", "kind": "stale"}
        write_atomic(path, text)
        return {"ok": True, "config": value,
                "revision": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES * 2 + 1)
        if len(raw) > MAX_BYTES * 2:
            raise ValueError("configuration request exceeds the byte limit")
        result = transact(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        result = {"error": str(error)}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
