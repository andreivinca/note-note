"""Audio attachment markup and its presentation in Qt's rich text document.

Notes keep ordinary HTML audio elements. Qt Quick's rich text supports image
objects, so a transparent image reserves the player's space in the document.
Its fragment carries the audio identity through Qt's HTML serialization; the
editor overlays an interactive player and the reader restores the audio tag.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from htmltree import parse

# The space a recording takes in the editor's document; ui/AudioPlayer.qml
# draws the player at this size over the transparent placeholder.
DISPLAY_WIDTH = 360
DISPLAY_HEIGHT = 56
DISPLAY_MARKER = "notenote-audio="
PLACEHOLDER = Path(__file__).with_name("audio-placeholder.svg").as_uri()
AUDIO_ELEMENT = r"""<audio\b(?:[^>"']|"[^"]*"|'[^']*')*>\s*</audio\s*>"""


def valid_identifier(value):
    return isinstance(value, str) and re.fullmatch(r"nn-audio-[a-z0-9-]{1,120}", value) is not None


def markup(source, title, identifier=""):
    identity = ' data-id="%s"' % html.escape(identifier, quote=True) if valid_identifier(identifier) else ""
    return '<audio src="%s" title="%s"%s></audio>' % (
        html.escape(source, quote=True), html.escape(title, quote=True), identity)


def from_markup(value):
    if not re.fullmatch(AUDIO_ELEMENT, value.strip(), re.I):
        return None
    nodes = parse(value).children
    if len(nodes) != 1 or nodes[0].tag != "audio":
        return None
    return from_attributes(nodes[0].attrs)


def from_attributes(attrs):
    """An `<audio>` element's attributes -> the audio token's attrs, or
    None when they are not the ones `markup` writes."""
    if not isinstance(attrs.get("src"), str) or set(attrs) - {"src", "title", "controls", "data-id"}:
        return None
    result = {"url": attrs["src"], "title": attrs.get("title") or "Audio recording"}
    if "data-id" in attrs:
        if not valid_identifier(attrs["data-id"]):
            return None
        result["id"] = attrs["data-id"]
    return result


def display_source(source, title, identifier=""):
    value = {"source": source, "title": title}
    if valid_identifier(identifier):
        value["id"] = identifier
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return PLACEHOLDER + "#" + DISPLAY_MARKER + quote(payload, safe="")


def from_display_source(source):
    try:
        fragment = urlsplit(source).fragment
        if not fragment.startswith(DISPLAY_MARKER):
            return None
        value = json.loads(unquote(fragment[len(DISPLAY_MARKER):]))
        if isinstance(value, dict) and isinstance(value.get("source"), str) and isinstance(value.get("title"), str):
            if not valid_identifier(value.get("id", "")):
                value.pop("id", None)
            return value
    except (ValueError, TypeError):
        pass
    return None


def _parse_audio(inline, match, state):
    attrs = from_markup(match.group(0))
    if attrs is None:
        return None
    state.append_token({"type": "audio", "attrs": attrs})
    return match.end()


def plugin(md):
    md.inline.register("audio", AUDIO_ELEMENT, _parse_audio, before="inline_html")
