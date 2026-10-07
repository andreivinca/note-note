#!/usr/bin/env python3
"""OneNote provider (Notes.ReadWrite; optional OneDrive ordering permissions).

  onenote.py list [--cached|--max-age S|--force] [--incremental] -> {"sections":[{id,name,notebook,notebookId,modified}],
                                           "pages":[{id,sectionId,title,modified}]}
                                           --cached: cache only; --max-age S: cache if younger than S seconds;
                                           --force: fetch every section, ignoring the per-section timestamps
                                           --incremental: return the tree before fetching page lists
  onenote.py list-step <file|->       -> one page-list response for {"sectionId", "interactive"?}
  onenote.py reorder-pages <file|->   -> save {"sectionId", "expected", "order"} and return confirmed inventory
  onenote.py page <id> [--check]        -> {"title","body"(markdown),"editable","view"}
  onenote.py recording <src> <title>    -> {"url"}: a recording's playable file, fetched to play it
  onenote.py update <id> <file>         -> reads {"title","body","view","resolution"?}
  onenote.py create <sectionId> <file>  -> {"ok":true,"page":{...}}
  onenote.py delete <id>
  onenote.py create-section <notebookId> <file|->  -> {"ok":true,"section":{...}}
  onenote.py search-sync <file|->      -> reconcile {"pages":[...]} with the text cache
  onenote.py search-step <file|->      -> index one due page, with {"preferredSections":[...]}
  onenote.py search <file|->           -> local matches for {"query":"..."}
  onenote.py clear-search <session>    -> clear text belonging to that sign-in
"""
import html as _html
import contextlib
import fcntl
import json, os, re, sys, time, urllib.parse, urllib.request, urllib.error, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "services", "microsoft"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
sys.path.insert(0, HERE)
import msgraph  # noqa: E402
import provider_io  # noqa: E402
import fileio  # noqa: E402
import ratelimit  # noqa: E402
from msgraph import graph, http, access_token, GRAPH  # noqa: E402
from provider_io import (fail, fail_throttled, out, load_json, save_private, read_payload,  # noqa: E402
                         TRANSIENT_STATUSES, STATE_DIR, CACHE_DIR)
import onenote_md  # noqa: E402
import onenote_patch  # noqa: E402
from onenote_audio import RecordingIdentity  # noqa: E402
from notemerge import MergeStore, StaleRemote, snapshot  # noqa: E402
import search_index  # noqa: E402
import notebook_inventory  # noqa: E402
import page_order  # noqa: E402
import web_session  # noqa: E402
import blank_lines  # noqa: E402

# OneNote's own Graph budget, shared with no other provider: a throttle here
# parks OneNote and leaves Sticky Notes listing. Microsoft's delegated OneNote
# limits are 120 requests/minute *and* 400/hour per app+user (and 5 concurrent,
# which lib/ratelimit.py caps at 4); these windows stay under both with room
# for the other things the account may be doing.
# Optional consent stays out of the required refresh scopes, including when
# an older, still-loaded UI supplies the previous combined scope list.
msgraph.configure("graph-onenote", [(60, 100), (3600, 350)],
                  scopes=" ".join(scope for scope in msgraph.settings.scopes.split()
                                  if scope not in ("Files.Read", "Files.ReadWrite")),
                  optional_scopes="Files.Read Files.ReadWrite")

ONENOTE_CACHE = os.path.join(CACHE_DIR, "note-note-onenote.json")
# The custom section order the last pass established (cmd_section_order):
# a file of its own, since the pass runs beside the listing, not inside it.
ONENOTE_ORDER = os.path.join(CACHE_DIR, "note-note-onenote-order.json")
ONENOTE_IMG_DIR = os.path.join(CACHE_DIR, "note-note-onenote-img")
ONENOTE_AUDIO_DIR = os.path.join(CACHE_DIR, "note-note-onenote-audio")
# This provider's limits: what it will read from Graph and keep around.
MAX_SECTIONS = 500
INVENTORY_VERSION = 2
PAGE_METADATA_VERSION = 1
# Seconds before each Graph listing that confirms a saved page order. Graph
# trails the revision service by a few seconds; three listings bound what
# one drag spends of the shared budget, and no wait follows the last.
ORDER_CONFIRM_DELAYS = (1, 2, 4)
READ_ONLY_REASON = "This notebook is shared with you as read-only."
MAX_PAGES = 3000
MAX_LIST_BODY = 4 * 1024 * 1024   # one page of a listing
SECTION_ORDER_VERSION = 3       # invalidates an order established before repeated numbers and several TOCs were accepted
MAX_ORDER_CACHE = 1024 * 1024
MAX_PAGE_HTML = 4 * 1024 * 1024   # a page's content
MAX_IMAGE = 20 * 1024 * 1024      # one cached image
MAX_AUDIO = 100 * 1024 * 1024     # one existing recording
MAX_AUDIO_CACHE_BYTES = 400 * 1024 * 1024
MAX_AUDIO_CACHE_FILES = 100
# Graph's 4 MB request limit counts text and every binary part. Unchanged
# recordings need no upload, but copied/recreated media share these bounds.
MAX_UPLOAD = 3 * 1024 * 1024      # one uploaded image or recording
MAX_UPLOAD_TOTAL = 3.5 * 1024 * 1024
MAX_UPLOAD_PARTS = 4


# ---------------------------------------------------------------- OneNote



def graph_raw(method, path, data=None, content_type=None, extra_headers=None,
              max_bytes=MAX_PAGE_HTML, retry_policy=None):
    """Graph call with a non-JSON body (OneNote HTML) and a text response.

    Paced and retried by the same loop as `msgraph.http()`, and classifying
    statuses out of the same two names — this used to be a second copy of it,
    and the two drifted.

    The shared transport owns the retry policy. Reads can replay, replacements
    restart the job with a fresh merge, and uncertain inserts/uploads stop.
    """
    url = path if path.startswith("http") else GRAPH + path

    def send(force):
        headers = {"Authorization": "Bearer " + access_token(force)}
        if content_type:
            headers["Content-Type"] = content_type
        headers.update(extra_headers or {})
        status, raw = msgraph.request(method, url, data, headers, max_bytes=max_bytes,
                                       timeout=60, retry_policy=retry_policy)
        return status, raw.decode(errors="replace")

    status, body = send(False)
    if status == 401:
        # As in `msgraph.graph()`: a 401 on a token the disk still calls valid
        # is a grant revoked at Microsoft's end, and only a forced refresh can
        # tell that apart from a token that simply needed renewing.
        status, body = send(True)
    return status, body


def graph_err(res, status):
    err = res.get("error") if isinstance(res, dict) else None
    if isinstance(err, dict):
        # Never pass an empty message through: the autosave retries on the
        # status code in the text, and "" retries nothing and explains nothing.
        return err.get("message") or "Graph error %s" % status
    return str(err or res or "") or "Graph error %s" % status


# A cold listing is one request per section, so it is also the thing most
# likely to be cut short by a throttle. Sections are written into the cache as
# they arrive, at most this often — a bounded number of writes, and a run that
# stops half way still leaves everything it fetched behind.
CHECKPOINT_SECONDS = 1.5


def cached_resource(collection, resource_id):
    return next((value for value in (load_listing() or {}).get(collection, [])
                 if value.get("id") == resource_id), {})


def notebook_record(collection, resource_id):
    """A notebook, or a page or section's notebook, as the inventory has it ({} if unknown)."""
    cache = load_listing() or {}

    def find(kind, identifier):
        return next((item for item in cache.get(kind, []) if item.get("id") == identifier), {})

    resource = find(collection, resource_id)
    if collection == "pages":
        resource = find("sections", resource.get("sectionId"))
    if collection in ("pages", "sections"):
        resource = find("notebooks", resource.get("notebookId"))
    return resource


def resource_read_only(collection, resource_id):
    """Resolve a page or section's current notebook permission from the inventory."""
    return str(notebook_record(collection, resource_id).get("userRole", "")).lower() in ("reader", "none")


def require_writable(collection, resource_id):
    if resource_read_only(collection, resource_id):
        fail(READ_ONLY_REASON)


def owns_personal_notebook(section_id):
    """The web revision service writes into the section's file in its
    owner's OneDrive, and the optional Files.ReadWrite grant reaches only
    the signed-in account's own drive: a personal notebook it owns, never
    one shared with it. Provider.qml's pageOrderingNotebook() offers drags
    on the same terms."""
    notebook = notebook_record("sections", section_id)
    return (str(notebook.get("userRole", "")).lower() == "owner"
            and bool(web_session.PERSONAL_ITEM.fullmatch(str(notebook.get("id", "")))))


def file_write_granted():
    """Whether the account granted the optional OneDrive write permission."""
    access_token()
    token = msgraph.signed_in(msgraph.config()[0]) or {}
    return "Files.ReadWrite" in token.get("scope", "").split()


def require_page_ordering(section_id):
    if not owns_personal_notebook(section_id):
        fail("Page ordering is available only in personal notebooks you own")


def resource_url(collection, resource_id):
    resource = cached_resource(collection, resource_id)
    url = notebook_inventory.graph_url(resource.get("self"))
    return url or "/me/onenote/%s/%s" % (collection, urllib.parse.quote(resource_id, safe=""))


def page_content_url(page_id):
    resource = cached_resource("pages", page_id)
    url = notebook_inventory.graph_url(resource.get("contentUrl"))
    return url or resource_url("pages", page_id) + "/content"


def page_record(page, section):
    result = {"id": page["id"], "title": page.get("title", "") or "",
              "sectionId": section["id"], "modified": page.get("lastModifiedDateTime", "")}
    for name in ("order", "level"):
        value = page.get(name)
        if type(value) is int and value >= 0:
            result[name] = value
    client_id = page_order.client_guid(page)
    if client_id:
        result["clientId"] = client_id
    endpoint = notebook_inventory.graph_url(page.get("self"))
    if not endpoint:
        section_url = notebook_inventory.graph_url(section.get("pagesUrl"))
        if section_url and "/sections/" in section_url:
            endpoint = section_url.split("/sections/", 1)[0] + "/pages/" + urllib.parse.quote(page["id"], safe="")
    if endpoint:
        result["self"] = endpoint
    content = notebook_inventory.graph_url(page.get("contentUrl"))
    if content:
        result["contentUrl"] = content
    return result


