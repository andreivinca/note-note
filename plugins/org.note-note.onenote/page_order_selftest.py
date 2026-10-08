"""Page identity, conditional revisions, hierarchy preservation and write failures."""
import copy
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote  # noqa: E402
import page_order as ordering  # noqa: E402
import revision_objects as revisions  # noqa: E402
import web_session as web  # noqa: E402


def guid(number):
    return "00000000-0000-0000-0000-%012d" % number


def ref(number):
    return "{%s}{1}" % guid(number)


def obj(number, kind, properties):
    return {"ObjectId": guid(number) + "|1", "ClassId": kind, "Properties": properties}


def fixture():
    root = obj(1, revisions.SECTION, [revisions.CHILDREN, ref(2) + "," + ref(3), 123, "preserve me"])
    objects = [root,
               obj(2, revisions.PAGE_SERIES, [revisions.PAGE_CELLS, ref(10) + "," + ref(11),
                                           revisions.PAGE_METADATA_REFS, ref(20) + "," + ref(21)]),
               obj(3, revisions.PAGE_SERIES, [revisions.PAGE_CELLS, ref(12), revisions.PAGE_METADATA_REFS, ref(22)])]
    pages = []
    for index, level in enumerate((0, 1, 0)):
        objects.append(obj(20 + index, revisions.PAGE_METADATA,
                           [revisions.ENTITY_GUID, guid(100 + index), revisions.PAGE_LEVEL, str(level + 1)]))
        pages.append({"id": "opaque-%d" % index, "clientId": guid(100 + index), "level": level,
                      "title": "note %d" % index, "order": index})
    state = {"RootCellId": guid(50) + "|1", "LatestRevisionId": guid(60) + "|1", "ClientKnowledge": "known",
             "RevisionList": [{"Id": guid(60) + "|1", "BaseId": web.NIL,
                               "RootObjectDescriptors": [{"RootId": revisions.CONTENT_ROOT, "ObjectId": root["ObjectId"]}],
                               "ObjectGroups": [{"Id": guid(61) + "|1", "Objects": objects}]}]}
    return state, pages


