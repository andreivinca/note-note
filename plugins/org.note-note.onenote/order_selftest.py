"""Synthetic TOC/OneDrive tests: no account, network or real notebook data."""
import builtins
import contextlib
import io
import json
import os
import struct
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch

import onenote  # noqa: F401 -- establishes the provider's shared library paths
import section_order as order
import toc


def compact(value):
    if value == 0:
        return b"\0"
    for width in range(1, 8):
        if value < 1 << (7 * width):
            return ((value << width) | (1 << (width - 1))).to_bytes(width, "little")
    return b"\x80" + value.to_bytes(8, "little")


def guid(value):
    return (value.to_bytes(16, "little"), 1)


def exguid(value):
    if value == toc.NIL:
        return b"\0"
    return b"\x80" + value[1].to_bytes(4, "little") + value[0]


def node(tag, data=b"", children=None):
    compound = 4 if children is not None else 0
    if tag < 64 and len(data) < 128:
        start = struct.pack("<H", (len(data) << 9) | (tag << 3) | compound)
    else:
        start = struct.pack("<I", (len(data) << 17) | (tag << 3) | compound | 2)
    end = b""
    if children is not None:
        end = bytes([(tag << 2) | 1]) if tag < 64 else struct.pack("<H", (tag << 2) | 3)
    return start + data + b"".join(children or []) + end


def prop_set(values, refs):
    ids, payloads = [], []
    for key, value in values.items():
        ids.append(struct.pack("<I", key))
        if key == toc.CHILDREN:
            payloads.append(struct.pack("<I", len(value)))
        elif key == toc.ORDER:
            payloads.append(struct.pack("<I", value))
        else:
            payloads.append(struct.pack("<I", len(value)) + value)
    return (struct.pack("<I", 0x80000000 | len(refs)) + bytes(4 * len(refs))
            + struct.pack("<H", len(values)) + b"".join(ids) + b"".join(payloads))


def fixture(names=("Food.one", "Welcome.one", "Health.one"), orders=(3, 1, 5),
            base=False, revision_cycle=False, object_cycle=False):
    """Build the actual packaged wire format, with optional revision inheritance."""
    index, manifest, cell, revision, group, root = [guid(i) for i in range(1, 7)]
    older, old_group = guid(7), guid(8)
    cell_id = guid(9), toc.NIL
    objects = [guid(20 + i) for i in range(len(names))]

    def element(key, kind, children):
        return node(1, exguid(key) + b"\0" + compact(kind), children)

    def object_group(key, values):
        declarations, data = [], []
        for object_id, properties, refs in values:
            for partition, payload, references in [(1, prop_set(properties, refs), refs), (4, struct.pack("<I", 0x20001), [])]:
                declarations.append(node(0x18, exguid(object_id) + compact(partition)
                                         + compact(len(payload)) + compact(len(references)) + b"\0"))
                data.append(node(0x16, compact(len(references)) + b"".join(exguid(ref) for ref in references)
                                 + b"\0" + compact(len(payload)) + payload))
        return element(key, 5, [node(0x1D, children=declarations), node(0x1E, children=data)])

    leaves = [(key, {toc.FILENAME: name.encode("utf-16-le"), toc.ORDER: position,
                     toc.IDENTITY: key[0]}, []) for key, name, position in zip(objects, names, orders)]
    root_refs = [root] if object_cycle else objects
    values = [(root, {toc.CHILDREN: root_refs}, root_refs)]
    index_children = [node(0x11, exguid(manifest) + b"\0"),
                      node(0x0E, exguid(cell_id[0]) + exguid(cell_id[1]) + exguid(cell) + b"\0")]
    parts = [element(index, 1, index_children),
             element(manifest, 2, [node(7, exguid(toc.DATA_ROOT) + exguid(cell_id[0]) + exguid(cell_id[1]))]),
             element(cell, 3, [node(0x0B, exguid(revision))])]
    predecessor = revision if revision_cycle else older if base else toc.NIL
    parts.append(element(revision, 4, [node(0x1A, exguid(revision) + exguid(predecessor)),
                                      node(0x0A, exguid(toc.CONTENT_ROOT) + exguid(root)),
                                      node(0x19, exguid(group))]))
    if base:
        # The current first leaf overrides the older revision, while all
        # other leaves are inherited from it.
        parts.append(object_group(group, values + leaves[:1]))
        old_values = [(key, dict(props), refs) for key, props, refs in leaves]
        old_values[0][1][toc.ORDER] = 99
        parts.append(object_group(old_group, old_values))
        parts.append(element(older, 4, [node(0x1A, exguid(older) + exguid(toc.NIL)),
                                       node(0x19, exguid(old_group))]))
    else:
        parts.append(object_group(group, values + leaves))
    return bytes(48) + toc.PACKAGING_FORMAT + bytes(4) + node(
        0x7A, exguid(index) + toc.TOC_SCHEMA, [node(0x15, b"\0", parts)])


