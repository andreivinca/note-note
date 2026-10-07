"""Reorder existing page series without touching page bodies or hierarchy.

Graph supplies page order, levels and public page identities. The web
revision service supplies the section's current page-series references.
Only an exact join between the two may be written, against the revision
just read. No inferred page-ID encoding, note recreation or manual overlay.
The same join locates a page's own revision cell (page_cell).
"""
import copy
import re
import urllib.parse
import uuid

from web_session import NIL, WebError

CONTENT_ROOT = "4a3717f8-1c14-49e7-9526-81d942de1741|1"
SECTION = 0x60007
PAGE_SERIES = 0x60008
PAGE_METADATA = 0x20030
CHILDREN = 0x24001C20
PAGE_CELLS = 0x2C001D63
PAGE_METADATA_REFS = 0x24003442
ENTITY_GUID = 0x1C001C30
PAGE_LEVEL = 0x14001DFF
REFERENCE = re.compile(r"\{([0-9A-Fa-f-]{36})\}\{([0-9]+)\}")
MAX_REVISIONS = 10000
MAX_OBJECTS = 50000


def client_guid(page):
    links = page.get("links")
    link = links.get("oneNoteClientUrl") if isinstance(links, dict) else None
    url = link.get("href") if isinstance(link, dict) else None
    if not isinstance(url, str) or len(url) > 8192 or not url.startswith("onenote:"):
        return None
    parsed = urllib.parse.urlsplit(url)
    values = [value for key, value in urllib.parse.parse_qsl(parsed.query + "&" + parsed.fragment)
              if key.casefold() == "page-id"]
    if len(values) != 1:
        return None
    try:
        return str(uuid.UUID(values[0].strip("{}")))
    except ValueError:
        return None


def properties(obj):
    values = obj.get("Properties")
    if not isinstance(values, list) or len(values) % 2:
        raise WebError("Microsoft returned invalid page ordering properties")
    result = {}
    for index in range(0, len(values), 2):
        key, value = values[index:index + 2]
        if type(key) is not int or key in result or not isinstance(value, str):
            raise WebError("Microsoft returned ambiguous page ordering properties")
        result[key] = value
    return result


def references(value):
    if not isinstance(value, str):
        raise WebError("Microsoft returned invalid page ordering references")
    if not value:
        return []
    result = []
    for part in value.split(","):
        match = REFERENCE.fullmatch(part)
        if not match:
            raise WebError("Microsoft returned invalid page ordering references")
        try:
            guid = str(uuid.UUID(match[1]))
        except ValueError as error:
            raise WebError("Microsoft returned an invalid ordering identifier") from error
        result.append(guid + "|" + str(int(match[2])))
    if len(result) != len(set(result)):
        raise WebError("Microsoft returned duplicate page ordering references")
    return result


def latest_objects(state):
    """Follow the latest revision's ancestry, excluding unrelated branches.

    Returns every current object by ID, and the root objects by root ID.
    """
    revisions = state.get("RevisionList")
    if not isinstance(revisions, list) or not 0 < len(revisions) <= MAX_REVISIONS:
        raise WebError("The section's ordering history is unavailable or too large")
    by_id = {}
    for revision in revisions:
        if not isinstance(revision, dict) or not isinstance(revision.get("Id"), str) or revision["Id"] in by_id:
            raise WebError("Microsoft returned ambiguous ordering revisions")
        by_id[revision["Id"]] = revision
    current = state.get("LatestRevisionId")
    chain, seen = [], set()
    while current != NIL:
        if not isinstance(current, str) or current in seen or current not in by_id:
            raise WebError("Microsoft returned an incomplete or cyclic ordering history")
        seen.add(current)
        revision = by_id[current]
        if revision.get("Ops"):
            raise WebError("The section uses an unsupported ordering revision format")
        chain.append(revision)
        current = revision.get("BaseId")
    objects, roots = {}, {}
    for revision in reversed(chain):
        for descriptor in revision.get("RootObjectDescriptors") or []:
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("ObjectId"), str):
                raise WebError("Microsoft returned an invalid section root")
            roots[descriptor.get("RootId")] = descriptor["ObjectId"]
        for group in revision.get("ObjectGroups") or []:
            if not isinstance(group, dict) or not isinstance(group.get("Objects"), list):
                raise WebError("Microsoft returned an invalid ordering object group")
            for obj in group["Objects"]:
                if not isinstance(obj, dict) or not isinstance(obj.get("ObjectId"), str):
                    raise WebError("Microsoft returned an invalid ordering object")
                objects[obj["ObjectId"]] = obj
                if len(objects) > MAX_OBJECTS:
                    raise WebError("The section's ordering metadata is too large")
    return objects, roots


def materialize(state):
    """The section root of the latest revision, and every current object."""
    objects, roots = latest_objects(state)
    root = objects.get(roots.get(CONTENT_ROOT))
    if not root or root.get("ClassId") != SECTION:
        raise WebError("Microsoft returned an unsupported section structure")
    return root, objects


