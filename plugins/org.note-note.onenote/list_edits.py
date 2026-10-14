"""Change list topology in one conditional OneNote page revision.

Graph's list IDs describe an HTML projection, not the native ownership tree.
A list can be an outline, a group, or an element's children; removing an HTML
item need not remove its projected descendants. Resolve the actual elements
and reparent them together. Unchanged rich text and attachments keep their
objects, including properties the editor does not represent.
"""
import copy
from dataclasses import dataclass
import json
import re
import time
import uuid

from blank_lines import ASCII_TEXT, CONTENT, ELEMENT, GENERATED_ID, GROUP, RICH_TEXT, TEXT, Page
from notemerge import AmbiguousAlignment, align
from onenote_md import Converter, Node
from onenote_patch import LISTS, children, parse, serialize, text, walk
from revision_objects import CHILDREN, properties, references
from web_session import WebError
import liststyles
import textcolor

OUTLINE = 0x6000C
NUMBER = 0x60012
FORMAT = 0x12004D
CHILD_LEVEL = 0x0C001C03
LIST_NODES = 0x24001C26
LIST_FORMAT = 0x1C001C1A
LIST_RESTART = 0x14001CB7
LIST_FONT = 0x1C001C52
MODIFIED = 0x14001D7A
RUN_FORMATTING = 0x24001E13
RUN_INDEX = 0x1C001E12
FONT = 0x1C001C0A
FONT_SIZE = 0x10001C0B
BOLD = 0x08001C04
ITALIC = 0x08001C05
UNDERLINE = 0x08001C06
STRIKE = 0x08001C07
COLOR = 0x14001C0C
HIGHLIGHT = 0x14001C0D
HYPERLINK = 0x08001E14
HIDDEN = 0x08001E16
LINK_PROTECTED = 0x08001E19
SPACE_BEFORE = 0x1400342E
SPACE_AFTER = 0x1400342F
TAG_STATES = 0x40003489
TAG_STATE = 0x44000811       # one entry of TAG_STATES, as the revision service lists them
TAG_DEFINITION = 0x120043
TAG_SHAPE = 0x10003464
TAG_LABEL = 0x1C003468
TAG_TYPE = 0x10003463
TAG_HIGHLIGHT = 0x14003465
TAG_TEXT_COLOR = 0x14003466
TAG_STATUS = 0x14003467
TAG_SCHEMA = 0x0C003473
TAG_CHECKED = 0x10003470
TAG_CREATED = 0x1400346E
TAG_COMPLETED = 0x1400346F
TAG_DEFINITION_REF = 0x20003488
TAG_DEFINITIONS = {
    "to-do": (0, 3, "To Do"), "important": (1, 13, "Important"),
    "question": (2, 15, "Question"), "idea": (10, 21, "Idea"),
    "critical": (12, 17, "Critical"), "remember-for-later": (3, 0, "Remember for later"),
    "contact": (6, 118, "Contact"), "address": (7, 23, "Address"),
    "phone-number": (8, 18, "Phone number"), "web-site-to-visit": (9, 125, "Web site to visit"),
    "definition": (4, 0, "Definition"), "to-do-priority-1": (26, 28, "To Do priority 1"),
    "to-do-priority-2": (27, 71, "To Do priority 2"),
}
MARKERS = {"decimal": "65533,0,46", "upper-roman": "65533,1,46", "lower-roman": "65533,2,46",
           "upper-alpha": "65533,3,46", "lower-alpha": "65533,4,46",
           "disc": "8226", "circle": "9675", "square": "9642"}
CHANGED = "The list changed in OneNote while saving; reload the note and try again"


def reference(identifier):
    return "{%s}{%s}" % tuple(identifier.split("|"))


def object_id(generated):
    match = GENERATED_ID.fullmatch(generated)
    if not match:
        raise WebError("OneNote returned an unexpected list element ID")
    return "%s|%d" % (uuid.UUID(match[1]), int(match[2]))


