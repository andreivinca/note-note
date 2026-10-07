"""Blank-line removal: exact element joins, refusals and one conditional revision."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote  # noqa: E402
import blank_lines  # noqa: E402
import page_order as ordering  # noqa: E402
import web_session as web  # noqa: E402
from onenote_patch import BlankLines  # noqa: E402

PAGE = "7d616289-a1fb-4bad-b296-4286b6c4813e"
CLIENT = "9090e046-a3bb-4572-9032-7bd4f96bc7be"


def ref(number):
    return "%s|%d" % (PAGE, number)


def braced(*numbers):
    return ",".join("{%s}{%d}" % (PAGE, number) for number in numbers)


def graph_id(number, tag="p"):
    return "%s:{%s}{%d}" % (tag, PAGE, number)


def obj(number, kind, *properties):
    return {"ObjectId": ref(number), "ClassId": kind, "Properties": list(properties)}


def line(number, text, children=()):
    """An element `number` holding rich text `number + 1`, as OneNote stores a line.

    Text None leaves the text property out, as OneNote clients do for some
    blank lines; a tuple gives the text object's properties as they are.
    """
    properties = [blank_lines.CONTENT, braced(number + 1)]
    if children:
        properties += [ordering.CHILDREN, braced(*children)]
    if text is None:
        content = [0x10001CFE, "1033"]
    elif isinstance(text, tuple):
        content = list(text)
    else:
        content = [blank_lines.TEXT, text]
    return [obj(number, blank_lines.ELEMENT, *properties),
            obj(number + 1, blank_lines.RICH_TEXT, *content)]


def page_state(lines, outline=(20, 22, 24, 26)):
    """A page cell: its own metadata, and an outline of the given lines."""
    objects = [obj(10, 0x6000C, 123, "keep", ordering.CHILDREN, braced(*outline)),
               obj(5, ordering.PAGE_METADATA, ordering.ENTITY_GUID, CLIENT)]
    for number, text, *children in lines:
        objects += line(number, text, *children)
    return {"LatestRevisionId": "latest|1", "ClientKnowledge": "known",
            "RevisionList": [{"Id": "latest|1", "BaseId": web.NIL,
                              "RootObjectDescriptors": [{"RootId": "metadata-root|2", "ObjectId": ref(5)}],
                              "ObjectGroups": [{"Objects": objects}]}]}


# Alpha, a line break written through Graph, an empty line from a client, Bravo.
LINES = [(20, "Alpha"), (22, "\x0b"), (24, ""), (26, "Bravo")]


def series_guid(index):
    return "00000001-0000-0000-0000-%012d" % index


def cell_guid(index):
    return "00000002-0000-0000-0000-%012d" % index


def section_state(guids=((CLIENT, CLIENT),)):
    """A section root whose page groups list each page's metadata, possibly twice."""
    root = {"ObjectId": "root|1", "ClassId": ordering.SECTION,
            "Properties": [ordering.CHILDREN, ",".join("{%s}{1}" % series_guid(index) for index in range(len(guids)))]}
    objects = [root]
    for index, group in enumerate(guids):
        metadata = []
        for position, guid in enumerate(group):
            identifier = "00000003-0000-0000-%04d-%012d" % (index, position)
            metadata.append("{%s}{1}" % identifier)
            objects.append({"ObjectId": identifier + "|1", "ClassId": ordering.PAGE_METADATA,
                            "Properties": [ordering.ENTITY_GUID, guid, ordering.PAGE_LEVEL, "1"]})
        objects.append({"ObjectId": series_guid(index) + "|1", "ClassId": ordering.PAGE_SERIES,
                        "Properties": [ordering.PAGE_CELLS, "{%s}{1}" % cell_guid(index),
                                       ordering.PAGE_METADATA_REFS, ",".join(metadata)]})
    return {"RootCellId": "section|1", "LatestRevisionId": "section|1", "ClientKnowledge": "known",
            "RevisionList": [{"Id": "section|1", "BaseId": web.NIL,
                              "RootObjectDescriptors": [{"RootId": ordering.CONTENT_ROOT, "ObjectId": "root|1"}],
                              "ObjectGroups": [{"Objects": objects}]}]}


def children(parent):
    return ordering.references(ordering.properties(parent)[ordering.CHILDREN])


