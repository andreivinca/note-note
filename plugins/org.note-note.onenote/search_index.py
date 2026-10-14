"""Persistent, bounded OneNote search text; no network or image loading.

A separate lock protects atomic JSON replacements across provider processes.
Each read carries an entry revision: a late response cannot undo a save,
inventory change, deletion or sign-out. Only sync() starts a new cache.
"""
import contextlib
import datetime
import fcntl
from html.parser import HTMLParser
import json
import math
import os
import time

from provider_io import save_private

MAX_PAGES = 3000
MAX_TEXT_BYTES = 128 * 1024
MAX_CACHE_BYTES = 16 * 1024 * 1024
REFRESH_SECONDS = 7 * 86400
# The indexer reads one page at a time, slowly, across workers and restarts:
# a page already searchable READ_SPACING seconds after the last read, so
# pages that come due together (a week after a first index) are read minutes
# apart instead of filling the hour's request budget. A page search cannot
# find yet goes FIRST_READ_SPEEDUP times as fast: until it is read, search
# misses it.
READ_SPACING = 180
FIRST_READ_SPEEDUP = 6
SAVE_GRACE_SECONDS = 60
LEASE_SECONDS = 600
VERSION = 1


class TextParser(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "td", "th", "tr", "table", "pre",
              "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
    HIDDEN = {"head", "script", "style", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in self.BLOCKS:
            self.parts.append(" ")
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("https://", "http://", "mailto:")):
                self.parts.append(" " + href + " ")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag in self.BLOCKS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def searchable_text(html):
    parser = TextParser()
    parser.feed(html)
    parser.close()
    text = " ".join("".join(parser.parts).split()).casefold()
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("page text exceeds the search cache limit")
    return text


def empty_state(session=""):
    return {"version": VERSION, "session": session, "serial": 0, "readAt": 0, "entries": {}}


def modified_at(modified):
    """Graph's lastModifiedDateTime in epoch seconds, or None."""
    try:
        moment = datetime.datetime.fromisoformat(modified)
    except ValueError:
        return None
    return moment.timestamp() if moment.tzinfo else None


def read_since(entry, modified):
    """Whether the text was read, or saved, after the page's last change:
    then the listing's newer stamp holds nothing new for search. Graph
    stamps a change by its clock, and `checked` is this one's."""
    changed = modified_at(modified)
    return isinstance(entry.get("text"), str) and changed is not None and entry.get("checked", 0) >= changed


def paced_at(state, entry, now):
    """When the pace lets `entry` be read: READ_SPACING after the last read,
    FIRST_READ_SPEEDUP times as soon for a page not searchable yet. A stamp
    ahead of the clock (it was set back) holds nothing back."""
    last = state.get("readAt", 0)
    if last > now:
        return 0
    if isinstance(entry.get("text"), str):
        return last + READ_SPACING
    return last + READ_SPACING / FIRST_READ_SPEEDUP


def due_at(entry):
    checked = entry.get("checked", 0)
    due = checked + REFRESH_SECONDS if checked else 0
    lease = entry.get("leaseUntil", 0)
    if lease and not process_alive(entry.get("leasePid", 0)):
        lease = 0
    return max(due, entry.get("retryAt", 0), entry.get("holdUntil", 0), lease)


def ready_at(state, entry, now):
    """When `entry` may be read: its own due time, and the pace."""
    return max(due_at(entry), paced_at(state, entry, now))


def process_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def select_page(state, preferred_sections, now):
    candidates = [(page_id, entry) for page_id, entry in state["entries"].items()
                  if ready_at(state, entry, now) <= now]
    if not candidates:
        return None
    page_id, entry = min(candidates, key=lambda pair: (
        pair[1].get("text") is not None, pair[1]["sectionId"] not in preferred_sections,
        pair[1].get("checked", 0)))
    return {"id": page_id, "revision": entry["revision"]}


def summary(state, now):
    result = {"total": 0, "indexed": 0, "pending": 0, "failed": 0, "sections": {},
              "serial": state["serial"]}
    delays = []
    for entry in state["entries"].values():
        section = result["sections"].setdefault(entry["sectionId"],
                    {"total": 0, "indexed": 0, "pending": 0, "failed": 0})
        indexed = isinstance(entry.get("text"), str)
        # Only a page search cannot find yet is pending: the slow refresh of
        # a searchable one is upkeep, not progress to show.
        pending = not indexed
        failed = pending and entry.get("failures", 0) > 0
        for counts in (result, section):
            counts["total"] += 1
            counts["indexed"] += int(indexed)
            counts["pending"] += int(pending)
            counts["failed"] += int(failed)
        delays.append(max(0, ready_at(state, entry, now) - now))
    result["nextDelay"] = min(delays, default=3600)
    return result


class Index:
    def __init__(self, directory, session, valid=lambda: True, now=time.time):
        self.path = os.path.join(directory, "note-note-onenote-search.json")
        self.session = session
        self.valid = valid
        self.now = now

    @contextlib.contextmanager
    def locked(self):
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def read(self):
        try:
            with open(self.path, "rb") as source:
                raw = source.read(MAX_CACHE_BYTES + 1)
            if len(raw) > MAX_CACHE_BYTES:
                raise ValueError("search cache exceeds its size limit")
            state = json.loads(raw)
        except FileNotFoundError:
            return empty_state()
        except (ValueError, UnicodeError):
            return empty_state()
        if (not isinstance(state, dict) or state.get("version") != VERSION
                or not isinstance(state.get("entries"), dict)
                or len(state["entries"]) > MAX_PAGES
                or not isinstance(state.get("serial"), int)
                or not isinstance(state.get("session"), str)
                or not isinstance(state.get("readAt", 0), (int, float))
                or not math.isfinite(state.get("readAt", 0)) or state.get("readAt", 0) < 0):
            return empty_state()
        for page_id, entry in state["entries"].items():
            if (not isinstance(page_id, str) or not isinstance(entry, dict)
                    or not isinstance(entry.get("sectionId"), str)
                    or not isinstance(entry.get("modified"), str)
                    or not isinstance(entry.get("revision"), int)
                    or not isinstance(entry.get("leasePid", 0), int)
                    or any(not isinstance(entry.get(key, 0), (int, float))
                           or not math.isfinite(entry.get(key, 0)) or entry.get(key, 0) < 0
                           for key in ("checked", "retryAt", "holdUntil", "leaseUntil", "failures"))
                    or (entry.get("text") is not None and not isinstance(entry["text"], str))):
                return empty_state()
            if isinstance(entry.get("text"), str) and len(entry["text"].encode("utf-8")) > MAX_TEXT_BYTES:
                return empty_state()
        return state

    def write(self, state):
        state["serial"] += 1
        if len(state["entries"]) > MAX_PAGES or len(json.dumps(state).encode("utf-8")) > MAX_CACHE_BYTES:
            raise ValueError("search cache is full")
        save_private(self.path, state)

    def current(self, state):
        return bool(self.session and state["session"] == self.session and self.valid())

    def sync(self, pages, replace=True):
        if not isinstance(pages, list) or len(pages) > MAX_PAGES:
            raise ValueError("invalid search inventory")
        inventory = {}
        for page in pages:
            if (not isinstance(page, dict) or not isinstance(page.get("id"), str)
                    or not page["id"] or not isinstance(page.get("sectionId"), str)
                    or not isinstance(page.get("modified", ""), str)):
                raise ValueError("invalid search page")
            inventory[page["id"]] = page
        with self.locked():
            if not self.session or not self.valid():
                return summary(empty_state(), self.now())
            state = self.read()
            if state["session"] != self.session:
                state = empty_state(self.session)
            previous = state["entries"]
            entries = {} if replace else dict(previous)
            for page_id, page in inventory.items():
                entry = previous.get(page_id)
                modified = page.get("modified", "")
                if entry is None:
                    state["serial"] += 1
                    entry = {"text": None, "checked": 0, "retryAt": 0, "holdUntil": 0,
                             "failures": 0, "revision": state["serial"], "modified": modified}
                elif entry["modified"] != modified:
                    state["serial"] += 1
                    entry.update(modified=modified, revision=state["serial"])
                    if not read_since(entry, modified):
                        entry.update(checked=0, retryAt=0, failures=0, leaseUntil=0)
                entry["sectionId"] = page["sectionId"]
                entries[page_id] = entry
            state["entries"] = entries
            self.write(state)
            return summary(state, self.now())

    def snapshot(self):
        with self.locked():
            state = self.read()
            return state if self.current(state) else empty_state()

    def status(self):
        return summary(self.snapshot(), self.now())

    def ticket(self, page_id):
        entry = self.snapshot()["entries"].get(page_id)
        return {"id": page_id, "revision": entry["revision"]} if entry else None

    def next_page(self, preferred_sections):
        return select_page(self.snapshot(), preferred_sections, self.now())

    def claim_page(self, preferred_sections):
        """Choose distinct pages across workers; crashed workers' leases expire."""
        with self.locked():
            state = self.read()
            if not self.current(state):
                return None
            ticket = select_page(state, preferred_sections, self.now())
            if ticket is None:
                return None
            entry = state["entries"][ticket["id"]]
            state["readAt"] = self.now()
            state["serial"] += 1
            ticket["revision"] = state["serial"]
            entry.update(revision=ticket["revision"], leasePid=os.getpid(),
                         leaseUntil=self.now() + LEASE_SECONDS)
            self.write(state)
            return ticket

    def record(self, page_id, text, ticket=None, saved=False):
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("page text exceeds the search cache limit")
        with self.locked():
            state = self.read()
            entry = state["entries"].get(page_id)
            if not self.current(state) or entry is None:
                return False
            if not saved and (not ticket or ticket["revision"] != entry["revision"]
                              or self.now() < entry.get("holdUntil", 0)):
                return False
            state["serial"] += 1
            entry.update(text=text, checked=self.now(), retryAt=0, failures=0, leaseUntil=0,
                         holdUntil=self.now() + SAVE_GRACE_SECONDS if saved else 0,
                         revision=state["serial"])
            self.write(state)
            return True

    def release(self, ticket):
        """A budget deferral did not fail the page, earn a retry backoff or
        spend a read: the pace owes it nothing."""
        with self.locked():
            state = self.read()
            entry = state["entries"].get(ticket["id"])
            if not self.current(state) or not entry or entry["revision"] != ticket["revision"]:
                return
            entry["leaseUntil"] = 0
            state["readAt"] = 0
            self.write(state)

    def failed(self, ticket, status=0):
        with self.locked():
            state = self.read()
            entry = state["entries"].get(ticket["id"])
            if not self.current(state) or not entry or entry["revision"] != ticket["revision"]:
                return
            failures = min(entry.get("failures", 0) + 1, 10)
            entry.update(failures=failures, leaseUntil=0,
                         retryAt=self.now() + min(300 * 2 ** (failures - 1), 86400))
            if status in (403, 404):
                entry.update(text=None, checked=0)
            self.write(state)

    def remove(self, page_id):
        with self.locked():
            state = self.read()
            if self.current(state) and page_id in state["entries"]:
                del state["entries"][page_id]
                self.write(state)

    def search(self, query):
        state = self.snapshot()
        needle = " ".join(query.split()).casefold()
        paths = [page_id for page_id, entry in state["entries"].items()
                 if needle and needle in (entry.get("text") or "")]
        return {"ids": paths, "status": summary(state, self.now())}

    def clear(self):
        with self.locked():
            # A delayed cleanup for an old sign-in must not remove the new one.
            state = self.read()
            if self.session and state["session"] != self.session:
                return
            with contextlib.suppress(FileNotFoundError):
                os.remove(self.path)