def item(number, guid=False):
    """A personal OneDrive item ID: numbered, or "s" and a GUID, the format
    OneDrive gives the items it has created since it changed formats."""
    return "0123456789ABCDEF!" + ("s%032x" % number if guid else str(number))


BOOK = "0-" + item(10)
TOC = item(12)


def sections(guid=False):
    return [{"id": "0-" + item(number, guid), "name": name,
             "notebookId": "0-" + item(10, guid), "notebook": "Test", "modified": "stamp"}
            for number, name in [(30, "Food"), (31, "Health"), (32, "Welcome"), (33, "New")]]


WALK = ["Welcome", "Food", "Health", "New"]   # the fixture's TOC order, Deleted.one left out


def ranked(names, guid=False):
    """The ranks the walk gives the fixture's sections listed in `names`
    order, by id: none for a section not named."""
    by_name = {section["name"]: section["id"] for section in sections(guid)}
    return {by_name[name]: index for index, name in enumerate(names)}


class Remote:
    def __init__(self, etag="v1", guid=False):
        self.etag, self.downloads, self.calls = etag, 0, []
        self.book = item(10, guid)
        self.children = [{"id": s["id"][2:], "name": s["name"] + ".one", "file": {}} for s in sections(guid)]
        self.children.append({"id": TOC, "name": "Open Notebook.onetoc2", "file": {}, "eTag": etag})

    def get(self, path):
        self.calls.append(path)
        if "/children" in path:
            return {"value": self.children}
        if path == order.item_path(TOC):
            return {"eTag": self.etag}
        return {"id": self.book, "name": "Test", "package": {"type": "oneNote"}}

    def download(self, item):
        self.downloads += 1
        return fixture(names=("Food.one", "Welcome.one", "Health.one", "Deleted.one", "New.one"), orders=(3, 1, 5, 0, 8))


GROUP = "0-" + item(40)


def grouped():
    """A notebook holding Food, the group Group with Child inside it, and
    Welcome, as Graph lists them: the sections, then the groups."""
    records = [{"id": "0-" + item(number), "name": name, "notebookId": BOOK, "notebook": "Test", "modified": "stamp"}
               for number, name in [(30, "Food"), (32, "Welcome"), (41, "Child")]]
    records[2]["parentGroupId"] = GROUP
    return records, [{"id": GROUP, "name": "Group", "notebookId": BOOK, "notebook": "Test"}]


class GroupedRemote(Remote):
    """The OneDrive package grouped() lists: Food, Group, then Welcome, by
    the notebook's TOC, and Child in the group's own folder."""

    def __init__(self):
        super().__init__()
        self.children = [{"id": item(30), "name": "Food.one", "file": {}},
                         {"id": item(40), "name": "Group", "folder": {}},
                         {"id": item(32), "name": "Welcome.one", "file": {}},
                         {"id": TOC, "name": "Open Notebook.onetoc2", "file": {}}]

    def get(self, path):
        if path.startswith(order.item_path(item(40)) + "/children"):
            self.calls.append(path)
            return {"value": [{"id": item(41), "name": "Child.one", "file": {}},
                              {"id": item(42), "name": "Open Notebook.onetoc2", "file": {}}]}
        return super().get(path)


def grouped_entries(reader, item):
    if item["id"] == TOC:
        return [{"name": "Food.one", "order": 1}, {"name": "Group", "order": 2}, {"name": "Welcome.one", "order": 3}]
    return [{"name": "Child.one", "order": 1}]


