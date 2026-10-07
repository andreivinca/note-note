"""Remove the blank lines Graph exports without an update target.

OneNote stores a blank line as an outline element holding one empty rich
text object. Graph exports it as a bare <br/> without an ID, so no Graph
command can remove it. OneNote's web client removes the element from its
parent's child list; this does the same through the web revision service.
Only an exact join with the Graph HTML the save planned against may be
written, against the page revision just read. See docs/onenote-blank-lines.md.
"""
import copy
import re
import uuid

import page_order
from page_order import CHILDREN, properties, references
from web_session import WebError

ELEMENT = 0x6000D
RICH_TEXT = 0x6000E
CONTENT = 0x24001C1F
TEXT = 0x1C001C22
ASCII_TEXT = 0x1C003498
# OneNote clients store a blank line's text as nothing, or leave it out;
# Graph input stores a line break.
BLANK_TEXTS = (None, "", "\x0b")
GENERATED_ID = re.compile(r"[a-z0-9]+:\{([0-9A-Fa-f-]{36})\}\{([0-9]+)\}")
CHANGED = "The blank lines changed in OneNote; reload the page and try again"


class Page:
    """A page revision's elements, and which element owns each object."""

    def __init__(self, state):
        self.objects, self.roots = page_order.latest_objects(state)
        self.owners, self.parents = {}, {}
        for identifier, obj in self.objects.items():
            props = properties(obj)
            if obj.get("ClassId") == ELEMENT:
                for content in references(props.get(CONTENT, "")):
                    self.owners[content] = identifier
            for child in references(props.get(CHILDREN, "")):
                if child in self.parents:
                    raise WebError("Microsoft returned an element with two parents")
                self.parents[child] = identifier

    def identity(self):
        """The page's client ID, from the cell's own page metadata."""
        found = [self.objects[identifier] for identifier in self.roots.values()
                 if self.objects.get(identifier, {}).get("ClassId") == page_order.PAGE_METADATA]
        if len(found) != 1:
            raise WebError("Microsoft returned a page without its identity")
        try:
            return str(uuid.UUID(properties(found[0])[page_order.ENTITY_GUID]))
        except (KeyError, ValueError) as error:
            raise WebError("Microsoft returned an invalid page identity") from error

    def element(self, generated_id):
        """The element a Graph ID names: itself, or the one holding that content."""
        match = GENERATED_ID.fullmatch(generated_id)
        if not match:
            raise WebError("OneNote returned an unexpected element ID")
        reference = "%s|%d" % (uuid.UUID(match[1]), int(match[2]))
        if self.objects.get(reference, {}).get("ClassId") == ELEMENT:
            return reference
        if reference not in self.owners:
            raise WebError(CHANGED)
        return self.owners[reference]

    def children(self, parent):
        return references(properties(self.objects[parent]).get(CHILDREN, ""))

    def blank(self, element):
        """One empty line: no child elements and only blank text."""
        props = properties(self.objects[element])
        contents = references(props.get(CONTENT, ""))
        if references(props.get(CHILDREN, "")) or len(contents) != 1:
            return False
        text = self.objects.get(contents[0], {})
        if text.get("ClassId") != RICH_TEXT:
            return False
        values = properties(text)
        return values.get(TEXT) in BLANK_TEXTS and not values.get(ASCII_TEXT)


def updated_parents(page, runs):
    """The parent objects to write, each without its removed blank lines.

    A run's neighbours must share one parent, with exactly the run's number
    of blank lines between them. A <br/> beside a list can be the blank
    text of the element the list hangs under; that element is not blank.
    """
    removed = {}
    for run in runs:
        first, last = page.element(run.before), page.element(run.after)
        parent = page.parents.get(first)
        if parent is None or page.parents.get(last) != parent:
            raise WebError(CHANGED)
        children = page.children(parent)
        between = children[children.index(first) + 1:children.index(last)]
        if len(between) != run.count or not all(page.blank(element) for element in between):
            raise WebError(CHANGED)
        removed.setdefault(parent, set()).update(between[index] for index in run.removed)
    updated = []
    for parent, elements in removed.items():
        obj = copy.deepcopy(page.objects[parent])
        values = obj["Properties"]
        kept = [child for child in page.children(parent) if child not in elements]
        values[values.index(CHILDREN) + 1] = ",".join("{%s}{%s}" % tuple(child.split("|")) for child in kept)
        updated.append(obj)
    return updated


def remove(session, client_id, runs):
    """One conditional page revision, confirmed by reading the page back."""
    cell = page_order.page_cell(session.read_section(), client_id)
    state = session.read(cell)
    page = Page(state)
    if page.identity() != client_id:
        raise WebError("The page's revisions could not be verified; refresh the section")
    parents = updated_parents(page, runs)
    session.write(cell, state, parents)
    confirmed = Page(session.read(cell))
    for parent in parents:
        expected = references(properties(parent)[CHILDREN])
        if parent["ObjectId"] not in confirmed.objects or confirmed.children(parent["ObjectId"]) != expected:
            raise WebError("OneNote did not confirm the removed blank lines; reload the page")
