#!/usr/bin/env python3
"""Tests for plugins/org.note-note.local/list.py — the order a notebook's notes come in.

The property is that a note sits where it was created and that editing it
moves nothing. It had never held. `os.stat()` carries `st_birthtime` only
where the platform's own `struct stat` does, which on Linux it does not, so
the birth key was the `getattr` default — 0 for every note — and the order
fell entirely to a tie-break built by formatting size, mtime and name into
one string. A string compares as text, so `100` sorted before `80` sorted
before `9`, and a note changed places as it was typed into. Both halves are
covered here: that a birth time is really read, and that the key is really
numeric.

Ground truth for a birth time is coreutils' `stat -c %W`, which reads one
through a statx(2) call of its own. It shares no struct definition with
list.py, so agreeing with it is what checks the ctypes layout — a layout
wrong by eight bytes still hands back a plausible-looking timestamp, which no
self-consistent test would catch.

Two legs need a birth time to exist. Where the filesystem records none, or
`stat` is not installed, they print a skip rather than fail: falling back to
the modification time is then the module's correct behaviour, not a fault.
Those legs are the ones that distinguish birth time from mtime; everything
else runs everywhere.

Creating notes in a known *order* means creating them in distinct seconds,
and a birth time cannot be set the way `os.utime` sets an mtime, so this
sleeps about a second per note it has to order.

The note format (notefile.py) is covered through every script that reads
it — the listing, the search, the load and the save — for the line endings
and byte-order mark a note written by another editor may carry.

The image test belongs to services/markdown/qthtml/imagesize.py rather than to
this directory. It is here because it is the same shape of property — a
listing that cannot be steered out of the notebook, and an image reference
that cannot be steered out of the note's folder — and because that module has
no cheaper place to assert it from.

    python3 plugins/org.note-note.local/selftest.py [-v]
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "services", "markdown"))
import list as listing  # noqa: E402
from qthtml.imagesize import local_path  # noqa: E402

FAILURES = []

# A second and a bit: long enough that two files land in different whole
# seconds, which is the resolution list.py sorts on.
TICK = 1.05

# The listing run with statx(2) taken away, which is the only way to reach the
# fallback on a kernel that has it. Nothing in list.py knows about this; the
# child reaches in and clears the entry point the module resolved at import.
NO_STATX = r"""
import sys
sys.path.insert(0, %r)
import list as listing
listing._statx = None
root = sys.argv[1]
sys.argv = ["list.py", root, "1000000"]
listing.main()
""" % HERE


def check(name, ok, detail=""):
    if ok:
        return 0
    FAILURES.append(name + (": " + detail if detail else ""))
    return 1


def skipped(name, reason):
    print("  SKIPPED %s: %s" % (name, reason))
    return 0


def note(root, name, size):
    """A note of exactly `size` bytes. The size is what the old string key
    sorted on, so it is precisely the thing the order must ignore."""
    path = os.path.join(root, name)
    with open(path, "wb") as handle:
        handle.write(b"x" * size)
    return path


def listed(root, statx=True):
    """The note names list.py emits, in the order it emits them — run as the
    child process it really is, so the test sees what Provider.qml sees."""
    argv = ([sys.executable, os.path.join(HERE, "list.py"), root, "1000000"] if statx
            else [sys.executable, "-c", NO_STATX, root])
    done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.decode()[-400:])
    names = []
    for line in done.stdout.decode().split("\n"):
        fields = line.split("\t")
        if fields[0] == "N":
            names.append(os.path.basename(fields[2]))
    return names


def coreutils_birth(path):
    """The birth time `stat` reports, whole seconds, or 0 when there is none
    to report — an older filesystem, or no `stat` on this machine. Like the
    module under test, it does not follow a symlink."""
    try:
        done = subprocess.run(["stat", "-c", "%W", "--", path], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 0
    text = done.stdout.decode().strip()
    return int(text) if text.isdigit() else 0


def test_first_notebook(directory, verbose):
    root = os.path.join(directory, "fresh")
    failures = check("first run lists the getting-started note", listed(root) == ["Getting started.md"])
    path = os.path.join(root, "Notes", "Getting started.md")
    with open(path, encoding="utf-8") as handle:
        title, body, _ = listing.notefile.split(handle.read())
    failures += check("starter note has its own title", title == "Getting started")
    failures += check("starter note includes a short formatted guide", "| Shortcut | Action |" in body and "- [ ]" in body)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("my edited introduction")
    listed(root)
    with open(path, encoding="utf-8") as handle:
        failures += check("refresh preserves an edited starter note", handle.read() == "my edited introduction")
    os.unlink(path)
    failures += check("refresh does not restore a deleted starter note", listed(root) == [])

    existing = os.path.join(directory, "existing-root")
    os.makedirs(existing)
    note(existing, "mine.md", 10)
    failures += check("root notes keep their existing notebook", listed(existing) == ["mine.md"] and not os.path.exists(os.path.join(existing, "Notes")))
    empty = os.path.join(directory, "existing-empty-notebook")
    os.makedirs(os.path.join(empty, "Work"))
    failures += check("existing empty notebooks are preserved", listed(empty) == [] and not os.path.exists(os.path.join(empty, "Notes")))
    blocked = os.path.join(directory, "blocked-first-notebook")
    os.makedirs(blocked)
    os.symlink(existing, os.path.join(blocked, "Notes"))
    try:
        listing.ensure_notebook(blocked)
    except FileExistsError:
        pass
    else:
        failures += check("initialization refuses a symlinked default notebook", False)
    failures += check("default notebook cannot write through a symlink", not os.path.exists(os.path.join(existing, "Getting started.md")))
    print("first-run notebook and starter note")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_struct_layout(directory, verbose):
    """The ctypes `struct statx` against the one the kernel writes."""
    failures = 0
    failures += check("struct statx is 256 bytes", ctypes.sizeof(listing._Statx) == 256,
                      "%d" % ctypes.sizeof(listing._Statx))
    failures += check("stx_atime at 64", listing._Statx.stx_atime.offset == 64,
                      "%d" % listing._Statx.stx_atime.offset)
    failures += check("stx_btime at 80", listing._Statx.stx_btime.offset == 80,
                      "%d" % listing._Statx.stx_btime.offset)

    # The fields ahead of stx_btime are what place it at its offset, so
    # reading them back from a real call and finding os.stat's own answers
    # there is the check that matters: if these three landed, so did the
    # birth time.
    if listing._statx is None:
        failures += skipped("live layout", "no statx(2) to call on this machine")
    else:
        path = note(directory, "layout.md", 41)
        info = listing._Statx()
        rc = listing._statx(listing.AT_FDCWD, os.fsencode(path),
                            listing.AT_SYMLINK_NOFOLLOW, listing.STATX_BTIME,
                            ctypes.byref(info))
        st = os.stat(path)
        failures += check("statx returns 0", rc == 0, "errno %d" % ctypes.get_errno())
        failures += check("stx_size lands", info.stx_size == st.st_size,
                          "%d vs %d" % (info.stx_size, st.st_size))
        failures += check("stx_ino lands", info.stx_ino == st.st_ino,
                          "%d vs %d" % (info.stx_ino, st.st_ino))
        failures += check("stx_mode lands", info.stx_mode == st.st_mode,
                          "%o vs %o" % (info.stx_mode, st.st_mode))
        if verbose:
            print("  mask %#x, btime %d.%09d" % (info.stx_mask, info.stx_btime.tv_sec,
                                                 info.stx_btime.tv_nsec))
    print("struct statx layout")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_birth_time(directory, verbose):
    """birth_time() against `stat`, and against a symlink it must not follow."""
    failures = 0
    root = os.path.join(directory, "birth")
    os.makedirs(root)

    target = note(root, "target.md", 10)
    truth = coreutils_birth(target)
    if not truth:
        return skipped("birth time", "nothing records one here (%s)" % root) or failures
    failures += check("birth_time agrees with stat", listing.birth_time(target) == truth,
                      "%d vs %d" % (listing.birth_time(target), truth))
    if verbose:
        print("  birth_time %d, stat -c %%W %d" % (listing.birth_time(target), truth))

    # The listing refuses symlinked notes precisely so that another file's
    # bytes cannot reach it. Reading a birth time must not be the one call
    # that walks through one, so the link's own time is the answer.
    time.sleep(TICK)
    link = os.path.join(root, "link.md")
    os.symlink(target, link)
    failures += check("symlink is not followed", listing.birth_time(link) == coreutils_birth(link),
                      "%d vs %d" % (listing.birth_time(link), coreutils_birth(link)))
    failures += check("symlink has its own birth time", listing.birth_time(link) != truth,
                      "both %d" % truth)

    failures += check("a missing file has no birth time",
                      listing.birth_time(os.path.join(root, "gone.md")) == 0)
    print("birth_time against stat")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_listing_order(directory, verbose):
    """The finding itself: three notes, listed where they were created."""
    failures = 0
    root = os.path.join(directory, "order")
    os.makedirs(root)

    # Sizes 9, 80 and 100, dealt out so that creation order matches nothing
    # else: not the names (a, m, z), not ascending size (a, m, z), and not the
    # old key's text order, which put "100" before "80" before "9" and so
    # answered z, m, a.
    order = [("m.md", 80), ("a.md", 9), ("z.md", 100)]
    for i, (name, size) in enumerate(order):
        if i:
            time.sleep(TICK)
        note(root, name, size)
    want = [name for name, _ in order]

    got = listed(root)
    failures += check("listed in creation order", got == want, "%r" % got)
    if verbose:
        print("  created %r, listed %r" % (want, got))

    # Now make the modification times run backwards. Only a real birth time
    # can still answer the creation order, so this is the leg that says the
    # statx read is doing the work rather than mtime standing in for it.
    if not coreutils_birth(os.path.join(root, "m.md")):
        failures += skipped("birth time outranks mtime", "no birth time on this filesystem")
    else:
        base = time.time()
        for i, name in enumerate(reversed(want)):
            stamp = base + i
            os.utime(os.path.join(root, name), (stamp, stamp))
        got = listed(root)
        failures += check("birth time outranks mtime", got == want, "%r" % got)
    print("three notes in creation order")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_numeric_key(directory, verbose):
    """Two sizes across a digit boundary: 9 and 80, which text sorts wrong."""
    failures = 0
    root = os.path.join(directory, "numeric")
    os.makedirs(root)

    small = note(root, "p.md", 9)
    time.sleep(TICK)
    note(root, "q.md", 80)

    # Under the old key these came back q, p, because "80" sorts under "9".
    got = listed(root)
    failures += check("9 bytes before 80 bytes", got == ["p.md", "q.md"], "%r" % got)

    # Typing into the smaller note carries it across the boundary — 9 to 200 —
    # which is what used to move it. Its birth time has not changed, so its
    # place must not either.
    with open(small, "wb") as handle:
        handle.write(b"x" * 200)
    if not coreutils_birth(small):
        failures += skipped("an edit moves nothing", "no birth time on this filesystem")
    else:
        got = listed(root)
        failures += check("an edit moves nothing", got == ["p.md", "q.md"], "%r" % got)
    if verbose:
        print("  after growing p.md from 9 to 200 bytes: %r" % got)
    print("a numeric sort key")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_fallback(directory, verbose):
    """With no statx(2) at all: an order, not an exception."""
    failures = 0
    root = os.path.join(directory, "fallback")
    os.makedirs(root)

    # Explicit modification times, so this leg needs no sleeping and holds the
    # same on a machine where every note really was created in one second.
    base = time.time()
    for i, (name, size) in enumerate([("z.md", 9), ("m.md", 100), ("a.md", 80)]):
        note(root, name, size)
        os.utime(os.path.join(root, name), (base + i, base + i))
    want = ["z.md", "m.md", "a.md"]

    got = listed(root, statx=False)
    failures += check("fallback lists in mtime order", got == want, "%r" % got)
    if verbose:
        print("  without statx: %r" % got)

    kept = listing._statx
    try:
        listing._statx = None
        failures += check("birth_time answers 0 rather than raising",
                          listing.birth_time(os.path.join(root, "z.md")) == 0)
    finally:
        listing._statx = kept
    print("the fallback to mtime")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def stream(root, budget):
    """The raw lines list.py emits for `root` under a byte budget."""
    done = subprocess.run([sys.executable, os.path.join(HERE, "list.py"), root, str(budget)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.decode()[-400:])
    return [line for line in done.stdout.decode().split("\n") if line]


FIELDS = {"B": 2, "D": 2, "O": 3, "N": 7, "X": 3}


def unescaped(field):
    """A field as list.py wrote it, read back the way Provider.qml does."""
    return re.sub(r"\\(.)", lambda m: {"t": "\t", "n": "\n"}.get(m.group(1), m.group(1)), field)


def test_exact_names(directory, verbose):
    """A name is listed exactly as the file system has it. The listing once
    collapsed the spaces in every field, so two notes could share one
    listed path — and the wrong one opened or went; a tab in a name would
    have broken the record it sat in."""
    root = os.path.join(directory, "names")
    book = os.path.join(root, "two  spaces")
    os.makedirs(book)
    names = ["two  spaces.md", "two spaces.md", "tab\there.md", "back\\slash.md"]
    for name in names:
        note(book, name, 8)
    with open(os.path.join(book, "two  spaces.md"), "w") as handle:
        handle.write("---\ntitle: two  spaces\n---\nbody\n")
    with open(os.path.join(book, ".order"), "w") as handle:
        handle.write("tab\there.md\n")
    failures = 0
    lines = stream(root, 1000000)
    failures += check("every record is whole", all(len(line.split("\t")) == FIELDS[line[0]] for line in lines[:-1]), repr(lines))
    records = [[unescaped(field) for field in line.split("\t")] for line in lines]
    listed = sorted(os.path.basename(r[2]) for r in records if r[0] == "N")
    failures += check("every name is listed exactly as the file system has it", listed == sorted(names), repr(listed))
    failures += check("a notebook key is exact", [r[1] for r in records if r[0] == "D"] == ["", "two  spaces"], repr(records))
    failures += check("a saved order entry is exact", [r[2] for r in records if r[0] == "O"] == ["tab\there.md"], repr(records))
    titles = [r[3] for r in records if r[0] == "N" and r[2].endswith("/two  spaces.md")]
    failures += check("a title keeps its spacing", titles == ["two  spaces"], repr(titles))
    print("exact names")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_listing_end_record(directory, verbose):
    """The last line says whether the listing can be trusted. Cut by its
    budget, a listing used to look exactly like a complete one, and the
    order file was then rewritten from it without the notes it never
    reached; a notebook it could not read was listed as empty."""
    root = os.path.join(directory, "ending")
    os.makedirs(os.path.join(root, "Book"))
    for index in range(6):
        note(root, "note-%d.md" % index, 20)
        note(os.path.join(root, "Book"), "book-%d.md" % index, 20)
    failures = 0
    whole = stream(root, 1000000)
    failures += check("a whole listing ends by saying so", whole[-1] == "E\tcomplete", repr(whole[-1:]))
    failures += check("a whole listing names every note", sum(line.startswith("N\t") for line in whole) == 12)
    cut = stream(root, 700)
    failures += check("a listing over its budget ends by saying so and why",
                      cut[-1].startswith("E\tpartial\tthe listing is larger than 700"), repr(cut[-1:]))
    failures += check("a cut listing stops short rather than growing past its budget",
                      0 < sum(line.startswith("N\t") for line in cut) < 12, repr(cut))
    failures += check("every line of a cut listing is a whole record",
                      all(len(line.split("\t")) == FIELDS[line[0]] for line in cut[:-1]), repr(cut))
    if os.geteuid() == 0:
        skipped("an unreadable notebook", "running as root, which can read anything")
    else:
        os.chmod(os.path.join(root, "Book"), 0)
        try:
            shut = stream(root, 1000000)
        finally:
            os.chmod(os.path.join(root, "Book"), 0o700)
        failures += check("an unreadable notebook is reported, not listed as empty",
                          any(line.startswith("X\tBook\t") for line in shut)
                          and not any(line.startswith("N\tBook\t") for line in shut), repr(shut))
        failures += check("the rest of the listing is still complete", shut[-1] == "E\tcomplete")
    print("the listing's last line")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def operation(root, **payload):
    """operations.py's answer, run as the child process Provider.qml runs."""
    payload["root"] = root
    done = subprocess.run([sys.executable, os.path.join(HERE, "operations.py")],
                          input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=60)
    return json.loads(done.stdout.decode())


