"""Automatic notebook discovery and shared-content routing; no live account."""
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote
import notebook_inventory as inventory

ROOT = "https://graph.microsoft.com/v1.0"
SHARED = ROOT + "/users/other-owner/onenote"


def section(section_id, notebook_id="owned"):
    return {"id": section_id, "displayName": section_id, "lastModifiedDateTime": "stamp",
            "parentNotebook": {"id": notebook_id, "displayName": notebook_id}}


class InventoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        cache = patch.object(onenote, "ONENOTE_CACHE", directory.name + "/listing.json")
        cache.start()
        self.addCleanup(cache.stop)

    def recent_graph(self, responses, known_ids=()):
        replies = iter(responses)

        def graph(method, url, **kwargs):
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": [{"id": key, "sections": [], "sectionGroups": []} for key in known_ids]}
            if url == inventory.RECENT_NOTEBOOKS:
                return 200, {"value": [{"links": {"oneNoteWebUrl": {"href":
                    "https://d.docs.live.net/0123456789ABCDEF/Family"}}}]}
            return next(replies)

        return unittest.mock.Mock(side_effect=graph)

    def test_inventory_keeps_returned_shared_and_empty_notebooks(self):
        shared = dict(section("shared", "family"), pagesUrl=SHARED + "/sections/shared/pages")
        calls = []

        def graph(method, url, **kwargs):
            calls.append(url)
            if url == inventory.RECENT_NOTEBOOKS:
                return 200, {"value": []}
            return 200, {"value": [
                {"id": "owned", "displayName": "Mine", "sections": [section("local")], "sectionGroups": []},
                {"id": "family", "displayName": "Family Room", "userRole": "Reader", "self": SHARED + "/notebooks/family",
                 "sections": [shared], "sectionGroups": []},
                {"id": "empty", "displayName": "Empty", "sections": [], "sectionGroups": []}]}

        books, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["name"] for book in books], ["Mine", "Family Room", "Empty"])
        self.assertEqual([value["id"] for value in sections], ["local", "shared"])
        self.assertEqual(sections[1]["pagesUrl"], SHARED + "/sections/shared/pages")
        self.assertEqual(sections[1]["notebook"], "Family Room")
        self.assertEqual(books[1]["userRole"], "Reader")
        self.assertTrue(calls[0].startswith("/me/onenote/notebooks?$select="))
        self.assertEqual(len(calls), 2)
        self.assertEqual(warnings, [])

    def test_nested_shared_groups_and_expanded_pagination(self):
        page_two = SHARED + "/notebooks/family/sections?$skip=1"
        nested = SHARED + "/sectionGroups/group/sectionGroups"

        def graph(method, url, **kwargs):
            if url == page_two:
                return 200, {"value": [section("second", "family")]}
            if url == nested:
                return 200, {"value": [{"id": "child", "sections": [section("third", "family")], "sectionGroups": []}]}
            return 200, {"value": [{"id": "family", "displayName": "Family Room",
                                    "sections": [section("first", "family")], "sections@odata.nextLink": page_two,
                                    "sectionGroups": [{"id": "group", "sections": [], "sectionGroupsUrl": nested}]}]}

        books, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([value["id"] for value in sections], ["first", "second", "third"])
        self.assertEqual(warnings, [])

    def test_relationship_urls_cannot_send_tokens_off_graph(self):
        for url in ("https://example.com/v1.0/me/onenote/sections/s/pages",
                    ROOT + "/me/drive/items/x", ROOT + "/me/onenote/../drive/items/x",
                    ROOT + "/me/onenote/%2e%2e/drive/items/x",
                    "https://graph.microsoft.com@evil.test/v1.0/me/onenote/pages/p"):
            self.assertEqual(inventory.graph_url(url), "")
        self.assertEqual(inventory.graph_url(SHARED + "/pages/p"), SHARED + "/pages/p")

    def test_recent_personal_share_is_verified_and_deduplicated(self):
        link = "https://d.docs.live.net/0123456789ABCDEF/Family"
        links = {"oneNoteWebUrl": {"href": link}}
        owned_links = {"oneNoteClientUrl": {"href": "onenote:" + link + "Owned"}}
        notebook_id = "0-0123456789ABCDEF!123"
        calls = []

        def graph(method, url, **kwargs):
            calls.append(url)
            self.assertEqual(method, "GET")
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": [{"id": "owned", "links": owned_links, "sections": []}]}
            if url == inventory.RECENT_NOTEBOOKS:
                return 200, {"value": [{"links": owned_links}, {"links": links}, {"links": links}]}
            if url.startswith("/shares/"):
                return 200, {"id": "0123456789ABCDEF!123", "package": {"type": "oneNote"}}
            self.assertTrue(url.startswith("/me/onenote/notebooks/0-0123456789ABCDEF%21123?"))
            return 200, {"id": notebook_id, "displayName": "Family", "userRole": "Reader",
                         "sections": [dict(section("shared"), pagesUrl=SHARED + "/sections/shared/pages")]}

        books, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["owned", notebook_id])
        self.assertEqual(books[1]["userRole"], "Reader")
        self.assertEqual(sections[0]["pagesUrl"], SHARED + "/sections/shared/pages")
        self.assertEqual(len(calls), 4)
        self.assertEqual(warnings, [])

    def test_recent_share_requires_a_verified_notebook(self):
        for item in ({"id": "0123456789ABCDEF!123", "folder": {}},
                     {"id": "../bad", "package": {"type": "oneNote"}}):
            graph = self.recent_graph([(200, item)])
            books, _, warnings = inventory.discover(graph, 500, 100000)
            self.assertEqual(books, [])
            self.assertTrue(warnings)
            self.assertEqual(graph.call_count, 3)
        graph = self.recent_graph([
            (200, {"id": "0123456789ABCDEF!123", "package": {"type": "oneNote"}}),
            (200, {"id": "some-other-notebook"}),
        ])
        books, _, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual(books, [])
        self.assertIn("different notebook", warnings[0])
        self.assertEqual(graph.call_count, 4)

    def test_recent_owned_alias_with_short_cid_skips_notebook_fetch(self):
        graph = self.recent_graph([(200, {
            "id": "123456789ABCDEF!123", "package": {"type": "oneNote"},
        })], known_ids=["0-123456789abcdef!123"])
        books, _, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["0-123456789abcdef!123"])
        self.assertEqual(warnings, [])
        self.assertEqual(graph.call_count, 3)

    def test_recent_lookup_failure_preserves_the_primary_inventory(self):
        def graph(method, url, **kwargs):
            if url == inventory.RECENT_NOTEBOOKS:
                return 403, {}
            return 200, {"value": [{"id": "owned", "sections": [section("s")]}]}

        books, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["owned"])
        self.assertEqual([entry["id"] for entry in sections], ["s"])
        self.assertIn("HTTP 403", warnings[0])

    def test_shared_section_self_supplies_the_page_route(self):
        value = inventory.section_record(dict(section("s", "family"), self=SHARED + "/sections/s"))
        self.assertEqual(value["pagesUrl"], SHARED + "/sections/s/pages")
        self.assertEqual(onenote.page_record({"id": "p"}, value)["self"], SHARED + "/pages/p")

    def test_shared_images_use_only_graph_resource_endpoints(self):
        for root in (SHARED, ROOT + "/me/onenote", ROOT + "/users('owner')/onenote",
                     ROOT + "/groups/group/onenote", ROOT + "/sites/site/onenote"):
            self.assertTrue(onenote.image_allowed(root + "/resources/image-id/$value"))
        for url in (SHARED + "/resources/image-id/$value?redirect=1",
                    SHARED + "/resources/image-id/$value#fragment", SHARED + "/pages/p/content",
                    "https://example.com/v1.0/me/onenote/resources/image-id/$value"):
            self.assertFalse(onenote.image_allowed(url))

    def test_pagination_cycles_stop_with_a_warning(self):
        next_page = ROOT + "/me/onenote/notebooks?$skip=100"

        def graph(method, url, **kwargs):
            if url == inventory.RECENT_NOTEBOOKS:
                return 200, {"value": []}
            return 200, {"value": [], "@odata.nextLink": next_page}

        books, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual(books, [])
        self.assertEqual(len(warnings), 1)

    def test_failed_notebook_listing_preserves_the_previous_cache(self):
        cache = {"notebooks": [{"id": "book", "name": "Mine"}], "sections": [], "pages": []}
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "load_order", return_value={}), \
                patch.object(onenote, "graph", return_value=(500, {"error": {"message": "Unavailable"}})), \
                patch.object(onenote, "save_listing") as save, patch.object(onenote.provider_io, "out") as output:
            with self.assertRaises(SystemExit):
                onenote.cmd_onenote_list(False)
        save.assert_not_called()
        self.assertEqual(output.call_args.args[0], {"error": "Unavailable", "kind": "transient"})

    def test_page_routes_retain_the_shared_owner_after_a_poll(self):
        shared_section = inventory.section_record(dict(section("s", "family"), pagesUrl=SHARED + "/sections/s/pages"))
        cache = {"sections": [shared_section], "pages": []}
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "graph", return_value=(200, {"value": [{"id": "p", "title": "Shared page"}]})) as graph, \
                patch.object(onenote, "save_listing"), patch.object(onenote, "out"):
            onenote.cmd_onenote_pages(["s"])
            self.assertTrue(graph.call_args.args[1].startswith(SHARED + "/sections/s/pages?"))
            self.assertEqual(onenote.page_content_url("p"), SHARED + "/pages/p/content")
            self.assertEqual(onenote.resource_url("pages", "p"), SHARED + "/pages/p")

    def test_one_forbidden_section_does_not_hide_other_notebooks(self):
        source = [section("working"), section("forbidden", "shared-book")]
        cache = {}

        def graph(method, url, **kwargs):
            return 200, {"value": [{"id": "owned", "displayName": "Mine", "sections": source[:1], "sectionGroups": []},
                                    {"id": "shared-book", "displayName": "Shared", "sections": source[1:], "sectionGroups": []}]}

        def pages(method, url, **kwargs):
            if "/forbidden/" in url:
                return 403, {"error": {"message": "Access denied"}}
            return 200, {"value": [{"id": "p", "title": "Visible"}]}

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
            stack.enter_context(patch.object(onenote, "load_order", return_value={}))
            stack.enter_context(patch.object(onenote, "has_section_order_scope", return_value=False))
            stack.enter_context(patch.object(onenote, "access_token", return_value="test-token"))
            stack.enter_context(patch.object(onenote, "graph", side_effect=graph))
            stack.enter_context(patch.object(onenote, "http", side_effect=pages))
            saved = stack.enter_context(patch.object(onenote, "save_listing", side_effect=cache.update))
            output = stack.enter_context(patch.object(onenote, "out"))
            onenote.cmd_onenote_list(False)
        answer = output.call_args.args[0]
        self.assertEqual([page["id"] for page in answer["pages"]], ["p"])
        self.assertEqual(len(answer["sections"]), 2)
        self.assertEqual(len(answer["notebooks"]), 2)
        self.assertFalse(answer["inventoryComplete"])
        self.assertIn("Access denied", answer["listingWarnings"][0])
        self.assertNotIn("forbidden", saved.call_args.args[0]["sectionPages"])

    def test_unreadable_relationship_keeps_cached_shared_pages(self):
        shared_section = inventory.section_record(section("s", "family"))
        cache = {"notebooks": [{"id": "family", "name": "Family Room"}], "sections": [shared_section],
                 "pages": [{"id": "p", "title": "Cached shared page", "sectionId": "s"}],
                 "sectionPages": {"s": {"modified": "stamp"}}}

        def graph(method, url, **kwargs):
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": [{"id": "family", "displayName": "Family Room",
                                        "sectionsUrl": SHARED + "/notebooks/family/sections", "sectionGroups": []}]}
            return 403, {"error": {"message": "Access denied"}}

        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "load_order", return_value={}), \
                patch.object(onenote, "access_token", return_value="test-token"), \
                patch.object(onenote, "graph", side_effect=graph), \
                patch.object(onenote, "save_listing"), patch.object(onenote, "out") as output:
            onenote.cmd_onenote_list(False)
        answer = output.call_args.args[0]
        self.assertEqual(answer["pages"], cache["pages"])
        self.assertEqual(answer["sections"], cache["sections"])
        self.assertFalse(answer["inventoryComplete"])
        self.assertIn("HTTP 403", answer["listingWarnings"][0])

    def test_read_only_incoming_page_opens_with_its_permission(self):
        cache = {"notebooks": [{"id": "family", "userRole": "Reader"}],
                 "sections": [{"id": "s", "notebookId": "family"}],
                 "pages": [{"id": "p", "sectionId": "s"}]}
        html = "<html><head><title>Shared</title></head><body><p>Read me</p></body></html>"
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
            stack.enter_context(patch.object(onenote, "graph_raw", return_value=(200, html)))
            stack.enter_context(patch.object(onenote, "search_ticket", return_value=None))
            stack.enter_context(patch.object(onenote, "remember_images"))
            stack.enter_context(patch.object(onenote, "remember_search"))
            journal = stack.enter_context(patch.object(onenote, "merge_store"))
            journal.return_value.__enter__.return_value.recover.return_value = None
            journal.return_value.__enter__.return_value.open.side_effect = lambda note: note
            output = stack.enter_context(patch.object(onenote, "out"))
            onenote.cmd_onenote_page("p")
        result = output.call_args.args[0]
        self.assertIn("Read me", result["body"])
        self.assertFalse(result["editable"])
        self.assertIn("read-only", result["reason"])

    def test_read_only_incoming_notebook_rejects_mutations_before_requests(self):
        cache = {"notebooks": [{"id": "family", "userRole": "Reader"}],
                 "sections": [{"id": "s", "notebookId": "family"}],
                 "pages": [{"id": "p", "sectionId": "s"}]}
        commands = ((onenote.cmd_onenote_update, ("p", "-")),
                    (onenote.cmd_onenote_delete, ("p",)),
                    (onenote.cmd_onenote_create, ("s", "-")),
                    (onenote.cmd_onenote_create_section, ("family", "-")))
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "graph") as graph, \
                patch.object(onenote, "graph_raw") as raw, \
                patch.object(onenote, "read_payload") as payload, \
                patch.object(onenote.provider_io, "out") as output:
            for command, args in commands:
                with self.subTest(command=command.__name__):
                    with self.assertRaises(SystemExit):
                        command(*args)
                    self.assertIn("read-only", output.call_args.args[0]["error"])
        graph.assert_not_called()
        raw.assert_not_called()
        payload.assert_not_called()


def run():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InventoryTests)
    return unittest.TextTestRunner().run(suite).wasSuccessful()


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
