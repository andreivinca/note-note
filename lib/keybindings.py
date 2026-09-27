"""Validate declarative shortcuts at the settings and package boundaries."""
import re

CONTEXTS = {"application", "notes", "workspace", "editor", "search", "page"}
COMMAND = re.compile(r"[a-z][a-z0-9.-]*/[a-zA-Z][a-zA-Z0-9-]*\Z")
MODIFIERS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift", "meta": "meta", "super": "meta"}
KEYS = set("esc escape tab enter return numenter space backspace delete insert home end pageup pagedown up down left right plus minus comma period slash backslash bracketleft bracketright equal backtab".split())
RESERVED = {"ctrl+a", "ctrl+c", "ctrl+x", "ctrl+v", "ctrl+shift+v", "ctrl+z", "ctrl+shift+z", "ctrl+y",
            "ctrl+insert", "shift+insert", "shift+delete"}


def validate_key(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("shortcut must be a string of at most 64 characters")
    parts = [part.strip() for part in value.lower().split("+")]
    key = parts.pop()
    modifiers = set()
    for part in parts:
        flag = MODIFIERS.get(part)
        if not flag or flag in modifiers:
            raise ValueError("invalid or repeated shortcut modifier")
        modifiers.add(flag)
    function_key = bool(re.fullmatch(r"f([1-9]|[12][0-9]|3[0-5])", key))
    if key not in KEYS and not function_key and not re.fullmatch(r"[a-z0-9]", key):
        raise ValueError("unknown shortcut key")
    if key == "backtab":
        key = "tab"
        modifiers.add("shift")
    if not modifiers.intersection({"ctrl", "alt", "meta"}) and not function_key:
        raise ValueError("shortcut needs Ctrl, Alt, Meta or a function key")
    normalized = "+".join([flag for flag in ("ctrl", "alt", "shift", "meta") if flag in modifiers] + [key])
    if normalized in RESERVED:
        raise ValueError("native editing shortcuts are reserved")
    return value


def validate_overrides(value):
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError("keybindings must be an array of at most 512 overrides")
    seen = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("keybinding override must be an object")
        command, keys = entry.get("command"), entry.get("keys")
        if not isinstance(command, str) or len(command) > 256 or not COMMAND.fullmatch(command):
            raise ValueError("keybinding command must be a qualified ID")
        if command in seen:
            raise ValueError("duplicate keybinding override: " + command)
        seen.add(command)
        if not isinstance(keys, list) or len(keys) > 8:
            raise ValueError("keybinding keys must be an array of at most 8 keys")
        for key in keys:
            validate_key(key)
