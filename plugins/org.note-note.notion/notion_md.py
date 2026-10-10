"""Notion blocks <-> Markdown, in the dialect Qt's TextEdit reads and writes.

Supported both ways: paragraph, heading_1..3, bulleted_list_item,
numbered_list_item, to_do, quote, code, divider, and nested children as
indentation. Rich text: bold, italic, underline, strikethrough, code, links,
the yellow highlight. Anything else marks the page as not editable
(unwritable()), and Markdown holding anything else is refused rather than
written without it (markdown_to_blocks(), Unkept).
"""


# All renderers share escaping and code delimiters.
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "services", "markdown"))
from mdtext import escape_text, escape_line_start, code_span, code_fence  # noqa: E402
from parse import parse as _parse  # noqa: E402
# A blank line is a paragraph holding this character in every backend's Markdown.
from qthtml.dialect import BLANK_PARAGRAPH  # noqa: E402
SUPPORTED = {"paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item",
             "numbered_list_item", "to_do", "quote", "code", "divider"}
# The one highlight the writer can put back; every other colour is lost.
KEPT_COLORS = {"default", "yellow_background"}
# The blocks whose children the writer puts back, as indented Markdown.
NESTING = {"bulleted_list_item", "numbered_list_item", "to_do"}
# Every property of a supported block (developers.notion.com/reference/block)
# is one of these two. The writer sets the text, the children, a to-do's
# state and a code block's language from the Markdown...
WRITTEN = {"rich_text", "children", "checked", "language"}
# ...and has no syntax for the rest, so every block it writes leaves them at
# Notion's default: each with that default, and what a reason calls a block
# that holds another value. A property Notion adds after this table counts
# the same way whenever it holds anything.
UNWRITTEN = {
    "color": ("default", "a coloured block"),
    "caption": ([], "a code caption"),
    "is_toggleable": (False, "a toggle heading"),
    "icon": (None, "a paragraph icon"),
    "list_start_index": (1, "a numbered list that does not start at 1"),
    "list_format": ("numbers", "a list numbered with letters or roman numerals"),
}


def _holds(key, value):
    """Whether a block property holds a value no block the writer makes has."""
    if key in UNWRITTEN:
        return value is not None and value != UNWRITTEN[key][0]
    return bool(value)


def _unwritten(body):
    """The properties of a block that a save could not write back as they
    are, with their values: {name: value}, in the block's own order."""
    return {key: value for key, value in body.items() if key not in WRITTEN and _holds(key, value)}


def _named(noun):
    return ("an " if noun[:1] in "aeiou" else "a ") + noun.replace("_", " ")


def _setting(kind, key):
    """What a reason calls a block holding this property."""
    if key in UNWRITTEN:
        return UNWRITTEN[key][1]
    return "%s %s" % (_named(kind), key.replace("_", " "))



# ---------------------------------------------------------------- blocks -> markdown

def _joined_rich(rich):
    """Backend chunk limits must not introduce adjacent Markdown delimiters."""
    out = []
    for item in rich or []:
        if (out and out[-1].get("annotations", {}) == item.get("annotations", {})
                and out[-1].get("href") == item.get("href")):
            out[-1]["plain_text"] += item.get("plain_text", "")
        else:
            out.append(dict(item, plain_text=item.get("plain_text", "")))
    return out


def rich_to_md(rich):
    out = []
    for r in _joined_rich(rich):
        t = r.get("plain_text", "")
        a = r.get("annotations", {})
        if not t:
            continue
        t = t if a.get("code") else escape_text(t)
        lead = t[:len(t) - len(t.lstrip())]
        trail = t[len(t.rstrip()):]
        core = t.strip()
        if core:
            if a.get("code"):
                core = code_span(core)
            if a.get("bold"):
                core = "**%s**" % core
            if a.get("italic"):
                core = "*%s*" % core
            if a.get("underline"):
                core = "_%s_" % core
            if a.get("strikethrough"):
                core = "~~%s~~" % core
            if str(a.get("color", "")).endswith("_background"):
                core = "==%s==" % core
            href = r.get("href")
            if href:
                core = "[%s](%s)" % (core, href)
        out.append(lead + core + trail)
    return "".join(out)


def _run_chars(run):
    """One rich-text run as the characters a save must reproduce: each with
    its formatting and link, except whitespace, which Markdown can neither
    format nor link. Reads Notion's answer (`plain_text`, `href`) and the
    writer's request (`text.content`, `text.link`) alike."""
    text = run.get("plain_text") if "plain_text" in run else (run.get("text") or {}).get("content", "")
    marks = tuple(sorted(k for k, v in (run.get("annotations") or {}).items()
                         if v is True or (k == "color" and v != "default")))
    color = (run.get("annotations") or {}).get("color", "default")
    link = run.get("href") or ((run.get("text") or {}).get("link") or {}).get("url") or None
    out = []
    for char in text or "":
        if char.isspace():
            out.append((char, (), "default", None))
        else:
            out.append((char, marks, color, link))
    return out


