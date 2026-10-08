"""OneNote merge integration, with a scripted server and private temporary state."""
import contextlib
import html
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from xml.etree import ElementTree as ET

WORK = tempfile.TemporaryDirectory(prefix="note-note-onenote-merges-")
for variable, subdir in (("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache"),
                         ("XDG_CONFIG_HOME", "config"), ("NOTE_NOTE_RATE_DIR", "rate")):
    os.environ[variable] = str(Path(WORK.name) / subdir)
os.environ["NOTE_NOTE_MS_TOKEN"] = str(Path(WORK.name) / "token.json")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote  # noqa: E402
from notemerge import MergeStore, StaleRemote  # noqa: E402
from qthtml import to_html, to_markdown  # noqa: E402


def note(body, title="Title"):
    return {"title": title, "body": body}


def page_html(value):
    source = ('<html><head><title>' + html.escape(value["title"]) + '</title></head><body><div>'
              + onenote.onenote_md.markdown_to_onenote_html(value["body"]) + '</div></body></html>')
    tree = ET.fromstring(source)
    for index, node in enumerate(tree.iter()):
        if node.tag in onenote.onenote_patch.REPLACEABLE or node.tag == "div":
            node.set("id", "%s:fixture%d" % (node.tag, index))
    return ET.tostring(tree, encoding="unicode")


class ImageConversionTests(unittest.TestCase):
    def test_known_pasted_image_keeps_display_width_during_normalization(self):
        local = "file:///tmp/cached-image"
        entry = {"src": "https://graph.microsoft.com/v1.0/me/onenote/resources/picture/$value", "width": 624}
        with patch.object(onenote, "known_image", side_effect=lambda url: entry if url == local else None):
            normalized = onenote.normalize_note(note("![Picture](%s)" % local))
            self.assertIn("{width=624}", normalized["body"])
            resized = onenote.normalize_note(note("![Picture](%s){width=200}" % local))
            self.assertIn("{width=200}", resized["body"])
            unknown = onenote.normalize_note(note("![Picture](file:///tmp/other-image)"))
            self.assertNotIn("{width=", unknown["body"])

    def test_generated_descriptions_preserve_images_in_every_container(self):
        descriptions = (
            "Text alternativ generat automat:\n\n",
            "First line\r\n\t\r\nsecond line",
            "Scan [page] and ] unmatched [",
            r"**bold** _underlined_ `code` ==mark== <tag> | C:\scan",
            "Literal &copy; and &#10; & text",
        )
        containers = ("%s", "<p>%s</p>", "<ul><li>%s</li></ul>",
                      "<table><tr><td>%s</td></tr></table>")
        local = "file:///tmp/scan-(page.png"
        for description in descriptions:
            for container in containers:
                with self.subTest(description=description, container=container):
                    image = '<img src="resource" alt="%s" width="624"/>' % html.escape(description, quote=True)
                    source = "<body>" + container % image + "</body>"
                    loaded = onenote.onenote_md.html_to_markdown(source, lambda src, width: local)
                    self.assertTrue(loaded["editable"])
                    self.assertTrue(loaded["images"])
                    self.assertTrue(all(item["alt"] == description for item in loaded["images"]))
                    for markdown in (loaded["body"], onenote.normalize_note(loaded)["body"]):
                        rendered = to_html(markdown)
                        pictures = list(ET.fromstring("<body>" + rendered + "</body>").iter("img"))
                        self.assertEqual(len(pictures), 1, markdown)
                        self.assertEqual(pictures[0].attrib, {
                            "src": local, "alt": " ".join(description.split()), "width": "624",
                        })
                        saved = to_markdown(rendered)
                        self.assertEqual(to_markdown(to_html(saved)), saved)