def page_cell(state, client_id):
    """The revision cell holding a page's content.

    The page metadata's entity GUID is the page's public OneNote client ID.
    Older sections list one page's metadata more than once; each cell joins
    the next distinct page. The caller confirms the cell's own metadata.
    """
    root, objects = materialize(state)
    cells = []
    for reference in references(properties(root).get(CHILDREN)):
        series = objects.get(reference, {})
        if series.get("ClassId") != PAGE_SERIES:
            raise WebError("The section contains an unsupported page group")
        props = properties(series)
        page_cells = references(props.get(PAGE_CELLS))
        guids = []
        for identifier in references(props.get(PAGE_METADATA_REFS)):
            obj = objects.get(identifier, {})
            if obj.get("ClassId") != PAGE_METADATA:
                raise WebError("Microsoft returned invalid page metadata")
            try:
                guid = str(uuid.UUID(properties(obj)[ENTITY_GUID]))
            except (KeyError, ValueError) as error:
                raise WebError("Microsoft returned invalid page identities") from error
            if guid not in guids:
                guids.append(guid)
        if len(page_cells) != len(guids):
            raise WebError("Microsoft returned incomplete page group metadata")
        for cell, guid in zip(page_cells, guids):
            if guid == client_id:
                cells.append(cell)
    if len(cells) != 1:
        raise WebError("The page was not found in its section; refresh the section")
    return cells[0]


class SectionOrder:
    def __init__(self, state, pages):
        self.state = state
        self.root, objects = materialize(state)
        self.properties = properties(self.root)
        self.references = references(self.properties.get(CHILDREN))
        if not self.references:
            raise WebError("The section has no reorderable pages")
        by_guid = {}
        for page in pages:
            guid = page.get("clientId")
            if (not isinstance(page.get("id"), str) or not isinstance(guid, str) or guid in by_guid
                    or type(page.get("level")) is not int or not 0 <= page["level"] <= 2):
                raise WebError("The complete page identities and hierarchy must be loaded before reordering")
            by_guid[guid] = page
        self.parents, self.pages, self.series = [], [], {}
        for reference in self.references:
            series = objects.get(reference, {})
            if series.get("ClassId") != PAGE_SERIES:
                raise WebError("The section contains an unsupported page group")
            props = properties(series)
            cells = references(props.get(PAGE_CELLS))
            metadata = references(props.get(PAGE_METADATA_REFS))
            if not cells or len(cells) != len(metadata):
                raise WebError("Microsoft returned incomplete page group metadata")
            block = []
            for identifier in metadata:
                obj = objects.get(identifier, {})
                if obj.get("ClassId") != PAGE_METADATA:
                    raise WebError("Microsoft returned invalid page metadata")
                values = properties(obj)
                try:
                    guid = str(uuid.UUID(values[ENTITY_GUID]))
                    level = int(values[PAGE_LEVEL]) - 1
                except (KeyError, ValueError) as error:
                    raise WebError("Microsoft returned invalid page identities or hierarchy") from error
                page = by_guid.get(guid)
                if page is None or page["level"] != level or (not block and level != 0) or (block and level == 0):
                    raise WebError("The section changed or its page hierarchy could not be verified")
                block.append(page["id"])
            parent = block[0]
            if parent in self.series:
                raise WebError("Microsoft returned duplicate page groups")
            self.parents.append(parent)
            self.pages.extend(block)
            self.series[parent] = reference
        if self.pages != [page["id"] for page in pages] or len(set(self.pages)) != len(pages):
            raise WebError("The page order changed in OneNote — refresh the section and try again")

    def arranged_root(self, expected, wanted):
        if expected != self.parents:
            raise WebError("The page order changed in OneNote — refresh the section and try again")
        if (not isinstance(wanted, list) or not all(isinstance(identifier, str) for identifier in wanted)
                or len(wanted) != len(self.parents) or len(set(wanted)) != len(wanted)
                or set(wanted) != set(self.parents)):
            raise WebError("The requested order must include every existing page group exactly once")
        root = copy.deepcopy(self.root)
        ordered = []
        for parent in wanted:
            guid, number = self.series[parent].split("|")
            ordered.append("{%s}{%s}" % (guid, number))
        values = root["Properties"]
        values[values.index(CHILDREN) + 1] = ",".join(ordered)
        return root

    def arranged_pages(self, pages, wanted):
        blocks = {}
        parent = None
        for page in pages:
            if page["level"] == 0:
                parent = page["id"]
                blocks[parent] = []
            blocks[parent].append(page)
        return [page for parent in wanted for page in blocks[parent]]


def reorder(session, pages, expected, wanted):
    """One conditional revision write, followed by a section-state readback."""
    state = session.read_section()
    order = SectionOrder(state, pages)
    root = order.arranged_root(expected, wanted)
    if expected == wanted:
        return pages
    session.put(state, root)
    arranged = order.arranged_pages(pages, wanted)
    # Read from the service that accepted the revision. Graph can lag behind
    # it; the provider's next inventory refresh still uses native Graph order.
    confirmed = SectionOrder(session.read_section(), arranged)
    if confirmed.parents != wanted:
        raise WebError("The saved order could not be confirmed; refresh the section")
    return arranged