def section_pages_url(section_id, pages_url=None):
    """Graph's native page order and hierarchy within a section.

    `pagelevel=true` includes `order` and `level`; without it Graph omits
    both even when explicitly selected. Keep Graph's ordered sequence
    through pagination and caching, including any gaps in order numbers.
    """
    if pages_url is None:
        pages_url = cached_resource("sections", section_id).get("pagesUrl")
    endpoint = notebook_inventory.graph_url(pages_url) or resource_url("sections", section_id) + "/pages"
    return endpoint + "?pagelevel=true&$select=id,title,lastModifiedDateTime,self,contentUrl,order,level,links&$orderby=order&$top=100"


def collect_section_pages(section, get):
    """Follow a bounded section listing, validating every continuation."""
    found = []
    visited = set()
    url = section_pages_url(section["id"], section.get("pagesUrl"))
    while url and len(found) < MAX_PAGES and len(visited) < MAX_PAGES:
        if url in visited:
            return {"pages": found, "error": "Microsoft returned a repeated page listing link"}
        visited.add(url)
        status, response = get(url)
        if status != 200:
            return {"pages": found, "error": graph_err(response, status),
                    "kind": "transient" if status in TRANSIENT_STATUSES else None}
        found.extend(page_record(page, section) for page in response.get("value", []))
        next_url = response.get("@odata.nextLink")
        url = notebook_inventory.graph_url(next_url)
        if next_url and not url:
            return {"pages": found[:MAX_PAGES], "error": "Microsoft returned an invalid page listing link"}
    if url or len(found) > MAX_PAGES:
        return {"pages": found[:MAX_PAGES], "error": "The page listing limit was reached"}
    return {"pages": found}


def content_index():
    client_id = msgraph.config()[0]
    token = msgraph.signed_in(client_id) or {}
    session = os.environ.get("NOTE_NOTE_MS_CACHE_SESSION") or token.get("cacheSession", "")

    def valid():
        current = msgraph.signed_in(client_id) or {}
        return bool(session and current.get("cacheSession") == session)

    return search_index.Index(CACHE_DIR, session, valid)


# The listing and the order are the signed-in account's (msgraph
# load_for_session / save_for_session): another account's stay unread.
def load_listing(default=None):
    return msgraph.load_for_session(ONENOTE_CACHE, default)


def save_listing(cached):
    msgraph.save_for_session(ONENOTE_CACHE, cached)


def invalidate_page_lists(cache, section_id=None):
    """Invalidate responses begun before a mutation of this inventory."""
    cache["pageRevision"] = uuid.uuid4().hex
    cache["pageListSerial"] = cache.get("pageListSerial", 0) + 1
    cache.pop("notebookProgress", None)
    if section_id is not None:
        cache.get("sectionProgress", {}).pop(section_id, None)