class StructureTests(unittest.TestCase):
    def test_native_page_query_and_public_identity(self):
        url = onenote.section_pages_url("section", "https://graph.microsoft.com/v1.0/users/owner/onenote/sections/s/pages")
        self.assertIn("pagelevel=true", url)
        self.assertIn("$orderby=order", url)
        self.assertIn("order,level,links", url)
        raw = {"id": "opaque", "order": 42, "level": 1,
               "links": {"oneNoteClientUrl": {"href": "onenote:https://example.test/#Title&page-id={%s}&end" % guid(10)}}}
        page = onenote.page_record(raw, {"id": "section"})
        self.assertEqual((page["order"], page["level"], page["clientId"]), (42, 1, guid(10)))
        self.assertNotIn("order", onenote.page_record({"id": "p", "order": True}, {"id": "s"}))
        self.assertIsNone(revisions.client_guid({"links": {"oneNoteClientUrl": {"href": "https://evil.test/?page-id=x"}}}))

    def test_parent_order_preserves_subpages_and_all_other_properties(self):
        state, pages = fixture()
        before = copy.deepcopy(state)
        order = ordering.SectionOrder(state, pages)
        root = order.arranged_root(["opaque-0", "opaque-2"], ["opaque-2", "opaque-0"])
        self.assertEqual(root["Properties"], [revisions.CHILDREN, ref(3) + "," + ref(2), 123, "preserve me"])
        self.assertEqual([page["id"] for page in order.arranged_pages(pages, ["opaque-2", "opaque-0"])],
                         ["opaque-2", "opaque-0", "opaque-1"])
        self.assertEqual(state, before)

    def test_inherited_revisions_follow_only_latest_ancestry(self):
        state, pages = fixture()
        latest = {"Id": guid(70) + "|1", "BaseId": state["LatestRevisionId"], "ObjectGroups": [{"Objects": [
            obj(1, revisions.SECTION, [revisions.CHILDREN, ref(2) + "," + ref(3), 123, "updated"]) ]}]}
        unrelated = {"Id": guid(71) + "|1", "BaseId": web.NIL, "ObjectGroups": [{"Objects": [
            obj(1, revisions.SECTION, [revisions.CHILDREN, "bad"])]}]}
        state["RevisionList"] = [latest, unrelated] + state["RevisionList"]
        state["LatestRevisionId"] = latest["Id"]
        order = ordering.SectionOrder(state, pages)
        self.assertEqual(revisions.properties(order.root)[123], "updated")

    def test_metadata_listed_twice_joins_each_cell_to_the_next_distinct_page(self):
        state, pages = fixture()
        objects = state["RevisionList"][0]["ObjectGroups"][0]["Objects"]
        objects.append(obj(23, revisions.PAGE_METADATA,
                           [revisions.ENTITY_GUID, guid(102), revisions.PAGE_LEVEL, "1"]))
        objects[2]["Properties"][3] = ref(22) + "," + ref(23)
        self.assertEqual(ordering.SectionOrder(state, pages).parents, ["opaque-0", "opaque-2"])

    def test_concurrent_order_partial_membership_and_duplicates_are_rejected(self):
        state, pages = fixture()
        order = ordering.SectionOrder(state, pages)
        for expected, wanted in ((["opaque-2", "opaque-0"], ["opaque-0", "opaque-2"]),
                                 (["opaque-0", "opaque-2"], ["opaque-0"]),
                                 (["opaque-0", "opaque-2"], ["opaque-0", "opaque-0"]),
                                 (["opaque-0", "opaque-2"], ["opaque-1", "opaque-0"])):
            with self.subTest(wanted=wanted), self.assertRaises(web.WebError):
                order.arranged_root(expected, wanted)
        with self.assertRaises(web.WebError):
            ordering.SectionOrder(state, pages[::-1])

    def test_invalid_histories_and_metadata_cannot_be_written(self):
        for damage in ("missing-base", "cycle", "duplicate-revision", "operations", "missing-page", "wrong-level", "duplicate-guid"):
            state, pages = fixture()
            revision = state["RevisionList"][0]
            if damage == "missing-base":
                revision["BaseId"] = "missing"
            elif damage == "cycle":
                revision["BaseId"] = revision["Id"]
            elif damage == "duplicate-revision":
                state["RevisionList"].append(copy.deepcopy(revision))
            elif damage == "operations":
                revision["Ops"] = ["unknown incremental operation"]
            elif damage == "missing-page":
                pages.pop()
            elif damage == "wrong-level":
                pages[1]["level"] = 0
            elif damage == "duplicate-guid":
                pages[1]["clientId"] = pages[0]["clientId"]
            with self.subTest(damage=damage), self.assertRaises(web.WebError):
                ordering.SectionOrder(state, pages)

    def test_write_contains_only_section_root_and_readback_verifies_order(self):
        state, pages = fixture()
        session = Mock()
        session.read_section.side_effect = [state, copy.deepcopy(state)]

        def commit(current, root):
            self.assertIs(current, state)
            session.read_section.side_effect = iter([dict(state, RevisionList=[dict(state["RevisionList"][0],
                ObjectGroups=[{"Objects": [root] + state["RevisionList"][0]["ObjectGroups"][0]["Objects"][1:]}])])])

        session.write_section.side_effect = commit
        arranged = ordering.reorder(session, pages, ["opaque-0", "opaque-2"], ["opaque-2", "opaque-0"])
        self.assertEqual([page["id"] for page in arranged], ["opaque-2", "opaque-0", "opaque-1"])
        session.write_section.assert_called_once()

    def test_old_cached_page_lists_stay_complete_until_their_section_is_opened(self):
        section = {"id": "s", "modified": "unchanged"}
        old = {"sections": [section], "pages": [{"id": "p", "sectionId": "s"}],
               "sectionPages": {"s": {"modified": "unchanged"}},
               "sectionProgress": {"s": {"url": "old cursor"}}}
        listing = onenote.Listing(old, [section])
        self.assertEqual(listing.pages(), old["pages"])
        self.assertEqual(listing.pending(), [])
        self.assertEqual(listing.outdated(), ["s"])
        self.assertEqual(listing.progress, {})
        listing.record(section, old["pages"])
        self.assertEqual(listing.outdated(), [])


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.session = web.Session({"WOPIsrc": "https://example.test", "access_token": "private", "access_token_ttl": 999})

    def response(self, kind, code=0, **kwargs):
        return json.dumps({"Responses": [[kind, dict(StatusCode=code, **kwargs)]]}).encode()

    def test_preview_and_frame_identity_validation(self):
        item = "0123456789ABCDEF!123"
        url = "https://my.microsoftpersonalcontent.com/personal/0123456789abcdef/_layouts/15/embed.aspx?access_token=private#view"
        self.assertFalse(web.preview_url(url).endswith("#view"))
        for bad in (url.replace("my.microsoftpersonalcontent.com", "evil.test"),
                    url.replace("https://", "http://"), url.replace("embed.aspx", "Doc.aspx"),
                    url.replace("https://", "https://user@")):
            with self.subTest(url=bad), self.assertRaises(web.WebError):
                web.preview_url(bad)
        info = {"wopiSrc": "https://my.microsoftpersonalcontent.com/personal/0123456789abcdef/_vti_bin/wopi.ashx/files/" + item,
                "wopiTokenAppAndUser": "private", "wopiTokenAppAndUserTtl": int((time.time() + 60) * 1000)}
        raw = ("var g_fileInfo = " + json.dumps(info) + ";").encode()
        self.assertEqual(web.frame_info(raw, item)["access_token"], "private")
        with self.assertRaises(web.WebError):
            web.frame_info(raw, "0123456789ABCDEF!456")

    def test_a_section_file_is_found_in_its_owners_drive(self):
        """A notebook shared with the account is reached by the owner's drive."""
        item = "0123456789ABCDEF!123"
        path = "/drives/0123456789ABCDEF/items/0123456789ABCDEF%21123"
        metadata = {"id": item, "name": "Section.one", "file": {},
                    "parentReference": {"driveId": "0123456789abcdef", "driveType": "personal"}}
        info = {"wopiSrc": "https://my.microsoftpersonalcontent.com/personal/0123456789abcdef/_vti_bin/wopi.ashx/files/" + item,
                "wopiTokenAppAndUser": "private", "wopiTokenAppAndUserTtl": int((time.time() + 60) * 1000)}
        frame = ("var g_fileInfo = " + json.dumps(info) + ";").encode()
        preview = {"getUrl": "https://my.microsoftpersonalcontent.com/personal/0123456789abcdef/_layouts/15/embed.aspx?access_token=private"}
        graph = Mock(side_effect=[(200, metadata), (200, preview)])
        with patch.object(web.Transport, "request", return_value=(200, frame, {})):
            session = web.Session.for_section({"id": "0-" + item}, graph)
        self.assertEqual([call.args[:2] for call in graph.call_args_list],
                         [("GET", path + "?$select=id,name,file,parentReference"), ("POST", path + "/preview")])
        self.assertEqual(session.headers["X-AccessToken"], "private")
        for parent in ({"driveId": "FEDCBA9876543210", "driveType": "personal"},
                       {"driveId": "0123456789ABCDEF", "driveType": "business"}, None):
            graph = Mock(return_value=(200, dict(metadata, parentReference=parent)))
            with self.subTest(parent=parent), self.assertRaises(web.WebError):
                web.Session.for_section({"id": "0-" + item}, graph)
            graph.assert_called_once()

    def test_read_discovers_version_and_retries_rejected_key_challenge(self):
        with patch.object(self.session, "request", side_effect=[
                (503, b"", {"X-OfficeVersion": "current"}),
                (412, b"", {"X-NewKey": "challenge"}),
                (200, self.response(2), {})]) as request:
            self.session.read_section()
        self.assertEqual(request.call_count, 3)
        self.assertEqual(self.session.headers["X-OfficeVersion"], "current")
        self.assertEqual(self.session.headers["X-Key"], "challenge")

    def test_uncertain_write_is_never_replayed(self):
        state, _ = fixture()
        root = state["RevisionList"][0]["ObjectGroups"][0]["Objects"][0]
        with patch.object(self.session, "request", return_value=(503, b"", {"X-OfficeVersion": "current"})) as request:
            with self.assertRaises(web.WebError) as caught:
                self.session.write_section(state, root)
        self.assertEqual(request.call_count, 1)
        self.assertIsNone(caught.exception.kind)

    def test_write_uses_fresh_base_revision_and_only_one_root_object(self):
        state, _ = fixture()
        root = state["RevisionList"][0]["ObjectGroups"][0]["Objects"][0]
        with patch.object(self.session, "request", return_value=(200, self.response(3), {})) as request:
            self.session.write_section(state, root)
        sent = json.loads(request.call_args.args[2])["srs"][0][1]
        self.assertEqual(sent["ExpectedLatestId"], state["LatestRevisionId"])
        self.assertEqual(sent["Revision"]["BaseId"], state["LatestRevisionId"])
        self.assertEqual(sent["Revision"]["ObjectGroups"][0]["Objects"], [root])

    def test_conflicts_and_missing_write_permission_are_visible_failures(self):
        for code in (2, 4, 5, 7):
            with patch.object(self.session, "request", return_value=(200, self.response(3, code), {})) as request:
                with self.assertRaises(web.WebError) as caught:
                    self.session.operation(3, {})
                self.assertEqual(request.call_count, 1)
                self.assertIsNone(caught.exception.kind)

    def test_transport_never_exposes_signed_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"NOTE_NOTE_RATE_DIR": directory}):
            with patch.object(self.session.opener, "open", side_effect=urllib.error.URLError("url?access_token=private")):
                with self.assertRaises(web.WebError) as caught:
                    self.session.request("POST", web.ENDPOINT, mutation=True)
        self.assertNotIn("private", str(caught.exception))

    def test_broken_response_to_a_write_is_an_uncertain_outcome(self):
        for error in (http.client.IncompleteRead(b"partial"), http.client.BadStatusLine("garbage")):
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"NOTE_NOTE_RATE_DIR": directory}):
                with patch.object(self.session.opener, "open", side_effect=error) as request:
                    with self.subTest(error=type(error).__name__), self.assertRaises(web.WebError) as caught:
                        self.session.request("POST", web.ENDPOINT, mutation=True)
            self.assertEqual(request.call_count, 1)
            self.assertIn("refresh the section", str(caught.exception))


