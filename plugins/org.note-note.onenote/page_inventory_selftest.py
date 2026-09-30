"""Large-account startup, resumable page discovery and foreground priority."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import onenote  # noqa: E402

ROOT = "https://graph.microsoft.com/v1.0/me/onenote"


def section(sid):
    return {"id": sid, "name": sid, "modified": "1", "notebook": "Book", "notebookId": "book"}


def page(pid, sid="s"):
    return {"id": pid, "title": pid, "sectionId": sid, "modified": "1"}


class ListingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(onenote, "ONENOTE_CACHE", directory.name + "/listing.json"))
        stack.enter_context(patch.object(onenote, "load_order", return_value={}))
        stack.enter_context(patch.object(onenote.msgraph, "current_session", return_value="test"))
        stack.enter_context(patch.dict(os.environ, {"NOTE_NOTE_MS_CACHE_SESSION": "test",
                                                  "NOTE_NOTE_RATE_DIR": directory.name + "/rate"}))
        self.payload = stack.enter_context(patch.object(onenote, "read_payload", return_value={"sectionId": "s"}))
        self.output = stack.enter_context(patch.object(onenote, "out"))

    def save(self, sections=None, pages=None, **kwargs):
        onenote.save_listing(dict({"sections": sections or [section("s")], "pages": pages or [],
                                   "pageRevision": "initial"}, **kwargs))

    def step(self, response, interactive=False, sid="s"):
        self.payload.return_value = {"sectionId": sid, "interactive": interactive}
        with patch.object(onenote, "graph", return_value=response) as graph:
            onenote.cmd_list_step("-")
        self.assertLessEqual(graph.call_count, 1)
        return self.output.call_args.args[0], graph

    def test_hundreds_of_sections_publish_before_any_page_requests(self):
        sections = [section("s%d" % i) for i in range(400)]
        with patch.object(onenote.notebook_inventory, "discover", return_value=([], sections, [])), \
                patch.object(onenote, "graph", side_effect=AssertionError("page request at startup")), \
                patch.object(onenote, "http", side_effect=AssertionError("listing pool at startup")):
            onenote.cmd_onenote_list(False, incremental=True)
        answer = self.output.call_args.args[0]
        self.assertEqual(len(answer["sections"]), 400)
        self.assertEqual(len(answer["pendingSections"]), 400)
        self.assertEqual(answer["pages"], [])
        self.assertFalse(answer["inventoryComplete"])
        answer, graph = self.step((200, {"value": [{"id": "selected"}]}), True, "s399")
        self.assertIn("/sections/s399/pages?", graph.call_args.args[1])
        self.assertEqual(answer["pages"][0]["id"], "selected")
        self.assertEqual(len(answer["pendingSections"]), 399)

    def test_pagination_resumes_after_restart_and_retains_tab_order(self):
        self.save()
        continuation = ROOT + "/sections/s/pages?$skip=100"
        first, graph = self.step((200, {"value": [{"id": "p%d" % i} for i in range(100)],
                                       "@odata.nextLink": continuation}))
        self.assertIn("$top=100", graph.call_args.args[1])
        self.assertEqual(len(first["pages"]), 100)
        self.assertFalse(first["inventoryComplete"])
        self.assertEqual(first["pendingSections"], ["s"])
        onenote.cmd_onenote_list(True)
        self.assertEqual(self.output.call_args.args[0]["pendingSections"], ["s"])
        second, graph = self.step((200, {"value": [{"id": "last"}]}))
        self.assertEqual(graph.call_args.args[1], continuation)
        self.assertEqual([item["id"] for item in second["pages"]], ["p%d" % i for i in range(100)] + ["last"])
        self.assertTrue(second["inventoryComplete"])
        self.assertGreater(second["pageListSerial"], first["pageListSerial"])

    def test_partial_refresh_retains_cached_pages_until_deletions_are_known(self):
        self.save(pages=[page("old"), page("kept")])
        first, _ = self.step((200, {"value": [{"id": "kept"}], "@odata.nextLink": ROOT + "/sections/s/pages?$skip=100"}))
        self.assertEqual({item["id"] for item in first["pages"]}, {"old", "kept"})
        second, _ = self.step((200, {"value": [{"id": "new"}]}))
        self.assertEqual([item["id"] for item in second["pages"]], ["kept", "new"])

    def test_budget_deferral_leaves_foreground_requests_available(self):
        self.save()
        key = onenote.msgraph.settings.rate_key
        now = time.time()
        onenote.ratelimit._save(key, {"stamps": [now - 120] * 330, "holders": [], "cooldownUntil": 0})

        def graph(method, url, **kwargs):
            with onenote.ratelimit.slot(key, onenote.msgraph.settings.rate_windows,
                                       reserve=onenote.msgraph.settings.background_reserve):
                return 200, {"value": [{"id": "opened"}]}

        with patch.object(onenote, "graph", side_effect=graph):
            onenote.cmd_list_step("-")
            self.assertTrue(self.output.call_args.args[0]["deferred"])
            self.assertNotIn("kind", self.output.call_args.args[0])
            self.payload.return_value["interactive"] = True
            onenote.cmd_list_step("-")
        self.assertTrue(self.output.call_args.args[0]["inventoryComplete"])
        self.assertEqual(onenote.ratelimit.cooldown_remaining(key), 0)

    def test_forbidden_section_does_not_block_other_sections_or_remove_cache(self):
        self.save(sections=[section("s"), section("other")], pages=[page("old")])
        failed, _ = self.step((403, {"error": {"message": "Access denied"}}))
        self.assertEqual(failed["pages"], [page("old")])
        self.assertGreater(failed["sectionRetryAt"]["s"], time.time())
        other, _ = self.step((200, {"value": [{"id": "visible"}]}), sid="other")
        self.assertEqual(other["pendingSections"], ["s"])
        self.assertEqual({item["id"] for item in other["pages"]}, {"old", "visible"})

    def test_unchanged_sections_do_not_cost_another_request(self):
        self.save(sectionPages={"s": {"modified": "1"}})
        _, graph = self.step((200, {"value": []}))
        graph.assert_not_called()

    def test_force_refresh_starts_over_and_normal_discovery_keeps_the_cursor(self):
        self.save()
        continuation = ROOT + "/sections/s/pages?$skip=100"
        self.step((200, {"value": [{"id": "first"}], "@odata.nextLink": continuation}))
        with patch.object(onenote.notebook_inventory, "discover", return_value=([], [section("s")], [])):
            onenote.cmd_onenote_list(False, incremental=True)
            self.assertEqual(onenote.load_listing()["sectionProgress"]["s"]["url"], continuation)
            onenote.cmd_onenote_list(False, force=True, incremental=True)
            self.assertEqual(onenote.load_listing()["sectionProgress"], {})

    def test_invalid_pagination_never_reaches_the_network(self):
        self.save(pages=[page("old")])
        result, graph = self.step((200, {"value": [], "@odata.nextLink": "https://evil.test/pages"}))
        self.assertIn("invalid", result["listingError"])
        self.assertEqual(result["pages"], [page("old")])
        self.assertEqual(graph.call_count, 1)

    def test_a_late_response_cannot_undo_a_page_creation(self):
        self.save()

        def graph(method, url, **kwargs):
            cache = onenote.load_listing()
            cache.update(pages=[page("created")], pageRevision="mutation")
            onenote.save_listing(cache)
            return 200, {"value": []}

        with patch.object(onenote, "graph", side_effect=graph):
            onenote.cmd_list_step("-")
        self.assertEqual(self.output.call_args.args[0]["pages"], [page("created")])
        self.assertEqual(onenote.load_listing()["pages"], [page("created")])

    def test_a_full_cache_can_refresh_existing_sections(self):
        self.save(pages=[page("old"), page("kept")])
        with patch.object(onenote, "MAX_PAGES", 2):
            result, graph = self.step((200, {"value": [{"id": "kept"}, {"id": "new"}]}), True)
        self.assertEqual(graph.call_count, 1)
        self.assertEqual([item["id"] for item in result["pages"]], ["kept", "new"])
        self.assertTrue(result["sectionComplete"])

    def test_a_capped_continuation_retains_cached_pages_and_stops(self):
        self.save(pages=[page("old"), page("kept")])
        with patch.object(onenote, "MAX_PAGES", 2):
            result, _ = self.step((200, {"value": [{"id": "kept"}, {"id": "new"}],
                                         "@odata.nextLink": ROOT + "/sections/s/pages?$skip=100"}))
            self.assertEqual([item["id"] for item in result["pages"]], ["old", "kept"])
            self.assertFalse(result["sectionComplete"])
            self.assertFalse(result["inventoryComplete"])
            self.assertEqual(result["pendingSections"], [])
            _, graph = self.step((200, {"value": []}))
            graph.assert_not_called()

    def test_discovery_cannot_remove_a_concurrently_created_section(self):
        self.save()

        def discover(*args, **kwargs):
            cache = onenote.load_listing()
            cache.update(sections=[section("s"), section("created")],
                         pageRevision="mutation", pageListSerial=1)
            onenote.save_listing(cache)
            return [], [section("s")], []

        with patch.object(onenote.notebook_inventory, "discover", side_effect=discover):
            onenote.cmd_onenote_list(False, incremental=True)
        result = self.output.call_args.args[0]
        self.assertTrue(result["deferred"])
        self.assertEqual([item["id"] for item in result["sections"]], ["created", "s"])
        self.assertEqual(len(onenote.load_listing()["sections"]), 2)

    def test_tree_discovery_resumes_without_spending_the_same_requests(self):
        self.save(pages=[page("old")], sectionPages={"s": {"modified": "1"}})
        calls = []
        endpoint = ROOT + "/notebooks/book/sections"
        paused = False

        def graph(method, url, **kwargs):
            nonlocal paused
            calls.append(url)
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": [{"id": "book", "displayName": "Book",
                                        "sectionsUrl": endpoint, "sectionGroups": []}]}
            if url == endpoint:
                if not paused:
                    paused = True
                    raise onenote.ratelimit.Deferred(60)
                return 200, {"value": [{"id": "s", "displayName": "Section", "lastModifiedDateTime": "1"}]}
            self.assertEqual(url, onenote.notebook_inventory.RECENT_NOTEBOOKS)
            return 200, {"value": []}

        with patch.object(onenote, "graph", side_effect=graph):
            onenote.cmd_onenote_list(False, force=True, incremental=True)
            first = self.output.call_args.args[0]
            self.assertTrue(first["deferred"])
            self.assertEqual(first["notebooks"][0]["id"], "book")
            self.assertFalse(first["inventoryComplete"])
            onenote.cmd_onenote_list(False, incremental=True)
        second = self.output.call_args.args[0]
        self.assertEqual(second["sections"][0]["id"], "s")
        self.assertEqual(second["pendingSections"], ["s"])
        self.assertEqual(sum(url.startswith("/me/onenote/notebooks?") for url in calls), 1)
        self.assertIsNone(onenote.load_listing()["notebookProgress"])

    def test_shared_notebook_verification_resumes_after_drive_resolution(self):
        calls = []
        paused = False
        notebook_id = "0-0123456789ABCDEF!123"

        def graph(method, url, **kwargs):
            nonlocal paused
            calls.append(url)
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": []}
            if url == onenote.notebook_inventory.RECENT_NOTEBOOKS:
                return 200, {"value": [{"links": {"oneNoteWebUrl": {"href":
                    "https://d.docs.live.net/0123456789ABCDEF/Family"}}}]}
            if url.startswith("/shares/"):
                return 200, {"id": "0123456789ABCDEF!123", "package": {"type": "oneNote"}}
            if not paused:
                paused = True
                raise onenote.ratelimit.Deferred(60)
            return 200, {"id": notebook_id, "displayName": "Family", "userRole": "Reader",
                         "sections": [], "sectionGroups": []}

        with patch.object(onenote, "graph", side_effect=graph):
            onenote.cmd_onenote_list(False, incremental=True)
            self.assertTrue(self.output.call_args.args[0]["deferred"])
            onenote.cmd_onenote_list(False, incremental=True)
        result = self.output.call_args.args[0]
        self.assertEqual(result["notebooks"][0]["id"], notebook_id)
        self.assertEqual(result["notebooks"][0]["userRole"], "Reader")
        self.assertTrue(result["inventoryComplete"])
        self.assertEqual(sum(url.startswith("/shares/") for url in calls), 1)
        self.assertEqual(calls.count(onenote.notebook_inventory.RECENT_NOTEBOOKS), 1)

    def test_full_listing_cannot_overwrite_a_concurrent_mutation(self):
        self.save()

        def http(*args, **kwargs):
            with onenote.listing_lock():
                cache = onenote.load_listing()
                cache.update(pages=[page("created")], pageRevision="mutation", pageListSerial=1)
                onenote.save_listing(cache)
            return 200, {"value": []}

        with patch.object(onenote.notebook_inventory, "discover", return_value=([], [section("s")], [])), \
                patch.object(onenote, "access_token", return_value="test-token"), \
                patch.object(onenote, "http", side_effect=http):
            with self.assertRaises(onenote.msgraph.GraphError) as error:
                onenote.cmd_onenote_list(False)
        self.assertEqual(error.exception.kind, "transient")
        self.assertEqual(onenote.load_listing()["pages"], [page("created")])

    def test_full_listing_fetches_four_sections_at_once(self):
        sections = [section("s%d" % i) for i in range(4)]
        self.save(sections=sections)
        simultaneous = threading.Barrier(4, timeout=5)

        def http(method, url, **kwargs):
            sid = next(value["id"] for value in sections if "/sections/" + value["id"] + "/" in url)
            simultaneous.wait()
            return 200, {"value": [{"id": sid + "-page"}]}

        with patch.object(onenote.notebook_inventory, "discover", return_value=([], sections, [])), \
                patch.object(onenote, "access_token", return_value="test-token"), \
                patch.object(onenote, "http", side_effect=http) as requests:
            onenote.cmd_onenote_list(False)
        self.assertEqual(requests.call_count, 4)
        self.assertEqual([item["id"] for item in onenote.load_listing()["pages"]],
                         [value["id"] + "-page" for value in sections])

    def test_page_steps_overlap_network_reads_and_merge_their_results(self):
        sections = [section("s0"), section("s1")]
        self.save(sections=sections)
        simultaneous = threading.Barrier(2, timeout=5)
        self.payload.side_effect = json.loads

        def graph(method, url, **kwargs):
            sid = next(value["id"] for value in sections if "/sections/" + value["id"] + "/" in url)
            simultaneous.wait()
            return 200, {"value": [{"id": sid + "-page"}]}

        with patch.object(onenote, "graph", side_effect=graph) as requests:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(onenote.cmd_list_step, json.dumps({"sectionId": value["id"], "interactive": True}))
                           for value in sections]
                for future in futures:
                    future.result(timeout=10)
        self.assertEqual(requests.call_count, 2)
        self.assertEqual([item["id"] for item in onenote.load_listing()["pages"]], ["s0-page", "s1-page"])
        self.assertEqual(onenote.load_listing()["pageListSerial"], 2)

    def test_full_listing_rejects_pagination_cycles_and_foreign_urls(self):
        for continuation in ("https://evil.test/pages", onenote.section_pages_url("s")):
            with self.subTest(continuation=continuation):
                self.save(pages=[page("old")])
                response = {"value": [{"id": "new"}], "@odata.nextLink": continuation}
                with patch.object(onenote.notebook_inventory, "discover", return_value=([], [section("s")], [])), \
                        patch.object(onenote, "access_token", return_value="test-token"), \
                        patch.object(onenote, "http", return_value=(200, response)) as http:
                    onenote.cmd_onenote_list(False)
                result = self.output.call_args.args[0]
                self.assertEqual(http.call_count, 1)
                self.assertEqual({item["id"] for item in result["pages"]}, {"old", "new"})
                self.assertTrue(result["listingWarnings"])
                self.assertFalse(result["inventoryComplete"])

    def test_a_repeated_tree_deferral_does_not_invalidate_page_requests(self):
        endpoint = ROOT + "/notebooks/book/sections"

        def graph(method, url, **kwargs):
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": [{"id": "book", "displayName": "Book",
                                        "sectionsUrl": endpoint, "sectionGroups": []}]}
            raise onenote.ratelimit.Deferred(60)

        with patch.object(onenote, "graph", side_effect=graph):
            onenote.cmd_onenote_list(False, incremental=True)
            revision = onenote.load_listing()["pageRevision"]
            serial = onenote.load_listing()["pageListSerial"]
            onenote.cmd_onenote_list(False, incremental=True)
        self.assertEqual(onenote.load_listing()["pageRevision"], revision)
        self.assertEqual(onenote.load_listing()["pageListSerial"], serial)

    def test_targeted_refresh_keeps_sections_outside_its_request_limit(self):
        sections = [section("s%d" % i) for i in range(11)]
        self.save(sections=sections, pages=[page("retained", "s10")])
        with patch.object(onenote, "graph", return_value=(200, {"value": []})) as graph:
            onenote.cmd_onenote_pages([value["id"] for value in sections])
        self.assertEqual(graph.call_count, 10)
        self.assertEqual(onenote.load_listing()["pages"], [page("retained", "s10")])
        self.assertEqual(len(self.output.call_args.args[0]["sections"]), 10)

    def test_targeted_refresh_cannot_overwrite_a_concurrent_mutation(self):
        self.save()

        def graph(*args, **kwargs):
            cache = onenote.load_listing()
            cache.update(pages=[page("created")], pageRevision="mutation", pageListSerial=1)
            onenote.save_listing(cache)
            return 200, {"value": []}

        with patch.object(onenote, "graph", side_effect=graph):
            with self.assertRaises(onenote.msgraph.GraphError):
                onenote.cmd_onenote_pages(["s"])
        self.assertEqual(onenote.load_listing()["pages"], [page("created")])

    def test_new_section_in_an_empty_notebook_retains_its_name(self):
        onenote.save_listing({"notebooks": [{"id": "book", "name": "Empty notebook"}],
                              "sections": [], "pages": []})
        self.payload.return_value = {"name": "Created"}
        with patch.object(onenote, "graph", return_value=(201, {"id": "s", "displayName": "Created"})):
            onenote.cmd_onenote_create_section("book", "-")
        self.assertEqual(onenote.load_listing()["sections"][0]["notebook"], "Empty notebook")


class QmlTests(unittest.TestCase):
    def test_discovery_priority_and_lifecycle(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic",
                   QT_FORCE_STDERR_LOGGING="1")
        result = subprocess.run(["qml6", str(HERE / "page_inventory_selftest.qml")],
                                capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<<<RESULT>>>", result.stderr, result.stderr)
        checks = json.loads(result.stderr.split("<<<RESULT>>>")[1].split("<<<END>>>")[0])
        self.assertTrue(checks)
        self.assertEqual([check for check in checks if not check["ok"]], [], result.stderr)
        self.assertFalse(any(".qml:" in line or "qrc:" in line for line in result.stderr.splitlines()), result.stderr)


if __name__ == "__main__":
    unittest.main()