@contextlib.contextmanager
def listing_lock():
    """Serialise cache updates, never network requests."""
    os.makedirs(os.path.dirname(ONENOTE_CACHE), mode=0o700, exist_ok=True)
    fd = os.open(ONENOTE_CACHE + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def load_order():
    return msgraph.load_for_session(ONENOTE_ORDER, {})


def save_order(order):
    msgraph.save_for_session(ONENOTE_ORDER, order)


def search_ticket(page_id):
    try:
        return content_index().ticket(page_id)
    except (OSError, ValueError):
        return None


def remember_search(page_id, html, ticket=None, saved=False):
    # Cache maintenance cannot turn a successful note read/save into a failed
    # operation. The background controller reports cache failures separately.
    try:
        return content_index().record(page_id, search_index.searchable_text(html), ticket, saved)
    except (OSError, ValueError):
        return False


def cmd_search_sync(payload):
    data = read_payload(payload)
    if not isinstance(data, dict):
        fail("invalid search inventory")
    out({"status": content_index().sync(data.get("pages"))})


def cmd_search_step(payload):
    data = read_payload(payload) or {}
    preferred = data.get("preferredSections", [])
    if not isinstance(preferred, list) or len(preferred) > MAX_SECTIONS:
        fail("invalid search scope")
    index = content_index()
    ticket = index.next_page(preferred)
    if ticket is None:
        out({"status": index.status()})
        return
    delay = ratelimit.background_delay(msgraph.settings.rate_key, msgraph.settings.rate_windows)
    if delay > 0:
        out({"status": index.status(), "deferred": True, "retryAfter": delay})
        return
    ticket = index.claim_page(preferred)
    if ticket is None:
        out({"status": index.status()})
        return
    try:
        with msgraph.background_requests():
            status, html = graph_raw("GET", page_content_url(ticket["id"]), retry_policy=msgraph.RetryPolicy.NEVER)
    except ratelimit.Deferred as deferred:
        index.release(ticket)
        out({"status": index.status(), "deferred": True, "retryAfter": deferred.retry_after})
        return
    except (ratelimit.Throttled, msgraph.GraphError):
        index.failed(ticket)
        raise
    if status == 200:
        try:
            index.record(ticket["id"], search_index.searchable_text(html), ticket)
        except ValueError:
            index.failed(ticket)
    else:
        index.failed(ticket, status)
    out({"status": index.status()})


def cmd_search(payload):
    data = read_payload(payload) or {}
    query = data.get("query", "")
    if not isinstance(query, str) or len(query) > 4096:
        fail("invalid search query")
    result = content_index().search(query)
    out({"paths": ["onenote:" + page_id for page_id in result["ids"]], "status": result["status"]})


def has_section_order_scope():
    """Inspect existing consent without refreshing or changing the sign-in."""
    try:
        token = msgraph.signed_in(msgraph.config()[0]) or {}
        return bool({"Files.Read", "Files.ReadWrite"}.intersection(token.get("scope", "").split()))
    except Exception:
        return False


def name_key(section):
    return section["name"].casefold(), section["name"], section["id"]


def by_notebook(sections):
    books = {}
    for section in sections:
        books.setdefault(section["notebookId"], []).append(section)
    return books


def in_notebook_slots(sections, arranged):
    """The sections with each notebook's members in `arranged` order, the
    notebooks themselves in the slots Graph gave them."""
    members = {key: iter(value) for key, value in arranged.items()}
    return [next(members[section["notebookId"]]) for section in sections]


def alphabetical_sections(sections):
    """Sort within each notebook, preserving notebook slots and all Graph data."""
    return in_notebook_slots(sections, {key: sorted(members, key=name_key)
                                        for key, members in by_notebook(sections).items()})


def order_matches(order):
    """Whether the order file was written under the present policy and consent."""
    return (isinstance(order, dict) and order.get("version") == SECTION_ORDER_VERSION
            and order.get("scope") == has_section_order_scope())


def remembered_order(sections, order):
    """Graph's sections in the order the last pass established (the order
    file). Within each notebook the sections the pass placed come first, by
    position, then the ones it has not seen, A-Z: a new section waits at the
    end for the pass that follows the listing. Without consent, or with an
    order file from another policy or consent state, A-Z throughout - no
    stale custom sequence is kept. Notebooks keep their Graph slots."""
    positions = order.get("positions") if order_matches(order) and order.get("scope") else None
    if not isinstance(positions, dict):
        return alphabetical_sections(sections)
    arranged = {}
    for key, members in by_notebook(sections).items():
        placed = [section for section in members if isinstance(positions.get(section["id"]), int)]
        placed.sort(key=lambda section: positions[section["id"]])
        waiting = sorted([section for section in members if section not in placed], key=name_key)
        arranged[key] = placed + waiting
    return in_notebook_slots(sections, arranged)


def ordered_sections(sections, cache, token):
    """Optional-workaround boundary; normal note access never depends on it."""
    fallback = alphabetical_sections(sections)
    warning = ["Custom section order unavailable; sections sorted alphabetically"]
    if not sections:
        return fallback, {}, []
    if not has_section_order_scope():
        return fallback, {}, warning
    try:
        # HIGH-RISK WORKAROUND: keep even imports inside the failure boundary.
        # A parser/module failure must not affect page reads, edits or listing.
        # Optional code cannot emit a second JSON reply or leak an exception
        # payload through a helper that prints before raising SystemExit.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            import section_order
            result, saved, warnings = section_order.arrange(
                [dict(section) for section in sections], cache, section_order.Remote(token))
        # Only a permutation is accepted. Never let optional code supply new
        # sections or modify the fields returned by the authoritative Graph API.
        originals = {section["id"]: section for section in sections}
        if (len(result) != len(sections) or {section["id"] for section in result} != set(originals)
                or any(section != originals[section["id"]] for section in result)
                or not isinstance(saved, dict) or len(json.dumps(saved).encode()) > MAX_ORDER_CACHE
                or not isinstance(warnings, list) or not all(isinstance(value, str) for value in warnings)):
            return fallback, {}, warning
        return [originals[section["id"]] for section in result], saved, warnings
    except (Exception, SystemExit):
        # Never include exception text here: it could contain a signed URL.
        # KeyboardInterrupt still cancels the command rather than continuing.
        return fallback, {}, warning


class Listing:
    """The listing cache, and what a re-listing may skip.

    Two things are folded in here, and both exist to spend fewer requests on
    an account that has not changed:

    **Continue, never restart.** Each section's pages are written into the
    cache as its request comes back, with the section's own
    `lastModifiedDateTime` beside them. A listing cut short by a throttle
    keeps everything it fetched, and the next run picks up the tail.

    **Diff by timestamp.** The notebook inventory includes each section's
    last modification time, so a re-listing fetches pages only for
    the sections whose stamp moved (and ones it has never seen). A quiet
    account skips page requests entirely. `--force` — the
    Refresh row — ignores the stamps and fetches everything.
    """

    def __init__(self, cache, sections, notebooks=None):
        self.sections = sections
        self.notebooks = cache.get("notebooks", []) if notebooks is None else notebooks
        self.by_section = {}
        for pg in (cache.get("pages") or []):
            self.by_section.setdefault(pg.get("sectionId", ""), []).append(pg)
        seen = cache.get("sectionPages")
        self.seen = dict(seen) if isinstance(seen, dict) else {}
        self.progress = dict(cache.get("sectionProgress") or {})
        if cache.get("pageMetadataVersion") != PAGE_METADATA_VERSION:
            # A cursor saved by an older listing would finish its section
            # without the metadata the new query asks for. Complete lists
            # stay as they are: each says which metadata it carries
            # (`outdated`), and only an opened section is fetched again.
            self.progress = {}
        self.notebook_progress = cache.get("notebookProgress")
        self.warnings = cache.get("listingWarnings", [])
        self.revision = cache.get("pageRevision", "")
        self.serial = cache.get("pageListSerial", 0)
        # `fetched` is when the account's notebooks and sections were last
        # discovered, which is what --max-age is measured against. Only a
        # discovery moves it: a section refreshed or a listing completed
        # afterwards is no newer than the inventory its stamps came from.
        self.fetched = cache.get("fetched", 0) if isinstance(cache.get("fetched"), (int, float)) else 0
        self.last_write = 0.0

    def stale(self, sct, force):
        if force:
            return True
        was = self.seen.get(sct["id"])
        # A section we have never finished has no entry at all, which is how
        # an interrupted run knows its own tail.
        return not isinstance(was, dict) or was.get("modified") != sct.get("modified", "")

    def record(self, sct, pages):
        self.by_section[sct["id"]] = pages
        self.seen[sct["id"]] = {"modified": sct.get("modified", ""), "at": time.time(),
                                "metadata": PAGE_METADATA_VERSION}
        self.progress.pop(sct["id"], None)

    def outdated(self):
        """Sections listed in full, but before the page metadata listings
        now carry (hierarchy and client identities). They count as current
        for discovery and search coverage; the provider fetches one again
        when it is opened, which is the only place the metadata is used."""
        return [section["id"] for section in self.sections
                if not self.stale(section, False)
                and self.seen[section["id"]].get("metadata") != PAGE_METADATA_VERSION]

    def prepare_sections(self, force=False):
        for section in self.sections:
            sid = section["id"]
            progress = self.progress.get(sid, {})
            if force:
                self.seen.pop(sid, None)
            if force or progress.get("modified") != section.get("modified", ""):
                self.progress.pop(sid, None)

    def pages(self):
        found = []
        for sct in self.sections:
            found.extend(self.by_section.get(sct["id"], []))
        return found[:MAX_PAGES]

    def complete(self):
        return (not self.warnings and not self.notebook_progress and self.within_limits()
                and all(not self.stale(section, False) for section in self.sections))

    def save(self, complete):
        live = set(sct["id"] for sct in self.sections)
        self.seen = dict((k, v) for k, v in self.seen.items() if k in live)
        self.progress = {key: value for key, value in self.progress.items() if key in live}
        complete = complete and self.complete()
        self.serial += 1
        save_listing({"sections": self.sections, "notebooks": self.notebooks, "pages": self.pages(),
                      "sectionPages": self.seen, "fetched": self.fetched,
                      "sectionProgress": self.progress, "listingWarnings": self.warnings,
                      "notebookProgress": self.notebook_progress,
                      "pageRevision": self.revision,
                      "pageListSerial": self.serial,
                      "inventoryVersion": INVENTORY_VERSION,
                      "pageMetadataVersion": PAGE_METADATA_VERSION,
                      "inventoryComplete": complete})
        self.last_write = time.monotonic()

    def commit(self, complete):
        """Checkpoint a full listing only while its cache snapshot is current."""
        with listing_lock():
            latest = load_listing() or {}
            if (latest.get("pageRevision", "") != self.revision
                    or latest.get("pageListSerial", 0) != self.serial):
                raise msgraph.GraphError("The notebook inventory changed — retry the listing", kind="transient")
            self.revision = uuid.uuid4().hex
            self.save(complete)

    def page_limit(self, section_id):
        other_pages = sum(len(self.by_section.get(section["id"], []))
                          for section in self.sections if section["id"] != section_id)
        return max(0, MAX_PAGES - other_pages)

    def pending(self):
        # A full cache can still refresh its existing sections. A capped
        # continuation stops until a refresh or changed section restarts it.
        return [section["id"] for section in self.sections
                if self.stale(section, False) and self.page_limit(section["id"]) > 0
                and not self.progress.get(section["id"], {}).get("limited")]

    def retain_pages(self, section_id, pages):
        """Publish partial titles without treating absent pages as deletions."""
        updated = {page["id"]: page for page in pages}
        previous = self.by_section.get(section_id, [])
        retained = [updated.get(page["id"], page) for page in previous]
        seen = {page["id"] for page in previous}
        retained.extend(page for page in pages if page["id"] not in seen)
        self.by_section[section_id] = retained[:self.page_limit(section_id)]

    def answer(self):
        pending = self.pending()
        retries = {sid: self.progress.get(sid, {}).get("retryAt", 0) for sid in pending}
        return {"sections": remembered_order(self.sections, load_order()), "notebooks": self.notebooks,
                "pages": self.pages(), "inventoryReady": True,
                "inventoryComplete": self.complete(),
                "pendingSections": pending, "outdatedSections": self.outdated(),
                "sectionRetryAt": retries,
                "pageListSerial": self.serial,
                "listingWarnings": self.warnings}

    def within_limits(self):
        # Hitting either listing cap means we cannot claim complete coverage.
        return (len(self.sections) < MAX_SECTIONS
                and sum(len(self.by_section.get(sct["id"], [])) for sct in self.sections) < MAX_PAGES)

    def checkpoint(self):
        if time.monotonic() - self.last_write >= CHECKPOINT_SECONDS:
            self.commit(False)


def retain_missing(current, previous):
    """An incomplete inventory cannot establish that a cached item was removed."""
    seen = {item["id"] for item in current}
    return current + [item for item in previous if item["id"] not in seen]


def cmd_onenote_list(cached, max_age=0, force=False, incremental=False):
    """The account's sections and pages. The custom section order is not
    established here: the listing answers in the order the last pass left
    (remembered_order) and says when a pass is due - after every network
    listing, and whenever the order file no longer matches the policy or
    the consent - and the provider runs `section-order` beside it."""
    c = load_listing()
    order = load_order()
    if cached or (max_age and c and c.get("inventoryVersion") == INVENTORY_VERSION
                  and c.get("inventoryComplete") is True
                  and time.time() - c.get("fetched", 0) < max_age):
        inventory_ready = c is not None
        c = c or {"sections": [], "pages": []}
        sections = c.get("sections", [])
        answer = Listing(c, sections).answer() if inventory_ready else {}
        answer.update(sections=remembered_order(sections, order), notebooks=c.get("notebooks", []),
                      pages=c.get("pages", []), cached=True, inventoryReady=inventory_ready,
                      inventoryComplete=c.get("inventoryComplete", False),
                      sectionOrderPending=bool(sections) and not order_matches(order))
        out(answer)
        return
    cache = c if isinstance(c, dict) else {}
    revision = cache.get("pageRevision", "")
    discovery_progress = cache.get("notebookProgress") if incremental and not force else None
    refresh_pages = force or bool(discovery_progress and discovery_progress.get("force"))

    def checkpoint(progress):
        with listing_lock():
            latest = load_listing() or {}
            if latest.get("pageRevision", "") != revision:
                raise msgraph.GraphError("The notebook inventory changed — retry the listing", kind="transient")
            progress["force"] = refresh_pages
            latest["notebookProgress"] = progress
            save_listing(latest)

    try:
        with msgraph.background_requests() if incremental else contextlib.nullcontext():
            notebooks, sections, warnings = notebook_inventory.discover(
                graph, MAX_SECTIONS, MAX_LIST_BODY,
                progress=discovery_progress,
                checkpoint=checkpoint if incremental else None,
                cached_notebooks=cache.get("notebooks", []))
    except ratelimit.Deferred as deferred:
        with listing_lock():
            latest = load_listing() or {}
            progress = latest.get("notebookProgress") or {}
            sections = retain_missing(progress.get("sections", []), latest.get("sections", []))[:MAX_SECTIONS]
            notebooks = retain_missing(progress.get("notebooks", []), latest.get("notebooks", []))[:MAX_SECTIONS]
            listing = Listing(latest, sections, notebooks)
            if progress.get("notebooks"):
                listing.warnings = progress.get("warnings", []) + ["Notebook discovery is incomplete"]
                if (sections != latest.get("sections", []) or notebooks != latest.get("notebooks", [])
                        or listing.warnings != latest.get("listingWarnings", [])):
                    listing.prepare_sections()
                    listing.revision = uuid.uuid4().hex
                    listing.save(False)
            ready = latest.get("inventoryVersion") == INVENTORY_VERSION or bool(notebooks)
            out(dict(listing.answer(), inventoryReady=ready, deferred=True, retryAfter=deferred.retry_after))
        return
    except notebook_inventory.DiscoveryError as error:
        fail(graph_err(error.response, error.status),
             kind="transient" if error.status in TRANSIENT_STATUSES else None)
    if warnings:
        notebooks = retain_missing(notebooks, cache.get("notebooks", []))[:MAX_SECTIONS]
        sections = retain_missing(sections, cache.get("sections", []))
    sections = remembered_order(sections[:MAX_SECTIONS], order)
    discovered = time.time()
    if incremental:
        with listing_lock():
            latest = load_listing() or {}
            if latest.get("pageRevision", "") != revision:
                answer = Listing(latest, latest.get("sections", [])).answer()
                out(dict(answer, deferred=True, retryAfter=0.1))
                return
            listing = Listing(latest, sections, notebooks)
            listing.fetched = discovered
            listing.warnings = warnings
            listing.notebook_progress = None
            listing.revision = uuid.uuid4().hex
            listing.prepare_sections(refresh_pages)
            listing.save(listing.complete())
            out(dict(listing.answer(), cached=False, sectionOrderPending=bool(sections)))
        return
    token = access_token()
    listing = Listing(cache, sections, notebooks)
    listing.fetched = discovered
    listing.warnings = warnings
    listing.notebook_progress = None
    todo = [sct for sct in sections if listing.stale(sct, force)]

    # Pages are listed per section: the account-wide /me/onenote/pages call
    # refuses accounts with many sections (docs/engine-notes.md). Each call
    # takes a couple of seconds, so the stale ones are fetched in parallel —
    # the pacer holds the total to four requests in flight.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # All workers use the already-validated token snapshot. Optional ordering
    # cannot change it or impose a cooldown on this normal OneNote lane.
    def get(url):
        return http("GET", url if url.startswith("http") else GRAPH + url,
                    headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                    max_bytes=MAX_LIST_BODY, retry_policy=msgraph.RetryPolicy.NEVER)

    if todo:
        error, error_kind = "", None
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(collect_section_pages, sct, get): sct for sct in todo}
                for future in as_completed(futures):
                    result = future.result()
                    if result.get("error"):
                        if result.get("kind") == "transient":
                            error, error_kind = result["error"], result["kind"]
                            break
                        section = futures[future]
                        warnings.append(section["notebook"] + " › " + section["name"] + ": " + result["error"])
                        listing.retain_pages(section["id"], result.get("pages", []))
                        continue
                    listing.record(futures[future], result["pages"])
                    listing.checkpoint()
        except (ratelimit.Throttled, msgraph.GraphError):
            # Keep what did arrive: the sections stored here are skipped by
            # their own stamp next time, so the run after the cooldown fetches
            # only the tail instead of spending the budget again from scratch.
            listing.commit(False)
            raise
        if error:
            # Whatever went wrong, what did arrive is kept first — the same
            # bargain the `Throttled` path above makes, and the reason a run
            # after a failure fetches only the tail.
            listing.commit(False)
            fail(error, kind=error_kind)

    complete = listing.complete()
    listing.commit(complete)
    out({"sections": sections, "notebooks": notebooks, "pages": listing.pages(), "cached": False,
         "listingWarnings": warnings,
         "inventoryComplete": complete and listing.within_limits(),
         "sectionOrderPending": bool(sections)})


