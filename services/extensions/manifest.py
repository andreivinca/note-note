"""Discover declarative packages without importing their executable code."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import jsondata
import keybindings
from readfile import read_bytes
import time

MAX_MANIFEST = 64 * 1024
MAX_RESOURCE = 256 * 1024
MAX_INPUT = 8 * 1024 * 1024
MAX_PACKAGES = 128
MAX_CONTRIBUTIONS = 4096
PACKAGE_ID = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+\Z")
LOCAL_ID = re.compile(r"[a-z][a-z0-9-]*\Z")
ACTION_ID = re.compile(r"[a-z][a-zA-Z0-9]{0,63}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
CONTEXTS = {"hasDocument", "editorWritable", "settingsClean"}
PROTECTED = "org.note-note.appearance"


def label(value, name, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\0" in value:
        raise ValueError("invalid " + name)
    return value


def identifier(value, expression, name):
    label(value, name, 128)
    if not expression.fullmatch(value):
        raise ValueError("invalid " + name)
    return value


def resource_parts(relative):
    label(relative, "resource path", 512)
    parts = PurePosixPath(relative).parts
    if relative.startswith("/") or "\\" in relative or ":" in relative or ".." in parts or not parts:
        raise ValueError("resources must be relative paths inside their package")
    return parts


def open_resource(root, relative):
    """Walk using directory descriptors; a replaced symlink never redirects a read."""
    parts = resource_parts(relative)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     dir_fd=directory)
            os.close(directory)
            directory = next_directory
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("resource is not a regular file")
        return fd
    finally:
        os.close(directory)


def resource(root, relative, cap=MAX_RESOURCE, read=True):
    with os.fdopen(open_resource(root, relative), "rb") as stream:
        if not read:
            return str(Path(root) / relative)
        before = os.fstat(stream.fileno())
        data = read_bytes(stream, cap + 1, time.monotonic() + 5)
        after = os.fstat(stream.fileno())
        if len(data) > cap:
            raise ValueError("resource exceeds the byte limit")
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise ValueError("resource changed while reading")
        return data.decode("utf-8")


def validate(value, root, builtin=False):
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise ValueError("unsupported plugin schemaVersion")
    if type(value.get("apiVersion")) is not int or value["apiVersion"] != 1:
        raise ValueError("unsupported plugin apiVersion")
    package_id = identifier(value.get("id"), PACKAGE_ID, "package ID")
    if not builtin and (package_id.startswith("org.note-note.") or package_id == "user.themes"):
        raise ValueError("reserved package namespace")
    name = label(value.get("name"), "package name")
    identifier(value.get("version"), VERSION, "package version")
    contributions = value.get("contributes")
    if not isinstance(contributions, dict) or not contributions or set(contributions) - {"commands", "themes", "providers", "keybindings"}:
        raise ValueError("unsupported or missing contributions")
    package = {"id": package_id, "name": name, "root": str(root), "builtin": builtin,
               "commands": [], "themes": [], "providers": [], "keybindings": []}
    for kind, items in contributions.items():
        if not isinstance(items, list) or len(items) > 128:
            raise ValueError("invalid or oversized " + kind + " list")
        if kind == "keybindings":
            continue
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("contribution must be an object")
            local_id = identifier(item.get("id"), LOCAL_ID, "contribution ID")
            if local_id in seen:
                raise ValueError("duplicate " + kind + " ID: " + local_id)
            seen.add(local_id)
            relative = item.get("handler") if kind == "commands" else item.get("path")
            absolute = resource(root, relative, read=False)
            descriptor = {"id": package_id + "/" + local_id, "localId": local_id,
                          "packageId": package_id, "packageName": name, "root": str(root),
                          "path": relative, "url": Path(absolute).as_uri(), "builtin": builtin}
            if kind == "commands":
                descriptor["title"] = label(item.get("title"), "command title")
                descriptor["category"] = label(item["category"], "command category") if "category" in item else ""
                descriptor["workspaceAction"] = identifier(item["workspaceAction"], ACTION_ID, "workspace action") if "workspaceAction" in item else ""
                keywords = item.get("keywords", [])
                if not isinstance(keywords, list) or len(keywords) > 32:
                    raise ValueError("invalid command keywords")
                descriptor["keywords"] = [label(word, "keyword", 64) for word in keywords]
                requirements = item.get("requires", [])
                if not isinstance(requirements, list) or any(not isinstance(key, str) or key not in CONTEXTS for key in requirements):
                    raise ValueError("unknown command context requirement")
                descriptor["requires"] = requirements
            elif kind == "themes":
                descriptor["name"] = label(item.get("name"), "theme name")
            else:
                descriptor["id"] = local_id
            package[kind].append(descriptor)
    command_ids = {command["localId"] for command in package["commands"]}
    for binding in contributions.get("keybindings", []):
        if not isinstance(binding, dict):
            raise ValueError("keybinding must be an object")
        command = identifier(binding.get("command"), LOCAL_ID, "keybinding command")
        if command not in command_ids:
            raise ValueError("keybindings must refer to a command in this package")
        context = binding.get("context", "notes")
        if not isinstance(context, str) or context not in keybindings.CONTEXTS:
            raise ValueError("unknown keybinding context")
        package["keybindings"].append({"command": package_id + "/" + command,
                                       "key": keybindings.validate_key(binding.get("key")), "context": context})
    package["executable"] = bool(package["commands"] or package["providers"])
    return package


def entries(directory, limit=MAX_PACKAGES):
    try:
        with os.scandir(directory) as scan:
            result = []
            for entry in scan:
                result.append(entry.name)
                if len(result) > limit:
                    raise ValueError("directory exceeds the entry limit")
        return sorted(result)
    except FileNotFoundError:
        return []


def discover(request):
    result = {"packages": [], "commands": [], "themes": [], "providers": [], "keybindings": [], "diagnostics": []}
    candidates = []
    input_bytes = 0

    def diagnostic(path, message, package_id=""):
        result["diagnostics"].append({"packageId": package_id, "stage": "discovery", "path": str(path), "message": message})

    for key, builtin in (("builtinRoot", True), ("userRoot", False)):
        directory = Path(request[key])
        try:
            names = entries(directory)
        except (OSError, ValueError) as error:
            diagnostic(directory, str(error))
            continue
        for name in names:
            root = directory / name
            try:
                raw = resource(root, "plugin.json", MAX_MANIFEST)
                input_bytes += len(raw.encode("utf-8"))
                if input_bytes > MAX_INPUT:
                    raise ValueError("catalog exceeds the input byte limit")
                candidates.append(validate(jsondata.parse(raw), root, builtin))
            except (OSError, ValueError) as error:
                diagnostic(root, str(error))
        if input_bytes > MAX_INPUT:
            return {"error": "catalog exceeds the input byte limit"}
    by_id = {}
    reserved_providers = set()
    for package in candidates:
        by_id.setdefault(package["id"], []).append(package)
        if package["builtin"]:
            reserved_providers.update(item["id"] for item in package["providers"])
    settings = request.get("settings", {}).get("plugins", {})
    for package_id, packages in by_id.items():
        if len(packages) != 1:
            for package in packages:
                diagnostic(package["root"], "duplicate package ID; all candidates rejected", package_id)
            continue
        package = packages[0]
        enabled = settings.get(package_id, {}).get("enabled", package["builtin"] or not package["executable"])
        if package_id == PROTECTED:
            enabled = True
        result["packages"].append({key: package[key] for key in ("id", "name", "root", "builtin", "executable")})
        if not enabled:
            diagnostic(package["root"], "disabled; enable this trusted package in settings and restart", package_id)
            continue
        for kind in ("commands", "themes", "providers", "keybindings"):
            result[kind].extend(package[kind])
    loose = Path(request["themesRoot"])
    try:
        for name in entries(loose):
            if not name.endswith(".json"):
                continue
            local_id = identifier(name[:-5], LOCAL_ID, "loose theme filename")
            result["themes"].append({"id": "user.themes/" + local_id, "localId": local_id,
                                     "name": local_id, "packageId": "user.themes", "packageName": "User themes",
                                     "root": str(loose), "path": name, "builtin": False})
    except (OSError, ValueError) as error:
        diagnostic(loose, str(error))
    # Compatibility window: legacy providers keep their activation defaults.
    legacy = Path(request["legacyRoot"])
    try:
        for name in entries(legacy):
            root = legacy / name
            try:
                identifier(name, LOCAL_ID, "legacy provider ID")
                path = resource(root, "Provider.qml", read=False)
                result["providers"].append({"id": name, "packageId": "legacy." + name,
                                            "url": Path(path).as_uri(), "builtin": False})
            except (OSError, ValueError) as error:
                diagnostic(root, str(error))
    except (OSError, ValueError) as error:
        diagnostic(legacy, str(error))
    providers = {}
    for provider in result["providers"]:
        providers.setdefault(provider["id"], []).append(provider)
    result["providers"] = []
    for provider_id, descriptors in providers.items():
        builtins = [item for item in descriptors if item["builtin"]]
        accepted = builtins if provider_id in reserved_providers else descriptors
        if len(accepted) == 1:
            result["providers"].extend(accepted)
        if len(descriptors) > 1 or not accepted:
            diagnostic(legacy, "ambiguous or reserved provider ID: " + provider_id)
    if sum(len(result[kind]) for kind in ("commands", "themes", "providers", "keybindings")) > MAX_CONTRIBUTIONS:
        return {"error": "catalog exceeds the contribution limit"}
    return result


def main():
    try:
        raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("catalog request exceeds the byte limit")
        request = jsondata.parse(raw)
        if request.get("operation") == "resource":
            text = resource(request["root"], request["path"])
            result = {"value": jsondata.parse(text)} if request.get("json") else {"text": text}
        else:
            result = discover(request)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"error": str(error)}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
