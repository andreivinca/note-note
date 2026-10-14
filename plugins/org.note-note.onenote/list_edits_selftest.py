"""Native list ownership, indentation, preservation, and rich-text encoding."""
import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote  # noqa: E402
import list_edits as edits  # noqa: E402
import list_indents  # noqa: E402
from revision_objects import CONTENT_ROOT, ENTITY_GUID, PAGE_METADATA, properties  # noqa: E402
from web_session import NIL, WebError  # noqa: E402

GUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CLIENT = "12345678-1234-1234-1234-123456789abc"


def oid(number):
    return GUID + "|" + str(number)


def refs(*numbers):
    return ",".join(edits.reference(oid(number)) for number in numbers)


def gid(tag, number):
    return "%s:{%s}{%d}" % (tag, GUID, number)


def obj(number, kind, values):
    return {"ObjectId": oid(number), "ClassId": kind, "Properties": [entry for pair in values.items() for entry in pair]}


def fixture():
    objects = [obj(1, 0x60037, {edits.CONTENT: refs(2)}),
               obj(2, 0x6000B, {edits.CHILDREN: refs(10, 40)}),
               obj(3, PAGE_METADATA, {ENTITY_GUID: CLIENT}),
               obj(10, edits.OUTLINE, {edits.CHILD_LEVEL: "2", edits.CHILDREN: refs(20)}),
               obj(40, edits.OUTLINE, {edits.CHILD_LEVEL: "2", edits.CHILDREN: refs(41, 44)})]
    for number, value, style, nested in ((20, "Parent", "decimal", (23, 26)),
                                         (23, "Upper", "upper-alpha", ()),
                                         (26, "Lower", "lower-alpha", (29,)),
                                         (29, "Nested", "lower-roman", ()),
                                         (41, "Last", "upper-roman", ()),
                                         (44, "", "", ())):
        values = {edits.CHILD_LEVEL: "1", edits.CONTENT: refs(number + 2), 999: "keep element"}
        if nested:
            values[edits.CHILDREN] = refs(*nested)
        if style:
            values[edits.LIST_NODES] = refs(number + 1)
            objects.append(obj(number + 1, edits.NUMBER, {edits.LIST_FORMAT: edits.MARKERS[style]}))
        objects.append(obj(number, edits.ELEMENT, values))
        objects.append(obj(number + 2, edits.RICH_TEXT, {edits.TEXT: value, 998: "keep text"}))
    state = {"LatestRevisionId": "base|1", "ClientKnowledge": "known", "RevisionList": [
        {"Id": "base|1", "BaseId": NIL,
         "RootObjectDescriptors": [{"RootId": CONTENT_ROOT, "ObjectId": oid(1)},
                                   {"RootId": "metadata", "ObjectId": oid(3)}],
         "ObjectGroups": [{"Objects": objects}]}]}
    source = ('<html><head><title>Title</title></head><body><div id="%s"><ol id="%s">'
              '<li id="%s"><p id="%s">Parent</p><ol id="%s">'
              '<li id="%s" style="list-style-type:upper-alpha">Upper</li>'
              '<li id="%s" style="list-style-type:lower-alpha"><p id="%s">Lower</p>'
              '<ol id="%s"><li id="%s" style="list-style-type:lower-roman">Nested</li></ol>'
              '</li></ol></li></ol></div><div id="%s"><ol id="%s">'
              '<li id="%s" style="list-style-type:upper-roman">Last</li></ol><br/></div></body></html>') % (
                  gid("div", 10), gid("ol", 10), gid("li", 21), gid("p", 22), gid("ol", 20),
                  gid("li", 24), gid("li", 27), gid("p", 28), gid("ol", 26), gid("li", 30),
                  gid("div", 40), gid("ol", 40), gid("li", 42))
    return state, source


def apply(state, updates):
    result = copy.deepcopy(state)
    result["RevisionList"].append({"Id": "changed|1", "BaseId": result["LatestRevisionId"],
                                   "ObjectGroups": [{"Objects": updates}]})
    result["LatestRevisionId"] = "changed|1"
    return result