def cmd_list_step(payload):
    """Fetch at most 100 page titles, then yield the queue to user actions.

    Pagination is persisted. Until a section is complete, cached pages are
    retained; a partial response cannot establish that a page was deleted.
    """
    data = read_payload(payload) or {}
    sid = data.get("sectionId")
    if not isinstance(sid, str) or len(sid) > 1024:
        fail("invalid section")
    interactive = data.get("interactive") is True
    with listing_lock():
        cache = load_listing() or {}
        listing = Listing(cache, cache.get("sections", []))
        section = next((section for section in listing.sections if section["id"] == sid), None)
        if section is None:
            out(listing.answer())
            return
        if data.get("refresh") is True:
            listing.seen.pop(sid, None)
            listing.progress.pop(sid, None)
            listing.revision = uuid.uuid4().hex
            listing.save(False)
        if sid not in listing.pending():
            out(listing.answer())
            return
        progress = listing.progress.get(sid, {})
        retry_after = max(0, progress.get("retryAt", 0) - time.time())
        if retry_after and not interactive:
            out(dict(listing.answer(), deferred=True, retryAfter=retry_after))
            return
        url = progress.get("url") or section_pages_url(sid, section.get("pagesUrl"))
        if progress.get("url") and not notebook_inventory.graph_url(url):
            fail("invalid saved page listing link")
        revision = listing.revision

    try:
        with contextlib.nullcontext() if interactive else msgraph.background_requests():
            status, response = graph("GET", url, max_bytes=MAX_LIST_BODY,
                                     retry_policy=msgraph.RetryPolicy.NEVER)
    except ratelimit.Deferred as deferred:
        out(dict(listing.answer(), deferred=True, retryAfter=deferred.retry_after))
        return

    with listing_lock():
        latest = load_listing() or {}
        listing = Listing(latest, latest.get("sections", []))
        current = listing.progress.get(sid, {})
        # Another discovery, creation, deletion or section refresh invalidates
        # the response. A continuation also has to match its starting point.
        if (listing.revision != revision or current.get("url") != progress.get("url")
                or not listing.stale(section, False)):
            out(listing.answer())
            return
        if status != 200:
            listing.progress[sid] = dict(progress, modified=section.get("modified", ""),
                                         retryAt=time.time() + 300)
            listing.save(False)
            out(dict(listing.answer(), listingError=graph_err(response, status)))
            return
        found = progress.get("pages", [])
        seen = {page["id"] for page in found}
        for page in response.get("value", []):
            if page["id"] not in seen:
                found.append(page_record(page, section))
                seen.add(page["id"])
        limit = listing.page_limit(sid)
        next_url = response.get("@odata.nextLink")
        visited = progress.get("visited", []) + [url]
        if next_url and (not notebook_inventory.graph_url(next_url) or next_url in visited
                         or len(visited) >= MAX_PAGES):
            listing.progress[sid] = dict(progress, modified=section.get("modified", ""),
                                         retryAt=time.time() + 300)
            listing.save(False)
            out(dict(listing.answer(), listingError="Microsoft returned an invalid page listing link"))
            return
        limited = len(found) > limit or (bool(next_url) and len(found) >= limit)
        found = found[:limit]
        if next_url or limited:
            listing.progress[sid] = {"modified": section.get("modified", ""), "url": next_url,
                                     "pages": found, "visited": visited, "limited": limited}
            listing.retain_pages(sid, found)
        else:
            listing.record(section, found)
        listing.save(listing.complete())
        out(dict(listing.answer(), sectionId=sid, sectionComplete=not next_url and not limited))


def cmd_section_order():
    """Establish the custom section order for the listing in the cache. Runs
    after the listing and beside the note lane, on the provider's word: the
    OneDrive metadata it reads can take a while, and neither the pages nor a
    note may wait for it (docs/onenote-section-order.md). The order goes to
    its own file - positions by section id, the TOC metadata the next pass
    may reuse, and the warnings - and the answer is the listing's sections
    as they stand now, in that order: a listing that landed meanwhile keeps
    its newer sections, waiting after the placed ones."""
    sections = (load_listing() or {}).get("sections", [])
    scope = has_section_order_scope()
    # This token has already worked for normal notes. Optional metadata uses
    # the snapshot as-is; it cannot refresh or invalidate the account.
    token = access_token() if sections and scope else ""
    ordered, metadata, warnings = ordered_sections(sections, load_order().get("metadata"), token)
    order = {"version": SECTION_ORDER_VERSION, "scope": scope, "metadata": metadata, "warnings": warnings,
             "positions": {section["id"]: index for index, section in enumerate(ordered)}}
    save_order(order)
    latest = (load_listing() or {}).get("sections", sections)
    out({"sections": remembered_order(latest, order), "sectionOrderWarnings": warnings})


# Page images and recordings are only fetched from Graph's resource endpoint, with
# the bearer token, and never across a redirect: an <img src> in page content
# is untrusted and must not be able to send our token (or any request)
# anywhere else. Anything else is shown as text, not loaded.
RESOURCE_PATH_RE = re.compile(notebook_inventory.ROOT_PATH.pattern + r"resources/[A-Za-z0-9!._-]+/\$value$")


class FetchBudget:
    """What one command may spend fetching one kind of resource: a request
    count and a wall-clock deadline. A page read spends the image budget on
    its pictures; recordings are fetched only when played, or when a save
    copies their bytes, under a budget of their own. Each resource cache is
    bounded too, so a page full of unique attachments can neither hold a
    fetch open nor fill the disk."""

    def __init__(self, seconds, requests):
        self.seconds = seconds
        self.requests = requests
        self.deadline = 0.0      # monotonic; 0 until a command starts it
        self.used = 0

    def start(self):
        self.deadline = time.monotonic() + self.seconds
        self.used = 0

    def spent(self):
        return self.used >= self.requests or bool(self.deadline and time.monotonic() > self.deadline)

    def until(self):
        """The deadline one fetch must finish by."""
        return self.deadline or time.monotonic() + self.seconds


MAX_CACHE_BYTES = 200 * 1024 * 1024
MAX_CACHE_FILES = 400
_image_budget = FetchBudget(seconds=45, requests=40)
# A recording is fetched while its player waits, so it may take longer than
# a picture; the provider process itself is stopped after ten minutes.
_recording_budget = FetchBudget(seconds=300, requests=MAX_UPLOAD_PARTS)


_image_opener = urllib.request.build_opener(provider_io.NoRedirect)


def image_allowed(src):
    if not notebook_inventory.graph_url(src):
        return False
    try:
        u = urllib.parse.urlsplit(src)
    except ValueError:
        return False
    return bool(RESOURCE_PATH_RE.match(u.path)) and not u.query


# A cached image on its own says nothing about where it came from, and a save
# has to hand OneNote the very same resource back. The index remembers that,
# and is written by the page load that filled the cache.
IMAGE_INDEX = os.path.join(ONENOTE_IMG_DIR, "index.json")
AUDIO_INDEX = os.path.join(ONENOTE_AUDIO_DIR, "index.json")


def remember_images(page_id, images, complete):
    """What the load saw: where each image came from, and whether it got them
    all. A page whose images could not all be fetched (a throttled account, a
    dropped connection) must not be written back — the note in the editor is
    missing a picture, and saving it would take that picture off the page."""
    index = load_json(IMAGE_INDEX, {})
    files = index.get("files", {})
    for img in images:
        name = os.path.basename(img.get("local", "").replace("file://", ""))
        if name:
            files[name] = {"src": img.get("src", ""), "width": img.get("width", 0)}
    # Entries whose file is gone are dead weight; the cache prunes itself.
    files = {k: v for k, v in files.items() if os.path.exists(os.path.join(ONENOTE_IMG_DIR, k))}
    pages = index.get("pages", {})
    pages.pop(page_id, None)
    pages[page_id] = {"complete": bool(complete)}
    while len(pages) > 500:                      # oldest first; bound the file
        pages.pop(next(iter(pages)))
    # An editor can still reference a staged paste while the next save reads
    # the page. Keep its resource alias so that read cannot cause a re-upload.
    staged = {path: entry for path, entry in index.get("staged", {}).items() if os.path.isfile(path)}
    staged = dict(list(staged.items())[-128:])
    save_private(IMAGE_INDEX, {"files": files, "pages": pages, "staged": staged})