def essence(blocks):
    """What a save can write back, block by block: the type, the text with
    its formatting per character, a to-do's state, a code block's language,
    every property the writer leaves at Notion's default that holds another
    value (a colour, a caption...), and the children — the same shape
    whether the blocks came from Notion or from markdown_to_blocks, so the
    two can be compared."""
    out = []
    for block in blocks or []:
        kind = block.get("type")
        body = block.get(kind) or {}
        chars = []
        for run in body.get("rich_text") or []:
            if run.get("type", "text") != "text":
                chars.append(("\ufffc", (run.get("type"),), "default", None))
            chars.extend(_run_chars(run))
        language = (body.get("language") or "plain text") if kind == "code" else None
        children = block.get("children") or body.get("children") or []
        out.append((kind, chars, bool(body.get("checked")), language, _unwritten(body), essence(children)))
    return out


def unwritable(blocks):
    """Why a save could not put this page back as it is: the names of what
    the writer has no block, annotation, property or nesting for, in page
    order and without repeats. Empty when the page round-trips — decided by
    the trip itself (essence), with these names as the explanation."""
    reasons = []

    def add(name):
        if name not in reasons:
            reasons.append(name)

    def walk(blocks, nested_under=None):
        for block in blocks or []:
            kind = block.get("type")
            body = block.get(kind) or {}
            if kind not in SUPPORTED:
                add(_named(str(kind)) + " block")
            else:
                if nested_under and nested_under not in NESTING:
                    add("text nested under " + _named(nested_under))
                for key in _unwritten(body):
                    add(_setting(kind, key))
            for run in body.get("rich_text") or []:
                if run.get("type", "text") != "text":
                    add(_named(str(run.get("type"))))
                elif (run.get("annotations") or {}).get("color", "default") not in KEPT_COLORS:
                    add("coloured text")
            children = block.get("children") or body.get("children") or []
            walk(children, kind if kind in SUPPORTED else None)

    walk(blocks)
    if reasons:
        return reasons
    # The trip itself: the page's Markdown written back as blocks. A refusal
    # there is a reason in its own right, never an error loading the page.
    try:
        written = markdown_to_blocks(blocks_to_markdown(blocks)[0])
    except Unkept as error:
        return [error.what]
    except ValueError:
        return ["text a save could not write back"]
    if essence(blocks) != essence(written):
        return ["formatting a save could not put back as it is"]
    return []


def _item_text(text, indent):
    """A list item's text with its line breaks written as Markdown hard
    breaks, each line continued at `indent` and escaped where it starts, so
    it reads back as one item holding the same lines (the writer's `\\n`)."""
    return ("  \n" + indent).join(escape_line_start(line) for line in text.split("\n"))


def blocks_to_markdown(blocks, depth=0):
    """blocks: [{type, <type>: {...}, children: [...]}] -> (markdown, editable).

    `editable` is the block types alone; `unwritable` is the whole answer,
    from the round trip, and is what decides whether the page opens for
    editing (notion.py, cmd_page)."""
    lines, editable, prev = [], True, None
    pad = "  " * depth
    for b in blocks:
        t = b.get("type")
        body = b.get(t, {}) or {}
        text = rich_to_md(body.get("rich_text"))
        kids = b.get("children") or []
        if t not in SUPPORTED:
            editable = False
            lines.append(pad + "[unsupported: %s]" % t)
            prev = t
            continue
        if t == "divider":
            lines.append("")
            lines.append(pad + "---")
            lines.append("")
        elif t.startswith("heading_"):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(pad + "#" * int(t[-1]) + " " + text)
            lines.append("")
        elif t == "paragraph":
            # Consecutive paragraphs of text are one Markdown paragraph with
            # hard breaks, which the writer splits back into paragraphs. A
            # blank one is a Markdown paragraph of its own, the dialect's
            # BLANK_PARAGRAPH: behind a hard break it was no line at all,
            # and the page around it could never be written back.
            joined = (prev == "paragraph" and text and lines
                      and lines[-1] != "" and not lines[-1].endswith(BLANK_PARAGRAPH))
            if joined:
                lines[-1] = lines[-1] + "  "
            elif prev is not None and lines and lines[-1] != "":
                lines.append("")
            first = (body.get("rich_text") or [{}])[0]
            ann = first.get("annotations") or {}
            plain_start = not ann.get("bold") and not ann.get("italic") and not ann.get("code") and not first.get("href")
            lines.append((pad + (escape_line_start(text) if plain_start else text)) if text else pad + BLANK_PARAGRAPH)
        elif t == "bulleted_list_item":
            if prev not in ("bulleted_list_item", "numbered_list_item", "to_do") and lines and lines[-1] != "":
                lines.append("")
            lines.append(pad + "- " + _item_text(text, pad + "  "))
        elif t == "numbered_list_item":
            if prev not in ("bulleted_list_item", "numbered_list_item", "to_do") and lines and lines[-1] != "":
                lines.append("")
            lines.append(pad + "1. " + _item_text(text, pad + "   "))
        elif t == "to_do":
            if prev not in ("bulleted_list_item", "numbered_list_item", "to_do") and lines and lines[-1] != "":
                lines.append("")
            lines.append(pad + ("- [x] " if body.get("checked") else "- [ ] ") + _item_text(text, pad + "  "))
        elif t == "quote":
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(pad + "> " + text)
            lines.append("")
        elif t == "code":
            if lines and lines[-1] != "":
                lines.append("")
            lang = body.get("language", "") or ""
            code = "".join(r.get("plain_text", "") for r in body.get("rich_text", []))
            fence = code_fence(code)
            lines.append(pad + fence + ("" if lang in ("plain text", "plain_text") else lang))
            for l in code.split("\n"):
                lines.append(pad + l)
            lines.append(pad + fence)
            lines.append("")
        if kids:
            sub, ok = blocks_to_markdown(kids, depth + 1)
            if not ok:
                editable = False
            lines.extend(sub.split("\n"))
        prev = t
    # tidy blank runs
    out, blank = [], True
    for l in lines:
        if l.strip() or l.endswith(BLANK_PARAGRAPH):
            out.append(l)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out), editable