class TocTests(unittest.TestCase):
    def test_current_and_inherited_revisions(self):
        for base in (False, True):
            entries = toc.section_entries(fixture(base=base))
            self.assertEqual([e["name"] for e in entries], ["Welcome.one", "Food.one", "Health.one"])
            self.assertEqual([e["order"] for e in entries], [1, 3, 5])

    def test_desktop_envelope(self):
        header = bytearray(1024)
        header[48:64] = toc.DESKTOP_FORMAT
        struct.pack_into("<QI", header, 160, 1024, 0)
        self.assertEqual(toc.section_entries(bytes(header) + fixture()), toc.section_entries(fixture()))
        struct.pack_into("<Q", header, 160, 2**63)
        with self.assertRaises(toc.InvalidToc):
            toc.section_entries(bytes(header) + fixture())

    def test_last_filename_reference_wins(self):
        entries = toc.section_entries(fixture(names=("Same.one", "Same.one"), orders=(1, 9)))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["order"], 9)

    def test_cycles_and_limits(self):
        for data in (fixture(revision_cycle=True), fixture(object_cycle=True), bytes(toc.MAX_BYTES + 1),
                     fixture() + b"unexpected", fixture().replace(toc.TOC_SCHEMA, bytes(16))):
            with self.assertRaises(toc.InvalidToc):
                toc.section_entries(data)

    def test_all_truncations_rejected(self):
        data = fixture()
        for size in range(len(data)):
            with self.assertRaises(toc.InvalidToc, msg=str(size)):
                toc.section_entries(data[:size])

    def test_compact_encodings(self):
        for value in [0, 1, 127, 128, 16383, 16384, 2**32, 2**63, 2**64 - 1]:
            reader = toc.Reader(compact(value))
            self.assertEqual(reader.compact(), value)
            reader.finish()