class JoinTests(unittest.TestCase):
    def test_only_requested_blank_lines_leave_their_parent(self):
        state = page_state(LINES)
        before = copy.deepcopy(state)
        for removed, kept in (((0,), [20, 24, 26]), ((1,), [20, 22, 26]), ((0, 1), [20, 26])):
            with self.subTest(removed=removed):
                run = BlankLines(graph_id(21), graph_id(27), 2, removed)
                parents = blank_lines.updated_parents(blank_lines.Page(state), (run,))
                self.assertEqual(len(parents), 1)
                self.assertEqual(children(parents[0]), [ref(number) for number in kept])
                self.assertEqual(parents[0]["Properties"][:2], [123, "keep"])
        self.assertEqual(state, before)

    def test_a_text_object_without_text_is_a_blank_line(self):
        state = page_state([(20, "Alpha"), (22, None), (24, ""), (26, "Bravo")])
        run = BlankLines(graph_id(21), graph_id(27), 2, (0,))
        parents = blank_lines.updated_parents(blank_lines.Page(state), (run,))
        self.assertEqual(children(parents[0]), [ref(20), ref(24), ref(26)])

    def test_an_id_naming_the_element_itself_is_a_neighbour(self):
        # A list's ID names the element it hangs under.
        run = BlankLines(graph_id(21), graph_id(26, "ul"), 2, (0, 1))
        parents = blank_lines.updated_parents(blank_lines.Page(page_state(LINES)), (run,))
        self.assertEqual(children(parents[0]), [ref(20), ref(26)])

    def test_runs_in_one_parent_are_written_as_one_object(self):
        state = page_state(LINES + [(28, "\x0b"), (30, "Charlie")], outline=(20, 22, 24, 26, 28, 30))
        runs = (BlankLines(graph_id(21), graph_id(27), 2, (0,)), BlankLines(graph_id(27), graph_id(31), 1, (0,)))
        parents = blank_lines.updated_parents(blank_lines.Page(state), runs)
        self.assertEqual([children(parent) for parent in parents], [[ref(20), ref(24), ref(26), ref(30)]])

    def test_anything_but_matching_blank_lines_is_refused(self):
        cases = {
            "fewer breaks than lines": (LINES, BlankLines(graph_id(21), graph_id(27), 1, (0,))),
            "text between neighbours": ([(20, "Alpha"), (22, "words"), (24, ""), (26, "Bravo")],
                                        BlankLines(graph_id(21), graph_id(27), 2, (0,))),
            "ASCII text between neighbours": ([(20, "Alpha"), (22, (blank_lines.ASCII_TEXT, "words")), (24, ""), (26, "Bravo")],
                                              BlankLines(graph_id(21), graph_id(27), 2, (0,))),
            "list under a blank line": ([(20, "Alpha"), (22, "\x0b", (40,)), (24, ""), (26, "Bravo"), (40, "item")],
                                        BlankLines(graph_id(21), graph_id(27), 2, (0,))),
            "neighbours in different parents": ([(20, "Alpha", (40,)), (22, "\x0b"), (24, ""), (26, "Bravo"), (40, "item")],
                                                BlankLines(graph_id(41), graph_id(27), 2, (0,))),
            "unknown neighbour": (LINES, BlankLines(graph_id(99), graph_id(27), 2, (0,))),
            "unexpected ID": (LINES, BlankLines("p:first", graph_id(27), 2, (0,))),
            "neighbours reversed": (LINES, BlankLines(graph_id(27), graph_id(21), 2, (0,))),
        }
        for name, (lines, run) in cases.items():
            with self.subTest(name), self.assertRaises(web.WebError):
                blank_lines.updated_parents(blank_lines.Page(page_state(lines)), (run,))

    def test_page_cell_joins_each_cell_to_the_next_distinct_page(self):
        other = "11111111-2222-3333-4444-555555555555"
        state = section_state(((other, other), (CLIENT, CLIENT)))
        self.assertEqual(ordering.page_cell(state, CLIENT), cell_guid(1) + "|1")
        for guids in (((other,),), ((CLIENT, other),)):
            with self.subTest(guids=guids), self.assertRaises(web.WebError):
                ordering.page_cell(section_state(guids), CLIENT)