# ---------------------------------------------------------------- markdown -> blocks
#
# Markdown is parsed by the vendored mistune (services/markdown/parse.py);
# this is only the renderer into Notion blocks. It renders what it has a
# block or an annotation for and refuses the rest (Unkept): a save replaces
# the whole page, so anything it flattened or left out would be gone from
# Notion while the editor still showed it.


class Unkept(ValueError):
    """Markdown holding something a Notion page cannot keep. `what` names it
    the way unwritable() names what a page holds."""

    def __init__(self, what):
        super().__init__("Notion cannot keep %s; take it out to save — your draft was kept" % what)
        self.what = what


# What a refusal calls each token the renderer has nothing for; any other
# is named after its type.
NOUNS = {"table": "a table", "block_html": "HTML", "inline_html": "HTML", "image": "a picture",
         "audio": "a recording", "text_color": "coloured text", "block_quote": "a quote",
         "list": "a list", "heading": "a heading", "block_code": "a code block",
         "thematic_break": "a rule"}
# The inline tokens that wrap text in a rich-text annotation, and which one.
ANNOTATIONS = {"strong": "bold", "emphasis": "italic", "underline": "underline",
               "strikethrough": "strikethrough"}


def _unkept(token, where=""):
    return Unkept((NOUNS.get(token["type"]) or _named(token["type"])) + where)


TEXT_LIMIT = 2000
ARRAY_LIMIT = 100
PAYLOAD_LIMIT = 500 * 1024
BLOCK_LIMIT = 1000


def text_items(text, annotations=None, link=None):
    """Keep every character, with the same metadata on each bounded entry."""
    if not isinstance(text, str):
        raise ValueError("note text must be a string")
    if link and len(link) > TEXT_LIMIT:
        raise ValueError("a link exceeds Notion's 2000-character limit")
    out = []
    for start in range(0, len(text), TEXT_LIMIT):
        item = {"type": "text", "text": {"content": text[start:start + TEXT_LIMIT]}}
        if annotations:
            item["annotations"] = dict(annotations)
        if link:
            item["text"]["link"] = {"url": link}
        out.append(item)
    return out


def validate_payload(payload):
    """Check the complete representation before any backend mutation."""
    import json
    blocks = 0

    def visit(value):
        nonlocal blocks
        if isinstance(value, list):
            if len(value) > ARRAY_LIMIT:
                raise ValueError("a Notion array exceeds 100 entries; split the paragraph or document")
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if value.get("type") in SUPPORTED:
                blocks += 1
            for key, item in value.items():
                if key in ("content", "url") and isinstance(item, str) and len(item) > TEXT_LIMIT:
                    raise ValueError("Notion text or link exceeds 2000 characters")
                visit(item)

    visit(payload)
    if blocks > BLOCK_LIMIT or len(json.dumps(payload).encode("utf-8")) > PAYLOAD_LIMIT:
        raise ValueError("the note exceeds Notion's request size limit")
    return payload


def append_batches(blocks):
    """Plan and validate every append before the first one is sent."""
    batches = [{"children": blocks[i:i + ARRAY_LIMIT]} for i in range(0, len(blocks), ARRAY_LIMIT)]
    for batch in batches:
        validate_payload(batch)
    return batches


