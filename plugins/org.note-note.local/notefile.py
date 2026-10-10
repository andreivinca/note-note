"""The local note file format, in one place.

A note is Markdown with a front matter block:

    ---
    title: Shopping
    ---
    body

The app owns only `title`. Any other line inside the fences — the `tags:`
an outside editor adds, a date, anything — is not the app's to understand,
so `split` hands it back verbatim and `serialize` writes it back where it
was. The lister, the search, the save and the load all read the format
through here; a fourth private parser is how a hand-written front matter
once opened as body text and was written back under a second, empty one.

A note written elsewhere may end its lines with CRLF or a lone CR, and may
open with a UTF-8 byte-order mark; it reads exactly like one with LF. A
fence matched only when a line feed ended it is how such a note once
listed "title: …" as its preview and gained a second block on its first
save.
A save writes the app's own format, LF and no mark: the body it is handed
is the editor's Markdown, which already has LF, so keeping the old file's
endings would mean either a file with two kinds or rewriting the body.
A kept front-matter line keeps its text; its ending is the format's.
"""
import re

FENCE = "---"
TITLE_KEY = "title:"
BOM = "\ufeff"
PREVIEW_CHARS = 200
_LINE_END = re.compile(r"\r\n|\r|\n")
_MARKERS = re.compile(r"^[#>*\-\s]+")
_INLINE = re.compile(r"[*_`]")


def _lines(text):
    """(line, after) for each line of `text`: the line without its ending
    — LF, CRLF or a lone CR — and the offset just past that ending."""
    start = 0
    for ending in _LINE_END.finditer(text):
        yield text[start:ending.start()], ending.end()
        start = ending.end()
    yield text[start:], len(text)


def split(text):
    """(title, body, extra): `extra` is every front-matter line that is not
    the title, kept as written, so a save can put it back. Text without a
    front matter is all body, and a front matter that never closes is
    body too — nothing is guessed. The body is the text after the closing
    fence's line, exactly as written. A leading byte-order mark is the
    encoding's, not the note's, and is not part of any of the three."""
    if text.startswith(BOM):
        text = text[len(BOM):]
    lines = _lines(text)
    if next(lines)[0] != FENCE:
        return "", text, []
    title, extra = "", []
    for line, after in lines:
        if line == FENCE:
            return title, text[after:], extra
        if line.startswith(TITLE_KEY) and not title:
            title = line[len(TITLE_KEY):].replace("\t", " ").strip()
        else:
            extra.append(line)
    return "", text, []


def serialize(title, body, extra=()):
    """The file for a title, a body and the front-matter lines kept from
    the file being replaced. A title is one line, whatever it was typed as."""
    title = " ".join(_LINE_END.split(title)).strip()
    front = [FENCE, TITLE_KEY + " " + title] + list(extra) + [FENCE]
    return "\n".join(front) + "\n" + body


def preview(body):
    """The sidebar's one line: the first line with content, its Markdown
    markers stripped, capped so a long first line stays a line."""
    for line in _LINE_END.split(body):
        text = _INLINE.sub("", _MARKERS.sub("", line[:PREVIEW_CHARS])).replace("\t", " ").strip()
        if text:
            return text
    return ""