def verify_text(page, row):
    """Do not overwrite text from a newer native revision than the HTML."""
    props = properties(page.objects[row.element])
    contents = references(props.get(CONTENT, ""))
    if len(contents) != 1 or page.objects.get(contents[0], {}).get("ClassId") != RICH_TEXT:
        return
    values = properties(page.objects[contents[0]])
    native = values.get(TEXT, values.get(ASCII_TEXT, ""))
    native = re.sub(r'\ufddfHYPERLINK "(?:[^"\\]|\\.)*"', "", native)
    visible = "".join((node.text or "") if node.tag is None else "\x0b" if node.tag == "br" else ""
                      for node in walk(row.node))
    if " ".join(native.split()) != " ".join(visible.split()):
        raise WebError(CHANGED)


def changed(obj, values, removed=()):
    props = properties(obj)
    for key in removed:
        props.pop(key, None)
    props.update(values)
    return dict(obj, Properties=[value for pair in props.items() for value in pair])


def confirmed(expected, actual):
    """Compare native properties, decoding the service's escaped tag JSON."""
    if actual.get("ClassId") != expected["ClassId"]:
        return False
    before, after = properties(expected), properties(actual)
    for props in (before, after):
        if TAG_STATES in props:
            try:
                states = json.loads(props[TAG_STATES])
                states["Values"] = [json.loads(value.replace(r"\u0022", '"')) for value in states["Values"]]
                props[TAG_STATES] = states
            except (TypeError, KeyError, ValueError) as error:
                raise WebError("OneNote returned invalid note-tag states") from error
    return before == after


@dataclass
class Row:
    node: Node
    depth: int = 0
    style: str = ""
    start: int = 0
    element: str = ""
    group: int = 0

    def key(self):
        if self.node.tag == "li":
            return Converter().list_inline(self.node)
        return text(self.node)


def rows(node, depth=0, style="", start=0, group=0):
    """Linear content, without confusing HTML list wrappers with ownership."""
    result = []
    if node.tag in LISTS:
        group = group or id(node)
        style = liststyles.from_attributes(node.attrs, liststyles.default(node.tag == "ol"))
        start = int(node.attrs.get("start", "1"))
        for child in children(node):
            result.extend(rows(child, depth + 1, style, start, group))
            if child.tag == "li":
                start = 0
    elif node.tag == "li":
        inline = copy.deepcopy(node)
        inline.children = [child for child in inline.children if child.tag not in LISTS]
        result.append(Row(inline, depth, liststyles.from_attributes(node.attrs, style), start, group=group))
        for child in children(node):
            if child.tag in LISTS:
                result.extend(rows(child, depth, group=group))
    elif node.tag in {"root", "html", "body", "div"}:
        for child in children(node):
            result.extend(rows(child))
    else:
        result.append(Row(copy.deepcopy(node)))
    return result


class ListPage(Page):
    def __init__(self, state):
        super().__init__(state)
        for identifier in self.reachable:
            obj = self.objects[identifier]
            props = properties(obj)
            if obj.get("ClassId") == ELEMENT:
                for marker in references(props.get(LIST_NODES, "")):
                    if marker in self.owners:
                        raise WebError("OneNote returned a list marker with two owners")
                    self.owners[marker] = identifier

    def descendants(self, identifier):
        yield identifier
        for child in self.children(identifier):
            yield from self.descendants(child)