class NativeListTests(unittest.TestCase):
    def test_split_branch_and_append_deep_list_keep_items_and_text(self):
        state, source = fixture()
        page = edits.ListPage(state)
        source = list_indents.restore(source, page.objects)
        desired = ('<ol><li>Parent<ol><li style="list-style-type:upper-alpha">Upper</li></ol></li></ol>'
                   '<ol><ol><li style="list-style-type:lower-alpha">Lower</li>'
                   '<ol><li style="list-style-type:lower-roman">Nested</li></ol></ol></ol>'
                   '<ol><li style="list-style-type:upper-roman">Last</li></ol><br/><br/>'
                   + '<ol>' * 6 + '<li style="list-style-type:lower-roman">Added</li>'
                   '<li style="list-style-type:lower-roman"><br/></li>' + '</ol>' * 6)
        desired = onenote.onenote_md.markdown_to_onenote_html(onenote.onenote_md.html_to_markdown(desired)["body"])
        planned = onenote.onenote_patch.plan(source, desired)
        self.assertIsNotNone(planned.native)
        updates = edits.plan(source, planned.native, page)
        saved = edits.ListPage(apply(state, updates))
        self.assertEqual(saved.identity(), CLIENT)
        for number in (22, 25, 28, 31, 43):
            self.assertEqual(saved.objects[oid(number)], page.objects[oid(number)])
        self.assertNotIn(oid(26), saved.children(oid(20)))
        self.assertEqual(saved.children(oid(26)), [oid(29)])
        self.assertEqual(saved.children(oid(20)), [oid(23)])
        self.assertIn(oid(26), list(saved.descendants(oid(40))))
        new_items = [obj for obj in updates if obj["ClassId"] == edits.RICH_TEXT]
        self.assertTrue(any(properties(obj).get(edits.TEXT) == "Added" for obj in new_items))
        self.assertTrue(any(properties(obj).get(edits.TEXT) == "\x0b" for obj in new_items))

    def test_detached_old_containers_do_not_create_second_parents(self):
        state, source = fixture()
        old = edits.ListPage(state)
        updates = [edits.changed(old.objects[oid(20)], {edits.CHILDREN: refs(23)}),
                   edits.changed(old.objects[oid(40)], {edits.CHILDREN: refs(26, 41, 44)}),
                   obj(100, edits.GROUP, {edits.CHILD_LEVEL: "1", edits.CHILDREN: refs(26)})]
        saved = edits.ListPage(apply(state, updates))
        self.assertEqual(saved.parents[oid(26)], oid(40))
        self.assertNotIn(oid(100), saved.reachable)

    def test_duplicate_live_parent_is_rejected(self):
        state, _ = fixture()
        outline = edits.ListPage(state).objects[oid(40)]
        update = edits.changed(outline, {edits.CHILDREN: refs(26, 41, 44)})
        with self.assertRaises(WebError):
            edits.ListPage(apply(state, [update]))

    def test_leaf_text_edit_keeps_graph_path(self):
        _, source = fixture()
        planned = onenote.onenote_patch.plan(source, source.replace("Nested", "Edited"))
        self.assertIsNone(planned.native)

    def test_parent_text_has_its_own_target_and_keeps_descendants(self):
        _, source = fixture()
        desired = onenote.onenote_md.html_to_markdown(source)["body"].replace("Parent", "Edited parent")
        planned = onenote.onenote_patch.plan(source, onenote.onenote_md.markdown_to_onenote_html(desired))
        self.assertEqual([command["target"] for command in planned.commands], [gid("p", 22)])
        self.assertIn(gid("li", 30), planned.simulated)

    def test_unknown_nonblank_native_content_is_not_removed(self):
        state, source = fixture()
        page = edits.ListPage(state)
        page.objects[oid(44 + 2)] = edits.changed(page.objects[oid(46)], {edits.TEXT: "Unseen edit"})
        planned = onenote.onenote_patch.plan(source, source.replace("Last", "Updated"))
        with self.assertRaises(WebError):
            edits.plan(source, planned.simulated, page)

    def test_inline_styles_links_and_utf16_run_boundaries(self):
        state, _ = fixture()
        writer = edits.Writer(edits.ListPage(state))
        node = onenote.onenote_patch.parse('<li>😀<b>bold</b><i>i</i><u>u</u><s>s</s>'
            '<span style="color:#123456;background-color:#ffff00">color</span>'
            '<a href="https://example.com">link</a><br/></li>').children[0]
        values = writer.rich_text(node)
        self.assertTrue(values[edits.TEXT].startswith('😀boldiuscolor\ufddfHYPERLINK "https://example.com"link'))
        self.assertEqual(values[edits.RUN_INDEX].split(",")[0], "2")
        formats = [properties(obj) for obj in writer.updates.values() if obj["ClassId"] == edits.FORMAT]
        for flag in (edits.BOLD, edits.ITALIC, edits.UNDERLINE, edits.STRIKE, edits.HYPERLINK):
            self.assertTrue(any(value.get(flag) == "true" for value in formats))
        self.assertTrue(any(value.get(edits.COLOR) == str(0x563412) for value in formats))

    def test_all_marker_choices_have_distinct_native_formats(self):
        self.assertEqual(len(set(edits.MARKERS.values())), 8)
        state, _ = fixture()
        for style in edits.MARKERS:
            with self.subTest(style=style):
                writer = edits.Writer(edits.ListPage(state))
                row = edits.Row(onenote.onenote_patch.parse('<li>Item</li>').children[0], 1, style, 1)
                writer.element(row, None)
                markers = [properties(obj) for obj in writer.updates.values() if obj["ClassId"] == edits.NUMBER]
                self.assertEqual(markers[0][edits.LIST_FORMAT], edits.MARKERS[style])

    def test_tag_write_and_readback_use_equivalent_json(self):
        state, _ = fixture()
        writer = edits.Writer(edits.ListPage(state))
        node = onenote.onenote_patch.parse('<li><span data-tag="to-do:completed">Checked</span></li>').children[0]
        expected = obj(100, edits.RICH_TEXT, writer.rich_text(node))
        states = json.loads(properties(expected)[edits.TAG_STATES])
        values = json.loads(states["Values"][0])
        self.assertEqual(dict(zip(values[::2], values[1::2]))[0x10003470], "1")
        states["Values"] = [value.replace('"', r"\u0022") for value in states["Values"]]
        actual = edits.changed(expected, {edits.TAG_STATES: json.dumps(states)})
        self.assertTrue(edits.confirmed(expected, actual))

    def test_a_newer_native_text_revision_is_not_overwritten(self):
        state, source = fixture()
        page = edits.ListPage(state)
        page.objects[oid(31)] = edits.changed(page.objects[oid(31)], {edits.TEXT: "Newer remote text"})
        planned = onenote.onenote_patch.plan(source, source.replace("Nested", "Local text"))
        with self.assertRaisesRegex(WebError, "changed in OneNote"):
            edits.plan(source, planned.simulated, page)

    def test_deep_indentation_uses_multiple_native_edges(self):
        state, _ = fixture()
        writer = edits.Writer(edits.ListPage(state))
        row = edits.Row(onenote.onenote_patch.parse('<li>Deep</li>').children[0], 63, "lower-roman", 1, group=1)
        writer.element(row, None)
        writer.outline(oid(40), [row])
        edits.validate(writer, [(oid(40), [row])])
        groups = [properties(obj)[edits.CHILD_LEVEL] for obj in writer.updates.values() if obj["ClassId"] == edits.GROUP]
        self.assertEqual(groups, ["31", "31", "1"])


