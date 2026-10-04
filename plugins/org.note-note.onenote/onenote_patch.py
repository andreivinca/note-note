"""Translate shared sequence alignment into identity-preserving Graph edits.

Planning has no I/O. Unsupported edits and invalid simulations are errors;
neither authorizes a broader replacement. Graph capabilities are documented
at https://learn.microsoft.com/en-us/graph/onenote-update-page.
"""
import copy
from dataclasses import dataclass
import html

from notemerge import AmbiguousAlignment, align, text_key
from onenote_md import Converter, Node, TreeBuilder
import htmltables

REPLACEABLE = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "img", "object"}
LISTS = {"ul", "ol"}
LAYOUT = {"html", "body", "div"}


class UnsupportedEdit(ValueError):
    """The available Graph targets cannot preserve this edit's neighbours."""


class InvalidPlan(ValueError):
    """A planned operation violated the document or preservation contract."""


@dataclass(frozen=True)
class Plan:
    commands: tuple
    simulated: str


def parse(source):
    builder = TreeBuilder()
    builder.feed(source)
    return builder.root


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def serialize(node, keep_ids=False):
    if node.tag is None:
        return html.escape(node.text or "", quote=False)
    content = "".join(serialize(child, keep_ids) for child in node.children)
    if node.tag == "root":
        return content
    attrs = "".join(' %s="%s"' % (key, html.escape(value or "", quote=True))
                    for key, value in node.attrs.items() if keep_ids or key != "id")
    if node.tag in TreeBuilder.VOID:
        return "<%s%s/>" % (node.tag, attrs)
    return "<%s%s>%s</%s>" % (node.tag, attrs, content, node.tag)


def children(node):
    return [child for child in node.children
            if child.tag not in {"head", "title", "meta", "style"}
            and (child.tag is not None or (child.text or "").strip())]


def elements(root):
    """Flatten layout wrappers, leaving lists and tables as nested scopes."""
    result = []
    for node in children(root):
        if node.tag in LAYOUT:
            result.extend(elements(node))
        else:
            result.append(node)
    return result


def document_elements(root):
    """Match the converter's omission of boundary line breaks.

    OneNote clients leave bare breaks around page content, sometimes in a
    separate empty layout div. They have no update target and the editor
    does not keep them. Exclude them from alignment, leaving the original
    tree intact; breaks between document blocks still belong to the note.
    """
    result = elements(root)
    start, end = 0, len(result)
    while start < end and result[start].tag == "br":
        start += 1
    while end > start and result[end - 1].tag == "br":
        end -= 1
    return result[start:end]


def content_converter():
    # Graph resources identify attachments during planning. Instance IDs
    # belong to the editor/merge boundary and need not exist on legacy HTML.
    return Converter(lambda src, width: src, lambda src, title: src,
                     lambda src, local, title, identifier: (local, ""))


def text(node):
    converter = content_converter()
    converter.block(node)
    return converter.result()


def identity(node):
    return text_key(text(node))


def target_identifier(node):
    value = node.attrs.get("id", "")
    if node.tag in REPLACEABLE and value.startswith(node.tag + ":"):
        return value
    if node.tag in {"img", "object"} and node.attrs.get("data-id"):
        return "#" + node.attrs["data-id"]
    return ""


def target(node):
    value = target_identifier(node)
    if value:
        return value
    raise UnsupportedEdit("OneNote supplied no editable target for this %s element" % (node.tag or "text"))


def replacement(old, new):
    if identity(old) != identity(new):
        return new
    # Only checkbox state differs. The carrier may be the paragraph itself
    # or an inline span inside a list item. Preserve its original HTML and
    # tag kind, including formatting that Markdown cannot represent.
    updated = copy.deepcopy(old)
    original = checkbox_carriers(updated)
    desired = checkbox_carriers(new)
    if len(original) != 1 or len(desired) != 1:
        raise UnsupportedEdit("this checkbox has no unique state carrier")
    carrier = original[0]
    tag = carrier.attrs["data-tag"].removesuffix(":completed")
    if desired[0].attrs["data-tag"].endswith(":completed"):
        tag += ":completed"
    carrier.attrs["data-tag"] = tag
    if text(updated) != text(new):
        raise UnsupportedEdit("this checkbox state cannot be changed without altering its content")
    return updated


