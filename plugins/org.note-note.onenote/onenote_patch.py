"""Translate shared sequence alignment into identity-preserving Graph edits.

Planning has no I/O. Unsupported edits and invalid simulations are errors;
neither authorizes a broader replacement. Graph capabilities are documented
at https://learn.microsoft.com/en-us/graph/onenote-update-page. Graph has no
target for a blank line; the plan lists those removals separately, for the
caller to make before any Graph command (docs/onenote-blank-lines.md).
Graph cannot move a list item either: the plan names the page OneNote's
native writer must make first (list_edits.py), and the caller plans again
against the page that writer leaves.
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
MEDIA = {"img", "object", "table"}


class UnsupportedEdit(ValueError):
    """The available Graph targets cannot preserve this edit's neighbours."""


class InvalidPlan(ValueError):
    """A planned operation violated the document or preservation contract."""


@dataclass(frozen=True)
class BlankLines:
    """Consecutive bare breaks between two siblings that have generated IDs.

    OneNote exports each blank line as a <br/> without an ID, so no Graph
    command can remove one. The caller removes the `removed` positions of
    this run before any Graph command runs.
    """
    before: str
    after: str
    count: int
    removed: tuple


@dataclass(frozen=True)
class Plan:
    commands: tuple
    simulated: str
    blank_lines: tuple
    native: str | None     # the page the native writer makes before any of the commands


def parse(source):
    builder = TreeBuilder()
    builder.feed(source)
    return builder.root


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def outside_tables(node):
    """`node` and its descendants, except those inside a table."""
    yield node
    if node.tag != "table":
        for child in node.children:
            yield from outside_tables(child)


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


def role(node):
    """The part of a list node's identity that its text does not carry.

    A node renders out of context, so an item and the same item wrapped one
    level deeper both read "- Two". Graph cannot move an item: the same text
    in another list role is another element, never an unchanged one.
    """
    return node.tag if node.tag in LISTS | {"li"} else ""


def identity(node):
    key = text_key(text(node))
    if key is None:
        return None
    return role(node), key


def unchanged(old, new):
    """Whether `new` is `old` as it stands: the same text in the same list role."""
    return role(old) == role(new) and text(old) == text(new)


def list_levels(nodes, depth=0, kind=""):
    """Each item's depth and family, or None for a span with other blocks."""
    result = []
    for node in nodes:
        if node.tag in LISTS:
            nested = list_levels(children(node), depth + 1, node.tag)
        elif node.tag == "li":
            result.append((depth, kind))
            nested = list_levels([child for child in node.children if child.tag in LISTS], depth, kind)
        elif node.tag in LAYOUT and not text(node):
            continue
        else:
            return None
        if nested is None:
            return None
        result.extend(nested)
    return result


