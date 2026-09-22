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
"""
import re

FENCE = "---"
TITLE_KEY = "title:"
PREVIEW_CHARS = 200
_MARKERS = re.compile(r"^[#>*\-\s]+")
_INLINE = re.compile(r"[*_`]")


def split(text):
    """(title, body, extra): `extra` is every front-matter line that is not
    the title, kept as written, so a save can put it back. Text without a
    front matter is all body, and a front matter that never closes is
    body too — nothing is guessed."""
    lines = text.split("\n")
    if not lines or lines[0] != FENCE:
        return "", text, []
    for end in range(1, len(lines)):
        if lines[end] == FENCE:
            break
    else:
        return "", text, []
    title, extra = "", []
    for line in lines[1:end]:
        if line.startswith(TITLE_KEY) and not title:
            title = line[len(TITLE_KEY):].replace("\t", " ").strip()
        else:
            extra.append(line)
    return title, "\n".join(lines[end + 1:]), extra


def serialize(title, body, extra=()):
    """The file for a title, a body and the front-matter lines kept from
    the file being replaced. A title is one line, whatever it was typed as."""
    title = " ".join(title.replace("\r", "\n").split("\n")).strip()
    front = [FENCE, TITLE_KEY + " " + title] + list(extra) + [FENCE]
    return "\n".join(front) + "\n" + body


def preview(body):
    """The sidebar's one line: the first line with content, its Markdown
    markers stripped, capped so a long first line stays a line."""
    for line in body.split("\n"):
        text = _INLINE.sub("", _MARKERS.sub("", line[:PREVIEW_CHARS])).replace("\t", " ").strip()
        if text:
            return text
    return ""