def checkbox_carriers(node):
    return [child for child in walk(node) if child.attrs.get("data-tag", "").startswith("to-do")]


class _Planner:
    def __init__(self, tree):
        self.tree = tree
        self.insertions = []
        self.replacements = []
        self.retained = {}
        self.parents = {id(child): parent for parent in walk(tree) for child in parent.children}

    def retain(self, node, subtree=True):
        for original in walk(node) if subtree else (node,):
            identifier = original.attrs.get("id")
            if identifier:
                content = serialize(original, keep_ids=True) if subtree else None
                self.retained[identifier] = (original.tag, dict(original.attrs), content)

    def sequence(self, before, after, container):
        # An unchanged prefix has no identities to disambiguate, even when
        # appended content repeats an existing heading or checklist label.
        # Preserve every original node and use the last one as the anchor.
        if len(after) > len(before) and all(text(old) == text(new) for old, new in zip(before, after)):
            for original in before:
                self.retain(original)
            self.insert(after[len(before):], before, len(before), container)
            return
        for span in align(before, after, identity):
            old = before[span.before_start:span.before_end]
            new = after[span.after_start:span.after_end]
            shared = min(len(old), len(new))
            for original, desired in zip(old, new):
                self.update(original, desired)
            for original in old[shared:]:
                # Deleting the first/last content can turn an internal break
                # into a boundary break. Like the breaks already excluded by
                # document_elements(), it can stay in OneNote without changing
                # the saved document. Internal gaps still require a target.
                boundary = container.tag in LAYOUT | {"root"} and span.after_end in (0, len(after))
                if original.tag == "br" and boundary:
                    self.retain(original)
                    continue
                # Graph deletions use empty replacements. A cell needs an
                # editable paragraph left behind for subsequent typing.
                empty = "<p><br/></p>" if container.tag in {"td", "th"} else "<div></div>"
                self.replacements.append({"target": target(original), "action": "replace", "content": empty})
            if new[shared:]:
                self.insert(new[shared:], before, span.before_end, container)

    def insert(self, additions, before, index, container):
        content = "".join(serialize(node) for node in additions)
        candidates = []
        if index < len(before):
            candidates.append((before[index], "before"))
        if index > 0:
            candidates.append((before[index - 1], "after"))
        command = None
        for node, position in candidates:
            identifier = target_identifier(node)
            if identifier:
                command = {"target": identifier, "action": "insert", "position": position}
                break
        if command is None:
            for node, position in candidates:
                command = self.insert_at_layout_boundary(node, position, additions)
                if command is not None:
                    self.insertions.append(command)
                    return
        if command is None and not before and container.tag in LISTS | {"body", "div"}:
            identifier = container.attrs.get("id")
            if container.tag != "body" and not identifier:
                raise UnsupportedEdit("OneNote supplied no target for this empty container")
            command = {"target": identifier or "body", "action": "append"}
        if command is None:
            raise UnsupportedEdit("OneNote supplied no insertion target at this position")
        self.insertions.append(dict(command, content=content))

    def insert_at_layout_boundary(self, node, position, additions):
        """A phone attachment may have no ID even with includeIDs=true.

        Its layout div supports adding first/last children by generated ID.
        Use that operation only at the corresponding content boundary; the
        original attachment and every other child stay intact.
        """
        parent = self.parents.get(id(node))
        while parent is not None and parent.tag in LAYOUT:
            if parent.tag == "div" and parent.attrs.get("id", "").startswith("div:"):
                contents = elements(parent)
                start, end = 0, len(contents)
                while start < end and contents[start].tag == "br":
                    start += 1
                while end > start and contents[end - 1].tag == "br":
                    end -= 1
                boundary = contents[start if position == "before" else end - 1] if start < end else None
                if boundary is node:
                    # Boundary breaks omitted on import become visible when
                    # content is added beyond them. Reuse the corresponding
                    # requested blank lines rather than adding them twice.
                    breaks = start if position == "before" else len(contents) - end
                    shared = additions[-breaks:] if position == "before" and breaks else additions[:breaks]
                    if len(shared) != breaks or any(item.tag != "br" for item in shared):
                        return None
                    inserted = additions[:-breaks] if position == "before" and breaks else additions[breaks:]
                    if not inserted:
                        return None
                    return {"target": parent.attrs["id"], "action": "append", "position": position,
                            "content": "".join(serialize(item) for item in inserted)}
            parent = self.parents.get(id(parent))
        return None

    def update(self, old, new):
        if text(old) == text(new):
            self.retain(old)
            return
        if old.tag == new.tag and old.tag in LISTS:
            self.retain(old, subtree=False)
            self.sequence(children(old), children(new), old)
            return
        if old.tag == new.tag == "li" and any(child.tag in LISTS for child in old.children + new.children):
            self.nested_item(old, new)
            return
        if old.tag == new.tag == "table":
            self.table(old, new)
            return
        # An inline recording shares its paragraph's Graph target. Replacing
        # that carrier is supported by the caller's bounded media upload;
        # independently editable paragraphs/lists/images must keep their IDs.
        if any(child.tag in REPLACEABLE - {"object"} for child in list(walk(old))[1:]):
            raise UnsupportedEdit("this restructure would replace nested elements; edit it in OneNote")
        self.replacements.append({"target": target(old), "action": "replace",
                                  "content": serialize(replacement(old, new))})

    def nested_item(self, old, new):
        def inline(item):
            holder = Node("li")
            holder.children = [child for child in item.children if child.tag not in LISTS]
            return text(holder)

        if inline(old) != inline(new):
            raise UnsupportedEdit("this list text has no separate target from its nested list; edit it in OneNote")
        self.retain(old, subtree=False)
        self.sequence([child for child in old.children if child.tag in LISTS],
                      [child for child in new.children if child.tag in LISTS], old)

    def table(self, old, new):
        # Graph cannot replace rows or cells. A cell's existing paragraph can
        # be edited without destroying the identities of the other cells.
        old_rows = list(htmltables.rows(old))
        new_rows = list(htmltables.rows(new))
        if len(old_rows) != len(new_rows):
            raise UnsupportedEdit("OneNote cannot change this table's rows without rebuilding it")
        if not any(child.tag in REPLACEABLE for child in list(walk(old))[1:]):
            self.inline_table(old, new_rows)
            return
        self.retain(old, subtree=False)
        converter = content_converter()
        for old_row, new_row in zip(old_rows, new_rows):
            old_cells = [node for node in children(old_row) if node.tag in {"td", "th"}]
            new_cells = [node for node in children(new_row) if node.tag in {"td", "th"}]
            if len(old_cells) != len(new_cells):
                raise UnsupportedEdit("OneNote cannot change this table's columns without rebuilding it")
            self.retain(old_row, subtree=False)
            for old_cell, new_cell in zip(old_cells, new_cells):
                desired = converter.rich_cell(new_cell)
                if converter.rich_cell(old_cell) == desired:
                    self.retain(old_cell)
                    continue
                content = children(old_cell)
                if not content or any(node.tag not in REPLACEABLE for node in content):
                    raise UnsupportedEdit("this table cell has no editable paragraph; edit it in OneNote")
                self.retain(old_cell, subtree=False)
                updated = children(new_cell)
                if not desired:
                    # An empty cell means its previous blocks were deleted.
                    # The renderer's blank paragraph is only a placeholder.
                    updated = []
                elif not any(node.tag in REPLACEABLE for node in updated):
                    paragraph = Node("p")
                    paragraph.children = new_cell.children
                    updated = [paragraph]
                self.sequence(content, updated, old_cell)

    def inline_table(self, old, new_rows):
        """A table containing only inline content is itself the editable unit.

        Legacy templates have spans and bare breaks directly inside cells.
        Graph cannot target those cells. Replace this table only when it has
        no nested paragraphs, lists, tables or images whose identities would
        be lost, copying the original layout and every unchanged cell.
        """
        updated = copy.deepcopy(old)
        converter = content_converter()
        for old_row, new_row in zip(htmltables.rows(updated), new_rows):
            old_cells = [node for node in children(old_row) if node.tag in {"td", "th"}]
            new_cells = [node for node in children(new_row) if node.tag in {"td", "th"}]
            if len(old_cells) != len(new_cells):
                raise UnsupportedEdit("OneNote cannot change this table's columns without rebuilding it")
            for old_cell, new_cell in zip(old_cells, new_cells):
                if converter.rich_cell(old_cell) == converter.rich_cell(new_cell):
                    continue
                content = copy.deepcopy(new_cell.children)
                if not any(child.tag in REPLACEABLE for child in content):
                    paragraph = Node("p")
                    paragraph.children = content
                    content = [paragraph]
                old_cell.children = content
        self.replacements.append({"target": target(old), "action": "replace", "content": serialize(updated)})

    def finish(self):
        # Insertions use original anchors, which still exist before any
        # replacements. Simulate exactly that same command order.
        commands = tuple(self.insertions + self.replacements)
        simulated = simulate(self.tree, commands)
        by_id = {node.attrs["id"]: node for node in walk(simulated) if node.attrs.get("id")}
        for identifier, (tag, attrs, content) in self.retained.items():
            kept = by_id.get(identifier)
            if kept is None or kept.tag != tag or kept.attrs != attrs:
                raise InvalidPlan("an unchanged element lost its identity")
            if content is not None and serialize(kept, keep_ids=True) != content:
                raise InvalidPlan("an unchanged element was modified")
        return Plan(commands, serialize(simulated, keep_ids=True))