def list_children(original, desired):
    """Keep the source's placement of sublists while aligning its items.

    OneNote exports sublists either inside the preceding item or beside it.
    The writer uses the latter. A presentation difference must not become a
    deletion and reinsertion of unchanged descendants.
    """
    nested = any(item.tag == "li" and any(child.tag in LISTS for child in item.children)
                 for item in original.children)
    if not nested:
        return children(desired)
    result = []
    for node in copy.deepcopy(children(desired)):
        if node.tag in LISTS and result and result[-1].tag == "li":
            result[-1].children.append(node)
        else:
            result.append(node)
    return result


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
        self.blank_runs = {}
        self.removed = set()
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
        if len(after) > len(before) and all(unchanged(old, new) for old, new in zip(before, after)):
            for original in before:
                self.retain(original)
            self.insert(after[len(before):], before, len(before), container)
            return
        for span in align(before, after, identity):
            old = before[span.before_start:span.before_end]
            new = after[span.after_start:span.after_end]
            if self.relevel_list(old, new):
                continue
            shared = min(len(old), len(new))
            pending = []
            for position, (original, desired) in enumerate(zip(old, new)):
                if original.tag == "br" and desired.tag != "br":
                    # Text typed on a blank line. The break has no target to
                    # replace: remove it and insert the text in its place.
                    self.remove_break(original)
                    pending.append(desired)
                    continue
                if pending:
                    self.insert(pending, before, span.before_start + position, container)
                    pending = []
                self.update(original, desired)
            for original in old[shared:]:
                # Deleting the first/last content can turn an internal break
                # into a boundary break. Like the breaks already excluded by
                # document_elements(), it can stay in OneNote without changing
                # the saved document. Internal gaps have no Graph target.
                boundary = container.tag in LAYOUT | {"root"} and span.after_end in (0, len(after))
                if original.tag == "br" and boundary:
                    self.retain(original)
                    continue
                if original.tag == "br":
                    self.remove_break(original)
                    continue
                # Graph deletions use empty replacements. A cell needs an
                # editable paragraph left behind for subsequent typing.
                empty = "<p><br/></p>" if container.tag in {"td", "th"} else "<div></div>"
                self.replacements.append({"target": target(original), "action": "replace", "content": empty})
            if pending or new[shared:]:
                self.insert(pending + list(new[shared:]), before, span.before_end, container)

    def relevel_list(self, old, new):
        # Graph has no move operation. When an item's depth changes, replace
        # only that changed span. Equal siblings outside it retain their IDs.
        # Every item in the span must change depth or family. If even one
        # stays at its level, recurse normally to preserve its identity.
        if (not old or not new or [node.tag for node in old] == [node.tag for node in new]
                or not any(node.tag in LISTS for node in old + new)):
            return False
        before, after = list_levels(old), list_levels(new)
        if not before or not after or len(before) != len(after) or any(a == b for a, b in zip(before, after)):
            return False
        content = "".join(serialize(node) for node in new)
        for node in old:
            if node.tag in LAYOUT:
                self.retain(node)
                continue
            self.replacements.append({"target": target(node), "action": "replace", "content": content})
            content = "<div></div>"
        return True

    def remove_break(self, node):
        """Record a blank line no Graph command can remove.

        Its run of consecutive breaks is identified by the generated IDs of
        the siblings around it.
        """
        siblings = children(self.parents[id(node)])
        index = next(position for position, child in enumerate(siblings) if child is node)
        start, end = index, index + 1
        while start > 0 and siblings[start - 1].tag == "br":
            start -= 1
        while end < len(siblings) and siblings[end].tag == "br":
            end += 1
        before = siblings[start - 1].attrs.get("id", "") if start > 0 else ""
        after = siblings[end].attrs.get("id", "") if end < len(siblings) else ""
        if not before or not after:
            raise UnsupportedEdit("OneNote supplied no editable target for this br element")
        removed = self.blank_runs.setdefault((before, after), (end - start, set()))[1]
        removed.add(index - start)
        self.removed.add(id(node))

    def neighbours(self, before, index):
        """Insertion anchors around `index`. Removed breaks are not anchors."""
        candidates = []
        following = index
        while following < len(before) and id(before[following]) in self.removed:
            following += 1
        if following < len(before):
            candidates.append((before[following], "before"))
        preceding = index - 1
        while preceding >= 0 and id(before[preceding]) in self.removed:
            preceding -= 1
        if preceding >= 0:
            candidates.append((before[preceding], "after"))
        return candidates

    def insert(self, additions, before, index, container):
        content = "".join(serialize(node) for node in additions)
        candidates = self.neighbours(before, index)
        command = None
        for node, position in candidates:
            if node.tag in LISTS:
                command = self.insert_at_layout_boundary(node, position, additions)
                if command is not None:
                    self.insertions.append(command)
                    return
                continue
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
        if command is None:
            # Only lists around it. A list's ID can name a container Graph
            # cannot find; the native writer carries this one (Plan.native).
            for node, position in candidates:
                identifier = target_identifier(node)
                if identifier:
                    command = {"target": identifier, "action": "insert", "position": position}
                    break
        if command is None and not before and container.tag in LISTS | {"body", "div"}:
            identifier = container.attrs.get("id")
            if container.tag != "body" and not identifier:
                raise UnsupportedEdit("OneNote supplied no target for this empty container")
            command = {"target": identifier or "body", "action": "append"}
        if command is None:
            raise UnsupportedEdit("OneNote supplied no insertion target at this position")
        self.insertions.append(dict(command, content=content))

    def insert_at_layout_boundary(self, node, position, additions):
        """Insert at a layout boundary using the layout's own Graph target.

        A native outline can expose a synthetic list ID Graph cannot locate;
        a phone attachment may have no ID at all. The containing div supports
        adding first/last children without replacing any existing content.
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
        if unchanged(old, new):
            self.retain(old)
            return
        if role(old) != role(new) and self.relevel_list([old], [new]):
            # An item moved to another level or family, in a span whose
            # other items changed in their own ways.
            return
        if old.tag == new.tag and old.tag in LISTS:
            self.retain(old, subtree=False)
            self.sequence(children(old), list_children(old, new), old)
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
            original = [child for child in children(old) if child.tag not in LISTS]
            if len(original) != 1 or original[0].tag != "p" or not target_identifier(original[0]):
                raise UnsupportedEdit("this list text has no separate target from its nested list; edit it in OneNote")
            paragraph = Node("p", {key: value for key, value in original[0].attrs.items() if key != "id"})
            paragraph.children = [child for child in new.children if child.tag not in LISTS]
            self.update(original[0], paragraph)
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
        # Blank lines are removed first. Insertions then use original
        # anchors, which still exist before any replacements. Simulate
        # exactly that same order.
        commands = tuple(self.insertions + self.replacements)
        blank_lines = tuple(BlankLines(before, after, count, tuple(sorted(removed)))
                            for (before, after), (count, removed) in self.blank_runs.items())
        simulated = simulate(without_blank_lines(self.tree, blank_lines), commands)
        by_id = {node.attrs["id"]: node for node in walk(simulated) if node.attrs.get("id")}
        for identifier, (tag, attrs, content) in self.retained.items():
            kept = by_id.get(identifier)
            if kept is None or kept.tag != tag or kept.attrs != attrs:
                raise InvalidPlan("an unchanged element lost its identity")
            if content is not None and serialize(kept, keep_ids=True) != content:
                raise InvalidPlan("an unchanged element was modified")
        return Plan(commands, serialize(simulated, keep_ids=True), blank_lines, self.native(commands, blank_lines))

    def native(self, commands, blank_lines):
        """The page OneNote's native writer must make first, or None.

        Graph cannot move a list item, and a list's ID can name a container
        it cannot find (list_edits.py). When a command moves an outline's
        list items, every command on its lists goes to the native writer,
        which also edits their text in place. A table is one element to that
        writer, so a list in a table cell stays Graph's.

        The native writer then also removes the blank lines, as it rewrites
        their outlines anyway; one beside a list is its to remove in any case,
        since blank_lines.py cannot name a list as a neighbour. Media cannot
        be written natively: a paragraph holding a no-break space stands where
        each goes, which Graph can target and the next plan replaces.
        """
        # What the outlines' lists hold, by ID; and the targets inside tables.
        scope = {node.attrs["id"]: node for outline_list in outside_tables(self.tree) if outline_list.tag in LISTS
                 for node in outside_tables(outline_list) if node.attrs.get("id")}
        cells = {target_identifier(node) for table in walk(self.tree) if table.tag == "table"
                 for node in list(walk(table))[1:]} - {""}
        carried = []
        moves = any(run.before in scope or run.after in scope for run in blank_lines)
        for command in commands:
            content = parse(command["content"])
            lists = any(node.tag in LISTS for node in outside_tables(content))
            target = scope.get(command["target"])
            if command["target"] in cells or (target is None and not lists):
                continue
            # Only an item's text replaced in place leaves its list as it was.
            moves = moves or lists or command["action"] != "replace" or any(node.tag in LISTS for node in walk(target))
            content.children = [parse("<p>\u00a0</p>").children[0] if node.tag in MEDIA else node
                                for node in content.children]
            carried.append(dict(command, content=serialize(content)))
        if not moves:
            return None
        return serialize(simulate(without_blank_lines(self.tree, blank_lines), carried), keep_ids=True)


def without_blank_lines(tree, blank_lines):
    """A copy of `tree` without the planned blank lines, as the caller removes them."""
    tree = copy.deepcopy(tree)
    for run in blank_lines:
        parents = [node for node in walk(tree)
                   if any(child.attrs.get("id") == run.before for child in node.children)]
        if len(parents) != 1:
            raise InvalidPlan("a blank line has no unique preceding element")
        siblings = children(parents[0])
        start = next(index for index, child in enumerate(siblings) if child.attrs.get("id") == run.before) + 1
        breaks = siblings[start:start + run.count]
        following = siblings[start + run.count] if start + run.count < len(siblings) else None
        if (len(breaks) != run.count or any(node.tag != "br" for node in breaks)
                or following is None or following.attrs.get("id") != run.after):
            raise InvalidPlan("blank lines no longer separate their neighbouring elements")
        removed = {id(breaks[index]) for index in run.removed}
        parents[0].children = [child for child in parents[0].children if id(child) not in removed]
    return tree


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
    if len(after) >= len(projected) and all(unchanged(old, new) for old, new in zip(projected, after)):
        matches = dict(enumerate(range(len(projected))))
    else:
        for span in align(projected, after, identity):
            if span.kind != "equal":
                continue
            for old, new in zip(range(span.before_start, span.before_end), range(span.after_start, span.after_end)):
                if unchanged(projected[old], after[new]):
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
