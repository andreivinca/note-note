#!/usr/bin/env python3
"""Tests for plugins/org.note-note.notion/notion.py — what a failed save leaves behind.

One property, and it is about a note that still exists after something went
wrong. `cmd_update` replaces a page's body, and it used to do that by deleting
every top-level block first and only then converting the markdown and sending
it back: a conversion and one round trip per hundred blocks during which the
user's page was empty, and any error in that window — a 400 from a block
Notion will not take, the app being killed — left it empty for good.

So the test is not "an update works". It is **no DELETE is ever issued until
every insert has come back 200**, checked by scripting `api` to fail the first
insert and then looking at what was asked of Notion. The happy path is checked
too, for the other half of the same property: the ids deleted at the end are
exactly the ones recorded before the insert, so appending can never lose a
block it just wrote.

No network: `notion.api` is replaced with a recorder, and nothing here reads
or writes a real token, cache or page.

    python3 plugins/org.note-note.notion/selftest.py [-v]
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile

# Point the state and cache directories somewhere harmless before notion.py
# reads them into module constants at import.
WORK = tempfile.mkdtemp(prefix="note-note-notion-selftest-")
os.environ["XDG_STATE_HOME"] = os.path.join(WORK, "state")
os.environ["XDG_CACHE_HOME"] = os.path.join(WORK, "cache")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion  # noqa: E402

FAILURES = []

PAGE_ID = "11111111-2222-3333-4444-555555555555"
TITLE = "Shopping"
OLD_IDS = ["block-one", "block-two", "block-three"]
BODY = "# Milk\n\nand bread\n"


def check(name, ok, detail=""):
    if ok:
        return 0
    FAILURES.append(name + (": " + detail if detail else ""))
    return 1


def run(text, **ann):
    """One rich-text run as Notion answers it."""
    annotations = {"bold": False, "italic": False, "strikethrough": False, "underline": False,
                   "code": False, "color": "default"}
    annotations.update(ann)
    return {"type": "text", "text": {"content": text, "link": None}, "annotations": annotations,
            "plain_text": text, "href": None}


def block(kind, *runs, children=None, **extra):
    """One block as Notion answers it: its text, its properties, its children."""
    made = {"type": kind, kind: dict({"rich_text": list(runs)}, **extra)}
    if children:
        made["children"] = children
    return made


def paragraphs(ids):
    """The page every update below starts from: a paragraph per id, each
    holding its id as its text — a page a save can put back as it is."""
    return [dict(block("paragraph", run(i), color="default"), id=i) for i in ids]


class Notion:
    """A scripted stand-in for `notion.api` that keeps every call it was asked
    to make, in order — the order is the thing under test."""

    def __init__(self, insert_status=200, delete_status=200, create_status=200, old=None):
        self.calls = []
        self.gates = []
        self.insert_status = insert_status
        self.delete_status = delete_status
        self.create_status = create_status
        self.old = paragraphs(OLD_IDS) if old is None else old

    def api(self, method, path, data=None, tok=None, transient_5xx=True):
        self.calls.append((method, path))
        self.gates.append(transient_5xx)
        if method == "PATCH" and path.startswith("/pages/"):
            return 200, {}                      # the title property
        if method == "POST" and path == "/pages":
            return self.create_status, {"id": "made", "properties": {}, "parent": {}}
        if method == "GET" and path.startswith("/pages/"):
            return 200, {"properties": {"Name": {"type": "title",
                                                 "title": [{"plain_text": TITLE}]}}}
        if method == "GET" and path.startswith("/blocks/"):
            return 200, {"results": self.old, "has_more": False}
        if method == "PATCH" and path.endswith("/children"):
            return self.insert_status, {"message": "body failed validation"}
        if method == "DELETE" and path.startswith("/blocks/"):
            return self.delete_status, {}
        raise AssertionError("unscripted call: %s %s" % (method, path))

    def paths(self, method):
        return [path for m, path in self.calls if m == method]

    def deleted(self):
        return [path[len("/blocks/"):] for path in self.paths("DELETE")]

    def inserts(self):
        return [i for i, (m, path) in enumerate(self.calls)
                if m == "PATCH" and path.endswith("/children")]

    def deletes(self):
        return [i for i, (m, _) in enumerate(self.calls) if m == "DELETE"]

    def mutations(self):
        return [(m, path) for m, path in self.calls if m in ("PATCH", "POST", "DELETE")]


def call(fake, command, *args, payload=None):
    """A command against the stub, with `payload` as its payload file if it
    takes one; gives back (what it printed last, exit code)."""
    path = None
    if payload is not None:
        handle, path = tempfile.mkstemp(dir=WORK, suffix=".json")
        with os.fdopen(handle, "w") as f:
            json.dump(payload, f)
        args = args + (path,)
    real, printed, code = notion.api, io.StringIO(), None
    notion.api = fake.api
    try:
        with contextlib.redirect_stdout(printed):
            command(*args)
    except SystemExit as e:
        code = e.code
    finally:
        notion.api = real
        if path:
            os.remove(path)
    lines = printed.getvalue().splitlines()
    return (json.loads(lines[-1]) if lines else {}), code


def run_update(fake, page_id=PAGE_ID, title=TITLE, body=BODY):
    """`cmd_update` against the stub; gives back (what it printed, exit code)."""
    return call(fake, notion.cmd_update, page_id, payload={"title": title, "body": body})


def test_failed_insert_keeps_the_page(verbose):
    """The §1 property: Notion refuses the new body, and the old one is still
    there because nothing was deleted."""
    fake = Notion(insert_status=400)
    answer, code = run_update(fake)
    failures = 0
    failures += check("failed insert reports the failure", code == 1 and "error" in answer,
                      "exit %r, answered %r" % (code, answer))
    failures += check("failed insert deletes nothing", fake.deleted() == [],
                      "deleted %r" % (fake.deleted(),))
    failures += check("failed insert had read the old ids first",
                      any(p.startswith("/blocks/") for p in fake.paths("GET")),
                      "read %r" % (fake.paths("GET"),))
    if verbose:
        print("  after a 400 on the first insert: %r" % (fake.calls,))
    print("a refused insert leaves the page alone")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_happy_path_deletes_what_it_recorded(verbose):
    """And the other half: the ids removed at the end are the ones captured
    before the insert, never anything the insert itself appended."""
    fake = Notion()
    answer, code = run_update(fake)
    failures = 0
    failures += check("update succeeds", code is None and answer == {"ok": True},
                      "exit %r, answered %r" % (code, answer))
    failures += check("deletes exactly the recorded ids", fake.deleted() == OLD_IDS,
                      "deleted %r" % (fake.deleted(),))
    failures += check("every delete comes after every insert",
                      bool(fake.inserts()) and bool(fake.deletes())
                      and min(fake.deletes()) > max(fake.inserts()),
                      "inserts at %r, deletes at %r" % (fake.inserts(), fake.deletes()))
    if verbose:
        print("  calls: %r" % (fake.calls,))
    print("a successful insert removes the blocks it replaced")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_conversion_failure_writes_nothing(verbose):
    """Conversion and limit failures leave both body and title untouched."""
    fake = Notion()
    real = notion.notion_md.markdown_to_blocks

    def explode(_body):
        raise ValueError("no blocks for you")

    notion.notion_md.markdown_to_blocks = explode
    try:
        try:
            answer, _ = run_update(fake, title="Something else")
            raised = False
        except ValueError:
            answer, raised = {}, True
    finally:
        notion.notion_md.markdown_to_blocks = real
    failures = 0
    failures += check("a broken conversion stops the update", raised or bool(answer.get("error")),
                      "answered %r" % (answer,))
    failures += check("a broken conversion leaves the body alone",
                      not fake.paths("DELETE")
                      and not [p for p in fake.paths("PATCH") if p.endswith("/children")],
                      "wrote %r" % (fake.calls,))
    failures += check("conversion failure leaves the title unchanged too",
                      not fake.paths("PATCH"),
                      "unexpected title write: %r" % (fake.calls,))
    if verbose:
        print("  calls: %r" % (fake.calls,))
    print("a body that will not convert never reaches the page")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_path_segments_are_quoted(verbose):
    """§4: ids reach the request path through `quote(..., safe="")`, the way
    onenote.py has always sent them, so an id can never open a path of its own."""
    fake = Notion()
    awkward = "a b/c?d"
    run_update(fake, page_id=awkward)
    quoted = "a%20b%2Fc%3Fd"
    failures = 0
    failures += check("the page id is quoted in every path",
                      all(quoted in path for path in fake.paths("GET") + fake.paths("PATCH")),
                      "%r" % (fake.paths("GET") + fake.paths("PATCH"),))
    failures += check("the raw id reaches no path",
                      not any(awkward in path for _, path in fake.calls),
                      "%r" % (fake.calls,))
    if verbose:
        print("  calls: %r" % (fake.calls,))
    print("ids are quoted into request paths")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def run_create(fake, parent_id="parent-page", title="New", body=BODY):
    """`cmd_create` against the stub; gives back (what it printed, exit code)."""
    return call(fake, notion.cmd_create, parent_id, payload={"title": title, "body": body})


def test_a_create_is_never_repeated(verbose):
    """A create must refuse the "transient" re-run, and a save must accept it.

    `kind: "transient"` re-runs the whole job three times. That is right for a
    body replace, which lands on known ids and is the same operation however
    often it runs — and wrong for `POST /pages`, because a 502 or a 504 is the
    gateway losing the *answer* to a page Notion may already have created. Run
    that again and the user has the same note two or three times.

    So the gate is asserted per request rather than per script: it is the flag
    that decides, and reading it here is what stops a later create being added
    without it.
    """
    made = Notion()
    run_create(made)
    saved = Notion()
    run_update(saved)

    def gate(fake, method, wanted):
        return [g for (m, path), g in zip(fake.calls, fake.gates)
                if m == method and wanted(path)]

    failures = 0
    creates = gate(made, "POST", lambda p: p == "/pages")
    failures += check("a create is asked once and refuses the re-run",
                      creates == [False], "gates %r" % (creates,))
    inserts = gate(saved, "PATCH", lambda p: p.endswith("/children"))
    failures += check("a body replace still allows it",
                      inserts and all(inserts), "gates %r" % (inserts,))
    if verbose:
        print("  create %r, body replace %r" % (creates, inserts))
    print("a create is never repeated, a body replace still may be")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_a_page_opens_for_editing_only_when_a_save_would_put_it_back(verbose):
    """A save replaces every block of the page with the Markdown written
    back, so a page that the writer cannot reproduce — a toggle, a colour,
    text nested under a paragraph, a mention — must open read-only and say
    why. Editability used to be decided by block type alone, so such pages
    were rewritten lossily on the first save.
    """
    import notion_md

    # Every property Notion gives these blocks, at its default — the shape a
    # page the writer made comes back in.
    plain = [block("heading_1", run("Title"), color="default", is_toggleable=False),
             block("paragraph", run("Hello "), run("bold ", bold=True), run("and "), run("mark", color="yellow_background"),
                   color="default"),
             block("to_do", run("task"), checked=True, color="default"), block("divider"),
             block("code", run("x = 1\ny = 2"), language="python", caption=[]), block("quote", run("said"), color="default"),
             block("bulleted_list_item", run("a"), color="default",
                   children=[block("numbered_list_item", run("b"), color="default")]),
             block("paragraph", dict(run("docs"), href="https://example.com")), block("paragraph"),
             block("paragraph"), block("paragraph", run("after two blank lines")),
             block("bulleted_list_item", run("two lines\nin one item"), color="default"),
             block("to_do", run("and in\na to-do"), checked=False, color="default")]
    failures = 0
    failures += check("a page the writer can reproduce opens for editing", notion_md.unwritable(plain) == [],
                      repr(notion_md.unwritable(plain)))
    # Each property of a supported block that Markdown has no syntax for
    # (developers.notion.com/reference/block), and a page holding it.
    lossy = {
        "a toggle block": [block("toggle", run("Details"), children=[block("paragraph", run("hidden"))])],
        "coloured text": [block("paragraph", run("red", color="red"))],
        "text nested under a paragraph": [block("paragraph", run("parent"), children=[block("paragraph", run("child"))])],
        "a mention": [block("paragraph", {"type": "mention", "mention": {}, "plain_text": "@someone", "annotations": {}})],
        "an image block": [block("image")],
        "a code caption": [block("code", run("make"), language="shell", caption=[run("Build it")])],
        "a coloured block": [block("paragraph", run("warning"), color="red_background")],
        "a toggle heading": [block("heading_2", run("Folded"), color="default", is_toggleable=True)],
        "a numbered list that does not start at 1": [block("numbered_list_item", run("third"), list_start_index=3)],
        "a list numbered with letters or roman numerals": [block("numbered_list_item", run("a"), list_format="roman")],
        "a paragraph icon": [block("paragraph", run("tab"), icon={"type": "emoji", "emoji": "x"})],
        "a paragraph sparkle": [block("paragraph", run("new"), sparkle={"on": True})],
    }
    coloured = {
        "heading": [block("heading_1", run("Title"), color="blue")],
        "list item": [block("bulleted_list_item", run("item"), color="green")],
        "to-do": [block("to_do", run("task"), checked=False, color="orange_background")],
        "quote": [block("quote", run("said"), color="gray")],
        "nested list item": [block("bulleted_list_item", run("parent"), color="default",
                                   children=[block("numbered_list_item", run("child"), color="purple")])],
    }
    for name, blocks in coloured.items():
        lossy["a coloured block (%s)" % name] = blocks
    for reason, blocks in lossy.items():
        found = notion_md.unwritable(blocks)
        wanted = reason.split(" (")[0]
        failures += check("a page with %s opens read-only and says so" % reason, found[:1] == [wanted], repr(found))
    return failures


def test_a_page_changed_in_notion_since_it_opened_is_not_saved_over(verbose):
    """The load decides whether a page opens for editing, but a save
    replaces the page as it is when the save runs. Something added in Notion
    in between — a caption, a colour, a toggle — went with the blocks the
    save deleted. The save reads the page first, so it judges that reading."""
    added = paragraphs(OLD_IDS) + [
        dict(block("code", run("make"), language="shell", caption=[run("Build it")]), id="captioned")]
    fake = Notion(old=added)
    answer, code = run_update(fake, title="A new title")
    failures = 0
    failures += check("a save over a page that changed is refused and says why",
                      code == 1 and "a code caption" in answer.get("error", "")
                      and "draft was kept" in answer.get("error", ""), "exit %r, answered %r" % (code, answer))
    failures += check("the refused save writes nothing — no title, no blocks, no deletes",
                      fake.mutations() == [], "wrote %r" % (fake.mutations(),))
    if verbose:
        print("  calls: %r" % (fake.calls,))
    print("a page that changed in Notion since it opened is not saved over")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_a_body_notion_cannot_keep_is_refused(verbose):
    """The writer used to flatten what it had no block for and report the
    save done: a table into "Name | Qty" paragraphs, a picture into its URL,
    coloured text into plain text, and HTML into nothing at all — a body of
    `<div>Keep me</div>` deleted the whole page and answered ok. A save
    replaces the page, so each is refused before Notion is asked anything."""
    bodies = {
        "a table": "Before\n\n| Name | Qty |\n| --- | --- |\n| Milk | 2 |\n",
        "a picture": "see ![cat](https://example.com/cat.png) here\n",
        "coloured text": 'plain <span style="color:#ff0000;">red words</span> end\n',
        "HTML": "<div>Keep me</div>\n",
        "a level-4 heading": "#### Deep\n",
        "a list inside a quote": "> - item\n",
    }
    failures = 0
    for what, body in bodies.items():
        for name, command in (("save", run_update), ("create", run_create)):
            fake = Notion()
            answer, code = command(fake, title="Changed", body=body)
            failures += check("a %s of %s is refused, naming it" % (name, what),
                              code == 1 and ("cannot keep " + what) in answer.get("error", ""),
                              "exit %r, answered %r" % (code, answer))
            failures += check("a refused %s of %s asks Notion nothing" % (name, what),
                              fake.calls == [], "asked %r" % (fake.calls,))
    import notion_md
    kept = notion_md.markdown_to_blocks("- one  \n  two\n- [ ] three  \n  four\n")
    failures += check("a line break in a list item is kept in the item, not glued shut",
                      ["".join(r["text"]["content"] for r in b[b["type"]]["rich_text"]) for b in kept]
                      == ["one\ntwo", "three\nfour"],
                      repr(kept))
    print("a body Notion cannot keep is refused before anything is written")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


class Workspaces(Notion):
    """Two integrations, each the secret of its own workspace with one page:
    the listing answers with the page of whichever secret is set up, read
    the way `api` reads it (`notion.token`)."""

    def api(self, method, path, data=None, tok=None, transient_5xx=True):
        if method == "GET" and path == "/users/me":
            self.calls.append((method, path))
            return 200, {"bot": {"workspace_name": "Workspace of " + tok}}
        if method == "POST" and path == "/search":
            self.calls.append((method, path))
            secret = notion.token()
            return 200, {"results": [{"id": "page-of-" + secret, "parent": {"workspace": True},
                                      "properties": {"t": {"type": "title", "title": [{"plain_text": secret}]}},
                                      "last_edited_time": "2026-10-10T00:00:00Z"}], "has_more": False}
        return super().api(method, path, data, tok, transient_5xx)


class SwitchedMidway(Workspaces):
    """The listing is answered under the secret it was asked with, and the
    user sets up another secret before the answer is written down."""

    def api(self, method, path, data=None, tok=None, transient_5xx=True):
        answer = super().api(method, path, data, tok, transient_5xx)
        if method == "POST" and path == "/search":
            notion.save_private(notion.TOKEN_FILE, {"token": "newer", "workspace": "Newer", "session": "newer"})
        return answer


def listed(answer):
    return [page["id"] for page in answer.get("pages", [])]


def test_a_new_integration_never_shows_the_old_ones_notes(verbose):
    """Setup replaced the secret and kept the listing cached under the old
    one, so the sidebar's first listings — `--cached`, then `--max-age` —
    showed the old workspace's pages under the new one until the next
    forced poll. A run made under the old secret that landed after the
    switch could write them back. The listing now belongs to the
    integration it was fetched under."""
    fake = Workspaces()
    environ = dict(os.environ)
    failures = 0
    try:
        call(fake, notion.cmd_setup, payload={"token": "old"})
        session = call(fake, notion.cmd_status)[0].get("session")
        listing = call(fake, notion.cmd_list, False, 0)[0]
        failures += check("the old integration lists its own page", listed(listing) == ["page-of-old"], repr(listing))
        answer, code = call(fake, notion.cmd_setup, payload={"token": "new"})
        failures += check("setting up another secret gives it a session of its own",
                          code is None and answer.get("session") not in ("", None, session), repr(answer))
        failures += check("the old listing is not the new workspace's cached listing",
                          listed(call(fake, notion.cmd_list, True, 0)[0]) == [], "listed old pages")
        failures += check("a young listing is fetched again rather than read from the old cache",
                          listed(call(fake, notion.cmd_list, False, 300)[0]) == ["page-of-new"], "listed old pages")
        os.environ[notion.SESSION_ENV] = session
        late, code = call(fake, notion.cmd_list, False, 0)
        failures += check("a run made under the old integration is refused once it has gone",
                          code == 1 and "integration changed" in late.get("error", ""), repr(late))
        os.environ[notion.SESSION_ENV] = answer.get("session")
        again = call(fake, notion.cmd_setup, payload={"token": "new"})[0]
        failures += check("the same secret set up again keeps its session and its listing",
                          again.get("session") == answer.get("session")
                          and listed(call(fake, notion.cmd_list, True, 0)[0]) == ["page-of-new"], repr(again))
        call(SwitchedMidway(), notion.cmd_list, False, 0)
        del os.environ[notion.SESSION_ENV]
        failures += check("a listing that lands after another setup is not cached as the new one's",
                          listed(call(fake, notion.cmd_list, True, 0)[0]) == [], "cached the old listing")
    finally:
        os.environ.clear()
        os.environ.update(environ)
        for path in (notion.TOKEN_FILE, notion.CACHE):
            if os.path.exists(path):
                os.remove(path)
    if verbose:
        print("  calls: %r" % (fake.calls,))
    print("a new integration never shows the old one's notes")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    total = 0
    try:
        total += test_failed_insert_keeps_the_page(args.verbose)
        total += test_happy_path_deletes_what_it_recorded(args.verbose)
        total += test_conversion_failure_writes_nothing(args.verbose)
        total += test_path_segments_are_quoted(args.verbose)
        total += test_a_create_is_never_repeated(args.verbose)
        total += test_a_page_opens_for_editing_only_when_a_save_would_put_it_back(args.verbose)
        total += test_a_page_changed_in_notion_since_it_opened_is_not_saved_over(args.verbose)
        total += test_a_body_notion_cannot_keep_is_refused(args.verbose)
        total += test_a_new_integration_never_shows_the_old_ones_notes(args.verbose)
    finally:
        import shutil
        shutil.rmtree(WORK, ignore_errors=True)

    if FAILURES:
        print("\n%d failure(s):" % len(FAILURES))
        for line in FAILURES:
            print("  - " + line)
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