class OrderingTests(unittest.TestCase):
    def test_live_join_and_versioned_cache(self):
        remote = Remote()
        cached, warnings, ranks = order.arrange(sections(), remote=remote)
        self.assertEqual(ranks, ranked(WALK))  # Deleted.one stays deleted.
        self.assertFalse(warnings)
        self.assertEqual(remote.downloads, 1)
        self.assertNotIn("downloadUrl", json.dumps(cached))
        remote = Remote()
        _, _, again = order.arrange(sections(), cached, remote)
        self.assertEqual(again, ranks)
        self.assertEqual(remote.downloads, 0)
        remote = Remote("v2")
        order.arrange(sections(), cached, remote)
        self.assertEqual(remote.downloads, 1)

    def test_unavailable_discards_last_remote_order_and_warns(self):
        cached, _, _ = order.arrange(sections(), remote=Remote())
        remote = Remote()
        def offline(path):
            raise order.OrderUnavailable("offline")
        remote.get = offline
        saved, warnings, ranks = order.arrange(sections(), cached, remote)
        self.assertEqual(ranks, {})
        self.assertTrue(warnings)
        self.assertFalse(saved["files"])

    def test_guid_item_ids_join_like_numbered_ones(self):
        _, warnings, ranks = order.arrange(sections(guid=True), remote=Remote(guid=True))
        self.assertEqual(ranks, ranked(WALK, guid=True))
        self.assertFalse(warnings)

    def test_unsupported_ids_never_probe_drive(self):
        for notebook in ("1-work-notebook", "0-0123456789ABCDEF!s0123", "0-0123456789ABCDEF!x" + "0" * 32):
            entries, remote = sections(), Remote()
            entries[0] = dict(entries[0], notebookId=notebook, notebook="Work")
            entries[1] = dict(entries[1], notebookId=notebook, notebook="Work")
            with self.subTest(notebook=notebook):
                _, warnings, ranks = order.arrange(entries, remote=remote)
                self.assertNotIn(entries[0]["id"], ranks)
                self.assertTrue(warnings)
                self.assertFalse(any(call.startswith(order.item_path(notebook[2:])) for call in remote.calls))

    def test_removed_notebooks_prune_metadata(self):
        cached, _, _ = order.arrange(sections(), remote=Remote())
        saved, _, _ = order.arrange([], cached, Remote())
        self.assertFalse(saved["files"])
        self.assertNotIn("notebooks", saved)

    def test_paginated_listing_cycle(self):
        remote = Remote()
        remote.get = lambda path: {"value": [], "@odata.nextLink": path}
        with self.assertRaisesRegex(order.OrderUnavailable, "cyclic"):
            order.Ordering(remote, {}).children(BOOK[2:])

    def test_newest_of_several_tocs_is_used(self):
        for newest in (TOC, "extra"):
            remote = Remote()
            remote.children[-1]["lastModifiedDateTime"] = "2026-09-08T08:03:37Z"
            stamp = "2025-06-15T16:35:10Z" if newest == TOC else "2026-09-08T08:03:37.5Z"
            remote.children.append({"id": "extra", "name": ".onetoc2", "file": {}, "lastModifiedDateTime": stamp})
            saved, warnings, ranks = order.arrange(sections(), remote=remote)
            self.assertEqual(ranks, ranked(WALK))
            self.assertFalse(warnings)
            self.assertEqual(list(saved["files"]), [newest])

    def test_tocs_without_a_newest_are_not_guessed(self):
        for stamps, reason in [((None, None), "invalid section metadata timestamp"),
                               (("2026-09-08T08:03:37Z", "2026-09-08T08:03:37Z"),
                                "notebook folder has no unique .onetoc2 metadata"),
                               (("2026-09-08T08:03:37Z", "yesterday"), "invalid section metadata timestamp")]:
            remote = Remote()
            remote.children[-1]["lastModifiedDateTime"] = stamps[0]
            remote.children.append({"id": "extra", "name": ".onetoc2", "file": {}, "lastModifiedDateTime": stamps[1]})
            _, warnings, ranks = order.arrange(sections(), remote=remote)
            self.assertEqual(ranks, {})
            self.assertEqual(warnings, ["Test: custom order unavailable (%s); sections sorted alphabetically" % reason])
            self.assertEqual(remote.downloads, 0)

    def test_nested_group_position_and_recycle_bin(self):
        remote = Remote()
        remote.children = [{"id": "group", "name": "Group", "folder": {}},
                           {"id": "bin", "name": "OneNote_RecycleBin", "folder": {}},
                           {"id": TOC, "name": "Open Notebook.onetoc2", "file": {}},
                           {"id": "food", "name": "Food.one", "file": {}}]
        original_get = remote.get
        def get(path):
            if path.startswith(order.item_path("group") + "/children"):
                return {"value": [{"id": "child", "name": "Child.one", "file": {}},
                                  {"id": "group-toc", "name": "Open Notebook.onetoc2", "file": {}}]}
            return original_get(path)
        remote.get = get
        reader = order.Ordering(remote, {})
        def entries(item):
            if item["id"] == TOC:
                return [{"name": "Food.one", "order": 1}, {"name": "Group", "order": 2}]
            return [{"name": "Child.one", "order": 1}]
        reader.entries = entries
        reader.folder(BOOK[2:])
        self.assertEqual(reader.places, {"0-food": ("", 0), "0-group": ("", 1), "0-child": ("0-group", 0)})
        self.assertEqual(reader.section_names, {"0-food": "Food", "0-child": "Child"})
        self.assertNotIn("bin", reader.visited)

    def test_groups_rank_among_their_holders_sections(self):
        records, groups = grouped()
        with patch.object(order.Ordering, "entries", grouped_entries):
            _, warnings, ranks = order.arrange(records, remote=GroupedRemote(), groups=groups)
        self.assertFalse(warnings)
        self.assertEqual(ranks, {records[0]["id"]: 0, GROUP: 1, records[1]["id"]: 2, records[2]["id"]: 0})

    def test_a_group_the_folders_do_not_confirm_has_no_rank(self):
        cases = {"renamed": lambda records, groups: groups[0].update(name="Other"),
                 "in another holder": lambda records, groups: groups[0].update(parentGroupId=records[0]["id"]),
                 "unlisted": lambda records, groups: groups.clear()}
        for case, change in cases.items():
            records, groups = grouped()
            change(records, groups)
            with self.subTest(case=case), patch.object(order.Ordering, "entries", grouped_entries):
                _, warnings, ranks = order.arrange(records, remote=GroupedRemote(), groups=groups)
                self.assertNotIn(GROUP, ranks)
                self.assertEqual(ranks[records[0]["id"]], 0)
                self.assertEqual(ranks[records[1]["id"]], 2)
                if case == "unlisted":
                    # A section whose group is not listed sits with the
                    # notebook's own: its rank in the group means nothing there.
                    self.assertNotIn(records[2]["id"], ranks)
                    self.assertFalse(warnings)
                else:
                    self.assertTrue(any("section group order unavailable" in warning for warning in warnings))

    def test_an_empty_group_needs_no_table_of_contents(self):
        records, groups = grouped()
        del records[2]
        remote = GroupedRemote()
        original_get = remote.get
        remote.get = lambda path: ({"value": []} if path.startswith(order.item_path(item(40)) + "/children")
                                   else original_get(path))
        with patch.object(order.Ordering, "entries", grouped_entries):
            _, warnings, ranks = order.arrange(records, remote=remote, groups=groups)
        self.assertFalse(warnings)
        self.assertEqual(ranks, {records[0]["id"]: 0, GROUP: 1, records[1]["id"]: 2})

    def test_a_section_graph_puts_elsewhere_has_no_rank(self):
        records, groups = grouped()
        del records[2]["parentGroupId"]
        with patch.object(order.Ordering, "entries", grouped_entries):
            _, warnings, ranks = order.arrange(records, remote=GroupedRemote(), groups=groups)
        self.assertNotIn(records[2]["id"], ranks)
        self.assertEqual(ranks[GROUP], 1)
        self.assertFalse(warnings)

    def test_listing_checkpoint_preserves_section_and_page_order(self):
        source = list(reversed(sections()))
        pages = [{"id": "second", "sectionId": source[0]["id"]},
                 {"id": "first", "sectionId": source[0]["id"]}]
        listing = onenote.Listing({"pages": pages}, source)
        with patch.object(onenote.msgraph, "save_private") as save:
            listing.save(False)
        data = save.call_args.args[1]
        self.assertEqual(data["sections"], source)
        self.assertEqual(data["pages"], pages)

    def test_unexpected_failures_and_throttles_leave_the_book_unranked(self):
        cached, _, _ = order.arrange(sections(), remote=Remote())
        for error in [RuntimeError("secret-url"), TypeError("secret-url"), SystemExit(1),
                      order.ratelimit.Throttled(60), toc.InvalidToc("unsupported"), TimeoutError()]:
            remote = Remote()
            with patch.object(remote, "get", side_effect=error):
                saved, warnings, ranks = order.arrange(list(reversed(sections())), cached, remote)
            self.assertEqual(ranks, {})
            self.assertFalse(saved["files"])
            self.assertEqual(warnings, ["Test: custom order unavailable; sections sorted alphabetically"])
            self.assertNotIn("secret-url", str(warnings))

    def test_partial_or_changed_id_mapping_is_rejected(self):
        for count in (1, 4):
            remote = Remote()
            for item in remote.children[:count]:
                item["id"] = "changed-" + item["id"]
            saved, warnings, ranks = order.arrange(sections(), remote=remote)
            self.assertEqual(ranks, {})
            self.assertFalse(saved["files"])
            self.assertTrue(warnings)

    def test_missing_live_position_is_rejected(self):
        remote = Remote()
        remote.download = lambda item: fixture(
            names=("Food.one", "Welcome.one", "Health.one", "New.one"), orders=(3, 1, 5))
        saved, warnings, ranks = order.arrange(sections(), remote=remote)
        self.assertEqual(ranks, {})
        self.assertTrue(warnings)
        self.assertFalse(saved["files"])

    def test_equal_and_skipped_numbers_keep_toc_order(self):
        remote = Remote()
        remote.download = lambda item: fixture(
            names=("Food.one", "Welcome.one", "Health.one", "New.one"), orders=(4, 1, 4, 9))
        _, warnings, ranks = order.arrange(sections(), remote=remote)
        self.assertEqual(ranks, ranked(WALK))
        self.assertFalse(warnings)

    def test_invalid_children_and_cache_do_not_abort(self):
        for invalid in [None, {}, {"name": "x.one"}, {"id": "x", "name": []}]:
            remote = Remote()
            remote.children.append(invalid)
            _, warnings, ranks = order.arrange(sections(), remote=remote)
            self.assertEqual(ranks, {})
            self.assertTrue(warnings)
        for files in [None, [], {TOC: None}, {TOC: {"etag": "v1", "entries": [None]}}]:
            _, warnings, ranks = order.arrange(sections(), {"version": order.CACHE_VERSION, "files": files}, Remote())
            self.assertEqual(ranks, {})
            self.assertTrue(warnings)


    def test_one_failed_notebook_does_not_change_a_healthy_one(self):
        broken = [dict(section, id="other-" + section["id"], notebookId="unsupported", notebook="Broken")
                  for section in reversed(sections())]
        mixed = [section for pair in zip(broken, sections()) for section in pair]
        saved, warnings, ranks = order.arrange(mixed, remote=Remote())
        self.assertEqual(ranks, ranked(WALK))
        self.assertEqual(len(warnings), 1)
        self.assertIn(TOC, saved["files"])