def file_path_of(url):
    return urllib.parse.unquote(url[len("file://"):])


def known_image(url):
    """A file:// url from the note -> the OneNote resource it came from."""
    if not url.startswith("file://"):
        return None
    path = file_path_of(url)
    index = load_json(IMAGE_INDEX, {})
    if os.path.dirname(path) == ONENOTE_IMG_DIR:
        return index.get("files", {}).get(os.path.basename(path))
    # A paste the last save already uploaded: the editor still shows the
    # staged file until the page is reloaded, and without this the same bytes
    # would go up again on every autosave in between.
    return index.get("staged", {}).get(path)


# A note names each recording by its Graph resource. The index keeps what a
# save needs to know about those resources without reading their pages:
# `resources` maps one to its title and MIME type, and `instances` maps a
# recording ID to the resource behind it. A copy keeps its original's
# resource in the editor until the page reloads, so the upload a save
# acknowledged is found here by the copy's ID (RecordingIdentity).
MAX_RECORDING_INDEX = 500


def recording_identity():
    return RecordingIdentity(load_json(AUDIO_INDEX, {}).get("instances", {}))


def remember_recording_index(resources=(), instances=()):
    """Add (resource, details) and (ID, resource) pairs; the newest are kept."""
    index = load_json(AUDIO_INDEX, {})
    known = {"resources": dict(index.get("resources", {})), "instances": dict(index.get("instances", {}))}
    for name, pairs in (("resources", resources), ("instances", instances)):
        for key, value in pairs:
            known[name].pop(key, None)
            known[name][key] = value
        known[name] = dict(list(known[name].items())[-MAX_RECORDING_INDEX:])
    if known != {"resources": index.get("resources"), "instances": index.get("instances")}:
        save_private(AUDIO_INDEX, known)


def remember_recordings(recordings):
    """The details and instance of each recording a page read shows."""
    playable = [recording for recording in recordings if image_allowed(recording["src"])]
    if not playable:
        return
    remember_recording_index(
        resources=[(item["src"], {"title": item["title"], "mime": item["mime"]}) for item in playable],
        instances=[(item["id"], item["src"]) for item in playable if item.get("id")])


def known_recording(src):
    """The title and MIME type a page read recorded for a Graph resource."""
    return load_json(AUDIO_INDEX, {}).get("resources", {}).get(src)


def acknowledged_uploads(staged, html):
    """(upload, Graph resource) for each upload whose data-id marks exactly
    one resource in the page that the save produced."""
    resources = {}
    for node in onenote_patch.walk(onenote_patch.parse(html)):
        if node.tag in {"img", "object"} and node.attrs.get("data-id"):
            source = node.attrs.get("src" if node.tag == "img" else "data", "")
            resources.setdefault(node.attrs["data-id"], []).append(source)
    for upload in staged.values():
        sources = resources.get(upload["dataId"], [])
        if len(sources) == 1 and image_allowed(sources[0]):
            yield upload, sources[0]


def remember_staged(staged, html):
    """Match upload aliases by the data-id written with each upload.

    Patch order and document order can differ. Only an exact, unique marker
    can associate a local paste with its acknowledged OneNote resource.
    """
    acknowledged = list(acknowledged_uploads(staged, html))
    images = [(upload, src) for upload, src in acknowledged if upload["kind"] == "image"]
    recordings = [(upload, src) for upload, src in acknowledged if upload["kind"] == "audio"]
    if any(upload["kind"] == "image" for upload in staged.values()):
        remember_uploaded_images(images)
    if recordings:
        remember_uploaded_recordings(recordings)


def remember_uploaded_images(uploads):
    index = load_json(IMAGE_INDEX, {})
    files, pastes = index.get("files", {}), index.get("staged", {})
    for upload, src in uploads:
        path, entry = upload["path"], {"src": src, "width": upload["width"]}
        if os.path.dirname(path) == ONENOTE_IMG_DIR:
            files[os.path.basename(path)] = entry
        else:
            pastes[path] = entry
    index["files"] = files
    index["staged"] = dict(list((p, e) for p, e in pastes.items() if os.path.isfile(p))[-128:])
    save_private(IMAGE_INDEX, index)


def remember_uploaded_recordings(uploads):
    """An uploaded copy is a new resource under the copy's own ID; the
    original it was copied from keeps its resource and ID."""
    remember_recording_index(
        resources=[(src, {"title": upload["title"], "mime": upload["mime"]}) for upload, src in uploads],
        instances=[(upload["dataId"], src) for upload, src in uploads])


def prune_resource_cache(directory, max_bytes, max_files):
    """Keep a resource cache under its ceilings, oldest first."""
    try:
        entries = []
        for name in os.listdir(directory):
            if name == "index.json":             # bookkeeping, not a cached image
                continue
            path = os.path.join(directory, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, path))
    except OSError:
        return
    entries.sort()
    total = sum(e[1] for e in entries)
    while entries and (len(entries) > max_files or total > max_bytes):
        _, size, path = entries.pop(0)
        try:
            os.remove(path)
            total -= size
        except OSError:
            pass


def cached_image(src, width=0):
    """A page image, fetched through Graph into the cache; returns a file://
    URL, or None when the source is not Graph's resource endpoint (then the
    page shows the image's alt text instead).

    The bytes are kept exactly as Graph served them — the editor caps its own
    display width, and a save may upload these bytes back, so nothing here may
    rescale or re-encode. `width` is only recorded (via the caller) so a save
    can write the same display width back into the page.
    """
    return cached_graph_file(src, image_cache_path(src), MAX_IMAGE, _image_budget,
                           lambda: prune_resource_cache(ONENOTE_IMG_DIR, MAX_CACHE_BYTES, MAX_CACHE_FILES))


def cached_audio(src, title):
    """A recording's playable file, fetched through Graph the first time
    someone plays it (cmd_onenote_recording) or a save copies its bytes.
    Opening or checking a page never fetches a recording."""
    return cached_graph_file(src, recording_cache_path(src, title), MAX_AUDIO, _recording_budget,
                           lambda: prune_resource_cache(ONENOTE_AUDIO_DIR, MAX_AUDIO_CACHE_BYTES, MAX_AUDIO_CACHE_FILES))


def cached_graph_file(src, path, max_bytes, budget, prune):
    """A Graph resource as a private file:// URL, fetched into `path` when it
    is not there yet; None when the source is not Graph's resource endpoint
    or the fetch fails."""
    if not image_allowed(src):
        return None
    try:
        if os.path.getsize(path) > 0:
            return "file://" + path
        os.remove(path)                  # a failed fetch left a stub
    except OSError:
        pass
    data = fetch_page_resource(src, max_bytes, budget)
    if data is None:
        return None
    # Committed whole and private (fileio.write_atomic): a reader never
    # meets half a resource.
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fileio.write_atomic(path, data, mode=0o600)
    prune()
    return "file://" + path


def image_cache_path(src):
    import hashlib
    return os.path.join(ONENOTE_IMG_DIR, hashlib.sha1(src.encode()).hexdigest())


def recording_cache_path(src, title):
    import hashlib
    return os.path.join(ONENOTE_AUDIO_DIR, hashlib.sha256(src.encode()).hexdigest() + audio_suffix(title))


def audio_suffix(title):
    suffix = os.path.splitext(title)[1].lower()
    return suffix if suffix in AUDIO_MIME_BY_SUFFIX else ""


def fetch_page_resource(src, max_bytes, budget):
    """Fetch a bounded, private Graph resource without following redirects;
    the bytes, or None when the budget is spent or the request fails.

    Nothing from the document is handed to Qt as an authenticated remote URL.
    """
    if not image_allowed(src) or budget.spent():
        return None
    # No revoked-grant pass of its own, for the reason the listing pool has
    # none: a page read's `graph_raw` fetch of the content has already met
    # any 401 and forced the refresh, and a recording is played or copied
    # from a page that was read. A grant revoked since then shows as a
    # failed download until the next read signs the account out.
    req = urllib.request.Request(src, headers={"Authorization": "Bearer " + access_token()})
    pause = 0.0        # a throttle met here, recorded once the slot is released
    try:
        # A resource is a Graph request like any other and is paced like one:
        # forty of them is what a picture-heavy page costs, and that is most
        # of a minute's budget on its own.
        with ratelimit.slot(msgraph.settings.rate_key, msgraph.settings.rate_windows,
                            reserve=msgraph.settings.background_reserve):
            with _image_opener.open(req, timeout=20) as r:
                # Bounded in size and in time: a TimeoutError is an OSError, caught below.
                data = provider_io.read_bounded(r, max_bytes, budget.until())
                if not data:
                    # Graph serves a just-written resource as 200 with an
                    # empty body; caching that would poison the page for good.
                    raise OverflowError("empty resource response")
        budget.used += 1
        return data
    except ratelimit.Throttled:
        pass                       # the pacer already knows; nothing to record
    except urllib.error.HTTPError as e:
        if e.code in (429, 503):
            pause = msgraph.wait_asked_by(e)
    except (urllib.error.URLError, OSError, OverflowError):
        pass
    if pause:
        # The rest of this page's resources would earn the same answer, and
        # so would the next process: record it once and let them all fail
        # fast. The page still loads — an image shows its alt text, a
        # recording its unavailable player — and the missing resource keeps
        # a save from writing the page back (remember_images, read_page).
        ratelimit.report_throttle(msgraph.settings.rate_key, pause)
    return None