class CommandTests(unittest.TestCase):
    def command(self, stack, cache, pages, listings, arranged=None, error=None):
        """cmd_reorder_pages against `cache`, with Graph answering `listings`."""
        stack.enter_context(patch.object(onenote, "read_payload", return_value={
            "sectionId": "s", "expected": ["opaque-0", "opaque-2"], "order": ["opaque-2", "opaque-0"]}))
        stack.enter_context(patch.object(onenote, "cached_resource", return_value={"id": "s"}))
        stack.enter_context(patch.object(onenote, "require_revision_access"))
        collect = stack.enter_context(patch.object(onenote, "collect_section_pages", side_effect=listings))
        stack.enter_context(patch.object(web.Session, "for_section"))
        stack.enter_context(patch.object(ordering, "reorder", return_value=arranged, side_effect=error))
        stack.enter_context(patch.object(onenote, "listing_lock", return_value=contextlib.nullcontext()))
        stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
        stack.enter_context(patch.object(onenote, "load_order", return_value={}))
        sleep = stack.enter_context(patch.object(onenote.time, "sleep"))
        saved = stack.enter_context(patch.object(onenote, "save_listing"))
        return collect, sleep, saved

    def test_post_write_errors_never_request_job_replay_and_invalidate_the_section(self):
        _, pages = fixture()
        for error in (onenote.msgraph.GraphError("readback failed", kind="transient"),
                      onenote.ratelimit.Throttled(60), http.client.IncompleteRead(b"cut off")):
            cache = {"sections": [{"id": "s"}], "pages": pages,
                     "sectionPages": {"s": {"modified": "unchanged"}}, "pageListSerial": 1,
                     "inventoryComplete": True}
            output = io.StringIO()
            with self.subTest(error=type(error).__name__), contextlib.ExitStack() as stack:
                _, _, saved = self.command(stack, cache, pages, [{"pages": pages}], error=error)
                stack.enter_context(contextlib.redirect_stdout(output))
                with self.assertRaises(SystemExit):
                    onenote.cmd_reorder_pages("-")
            result = json.loads(output.getvalue())
            self.assertIn("error", result)
            self.assertNotIn("kind", result)
            self.assertFalse(saved.call_args.args[0]["inventoryComplete"])
            self.assertNotIn("s", saved.call_args.args[0]["sectionPages"])
            self.assertGreater(saved.call_args.args[0]["pageListSerial"], 1)

    def test_graph_confirmation_backs_off_and_never_waits_after_its_last_listing(self):
        _, pages = fixture()
        arranged = ordering.SectionOrder(fixture()[0], pages).arranged_pages(pages, ["opaque-2", "opaque-0"])
        stale = {"pages": pages}
        for listings, sleeps, confirmed in (([stale, stale, {"pages": arranged}], [1, 2], True),
                                            ([stale, stale, stale, stale], [1, 2, 4], False)):
            cache = {"sections": [{"id": "s", "name": "S", "notebookId": "n"}], "pages": pages, "sectionPages": {"s": {"modified": "m"}},
                     "pageListSerial": 1}
            output = io.StringIO()
            with self.subTest(confirmed=confirmed), contextlib.ExitStack() as stack:
                collect, sleep, _ = self.command(stack, cache, pages, listings, arranged=arranged)
                stack.enter_context(contextlib.redirect_stdout(output))
                if confirmed:
                    onenote.cmd_reorder_pages("-")
                else:
                    with self.assertRaises(SystemExit):
                        onenote.cmd_reorder_pages("-")
            self.assertEqual([call.args[0] for call in sleep.call_args_list], sleeps)
            self.assertEqual(collect.call_count, len(listings))
            self.assertEqual("error" in json.loads(output.getvalue()), not confirmed)

    def test_revisions_require_a_personal_notebook_the_account_can_edit(self):
        personal = "0-0123456789abcdef!12"
        for role, notebook, allowed in (("Owner", personal, True), ("owner", personal, True),
                                        ("Contributor", personal, True), ("Reader", personal, False),
                                        ("Owner", "1-business-id", False), (None, personal, False)):
            cache = {"notebooks": [{"id": notebook, "userRole": role}],
                     "sections": [{"id": "s", "notebookId": notebook}]}
            output = io.StringIO()
            with self.subTest(role=role, notebook=notebook), contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
                stack.enter_context(patch.object(web, "write_granted", return_value=True))
                stack.enter_context(contextlib.redirect_stdout(output))
                if allowed:
                    onenote.require_revision_access("s", "not writable", "not granted")
                else:
                    with self.assertRaises(SystemExit):
                        onenote.require_revision_access("s", "not writable", "not granted")
            self.assertEqual(output.getvalue() == "", allowed)

    def test_revisions_require_the_write_grant(self):
        cache = {"notebooks": [{"id": "0-0123456789abcdef!12", "userRole": "Owner"}],
                 "sections": [{"id": "s", "notebookId": "0-0123456789abcdef!12"}]}
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
            stack.enter_context(patch.object(web, "write_granted", return_value=False))
            stack.enter_context(contextlib.redirect_stdout(output))
            with self.assertRaises(SystemExit):
                onenote.require_revision_access("s", "not writable", "not granted")
        self.assertEqual(json.loads(output.getvalue())["error"], "not granted")

    def test_a_created_page_is_recorded_as_a_top_level_page(self):
        created = {"id": "new", "title": "New", "lastModifiedDateTime": "2026-10-06T00:00:00Z",
                   "links": {"oneNoteClientUrl": {"href": "onenote:https://example.test/#New&page-id={%s}&end" % guid(9)}}}
        cache = {"sections": [{"id": "s"}], "pages": [], "pageListSerial": 1}
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "require_writable"))
            stack.enter_context(patch.object(onenote, "merge_account", return_value="account"))
            stack.enter_context(patch.object(onenote, "read_payload", return_value={"title": "New", "body": ""}))
            stack.enter_context(patch.object(onenote, "cached_resource", return_value={"id": "s"}))
            stack.enter_context(patch.object(onenote, "graph_raw", return_value=(201, json.dumps(created))))
            stack.enter_context(patch.object(onenote, "listing_lock", return_value=contextlib.nullcontext()))
            stack.enter_context(patch.object(onenote, "load_listing", return_value=cache))
            saved = stack.enter_context(patch.object(onenote, "save_listing"))
            stack.enter_context(patch.object(onenote, "content_index", side_effect=OSError))
            store = stack.enter_context(patch.object(onenote, "merge_store"))
            store.return_value.__enter__.return_value.open.return_value = {"title": "New", "body": ""}
            stack.enter_context(contextlib.redirect_stdout(output))
            onenote.cmd_onenote_create("s", "-")
        page = json.loads(output.getvalue())["page"]
        self.assertEqual((page["level"], page["clientId"]), (0, guid(9)))
        self.assertEqual(saved.call_args.args[0]["pages"], [page])


if __name__ == "__main__":
    unittest.main()