class SaveTests(unittest.TestCase):
    def recording(self, name="phone", title="Audio Recording.3gp"):
        """An attachment served by the scripted page endpoint, whose bytes a
        save can fetch to copy or recreate it."""
        source = "https://graph.microsoft.com/v1.0/me/onenote/resources/%s/$value" % name
        self.store_recording(source, ("synthetic audio " + name).encode())
        return ('<object id="object:%s" data="%s" type="video/3gpp" '
                'data-attachment="%s" style="width:120px"></object>' % (name, source, html.escape(title)))

    def store_recording(self, source, data):
        """The bytes Graph serves for a recording, where the patched fetch finds them."""
        path = Path(onenote.recording_cache_path(source, "Audio Recording.3gp"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.audio_paths[source] = "file://" + str(path)

    def audio_page(self, contents):
        self.remote = ('<html><head><title>Title</title></head><body><div id="div:audio">'
                       + contents + '</div></body></html>')

    def operations(self):
        return [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]

    def upload_audio_patch(self, url, commands, parts):
        """Acknowledge uploaded parts with new Graph resource identities."""
        references = {}
        for name, mime, data in parts:
            self.audio_uploads.append((name, mime, data))
            source = "https://graph.microsoft.com/v1.0/me/onenote/resources/%s/$value" % name
            self.store_recording(source, data)
            references["name:" + name] = source
        expanded = json.dumps(commands)
        for reference, source in references.items():
            expanded = expanded.replace(reference, source)
        return self.graph("PATCH", url, expanded)

    def test_moving_recording_keeps_audio_bytes_and_text(self):
        self.audio_page('<p id="p:before">Before</p>' + self.recording() + '<p id="p:after">After</p>')
        loaded = self.load()
        audio_markup = loaded["body"].split("\n\n")[1]
        with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
            result = self.save(note("Before  \nAfter\n\n" + audio_markup), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(self.audio_uploads, [])
        self.assertEqual(len(list(ET.fromstring(self.remote).iter("object"))), 1)
        self.assertIn('id="p:before"', self.remote)
        self.assertIn('id="object:phone"', self.remote)
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(result))

    def test_audio_outside_the_recording_cache_is_refused_and_the_draft_kept(self):
        # Pasted markup can name any local file; a save must never upload it.
        self.audio_page('<p id="p:text">Text</p>')
        loaded = self.load()
        path = Path(self.temp.name) / "New recording.3gp"
        path.write_bytes(b"private bytes")
        audio_markup = '<audio src="%s" title="New recording.3gp"></audio>' % path.as_uri()
        with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
            result = self.save(note(loaded["body"] + "\n\n" + audio_markup), loaded["view"])
        self.assertIn("did not come from OneNote", result.get("error", ""))
        self.assertEqual(self.audio_uploads, [])
        self.assertEqual(self.operations(), [])
        with self.store() as journal:
            self.assertIn("New recording.3gp", journal.recover()["body"])

    def test_copied_recording_saves_and_subsequent_edits_keep_both_resources(self):
        for placement in ("before", "middle", "after", "inline"):
            with self.subTest(placement=placement):
                with self.store() as journal:
                    journal.discard()
                self.audio_uploads.clear()
                self.audio_page('<p id="p:before">Before</p>' + self.recording() + '<p id="p:after">After</p>')
                loaded = self.load()
                original = loaded["body"].split("\n\n")[1]
                copied = original.replace('data-id="nn-audio-legacy-', 'data-id="nn-audio-copy-')
                bodies = {
                    "before": copied + "\n\n" + loaded["body"],
                    "middle": loaded["body"].replace(original, original + "\n\n" + copied),
                    "after": loaded["body"] + "\n\n" + copied,
                    "inline": loaded["body"].replace("After", "After " + copied),
                }
                body = bodies[placement]
                with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
                    result = self.save(note(body), loaded["view"])
                    self.assertTrue(result.get("ok"), result)
                    self.assertEqual(len(self.audio_uploads), 1)
                    self.assertIn('id="object:phone"', self.remote)
                    self.calls.clear()
                    edited = body.replace("Before", "Edited before")
                    result = self.save(note(edited), loaded["view"])
                self.assertTrue(result.get("ok"), result)
                self.assertEqual(len(self.audio_uploads), 1, "editing text must not upload either recording again")
                recordings = list(ET.fromstring(self.remote).iter("object"))
                self.assertEqual(len(recordings), 2)
                self.assertEqual(len({recording.get("data") for recording in recordings}), 2)
                self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(result))

    def test_recording_pasted_into_another_note_keeps_both_notes_saveable(self):
        self.audio_page('<p id="p:source">Source text</p>' + self.recording())
        source_html = self.remote
        source = self.load("source")
        original = source["body"].split("\n\n")[1]
        copied = original.replace('data-id="nn-audio-legacy-', 'data-id="nn-audio-copy-')
        original_resource = next(ET.fromstring(source_html).iter("object")).get("data")
        self.audio_page('<p id="p:target">Target text</p>')
        target = self.load("target")
        pasted = target["body"] + "\n\n" + copied
        self.calls.clear()
        with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
            result = self.save(note(pasted), target["view"], page_id="target")
            self.assertTrue(result.get("ok"), result)
            self.assertEqual([(mime, data) for _, mime, data in self.audio_uploads],
                             [("video/3gpp", b"synthetic audio phone")])
            copied_resource = next(ET.fromstring(self.remote).iter("object")).get("data")
            self.assertNotEqual(copied_resource, original_resource)
            result = self.save(note(pasted.replace("Target text", "Edited target")),
                               target["view"], page_id="target")
            self.assertTrue(result.get("ok"), result)
            self.assertEqual(len(self.audio_uploads), 1)
            self.assertEqual(onenote.normalize_note(self.load("target")), onenote.normalize_note(result))
            self.assertTrue(all("/target/" in path for method, path, _ in self.calls if method == "PATCH"))
            self.remote = source_html
            self.assertEqual(self.load("source")["body"], source["body"])
            result = self.save(note(source["body"].replace("Source text", "Edited source")),
                               source["view"], page_id="source")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(len(self.audio_uploads), 1, "editing the source must retain its original resource")
        self.assertEqual(next(ET.fromstring(self.remote).iter("object")).get("data"), original_resource)
        self.assertIn('id="object:phone"', self.remote)

    def test_draft_naming_downloaded_recordings_is_recovered_and_saved(self):
        # Earlier builds downloaded recordings with the page and named them
        # by their cached files. Such a draft keeps its text; the recording
        # it did not change is the page's own, and is neither lost nor copied.
        self.audio_page('<p id="p:text">Text</p>' + self.recording())
        downloaded = '<audio src="file:///cache/%s.3gp" title="Audio Recording.3gp" data-id="nn-audio-legacy-%s-1"></audio>' % (
            "a" * 64, "a" * 64)
        base = note("Text\n\n" + downloaded)
        draft = note("Unsaved text\n\n" + downloaded)
        with MergeStore(self.temp.name, "onenote", "test-account", "page") as journal:
            view = journal.open(base)["view"]
            journal.stage(view, draft)
        recovered = self.load()
        self.assertTrue(recovered.get("recovered"), recovered)
        self.assertIn("Unsaved text", recovered["body"])
        with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
            result = self.save(draft, view)
        self.assertTrue(result.get("ok"), result)
        self.assertIn("Unsaved text", self.remote)
        self.assertEqual(len(list(ET.fromstring(self.remote).iter("object"))), 1)
        self.assertIn('id="object:phone"', self.remote)
        self.assertFalse(self.audio_uploads)
        with self.store() as journal:
            self.assertIsNone(journal.recover())

    def test_text_edits_preserve_recording_and_neighbouring_elements(self):
        attachment = self.recording()
        self.audio_page('<p id="p:before">Before</p>' + attachment + '<p id="p:after">After</p>')
        original = ET.tostring(next(ET.fromstring(self.remote).iter("object")))
        loaded = self.load()
        self.assertTrue(loaded["editable"], loaded)
        desired = to_markdown(to_html(loaded["body"])).replace("Before", "Edited before").replace("After", "Edited after")
        result = self.save(note(desired), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([op["target"] for op in self.operations()], ["p:before", "p:after"])
        self.assertTrue(all("<object" not in op["content"] for op in self.operations()))
        self.assertEqual(ET.tostring(next(ET.fromstring(self.remote).iter("object"))), original)
        self.assertEqual(self.load()["body"], result["body"])

    def test_audio_only_page_accepts_text_before_and_after(self):
        self.audio_page(self.recording())
        loaded = self.load()
        result = self.save(note("Before\n\n" + loaded["body"] + "\n\nAfter"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        operations = self.operations()
        self.assertEqual([op["target"] for op in operations], ["object:phone", "object:phone"])
        self.assertEqual([op["position"] for op in operations], ["before", "after"])
        self.assertIn('id="object:phone"', self.remote)
        self.assertEqual(self.load()["body"], result["body"])

    def test_phone_recording_without_object_id_uses_its_layout_for_pastes(self):
        self.generate_object_ids = False
        cases = [(placement, breaks) for placement in ("before", "after") for breaks in (0, 1, 3)]
        for placement, breaks in cases:
            with self.subTest(placement=placement, breaks=breaks):
                with self.store() as journal:
                    journal.discard()
                self.audio_uploads.clear()
                attachment = self.recording().replace(' id="object:phone"', '')
                self.audio_page(attachment + '<br/>' * breaks)
                tree = ET.fromstring(self.remote)
                next(tree.iter("div")).set("style", "position:absolute;left:48px;top:139px;width:624px")
                self.remote = ET.tostring(tree, encoding="unicode")
                original = ET.tostring(next(tree.iter("object")))
                loaded = self.load()
                copied = loaded["body"].replace('data-id="nn-audio-legacy-', 'data-id="nn-audio-copy-')
                bodies = {"before": copied + "\n\n" + loaded["body"],
                          "after": loaded["body"] + "\n\n\u00a0" * breaks + "\n\n" + copied}
                self.calls.clear()
                with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
                    result = self.save(note(bodies[placement]), loaded["view"])
                    self.assertTrue(result.get("ok"), result)
                    operations = self.operations()
                    self.assertEqual(len(operations), 1)
                    self.assertEqual({key: operations[0][key] for key in ("target", "action", "position")},
                                     {"target": "div:audio", "action": "append", "position": placement})
                    self.assertEqual(len(self.audio_uploads), 1)
                    recordings = list(ET.fromstring(self.remote).iter("object"))
                    self.assertEqual(len(recordings), 2)
                    retained = next(recording for recording in recordings if not recording.get("data-id"))
                    self.assertEqual(ET.tostring(retained), original)
                    self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(result))
                    self.calls.clear()
                    remaining = loaded["body"]
                    result = self.save(note(remaining), self.load()["view"])
                self.assertTrue(result.get("ok"), result)
                self.assertEqual(len(self.audio_uploads), 1)
                self.assertEqual(len(self.operations()), 1)
                self.assertTrue(self.operations()[0]["target"].startswith("#nn-audio-copy-"))
                self.assertEqual(len(list(ET.fromstring(self.remote).iter("object"))), 1)

    def test_legacy_pending_audio_copy_can_save_without_a_graph_object_id(self):
        self.audio_page(self.recording().replace(' id="object:phone"', '') + '<br/>')
        loaded = self.load()
        identifier = onenote.onenote_md.audio.from_markup(loaded["body"])["id"]
        legacy = loaded["body"].replace(' data-id="%s"' % identifier, '')
        desired = legacy + "\n\n\u00a0\n\n" + legacy + "\n\n\u00a0\n\nCaption"
        with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
            result = self.save(note(desired), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(len(self.audio_uploads), 1)
        self.assertEqual(len(list(ET.fromstring(self.remote).iter("object"))), 2)
        self.assertIn("Caption", self.remote)
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(result))
        with self.store() as journal:
            self.assertIsNone(journal.recover())

    def test_text_around_phone_recording_without_id_keeps_original_bytes(self):
        self.audio_page(self.recording().replace(' id="object:phone"', '') + '<br/>')
        loaded = self.load()
        result = self.save(note("Before\n\n" + loaded["body"] + "\n\n\u00a0\n\nAfter"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([(op["target"], op["action"], op["position"]) for op in self.operations()],
                         [("div:audio", "append", "before"), ("div:audio", "append", "after")])
        self.assertEqual(self.audio_uploads, [])
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(result))

    def test_recordings_with_same_filename_keep_distinct_resources(self):
        self.audio_page(self.recording("first") + self.recording("second") + '<p id="p:end">End</p>')
        loaded = self.load()
        self.assertEqual(loaded["body"].count("<audio"), 2)
        result = self.save(note(loaded["body"].replace("End", "Edited ending")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([op["target"] for op in self.operations()], ["p:end"])
        self.assertIn('id="object:first"', self.remote)
        self.assertIn('id="object:second"', self.remote)

    def test_table_cell_edits_preserve_recording(self):
        attachment = self.recording()
        self.audio_page('<table id="table:audio"><tr><td>' + attachment + '<p id="p:caption">Caption</p>'
                        '</td><td><p id="p:neighbour">Neighbour</p></td></tr></table>')
        loaded = self.load()
        self.assertTrue(loaded["editable"], loaded)
        result = self.save(note(loaded["body"].replace("Caption", "Edited caption")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([op["target"] for op in self.operations()], ["p:caption"])
        self.assertIn('id="object:phone"', self.remote)
        self.assertIn('id="p:neighbour"', self.remote)

    def test_remote_recording_added_during_local_text_edit_is_merged(self):
        self.audio_page('<p id="p:text">Original text</p>')
        loaded = self.load()
        attachment = self.recording()
        self.audio_page('<p id="p:text">Original text</p>' + attachment)
        result = self.save(note("Edited text"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertIn("<audio", result["body"])
        self.assertEqual([op["target"] for op in self.operations()], ["p:text"])
        self.assertIn('id="object:phone"', self.remote)

    def test_recording_deletion_is_explicit_and_preserves_neighbour(self):
        self.audio_page(self.recording() + '<p id="p:keep">Keep</p>')
        loaded = self.load()
        result = self.save(note("Keep"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([op["target"] for op in self.operations()], ["object:phone"])
        self.assertNotIn("<object", self.remote)
        self.assertIn('id="p:keep"', self.remote)

    def test_title_edit_does_not_touch_recording(self):
        self.audio_page(self.recording())
        loaded = self.load()
        result = self.save(note(loaded["body"], "New title"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([op["target"] for op in self.operations()], ["title"])
        self.assertIn('id="object:phone"', self.remote)

    def test_inline_text_edit_recreates_recording_with_unchanged_bytes(self):
        self.audio_page('<p id="p:inline">Before ' + self.recording() + ' after</p><p id="p:keep">Keep</p>')
        loaded = self.load()
        with patch.object(onenote, "patch_page", side_effect=self.upload_audio_patch):
            result = self.save(note(loaded["body"].replace("Before", "Edited before")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([(mime, data) for _, mime, data in self.audio_uploads], [("video/3gpp", b"synthetic audio phone")])
        self.assertIn('id="p:keep"', self.remote)
        self.assertEqual(len(list(ET.fromstring(self.remote).iter("object"))), 1)
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(result))
        loaded = self.load()
        self.calls.clear()
        result = self.save(note(loaded["body"].replace("Keep", "Keep edited")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(len(self.operations()), 1)
        self.assertNotIn("<object", self.operations()[0]["content"])

    def test_edit_beside_normalized_layout_preserves_original_elements(self):
        image = Path(onenote.ONENOTE_IMG_DIR) / "layout-image"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"synthetic image")
        patch.object(onenote, "cached_image", return_value=image.as_uri()).start()
        src = "https://graph.microsoft.com/v1.0/me/onenote/resources/layout/$value"
        layout = ('<img id="img:banner" src="' + src + '" alt="Generated description:&#10;&#10;" width="400"/>'
                  '<table id="table:ideas"><tr><td><ul id="ul:ideas">'
                  '<li id="li:first">First idea</li>\n<br/>\n<li id="li:second">Second idea</li>'
                  '</ul></td></tr></table>')
        photos = ('<table id="table:photos"><tr><td><p id="p:caption">Caption</p></td></tr>'
                  '<tr><td><img id="img:photo" src="' + src + '" alt="Photo" width="100"/></td></tr></table>')
        heading = ('<table id="table:heading"><tr><td><p id="p:left">Left</p></td>'
                   '<td><p id="p:middle"></p></td><td><p id="p:right">Right</p></td></tr></table>')
        self.remote = ('<html><head><title>Title</title></head><body><div id="div:layout">'
                       + layout + heading + photos + '<p id="p:end">End</p></div></body></html>')
        original = ET.fromstring(self.remote)
        loaded = self.load()
        displayed = ET.fromstring("<body>" + to_html(loaded["body"]) + "</body>")
        pictures = list(displayed.iter("img"))
        self.assertEqual(len(pictures), 2)
        self.assertEqual(pictures[0].get("alt"), "Generated description:")
        desired = loaded["body"].replace('| Left |  | Right |', r'| Left | \| | Right |')
        desired = desired.replace('End', 'Edited ending')
        self.assertNotEqual(desired, loaded["body"])
        result = self.save(note(desired), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([op["target"] for op in operations], ["p:middle", "p:end"])
        current = ET.fromstring(self.remote)
        for identifier in ("img:banner", "table:ideas", "table:photos", "p:left", "p:right"):
            before = next(node for node in original.iter() if node.get("id") == identifier)
            after = next(node for node in current.iter() if node.get("id") == identifier)
            self.assertEqual(ET.tostring(after), ET.tostring(before))
        self.assertEqual(self.load()["body"], result["body"])

    def test_inline_table_cell_edit_preserves_layout_and_nearby_targets(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:before">Before</p><table id="table:legacy" style="border:0px;width:400px">'
                       '<tr><td style="width:190px"><span style="color:#3f3f3f;font-weight:bold">Left</span></td>'
                       '<td style="width:20px"><br/></td><td style="width:190px"><b>Right</b></td></tr></table>'
                       '<p id="p:after">After</p></div></body></html>')
        original = ET.fromstring(self.remote)
        loaded = self.load()
        changed = loaded["body"].replace(' |  | ', r' | \| | ')
        result = self.save(note(changed), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([op["target"] for op in operations], ["table:legacy"])
        content = ET.fromstring(operations[0]["content"])
        old_table = next(original.iter("table"))
        self.assertEqual(content.attrib, {key: value for key, value in old_table.attrib.items() if key != "id"})
        old_cells, new_cells = list(old_table.iter("td")), list(content.iter("td"))
        for index in (0, 2):
            self.assertEqual(ET.tostring(new_cells[index]), ET.tostring(old_cells[index]))
        identifiers = {node.get("id") for node in ET.fromstring(self.remote).iter()}
        self.assertTrue({"p:before", "p:after"}.issubset(identifiers))
        self.assertEqual(self.load()["body"], result["body"])

    def test_untargetable_cell_does_not_replace_nested_editable_content(self):
        self.remote = ('<html><head><title>Title</title></head><body><div><table id="table:mixed">'
                       '<tr><td><p id="p:keep">Keep</p></td><td><br/></td></tr></table></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace('| Keep |  |', '| Keep | Added |')), loaded["view"])
        self.assertIn("no editable paragraph", result.get("error", ""))
        self.assertFalse(any(method == "PATCH" for method, *_ in self.calls))
        self.assertIn('id="p:keep"', self.remote)

    def test_color_conversion_and_reset_preserve_checkboxes_and_neighbours(self):
        self.remote = ('<html><head><title>Title</title></head><body><div id="div:food">'
                       '<p id="p:mushrooms" data-tag="to-do:completed"><span style="color:#0070c0">Mushrooms</span></p>'
                       '<p id="p:milk" data-tag="to-do">Milk</p></div></body></html>')
        loaded = self.load()
        self.assertIn('<span style="color:#0070c0;">Mushrooms</span>', loaded["body"])
        changed = loaded["body"].replace("#0070c0", "#ff0000")
        result = self.save(note(changed), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertIn("#ff0000", self.remote)
        self.assertIn('data-tag="to-do:completed"', self.remote)
        self.assertIn('id="p:milk"', self.remote)
        loaded = self.load()
        reset = loaded["body"].replace('<span style="color:#ff0000;">Mushrooms</span>', 'Mushrooms')
        result = self.save(note(reset), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertNotIn("color:", self.remote)
        self.assertIn('data-tag="to-do:completed"', self.remote)


    def test_nested_table_conversion_preserves_cell_blocks(self):
        source = ('<table><tr><td><p>Parent</p></td><td><p>Neighbour</p></td></tr><tr><td>'
                  '<p><strong>before</strong></p><table><tr><td><p>Inner</p></td></tr>'
                  '<tr><td><p>one</p></td></tr></table><p>after</p></td><td><p>untouched</p></td></tr></table>')
        rendered = onenote.onenote_md.markdown_to_onenote_html(source)
        actual = onenote.onenote_md.html_to_markdown(rendered)
        self.assertTrue(actual["editable"])
        self.assertEqual(actual["body"], source)

    def test_table_lists_preserve_markers_and_check_states(self):
        for contents in ("- **One**\n- Two", "3. One\n4. Two", "- [x] One\n- [ ] Two"):
            with self.subTest(contents=contents):
                source = onenote.onenote_md.htmltables.table_markup([[contents, "Neighbour"]])
                rendered = onenote.onenote_md.markdown_to_onenote_html(source)
                actual = onenote.onenote_md.html_to_markdown(rendered)
                self.assertTrue(actual["editable"])
                self.assertEqual(actual["body"], source)

    def test_apply_lists_in_table_cells_saves_without_replacing_neighbours(self):
        for contents in ("- One", "1. One", "- [ ] One"):
            with self.subTest(contents=contents):
                with self.store() as journal:
                    journal.discard()
                self.remote = ('<html><head><title>Title</title></head><body><div><table id="table:lists">'
                               '<tr><td><p id="p:header">Header</p></td><td><p id="p:neighbour">Neighbour</p></td></tr>'
                               '<tr><td><p id="p:target">One</p></td><td><p id="p:untouched">untouched</p></td></tr>'
                               '</table></div></body></html>')
                neighbour = next(node for node in ET.fromstring(self.remote).iter("p") if node.text == "untouched")
                loaded = self.load()
                desired = onenote.onenote_md.htmltables.table_markup([["Header", "Neighbour"], [contents, "untouched"]])
                result = self.save(note(desired), loaded["view"])
                self.assertTrue(result.get("ok"), result)
                self.assertEqual(self.load()["body"], desired)
                self.assertIn(neighbour.get("id"), self.remote)

    def test_table_export_uses_onenote_border_attribute(self):
        cases = [
            "| Item | Quantity |\n|---|---|\n| Apples | 2 |",
            "|  |  |\n|---|---|\n|  |  |",
            '<table><tr><td><p>Parent</p><table><tr><td><p>Inner</p></td></tr></table>'
            '</td></tr></table>',
        ]
        for source in cases:
            with self.subTest(source=source):
                rendered = onenote.onenote_md.markdown_to_onenote_html(source)
                tables = list(ET.fromstring("<root>" + rendered + "</root>").iter("table"))
                self.assertTrue(tables)
                for table in tables:
                    self.assertEqual(table.get("border"), "1")
                    self.assertNotIn("border:", table.get("style", ""))

    def test_literal_pipes_in_table_cells_survive_save_and_reload(self):
        self.remote = ('<html><head><title>Title</title></head><body><div><table id="table:pipes">'
                       '<tr><td><p id="p:head1"></p></td><td><p id="p:head2"></p></td></tr>'
                       '<tr><td><p id="p:cell1"></p></td><td><p id="p:cell2"></p></td></tr>'
                       '</table></div></body></html>')
        loaded = self.load()
        cases = [
            ("|", r"\|"),
            ("left|right", r"left\|right"),
            (r"\|", r"\\\|"),
            (r"\\|", r"\\\\\|"),
            ("bold|pipe", r"**bold\|pipe**"),
        ]
        for text, markdown in cases:
            with self.subTest(text=text):
                row = "| " + markdown + " | " + markdown + " |"
                desired = row + "\n|---|---|\n" + row
                result = self.save(note(desired), loaded["view"])
                self.assertTrue(result.get("ok"), result)
                current = ET.fromstring(self.remote)
                tables = list(current.iter("table"))
                self.assertEqual(len(tables), 1)
                rows = list(tables[0].iter("tr"))
                self.assertEqual(len(rows), 2)
                for row in rows:
                    self.assertEqual(["".join(cell.itertext()) for cell in row], [text, text])
                loaded = self.load()
                self.assertEqual(loaded["body"], desired)

    def test_appending_calendar_with_repeated_heading_preserves_existing_page(self):
        self.remote = ('<html><head><title>Title</title></head><body><div id="div:main">'
                       '<p id="p:item" data-tag="to-do">Apples</p><br/>'
                       '<p id="p:month">September 2026</p></div></body></html>')
        loaded = self.load()
        table = "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |\n|---|---|---|---|---|---|---|"
        table += "\n|  |  |  |  |  |  |  |" * 5
        desired = loaded["body"] + "\n\n\u00a0\n\nSeptember 2026\n\n" + table
        saved = self.save(note(desired), loaded["view"])
        self.assertTrue(saved.get("ok"), saved)
        self.assertEqual(self.load()["body"], desired)
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([(op["target"], op["action"], op.get("position")) for op in operations],
                         [("p:month", "insert", "after")])
        current = ET.fromstring(self.remote)
        paragraphs = {node.get("id"): node for node in current.iter("p")}
        self.assertEqual(paragraphs["p:month"].text, "September 2026")
        self.assertEqual(paragraphs["p:item"].get("data-tag"), "to-do")
        rows = list(next(current.iter("table")).iter("tr"))
        self.assertEqual(len(rows), 6)
        self.assertEqual([cell.text for cell in rows[0]], ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertTrue(all(not "".join(cell.itertext()).strip() for row in rows[1:] for cell in row))
        with self.store() as journal:
            self.assertIsNone(journal.recover())

    def test_clearing_table_body_preserves_header_cells_and_structure(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:before">Before</p><table id="table:calendar">'
                       '<tr id="tr:head"><td id="td:mon"><p id="p:mon">Mon</p></td>'
                       '<td id="td:tue"><p id="p:tue">Tue</p></td></tr>'
                       '<tr id="tr:one"><td id="td:empty"><br/></td>'
                       '<td id="td:one"><p id="p:one">1</p></td></tr>'
                       '<tr id="tr:two"><td id="td:two"><p id="p:two">2</p></td>'
                       '<td id="td:three"><p id="p:three">3</p></td></tr>'
                       '</table><p id="p:after">After</p></div></body></html>')
        original = ET.fromstring(self.remote)
        loaded = self.load()
        desired = loaded["body"].replace("|  | 1 |", "|  |  |")
        desired = desired.replace("| 2 | 3 |", "|  |  |")
        saved = self.save(note(desired), loaded["view"])
        self.assertTrue(saved.get("ok"), saved)
        self.assertEqual(self.load()["body"], desired)
        current = ET.fromstring(self.remote)
        kept = {node.get("id"): node for node in current.iter()}
        for node in original.iter():
            identifier = node.get("id")
            if identifier and identifier not in {"p:one", "p:two", "p:three"}:
                self.assertIn(identifier, kept)
                self.assertEqual(kept[identifier].attrib, node.attrib)
                if identifier in {"p:before", "p:after", "tr:head", "td:empty"}:
                    self.assertEqual(ET.tostring(kept[identifier]), ET.tostring(node))
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([op["target"] for op in operations], ["p:one", "p:two", "p:three"])
        self.assertTrue(all(op["content"] == "<p><br/></p>" for op in operations))

    def test_partial_deletion_of_repeated_entries_still_preserves_draft(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:first" data-tag="to-do">Same</p>'
                       '<p id="p:second" data-tag="to-do">Same</p></div></body></html>')
        loaded = self.load()
        saved = self.save(note("- [ ] Same"), loaded["view"])
        self.assertIn("repeated entry", saved.get("error", ""))
        self.assertFalse(any(method == "PATCH" for method, *_ in self.calls))
        with self.store() as journal:
            self.assertEqual(journal.recover()["body"], "- [ ] Same")

    def test_formatting_the_page_cannot_keep_is_refused_before_staging(self):
        # A quote, a code block, inline code and a rule are written as looks
        # the reader cannot read back; they used to be flattened silently,
        # because the guard ran on a draft the merge store had normalised.
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:one">One</p></div></body></html>')
        loaded = self.load()
        for body, kinds in (("> One", "a quote"), ("One `x`", "inline code"),
                            ("One\n\n```\nx\n```", "a code block"), ("One\n\n---\n\n> x", "a rule or a quote")):
            with self.subTest(body):
                self.calls.clear()
                saved = self.save(note(body), loaded["view"])
                self.assertIn("cannot keep " + kinds, saved.get("error", ""))
                self.assertFalse(any(method == "PATCH" for method, *_ in self.calls))
        with self.store() as journal:
            self.assertIsNone(journal.recover())
        saved = self.save(note("One **kept**"), loaded["view"])
        self.assertTrue(saved.get("ok"), saved)

    def test_nested_table_insertion_preserves_parent_and_neighbour_ids(self):
        self.remote = ('<html><head><title>Title</title></head><body><table id="table:outer">'
                       '<tr><td><p id="p:head1">Parent</p></td><td><p id="p:head2">Neighbour</p></td></tr>'
                       '<tr><td><p id="p:before">before</p></td><td><p id="p:neighbour">untouched</p></td></tr>'
                       '</table></body></html>')
        loaded = self.load()
        nested = ('<table><tr><td><p>Parent</p></td><td><p>Neighbour</p></td></tr><tr><td>'
                  '<p>before</p><table><tr><td><p>Inner</p></td></tr><tr><td><p>one</p></td></tr></table>'
                  '</td><td><p>untouched</p></td></tr></table>')
        result = self.save(note(nested), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        current = ET.fromstring(self.remote)
        self.assertEqual(len(list(current.iter("table"))), 2)
        identifiers = {node.get("id") for node in current.iter()}
        self.assertTrue({"table:outer", "p:head1", "p:head2", "p:before", "p:neighbour"}.issubset(identifiers))
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([(op["target"], op["action"]) for op in operations], [("p:before", "insert")])
        reloaded = self.load()
        self.assertEqual(reloaded["body"], nested)
        self.calls.clear()
        result = self.save(note(nested.replace("<p>one</p>", "<p>edited</p>")), reloaded["view"])
        self.assertTrue(result.get("ok"), result)
        edited = ET.fromstring(self.remote)
        self.assertEqual(len(list(edited.iter("table"))), 2)
        self.assertTrue(identifiers - {node.get("id") for node in current.iter("p") if node.text == "one"}
                        <= {node.get("id") for node in edited.iter()})
        targets = [op["target"] for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].startswith("p:"))

    def test_nested_table_insertion_into_empty_cell(self):
        self.remote = ('<html><head><title>Title</title></head><body><table id="table:outer">'
                       '<tr><td><p id="p:head1">Parent</p></td><td><p id="p:head2">Neighbour</p></td></tr>'
                       '<tr><td><p id="p:empty"><br/></p></td><td><p id="p:neighbour">untouched</p></td></tr>'
                       '</table></body></html>')
        loaded = self.load()
        nested = ('<table><tr><td><p>Parent</p></td><td><p>Neighbour</p></td></tr><tr><td>'
                  '<table><tr><td><p>Inner</p></td></tr><tr><td><p>one</p></td></tr></table>'
                  '</td><td><p>untouched</p></td></tr></table>')
        result = self.save(note(nested), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        current = ET.fromstring(self.remote)
        self.assertEqual(len(list(current.iter("table"))), 2)
        identifiers = {node.get("id") for node in current.iter()}
        self.assertTrue({"table:outer", "p:head1", "p:head2", "p:neighbour"}.issubset(identifiers))
        self.assertEqual(self.load()["body"], nested)

    def test_table_deletion_preserves_surrounding_content(self):
        nested = ('<table><tr><td><p>Parent</p></td><td><p>Neighbour</p></td></tr><tr><td>'
                  '<table><tr><td><p>Inner</p></td></tr><tr><td><p>value</p></td></tr></table>'
                  '</td><td><p>untouched</p></td></tr></table>')
        cases = [
            ("entire table", "Before\n\n" + nested + "\n\nAfter", "Before\n\nAfter", 0),
            ("inner table", nested, "| Parent | Neighbour |\n|---|---|\n|  | untouched |", 1),
        ]
        for name, source, expected, tables in cases:
            with self.subTest(name=name):
                self.remote = page_html(note(source))
                tree = ET.fromstring(self.remote)
                labels = {"Parent", "Neighbour", "untouched"} if tables else {"Before", "After"}
                neighbours = {node.get("id") for node in tree.iter("p")
                              if node.text in labels}
                if tables:
                    neighbours.add(next(tree.iter("table")).get("id"))
                loaded = self.load()
                result = self.save(note(expected), loaded["view"])
                self.assertTrue(result.get("ok"), result)
                current = ET.fromstring(self.remote)
                self.assertEqual(len(list(current.iter("table"))), tables)
                self.assertTrue(neighbours <= {node.get("id") for node in current.iter()})
                reloaded = self.load()
                self.assertEqual(onenote.normalize_note(reloaded), onenote.normalize_note(note(expected)))
                if tables:
                    refilled = expected.replace("|  | untouched |", "| new text | untouched |")
                    result = self.save(note(refilled), reloaded["view"])
                    self.assertTrue(result.get("ok"), result)
                    self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(note(refilled)))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=WORK.name)
        self.addCleanup(self.temp.cleanup)
        self.remote = page_html(note("one\n\nmiddle\n\nthree"))
        self.calls = []
        self.refuse_title = False
        self.refuse_body = False
        self.refuse_paragraphs = False
        self.write_ids = 0
        self.audio_paths = {}
        self.audio_uploads = []
        self.generate_object_ids = True
        self.addCleanup(patch.stopall)
        self.raw_transport = onenote.graph_raw
        patch.object(onenote, "merge_store", self.store).start()
        patch.object(onenote, "graph_raw", self.graph).start()
        patch.object(onenote, "graph", side_effect=AssertionError("unexpected network request")).start()
        patch.object(onenote, "ONENOTE_AUDIO_DIR", str(Path(self.temp.name) / "audio")).start()
        patch.object(onenote, "AUDIO_INDEX", str(Path(self.temp.name) / "audio/index.json")).start()
        patch.object(onenote, "cached_audio", side_effect=lambda src, title: self.audio_paths.get(src)).start()

    def store(self, page_id="page"):
        return MergeStore(self.temp.name, "onenote", "test-account", page_id,
                          normalize=onenote.normalize_note, stale_seconds=120)

    def graph(self, method, path, data=None, content_type=None, **options):
        self.calls.append((method, path, data))
        if method == "GET":
            return 200, self.remote
        if method == "PATCH":
            operations = json.loads(data)
            current = ET.fromstring(self.remote)
            for operation in operations:
                if operation["target"] == "title":
                    if self.refuse_title:
                        return 500, '{"error":{"message":"title refused"}}'
                    current.find("./head/title").text = html.unescape(operation["content"])
                else:
                    if self.refuse_body:
                        return 400, '{"error":{"message":"body refused"}}'
                    if self.refuse_paragraphs and operation["target"].startswith("p:"):
                        return 400, '{"error":{"message":"The PATCH target P for action replace is not supported"}}'
                    replacements = list(ET.fromstring("<root>" + operation["content"] + "</root>"))
                    for replacement in replacements:
                        for child in replacement.iter():
                            self.write_ids += 1
                            if child.tag != "object" or self.generate_object_ids:
                                child.set("id", "%s:written%d" % (child.tag, self.write_ids))
                    if operation["target"] == "body":
                        self.assertEqual(operation["action"], "append", "a save must never replace the page body")
                        body = current.find("body")
                        outer = body.find("div")
                        (outer if outer is not None else body).extend(replacements)
                        continue
                    identifier = operation["target"]
                    attribute = "data-id" if identifier.startswith("#") else "id"
                    value = identifier[1:] if attribute == "data-id" else identifier
                    found = [(parent, child) for parent in current.iter() for child in parent
                             if child.get(attribute) == value]
                    self.assertEqual(len(found), 1, "PATCH targeted a missing or repeated generated ID")
                    parent, child = found[0]
                    index = list(parent).index(child)
                    if operation["action"] == "replace":
                        parent[index:index + 1] = replacements
                    elif operation["action"] == "append":
                        if operation.get("position", "after") == "before":
                            child[0:0] = replacements
                        else:
                            child.extend(replacements)
                    else:
                        self.assertEqual(operation["action"], "insert")
                        index += int(operation.get("position", "after") == "after")
                        parent[index:index] = replacements
            self.remote = ET.tostring(current, encoding="unicode")
            return 204, ""
        raise AssertionError("unexpected request " + method)

    def invoke(self, function, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                function(*args)
            except SystemExit:
                pass
        return json.loads(output.getvalue())

    def load(self, page_id="page"):
        return self.invoke(onenote.cmd_onenote_page, page_id)

    def save(self, value, view, resolution=None, page_id="page"):
        path = Path(self.temp.name) / "payload.json"
        path.write_text(json.dumps(dict(value, view=view, resolution=resolution)))
        return self.invoke(onenote.cmd_onenote_update, page_id, str(path))

    @contextlib.contextmanager
    def http_transport(self, endpoint):
        """Use the actual authentication wrapper, HTTP handling and retry loop."""
        with (patch.object(onenote, "graph_raw", self.raw_transport),
              patch.object(onenote, "access_token", return_value="synthetic-token"),
              patch.object(onenote.msgraph.settings, "rate_key", None),
              patch.object(onenote.msgraph.urllib.request, "urlopen", side_effect=endpoint)):
            yield

    def response(self, request):
        status, content = self.graph(request.get_method(), request.full_url.removeprefix(onenote.GRAPH), request.data)
        response = io.BytesIO(content.encode())
        response.status = status
        return response

    def test_uncertain_insertion_is_reconciled_before_an_explicit_retry(self):
        loaded = self.load()
        local = note("one\n\nadded\n\nmiddle\n\nthree")
        failed = False

        def endpoint(request, **options):
            nonlocal failed
            response = self.response(request)
            if request.get_method() == "PATCH" and not failed:
                # The service applied the insertion but returned an error.
                failed = True
                raise urllib.error.HTTPError(request.full_url, 503, "uncertain", {"Retry-After": "0"}, io.BytesIO(b"{}"))
            return response

        with self.http_transport(endpoint):
            result = self.save(local, loaded["view"])
            self.assertIn("error", result)
            self.assertNotIn("kind", result)
            self.assertEqual([method for method, _, _ in self.calls], ["GET", "GET", "PATCH"])
            with self.store() as store:
                self.assertEqual(store.recover()["body"], onenote.normalize_note(local)["body"])
            # A deliberate retry observes that the content already landed.
            result = self.save(local, loaded["view"])
            self.assertTrue(result.get("ok"), result)
            self.assertEqual([method for method, _, _ in self.calls], ["GET", "GET", "PATCH", "GET"])
            self.assertEqual(onenote.normalize_note(onenote.onenote_md.html_to_markdown(self.remote)), onenote.normalize_note(local))

    def test_503_replacement_restarts_with_a_fresh_merge(self):
        loaded = self.load()
        local = note("APP\n\nmiddle\n\nthree")
        failed = False

        def endpoint(request, **options):
            nonlocal failed
            if request.get_method() == "PATCH" and not failed:
                failed = True
                self.calls.append(("PATCH", request.full_url, request.data))
                raise urllib.error.HTTPError(request.full_url, 503, "uncertain", {"Retry-After": "0"}, io.BytesIO(b"{}"))
            return self.response(request)

        with self.http_transport(endpoint):
            with self.assertRaises(onenote.msgraph.ratelimit.Throttled):
                self.save(local, loaded["view"])
            self.remote = page_html(note("one\n\nmiddle\n\nPHONE"))
            result = self.save(local, loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["body"], onenote.normalize_note(note("APP\n\nmiddle\n\nPHONE"))["body"])
        self.assertEqual([method for method, _, _ in self.calls], ["GET", "GET", "PATCH", "GET", "PATCH"])

    def test_fetch_merge_write_and_next_edit(self):
        loaded = self.load()
        self.remote = page_html(note("one\n\nmiddle\n\nPHONE"))
        first = self.save(note("APP\n\nmiddle\n\nthree"), loaded["view"])
        self.assertTrue(first["ok"])
        self.assertTrue(first["merged"])
        self.assertEqual(first["body"], onenote.normalize_note(note("APP\n\nmiddle\n\nPHONE"))["body"])
        self.assertEqual([call[0] for call in self.calls], ["GET", "GET", "PATCH"])
        # The editor still shows its old third paragraph while this save runs.
        second = self.save(note("APP AGAIN\n\nmiddle\n\nthree"), loaded["view"])
        self.assertEqual(second["body"], onenote.normalize_note(note("APP AGAIN\n\nmiddle\n\nPHONE"))["body"])

    def test_different_checkboxes_on_phone_and_app_merge(self):
        original = note("- [ ] Apples\n- [ ] Bread\n- [ ] Coffee")
        self.remote = page_html(original)
        loaded = self.load()
        self.remote = page_html(note(original["body"].replace("[ ] Apples", "[x] Apples")))
        ours = note(original["body"].replace("[ ] Bread", "[x] Bread"))
        result = self.save(ours, loaded["view"])
        self.assertTrue(result.get("ok"), result)
        expected = note(original["body"].replace("[ ] Apples", "[x] Apples").replace("[ ] Bread", "[x] Bread"))
        self.assertEqual(result["body"], onenote.normalize_note(expected)["body"])
        stored = onenote.onenote_md.html_to_markdown(self.remote)
        self.assertEqual(onenote.normalize_note(stored), onenote.normalize_note(expected))
        operations = [operation for method, _, data in self.calls if method == "PATCH" for operation in json.loads(data)]
        self.assertEqual(len(operations), 1)
        self.assertTrue(operations[0]["target"].startswith("p:"))
        self.assertNotIn("Apples", operations[0]["content"])

    def test_late_phone_checkbox_edit_still_targets_the_same_item(self):
        self.remote = page_html(note("- [ ] Apples\n- [ ] Bread\n- [ ] Coffee"))
        phone = ET.fromstring(self.remote)
        phone_item = next(node for node in phone.iter("p") if node.text == "Apples")
        phone_id = phone_item.get("id")
        loaded = self.load()
        saved = self.save(note(loaded["body"].replace("[ ] Bread", "[x] Bread")), loaded["view"])
        self.assertTrue(saved.get("ok"), saved)
        # A phone syncs its earlier view after the app's write. Its original
        # item must still exist, otherwise OneNote can resurrect it elsewhere.
        current = ET.fromstring(self.remote)
        targets = [node for node in current.iter("p") if node.get("id") == phone_id]
        self.assertEqual(len(targets), 1)
        targets[0].set("data-tag", "to-do:completed")
        self.remote = ET.tostring(current, encoding="unicode")
        reloaded = self.load()
        self.assertEqual(reloaded["body"], "- [x] Apples\n- [x] Bread\n- [ ] Coffee")
        self.assertEqual(len(list(current.iter("p"))), 3)

    def test_rejected_item_update_never_falls_back_to_replacing_the_list(self):
        self.remote = page_html(note("- [ ] Apples\n- [ ] Bread"))
        before = self.remote
        loaded = self.load()
        self.refuse_paragraphs = True
        result = self.save(note("- [ ] Apples\n- [x] Bread"), loaded["view"])
        self.assertIn("not supported", result["error"])
        self.assertEqual(self.remote, before)
        operations = [operation for method, _, data in self.calls if method == "PATCH" for operation in json.loads(data)]
        self.assertEqual(len(operations), 1)
        self.assertNotEqual(operations[0]["target"], "body")
        self.assertTrue(self.load()["recovered"])

    def test_uncertain_insertion_is_not_automatically_repeated(self):
        operations = [
            {"target": "p:anchor", "action": "replace", "content": "<p>edited</p>"},
            {"target": "p:anchor", "action": "insert", "content": "<p>new</p>"},
            {"target": "body", "action": "append", "content": "<p>new</p>"},
        ]
        for operation in operations:
            with self.subTest(action=operation["action"]):
                with patch.object(onenote, "graph_raw", return_value=(500, "uncertain")) as request:
                    onenote.patch_page("/page/content", [operation], [])
                expected = onenote.msgraph.RetryPolicy.RESTART if operation["action"] == "replace" else onenote.msgraph.RetryPolicy.NEVER
                self.assertEqual(request.call_args.kwargs["retry_policy"], expected)

    def test_checkbox_state_preserves_native_inline_formatting(self):
        cases = (("ul", "Intro"), ("ol", "Intro"), ("ol", '<span data-tag="to-do">Intro</span>'))
        for index, (container, intro) in enumerate(cases):
            for state, updated in (("to-do", "to-do:completed"), ("to-do:completed", "to-do")):
                with self.subTest(container=container, state=state):
                    self.remote = ('<html><head><title>Title</title></head><body><div id="div:root">'
                                   '<%s id="%s:list"><li id="li:intro">%s</li>'
                                   '<li id="li:task" style="margin-left:8px"><span data-tag="%s" data-id="task">'
                                   '<span style="color:red;font-family:Arial">Task</span></span></li>'
                                   '</%s></div></body></html>') % (container, container, intro, state, container)
                    # Each representation has a separate editing baseline.
                    with patch.object(onenote, "merge_store", side_effect=lambda page: self.store(str(index) + state)):
                        loaded = self.load()
                        before = "[x]" if state.endswith(":completed") else "[ ]"
                        after = "[x]" if updated.endswith(":completed") else "[ ]"
                        result = self.save(note(loaded["body"].replace(before + ' <span style="color:#ff0000;">Task</span>', after + ' <span style="color:#ff0000;">Task</span>')), loaded["view"])
                    self.assertTrue(result.get("ok"), result)
                    tree = ET.fromstring(self.remote)
                    carrier = next(node for node in tree.iter("span") if node.get("data-id") == "task")
                    self.assertEqual(carrier.get("data-tag"), updated)
                    self.assertEqual(carrier.find("span").get("style"), "color:red;font-family:Arial")
                    self.assertEqual(list(tree.iter("li"))[1].get("style"), "margin-left:8px")
                    self.assertEqual(list(tree.iter("li"))[0].get("id"), "li:intro")
                    self.assertEqual(tree.find(".//" + container).get("id"), container + ":list")

    def assert_paragraph_edit_preserves_neighbours(self, body):
        original = note("one\n\nmiddle\n\nlast")
        self.remote = page_html(original)
        loaded = self.load()
        anchor = next(node.get("id") for node in ET.fromstring(self.remote).iter("p") if node.text == "one")
        self.calls = []
        result = self.save(note(body), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        current = ET.fromstring(self.remote)
        self.assertEqual(next(node.get("id") for node in current.iter("p") if node.text == "one"), anchor)
        self.assertEqual(onenote.normalize_note(onenote.onenote_md.html_to_markdown(self.remote)),
                         onenote.normalize_note(note(body)))
        self.assertTrue(all(operation["target"] != "body" for method, _, data in self.calls if method == "PATCH"
                            for operation in json.loads(data)))

    def test_inserted_paragraph_preserves_neighbours(self):
        self.assert_paragraph_edit_preserves_neighbours("one\n\nadded\n\nmiddle\n\nlast")

    def test_deleted_paragraph_preserves_neighbours(self):
        self.assert_paragraph_edit_preserves_neighbours("one\n\nlast")

    def test_expanded_final_paragraph_preserves_neighbours(self):
        self.assert_paragraph_edit_preserves_neighbours("one\n\nmiddle\n\nLAST\n\nextra")

    def test_identical_item_names_keep_positions_and_inline_formatting(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:first" data-tag="to-do"><span style="color:#123456">Same</span></p>'
                       '<p id="p:second" data-tag="to-do"><span style="color:#abcdef">Same</span></p>'
                       '</div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace('[ ] <span style="color:#abcdef;">', '[x] <span style="color:#abcdef;">')), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        operations = [operation for method, _, data in self.calls if method == "PATCH" for operation in json.loads(data)]
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["target"], "p:second")
        self.assertIn('style="color:#abcdef"', operations[0]["content"])

    def test_repeated_checkbox_and_prose_edits_keep_both_devices_changes(self):
        self.remote = page_html(note("- [ ] Same\n- [ ] Same\n- [x] Same\n\nFooter"))
        loaded = self.load()
        self.remote = page_html(note("- [ ] Same\n- [ ] Same\n- [ ] Same\n\nFooter"))
        result = self.save(note("- [ ] Same\n- [x] Same\n- [x] Same\n\nNew footer"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(self.load()["body"], "- [ ] Same\n- [x] Same\n- [ ] Same\n\nNew footer")

    def test_repeated_labels_and_footer_edit_preserve_the_untouched_item(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:first" data-tag="to-do">Same</p>'
                       '<p id="p:second" data-tag="to-do"><span style="color:#abcdef">Same</span></p>'
                       '<p id="p:footer">Footer</p></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("[ ] Same", "[x] Same").replace("Footer", "New footer")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        kept = next(node for node in ET.fromstring(self.remote).iter("p") if node.get("id") == "p:second")
        self.assertEqual(kept.get("data-tag"), "to-do")
        self.assertEqual(kept.find("span").get("style"), "color:#abcdef")
        targets = [op["target"] for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual(targets, ["p:first", "p:footer"])

    def test_blank_line_does_not_turn_a_checkbox_edit_into_a_page_replacement(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:first" data-tag="to-do">Apples</p><br/>'
                       '<p id="p:second" data-tag="to-do">Bread</p></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("[ ] Bread", "[x] Bread")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([op["target"] for op in operations], ["p:second"])
        self.assertEqual(len(list(ET.fromstring(self.remote).iter("br"))), 1)

    def test_mobile_table_and_boundary_breaks_do_not_block_pending_save(self):
        self.remote = ('<html><head><title>Title</title></head><body><div id="div:main">'
                       '<p id="p:first" data-tag="to-do">Apples</p>'
                       '<p id="p:remove">Remove this heading</p>'
                       '<p id="p:second" data-tag="to-do">Bread</p></div></body></html>')
        loaded = self.load()
        local = loaded["body"].replace("\n\nRemove this heading\n", "")
        table = ('<table id="table:mobile" style="border:1px solid;border-collapse:collapse">'
                 '<tr id="tr:first"><td id="td:first" style="border:1px solid"><br/></td>'
                 '<td id="td:second" style="border:1px solid"><br/></td></tr>'
                 '<tr id="tr:second"><td id="td:third" style="border:1px solid"><br/></td>'
                 '<td id="td:fourth" style="border:1px solid"><br/></td></tr></table>')
        self.remote = self.remote.replace('<p id="p:first"', '<br/><br/><p id="p:first"')
        self.remote = self.remote.replace('</div></body>', '<br/><br/>' + table + '</div>'
                                          '<div id="div:empty"><br/><br/></div></body>')
        result = self.save(note(local), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertTrue(result.get("merged"), result)
        self.assertNotIn("Remove this heading", result["body"])
        self.assertIn("|  |  |\n|---|---|\n|  |  |", result["body"])
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual(operations, [{"target": "p:remove", "action": "replace", "content": "<div></div>"}])
        current = ET.fromstring(self.remote)
        self.assertEqual(ET.tostring(next(current.iter("table"))), ET.tostring(ET.fromstring(table)))
        self.assertEqual(len(list(current.iter("br"))), 10)
        self.assertEqual(self.load()["body"], result["body"])
        with self.store() as journal:
            self.assertIsNone(journal.recover())

    def test_append_after_table_keeps_ignored_trailing_breaks(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<table id="table:mobile"><tr><td><br/></td></tr></table><br/>'
                       '</div><div id="div:empty"><br/></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"] + "\n\nAfter table"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([(op["target"], op["action"], op.get("position")) for op in operations],
                         [("table:mobile", "insert", "after")])
        self.assertEqual(len(list(ET.fromstring(self.remote).iter("br"))), 3)
        self.assertEqual(self.load()["body"], result["body"])

    def test_deletion_can_turn_internal_breaks_into_boundary_breaks(self):
        table = ('<table id="table:remove"><tr><td><p id="p:cell">Heading</p></td></tr>'
                 '<tr><td><br/></td></tr></table>')
        kept = '<p id="p:keep" data-tag="to-do">Keep this</p>'
        cases = [
            ("last table", kept + '<br/><br/>' + table, "- [ ] Keep this", ["table:remove"]),
            ("first table", table + '<br/><br/>' + kept, "- [ ] Keep this", ["table:remove"]),
            ("whole page", kept + '<br/>' + table, "", ["p:keep", "table:remove"]),
            ("last paragraph", kept + '<br/><p id="p:remove">Remove this</p>',
             "- [ ] Keep this", ["p:remove"]),
        ]
        for name, content, desired, targets in cases:
            with self.subTest(name=name):
                with self.store() as journal:
                    journal.discard()
                self.remote = ('<html><head><title>Title</title></head><body>'
                               '<div id="div:main">' + content + '</div></body></html>')
                breaks = len(list(ET.fromstring(self.remote).iter("br")))
                loaded = self.load()
                self.calls.clear()
                result = self.save(note(desired), loaded["view"])
                self.assertTrue(result.get("ok"), result)
                self.assertEqual(self.load()["body"], desired)
                operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
                self.assertEqual([op["target"] for op in operations], targets)
                current = ET.fromstring(self.remote)
                self.assertEqual(len(list(current.iter("table"))), 0)
                self.assertEqual(len(list(current.iter("br"))), breaks - int("table:remove" in targets))
                if desired:
                    remaining = next(node for node in current.iter("p") if node.get("id") == "p:keep")
                    self.assertEqual(ET.tostring(remaining), ET.tostring(ET.fromstring(kept)))
                with self.store() as journal:
                    self.assertIsNone(journal.recover())

    def test_table_deletion_merges_with_remote_spacing_change(self):
        table = ('<table id="table:mobile"><tr><td><br/></td><td><br/></td></tr>'
                 '<tr><td><br/></td><td><br/></td></tr></table>')
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:keep" data-tag="to-do">Apples</p><br/><br/><br/>'
                       + table + '</div></body></html>')
        loaded = self.load()
        self.remote = self.remote.replace('</p><br/><br/><br/>', '</p><br/>')
        result = self.save(note("- [ ] Apples"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertNotIn("conflict", result)
        self.assertEqual(self.load()["body"], "- [ ] Apples")
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual(operations, [{"target": "table:mobile", "action": "replace", "content": "<div></div>"}])

    def revision_service(self):
        """Remove blank lines from the simulated page as the web revision service does."""
        def remove(page_id, runs):
            self.calls.append(("REVISION", page_id, runs))
            current = ET.fromstring(self.remote)
            for run in runs:
                parent = next(node for node in current.iter() if any(child.get("id") == run.before for child in node))
                siblings = list(parent)
                start = next(index for index, child in enumerate(siblings) if child.get("id") == run.before) + 1
                breaks = siblings[start:start + run.count]
                self.assertEqual([node.tag for node in breaks], ["br"] * run.count)
                self.assertEqual(siblings[start + run.count].get("id"), run.after)
                for index in run.removed:
                    parent.remove(breaks[index])
            self.remote = ET.tostring(current, encoding="unicode")

        patch.object(onenote, "remove_blank_lines", side_effect=remove).start()

    def blank_line_page(self, middle='<br/>'):
        self.remote = ('<html><head><title>Title</title></head><body><div id="div:outline">'
                       '<p id="p:first">Before</p>' + middle + '<p id="p:second">After</p>'
                       '</div></body></html>')

    def test_deleting_a_blank_line_removes_it_through_the_revision_service(self):
        self.revision_service()
        self.blank_line_page('<br/><br/>')
        loaded = self.load()
        result = self.save(note("Before\n\nAfter"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([call[2] for call in self.calls if call[0] == "REVISION"],
                         [(onenote.onenote_patch.BlankLines("p:first", "p:second", 2, (0, 1)),)])
        self.assertFalse(any(method == "PATCH" for method, *_ in self.calls))
        current = ET.fromstring(self.remote)
        self.assertEqual(list(current.iter("br")), [])
        self.assertEqual([node.get("id") for node in current.iter("p")], ["p:first", "p:second"])
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(note("Before\n\nAfter")))

    def test_typing_on_a_blank_line_replaces_it_in_place(self):
        self.revision_service()
        self.blank_line_page()
        loaded = self.load()
        result = self.save(note("Before\n\nMiddle\n\nAfter"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        kinds = [call[0] for call in self.calls if call[0] in ("REVISION", "PATCH")]
        self.assertEqual(kinds, ["REVISION", "PATCH"])
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([(op["action"], op["position"], op["target"]) for op in operations],
                         [("insert", "before", "p:second")])
        current = ET.fromstring(self.remote)
        self.assertEqual(list(current.iter("br")), [])
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(note("Before\n\nMiddle\n\nAfter")))

    def test_blank_lines_are_removed_before_graph_edits_their_neighbours(self):
        self.revision_service()
        self.blank_line_page()
        loaded = self.load()
        result = self.save(note("Edited\n\nAfter"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        kinds = [call[0] for call in self.calls if call[0] in ("REVISION", "PATCH")]
        self.assertEqual(kinds, ["REVISION", "PATCH"])
        self.assertEqual(onenote.normalize_note(self.load()), onenote.normalize_note(note("Edited\n\nAfter")))

    def test_deleting_a_blank_line_without_revision_access_keeps_the_draft(self):
        self.blank_line_page()
        loaded = self.load()
        result = self.save(note("Before\n\nAfter"), loaded["view"])
        self.assertIn("remove them in OneNote", result.get("error", ""))
        self.assertIn("your draft was kept", result["error"])
        self.assertFalse(any(method == "PATCH" for method, *_ in self.calls))
        with self.store() as journal:
            self.assertEqual(journal.recover()["body"], onenote.normalize_note(note("Before\n\nAfter"))["body"])

    def test_a_blank_line_beside_an_element_without_an_id_keeps_the_draft(self):
        self.revision_service()
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:first">Before</p><cite>Quoted</cite><br/><p id="p:second">After</p>'
                       '</div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("\n\n ", "")), loaded["view"])
        self.assertIn("no editable target", result.get("error", ""))
        self.assertFalse(any(call[0] in ("REVISION", "PATCH") for call in self.calls))

    def test_inserting_a_blank_line_preserves_existing_elements(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<p id="p:first" data-tag="to-do">Apples</p><br/>'
                       '<p id="p:second" data-tag="to-do">Bread</p></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("\u00a0", "\u00a0\n\n\u00a0")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        current = ET.fromstring(self.remote)
        self.assertEqual(len(list(current.iter("br"))), 2)
        self.assertTrue({"p:first", "p:second"}.issubset({node.get("id") for node in current.iter()}))

    def test_unchanged_content_needs_no_patch_target(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<cite>Keep this</cite><p id="p:edit">Original</p></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("Original", "Edited")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(next(ET.fromstring(self.remote).iter("cite")).text, "Keep this")

    def test_ordinary_list_item_edit_preserves_list_and_neighbour(self):
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<ul id="ul:list"><li id="li:first">Apples</li><li id="li:second">Bread</li></ul>'
                       '<p id="p:footer">Footer</p></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("Bread", "Coffee")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        identifiers = {node.get("id") for node in ET.fromstring(self.remote).iter()}
        self.assertTrue({"ul:list", "li:first", "p:footer"}.issubset(identifiers))
        operations = [op for method, _, data in self.calls if method == "PATCH" for op in json.loads(data)]
        self.assertEqual([op["target"] for op in operations], ["li:second"])

    def test_nested_list_item_edit_preserves_its_ancestors(self):
        self.remote = page_html(note("- Parent\n  - Apples\n  - Bread\n- Other"))
        loaded = self.load()
        original = ET.fromstring(self.remote)
        parent_id = next(node.get("id") for node in original.iter("li") if node.text == "Parent")
        result = self.save(note(loaded["body"].replace("Bread", "Coffee")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertIn(parent_id, {node.get("id") for node in ET.fromstring(self.remote).iter("li")})

    def test_table_cell_edit_preserves_other_cells(self):
        self.remote = ('<html><head><title>Title</title></head><body><div><table id="table:one">'
                       '<tr><td><p id="p:apple">Apples</p></td><td><p id="p:bread">Bread</p></td></tr>'
                       '</table></div></body></html>')
        loaded = self.load()
        result = self.save(note(loaded["body"].replace("Bread", "**Coffee**")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        identifiers = {node.get("id") for node in ET.fromstring(self.remote).iter()}
        self.assertTrue({"table:one", "p:apple"}.issubset(identifiers))
        self.assertIn("**Coffee**", self.load()["body"])

    def test_missing_target_keeps_the_draft_without_replacing_the_page(self):
        self.remote = '<html><head><title>Title</title></head><body><div><p>Original</p></div></body></html>'
        loaded = self.load()
        result = self.save(note("Edited"), loaded["view"])
        self.assertIn("no editable target", result["error"])
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.calls))
        self.assertEqual(self.load()["body"], "Edited")

    def test_invalid_simulation_keeps_the_draft_without_writing(self):
        loaded = self.load()
        invalid = onenote.onenote_patch.Plan((), "<body><p>Wrong</p></body>", ())
        with patch.object(onenote.onenote_patch, "plan", return_value=invalid):
            result = self.save(note("Edited"), loaded["view"])
        self.assertIn("could not preserve", result["error"])
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.calls))
        self.assertEqual(self.load()["body"], "Edited")

    def test_simulation_checks_unchanged_identity_as_well_as_text(self):
        loaded = self.load()
        real_simulate = onenote.onenote_patch.simulate

        def lose_identity(tree, commands):
            simulated = real_simulate(tree, commands)
            for node in onenote.onenote_patch.walk(simulated):
                if node.tag == "p" and onenote.onenote_patch.text(node) == "three":
                    node.attrs.pop("id")
            return simulated

        with patch.object(onenote.onenote_patch, "simulate", side_effect=lose_identity):
            result = self.save(note(loaded["body"].replace("one", "Edited")), loaded["view"])
        self.assertIn("lost its identity", result["error"])
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.calls))

    def test_empty_page_is_populated_by_appending(self):
        self.remote = '<html><head><title>Title</title></head><body><div/></body></html>'
        loaded = self.load()
        result = self.save(note("First paragraph"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(self.load()["body"], "First paragraph")

    def test_conflict_never_writes_and_recovery_can_be_resolved(self):
        loaded = self.load()
        self.remote = page_html(note("PHONE\n\nmiddle\n\nthree"))
        ours = note("APP\n\nmiddle\n\nthree")
        result = self.save(ours, loaded["view"])
        self.assertTrue(result["conflict"])
        self.assertEqual([call[0] for call in self.calls], ["GET", "GET"])
        recovered = self.load()
        self.assertTrue(recovered["recovered"])
        self.assertEqual(recovered["body"], onenote.normalize_note(ours)["body"])
        resolution = {"id": result["conflict"]["id"], "choices": {
            part["id"]: "both" for part in result["conflict"]["parts"]}}
        saved = self.save(ours, loaded["view"], resolution)
        self.assertTrue(saved["ok"])
        self.assertIn("APP", saved["body"])
        self.assertIn("PHONE", saved["body"])

    def test_remote_changes_during_conflict_review_require_another_review(self):
        loaded = self.load()
        self.remote = page_html(note("phone"))
        result = self.save(note("app"), loaded["view"])
        resolution = {"id": result["conflict"]["id"], "choices": {
            part["id"]: "local" for part in result["conflict"]["parts"]}}
        self.remote = page_html(note("new phone changes"))
        result = self.save(note("app"), loaded["view"], resolution)
        self.assertTrue(result["conflict"])
        self.assertFalse(any(call[0] == "PATCH" for call in self.calls))

    def test_no_change_has_no_write(self):
        loaded = self.load()
        result = self.save(loaded, loaded["view"])
        self.assertTrue(result["ok"])
        self.assertFalse(any(call[0] == "PATCH" for call in self.calls))

    def test_remote_only_title_change_survives_local_body_save(self):
        loaded = self.load()
        self.remote = page_html(note(loaded["body"], "Phone title"))
        saved = self.save(note("app body"), loaded["view"])
        self.assertEqual(saved["title"], "Phone title")
        operations = [json.loads(call[2]) for call in self.calls if call[0] == "PATCH"]
        self.assertTrue(all(operation["target"] != "title" for batch in operations for operation in batch))

    def test_failed_title_retains_draft_and_correct_next_merge_base(self):
        loaded = self.load()
        self.refuse_title = True
        result = self.save(note("first", "New title"), loaded["view"])
        self.assertIn("title", result["error"])
        self.assertEqual(self.load()["body"], "first")
        self.refuse_title = False
        result = self.save(note("second", "New title"), loaded["view"])
        self.assertEqual(result["body"], "second")
        self.assertEqual(result["title"], "New title")

    def test_missing_base_and_unrepresentable_remote_do_not_write(self):
        with self.assertRaises(ValueError):
            self.save(note("app"), "missing")
        self.assertEqual(self.calls, [])
        loaded = self.load()
        self.remote = '<html><head><title>Title</title></head><body><object data="ink"/></body></html>'
        result = self.save(note("app"), loaded["view"])
        self.assertIn("cannot be saved safely", result["error"])
        self.assertFalse(any(call[0] == "PATCH" for call in self.calls))

    def test_stale_read_does_not_revert_previous_merge(self):
        old = self.remote
        loaded = self.load()
        self.save(note("first"), loaded["view"])
        self.remote = old
        count = len(self.calls)
        with self.assertRaises(StaleRemote):
            self.save(note("second"), loaded["view"])
        self.assertEqual([call[0] for call in self.calls[count:]], ["GET"])
        self.assertEqual(self.load()["body"], "second")

    def test_failed_body_save_retains_local_and_observed_remote(self):
        loaded = self.load()
        self.refuse_body = True
        result = self.save(note("app"), loaded["view"])
        self.assertIn("body refused", result["error"])
        with self.store() as store:
            self.assertEqual(store._state["draft"]["local"]["body"], "app")
            self.assertEqual(store._state["draft"]["remote"]["body"], loaded["body"])

    def test_poll_does_not_replace_an_editing_baseline_or_recover_a_draft(self):
        loaded = self.load()
        with self.store() as store:
            store.stage(loaded["view"], note("unsaved"))
        checked = self.invoke(onenote.cmd_onenote_page, "page", True)
        self.assertEqual(checked["body"], loaded["body"])
        self.assertNotIn("view", checked)
        with self.store() as store:
            self.assertEqual(store._state["views"][loaded["view"]]["body"], loaded["body"])

    def test_remote_image_added_during_local_edit_is_kept_without_upload(self):
        loaded = self.load()
        src = "https://graph.microsoft.com/v1.0/me/onenote/resources/new/$value"
        path = str(Path(onenote.ONENOTE_IMG_DIR) / "new-image")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"synthetic image")
        patch.object(onenote, "cached_image", return_value="file://" + path).start()
        self.remote = ('<html><head><title>Title</title></head><body><div>'
                       '<div id="div:text"><p id="p:one">one</p><p id="p:middle">middle</p><p id="p:three">three</p></div>'
                       '<img id="img:new" src="' + src + '" alt="Phone photo"/>'
                       '</div></body></html>')
        writes = []

        def record_patch(url, commands, parts):
            writes.extend(commands)
            self.assertEqual(parts, [])
            return 204, ""

        patch.object(onenote, "patch_page", record_patch).start()
        result = self.save(note("APP\n\nmiddle\n\nthree"), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertIn("Phone photo", result["body"])
        self.assertTrue(writes)
        self.assertTrue(all(command["target"] != "img:new" for command in writes))
        self.assertTrue(all("<img" not in command.get("content", "") for command in writes))

    def test_page_read_keeps_alias_for_a_previously_uploaded_paste(self):
        paste = Path(self.temp.name) / "paste.png"
        paste.write_bytes(b"synthetic image")
        entry = {"src": "https://graph.microsoft.com/v1.0/me/onenote/resources/paste/$value", "width": 200}
        onenote.save_private(onenote.IMAGE_INDEX, {"staged": {str(paste): entry}})
        self.load()
        self.assertEqual(onenote.known_image(paste.as_uri()), entry)

    def test_upload_aliases_follow_markers_instead_of_document_order(self):
        uploads = onenote.Uploads()
        files = [Path(self.temp.name) / (name + ".png") for name in ("first", "second")]
        references = []
        for index, path in enumerate(files):
            path.write_bytes(b"synthetic image " + bytes([index]))
            references.append(uploads.ref(path.as_uri(), "")[0])
        first, second = list(uploads.staged.values())
        source = "https://graph.microsoft.com/v1.0/me/onenote/resources/"
        html = ('<body><div><div><img data-id="' + second["dataId"] + '" src="' + source + 'second/$value"/>'
                '<img data-id="' + first["dataId"] + '" src="' + source + 'first/$value"/></div></div></body>')
        rendered = uploads.render_uploads("".join('<img src="' + reference + '"/>' for reference in references))
        self.assertIn(first["dataId"], rendered)
        self.assertIn(second["dataId"], rendered)
        onenote.remember_staged(uploads.staged, html)
        self.assertEqual(onenote.known_image(files[0].as_uri())["src"], source + "first/$value")
        self.assertEqual(onenote.known_image(files[1].as_uri())["src"], source + "second/$value")

    def test_only_a_changed_existing_image_is_materialized(self):
        path = Path(self.temp.name) / "photo.png"
        path.write_bytes(b"synthetic image")
        source = "https://graph.microsoft.com/v1.0/me/onenote/resources/photo/$value"
        onenote.save_private(onenote.IMAGE_INDEX, {"staged": {str(path): {"src": source, "width": 100}}})
        uploads = onenote.Uploads()
        uploads.ref(path.as_uri(), "")
        unchanged = uploads.materialize([{"target": "p:text", "action": "replace", "content": "<p>New text</p>"}])
        self.assertEqual(uploads.parts, [])
        self.assertNotIn("<img", unchanged[0]["content"])
        resized = uploads.materialize([{"target": "img:photo", "action": "replace",
                                        "content": '<img src="' + source + '" width="200"/>'}])
        self.assertEqual(len(uploads.parts), 1)
        self.assertIn('src="name:' + uploads.parts[0][0] + '"', resized[0]["content"])
        self.assertNotIn(source, resized[0]["content"])
        self.assertEqual(next(iter(uploads.staged.values()))["width"], 200)

    def test_no_longer_readable_image_blocks_write(self):
        loaded = self.load()
        patch.object(onenote, "cached_image", return_value=None).start()
        self.remote = ('<html><body><p>one</p><img src="https://example.invalid/picture"/></body></html>')
        result = self.save(note("app"), loaded["view"])
        self.assertIn("cannot be saved safely", result["error"])
        self.assertFalse(any(call[0] == "PATCH" for call in self.calls))

    def test_markdown_structure_is_preserved_when_sections_change_independently(self):
        original = note("# Shopping\n\n- [ ] Milk\n\n## Notes\n\n**Remember**")
        self.remote = page_html(original)
        loaded = self.load()
        self.remote = page_html(note(original["body"].replace("Remember", "Phone reminder")))
        result = self.save(note(original["body"].replace("Milk", "Bread")), loaded["view"])
        self.assertTrue(result.get("ok"), result)
        self.assertIn("# Shopping", result["body"])
        self.assertIn("[ ] Bread", result["body"])
        self.assertIn("**Phone reminder**", result["body"])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        WORK.cleanup()
