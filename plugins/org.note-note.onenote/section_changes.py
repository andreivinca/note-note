"""Which of the account's OneNote sections changed, from OneDrive's delta.

A OneNote section is a .one file in its notebook's OneDrive folder, and a
change to any of its pages - made here, in OneNote's apps or by someone the
notebook is shared with - changes that file. OneDrive's delta, an official
Graph API (OneNote has no change feed of its own), lists the files changed
since a cursor: one request says which sections changed in every notebook
the account owns. It names the section, never the page, so the open page is
still compared by its text (onenote.py, `page --check`).

The cursor follows the account's own drive and sees only the notebooks the
account owns: one shared with it lives in its owner's drive. Only an owned
personal notebook's sections are tracked, and the provider polls any other
as it did before. See docs/onenote-changes.md.
"""
import urllib.parse

import msgraph
from notebook_inventory import PERSONAL_ID

# A cursor at "now" costs one request, where one from the start would list
# every file the drive holds first. A section's ID holds its file's item ID
# (PERSONAL_ID), so the item ID is all a change needs to carry.
START = "/me/drive/root/delta?token=latest&$select=id"
# The pages one round follows before it keeps its place for the next: a
# drive busy with other files, a phone uploading photos, can list thousands.
MAX_PAGES = 10
MAX_BODY = 4 * 1024 * 1024


def tracked(notebooks, sections):
    """The IDs of the sections whose files are in the account's own drive."""
    owned = {notebook.get("id") for notebook in notebooks
             if str(notebook.get("userRole", "")).lower() == "owner"
             and PERSONAL_ID.fullmatch(str(notebook.get("id", "")))}
    return [section["id"] for section in sections
            if section.get("notebookId") in owned and PERSONAL_ID.fullmatch(str(section.get("id", "")))]


def cursor_url(url):
    """`url` when it continues a drive delta, otherwise "". A cursor arrives
    in a response, so it is remote content: it must be a Graph URL for a
    drive, which also keeps it on the provider's OneDrive budget."""
    if not isinstance(url, str) or not msgraph.graph_url(url):
        return ""
    return url if urllib.parse.urlsplit(url).path.startswith(msgraph.DRIVE_PATHS) else ""


def start(graph):
    """A new cursor at now."""
    status, body = graph("GET", START, max_bytes=MAX_BODY)
    cursor = cursor_url(body.get("@odata.deltaLink")) if status == 200 and isinstance(body, dict) else ""
    if not cursor:
        raise msgraph.GraphError("OneDrive did not start a change cursor (HTTP %s)" % status)
    return cursor


def read(graph, cursor, sections):
    """One round from `cursor` over the tracked `sections`: (the IDs of those
    whose files changed, the cursor for the next round).

    Without a cursor, or with one OneDrive no longer keeps (410), a new one
    starts at now, and every tracked section counts as changed: what changed
    before it is unknown. A round follows at most MAX_PAGES pages and keeps
    its place in the rest, so what it read is answered now and the rest in
    the next round.
    """
    by_item = {PERSONAL_ID.fullmatch(section).group(1).casefold(): section for section in sections}
    url = cursor_url(cursor)
    if not url:
        return list(sections), start(graph)
    changed = set()
    for _ in range(MAX_PAGES):
        status, body = graph("GET", url, max_bytes=MAX_BODY)
        if status == 410:
            return list(sections), start(graph)
        if status != 200 or not isinstance(body, dict) or not isinstance(body.get("value"), list):
            raise msgraph.GraphError("OneDrive did not list the changed files (HTTP %s)" % status)
        for item in body["value"]:
            section = by_item.get(str(item.get("id", "")).casefold()) if isinstance(item, dict) else None
            if section:
                changed.add(section)
        url = cursor_url(body.get("@odata.nextLink"))
        if not url:
            following = cursor_url(body.get("@odata.deltaLink"))
            if not following:
                raise msgraph.GraphError("OneDrive returned no change cursor")
            return sorted(changed), following
    return sorted(changed), url
