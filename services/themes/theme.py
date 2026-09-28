"""Color theme validation; no executable theme input.

Which tokens a theme may set, and which of them may be translucent, is the
application's list (design/tokens.js). It comes with each request, so it is
kept in one place.
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import jsondata
import packagefiles

MAX_INPUT = 8 * 1024 * 1024
MAX_REQUEST = 2 * 1024 * 1024
COLOR = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")
FIELDS = {"schemaVersion", "id", "name", "colors"}
KEYWORDS = ("system", "transparent")


def translucent(color):
    """#AARRGGBB follows Qt: the alpha comes first."""
    return color == "transparent" or (len(color) == 9 and color[1:3].lower() != "ff")


def validate(value, local_id, tokens):
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise ValueError("unsupported theme schemaVersion")
    if set(value) - FIELDS:
        raise ValueError("unknown theme field")
    if value.get("id") != local_id:
        raise ValueError("theme ID does not match its descriptor or filename")
    packagefiles.label(value.get("name"), "theme name")
    colors = value.get("colors")
    if not isinstance(colors, dict):
        raise ValueError("theme colors must be an object")
    for key, color in colors.items():
        if key not in tokens:
            raise ValueError("unknown theme token: " + key)
        if not isinstance(color, str) or (color not in KEYWORDS and not COLOR.fullmatch(color)):
            raise ValueError("invalid color for " + key)
        if translucent(color) and not tokens[key]["overlay"]:
            raise ValueError("transparency is not supported for " + key)
    return value


def load(descriptor, tokens):
    raw = packagefiles.read_resource(descriptor["root"], descriptor["path"])
    return validate(jsondata.parse(raw), descriptor["localId"], tokens), len(raw.encode("utf-8"))


def named_tokens(request):
    tokens = request.get("tokens")
    if not isinstance(tokens, dict) or not tokens:
        raise ValueError("the request names no tokens")
    if any(not isinstance(token, dict) or type(token.get("overlay")) is not bool for token in tokens.values()):
        raise ValueError("each token says whether it may be translucent")
    return tokens


def respond(request):
    tokens = named_tokens(request)
    result = {"themes": [], "diagnostics": []}
    size = 0
    for descriptor in request.get("descriptors", []):
        try:
            value, length = load(descriptor, tokens)
            size += length
            if size > MAX_INPUT:
                raise ValueError("the theme catalog's input limit is reached; this theme is left out")
            result["themes"].append({"descriptor": descriptor, "value": value})
        except (OSError, ValueError) as error:
            result["diagnostics"].append({"id": descriptor.get("id"), "message": str(error)})
    return result


if __name__ == "__main__":
    jsondata.answer(respond, MAX_REQUEST)
