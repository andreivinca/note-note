"""Discover declarative packages without importing their executable code.

What a manifest may declare is decided here. Two things are not: the grammar
of a shortcut key and the names of command requirements belong to the code
that acts on them (services/shortcuts, services/commands), which reports what
it cannot use instead of having a second list kept in step here.
"""
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import jsondata
import packagefiles
from packagefiles import label

MAX_MANIFEST = 64 * 1024
MAX_INPUT = 8 * 1024 * 1024
MAX_REQUEST = 2 * 1024 * 1024
MAX_PACKAGES = 128
MAX_PER_KIND = 128
MAX_CONTRIBUTIONS = 4096
PACKAGE_ID = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+\Z")
LOCAL_ID = re.compile(r"[a-z][a-z0-9-]*\Z")
ACTION_ID = re.compile(r"[a-z][a-zA-Z0-9]{0,63}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
PROTECTED = "org.note-note.appearance"
LOOSE_THEMES = "user.themes"
KINDS = ("commands", "themes", "providers", "keybindings")
# Where a provider's tabs stand among the others when the settings name no
# order of their own; lower comes first.
DEFAULT_ORDER = 1000
MAX_ORDER = 9999


def identifier(value, expression, name):
    label(value, name, 128)
    if not expression.fullmatch(value):
        raise ValueError("invalid " + name)
    return value


def strings(value, name, count, length):
    if not isinstance(value, list) or len(value) > count:
        raise ValueError("invalid " + name)
    return [label(item, name, length) for item in value]


# ---- one manifest --------------------------------------------------------

def owned(package, local_id, relative=None):
    """What every contribution says about where it came from."""
    descriptor = {"id": package["id"] + "/" + local_id, "localId": local_id, "packageId": package["id"],
                  "packageName": package["name"], "root": package["root"], "builtin": package["builtin"]}
    if relative is not None:
        descriptor["path"] = relative
        descriptor["url"] = Path(packagefiles.resource_path(package["root"], relative)).as_uri()
    return descriptor


def command(package, item, local_id):
    handler, action = item.get("handler"), item.get("workspaceAction")
    if (handler is None) == (action is None):
        raise ValueError("a command names a handler or a workspaceAction, one of the two")
    descriptor = owned(package, local_id, handler)
    descriptor["title"] = label(item.get("title"), "command title")
    descriptor["category"] = label(item["category"], "command category") if "category" in item else ""
    descriptor["workspaceAction"] = "" if action is None else identifier(action, ACTION_ID, "workspace action")
    descriptor["keywords"] = strings(item.get("keywords", []), "command keywords", 32, 64)
    descriptor["requires"] = strings(item.get("requires", []), "command requirements", 16, 64)
    return descriptor


def theme(package, item, local_id):
    return owned(package, local_id, label(item.get("path"), "theme path", 512))


def provider(package, item, local_id):
    descriptor = owned(package, local_id, label(item.get("path"), "provider path", 512))
    # A provider keeps the identity its notes, settings and state are filed under.
    descriptor["id"] = local_id
    order = item.get("order", DEFAULT_ORDER)
    if type(order) is not int or not 0 <= order <= MAX_ORDER:
        raise ValueError("provider order must be a whole number from 0 to " + str(MAX_ORDER))
    descriptor["order"] = order
    return descriptor


BUILDERS = {"commands": command, "themes": theme, "providers": provider}


def listed(contributions, kind):
    items = contributions.get(kind, [])
    if not isinstance(items, list) or len(items) > MAX_PER_KIND:
        raise ValueError("invalid or oversized " + kind + " list")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError(kind + " entries must be objects")
    return items


def contributed(package, contributions, kind):
    seen = set()
    result = []
    for item in listed(contributions, kind):
        local_id = identifier(item.get("id"), LOCAL_ID, "contribution ID")
        if local_id in seen:
            raise ValueError("duplicate " + kind + " ID: " + local_id)
        seen.add(local_id)
        result.append(BUILDERS[kind](package, item, local_id))
    return result


def keybinding(package, item, commands):
    local_id = identifier(item.get("command"), LOCAL_ID, "keybinding command")
    if local_id not in commands:
        raise ValueError("keybindings must refer to a command in this package")
    return {"command": package["id"] + "/" + local_id, "key": label(item.get("key"), "keybinding key", 64),
            "context": label(item.get("context", "notes"), "keybinding context", 32)}


def validate(value, root, builtin=False):
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise ValueError("unsupported plugin schemaVersion")
    if type(value.get("apiVersion")) is not int or value["apiVersion"] != 1:
        raise ValueError("unsupported plugin apiVersion")
    package_id = identifier(value.get("id"), PACKAGE_ID, "package ID")
    if not builtin and (package_id.startswith("org.note-note.") or package_id == LOOSE_THEMES):
        raise ValueError("reserved package namespace")
    identifier(value.get("version"), VERSION, "package version")
    contributions = value.get("contributes")
    if not isinstance(contributions, dict) or not contributions or set(contributions) - set(KINDS):
        raise ValueError("unsupported or missing contributions")
    package = {"id": package_id, "name": label(value.get("name"), "package name"),
               "root": str(root), "builtin": builtin}
    for kind in BUILDERS:
        package[kind] = contributed(package, contributions, kind)
    commands = {item["localId"] for item in package["commands"]}
    package["keybindings"] = [keybinding(package, item, commands) for item in listed(contributions, "keybindings")]
    package["executable"] = bool(package["commands"] or package["providers"])
    return package


# ---- the catalog ---------------------------------------------------------

def diagnose(catalog, path, message, package_id="", level="error"):
    catalog["diagnostics"].append({"packageId": package_id, "stage": "discovery", "level": level,
                                   "path": str(path), "message": message})


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


def listing(catalog, directory):
    try:
        return entries(directory)
    except (OSError, ValueError) as error:
        diagnose(catalog, directory, str(error))
        return []


def manifests(catalog, request):
    """Every package whose manifest is valid: the application's own first,
    so nothing a user installs can use up their share of a limit."""
    found = []
    read = 0
    for key, builtin in (("builtinRoot", True), ("userRoot", False)):
        directory = Path(request[key])
        for name in listing(catalog, directory):
            root = directory / name
            try:
                raw = packagefiles.read_resource(root, "plugin.json", MAX_MANIFEST)
                read += len(raw.encode("utf-8"))
                if read > MAX_INPUT:
                    raise ValueError("the catalog's input limit is reached; this package is left out")
                found.append(validate(jsondata.parse(raw), root, builtin))
            except (OSError, ValueError) as error:
                diagnose(catalog, root, str(error))
    return found


def enabled(package, settings):
    if package["id"] == PROTECTED:
        return True
    return settings.get(package["id"], {}).get("enabled", package["builtin"] or not package["executable"])


def accepted(catalog, found, settings):
    """The packages that are one of a kind and switched on."""
    claims = {}
    for package in found:
        claims.setdefault(package["id"], []).append(package)
    result = []
    for package in found:
        if len(claims[package["id"]]) > 1:
            diagnose(catalog, package["root"], "duplicate package ID; all candidates rejected", package["id"])
        elif enabled(package, settings):
            result.append(package)
        else:
            diagnose(catalog, package["root"], "disabled; enable this trusted package in settings and restart",
                     package["id"], "note")
    return result


def admit(catalog, contributions, path, package_id=""):
    """Add one owner's contributions, all of them or none."""
    size = sum(len(contributions.get(kind, [])) for kind in KINDS)
    if sum(len(catalog[kind]) for kind in KINDS) + size > MAX_CONTRIBUTIONS:
        diagnose(catalog, path, "the catalog's contribution limit is reached; this is left out", package_id)
        return
    for kind in KINDS:
        catalog[kind].extend(contributions.get(kind, []))


def loose_themes(catalog, directory):
    """Single theme files a user dropped in: data, so no package is needed."""
    for name in listing(catalog, directory):
        if not name.endswith(".json"):
            continue
        try:
            local_id = identifier(name[:-5], LOCAL_ID, "loose theme filename")
        except ValueError as error:
            diagnose(catalog, directory / name, str(error), LOOSE_THEMES)
            continue
        descriptor = {"id": LOOSE_THEMES + "/" + local_id, "localId": local_id, "packageId": LOOSE_THEMES,
                      "packageName": "User themes", "root": str(directory), "path": name, "builtin": False}
        admit(catalog, {"themes": [descriptor]}, directory / name, LOOSE_THEMES)


def legacy_providers(catalog, directory):
    """Compatibility window: a provider in the old directory, as it was
    installed — by copy or by symlink — and switched on as it always was."""
    for name in listing(catalog, directory):
        root = directory / name
        package_id = "legacy." + name
        try:
            identifier(name, LOCAL_ID, "legacy provider ID")
            path = packagefiles.resource_path(root, "Provider.qml", follow_root=True)
        except (OSError, ValueError) as error:
            diagnose(catalog, root, str(error), package_id)
            continue
        descriptor = {"id": name, "packageId": package_id, "root": str(root), "url": Path(path).as_uri(),
                      "builtin": False, "order": DEFAULT_ORDER}
        admit(catalog, {"providers": [descriptor]}, root, package_id)


def one_of_a_kind(catalog):
    """Providers whose identity nothing else claims, in tab order. A built-in
    keeps its identity against any other claim; among others nobody wins."""
    claims = {}
    for descriptor in catalog["providers"]:
        claims.setdefault(descriptor["id"], []).append(descriptor)
    kept = []
    for descriptor in catalog["providers"]:
        rivals = claims[descriptor["id"]]
        builtin = [rival for rival in rivals if rival["builtin"]]
        if len(rivals) == 1 or builtin == [descriptor]:
            kept.append(descriptor)
        else:
            diagnose(catalog, descriptor["root"], "ambiguous or reserved provider ID: " + descriptor["id"],
                     descriptor["packageId"])
    return sorted(kept, key=lambda descriptor: descriptor["order"])


def discover(request):
    catalog = {kind: [] for kind in KINDS}
    catalog["diagnostics"] = []
    settings = request.get("settings", {}).get("plugins", {})
    for package in accepted(catalog, manifests(catalog, request), settings):
        admit(catalog, package, package["root"], package["id"])
    loose_themes(catalog, Path(request["themesRoot"]))
    legacy_providers(catalog, Path(request["legacyRoot"]))
    catalog["providers"] = one_of_a_kind(catalog)
    return catalog


def respond(request):
    if request.get("operation") != "resource":
        return discover(request)
    text = packagefiles.read_resource(request["root"], request["path"])
    return {"value": jsondata.parse(text)} if request.get("json") else {"text": text}


if __name__ == "__main__":
    jsondata.answer(respond, MAX_REQUEST)
