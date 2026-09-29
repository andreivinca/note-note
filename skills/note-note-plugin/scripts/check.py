#!/usr/bin/env python3
"""Check Note Note plugin packages with the application's own validator.

Runs the app's services/extensions/manifest.py over the user's plugin and
theme folders, as the app does at startup, and prints what it would load and
what it would refuse. The rules live in the app; nothing here repeats them.
Theme colors are checked by the app when its Color Theme picker opens.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

APP_ID = "io.github.andreivinca.note-note"
VALIDATOR = Path("services/extensions/manifest.py")
MAX_CONFIG = 1024 * 1024
TIMEOUT_SECONDS = 30


def installed_apps():
    """Where the app's files can be, most specific first."""
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    flatpak = Path("app") / APP_ID / "current/active/files/share/note-note"
    # This skill ships at skills/note-note-plugin/ inside the app's own tree.
    beside_skill = Path(__file__).resolve().parents[3]
    return [beside_skill, config / "omarchy/plugins" / APP_ID, data / "flatpak" / flatpak,
            Path("/var/lib/flatpak") / flatpak, Path("/usr/local/share/note-note"), Path("/usr/share/note-note")]


def find_app(given):
    candidates = [Path(given).expanduser()] if given else installed_apps()
    for root in candidates:
        if (root / VALIDATOR).is_file():
            return root
    raise SystemExit("Note Note was not found. Pass --app with the folder that holds " + str(VALIDATOR) + ".")


def plugin_settings(config_dir):
    """The `plugins` group of the user's config.json: which packages are on."""
    path = config_dir / "config.json"
    try:
        with open(path, "rb") as stream:
            raw = stream.read(MAX_CONFIG + 1)
    except FileNotFoundError:
        return {}
    if len(raw) > MAX_CONFIG:
        raise SystemExit(str(path) + " is larger than " + str(MAX_CONFIG) + " bytes.")
    try:
        plugins = json.loads(raw).get("plugins", {})
    except (ValueError, AttributeError) as error:
        raise SystemExit(str(path) + " is not a JSON object: " + str(error))
    if not isinstance(plugins, dict):
        raise SystemExit(str(path) + ": \"plugins\" must be an object.")
    return plugins


def discover(app, config_dir, settings):
    request = {"builtinRoot": str(app / "plugins"), "userRoot": str(config_dir / "plugins"),
               "themesRoot": str(config_dir / "themes"), "legacyRoot": str(config_dir / "providers"),
               "settings": {"plugins": settings}}
    completed = subprocess.run([sys.executable, str(app / VALIDATOR)], input=json.dumps(request),
                               capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    try:
        catalog = json.loads(completed.stdout)
    except ValueError:
        raise SystemExit("The validator gave no answer:\n" + completed.stderr)
    if "error" in catalog:
        raise SystemExit("The validator refused the request: " + catalog["error"])
    return catalog


def report(catalog):
    """Print the user's contributions and every diagnostic; True when nothing was refused."""
    commands = [item for item in catalog["commands"] if not item["builtin"]]
    own = {item["id"] for item in commands}
    lines = []
    for item in commands:
        lines.append("command     " + item["id"] + "  \"" + item["title"] + "\"")
    for binding in catalog["keybindings"]:
        if binding["command"] in own:
            lines.append("keybinding  " + binding["key"] + " -> " + binding["command"] + " (" + binding["context"] + ")")
    for item in catalog["themes"]:
        if not item["builtin"]:
            lines.append("theme       " + item["id"])
    for item in catalog["tools"]:
        if not item["builtin"]:
            lines.append("tool        " + item["id"] + " (" + item["packageId"] + ")")
    for item in catalog["providers"]:
        if not item["builtin"]:
            lines.append("provider    " + item["id"] + " (" + item["packageId"] + ")")
    print("Loaded:")
    print("\n".join("  " + line for line in lines) if lines else "  nothing from the user's folders")
    diagnostics = catalog["diagnostics"]
    if diagnostics:
        print("Diagnostics:")
    for diagnostic in diagnostics:
        name = diagnostic.get("packageId") or Path(diagnostic.get("path", "")).name
        print("  " + diagnostic.get("level", "error").ljust(6) + name + ": " + diagnostic["message"])
        print("        " + diagnostic.get("path", ""))
    return not any(diagnostic.get("level", "error") == "error" for diagnostic in diagnostics)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "notenote"
    parser.add_argument("--app", help="the Note Note folder holding services/ and plugins/ (found when left out)")
    parser.add_argument("--config", default=str(default_config),
                        help="the app's config folder (default: %(default)s; Flatpak: "
                             "~/.var/app/" + APP_ID + "/config/notenote)")
    parser.add_argument("--enable", action="append", default=[], metavar="PACKAGE_ID",
                        help="check this package as if the user had enabled it (repeatable)")
    arguments = parser.parse_args()
    app = find_app(arguments.app)
    config_dir = Path(arguments.config).expanduser()
    settings = plugin_settings(config_dir)
    for package_id in arguments.enable:
        settings[package_id] = dict(settings.get(package_id, {}), enabled=True)
    print("App:     " + str(app))
    print("Plugins: " + str(config_dir / "plugins"))
    print("Themes:  " + str(config_dir / "themes"))
    return 0 if report(discover(app, config_dir, settings)) else 1


if __name__ == "__main__":
    sys.exit(main())
