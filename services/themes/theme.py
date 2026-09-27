"""Color theme validation; no executable theme input."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extensions"))
import jsondata
import manifest

COLOR = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")


def specification():
    return jsondata.read(Path(__file__).with_name("tokens.json"), 64 * 1024)


def validate(value, local_id, tokens):
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise ValueError("unsupported theme schemaVersion")
    if set(value) - {"schemaVersion", "id", "name", "appearance", "colors"}:
        raise ValueError("unknown theme field")
    if value.get("id") != local_id:
        raise ValueError("theme ID does not match its descriptor or filename")
    manifest.label(value.get("name"), "theme name")
    if value.get("appearance", "system") not in ("system", "light", "dark"):
        raise ValueError("appearance must be system, light, or dark")
    colors = value.get("colors")
    if not isinstance(colors, dict):
        raise ValueError("theme colors must be an object")
    for key, color in colors.items():
        if key not in tokens:
            raise ValueError("unknown theme token: " + key)
        if not isinstance(color, str) or (color not in ("system", "transparent") and not COLOR.fullmatch(color)):
            raise ValueError("invalid color for " + key)
        transparent = color == "transparent" or (color.startswith("#") and len(color) == 9 and color[1:3].lower() != "ff")
        if transparent and not tokens[key]["overlay"]:
            raise ValueError("transparency is not supported for " + key)
    return value


def load(descriptor, tokens):
    raw = manifest.resource(descriptor["root"], descriptor["path"])
    return validate(jsondata.parse(raw), descriptor["localId"], tokens), len(raw.encode("utf-8"))


def main():
    try:
        raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("theme request exceeds the byte limit")
        request = jsondata.parse(raw)
        tokens = specification()
        result = {"specification": tokens, "themes": [], "diagnostics": []}
        size = 0
        for descriptor in request.get("descriptors", []):
            try:
                value, length = load(descriptor, tokens)
                size += length
                if size > manifest.MAX_INPUT:
                    break
                result["themes"].append({"descriptor": descriptor, "value": value})
            except (OSError, ValueError) as error:
                result["diagnostics"].append({"id": descriptor.get("id"), "message": str(error)})
        if size > manifest.MAX_INPUT:
            raise ValueError("theme catalog exceeds the input byte limit")
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"error": str(error)}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