class BoundaryTests(unittest.TestCase):
    def test_missing_scope_never_invokes_workaround(self):
        with patch.object(onenote, "files_read_granted", return_value=False), patch.object(order, "Remote") as remote:
            saved, warnings, ranks = onenote.ordered_sections(list(reversed(sections())), {}, "token")
        remote.assert_not_called()
        self.assertEqual((saved, ranks), ({}, {}))
        self.assertTrue(warnings)

    def test_broken_optional_import_and_constructor_are_contained(self):
        original_import = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "section_order":
                raise ImportError("secret-url")
            return original_import(name, *args, **kwargs)
        with patch.object(onenote, "files_read_granted", return_value=True):
            with patch.object(builtins, "__import__", side_effect=missing):
                _, warnings, ranks = onenote.ordered_sections(sections(), {}, "token")
            self.assertEqual(ranks, {})
            self.assertNotIn("secret-url", str(warnings))
            with patch.object(order, "Remote", side_effect=RuntimeError("secret-url")):
                _, warnings, ranks = onenote.ordered_sections(sections(), {}, "token")
            self.assertEqual(ranks, {})
            self.assertTrue(warnings)

    def test_optional_code_cannot_rank_what_graph_did_not_list(self):
        for ranks in [{"stranger": 0}, {sections()[0]["id"]: -1}, {sections()[0]["id"]: "1"}, []]:
            with patch.object(onenote, "files_read_granted", return_value=True), patch.object(order, "Remote"):
                with patch.object(order, "arrange", return_value=({}, [], ranks)):
                    _, warnings, kept = onenote.ordered_sections(sections(), {}, "token")
            self.assertTrue(warnings)
            self.assertEqual(kept, {})

    def files(self, listing=None):
        """The cache files on disk, as the commands read and write them."""
        files = {}
        if listing is not None:
            files[onenote.ONENOTE_CACHE] = listing
        return files

    # The listing and the order are the account's caches, read and written
    # through msgraph (load_for_session / save_for_session): `files` stands
    # in for the disk there.
    def on_disk(self, stack, files):
        stack.enter_context(patch.object(onenote, "listing_lock", return_value=contextlib.nullcontext()))
        stack.enter_context(patch.object(onenote.msgraph, "load_json", side_effect=lambda path, default=None, cap=None: files.get(path, default)))
        stack.enter_context(patch.object(onenote.msgraph, "save_private", side_effect=files.__setitem__))

    def test_listing_answers_pages_before_any_order_pass(self):
        source = sections()
        graph_sections = [{"id": section["id"], "displayName": section["name"],
                           "lastModifiedDateTime": "stamp", "parentNotebook": {"id": BOOK, "displayName": "Test"}}
                          for section in source]
        printed = io.StringIO()
        files = self.files()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "files_read_granted", return_value=True))
            self.on_disk(stack, files)
            stack.enter_context(patch.object(onenote, "access_token", return_value="token"))
            stack.enter_context(patch.object(onenote, "graph", return_value=(200, {"value": [
                {"id": BOOK, "displayName": "Test", "sections": graph_sections, "sectionGroups": []}]})))
            http = stack.enter_context(patch.object(onenote, "http", return_value=(200, {"value": [
                {"id": "z", "title": "Z first"}, {"id": "a", "title": "A second"}]})))
            arrange = stack.enter_context(patch.object(order, "arrange", side_effect=RuntimeError("secret-url")))
            stack.enter_context(contextlib.redirect_stdout(printed))
            onenote.cmd_onenote_list(False)
        reply = json.loads(printed.getvalue())
        arrange.assert_not_called()
        self.assertEqual(reply["sections"], source)
        self.assertEqual(reply["sectionRanks"], {})
        self.assertTrue(reply["sectionOrderPending"])
        self.assertEqual(http.call_count, len(source))
        self.assertTrue(all("$orderby=order" in call.args[1] for call in http.call_args_list))
        self.assertEqual([page["id"] for page in reply["pages"]], ["z", "a"] * len(source))
        self.assertEqual(files[onenote.ONENOTE_CACHE]["sections"], source)
        self.assertNotIn("sectionOrders", files[onenote.ONENOTE_CACHE])

    def test_order_pass_writes_its_file_and_the_listing_follows_it(self):
        expected = ranked(WALK)
        files = self.files({"sections": list(reversed(sections())), "pages": [], "fetched": time.time()})
        printed = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "files_read_granted", return_value=True))
            self.on_disk(stack, files)
            stack.enter_context(patch.object(onenote, "access_token", return_value="token"))
            stack.enter_context(patch.object(order, "Remote", side_effect=lambda token: Remote()))
            stack.enter_context(contextlib.redirect_stdout(printed))
            onenote.cmd_section_order()
            passed = json.loads(printed.getvalue())
            printed.seek(0)
            printed.truncate()
            onenote.cmd_onenote_list(True)
            listed = json.loads(printed.getvalue())
        self.assertEqual(passed["sectionRanks"], expected)
        self.assertEqual(passed["sectionOrderWarnings"], [])
        self.assertNotIn("sections", passed)
        order_file = files[onenote.ONENOTE_ORDER]
        self.assertEqual(order_file["version"], onenote.SECTION_ORDER_VERSION)
        self.assertTrue(order_file["scope"])
        self.assertTrue(order_file["metadata"]["files"])
        # The ranks are the order, and the one form it is kept in.
        self.assertEqual(order_file["ranks"], expected)
        self.assertNotIn("positions", order_file)
        self.assertEqual(listed["sections"], list(reversed(sections())))
        self.assertEqual(listed["sectionRanks"], expected)
        self.assertFalse(listed["sectionOrderPending"])

    def test_order_pass_failure_leaves_no_rank_and_is_contained(self):
        files = self.files({"sections": list(reversed(sections())), "pages": []})
        printed = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(onenote, "files_read_granted", return_value=True))
            self.on_disk(stack, files)
            stack.enter_context(patch.object(onenote, "access_token", return_value="token"))
            stack.enter_context(patch.object(order, "arrange", side_effect=RuntimeError("secret-url")))
            stack.enter_context(contextlib.redirect_stdout(printed))
            onenote.cmd_section_order()
        reply = json.loads(printed.getvalue())
        self.assertEqual(reply["sectionRanks"], {})
        self.assertTrue(reply["sectionOrderWarnings"])
        self.assertNotIn("secret-url", printed.getvalue())
        self.assertEqual(files[onenote.ONENOTE_ORDER]["metadata"], {})

    def test_cached_order_loses_permission_or_old_policy(self):
        established = list(reversed(sections()))
        for scope, version in [(False, onenote.SECTION_ORDER_VERSION), (True, 1)]:
            files = {onenote.ONENOTE_CACHE: {"sections": established, "pages": [], "fetched": time.time()},
                     onenote.ONENOTE_ORDER: {"version": version, "scope": True, "ranks": ranked(WALK)}}
            printed = io.StringIO()
            with contextlib.ExitStack() as stack:
                self.on_disk(stack, files)
                stack.enter_context(patch.object(onenote, "files_read_granted", return_value=scope))
                stack.enter_context(contextlib.redirect_stdout(printed))
                onenote.cmd_onenote_list(True)
            reply = json.loads(printed.getvalue())
            self.assertEqual(reply["sections"], established)
            self.assertEqual(reply["sectionRanks"], {})
            self.assertTrue(reply["sectionOrderPending"])

    def test_print_then_exit_cannot_corrupt_provider_protocol(self):
        def broken(*args):
            onenote.fail("secret-url")
        printed = io.StringIO()
        with patch.object(onenote, "files_read_granted", return_value=True), patch.object(order, "Remote"):
            with patch.object(order, "arrange", side_effect=broken), contextlib.redirect_stdout(printed):
                _, warnings, ranks = onenote.ordered_sections(sections(), {}, "token")
        self.assertEqual(ranks, {})
        self.assertTrue(warnings)
        self.assertEqual(printed.getvalue(), "")