class RemovalTests(unittest.TestCase):
    def session(self, page, confirmed):
        session = Mock()
        session.read_section.return_value = section_state()
        session.read.side_effect = [page, confirmed]
        return session

    def test_one_revision_to_the_page_cell_then_a_confirming_read(self):
        state = page_state(LINES)
        run = BlankLines(graph_id(21), graph_id(27), 2, (0, 1))
        expected = blank_lines.updated_parents(blank_lines.Page(state), (run,))
        confirmed = page_state([(20, "Alpha"), (26, "Bravo")], outline=(20, 26))
        session = self.session(state, confirmed)
        blank_lines.remove(session, CLIENT, (run,))
        cell = cell_guid(0) + "|1"
        self.assertEqual([call.args for call in session.read.call_args_list], [(cell,), (cell,)])
        session.write.assert_called_once_with(cell, state, expected)

    def test_unconfirmed_removal_is_a_visible_failure(self):
        state = page_state(LINES)
        session = self.session(state, copy.deepcopy(state))
        with self.assertRaises(web.WebError):
            blank_lines.remove(session, CLIENT, (BlankLines(graph_id(21), graph_id(27), 2, (0,)),))
        session.write.assert_called_once()

    def test_a_cell_holding_another_page_is_never_written(self):
        state = page_state(LINES)
        state["RevisionList"][0]["ObjectGroups"][0]["Objects"][1]["Properties"][1] = "11111111-2222-3333-4444-555555555555"
        session = self.session(state, state)
        with self.assertRaises(web.WebError):
            blank_lines.remove(session, CLIENT, (BlankLines(graph_id(21), graph_id(27), 2, (0,)),))
        session.write.assert_not_called()

    def test_page_write_names_the_page_cell_and_every_object(self):
        session = web.Session({"WOPIsrc": "https://example.test", "access_token": "private", "access_token_ttl": 999})
        response = json.dumps({"Responses": [[3, {"StatusCode": 0}]]}).encode()
        state = page_state(LINES)
        written = [obj(10, 0x6000C), obj(12, 0x6000C)]
        with patch.object(session, "request", return_value=(200, response, {})) as request:
            session.write("cell|1", state, written)
        sent = json.loads(request.call_args.args[2])["srs"][0][1]["Revision"]
        self.assertEqual((sent["CellId"], sent["BaseId"]), ("cell|1", "latest|1"))
        self.assertEqual(sent["ObjectGroups"][0]["Objects"], written)


class CommandTests(unittest.TestCase):
    RUNS = (BlankLines("p:first", "p:second", 1, (0,)),)

    def remove(self, owned=True, granted=True, links=True, error=None):
        """remove_blank_lines with the inventory, permissions and service given."""
        resources = {"pages": {"id": "page", "sectionId": "s"}, "sections": {"id": "s"}}
        metadata = {"links": {"oneNoteClientUrl": {"href": "onenote:https://example.test/#T&page-id={%s}&end" % CLIENT}}}
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "cached_resource", side_effect=lambda kind, _: resources[kind]))
            stack.enter_context(patch.object(onenote, "owns_personal_notebook", return_value=owned))
            stack.enter_context(patch.object(onenote, "file_write_granted", return_value=granted))
            graph = stack.enter_context(patch.object(onenote, "graph", return_value=(200, metadata if links else {})))
            stack.enter_context(patch.object(web.Session, "for_section"))
            remove = stack.enter_context(patch.object(blank_lines, "remove", side_effect=error))
            stack.enter_context(contextlib.redirect_stdout(output))
            try:
                onenote.remove_blank_lines("page", self.RUNS)
            except SystemExit:
                pass
        return (json.loads(output.getvalue()) if output.getvalue() else {}), graph, remove

    def test_removal_uses_the_page_client_id(self):
        result, _, remove = self.remove()
        self.assertEqual(result, {})
        self.assertEqual(remove.call_args.args[1:], (CLIENT, self.RUNS))

    def test_without_revision_access_nothing_is_requested(self):
        for owned, granted in ((False, True), (True, False)):
            with self.subTest(owned=owned, granted=granted):
                result, graph, remove = self.remove(owned=owned, granted=granted)
                self.assertIn("remove them in OneNote", result["error"])
                self.assertIn("your draft was kept", result["error"])
                graph.assert_not_called()
                remove.assert_not_called()

    def test_service_failures_keep_the_draft(self):
        result, _, _ = self.remove(error=web.WebError("The blank lines changed"))
        self.assertIn("The blank lines changed", result["error"])
        self.assertIn("your draft was kept", result["error"])
        self.assertNotIn("kind", result)
        result, _, remove = self.remove(links=False)
        self.assertIn("your draft was kept", result["error"])
        remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
