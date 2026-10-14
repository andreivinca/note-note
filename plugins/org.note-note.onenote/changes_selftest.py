"""Synthetic tests for the changed sections OneDrive reports: no account or network."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import onenote
import ratelimit
import section_changes as changes

DELTA = onenote.GRAPH + "/me/drive/root/delta"
OWNED = {"id": "0-ABCDEF0123456789!100", "userRole": "Owner"}
SHARED = {"id": "0-1111111111111111!7", "userRole": "Contributor"}
SECTIONS = [{"id": "0-ABCDEF0123456789!101", "notebookId": OWNED["id"]},
            {"id": "0-ABCDEF0123456789!102", "notebookId": OWNED["id"]},
            {"id": "0-1111111111111111!8", "notebookId": SHARED["id"]}]
TRACKED = ["0-ABCDEF0123456789!101", "0-ABCDEF0123456789!102"]


class Graph:
    """Answers each request with the next response, and keeps the URLs asked for."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []

    def __call__(self, method, url, max_bytes=None):
        self.urls.append(url)
        return self.responses.pop(0)


def page(items, next_link=None, delta_link=None):
    body = {"value": [{"id": item} for item in items]}
    if next_link:
        body["@odata.nextLink"] = next_link
    if delta_link:
        body["@odata.deltaLink"] = delta_link
    return 200, body


class ReadTests(unittest.TestCase):
    def test_only_sections_of_owned_personal_notebooks_are_tracked(self):
        sections = SECTIONS + [{"id": "1-not-personal", "notebookId": OWNED["id"]}]
        self.assertEqual(changes.tracked([OWNED, SHARED], sections), TRACKED)

    def test_a_first_round_starts_at_now_and_counts_every_section_as_changed(self):
        graph = Graph(page([], delta_link=DELTA + "?token=now"))
        self.assertEqual(changes.read(graph, None, TRACKED), (TRACKED, DELTA + "?token=now"))
        self.assertEqual(graph.urls, [changes.START])

    def test_a_round_names_the_tracked_sections_whose_files_changed(self):
        graph = Graph(page(["abcdef0123456789!102", "ABCDEF0123456789!999"], next_link=DELTA + "?token=b"),
                      page(["1111111111111111!8", "ABCDEF0123456789!100"], delta_link=DELTA + "?token=c"))
        self.assertEqual(changes.read(graph, DELTA + "?token=a", TRACKED),
                         (["0-ABCDEF0123456789!102"], DELTA + "?token=c"))
        self.assertEqual(graph.urls, [DELTA + "?token=a", DELTA + "?token=b"])

    def test_an_expired_cursor_starts_again_and_counts_every_section_as_changed(self):
        graph = Graph((410, {"error": {"code": "resyncRequired"}}), page([], delta_link=DELTA + "?token=new"))
        self.assertEqual(changes.read(graph, DELTA + "?token=old", TRACKED), (TRACKED, DELTA + "?token=new"))

    def test_a_long_round_keeps_its_place_for_the_next(self):
        responses = [page(["ABCDEF0123456789!101"], next_link=DELTA + "?token=%d" % index)
                     for index in range(changes.MAX_PAGES)]
        graph = Graph(*responses)
        self.assertEqual(changes.read(graph, DELTA + "?token=start", TRACKED),
                         (["0-ABCDEF0123456789!101"], DELTA + "?token=%d" % (changes.MAX_PAGES - 1)))
        self.assertEqual(len(graph.urls), changes.MAX_PAGES)

    def test_a_cursor_must_continue_a_graph_drive_delta(self):
        for url in ("https://graph.microsoft.com.evil.example/v1.0/drives/a/root/delta",
                    onenote.GRAPH + "/me/onenote/pages", "http://graph.microsoft.com/v1.0/drives/a/root/delta",
                    None, 7):
            with self.subTest(url=url):
                self.assertEqual(changes.cursor_url(url), "")
        graph = Graph(page([], delta_link=DELTA + "?token=now"))
        self.assertEqual(changes.read(graph, onenote.GRAPH + "/me/onenote/pages", TRACKED)[0], TRACKED)
        self.assertEqual(graph.urls, [changes.START])

    def test_a_failed_round_or_a_round_without_a_cursor_is_an_error(self):
        for response in ((503, {}), (200, {"value": "not a list"}), page(["ABCDEF0123456789!101"])):
            with self.subTest(response=response), self.assertRaises(onenote.msgraph.GraphError):
                changes.read(Graph(response), DELTA + "?token=a", TRACKED)


class CommandTests(unittest.TestCase):
    def run_command(self, graph, granted=True, saved=None):
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "load_listing",
                                             return_value={"notebooks": [OWNED, SHARED], "sections": SECTIONS}))
            stack.enter_context(patch.object(onenote, "files_read_granted", return_value=granted))
            stack.enter_context(patch.object(onenote, "graph", graph))
            stack.enter_context(patch.object(onenote.msgraph, "load_for_session", return_value=saved or {}))
            save = stack.enter_context(patch.object(onenote.msgraph, "save_for_session"))
            stack.enter_context(contextlib.redirect_stdout(output))
            try:
                onenote.cmd_changes()
            except SystemExit:
                pass
        return json.loads(output.getvalue()), save

    def test_without_onedrive_consent_nothing_is_tracked_or_asked(self):
        graph = Graph()
        result, save = self.run_command(graph, granted=False)
        self.assertEqual(result, {"tracked": [], "changed": []})
        self.assertEqual(graph.urls, [])
        save.assert_not_called()

    def test_a_round_keeps_its_cursor_and_answers_the_changed_sections(self):
        graph = Graph(page(["ABCDEF0123456789!101"], delta_link=DELTA + "?token=b"))
        result, save = self.run_command(graph, saved={"cursor": DELTA + "?token=a"})
        self.assertEqual(result, {"tracked": TRACKED, "changed": ["0-ABCDEF0123456789!101"]})
        save.assert_called_once_with(onenote.ONENOTE_CHANGES, {"cursor": DELTA + "?token=b"})

    def test_a_paused_round_is_deferred_and_keeps_the_old_cursor(self):
        for pause in (ratelimit.Deferred(12), ratelimit.Throttled(300)):
            def graph(method, url, max_bytes=None):
                raise pause
            with self.subTest(pause=type(pause).__name__):
                result, save = self.run_command(graph, saved={"cursor": DELTA + "?token=a"})
                self.assertEqual(result, {"deferred": True, "retryAfter": pause.retry_after})
                save.assert_not_called()

    def test_a_failed_round_is_not_run_again_and_keeps_the_old_cursor(self):
        result, save = self.run_command(Graph((503, {})), saved={"cursor": DELTA + "?token=a"})
        self.assertIn("error", result)
        self.assertNotIn("kind", result)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