class ReadTests(unittest.TestCase):
    def test_tags_on_native_items_match_tags_on_graph_spans(self):
        for tag in ("to-do", "to-do:completed", "important"):
            with self.subTest(tag=tag):
                native = '<ol><li style="list-style-type:lower-roman" data-tag="%s">Item</li></ol>' % tag
                graph = '<ol><li style="list-style-type:lower-roman"><span data-tag="%s">Item</span></li></ol>' % tag
                self.assertEqual(onenote.onenote_md.html_to_markdown(native)["body"],
                                 onenote.onenote_md.html_to_markdown(graph)["body"])
                body = onenote.onenote_md.html_to_markdown(graph)["body"]
                written = onenote.onenote_md.markdown_to_onenote_html(body)
                self.assertEqual(onenote.onenote_md.html_to_markdown(written)["body"], body)

    def test_existing_native_outline_keeps_its_original_appearance(self):
        state, source = fixture()
        objects = edits.ListPage(state).objects
        self.assertEqual(onenote.onenote_md.html_to_markdown(source)["body"],
                         onenote.onenote_md.html_to_markdown(list_indents.restore(source, objects))["body"])

    def source(self, level):
        objects = {
            oid(1): obj(1, edits.OUTLINE, {edits.CHILD_LEVEL: "1", edits.CHILDREN: refs(2)}),
            oid(2): obj(2, edits.GROUP, {edits.CHILD_LEVEL: str(level), edits.CHILDREN: refs(3, 6)}),
            oid(3): obj(3, edits.ELEMENT, {edits.LIST_NODES: refs(4)}),
            oid(6): obj(6, edits.ELEMENT, {edits.LIST_NODES: refs(7)})}
        source = ('<body><div id="%s"><ol id="%s"><li id="%s" style="list-style-type:lower-roman">Item</li>'
                  '<li id="%s" style="list-style-type:lower-roman"><br/></li></ol></div></body>') % (
                      gid("div", 1), gid("ol", 2), gid("li", 4), gid("li", 7))
        return source, objects

    def test_native_levels_and_empty_items_survive_readback(self):
        for level in (1, 2, 6, 31):
            with self.subTest(level=level):
                source, objects = self.source(level)
                restored = list_indents.restore(source, objects)
                body = onenote.onenote_md.html_to_markdown(restored)["body"]
                indent = ' data-list-indent="%d"' % level if level > 1 else ""
                self.assertEqual(body, '<ol style="list-style-type:lower-roman"%s>'
                                 '<li><p>Item</p></li><li></li></ol>' % indent)
                emitted = onenote.onenote_md.markdown_to_onenote_html(body)
                self.assertIn('<li style="list-style-type:lower-roman"><br/></li>', emitted)

    def test_missing_or_invalid_native_level_is_not_guessed(self):
        source, objects = self.source(6)
        with self.assertRaises(WebError):
            list_indents.restore(source, {})
        for value in ("0", "32", "bad"):
            with self.subTest(value=value):
                objects[oid(2)] = edits.changed(objects[oid(2)], {edits.CHILD_LEVEL: value})
                with self.assertRaises(WebError):
                    list_indents.restore(source, objects)

    def test_restored_depth_keeps_leaf_edit_targets(self):
        source, objects = self.source(6)
        restored = list_indents.restore(source, objects)
        body = onenote.onenote_md.html_to_markdown(restored)["body"].replace("Item", "Edited")
        planned = onenote.onenote_patch.plan(restored, onenote.onenote_md.markdown_to_onenote_html(body))
        self.assertEqual([command["target"] for command in planned.commands], [gid("li", 4)])

    def test_tab_on_an_already_deep_list_has_native_targets(self):
        source, objects = self.source(6)
        restored = list_indents.restore(source, objects)
        body = onenote.onenote_md.html_to_markdown(restored)["body"].replace('data-list-indent="6"', 'data-list-indent="7"')
        planned = onenote.onenote_patch.plan(restored, onenote.onenote_md.markdown_to_onenote_html(body))
        self.assertIsNotNone(planned.native)