def cmd_onenote_pages(section_ids):
    """Pages of a few sections (one request each) — for cheap refreshes."""
    section_ids = section_ids[:10]
    cache = load_listing() or {}
    sections = {section["id"]: section for section in cache.get("sections", [])}
    found = []

    def get(url):
        return graph("GET", url, max_bytes=MAX_LIST_BODY)

    for sid in section_ids:
        result = collect_section_pages(sections.get(sid, {"id": sid}), get)
        if result.get("error"):
            fail(result["error"], kind=result.get("kind"))
        found.extend(result["pages"])
    if len(found) > MAX_PAGES:
        fail("The page listing limit was reached")
    with listing_lock():
        c = load_listing()
        if c:
            if (c.get("pageRevision", "") != cache.get("pageRevision", "")
                    or c.get("pageListSerial", 0) != cache.get("pageListSerial", 0)):
                raise msgraph.GraphError("The notebook inventory changed — retry the listing", kind="transient")
            pages = [p for p in c.get("pages", []) if p["sectionId"] not in section_ids] + found
            if len(pages) > MAX_PAGES:
                fail("The page listing limit was reached")
            c["pages"] = pages
            for sid in section_ids:
                c.get("sectionProgress", {}).pop(sid, None)
            invalidate_page_lists(c)
            save_listing(c)
    out({"sections": section_ids, "pages": found, "pageListSerial": (c or {}).get("pageListSerial", 0)})


def normalize_note(note):
    """Comparable Markdown, including aliases for pictures already uploaded."""
    def image_ref(url, alt):
        known = known_image(url)
        width = (known or {}).get("width", 0)
        if known and known.get("src"):
            cached = image_cache_path(known["src"])
            if os.path.isfile(cached):
                return "file://" + cached, width
        return url, width

    identity = recording_identity()

    def audio_ref(url, title, identifier=""):
        url, identifier = identity.resolve(url, identifier)
        return onenote_md.audio.markup(url, title, identifier)

    html = onenote_md.markdown_to_onenote_html(note["body"], image_ref, audio_ref)
    body = onenote_md.html_to_markdown("<body>" + html + "</body>", lambda src, width: src,
                                     lambda src, title: src)["body"]
    return {"title": note["title"].strip(), "body": body}


def merge_account():
    # Stable Graph identity, never an email/display name or a rotating token.
    client_id = msgraph.config()[0]
    token = msgraph.signed_in(client_id)
    if not token:
        fail("not signed in")
    expected = os.environ.get("NOTE_NOTE_MS_CACHE_SESSION", "")
    if expected and token.get("cacheSession") != expected:
        fail("the signed-in account changed")
    account = token.get("userId")
    if not account:
        status, profile = graph("GET", "/me?$select=id")
        if status != 200 or not profile.get("id"):
            fail("could not identify the account for note recovery")
        account = profile["id"]
        with msgraph.token_lock():
            current = msgraph.signed_in(client_id)
            if not current or current.get("cacheSession") != token.get("cacheSession"):
                fail("the signed-in account changed")
            current["userId"] = account
            save_private(msgraph.TOKENS, current)
    return client_id + ":" + account


def merge_store(page_id):
    return MergeStore(os.path.join(STATE_DIR, "note-note-merges"),
                      "onenote", merge_account(), page_id,
                      normalize=normalize_note, stale_seconds=120)


def recording_resource(src, title):
    """A page names a recording by its Graph resource; nothing is fetched."""
    return src if image_allowed(src) else None


def read_page(page_id):
    """The page as a note. Its images are fetched into the cache. Its
    recordings are not: each is named by its Graph resource and fetched when
    someone plays it (cmd_onenote_recording)."""
    _image_budget.start()
    ticket = search_ticket(page_id)
    url = page_content_url(page_id) + "?includeIDs=true"
    status, html = graph_raw("GET", url)
    if status != 200:
        try:
            fail(graph_err(json.loads(html), status))
        except ValueError:
            fail("Graph error %s" % status)
    # Graph's resources are the truth here: no upload alias applies.
    identity = RecordingIdentity()
    result = onenote_md.html_to_markdown(html, cached_image, recording_resource,
        lambda src, local, title, identifier: identity.resolve(local, identifier))
    if any(not recording["local"] for recording in result["recordings"]):
        result["reason"] = "A recording on this page has no OneNote resource, so the page is read-only."
    remember_images(page_id, result["images"], result["editable"])
    remember_recordings(result["recordings"])
    remember_search(page_id, html, ticket)
    if resource_read_only("pages", page_id):
        result["editable"] = False
        result["reason"] = READ_ONLY_REASON
    return result, html


def cmd_onenote_page(page_id, check=False):
    with msgraph.background_requests() if check else contextlib.nullcontext(), merge_store(page_id) as journal:
        # Recovery does not depend on the account's page service being online.
        if not check:
            recovered = journal.recover()
            if recovered is not None:
                read_only = resource_read_only("pages", page_id)
                out(dict(recovered, editable=not read_only, markdown=True,
                         reason=READ_ONLY_REASON if read_only else ""))
                return
        remote, html = read_page(page_id)
        if check:
            journal.check_remote(remote)
        result = normalize_note(remote) if check else journal.open(remote)
        out(dict(result, editable=remote["editable"], markdown=True, reason=remote.get("reason", "")))


def cmd_onenote_recording(src, title):
    """One recording's playable file, fetched when the user plays it."""
    if not image_allowed(src):
        fail("This recording is not a OneNote attachment")
    _recording_budget.start()
    url = cached_audio(src, title)
    if not url:
        fail("The recording could not be downloaded. Press Play to try again")
    out({"url": url})


MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff"}
AUDIO_MIME_BY_SUFFIX = {".3gp": "video/3gpp", ".3gpp": "video/3gpp", ".m4a": "audio/mp4",
                        ".mp3": "audio/mpeg", ".mp4": "audio/mp4", ".wav": "audio/wav",
                        ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
                        ".aac": "audio/aac", ".amr": "audio/amr", ".wma": "audio/x-ms-wma",
                        ".flac": "audio/flac", ".webm": "audio/webm"}


class Uploads:
    """The media a save has to carry, and the rules about how much.

    Existing media use their resource identity during planning. Only media
    mentioned by a command are materialized as upload parts. Graph's 4 MB
    limit includes those bytes, so both the count and total size are bounded.
    """

    def __init__(self, upload_known=False, recordings=()):
        self.parts = []          # [(part name, mime, bytes)]
        self.staged = {}         # part name -> local file and durable data-id
        self.bytes = 0
        self.error = ""
        self.image_paths = {}
        self.recordings = {item["src"]: item for item in recordings}
        self.recording_instances = {item["id"]: item for item in recordings if item.get("id")}
        self.audio_paths = {item["src"]: item["local"] for item in recordings}
        # A new page owns no existing resources; creation uploads all media.
        self.upload_known = upload_known

    def ref(self, url, alt):
        """(src for the <img>, width) — the resolver onenote_md renders with."""
        known = known_image(url)
        if known and not self.upload_known:
            self.image_paths[known.get("src", "")] = url
            return known.get("src", ""), known.get("width", 0)
        if known:
            return self.part(file_path_of(url), "image/png", known.get("width", 0))
        if url.startswith(("https://", "http://")):
            return url, 0                       # a public image OneNote fetches itself
        if not url.startswith("file://"):
            return "", 0
        path = file_path_of(url)
        mime = MIME_BY_SUFFIX.get(os.path.splitext(path)[1].lower())
        if not mime:
            self.error = self.error or "only PNG, JPEG, GIF, BMP and TIFF images can be saved to OneNote"
            return "", 0
        return self.part(path, mime, 0)

    def audio_ref(self, url, title, identifier=""):
        """Resolve a recording token, named by its Graph resource, to
        OneNote's attachment object."""
        recording = self.recording_instances.get(identifier)
        if recording is None and not identifier:
            recording = self.recordings.get(url)
        known = known_recording(url)
        mime = (recording or known or {}).get("mime", "") or AUDIO_MIME_BY_SUFFIX.get(
            os.path.splitext(title)[1].lower())
        if not mime or not re.fullmatch(r"audio/[a-z0-9.+-]+|video/3gpp", mime):
            self.error = self.error or "this recording's audio format cannot be saved to OneNote"
            return ""
        if recording and not self.upload_known:
            source = recording["src"]
            self.audio_paths[source] = url
        else:
            source = self.recording_part(url, mime, title, identifier)
            if not source:
                return ""
        identity = ' data-id="%s"' % _html.escape(identifier, quote=True) if identifier else ""
        return '<object data="%s" data-attachment="%s" type="%s"%s></object>' % (
            _html.escape(source, quote=True), _html.escape(title, quote=True), _html.escape(mime, quote=True), identity)

    def recording_part(self, src, mime, title, data_id):
        """Upload a recording again with the bytes of its Graph resource: from
        the cache when it was played, otherwise fetched now. The resource
        comes from the note, and a paste can name any URL, so nothing but
        Graph's resource endpoint is read; never a local file."""
        if not image_allowed(src):
            self.error = self.error or "a recording that did not come from OneNote cannot be saved"
            return ""
        local = cached_audio(src, title)
        if not local:
            self.error = self.error or "a recording could not be downloaded from OneNote to save its copy"
            return ""
        return self.part(file_path_of(local), mime, 0, kind="audio", title=title, source_url=src, data_id=data_id)[0]

    def part(self, path, mime, width, kind="image", title="", source_url="", data_id=""):
        label = "recording" if kind == "audio" else "image"
        if len(self.parts) >= MAX_UPLOAD_PARTS:
            self.error = self.error or "only %d media files can go up in one save" % MAX_UPLOAD_PARTS
            return "", 0
        try:
            with open(path, "rb") as f:
                data = f.read(MAX_UPLOAD + 1)
        except OSError:
            data = b""
        if not data:
            self.error = self.error or "a %s could not be read from disk — open the page again before saving" % label
            return "", 0
        if len(data) > MAX_UPLOAD:
            self.error = self.error or "a %s is larger than %d MB" % (label, MAX_UPLOAD // (1024 * 1024))
            return "", 0
        if self.bytes + len(data) > MAX_UPLOAD_TOTAL:
            self.error = self.error or "the media in this save is larger than Graph accepts at once"
            return "", 0
        name = "nn-%s-%d" % (kind, len(self.parts) + 1)
        self.parts.append((name, mime, data))
        self.staged[name] = {"path": path, "width": width, "kind": kind, "title": title,
                             "mime": mime, "dataId": data_id or "nn-upload-" + uuid.uuid4().hex}
        self.bytes += len(data)
        paths = self.audio_paths if kind == "audio" else self.image_paths
        paths["name:" + name] = source_url or "file://" + path
        return "name:" + name, width

    def materialize(self, commands):
        """Only media included in a command need bytes rather than URLs.

        Independently targeted media stay in place when neighbouring text
        changes. Replacing an inline carrier needs the embedded bytes again.
        """
        return [dict(command, content=self.render_uploads(command["content"])) for command in commands]

    def render_uploads(self, source):
        """Materialize media and label upload parts in a presentation fragment."""
        content = onenote_patch.parse(source)
        for node in onenote_patch.walk(content):
            if node.tag == "img":
                self.materialize_image(node)
                self.label_upload(node, "src")
            elif node.tag == "object":
                self.materialize_recording(node)
                self.label_upload(node, "data")
        return onenote_patch.serialize(content)

    def materialize_image(self, node):
        source = node.attrs.get("src", "")
        local = self.image_paths.get(source)
        if local and not source.startswith("name:"):
            path = file_path_of(local)
            mime = MIME_BY_SUFFIX.get(os.path.splitext(path)[1].lower(), "image/png")
            width = int(float(node.attrs.get("width", "0") or 0))
            node.attrs["src"] = self.part(path, mime, width)[0]

    def materialize_recording(self, node):
        source = node.attrs.get("data", "")
        local = self.audio_paths.get(source)
        if local and not source.startswith("name:"):
            node.attrs["data"] = self.recording_part(local, node.attrs.get("type", ""),
                                                     node.attrs.get("data-attachment", ""),
                                                     node.attrs.get("data-id", ""))

    def label_upload(self, node, attribute):
        if node.attrs.get(attribute, "").startswith("name:"):
            upload = self.staged.get(node.attrs[attribute][5:])
            if upload:
                node.attrs["data-id"] = upload["dataId"]


def multipart(commands, parts):
    """The Commands part plus one part per media file, as Graph requires."""
    boundary = "NoteNotePart" + uuid.uuid4().hex
    body = [("--%s\r\nContent-Disposition: form-data; name=\"Commands\"\r\n"
             "Content-Type: application/json\r\n\r\n%s\r\n" % (boundary, json.dumps(commands))).encode()]
    for name, mime, data in parts:
        body.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n"
                     "Content-Type: %s\r\n\r\n" % (boundary, name, mime)).encode())
        body.append(data + b"\r\n")
    body.append(("--%s--\r\n" % boundary).encode())
    return "multipart/form-data; boundary=" + boundary, b"".join(body)


