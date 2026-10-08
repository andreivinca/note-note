"""The objects OneNote's web revision service reads and writes.

A section file holds cells, each a chain of revisions of objects. The
section's root cell lists its page series, and each page's content is a cell
of its own. web_session.py carries the reads and writes; page_order.py and
blank_lines.py change these objects. Pages are joined to Graph by their
public OneNote client ID, which their metadata names.
"""
import copy
from dataclasses import dataclass
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
    """A Graph page's public OneNote client ID, from its client link."""
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
        raise WebError("Microsoft returned invalid revision properties")
    result = {}
    for index in range(0, len(values), 2):
        key, value = values[index:index + 2]
        if type(key) is not int or key in result or not isinstance(value, str):
            raise WebError("Microsoft returned ambiguous revision properties")
        result[key] = value
    return result


def references(value):
    """Object IDs, `guid|n`, from a property's `{guid}{n},…` list."""
    if not isinstance(value, str):
        raise WebError("Microsoft returned invalid revision references")
    if not value:
        return []
    result = []
    for part in value.split(","):
        match = REFERENCE.fullmatch(part)
        if not match:
            raise WebError("Microsoft returned invalid revision references")
        try:
            guid = str(uuid.UUID(match[1]))
        except ValueError as error:
            raise WebError("Microsoft returned an invalid revision identifier") from error
        result.append(guid + "|" + str(int(match[2])))
    if len(result) != len(set(result)):
        raise WebError("Microsoft returned duplicate revision references")
    return result


def with_children(obj, children):
    """A copy of `obj` listing exactly these object IDs as its children."""
    updated = copy.deepcopy(obj)
    values = updated["Properties"]
    values[values.index(CHILDREN) + 1] = ",".join("{%s}{%s}" % tuple(child.split("|")) for child in children)
    return updated


def page_guid(obj):
    """The client ID a page metadata object names."""
    if obj.get("ClassId") != PAGE_METADATA:
        raise WebError("Microsoft returned invalid page metadata")
    try:
        return str(uuid.UUID(properties(obj)[ENTITY_GUID]))
    except (KeyError, ValueError) as error:
        raise WebError("Microsoft returned invalid page identities") from error


def latest_objects(state):
    """Follow the latest revision's ancestry, excluding unrelated branches.

    Returns every current object by ID, and the root objects by root ID.
    """
    revisions = state.get("RevisionList")
    if not isinstance(revisions, list) or not 0 < len(revisions) <= MAX_REVISIONS:
        raise WebError("OneNote's revision history is unavailable or too large")
    by_id = {}
    for revision in revisions:
        if not isinstance(revision, dict) or not isinstance(revision.get("Id"), str) or revision["Id"] in by_id:
            raise WebError("Microsoft returned ambiguous revisions")
        by_id[revision["Id"]] = revision
    current = state.get("LatestRevisionId")
    chain, seen = [], set()
    while current != NIL:
        if not isinstance(current, str) or current in seen or current not in by_id:
            raise WebError("Microsoft returned an incomplete or cyclic revision history")
        seen.add(current)
        revision = by_id[current]
        if revision.get("Ops"):
            raise WebError("OneNote uses an unsupported revision format")
        chain.append(revision)
        current = revision.get("BaseId")
    objects, roots = {}, {}
    for revision in reversed(chain):
        for descriptor in revision.get("RootObjectDescriptors") or []:
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("ObjectId"), str):
                raise WebError("Microsoft returned an invalid revision root")
            roots[descriptor.get("RootId")] = descriptor["ObjectId"]
        for group in revision.get("ObjectGroups") or []:
            if not isinstance(group, dict) or not isinstance(group.get("Objects"), list):
                raise WebError("Microsoft returned an invalid revision object group")
            for obj in group["Objects"]:
                if not isinstance(obj, dict) or not isinstance(obj.get("ObjectId"), str):
                    raise WebError("Microsoft returned an invalid revision object")
                objects[obj["ObjectId"]] = obj
                if len(objects) > MAX_OBJECTS:
                    raise WebError("OneNote's revision is too large")
    return objects, roots


@dataclass(frozen=True)
class SeriesPage:
    """A page of a page series: its content cell and its metadata."""
    cell: str
    guid: str
    metadata: dict

    def level(self):
        try:
            return int(properties(self.metadata)[PAGE_LEVEL]) - 1
        except (KeyError, ValueError) as error:
            raise WebError("Microsoft returned an invalid page hierarchy") from error


class Section:
    """A section revision: its root object and its page series, in order.

    Each series lists its pages' cells and metadata. Older sections list one
    page's metadata more than once; each cell joins the next distinct page.
    """

    def __init__(self, state):
        self.objects, roots = latest_objects(state)
        self.root = self.objects.get(roots.get(CONTENT_ROOT))
        if not self.root or self.root.get("ClassId") != SECTION:
            raise WebError("Microsoft returned an unsupported section structure")
        self.series = {reference: self.pages(reference)
                       for reference in references(properties(self.root).get(CHILDREN))}

    def pages(self, reference):
        series = self.objects.get(reference, {})
        if series.get("ClassId") != PAGE_SERIES:
            raise WebError("The section contains an unsupported page group")
        values = properties(series)
        cells = references(values.get(PAGE_CELLS))
        metadata = {}
        for identifier in references(values.get(PAGE_METADATA_REFS)):
            obj = self.objects.get(identifier, {})
            metadata.setdefault(page_guid(obj), obj)
        if len(cells) != len(metadata):
            raise WebError("Microsoft returned incomplete page group metadata")
        return [SeriesPage(cell, guid, obj) for cell, (guid, obj) in zip(cells, metadata.items())]

    def cell(self, client_id):
        """The cell holding the content of the page with this client ID."""
        cells = [page.cell for pages in self.series.values() for page in pages if page.guid == client_id]
        if len(cells) != 1:
            raise WebError("The page was not found in its section; refresh the section")
        return cells[0]