class WriteTests(unittest.TestCase):
    def test_provider_writes_one_conditional_revision_and_confirms_objects(self):
        state, source = fixture()
        current = list_indents.restore(source, edits.ListPage(state).objects)
        desired = current.replace("Nested", "Changed")
        updates = []
        session = Mock()
        session.read.side_effect = lambda cell: apply(state, updates) if updates else state
        session.write.side_effect = lambda cell, base, objects: updates.extend(objects)
        section = Mock()
        section.cell.return_value = "page-cell"
        with patch.object(onenote, "require_revision_access"), \
                patch.object(onenote, "cached_resource", return_value={"sectionId": "section", "clientId": CLIENT}), \
                patch.object(onenote.web_session.Session, "for_section", return_value=session), \
                patch.object(onenote.revision_objects, "Section", return_value=section), \
                patch.object(onenote, "graph_raw", side_effect=[(200, source), (200, source.replace("Nested", "Changed"))]):
            saved = onenote.write_lists("page", current, desired, "base|1")
        self.assertEqual(session.write.call_count, 1)
        self.assertEqual(session.write.call_args.args[:2], ("page-cell", state))
        self.assertEqual(onenote.onenote_md.html_to_markdown(saved)["body"],
                         onenote.onenote_md.html_to_markdown(desired)["body"])

    def test_a_changed_page_revision_is_never_written(self):
        state, source = fixture()
        session = Mock()
        session.read.return_value = state
        section = Mock()
        section.cell.return_value = "page-cell"
        with patch.object(onenote, "require_revision_access"), \
                patch.object(onenote, "cached_resource", return_value={"sectionId": "section", "clientId": CLIENT}), \
                patch.object(onenote.web_session.Session, "for_section", return_value=session), \
                patch.object(onenote.revision_objects, "Section", return_value=section), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            onenote.write_lists("page", source, source, "older|1")
        session.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
