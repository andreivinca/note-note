"""Reorder existing page series without touching page bodies or hierarchy.

Graph supplies page order, levels and public page identities. The web
revision service supplies the section's current page-series references.
Only an exact join between the two may be written, against the revision
just read. No inferred page-ID encoding, note recreation or manual overlay.
"""
from revision_objects import Section, with_children
from web_session import WebError


class SectionOrder:
    def __init__(self, state, pages):
        section = Section(state)
        self.root = section.root
        if not section.series:
            raise WebError("The section has no reorderable pages")
        by_guid = {}
        for page in pages:
            guid = page.get("clientId")
            if (not isinstance(page.get("id"), str) or not isinstance(guid, str) or guid in by_guid
                    or type(page.get("level")) is not int or not 0 <= page["level"] <= 2):
                raise WebError("The complete page identities and hierarchy must be loaded before reordering")
            by_guid[guid] = page
        self.parents, self.pages, self.series = [], [], {}
        for reference, members in section.series.items():
            if not members:
                raise WebError("Microsoft returned incomplete page group metadata")
            block = []
            for member in members:
                page = by_guid.get(member.guid)
                level = member.level()
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
        return with_children(self.root, [self.series[parent] for parent in wanted])

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
    session.write_section(state, root)
    arranged = order.arranged_pages(pages, wanted)
    # Read from the service that accepted the revision. Graph can lag behind
    # it; the provider's next inventory refresh still uses native Graph order.
    confirmed = SectionOrder(session.read_section(), arranged)
    if confirmed.parents != wanted:
        raise WebError("The saved order could not be confirmed; refresh the section")
    return arranged