def patch_page(url, commands, parts):
    # An uncertain insert or upload must not be repeated: the first request
    # may already have added the item. Replacements can retry through a new
    # fetch and merge; they never append another copy to the same anchor.
    if parts:
        content_type, body = multipart(commands, parts)
    else:
        content_type, body = "application/json", json.dumps(commands).encode()
    repeatable = not parts and all(command["action"] == "replace" for command in commands)
    policy = msgraph.RetryPolicy.RESTART if repeatable else msgraph.RetryPolicy.NEVER
    return graph_raw("PATCH", url, body, content_type, retry_policy=policy)


def wrap_runs(runs):
    """Group text for a new page, with media beside the text containers."""
    out = []
    for run in runs:
        if run["kind"] in {"image", "audio"}:
            out.append(run["html"])
        else:
            out.append("<div>%s</div>" % run["html"])
    return "".join(out) or "<div><p></p></div>"




def remove_blank_lines(page_id, runs):
    """Graph has no target for a blank line between two blocks. OneNote's
    web revision service removes it, on the same terms as page order
    (docs/onenote-blank-lines.md)."""
    section = cached_resource("sections", cached_resource("pages", page_id).get("sectionId"))
    if not section or not owns_personal_notebook(section["id"]) or not file_write_granted():
        fail("OneNote's API cannot remove blank lines between paragraphs. Choose Enable page ordering… "
             "to let Note Note remove them, or remove them in OneNote — your draft was kept")
    status, metadata = graph("GET", resource_url("pages", page_id) + "?$select=id,links")
    client_id = page_order.client_guid(metadata) if status == 200 and isinstance(metadata, dict) else None
    if not client_id:
        fail("OneNote did not identify this page to remove its blank lines — your draft was kept")
    try:
        session = web_session.Session.for_section(section, graph)
        blank_lines.remove(session, client_id, runs)
    except web_session.WebError as error:
        fail("Could not remove the blank lines: %s — your draft was kept" % error)


def write_page(page_id, note, remote, current):
    """Write a merge planned against the exact HTML fetched by this save."""
    url = page_content_url(page_id)
    saved_html = current
    if note["body"] != normalize_note(remote)["body"]:
        _recording_budget.start()            # the copies this save fetches
        uploads = Uploads(recordings=remote.get("recordings", []))
        runs = onenote_md.markdown_to_runs(note["body"], uploads.ref, uploads.audio_ref)
        if uploads.error:
            fail(uploads.error)
        image_paths = {item["src"]: item.get("local") for item in remote.get("images", [])}
        image_paths.update(uploads.image_paths)

        def audio_identity(src, local, title, identifier):
            recording = uploads.recordings.get(src)
            return local, identifier or (recording or {}).get("id", "")

        def project(element):
            source = onenote_patch.serialize(element, keep_ids=True)
            displayed = onenote_md.html_to_markdown(source, lambda src, width: image_paths.get(src),
                                                   lambda src, title: uploads.audio_paths.get(src), audio_identity)
            normalized = normalize_note(displayed)
            return onenote_md.markdown_to_onenote_html(normalized["body"], uploads.ref, uploads.audio_ref)

        try:
            planned = onenote_patch.plan(current, "".join(run["html"] for run in runs), project=project)
        except (onenote_patch.UnsupportedEdit, onenote_patch.InvalidPlan) as error:
            fail(str(error) + " — your draft was kept")
        simulated_note = onenote_md.html_to_markdown(planned.simulated, lambda src, width: image_paths.get(src),
                                                    lambda src, title: uploads.audio_paths.get(src), audio_identity)
        if not simulated_note["editable"] or normalize_note(simulated_note)["body"] != note["body"]:
            fail("the proposed update could not preserve this page's content — your draft was kept")
        saved_html = planned.simulated
        commands = uploads.materialize(planned.commands)
        if uploads.error:
            fail(uploads.error)
        if planned.blank_lines:
            # First: Graph commands never target blank lines, so their
            # targets survive this, and the next save plans without them.
            remove_blank_lines(page_id, planned.blank_lines)
        if commands:
            status, res = patch_page(url, commands, uploads.parts)
            if status not in (200, 204):
                try:
                    fail(graph_err(json.loads(res), status))
                except ValueError:
                    fail("Graph error %s" % status)
            if uploads.staged:
                status, content = graph_raw("GET", url + "?includeIDs=true")
                if status == 200:
                    remember_staged(uploads.staged, content)

    # Some older pages reject title writes. Record the successful body and
    # retain the title's draft if that happens, so a retry has the right base.
    warning = ""
    if note["title"] != remote["title"]:
        ops = [{"target": "title", "action": "replace", "content": _html.escape(note["title"])}]
        status, res = graph_raw("PATCH", url, json.dumps(ops).encode(), "application/json",
                                retry_policy=msgraph.RetryPolicy.NEVER)
        if status not in (200, 204):
            try:
                warning = "title not saved: " + graph_err(json.loads(res), status)
            except ValueError:
                warning = "title not saved (Graph error %s)" % status
    remember_search(page_id, saved_html, saved=True)
    return warning


def refuse_unkept_formatting(payload):
    """A save that OneNote would flatten is refused before it is staged: the
    merge store normalises a staged draft, so a check after staging could
    never see the loss. The draft stays with the editor, unsaved."""
    lost = onenote_md.unkept_formatting(payload.get("body", ""))
    if lost:
        fail("this page cannot keep %s; take it out to save — your draft was kept"
             % " or ".join(lost))


def cmd_onenote_update(page_id, path):
    require_writable("pages", page_id)
    payload = read_payload(path)
    if not isinstance(payload, dict):
        fail("cannot read payload")
    refuse_unkept_formatting(payload)
    with merge_store(page_id) as journal:
        journal.stage(payload.get("view", ""), payload)
        remote, current = read_page(page_id)
        if not remote["editable"]:
            fail(remote.get("reason") or "this page now contains content that cannot be saved safely — your draft was kept")
        merged = journal.prepare(remote, payload.get("resolution"))
        if merged["conflict"]:
            out({"error": "This note changed elsewhere. Review the conflicting changes.",
                 "conflict": merged["conflict"]})
            return
        note = merged["note"]
        if normalize_note(note) != note:
            fail("the merged formatting needs review before saving — your draft was kept")
        warning = write_page(page_id, note, remote, current)
        if warning:
            journal.commit(dict(note, title=remote["title"]), accepted_fields=("body",))
            out({"error": warning})
            return
        saved = journal.commit(note)
        out(dict(saved, ok=True, merged=normalize_note(payload) != snapshot(saved)))


