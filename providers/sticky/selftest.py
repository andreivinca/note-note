"""Sticky Notes provider checks that need no account: how a Graph message
becomes a note. Run: python3 providers/sticky/selftest.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sticky  # noqa: E402


def message(body):
    return {"id": "AAMk", "subject": "first line", "lastModifiedDateTime": "2026-01-01T00:00:00Z",
            "body": {"contentType": "text", "content": body}}


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    return ok


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
    print("%d/%d sticky checks" % (sum(results), len(results)))
    return int(not all(results))


if __name__ == "__main__":
    sys.exit(main())
