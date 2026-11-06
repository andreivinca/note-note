"""Automatic notebook discovery and shared-content routing; no live account."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote
import notebook_inventory as inventory
import provider_io  # on the path onenote set up

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
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return reply

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

        books, groups, sections, warnings = inventory.discover(graph, 500, 100000)
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

        books, groups, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([value["id"] for value in sections], ["first", "second", "third"])
        self.assertEqual([(group["id"], group.get("parentGroupId")) for group in groups],
                         [("group", None), ("child", "group")])
        self.assertEqual(sections[2]["parentGroupId"], "child")
        self.assertNotIn("parentGroupId", sections[1])
        self.assertEqual(warnings, [])

    def test_groups_are_listed_with_what_they_hold(self):
        """A notebook's groups are records of their own, each saying which
        group it sits in, as each section does: the one it was listed under,
        which an expanded child listed with $select does not say itself. An
        empty group is listed too, and a name may repeat under another
        parent."""
        archive = SHARED + "/sectionGroups/work/sectionGroups"
        calls = []

        def graph(method, url, **kwargs):
            calls.append(url)
            if url == inventory.RECENT_NOTEBOOKS:
                return 200, {"value": []}
            if url == archive:
                return 200, {"value": [
                    {"id": "archive", "displayName": "Archive", "sections": [section("old", "family")],
                     "sectionGroups": []},
                    {"id": "notes-in-work", "displayName": "Notes", "sections": [], "sectionGroups": []}]}
            work = {"id": "work", "displayName": "Work", "self": SHARED + "/sectionGroups/work",
                    "sections": [{"id": "tasks", "displayName": "Tasks"}], "sectionGroupsUrl": archive}
            notes = {"id": "notes", "displayName": "Notes", "sections": [], "sectionGroups": []}
            return 200, {"value": [{"id": "family", "displayName": "Family Room",
                                    "sections": [section("loose", "family")], "sectionGroups": [work, notes]}]}

        books, groups, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual(warnings, [])
        self.assertEqual(len(calls), 3)
        self.assertEqual([(group["id"], group["name"], group.get("parentGroupId")) for group in groups],
                         [("work", "Work", None), ("notes", "Notes", None),
                          ("archive", "Archive", "work"), ("notes-in-work", "Notes", "work")])
        self.assertEqual([(value["id"], value.get("parentGroupId")) for value in sections],
                         [("loose", None), ("tasks", "work"), ("old", "archive")])
        self.assertTrue(all(group["notebookId"] == "family" and group["notebook"] == "Family Room" for group in groups))
        self.assertEqual(groups[0]["self"], SHARED + "/sectionGroups/work")
        self.assertEqual(sections[1]["notebookId"], "family")

    def test_resumed_discovery_keeps_the_groups_it_found(self):
        nested = SHARED + "/sectionGroups/work/sectionGroups"
        progress = {}
        paused = False

        def checkpoint(state):
            progress.clear()
            progress.update(copy.deepcopy(state))

        def graph(method, url, **kwargs):
            nonlocal paused
            if url == inventory.RECENT_NOTEBOOKS:
                return 200, {"value": []}
            if url == nested:
                if not paused:
                    paused = True
                    raise onenote.ratelimit.Deferred(60)
                return 200, {"value": [{"id": "archive", "displayName": "Archive",
                                        "sections": [section("old", "family")], "sectionGroups": []}]}
            return 200, {"value": [{"id": "family", "displayName": "Family Room", "sections": [],
                                    "sectionGroups": [{"id": "work", "displayName": "Work",
                                                       "sections": [section("tasks", "family")],
                                                       "sectionGroupsUrl": nested}]}]}

        with self.assertRaises(onenote.ratelimit.Deferred):
            inventory.discover(graph, 500, 100000, checkpoint=checkpoint)
        self.assertEqual([group["id"] for group in progress["sectionGroups"]], ["work"])
        books, groups, sections, warnings = inventory.discover(graph, 500, 100000, progress=progress)
        self.assertEqual([(group["id"], group.get("parentGroupId")) for group in groups],
                         [("work", None), ("archive", "work")])
        self.assertEqual([(value["id"], value.get("parentGroupId")) for value in sections],
                         [("tasks", "work"), ("old", "archive")])
        self.assertEqual(warnings, [])

    def test_a_checkpoint_of_another_layout_is_not_resumed(self):
        """An older checkpoint kept the IDs of the groups it had visited and
        nothing else of them, which cannot say what it had found: discovery
        starts over."""
        older = {"tasks": [{"kind": "sections", "url": SHARED + "/notebooks/family/sections", "label": "Family"}],
                 "notebooks": [{"id": "family", "name": "Family"}], "sections": [], "warnings": [],
                 "links": [], "groups": ["work"], "visited": [], "recentChecks": 0}
        cache = {"notebooks": [], "sections": [], "pages": [], "notebookProgress": older}
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "load_order", return_value={}), \
                patch.object(onenote.notebook_inventory, "discover", return_value=([], [], [], [])) as discover, \
                patch.object(onenote, "save_listing", side_effect=cache.update), \
                patch.object(onenote, "out"):
            onenote.cmd_onenote_list(False, incremental=True)
        self.assertIsNone(discover.call_args.kwargs["progress"])

    def test_an_incomplete_discovery_keeps_the_cached_groups(self):
        """A listing cut short cannot say a cached group, or a section's
        place in it, is gone."""
        cached_group = {"id": "work", "name": "Work", "notebook": "Family Room", "notebookId": "family"}
        cached_section = inventory.section_record(section("tasks", "family"), group_id="work")
        cache = {"notebooks": [{"id": "family", "name": "Family Room"}], "sectionGroups": [cached_group],
                 "sections": [cached_section], "pages": [{"id": "p", "title": "Task", "sectionId": "tasks"}],
                 "sectionPages": {"tasks": {"modified": "stamp"}},
                 "pageMetadataVersion": onenote.PAGE_METADATA_VERSION}

        def graph(method, url, **kwargs):
            if url.startswith("/me/onenote/notebooks?"):
                return 200, {"value": [{"id": "family", "displayName": "Family Room", "sections": [],
                                        "sectionGroupsUrl": SHARED + "/notebooks/family/sectionGroups"}]}
            return 403, {"error": {"message": "Access denied"}}

        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "load_order", return_value={}), \
                patch.object(onenote, "access_token", return_value="test-token"), \
                patch.object(onenote, "graph", side_effect=graph), \
                patch.object(onenote, "save_listing", side_effect=cache.update), patch.object(onenote, "out") as output:
            onenote.cmd_onenote_list(False)
        answer = output.call_args.args[0]
        self.assertEqual(answer["sectionGroups"], [cached_group])
        self.assertEqual(answer["sections"], [cached_section])
        self.assertEqual(cache["sectionGroups"], [cached_group])
        self.assertFalse(answer["inventoryComplete"])

    def test_a_section_is_made_in_its_group(self):
        group = {"id": "work", "name": "Work", "notebook": "Family Room", "notebookId": "family",
                 "self": SHARED + "/sectionGroups/work"}
        cache = {"notebooks": [{"id": "family", "name": "Family Room", "userRole": "Owner"}],
                 "sectionGroups": [group], "sections": [], "pages": []}
        made = {"id": "tasks", "displayName": "Tasks", "self": SHARED + "/sections/tasks"}
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "read_payload", return_value={"name": "Tasks"}), \
                patch.object(onenote, "graph", return_value=(201, made)) as graph, \
                patch.object(onenote, "save_listing", side_effect=cache.update), \
                patch.object(onenote, "out") as output:
            onenote.cmd_onenote_create_section("work", "-")
        self.assertEqual(graph.call_args.args[:2], ("POST", SHARED + "/sectionGroups/work/sections"))
        made_section = output.call_args.args[0]["section"]
        self.assertEqual((made_section["parentGroupId"], made_section["notebookId"], made_section["notebook"]),
                         ("work", "family", "Family Room"))
        self.assertEqual(cache["sections"], [made_section])

    def test_a_section_asked_of_a_holder_the_listing_does_not_hold_is_refused(self):
        """The holder could be a notebook or a group: Graph is not asked to
        guess, and the answer says to read the list again."""
        cache = {"notebooks": [{"id": "family", "name": "Family Room", "userRole": "Owner"}],
                 "sectionGroups": [], "sections": [], "pages": []}
        output = io.StringIO()
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "read_payload", return_value={"name": "Tasks"}), \
                patch.object(onenote, "graph") as graph, contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):
                onenote.cmd_onenote_create_section("work", "-")
        self.assertEqual(json.loads(output.getvalue())["error"], onenote.HOLDER_NOT_LISTED)
        graph.assert_not_called()

    def test_a_section_group_is_made_in_its_notebook(self):
        cache = {"notebooks": [{"id": "family", "name": "Family Room", "userRole": "Owner",
                                "self": SHARED + "/notebooks/family"}],
                 "sectionGroups": [], "sections": [], "pages": []}
        made = {"id": "work", "displayName": "Work", "self": SHARED + "/sectionGroups/work"}
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "read_payload", return_value={"name": "Work"}), \
                patch.object(onenote, "graph", return_value=(201, made)) as graph, \
                patch.object(onenote, "save_listing", side_effect=cache.update), \
                patch.object(onenote, "out") as output:
            onenote.cmd_onenote_create_section_group("family", "-")
        self.assertEqual(graph.call_args.args[:2], ("POST", SHARED + "/notebooks/family/sectionGroups"))
        group = output.call_args.args[0]["group"]
        self.assertEqual(group, {"id": "work", "name": "Work", "notebook": "Family Room", "notebookId": "family",
                                 "self": SHARED + "/sectionGroups/work"})
        self.assertEqual(cache["sectionGroups"], [group])

    # A section group's folder is renamed and deleted as a section's file
    # is (page_order_selftest's SectionCommandTests), the group with
    # everything in it.
    GROUP_BOOK = "0-0123456789abcdef!12"
    WORK = "0-0123456789abcdef!s" + "a" * 32
    ARCHIVE = "0-0123456789abcdef!s" + "b" * 32
    GROUP_ITEM = "/drives/0123456789abcdef/items/0123456789abcdef%21s" + "a" * 32

    def grouped_listing(self):
        return {"notebooks": [{"id": self.GROUP_BOOK, "name": "Test", "userRole": "Owner"}],
                "sectionGroups": [{"id": self.WORK, "name": "Work", "notebookId": self.GROUP_BOOK},
                                  {"id": self.ARCHIVE, "name": "Archive", "notebookId": self.GROUP_BOOK,
                                   "parentGroupId": self.WORK},
                                  {"id": "empty", "name": "Empty", "notebookId": self.GROUP_BOOK}],
                "sections": [{"id": "loose", "notebookId": self.GROUP_BOOK, "name": "Loose"},
                             {"id": "tasks", "notebookId": self.GROUP_BOOK, "name": "Tasks", "parentGroupId": self.WORK},
                             {"id": "old", "notebookId": self.GROUP_BOOK, "name": "Old", "parentGroupId": self.ARCHIVE}],
                "pages": [{"id": "p1", "sectionId": "loose"}, {"id": "p2", "sectionId": "tasks"},
                          {"id": "p3", "sectionId": "old"}],
                "sectionPages": {"loose": {"modified": "1"}, "tasks": {"modified": "1"}, "old": {"modified": "1"}},
                "pageListSerial": 1}

    def run_group_command(self, command, cache, item=GROUP_ITEM, graph=(200, {}), raw=(204, "")):
        """The command's answer, whether it failed, and the patched calls —
        run against `cache`, Graph finding the folder at `item` (or raising
        it) and answering `graph` to a rename and `raw` to a delete."""
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
            stack.enter_context(patch.object(onenote, "listing_lock", return_value=contextlib.nullcontext()))
            saved = stack.enter_context(patch.object(onenote, "save_listing"))
            stack.enter_context(patch.object(onenote, "content_index"))
            stack.enter_context(patch.object(onenote, "merge_store"))
            stack.enter_context(patch.object(onenote, "read_payload", return_value={"name": "New"}))
            stack.enter_context(patch.object(onenote.onenote_web, "write_granted", return_value=True))
            if isinstance(item, Exception):
                found = stack.enter_context(patch.object(onenote.onenote_web, "group_item", side_effect=item))
            else:
                found = stack.enter_context(patch.object(onenote.onenote_web, "group_item", return_value=item))
            renamed = stack.enter_context(patch.object(onenote, "graph", return_value=graph))
            deleted = stack.enter_context(patch.object(onenote, "graph_raw", return_value=raw))
            stack.enter_context(contextlib.redirect_stdout(output))
            failed = False
            try:
                command()
            except SystemExit:
                failed = True
        calls = {"saved": saved, "found": found, "renamed": renamed, "deleted": deleted}
        return json.loads(output.getvalue()), failed, calls

    def rename_group(self):
        onenote.cmd_onenote_rename_group(self.WORK, "-")

    def delete_group(self):
        onenote.cmd_onenote_delete_group(self.WORK)

    def test_a_group_is_renamed_as_its_folder(self):
        cache = self.grouped_listing()
        answer, failed, calls = self.run_group_command(self.rename_group, cache)
        self.assertFalse(failed)
        self.assertEqual((answer["ok"], answer["name"]), (True, "New"))
        calls["renamed"].assert_called_once_with("PATCH", self.GROUP_ITEM, {"name": "New"},
                                                 retry_policy=onenote.msgraph.RetryPolicy.NEVER)
        self.assertEqual(calls["found"].call_args.args[0]["id"], self.WORK)
        self.assertEqual([group["name"] for group in cache["sectionGroups"]], ["New", "Archive", "Empty"])

    def test_a_rename_takes_the_name_onedrive_takes(self):
        """A section's and a group's names are OneDrive's: one rule, named
        for what is renamed."""
        with patch.object(onenote, "read_payload", return_value={"name": "  " + "N" * 60 + " "}):
            self.assertEqual(onenote.requested_name("-", "section group"), "N" * 50)
        refused = " ".join(onenote.SECTION_NAME_REFUSED)
        for noun, name, error in (("section", "", "a section needs a name"),
                                  ("section group", " ", "a section group needs a name"),
                                  ("section", "a/b", "A section name cannot contain any of " + refused),
                                  ("section group", "a:b", "A section group name cannot contain any of " + refused)):
            output = io.StringIO()
            with self.subTest(noun=noun, name=name), \
                    patch.object(onenote, "read_payload", return_value={"name": name}), \
                    contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit):
                    onenote.requested_name("-", noun)
                self.assertEqual(json.loads(output.getvalue())["error"], error)

    def test_a_group_rename_onto_a_name_the_notebook_has_is_refused(self):
        cache = self.grouped_listing()
        answer, failed, calls = self.run_group_command(self.rename_group, cache, graph=(409, {}))
        self.assertTrue(failed)
        self.assertIn("already has a section group called", answer["error"])
        self.assertEqual(cache["sectionGroups"][0]["name"], "Work")
        calls["saved"].assert_not_called()

    def test_a_rename_of_a_folder_gone_takes_the_group_off_the_list_with_everything_in_it(self):
        cache = self.grouped_listing()
        answer, failed, calls = self.run_group_command(self.rename_group, cache,
                                                       item=onenote.onenote_web.SectionGone("gone"))
        self.assertFalse(failed)
        self.assertEqual((answer["gone"], answer["pages"]), (True, ["p2", "p3"]))
        calls["renamed"].assert_not_called()
        self.assertEqual([group["id"] for group in cache["sectionGroups"]], ["empty"])
        self.assertEqual([section["id"] for section in cache["sections"]], ["loose"])

    def test_a_group_is_deleted_as_its_folder_with_everything_in_it(self):
        cache = self.grouped_listing()
        answer, failed, calls = self.run_group_command(self.delete_group, cache)
        self.assertFalse(failed)
        self.assertEqual((answer["ok"], answer["pages"]), (True, ["p2", "p3"]))
        calls["deleted"].assert_called_once_with("DELETE", self.GROUP_ITEM, max_bytes=onenote.MAX_PAGE_HTML)
        self.assertEqual([group["id"] for group in cache["sectionGroups"]], ["empty"])
        self.assertEqual([section["id"] for section in cache["sections"]], ["loose"])
        self.assertEqual([page["id"] for page in cache["pages"]], ["p1"])
        self.assertEqual(list(cache["sectionPages"]), ["loose"])
        self.assertGreater(answer["pageListSerial"], 1)

    def test_a_group_delete_onedrive_refuses_changes_nothing(self):
        cache = self.grouped_listing()
        refusal = (403, json.dumps({"error": {"message": "Access denied"}}))
        answer, failed, calls = self.run_group_command(self.delete_group, cache, raw=refusal)
        self.assertTrue(failed)
        self.assertEqual(answer["error"], "Access denied")
        self.assertEqual(len(cache["sectionGroups"]), 3)
        calls["saved"].assert_not_called()

    def test_a_group_the_saved_listing_does_not_hold_is_left_alone(self):
        for cache in (None, {"notebooks": [], "sectionGroups": [], "sections": [], "pages": []}):
            for command in (self.rename_group, self.delete_group):
                with self.subTest(cache=cache, command=command.__name__):
                    answer, failed, calls = self.run_group_command(command, cache)
                    self.assertTrue(failed)
                    self.assertEqual(answer["error"], onenote.GROUP_NOT_LISTED)
                    calls["found"].assert_not_called()
                    calls["saved"].assert_not_called()

    def test_a_group_folder_is_verified_before_it_is_written(self):
        """The folder must be the group's: in its holder, named after it."""
        web = onenote.onenote_web
        drive = "0123456789abcdef"
        group = {"id": self.WORK, "name": "Work", "notebookId": self.GROUP_BOOK}
        folder = {"id": drive + "!s" + "a" * 32, "name": "Work", "folder": {},
                  "parentReference": {"driveId": drive, "driveType": "personal", "id": drive + "!12"}}
        asked = []

        def graph(method, url):
            asked.append((method, url))
            return 200, folder

        self.assertEqual(web.group_item(group, graph), self.GROUP_ITEM)
        self.assertEqual(asked, [("GET", self.GROUP_ITEM + "?$select=id,name,folder,parentReference")])
        nested = dict(group, parentGroupId=self.ARCHIVE)
        inside = dict(folder, parentReference=dict(folder["parentReference"], id=drive + "!s" + "b" * 32))
        self.assertEqual(web.group_item(nested, lambda method, url: (200, inside)), self.GROUP_ITEM)
        wrong = [dict(folder, name="Other"), dict(folder, id="other"),
                 {key: value for key, value in folder.items() if key != "folder"},
                 dict(folder, parentReference=dict(folder["parentReference"], id="elsewhere")),
                 dict(folder, parentReference=dict(folder["parentReference"], driveType="business")),
                 dict(folder, parentReference=dict(folder["parentReference"], driveId="fedcba9876543210"))]
        for metadata in wrong:
            with self.subTest(metadata=metadata):
                with self.assertRaises(web.WebError):
                    web.group_item(group, lambda method, url: (200, metadata))
        # The folder of a group renamed in OneNote since the listing was
        # read: not written under the old name, and the answer says what to do.
        with self.assertRaisesRegex(web.WebError, "refresh the list"):
            web.group_item(group, lambda method, url: (200, dict(folder, name="Other")))
        with self.assertRaises(web.SectionGone):
            web.group_item(group, lambda method, url: (404, {}))
        with self.assertRaises(web.WebError):
            web.group_item(dict(group, notebookId="work-notebook"), graph)

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

        books, groups, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["owned", notebook_id])
        self.assertEqual(books[1]["userRole"], "Reader")
        self.assertEqual(sections[0]["pagesUrl"], SHARED + "/sections/shared/pages")
        self.assertEqual(len(calls), 4)
        self.assertEqual(warnings, [])

    def test_recent_share_requires_a_verified_notebook(self):
        for item in ({"id": "0123456789ABCDEF!123", "folder": {}},
                     {"id": "../bad", "package": {"type": "oneNote"}}):
            graph = self.recent_graph([(200, item)])
            books, _, _, warnings = inventory.discover(graph, 500, 100000)
            self.assertEqual(books, [])
            self.assertTrue(warnings)
            self.assertEqual(graph.call_count, 3)
        graph = self.recent_graph([
            (200, {"id": "0123456789ABCDEF!123", "package": {"type": "oneNote"}}),
            (200, {"id": "some-other-notebook"}),
        ])
        books, _, _, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual(books, [])
        self.assertIn("different notebook", warnings[0])
        self.assertEqual(graph.call_count, 4)

    def test_recent_owned_alias_with_short_cid_skips_notebook_fetch(self):
        graph = self.recent_graph([(200, {
            "id": "123456789ABCDEF!123", "package": {"type": "oneNote"},
        })], known_ids=["0-123456789abcdef!123"])
        books, _, _, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["0-123456789abcdef!123"])
        self.assertEqual(warnings, [])
        self.assertEqual(graph.call_count, 3)

    def test_recent_lookup_failure_preserves_the_primary_inventory(self):
        def graph(method, url, **kwargs):
            if url == inventory.RECENT_NOTEBOOKS:
                return 403, {}
            return 200, {"value": [{"id": "owned", "sections": [section("s")]}]}

        books, groups, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["owned"])
        self.assertEqual([entry["id"] for entry in sections], ["s"])
        self.assertIn("HTTP 403", warnings[0])

    def test_unavailable_recent_links_do_not_fail_the_inventory(self):
        for status in (403, 404, 410):
            with self.subTest(status=status):
                graph = self.recent_graph([(status, {"error": {"code": "accessDenied"}})],
                                          known_ids=["owned"])
                books, _, _, warnings = inventory.discover(graph, 500, 100000)
                self.assertEqual([book["id"] for book in books], ["owned"])
                self.assertEqual(warnings, [])

    def test_recent_server_failure_still_warns(self):
        graph = self.recent_graph([(503, {})], known_ids=["owned"])
        books, _, _, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual([book["id"] for book in books], ["owned"])
        self.assertIn("HTTP 503", warnings[0])

    def cached_share_after_failed_recent_link(self, status):
        shared_section = inventory.section_record(section("s", "family"))
        cache = {"notebooks": [{"id": "owned", "name": "Mine"},
                               {"id": "family", "name": "Family", "self": SHARED + "/notebooks/family"}],
                 "sections": [shared_section],
                 "pages": [{"id": "p", "title": "Cached shared page", "sectionId": "s"}],
                 "sectionPages": {"s": {"modified": "stamp"}},
                 "pageMetadataVersion": onenote.PAGE_METADATA_VERSION}
        book = {"id": "family", "displayName": "Family", "userRole": "Reader",
                "sections": [section("s", "family")], "sectionGroups": []}
        graph = self.recent_graph([(403, {}), (status, book if status == 200 else {})],
                                  known_ids=["owned"])
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "load_order", return_value={}), \
                patch.object(onenote, "graph", graph), \
                patch.object(onenote, "save_listing", side_effect=cache.update), \
                patch.object(onenote, "out") as output:
            onenote.cmd_onenote_list(False, incremental=True)
        self.assertEqual(graph.call_args.args[1], SHARED + "/notebooks/family?$expand=" + inventory.NOTEBOOK_EXPAND)
        return output.call_args.args[0], cache

    def test_removed_cached_notebook_does_not_return_from_recent_history(self):
        for status in (404, 410):
            with self.subTest(status=status):
                answer, cache = self.cached_share_after_failed_recent_link(status)
                self.assertEqual([book["id"] for book in answer["notebooks"]], ["owned"])
                self.assertEqual(answer["pages"], [])
                self.assertEqual(answer["listingWarnings"], [])
                self.assertTrue(answer["inventoryComplete"])
                self.assertNotIn("s", cache["sectionPages"])

    def test_cached_shared_notebook_is_verified_when_recent_link_is_unavailable(self):
        answer, _ = self.cached_share_after_failed_recent_link(200)
        self.assertEqual([book["id"] for book in answer["notebooks"]], ["owned", "family"])
        self.assertEqual([page["id"] for page in answer["pages"]], ["p"])
        self.assertEqual(answer["listingWarnings"], [])
        self.assertTrue(answer["inventoryComplete"])

    def test_cached_permission_failure_still_preserves_the_notebook(self):
        answer, _ = self.cached_share_after_failed_recent_link(403)
        self.assertEqual([book["id"] for book in answer["notebooks"]], ["owned", "family"])
        self.assertEqual([page["id"] for page in answer["pages"]], ["p"])
        self.assertIn("Family: could not retrieve the list (HTTP 403)", answer["listingWarnings"])
        self.assertFalse(answer["inventoryComplete"])

    def test_cached_verification_resumes_without_repeating_recent_lookups(self):
        cached = [{"id": "family", "name": "Family"}]
        progress = {}

        def checkpoint(state):
            progress.clear()
            progress.update(copy.deepcopy(state))

        graph = self.recent_graph([(403, {}), onenote.ratelimit.Deferred(60), (404, {})],
                                  known_ids=["owned"])
        with self.assertRaises(onenote.ratelimit.Deferred):
            inventory.discover(graph, 500, 100000, checkpoint=checkpoint, cached_notebooks=cached)
        books, _, _, warnings = inventory.discover(graph, 500, 100000, progress=progress,
                                                cached_notebooks=cached)
        self.assertEqual([book["id"] for book in books], ["owned"])
        self.assertEqual(warnings, [])
        self.assertEqual(graph.call_count, 5)

    def test_missing_recent_notebook_is_not_verified_twice_from_cache(self):
        cached = [{"id": "0-0123456789ABCDEF!123", "name": "Family"}]
        graph = self.recent_graph([
            (200, {"id": "0123456789ABCDEF!123", "package": {"type": "oneNote"}}),
            (404, {}),
        ], known_ids=["owned"])
        books, _, _, warnings = inventory.discover(graph, 500, 100000, cached_notebooks=cached)
        self.assertEqual([book["id"] for book in books], ["owned"])
        self.assertEqual(warnings, [])
        self.assertEqual(graph.call_count, 4)

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

        books, groups, sections, warnings = inventory.discover(graph, 500, 100000)
        self.assertEqual(books, [])
        self.assertEqual(len(warnings), 1)

    def test_failed_notebook_listing_preserves_the_previous_cache(self):
        cache = {"notebooks": [{"id": "book", "name": "Mine"}], "sections": [], "pages": []}
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "load_order", return_value={}), \
                patch.object(onenote, "graph", return_value=(500, {"error": {"message": "Unavailable"}})), \
                patch.object(onenote, "save_listing") as save, patch.object(provider_io, "out") as output:
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
            stack.enter_context(patch.object(onenote, "files_read_granted", return_value=False))
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
                 "sectionPages": {"s": {"modified": "stamp"}},
                 "pageMetadataVersion": onenote.PAGE_METADATA_VERSION}

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
                 "sectionGroups": [{"id": "g", "notebookId": "family"}],
                 "sections": [{"id": "s", "notebookId": "family"}],
                 "pages": [{"id": "p", "sectionId": "s"}]}
        commands = ((onenote.cmd_onenote_update, ("p", "-")),
                    (onenote.cmd_onenote_delete, ("p",)),
                    (onenote.cmd_onenote_create, ("s", "-")),
                    (onenote.cmd_onenote_create_section, ("family", "-")),
                    (onenote.cmd_onenote_create_section, ("g", "-")),
                    (onenote.cmd_onenote_create_section_group, ("family", "-")))
        with patch.object(onenote, "load_listing", return_value=cache), \
                patch.object(onenote, "graph") as graph, \
                patch.object(onenote, "graph_raw") as raw, \
                patch.object(onenote, "read_payload") as payload, \
                patch.object(provider_io, "out") as output:
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