def cmd_onenote_create(section_id, path):
    require_writable("sections", section_id)
    # Resolve the recovery identity before making a page. A failed profile
    # read must not leave a newly created page behind an apparent failure.
    merge_account()
    payload = read_payload(path) or {}
    title = _html.escape(payload.get("title", "") or "")
    # A brand-new page has no resources of its own to keep, so everything the
    # note shows goes up as bytes — never as a reference OneNote would copy.
    _recording_budget.start()
    uploads = Uploads(upload_known=True)
    runs = onenote_md.markdown_to_runs(payload.get("body", ""), uploads.ref, uploads.audio_ref)
    if uploads.error:
        fail(uploads.error)
    html = "<!DOCTYPE html><html><head><title>%s</title></head><body>%s</body></html>" % (title, uploads.render_uploads(wrap_runs(runs)))
    if uploads.parts:
        # A page created with media is a multipart POST: the HTML is the
        # "Presentation" part and each media file has one of its own.
        boundary = "NoteNotePart" + uuid.uuid4().hex
        body = [("--%s\r\nContent-Disposition: form-data; name=\"Presentation\"\r\n"
                 "Content-Type: text/html\r\n\r\n%s\r\n" % (boundary, html)).encode()]
        for name, mime, data in uploads.parts:
            body.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n"
                         "Content-Type: %s\r\n\r\n" % (boundary, name, mime)).encode())
            body.append(data + b"\r\n")
        body.append(("--%s--\r\n" % boundary).encode())
        content_type, payload_bytes = "multipart/form-data; boundary=" + boundary, b"".join(body)
    else:
        content_type, payload_bytes = "application/xhtml+xml", html.encode()
    # A 502 or a 504 is the gateway losing the answer to a page Graph may
    # already have made; re-running would leave the user with two or three.
    section = cached_resource("sections", section_id)
    endpoint = notebook_inventory.graph_url(section.get("pagesUrl")) or resource_url("sections", section_id) + "/pages"
    status, res = graph_raw("POST", endpoint,
                            payload_bytes, content_type, retry_policy=msgraph.RetryPolicy.NEVER)
    if status not in (200, 201):
        try:
            fail(graph_err(json.loads(res), status))
        except ValueError:
            fail("Graph error %s" % status)
    pg = json.loads(res)
    # Graph adds a created page at the end of its section as a top-level
    # page, and its answer carries no pagelevel data to say so. Without the
    # level the section's page ordering would stay off until a relisting.
    page = dict(page_record(pg, dict(section, id=section_id)), level=0)
    # A new page goes to the end of its section, which is where OneNote itself
    # puts one and so where the next listing will show it. (It used to go to
    # the front, which was right while the list was newest-first.)
    with listing_lock():
        c = load_listing({"sections": [], "pages": []})
        kept = [p for p in c.get("pages", []) if p["id"] != page["id"]]
        last = max([i for i, p in enumerate(kept) if p.get("sectionId") == section_id],
                   default=len(kept) - 1)
        kept.insert(last + 1, page)
        c["pages"] = kept
        invalidate_page_lists(c, section_id)
        save_listing(c)
    try:
        index = content_index()
        index.sync([page], replace=False)
        index.record(page["id"], search_index.searchable_text(html), saved=True)
    except (OSError, ValueError):
        pass
    with merge_store(page["id"]) as journal:
        note = journal.open({"title": page["title"], "body": payload.get("body", "")})
    out({"ok": True, "page": page, "note": note, "pageListSerial": c["pageListSerial"]})


def cmd_onenote_create_section(notebook_id, path):
    require_writable("notebooks", notebook_id)
    payload = read_payload(path) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        fail("a section needs a name")
    # Not repeatable either, for the same reason a page create is not.
    status, res = graph("POST", resource_url("notebooks", notebook_id) + "/sections",
                        {"displayName": name[:50]}, retry_policy=msgraph.RetryPolicy.NEVER)
    if status not in (200, 201) or "id" not in res:
        fail(graph_err(res, status))
    notebook = cached_resource("notebooks", notebook_id)
    section = notebook_inventory.section_record(res, {"id": notebook_id, "displayName": notebook.get("name", "")})
    section["name"] = res.get("displayName", name)
    with listing_lock():
        c = load_listing()
        if c:
            for sct in c.get("sections", []):
                if sct.get("notebookId") == notebook_id:
                    section["notebook"] = sct.get("notebook", "")
                    break
            c["sections"] = c.get("sections", []) + [section]
            invalidate_page_lists(c)
            save_listing(c)
    out({"ok": True, "section": section, "pageListSerial": (c or {}).get("pageListSerial", 0)})


def cmd_onenote_delete(page_id):
    require_writable("pages", page_id)
    with merge_store(page_id) as journal:
        status, res = graph_raw("DELETE", resource_url("pages", page_id))
        if status not in (204, 200, 404):
            try:
                fail(graph_err(json.loads(res), status))
            except ValueError:
                fail("Graph error %s" % status)
        with listing_lock():
            c = load_listing({"sections": [], "pages": []})
            section = next((p.get("sectionId") for p in c.get("pages", []) if p["id"] == page_id), "")
            c["pages"] = [p for p in c.get("pages", []) if p["id"] != page_id]
            invalidate_page_lists(c, section)
            save_listing(c)
        try:
            content_index().remove(page_id)
        except (OSError, ValueError):
            pass
        journal.discard()
    out({"ok": True, "pageListSerial": c["pageListSerial"]})




def cmd_reorder_pages(payload_path):
    payload = read_payload(payload_path)
    section_id = payload.get("sectionId")
    section = cached_resource("sections", section_id)
    expected, wanted = payload.get("expected"), payload.get("order")
    if (not section or not isinstance(expected, list) or not isinstance(wanted, list)
            or not 1 < len(wanted) <= MAX_PAGES or len(expected) != len(wanted)
            or not all(isinstance(value, str) for value in expected + wanted)
            or len(set(expected)) != len(expected) or set(expected) != set(wanted)):
        fail("invalid page reorder request")
    require_page_ordering(section_id)
    if not file_write_granted():
        fail("Enable page ordering to grant the OneDrive write permission")
    fresh = collect_section_pages(section, lambda url: graph("GET", url, max_bytes=MAX_LIST_BODY))
    if fresh.get("error"):
        fail(fresh["error"], kind=fresh.get("kind"))
    session = web_session.Session.for_section(section, graph)
    # From this point a revision might commit. Neither a follow-up throttle
    # nor a lost response may tell the host to replay this whole command.
    try:
        arranged = page_order.reorder(session, fresh["pages"], expected, wanted)
        final = None
        for delay in ORDER_CONFIRM_DELAYS:
            time.sleep(delay)
            confirmed = collect_section_pages(section, lambda url: graph("GET", url, max_bytes=MAX_LIST_BODY))
            if not confirmed.get("error") and [page["id"] for page in confirmed["pages"]] == [page["id"] for page in arranged]:
                final = confirmed["pages"]
                break
        if final is None:
            raise web_session.WebError("OneNote accepted the order but Graph is still syncing; refresh the section")
    except Exception as error:
        # Whatever ended the command, the revision may have committed, so
        # the cached order is no longer known and the section is listed
        # again. No failure here carries a `kind` the host could replay.
        with listing_lock():
            cache = load_listing() or {}
            invalidate_page_lists(cache, section_id)
            cache.get("sectionPages", {}).pop(section_id, None)
            cache["inventoryComplete"] = False
            save_listing(cache)
        message = str(error) if isinstance(error, msgraph.GraphError) else "Page ordering could not be confirmed; refresh the section"
        fail(message)
    with listing_lock():
        cache = load_listing() or {}
        listing = Listing(cache, cache.get("sections", []))
        current_section = next((value for value in listing.sections if value["id"] == section_id), None)
        if current_section is None:
            fail("The order was saved but the notebook inventory changed; refresh it")
        listing.record(current_section, final)
        listing.revision = uuid.uuid4().hex
        listing.save(listing.complete())
        answer = listing.answer()
    out(dict(answer, ok=True))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "list":
        age = 0
        if "--max-age" in argv:
            try:
                age = int(argv[argv.index("--max-age") + 1])
            except (IndexError, ValueError):
                age = 0
        cmd_onenote_list("--cached" in argv[2:], age, "--force" in argv[2:], "--incremental" in argv[2:])
    elif cmd == "list-step" and len(argv) >= 3:
        cmd_list_step(argv[2])
    elif cmd == "section-order":
        cmd_section_order()
    elif cmd == "reorder-pages" and len(argv) >= 3:
        cmd_reorder_pages(argv[2])
    elif cmd == "pages" and len(argv) >= 3:
        cmd_onenote_pages(argv[2:])
    elif cmd == "page" and len(argv) >= 3:
        cmd_onenote_page(argv[2], "--check" in argv[3:])
    elif cmd == "recording" and len(argv) >= 4:
        cmd_onenote_recording(argv[2], argv[3])
    elif cmd == "update" and len(argv) >= 4:
        cmd_onenote_update(argv[2], argv[3])
    elif cmd == "create" and len(argv) >= 4:
        cmd_onenote_create(argv[2], argv[3])
    elif cmd == "delete" and len(argv) >= 3:
        cmd_onenote_delete(argv[2])
    elif cmd == "create-section" and len(argv) >= 4:
        cmd_onenote_create_section(argv[2], argv[3])
    elif cmd == "search-sync" and len(argv) >= 3:
        cmd_search_sync(argv[2])
    elif cmd == "search-step" and len(argv) >= 3:
        cmd_search_step(argv[2])
    elif cmd == "search" and len(argv) >= 3:
        cmd_search(argv[2])
    elif cmd == "clear-search" and len(argv) >= 3:
        search_index.Index(CACHE_DIR, argv[2]).clear()
        out({"ok": True})
    elif cmd == "clear-cache":
        for path in (ONENOTE_CACHE, ONENOTE_ORDER):
            try:
                os.remove(path)
            except OSError:
                pass
        out({"ok": True})
    else:
        fail("usage: onenote.py list [--cached|--max-age S|--force]|section-order|reorder-pages <file|->|page <id>|recording <src> <title>|update <id> <file>|create <sectionId> <file>|delete <id>|create-section <notebookId> <file>|clear-cache", 2)


def run(argv):
    """The entry point: the one place a failure becomes the JSON error line."""
    try:
        main(argv)
    except SystemExit:
        raise
    except msgraph.GraphError as error:
        fail(str(error), kind=error.kind)
    except StaleRemote:
        fail("OneNote is still syncing the previous save — try again shortly", kind="transient")
    except ratelimit.Throttled as t:
        fail_throttled(t)
    except ratelimit.Deferred as deferred:
        out({"deferred": True, "retryAfter": deferred.retry_after})
    except Exception as e:
        fail("%s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    run(sys.argv)
