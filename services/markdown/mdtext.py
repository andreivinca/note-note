"""Writing text back out as Markdown, without it being read as Markdown again.

Escaping is deliberately *minimal*: a note that says `2 * 3 = 6` must not grow
a backslash on every save, which is exactly the complaint that Qt's own
Markdown writer earned. A marker is escaped only where it could actually
open or close something — and `reader` verifies the result by re-parsing it,
falling back to `strict` escaping if a single character would have changed
the meaning.

The lenient rules have to know every construct `parse.py` enables, because
the fallback is blunt: it escapes every marker in the whole note, which is
the complaint above all over again, and it cannot repair a line start at
all — a two-dash line under text, the shape of an e-mail signature, was a
setext underline the strict pass could not undo, and the note could not be
saved. Add a rule here for a construct before enabling it there.
"""
import re

ALWAYS = set("\\`")
# `*` and `~` only mean something next to a non-space character; a lone one
# between spaces is literal in every dialect we care about.
ADJACENT = set("*~")
# What can start a heading, a quote, a bullet, a rule, a table row — and a
# line made of nothing but dashes or equals signs, however few: under a line
# of text it is a setext underline, which turns that line into a heading and
# is itself consumed. An e-mail signature's `--` is exactly that.
LINE_START = re.compile(r"^(\s*)([#>]|[-+*](?=\s)|[-=](?=[-=\s]*$)|\|)")
LINE_NUMBER = re.compile(r"^(\s*\d+)([.)])")
# A table's delimiter row without a leading pipe (`---|---`): with a line of
# text above it, the two become a table and the row disappears.
TABLE_DELIMITER = re.compile(r"^(\s*:?)(-)(?=-*:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$)")
# A link reference definition (`[name]: url`) is consumed whole by the parser.
LINK_DEFINITION = re.compile(r"^(\s*)(\[)(?=[^\]\n]*\]:)")
STRICT = re.compile(r"([\\*_`~=\[\]<>|])")
UNESCAPED_PIPE = re.compile(r"(?<!\\)((?:\\\\)*)\|")
LINK_DESTINATION_MARKERS = re.compile(r"([\\()])")


def escape_inline(text, strict=False):
    """Escape what would otherwise be read as inline Markdown."""
    if not text:
        return ""
    if strict:
        return STRICT.sub(r"\\\1", text)
    link_ahead = "](" in text
    out = []
    for index, char in enumerate(text):
        before = text[index - 1] if index else " "
        after = text[index + 1] if index + 1 < len(text) else " "
        escape = (char in ALWAYS
                  or (char in ADJACENT and not (before.isspace() and after.isspace()))
                  or (char == "_" and _emphasises(before, after))
                  # `==` opens or closes a highlight; a lone `=` is arithmetic.
                  or (char == "=" and (before == "=" or after == "="))
                  # A tag, a closing tag, a comment or a processing instruction.
                  or (char == "<" and (after.isalpha() or after in "/!?"))
                  or (char in "[]" and link_ahead))
        out.append("\\" + char if escape else char)
    return "".join(out)


def _emphasises(before, after):
    """Could this underscore open or close emphasis?

    Markdown does not read `user_name_field` as emphasis: an underscore only
    counts next to a word boundary, which is why `*` and `_` need different
    rules and why the naive one put a backslash in every identifier.
    """
    opens = not (before.isalnum() or before == "_") and not after.isspace()
    closes = not (after.isalnum() or after == "_") and not before.isspace()
    return opens or closes


def escape_line_start(line):
    """A line start that would become a heading, list, quote, rule or table.

    `**bold**` is not a bullet: only `- `, `+ ` and `* ` followed by a space
    are, which is what keeps emphasis at the start of a line intact.
    """
    line = LINE_START.sub(r"\1\\\2", line or "")
    line = TABLE_DELIMITER.sub(r"\1\\\2", line)
    line = LINK_DEFINITION.sub(r"\1\\\2", line)
    return LINE_NUMBER.sub(r"\1\\\2", line)


def escape_text(text):
    """Conservative escaping for plain text supplied by a remote backend."""
    return escape_inline(text, strict=True)


def escape_image_alt(text):
    """Keep a plain image description inside one Markdown label.

    Generated descriptions can contain blank lines or Markdown delimiters.
    Whitespace belongs to the label, not the surrounding document structure.
    """
    return escape_text(" ".join(text.split()))


def escape_table_cell(text):
    """Protect pipes in serialized inline Markdown without escaping them twice.

    An odd number of backslashes already protects the pipe. An even number
    represents literal backslashes and still needs an escape for the pipe.
    """
    return UNESCAPED_PIPE.sub(r"\1\\|", text).replace("\n", " ")


def escape_link_destination(url):
    """Protect Markdown delimiters while preserving the URL after parsing.

    Escaping only a closing parenthesis leaves an unmatched opening one,
    so Markdown reads the entire link as text. Backslashes must be escaped
    too, or they can consume the escape intended for a following delimiter.
    """
    return LINK_DESTINATION_MARKERS.sub(r"\\\1", url)


def code_span(text):
    """Choose a delimiter that cannot be closed by the code's own backticks."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    delimiter = "`" * (longest + 1)
    pad = text.startswith("`") or text.endswith("`") or (
        text.startswith(" ") and text.endswith(" ") and bool(text.strip()))
    body = " " + text + " " if pad else text
    return delimiter + body + delimiter


def code_fence(text):
    """A backtick fence longer than every backtick run in its body."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)