def found(root, query):
    """The note names search.py answers for `query`, sorted."""
    done = subprocess.run([sys.executable, os.path.join(HERE, "search.py"), root, query, "1000000"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    return sorted(os.path.basename(line) for line in done.stdout.decode().split("\n") if line)


def test_line_endings(directory, verbose):
    """A note written elsewhere — CRLF line endings, lone CRs, a UTF-8
    byte-order mark — has the same front matter as one with plain LF. The
    format read a fence only as `---` before a `\\n`, so such a note was all
    body: the sidebar previewed "title: Shopping", and the first save wrote
    a second block above the first, which then stayed in the body for good
    while outside tools lost the `tags:` they had written."""
    root = os.path.join(directory, "endings")
    book = os.path.join(root, "Work")
    os.makedirs(book)
    # name: the bytes on disk, the title, the line the app does not own, the
    # body as loaded (kept exactly), its preview, and the body the editor
    # hands back on save — its own Markdown, which has LF.
    notes = {
        "crlf.md": (b"---\r\ntitle: Shopping\r\ntags: [home]\r\n---\r\nMilk\r\nEggs\r\n",
                    "Shopping", "tags: [home]", "Milk\r\nEggs\r\n", "Milk", "Milk\nEggs\n"),
        "cr.md": (b"---\rtitle: Market\rtags: [town]\r---\rFish\rChips\r",
                  "Market", "tags: [town]", "Fish\rChips\r", "Fish", "Fish\nChips\n"),
        "bom.md": (b"\xef\xbb\xbf---\ntitle: Bakery\ntags: [bread]\n---\nRye\n",
                   "Bakery", "tags: [bread]", "Rye\n", "Rye", "Rye\n"),
    }
    for name, (raw, _, _, _, _, _) in notes.items():
        with open(os.path.join(book, name), "wb") as handle:
            handle.write(raw)
    failures = 0

    records = [line.split("\t") for line in stream(root, 1000000) if line.startswith("N\t")]
    heads = {os.path.basename(r[2]): (r[3], r[4]) for r in records}
    for name, (_, title, _, _, preview, _) in notes.items():
        failures += check("%s lists its title and its first body line" % name,
                          heads.get(name) == (title, preview), repr(heads.get(name)))

    failures += check("the search does not read a front matter as body",
                      found(root, "title") == [] and found(root, "tags") == [],
                      repr((found(root, "title"), found(root, "tags"))))
    failures += check("the search still reads the body after one",
                      found(root, "eggs") == ["crlf.md"] and found(root, "chips") == ["cr.md"])

    for name, (_, title, kept, body, _, edited) in notes.items():
        path = os.path.join(book, name)
        loaded = operation(root, action="read", file=path)
        failures += check("%s loads its title and its body as written" % name,
                          (loaded.get("title"), loaded.get("body")) == (title, body), repr(loaded))
        saved = operation(root, action="save", file=path, title=title, body=edited)
        failures += check("%s saves" % name, saved.get("ok") is True, repr(saved))
        with open(path, "rb") as handle:
            written = handle.read().decode("utf-8")
        failures += check("%s saves one front matter, its own line kept" % name,
                          written == "---\ntitle: %s\n%s\n---\n%s" % (title, kept, edited), repr(written))
        again = operation(root, action="read", file=path)
        failures += check("%s reloads as it was saved" % name,
                          (again.get("title"), again.get("body")) == (title, edited), repr(again))
    print("line endings and a byte-order mark")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_image_escape(directory, verbose):
    """An `<img src>` that climbs out of the note's folder measures nothing."""
    failures = 0
    base = os.path.join(directory, "notebook")
    cases = [
        ("../../x.png", ""),
        ("../x.png", ""),
        ("a/../../x.png", ""),
        ("..", ""),
        ("%2Fetc%2Fpasswd", ""),                       # absolute only once unquoted
        (".assets/paste-1.png", os.path.join(base, ".assets/paste-1.png")),
        ("shot.png", os.path.join(base, "shot.png")),
    ]
    for url, want in cases:
        got = local_path(url, base)
        failures += check("local_path(%r)" % url, got == want, "%r" % got)

    # A relative base still resolves: the containment is decided on the src,
    # so it never depends on the base being absolute.
    failures += check("a relative base still resolves", local_path("x.png", ".") == "./x.png",
                      "%r" % local_path("x.png", "."))
    failures += check("a file:// url is untouched",
                      local_path("file:///tmp/a.png") == "/tmp/a.png")
    print("an image reference stays in the note's folder")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def test_unkept_opens_read_only(directory, verbose):
    """A note holding what the editor would not write back as it is — raw
    HTML, a heading inside a quote — opens read-only and says why. Its
    first save used to write the editor's version over it: the HTML gone,
    the heading out of its quote. Run as the child process Provider.qml
    runs, so the answer checked is the one the provider reads."""
    failures = 0
    root = os.path.join(directory, "unkept")
    os.makedirs(root)
    cases = [
        ("plain.md", "# Shopping\n\n- [ ] milk\n\n> a quote\n", True, ""),
        ("html.md", "Before\n\n<div>Keep me</div>\n\nAfter\n", False, "HTML"),
        ("quoted.md", "> # Heading\n> text\n", False, "a quoted heading"),
    ]
    for name, body, editable, named in cases:
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("---\ntitle: %s\n---\n%s" % (name, body))
        request = json.dumps({"action": "read", "root": root, "file": path})
        done = subprocess.run([sys.executable, os.path.join(HERE, "operations.py")], input=request,
                              capture_output=True, text=True, timeout=60)
        answer = json.loads(done.stdout or "{}")
        failures += check("%s reads back as written" % name, answer.get("body") == body, repr(answer))
        failures += check("%s opens %s" % (name, "editable" if editable else "read-only"),
                          answer.get("editable") is editable, repr(answer))
        failures += check("%s gives %s" % (name, "a reason naming " + named if named else "no reason"),
                          (named in answer.get("reason", "")) if named else answer.get("reason") == "",
                          repr(answer.get("reason")))
    print("a note the editor cannot write back opens read-only")
    print("  %d checks failed" % failures if failures else "  all green")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="note-note-local-selftest-") as directory:
        total = 0
        total += test_first_notebook(directory, args.verbose)
        total += test_struct_layout(directory, args.verbose)
        total += test_birth_time(directory, args.verbose)
        total += test_listing_order(directory, args.verbose)
        total += test_numeric_key(directory, args.verbose)
        total += test_fallback(directory, args.verbose)
        total += test_image_escape(directory, args.verbose)
        total += test_listing_end_record(directory, args.verbose)
        total += test_exact_names(directory, args.verbose)
        total += test_line_endings(directory, args.verbose)
        total += test_unkept_opens_read_only(directory, args.verbose)

    if FAILURES:
        print("\n%d failure(s):" % len(FAILURES))
        for line in FAILURES:
            print("  - " + line)
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