def _rich(tokens, ann=None, link=None):
    """Inline tokens -> Notion rich_text array; Unkept for any token that
    is no annotation of Notion's (a picture, coloured text, HTML...)."""
    out = []
    ann = dict(ann or {})

    def emit(text):
        out.extend(text_items(text, ann, link))

    for t in tokens or []:
        ty = t["type"]
        if ty == "text":
            emit(t.get("raw", ""))
        elif ty == "softbreak":
            emit(" ")
        elif ty == "linebreak":
            emit("\n")
        elif ty == "codespan":
            out.extend(text_items(t.get("raw", ""), dict(ann, code=True), link))
        elif ty in ANNOTATIONS:
            out.extend(_rich(t.get("children"), dict(ann, **{ANNOTATIONS[ty]: True}), link))
        elif ty == "mark":
            out.extend(_rich(t.get("children"), dict(ann, color="yellow_background"), link))
        elif ty == "link":
            out.extend(_rich(t.get("children"), ann, t.get("attrs", {}).get("url", "") or link))
        else:
            raise _unkept(t)
    return out


def _split_lines(tokens):
    """Inline tokens split at hard line breaks -> list of token lists."""
    out, cur = [], []
    for t in tokens or []:
        if t["type"] == "linebreak":
            out.append(cur)
            cur = []
        else:
            cur.append(t)
    out.append(cur)
    return out


def _para_blocks(tokens):
    blocks = []
    for line in _split_lines(tokens):
        rich = _rich(line)
        blocks.append({"type": "paragraph", "paragraph": {"rich_text": rich}})
    return blocks


def _list_blocks(t):
    """A list's items, each one block whose text is the item's paragraph —
    its line breaks kept as Notion's `\\n` (blocks_to_markdown writes them
    back as hard breaks) — and whose children are the rest of the item."""
    blocks = []
    ordered = t.get("attrs", {}).get("ordered", False)
    for item in t.get("children") or []:
        paragraphs, kids = [], []
        for c in item.get("children") or []:
            if c["type"] in ("block_text", "paragraph"):
                paragraphs.append(c.get("children") or [])
            elif c["type"] == "list":
                kids.extend(_list_blocks(c))
            else:
                kids.extend(_blocks([c]))
        if len(paragraphs) > 1:
            raise Unkept("a list item of more than one paragraph")
        rich = _rich(paragraphs[0] if paragraphs else [])
        if item["type"] == "task_list_item":
            b = {"type": "to_do", "to_do": {"rich_text": rich, "checked": bool(item.get("attrs", {}).get("checked"))}}
        elif ordered:
            b = {"type": "numbered_list_item", "numbered_list_item": {"rich_text": rich}}
        else:
            b = {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich}}
        if kids:
            b[b["type"]]["children"] = kids
        blocks.append(b)
    return blocks


def _quote_blocks(t):
    """A quote is one quote block per line of its text; Notion's quote holds
    text, so a list, a heading or another quote inside one is refused."""
    for c in t.get("children") or []:
        if c["type"] not in ("paragraph", "blank_line"):
            raise _unkept(c, " inside a quote")
    return [{"type": "quote", "quote": b["paragraph"]} for b in _blocks(t.get("children"))]


def _blocks(tokens):
    """Block tokens -> Notion blocks; Unkept for any block Notion has no
    block for (a table, HTML, a heading below level 3...)."""
    out = []
    for t in tokens or []:
        ty = t["type"]
        if ty == "blank_line":
            continue
        if ty == "paragraph":
            children = t.get("children") or []
            text_only = "".join(x.get("raw", "") for x in children if x["type"] == "text")
            if text_only.strip() == "" and BLANK_PARAGRAPH in "".join(x.get("raw", "") for x in children):
                out.append({"type": "paragraph", "paragraph": {"rich_text": []}})
            else:
                out.extend(_para_blocks(t.get("children")))
        elif ty == "heading":
            level = t.get("attrs", {}).get("level", 1)
            if level > 3:
                raise Unkept("a level-%d heading" % level)
            key = "heading_%d" % level
            out.append({"type": key, key: {"rich_text": _rich(t.get("children"))}})
        elif ty == "thematic_break":
            out.append({"type": "divider", "divider": {}})
        elif ty == "block_code":
            lang = (t.get("attrs", {}).get("info") or "plain text").strip() or "plain text"
            out.append({"type": "code", "code": {"language": lang, "rich_text": text_items(t.get("raw", "").removesuffix("\n"))}})
        elif ty == "block_quote":
            out.extend(_quote_blocks(t))
        elif ty == "list":
            out.extend(_list_blocks(t))
        elif ty == "block_text":
            out.extend(_para_blocks(t.get("children")))
        else:
            raise _unkept(t)
    return out


def markdown_to_blocks(md):
    return _blocks(_parse(md))
