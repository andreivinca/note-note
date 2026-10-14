"""Restore native list depth and paragraph boundaries omitted by Graph HTML.

Graph's list wrappers sometimes include following blank paragraphs and sibling
outline groups. Read the native ownership and indentation, keeping Graph's
inline text, formatting, attachments and generated item IDs.
"""
from onenote_md import Node
from onenote_patch import LISTS, children, parse, serialize, walk
from revision_objects import CHILDREN, properties, references
from web_session import WebError
from blank_lines import ELEMENT
from list_edits import CHILD_LEVEL, GROUP, LIST_NODES, OUTLINE, object_id, rows
import liststyles

OUTLINE_CONTAINERS = {OUTLINE, ELEMENT, GROUP}


def levels(objects, outline):
    result, groups, seen = {}, {}, set()

    def visit(identifier, depth, group):
        if identifier in seen:
            raise WebError("OneNote returned an ambiguous list hierarchy")
        seen.add(identifier)
        obj = objects.get(identifier, {})
        if obj.get("ClassId") not in OUTLINE_CONTAINERS:
            return
        props = properties(obj)
        for marker in references(props.get(LIST_NODES, "")):
            result[marker] = depth
            groups[marker] = group
        descendants = references(props.get(CHILDREN, ""))
        if descendants:
            try:
                level = int(props[CHILD_LEVEL])
            except (KeyError, ValueError) as error:
                raise WebError("OneNote returned an invalid list indentation") from error
            if not 1 <= level <= 31:
                raise WebError("OneNote returned an invalid list indentation")
            for child in descendants:
                root_group = child if identifier == outline and objects.get(child, {}).get("ClassId") == GROUP else group
                visit(child, depth + level, root_group)

    visit(outline, 0, outline)
    # An outline's first native level positions the list within the outline.
    # Direct items in older Graph pages may instead start at level one.
    origin = min(1, min(result.values()) - 1) if result else 0
    return {identifier: depth - origin for identifier, depth in result.items()}, groups


def restore(source, objects):
    tree = parse(source)
    for outline in [node for node in walk(tree) if node.tag == "div" and node.attrs.get("id", "").startswith("div:")]:
        if not any(node.tag in LISTS for node in walk(outline)):
            continue
        depths, groups = levels(objects, object_id(outline.attrs["id"]))
        content = rows(outline)
        owners = {}
        for node in walk(outline):
            if node.tag in LISTS:
                for child in children(node):
                    if child.tag == "li":
                        owners[child.attrs.get("id")] = node
        for row in content:
            if row.depth:
                marker = object_id(row.node.attrs.get("id", ""))
                if marker not in depths:
                    raise WebError("The list changed while its indentation was being read; reload the note")
                row.depth = depths[marker]
                row.group = groups[marker]
        result, stack, used, group = [], [], set(), None
        for row in content:
            if not row.depth:
                result.append(row.node)
                stack = []
                continue
            if row.group != group:
                stack = []
                group = row.group
            kind = "ol" if row.style in liststyles.NUMBERS else "ul"
            while len(stack) > row.depth:
                stack.pop()
            if len(stack) == row.depth and stack[-1].tag != kind:
                stack.pop()
            while len(stack) < row.depth:
                container = Node(kind)
                if stack:
                    stack[-1].children.append(container)
                else:
                    result.append(container)
                stack.append(container)
            container = stack[-1]
            # The Graph list that held the item gives its ID, style and start
            # to one rebuilt list, once: the item's own, or, below levels no
            # item opens, the outermost, where Graph showed the list before it
            # left those levels out.
            original = owners.get(row.node.attrs.get("id"))
            identifier = original.attrs.get("id") if original is not None else None
            identified = container
            if not any(child.tag == "li" for parent in stack[:-1] for child in parent.children):
                identified = stack[0]
            if identifier and identifier not in used and not identified.attrs.get("id"):
                identified.attrs.update(original.attrs)
                used.add(identifier)
            container.children.append(row.node)
        outline.children = result
    return serialize(tree, keep_ids=True)