class Writer:
    def __init__(self, page):
        self.page = page
        self.namespace = str(uuid.uuid4())
        self.next_id = 1
        self.updates = {}
        self.stamp = str(int(time.time()) * 1000)
        self.formats = {}

    def create(self, class_id, values):
        identifier = "%s|%d" % (self.namespace, self.next_id)
        self.next_id += 1
        self.updates[identifier] = {"ClassId": class_id, "ObjectId": identifier,
                                    "Properties": [value for pair in values.items() for value in pair]}
        return identifier

    def update(self, identifier, values, removed=()):
        original = self.updates.get(identifier, self.page.objects.get(identifier))
        if original is None:
            raise WebError(CHANGED)
        updated = changed(original, values, removed)
        if properties(updated) != properties(original):
            updated = changed(updated, {MODIFIED: self.stamp})
            self.updates[identifier] = updated

    def format(self, values):
        key = tuple(sorted(values.items()))
        if key not in self.formats:
            self.formats[key] = self.create(FORMAT, values)
        return self.formats[key]

    def rich_text(self, node):
        runs = []
        tags = []

        def append(value, formatting):
            if value:
                if runs and runs[-1][1] == formatting:
                    runs[-1] = (runs[-1][0] + value, formatting)
                else:
                    runs.append((value, formatting))

        def visit(node, inherited):
            formatting = dict(inherited)
            if node.attrs.get("data-tag"):
                tags.append(node.attrs["data-tag"])
            flags = {"b": BOLD, "strong": BOLD, "i": ITALIC, "em": ITALIC,
                     "u": UNDERLINE, "s": STRIKE, "del": STRIKE, "strike": STRIKE}
            if node.tag in flags:
                formatting[flags[node.tag]] = "true"
            for declaration in node.attrs.get("style", "").split(";"):
                name, separator, value = declaration.partition(":")
                if not separator:
                    continue
                name, value = name.strip().lower(), value.strip()
                if name in {"color", "background-color"}:
                    color = textcolor.normalize(value)
                    if color:
                        rgb = bytes.fromhex(color.lstrip("#"))
                        formatting[COLOR if name == "color" else HIGHLIGHT] = str(int.from_bytes(rgb, "little"))
                elif name == "font-weight" and value == "bold":
                    formatting[BOLD] = "true"
                elif name == "font-style" and value == "italic":
                    formatting[ITALIC] = "true"
                elif name == "text-decoration":
                    if "underline" in value:
                        formatting[UNDERLINE] = "true"
                    if "line-through" in value:
                        formatting[STRIKE] = "true"
            if node.tag is None:
                append(re.sub(r"[\t\r\n ]+", " ", node.text or ""), formatting)
                return
            if node.tag == "br":
                append("\x0b", formatting)
                return
            if node.tag == "a":
                destination = node.attrs.get("href", "")
                if any(character in destination for character in ('"', "\r", "\n")):
                    raise WebError("OneNote cannot encode this list hyperlink")
                append('\ufddfHYPERLINK "%s"' % destination,
                       {HYPERLINK: "true", HIDDEN: "true", LINK_PROTECTED: "true"})
                formatting.update({HYPERLINK: "true", LINK_PROTECTED: "true"})
            elif node.tag not in {"p", "li", "span", "b", "strong", "i", "em", "u", "s", "del", "strike"}:
                raise WebError("This list contains content the native text writer cannot encode")
            for child in node.children:
                visit(child, formatting)

        visit(node, {FONT: "Calibri", FONT_SIZE: "22"})
        if not runs:
            runs = [("", {FONT: "Calibri", FONT_SIZE: "22"})]
        indices, position = [], 0
        for value, _ in runs[:-1]:
            position += len(value.encode("utf-16-le")) // 2
            indices.append(str(position))
        values = {TEXT: "".join(value for value, _ in runs),
                  RUN_FORMATTING: ",".join(reference(self.format(formatting)) for _, formatting in runs),
                  RUN_INDEX: ",".join(indices), MODIFIED: self.stamp,
                  SPACE_BEFORE: "0", SPACE_AFTER: "0"}
        if tags:
            states = []
            for tag in dict.fromkeys(tags):
                name = tag.removesuffix(":completed")
                if name not in TAG_DEFINITIONS:
                    raise WebError("OneNote returned an unsupported note tag")
                kind, shape, label = TAG_DEFINITIONS[name]
                definition_values = {TAG_TYPE: str(kind), TAG_SHAPE: str(shape), TAG_LABEL: label,
                                     TAG_STATUS: "0", TAG_SCHEMA: "0"}
                if name in {"remember-for-later", "definition"}:
                    # These two tags highlight their text: yellow and green.
                    highlight = "65535" if name == "remember-for-later" else "65280"
                    definition_values.update({TAG_TEXT_COLOR: "0", TAG_HIGHLIGHT: highlight})
                definition = self.create(TAG_DEFINITION, definition_values)
                checked = tag.endswith(":completed") or not name.startswith("to-do")
                state = [TAG_CHECKED, "1" if checked else "0", TAG_CREATED, self.stamp,
                         TAG_COMPLETED, self.stamp if checked else "0", TAG_DEFINITION_REF, reference(definition)]
                states.append(json.dumps(state, separators=(",", ":")))
            values[TAG_STATES] = json.dumps({"PropertyId": TAG_STATE, "Values": states}, separators=(",", ":"))
        return values

    def element(self, row, previous):
        identifier = row.element
        if identifier:
            obj = self.page.objects[identifier]
            if obj.get("ClassId") != ELEMENT:
                raise WebError(CHANGED)
            if previous is None or previous.key() != row.key():
                contents = references(properties(obj).get(CONTENT, ""))
                if len(contents) != 1 or self.page.objects.get(contents[0], {}).get("ClassId") != RICH_TEXT:
                    raise WebError("The changed list text has no independent text object")
                self.update(contents[0], self.rich_text(row.node), (ASCII_TEXT, TAG_STATES))
        else:
            content = self.create(RICH_TEXT, self.rich_text(row.node))
            identifier = self.create(ELEMENT, {CHILD_LEVEL: "1", CONTENT: reference(content), MODIFIED: self.stamp})
            row.element = identifier
        if row.depth:
            props = properties(self.updates.get(identifier, self.page.objects.get(identifier)))
            markers = references(props.get(LIST_NODES, ""))
            if len(markers) > 1:
                raise WebError("OneNote returned more than one marker for this list item")
            values = {LIST_FORMAT: MARKERS[row.style]}
            if row.start:
                values[LIST_RESTART] = str(row.start)
            if not markers:
                values[LIST_FONT if row.style in liststyles.BULLETS else FONT] = "Calibri"
                marker = self.create(NUMBER, values)
                self.update(identifier, {LIST_NODES: reference(marker)})
            elif previous is None or (previous.style, previous.start) != (row.style, row.start):
                self.update(markers[0], values, () if row.start else (LIST_RESTART,))
        elif previous is not None and previous.depth:
            self.update(identifier, {}, (LIST_NODES,))
        return identifier

    def forest(self, content, level):
        """Outline elements at one level, with deeper runs under their parent."""
        result, index = [], 0
        while index < len(content):
            row = content[index]
            if row.depth == level:
                result.append(row.element)
                self.update(row.element, {CHILD_LEVEL: "1"}, (CHILDREN,))
                index += 1
                continue
            end = index + 1
            while end < len(content) and content[end].depth > level:
                end += 1
            deeper = min(item.depth for item in content[index:end])
            nested = self.forest(content[index:end], deeper)
            if result and content[index - 1].depth == level:
                distance = deeper - level
                if distance > 31:
                    nested = [self.group(nested, distance - 1)]
                    distance = 1
                self.update(result[-1], {CHILD_LEVEL: str(distance),
                                         CHILDREN: ",".join(reference(item) for item in nested)})
            else:
                result.append(self.group(nested, deeper - level))
            index = end
        return result

    def group(self, content, level):
        # The native field is 1..31 for one edge, not a maximum depth.
        while level > 31:
            content = [self.create(GROUP, {CHILD_LEVEL: "31",
                                           CHILDREN: ",".join(reference(item) for item in content), MODIFIED: self.stamp})]
            level -= 31
        return self.create(GROUP, {CHILD_LEVEL: str(level),
                                   CHILDREN: ",".join(reference(item) for item in content), MODIFIED: self.stamp})

    def outline(self, identifier, content):
        result, index = [], 0
        while index < len(content):
            if not content[index].depth:
                result.append(content[index].element)
                if content[index].node.tag in {"p", "br"}:
                    self.update(content[index].element, {}, (CHILDREN,))
                index += 1
                continue
            end = index + 1
            while end < len(content) and content[end].depth and content[end].group == content[index].group:
                end += 1
            level = min(row.depth for row in content[index:end])
            nested = self.forest(content[index:end], level)
            result.append(self.group(nested, level))
            index = end
        self.update(identifier, {CHILD_LEVEL: "1", CHILDREN: ",".join(reference(item) for item in result)})