class TransportTests(unittest.TestCase):
    def setUp(self):
        # A request takes a slot from the section-order limiter before it
        # opens anything (ratelimit.slot), and the limiter keeps its stamps
        # on disk: this test's go to a directory of its own, never the user's.
        rate_dir = tempfile.TemporaryDirectory(prefix="note-note-rate-")
        self.addCleanup(rate_dir.cleanup)
        environment = patch.dict(os.environ, {"NOTE_NOTE_RATE_DIR": rate_dir.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_download_origin_allowlist(self):
        for host in order.DOWNLOAD_HOSTS:
            url = "https://test" + host + "/signed?secret=redacted"
            self.assertEqual(order.download_url(url), url)
        for url in ["http://x.files.1drv.com/x", "https://x.files.1drv.com.evil.test/x",
                    "https://files.1drv.com@evil.test/x", "file:///etc/passwd",
                    "https://user@x.sharepoint.com/x", "https://x.sharepoint.com:444/x",
                    "https://x.sharepoint.com/x#fragment", "https://[invalid"]:
            with self.assertRaises(order.OrderUnavailable):
                order.download_url(url)

    def test_untrusted_pagination_has_no_authorization(self):
        remote = order.Remote("snapshot")
        with patch.object(remote, "request") as request:
            for path in ["https://evil.test/v1.0/me/drive/items/x", "https://graph.microsoft.com.evil.test/v1.0/me/drive/items/x"]:
                with self.assertRaises(order.OrderUnavailable):
                    remote.get(path)
            request.assert_not_called()

    def test_signed_download_omits_bearer_and_refuses_redirect(self):
        remote = order.Remote("snapshot")
        class Response(io.BytesIO):
            status = 200
        with patch.object(remote.opener, "open", return_value=Response(b"toc")) as opened:
            remote.download({"size": 3, "@microsoft.graph.downloadUrl": "https://test.files.1drv.com/x"})
            request = opened.call_args.args[0]
            self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(order.provider_io.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))
        with patch.object(remote.opener, "open", side_effect=urllib.error.HTTPError("secret-url", 302, "", {}, None)):
            with self.assertRaisesRegex(order.OrderUnavailable, "HTTP 302"):
                remote.download({"size": 3, "@microsoft.graph.downloadUrl": "https://test.files.1drv.com/x"})

    def test_size_and_wall_clock_limits(self):
        class Response(io.BytesIO):
            status = 200
        remote = order.Remote("snapshot")
        with patch.object(remote.opener, "open", return_value=Response(bytes(order.MAX_BODY + 1))):
            with self.assertRaisesRegex(order.OrderUnavailable, "size limit"):
                remote.request("https://graph.microsoft.com/v1.0/x")
        # Every clock read passes until the body starts to arrive; the
        # reader's next one finds the deadline gone, which must come back as
        # "timed out", not as a size limit or a bare transport error.
        early, late = remote.deadline - 100, remote.deadline + 1
        clock = [early]

        class Arriving(Response):
            def read1(self, size=-1):
                clock[0] = late
                return super().read1(size)

        with patch.object(remote.opener, "open", return_value=Arriving(b"x")):
            with patch.object(order.time, "monotonic", side_effect=lambda: clock[0]):
                with self.assertRaisesRegex(order.OrderUnavailable, "timed out"):
                    remote.request("https://graph.microsoft.com/v1.0/x")

    def test_graph_401_never_refreshes_or_forgets_shared_auth(self):
        remote = order.Remote("snapshot")
        with patch.object(order.msgraph, "access_token") as token, patch.object(order.msgraph, "forget_token") as forget:
            with patch.object(remote, "request", return_value=(401, b"")) as request:
                with self.assertRaises(order.OrderUnavailable):
                    remote.get(order.item_path("x"))
                self.assertEqual(request.call_args.args[1], "snapshot")
                self.assertEqual(request.call_count, 1)
            token.assert_not_called()
            forget.assert_not_called()

    def test_request_count_limit_before_sending(self):
        remote = order.Remote("snapshot")
        remote.requests = order.MAX_REQUESTS
        with patch.object(remote.opener, "open") as opened:
            with self.assertRaises(order.OrderUnavailable):
                remote.request("https://test.files.1drv.com/x")
            opened.assert_not_called()

    def test_metadata_throttle_has_its_own_budget(self):
        remote = order.Remote("snapshot")
        with patch.object(order.ratelimit, "attempt_loop", return_value=(429, b"")) as attempt:
            remote.request(order.msgraph.GRAPH + order.item_path("x"), "snapshot")
        self.assertEqual(attempt.call_args.args[0], "graph-onenote-section-order")
        self.assertNotEqual(attempt.call_args.args[0], onenote.msgraph.settings.rate_key)


def run():
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    return unittest.TextTestRunner().run(suite).wasSuccessful()


if __name__ == "__main__":
    unittest.main()