def simulate(tree, commands):
    """Apply the public Graph operations, independently of the alignment."""
    tree = copy.deepcopy(tree)
    for command in commands:
        identifier = command["target"]
        if identifier == "body":
            bodies = [node for node in walk(tree) if node.tag == "body"]
            parent = bodies[0] if bodies else tree
            node = next((child for child in parent.children if child.tag == "div"), parent)
        else:
            attribute = "data-id" if identifier.startswith("#") else "id"
            value = identifier[1:] if attribute == "data-id" else identifier
            matches = [(parent, node) for parent in walk(tree) for node in parent.children
                       if node.attrs.get(attribute) == value]
            if len(matches) != 1:
                raise InvalidPlan("an operation targets a missing or repeated element")
            parent, node = matches[0]
        content = parse(command["content"]).children
        if command["action"] == "append":
            if command.get("position", "after") == "before":
                node.children[0:0] = content
            else:
                node.children.extend(content)
        else:
            position = parent.children.index(node)
            if command["action"] == "replace":
                parent.children[position:position + 1] = content
            elif command["action"] == "insert":
                position += int(command["position"] == "after")
                parent.children[position:position] = content
            else:
                raise InvalidPlan("unsupported operation")
    return tree


def preserve_projected(before, after, project):
    """Match the editor's representation back to its original source elements.

    A source table can display as a table followed by images, and whitespace
    can normalize on import. Only a complete, consecutive, unchanged projection
    permits retaining the source subtree. Changed projections still go through
    the ordinary target checks and the caller's whole-document validation.
    """
    projected, groups = [], []
    for original in before:
        start = len(projected)
        projected.extend(document_elements(parse(project(original))) or [original])
        groups.append((original, start, len(projected)))

    matches = {}
    if len(after) >= len(projected) and all(text(old) == text(new) for old, new in zip(projected, after)):
        matches = dict(enumerate(range(len(projected))))
    else:
        for span in align(projected, after, identity):
            if span.kind != "equal":
                continue
            for old, new in zip(range(span.before_start, span.before_end), range(span.after_start, span.after_end)):
                if text(projected[old]) == text(after[new]):
                    matches[old] = new

    retained = {}
    for original, start, end in groups:
        position = matches.get(start)
        if position is not None and all(matches.get(index) == position + index - start for index in range(start, end)):
            retained[position] = (original, end - start)

    result, index = [], 0
    while index < len(after):
        original, count = retained.get(index, (after[index], 1))
        result.append(original)
        index += count
    return result


def plan(current, desired, project=None):
    """Return a validated Plan, or raise UnsupportedEdit/InvalidPlan."""
    tree, desired_tree = parse(current), parse(desired)
    bodies = [node for node in walk(tree) if node.tag == "body"]
    body = bodies[0] if bodies else tree
    planner = _Planner(tree)
    try:
        before, after = document_elements(body), document_elements(desired_tree)
        if project is not None:
            after = preserve_projected(before, after, project)
        planner.sequence(before, after, body)
    except AmbiguousAlignment as error:
        raise UnsupportedEdit(str(error)) from error
    return planner.finish()