def plan(current, desired, page):
    """Translate changed HTML outlines, retaining matched elements and content."""
    old_tree, new_tree = parse(current), parse(desired)
    old_outlines = {node.attrs["id"]: node for node in walk(old_tree)
                    if node.tag == "div" and node.attrs.get("id", "").startswith("div:")}
    new_outlines = {node.attrs["id"]: node for node in walk(new_tree)
                    if node.tag == "div" and node.attrs.get("id", "").startswith("div:")}
    if old_outlines.keys() != new_outlines.keys():
        raise WebError("The native list save must preserve this page's outlines")
    affected = [key for key in old_outlines if serialize(old_outlines[key], True) != serialize(new_outlines[key], True)]
    before, after, scopes = [], [], []
    for key in affected:
        identifier = object_id(key)
        if page.objects.get(identifier, {}).get("ClassId") != OUTLINE:
            raise WebError(CHANGED)
        original, updated = rows(old_outlines[key]), rows(new_outlines[key])
        blanks = [item for item in page.descendants(identifier)
                  if page.objects[item].get("ClassId") == ELEMENT and page.blank(item)
                  and not properties(page.objects[item]).get(LIST_NODES)]
        bare = [row for row in original if row.node.tag == "br"]
        if len(blanks) == len(bare):
            for row, item in zip(bare, blanks):
                row.element = item
        for row in original:
            if row.node.attrs.get("id"):
                row.element = page.element(row.node.attrs["id"])
                verify_text(page, row)
        represented = {row.element for row in original if row.element}
        for item in page.descendants(identifier):
            obj = page.objects[item]
            if obj.get("ClassId") != ELEMENT or item in represented:
                continue
            props = properties(obj)
            contents = references(props.get(CONTENT, ""))
            if (props.get(LIST_NODES) or any(page.objects.get(content, {}).get("ClassId") != RICH_TEXT
                    or properties(page.objects[content]).get(TEXT) not in (None, "", "\x0b")
                    or properties(page.objects[content]).get(ASCII_TEXT) for content in contents)):
                raise WebError("The list save could not account for every existing outline element")
        before.extend(original)
        after.extend(updated)
        scopes.append((identifier, updated))
    existing = {row.node.attrs.get("id"): row for row in before if row.node.attrs.get("id")}
    used, previous = set(), {}
    for row in after:
        original = existing.get(row.node.attrs.get("id"))
        if original is not None and original.element:
            row.element = original.element
            used.add(row.element)
            previous[row.element] = original
    # Bare breaks have no Graph identity. Their requested count is exact,
    # but identical empty lines cannot identify a moved native object.
    old_remaining = [row for row in before if row.element and row.element not in used and row.key()]
    new_remaining = [row for row in after if not row.element and row.key()]
    try:
        aligned = align(old_remaining, new_remaining, lambda row: row.key())
    except AmbiguousAlignment as error:
        raise WebError(str(error)) from error
    for span in aligned:
        for old, new in zip(old_remaining[span.before_start:span.before_end], new_remaining[span.after_start:span.after_end]):
            if old.element not in used and (old.node.tag in {"li", "p", "br"} and new.node.tag in {"li", "p", "br"}
                                           or old.key() == new.key()):
                new.element = old.element
                previous[new.element] = old
                used.add(new.element)
    writer = Writer(page)
    for row in after:
        writer.element(row, previous.get(row.element))
    for identifier, content in scopes:
        writer.outline(identifier, content)
    validate(writer, scopes)
    return list(writer.updates.values())


def validate(writer, scopes):
    """Reject an incomplete move, shared child or cycle before any write."""
    objects = dict(writer.page.objects, **writer.updates)
    seen = set()

    def visit(identifier, depth):
        if identifier in seen or identifier not in objects:
            raise WebError("The proposed list save has an ambiguous outline hierarchy")
        seen.add(identifier)
        obj = objects[identifier]
        props = properties(obj)
        content = [(identifier, depth)] if obj["ClassId"] == ELEMENT else []
        descendants = references(props.get(CHILDREN, ""))
        if descendants:
            level = int(props[CHILD_LEVEL])
            if not 1 <= level <= 31:
                raise WebError("The proposed list indentation is invalid")
            for child in descendants:
                content.extend(visit(child, depth + level))
        return content

    for identifier, content in scopes:
        actual = visit(identifier, 0)
        expected = [(row.element, row.depth + 1 if row.depth else 1) for row in content]
        if actual != expected:
            raise WebError("The proposed list save did not preserve every item and its indentation")
