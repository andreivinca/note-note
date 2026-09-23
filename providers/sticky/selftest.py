"""Sticky Notes provider checks that need no account: how a Graph message
becomes a note. Run: python3 providers/sticky/selftest.py"""
import json
import os
import sys
import tempfile
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sticky  # noqa: E402


def message(body):
    return {"id": "AAMk", "subject": "first line", "lastModifiedDateTime": "2026-01-01T00:00:00Z",
            "body": {"contentType": "text", "content": body}}


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    return ok


def stored(cache):
    with open(cache) as handle:
        return json.load(handle)


def cached_listing(cache, session):
    """What `list --cached` answers while `session` is the signed-in one."""
    answers = []
    with patch.object(sticky, "CACHE", cache), patch.object(sticky.msgraph, "current_session", return_value=session), \
            patch.object(sticky, "out", answers.append):
        sticky.cmd_list(cached=True)
    return answers[0]["notes"]


def cache_checks():
    """The cache is the sign-in's. The app once showed the previous account's
    notes after a sign-in as another: the file was still there, and the
    cached listing answered from it before the network had."""
    results = []
    with tempfile.TemporaryDirectory(prefix="note-note-sticky-") as directory:
        cache = os.path.join(directory, "note-note-sticky.json")
        with patch.dict(os.environ, {"NOTE_NOTE_MS_CACHE_SESSION": "first"}), \
                patch.object(sticky.msgraph, "current_session", return_value="first"):
            sticky.msgraph.save_for_session(cache, {"notes": [{"id": "a", "body": "the first account's note"}]})
        results.append(check("a cache is stamped with the session it was fetched under",
                             stored(cache)["cacheSession"] == "first"))
        results.append(check("the account that fetched a cache reads it back", cached_listing(cache, "first") == [{"id": "a", "body": "the first account's note"}]))
        results.append(check("another account's cache is never answered from", cached_listing(cache, "second") == []))
        results.append(check("no sign-in reads no cache", cached_listing(cache, "") == []))
        with patch.dict(os.environ, {"NOTE_NOTE_MS_CACHE_SESSION": "first"}), \
                patch.object(sticky.msgraph, "current_session", return_value="second"):
            sticky.msgraph.save_for_session(cache, {"notes": [{"id": "late", "body": "fetched before the sign-in changed"}]})
        results.append(check("a listing that lands after a new sign-in is dropped, not stored as the new account's",
                             cached_listing(cache, "second") == [] and stored(cache)["notes"][0]["id"] == "a"))
    return results


def main():
    results = []
    short = sticky.to_note(message("first line\r\nsecond\r\n"))
    results.append(check("a note keeps its text with Unix line ends and no title",
                         short["body"] == "first line\nsecond" and short["title"] == "" and "truncatedAt" not in short))
    limit = sticky.MAX_NOTE_BODY
    exact = sticky.to_note(message("x" * limit))
    results.append(check("a note exactly at the limit is whole", len(exact["body"]) == limit and "truncatedAt" not in exact))
    cut = sticky.to_note(message("y" * (limit + 1)))
    results.append(check("a longer note is cut at the limit and says where",
                         len(cut["body"]) == limit and cut["truncatedAt"] == limit))
    results.append(check("a note with no body is empty, not an error", sticky.to_note({"id": "x"})["body"] == ""))
    results += cache_checks()
    print("%d/%d sticky checks" % (sum(results), len(results)))
    return int(not all(results))


if __name__ == "__main__":
    sys.exit(main())
