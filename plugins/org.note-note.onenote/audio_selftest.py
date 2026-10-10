"""OneNote recordings: conversion, fetching on play, identity and media uploads."""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

WORK = tempfile.TemporaryDirectory(prefix="note-note-onenote-audio-")
os.environ["NOTE_NOTE_STATE_DIR"] = WORK.name + "/state"
os.environ["NOTE_NOTE_CACHE_DIR"] = WORK.name + "/cache"
os.environ["NOTE_NOTE_RATE_DIR"] = WORK.name + "/rate"
os.environ["NOTE_NOTE_MS_TOKEN"] = WORK.name + "/token.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import onenote  # noqa: E402
import onenote_md  # noqa: E402

RESOURCE = "https://graph.microsoft.com/v1.0/users('test@example.com')/onenote/resources/audio-id/$value"
COPY = RESOURCE.replace("audio-id", "copy-id")
IMAGE = RESOURCE.replace("audio-id", "image-id")
PHONE_OBJECT = '<object data-attachment="Audio Recording.3gp" type="video/3gpp" data="%s" />' % RESOURCE


def private_cache(test):
    """Empty recording and image caches, a test token and no pacing."""
    directory = tempfile.TemporaryDirectory(dir=WORK.name)
    test.addCleanup(directory.cleanup)
    stack = contextlib.ExitStack()
    test.addCleanup(stack.close)
    work = Path(directory.name)
    stack.enter_context(patch.object(onenote, "ONENOTE_AUDIO_DIR", str(work / "audio")))
    stack.enter_context(patch.object(onenote, "AUDIO_INDEX", str(work / "audio/index.json")))
    stack.enter_context(patch.object(onenote, "ONENOTE_IMG_DIR", str(work / "images")))
    stack.enter_context(patch.object(onenote, "_image_budget", onenote.FetchBudget(seconds=45, requests=40)))
    stack.enter_context(patch.object(onenote, "_recording_budget", onenote.FetchBudget(seconds=300, requests=4)))
    stack.enter_context(patch.object(onenote.ratelimit, "slot", side_effect=lambda *a, **kw: contextlib.nullcontext()))
    token = stack.enter_context(patch.object(onenote, "access_token", return_value="test-token"))
    return work, token


def responses(data):
    return patch.object(onenote._image_opener, "open", side_effect=lambda *a, **kw: io.BytesIO(data))


def no_requests():
    return patch.object(onenote._image_opener, "open", side_effect=AssertionError("a resource was fetched"))


def read_page(html, read_only=False):
    with patch.object(onenote, "graph_raw", return_value=(200, html)), \
            patch.object(onenote, "search_ticket", return_value=None), patch.object(onenote, "remember_search"), \
            patch.object(onenote, "remember_images"), \
            patch.object(onenote, "resource_read_only", return_value=read_only):
        return onenote.read_page("page-id")[0]


def cached(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


class RecordingTests(unittest.TestCase):
    def test_phone_object_is_playable_and_editable(self):
        cache = unittest.mock.Mock(return_value="file:///tmp/recording.3gp")
        result = onenote_md.html_to_markdown("<body>" + PHONE_OBJECT + "</body>", audio_path_for=cache)
        cache.assert_called_once_with(RESOURCE, "Audio Recording.3gp")
        self.assertEqual(result["body"], '<audio src="file:///tmp/recording.3gp" title="Audio Recording.3gp"></audio>')
        self.assertTrue(result["editable"])
        normalized = onenote.normalize_note(result)
        self.assertIn('data-id="nn-audio-', normalized["body"])
        self.assertEqual(onenote.normalize_note(normalized), normalized)

    def test_inline_recording_is_resolved_once_and_surrounding_text_survives(self):
        cache = unittest.mock.Mock(return_value="file:///tmp/voice.m4a")
        markup = '<body><p>Before <object type="audio/mp4" data="%s" data-attachment="Voice.m4a" /> after</p></body>' % RESOURCE
        result = onenote_md.html_to_markdown(markup, audio_path_for=cache)
        cache.assert_called_once()
        self.assertEqual(len(result["recordings"]), 1)
        self.assertTrue(result["body"].startswith("Before <audio"))
        self.assertTrue(result["body"].endswith("</audio> after"))

    def test_audio_element_and_nested_table_recording(self):
        markup = '<body><table><tr><td><p>Recording</p>%s</td></tr></table></body>' % PHONE_OBJECT
        result = onenote_md.html_to_markdown(markup, audio_path_for=lambda src, title: "file:///tmp/voice.3gp")
        self.assertEqual(len(result["recordings"]), 1)
        self.assertIn("<audio", result["body"])
        self.assertTrue(result["editable"])
        markup = '<body><audio title="Voice"><source src="%s" type="audio/ogg"></audio></body>' % RESOURCE
        result = onenote_md.html_to_markdown(markup, audio_path_for=lambda src, title: src)
        self.assertEqual(result["recordings"][0]["src"], RESOURCE)

    def test_attachment_without_a_resource_holds_the_page_read_only(self):
        result = onenote_md.html_to_markdown("<body>" + PHONE_OBJECT + "</body>")
        self.assertIn('<audio src=""', result["body"])
        self.assertFalse(result["editable"])

    def test_other_attachments_remain_unsupported(self):
        cache = unittest.mock.Mock()
        for mime, title in (("application/pdf", "Document.pdf"), ("video/mp4", "Video.mp4")):
            with self.subTest(mime=mime):
                markup = '<body><object type="%s" data-attachment="%s" data="%s" /></body>' % (mime, title, RESOURCE)
                result = onenote_md.html_to_markdown(markup, audio_path_for=cache)
                self.assertEqual(result["body"], "[unsupported: object]")
                self.assertFalse(result["editable"])
        cache.assert_not_called()


class PageTests(unittest.TestCase):
    def setUp(self):
        self.work, _ = private_cache(self)

    def test_opening_a_page_never_fetches_its_recordings(self):
        with no_requests():
            result = read_page("<body>" + PHONE_OBJECT + "</body>")
        self.assertTrue(result["editable"])
        self.assertEqual(result["reason"], "")
        expected = onenote_md.audio.markup(RESOURCE, "Audio Recording.3gp",
                                           "nn-audio-legacy-%s-1" % hashlib.sha256(RESOURCE.encode()).hexdigest())
        self.assertEqual(result["body"], expected)
        self.assertFalse(any(path.name != "index.json" for path in (self.work / "audio").glob("*")))

    def test_recording_ids_follow_the_resource_across_reads(self):
        page = "<body>" + PHONE_OBJECT + PHONE_OBJECT.replace(RESOURCE, COPY) + "</body>"
        with no_requests():
            first, second = read_page(page), read_page(page)
        self.assertEqual(first["body"], second["body"])
        self.assertEqual(onenote.normalize_note(first)["body"], first["body"])
        self.assertEqual(len({recording["id"] for recording in first["recordings"]}), 2)

    def test_shared_read_only_permission_still_applies_to_recordings(self):
        result = read_page("<body>" + PHONE_OBJECT + "</body>", read_only=True)
        self.assertFalse(result["editable"])
        self.assertEqual(result["reason"], onenote.READ_ONLY_REASON)


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.work, self.token = private_cache(self)

    def play(self, src, title="Audio Recording.3gp"):
        with patch.object(onenote, "out") as output:
            onenote.cmd_onenote_recording(src, title)
        return output.call_args.args[0]["url"]

    def test_playing_fetches_once_privately_and_authenticated(self):
        with responses(b"recording") as request:
            url = self.play(RESOURCE)
            again = self.play(RESOURCE)
        self.assertEqual(url, again)
        self.assertTrue(url.endswith(".3gp"))
        path = Path(onenote.file_path_of(url))
        self.assertEqual(path.read_bytes(), b"recording")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0].get_header("Authorization"), "Bearer test-token")

    def test_untrusted_sources_never_receive_a_request(self):
        sources = ("https://example.com/audio.3gp", "file:///etc/passwd",
                   RESOURCE + "?redirect=1", RESOURCE.replace("https:", "http:"))
        with no_requests(), patch.object(onenote, "fail", side_effect=SystemExit) as failure:
            for source in sources:
                with self.subTest(source=source):
                    self.assertIsNone(onenote.cached_audio(source, "Voice.3gp"))
                    with self.assertRaises(SystemExit):
                        onenote.cmd_onenote_recording(source, "Voice.3gp")
        self.assertIn("not a OneNote attachment", failure.call_args.args[0])
        self.token.assert_not_called()

    def test_oversize_empty_and_redirected_resources_are_not_cached(self):
        responses_ = (io.BytesIO(b"123456789"), io.BytesIO(b""),
                      urllib.error.HTTPError(RESOURCE, 302, "redirect", {}, None))
        for response in responses_:
            self.addCleanup(response.close)
            with self.subTest(response=response), patch.object(onenote, "MAX_AUDIO", 8), \
                    patch.object(onenote, "fail", side_effect=SystemExit) as failure:
                if isinstance(response, Exception):
                    context = patch.object(onenote._image_opener, "open", side_effect=response)
                else:
                    context = patch.object(onenote._image_opener, "open", return_value=response)
                with context, self.assertRaises(SystemExit):
                    onenote.cmd_onenote_recording(RESOURCE, "Voice.3gp")
                self.assertIn("could not be downloaded", failure.call_args.args[0])
                self.assertFalse((self.work / "audio").exists())

    def test_spent_budgets_still_serve_cached_resources(self):
        with responses(b"bytes"):
            recording = onenote.cached_audio(RESOURCE, "Voice.3gp")
            image = onenote.cached_image(IMAGE)
        spent = onenote.FetchBudget(seconds=45, requests=0)
        with patch.object(onenote, "_recording_budget", spent), patch.object(onenote, "_image_budget", spent), \
                no_requests():
            self.assertEqual(onenote.cached_audio(RESOURCE, "Voice.3gp"), recording)
            self.assertEqual(onenote.cached_image(IMAGE), image)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.work, _ = private_cache(self)
        cached(onenote.recording_cache_path(RESOURCE, "Voice.3gp"), b"audio bytes")
        self.recording = {"src": RESOURCE, "title": "Voice.3gp", "local": RESOURCE, "mime": "video/3gpp"}

    def test_retained_audio_uses_no_upload_bytes(self):
        uploads = onenote.Uploads(recordings=[self.recording])
        with no_requests():
            rendered = uploads.audio_ref(RESOURCE, "Voice.3gp")
            commands = uploads.materialize([{"target": "p:text", "action": "replace", "content": "<p>Edited</p>"}])
        self.assertEqual(onenote.onenote_patch.parse(rendered).children[0].attrs["data"], RESOURCE)
        self.assertEqual(uploads.parts, [])
        self.assertEqual(commands[0]["content"], "<p>Edited</p>")

    def test_recreated_audio_is_uploaded_with_mime_filename_and_marker(self):
        uploads = onenote.Uploads(recordings=[self.recording])
        content = uploads.audio_ref(RESOURCE, "Voice.3gp")
        with no_requests():
            commands = uploads.materialize([{"target": "object:voice", "action": "replace", "content": content}])
        self.assertEqual(len(uploads.parts), 1)
        name, mime, data = uploads.parts[0]
        self.assertEqual((mime, data), ("video/3gpp", b"audio bytes"))
        self.assertIn('data="name:' + name + '"', commands[0]["content"])
        self.assertIn('data-attachment="Voice.3gp"', commands[0]["content"])
        self.assertIn(next(iter(uploads.staged.values()))["dataId"], commands[0]["content"])
        content_type, body = onenote.multipart(commands, uploads.parts)
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertIn(b"Content-Type: video/3gpp", body)
        self.assertIn(b"audio bytes", body)

    def test_copy_of_a_recording_never_played_fetches_its_bytes_to_save(self):
        uploads = onenote.Uploads()
        with responses(b"copied bytes") as request:
            content = uploads.audio_ref(COPY, "Copy.3gp", "nn-audio-pasted")
        request.assert_called_once()
        self.assertIn('data-id="nn-audio-pasted"', content)
        self.assertEqual([(mime, data) for _, mime, data in uploads.parts], [("video/3gpp", b"copied bytes")])

    def test_oversized_audio_can_be_retained_but_cannot_be_reuploaded(self):
        with patch.object(onenote, "MAX_UPLOAD", 4):
            uploads = onenote.Uploads(recordings=[self.recording])
            content = uploads.audio_ref(RESOURCE, "Voice.3gp")
            self.assertFalse(uploads.error)
            uploads.materialize([{"target": "object:voice", "action": "replace", "content": content}])
        self.assertIn("recording is larger", uploads.error)
        self.assertEqual(uploads.parts, [])

    def test_unavailable_bytes_block_recreation(self):
        uploads = onenote.Uploads(recordings=[self.recording])
        content = uploads.audio_ref(RESOURCE, "Voice.3gp")
        os.remove(onenote.recording_cache_path(RESOURCE, "Voice.3gp"))
        with patch.object(onenote._image_opener, "open", side_effect=urllib.error.URLError("offline")):
            uploads.materialize([{"target": "object:voice", "action": "replace", "content": content}])
        self.assertIn("could not be downloaded", uploads.error)
        self.assertEqual(uploads.parts, [])

    def test_acknowledged_upload_becomes_the_copy_s_resource(self):
        uploads = onenote.Uploads(upload_known=True)
        content = uploads.render_uploads(uploads.audio_ref(RESOURCE, "Voice.3gp", "nn-audio-copy"))
        self.assertEqual(len(uploads.parts), 1)
        self.assertIn('data-id="nn-audio-copy"', content)
        remote = '<body><object data-id="nn-audio-copy" data="%s" type="video/3gpp" data-attachment="Voice.3gp"/></body>' % COPY
        onenote.remember_staged(uploads.staged, remote)
        self.assertEqual(onenote.known_recording(COPY), {"title": "Voice.3gp", "mime": "video/3gpp"})
        # The editor still names the copy by its original until the page
        # reloads; normalization finds its own resource under its ID.
        self.assertEqual(onenote.recording_identity().resolve(RESOURCE, "nn-audio-copy"), (COPY, "nn-audio-copy"))
        self.assertEqual(onenote.recording_identity().resolve(RESOURCE, "nn-audio-other"), (RESOURCE, "nn-audio-other"))

    def test_new_recording_uses_the_shared_upload_limits(self):
        uploads = onenote.Uploads(upload_known=True)
        uploads.audio_ref(RESOURCE, "Voice.3gp")
        with patch.object(onenote, "MAX_UPLOAD_PARTS", 1):
            uploads.audio_ref(RESOURCE, "Voice.3gp")
        self.assertEqual(len(uploads.parts), 1)
        self.assertIn("media files", uploads.error)

    def test_audio_that_is_not_a_onenote_resource_is_never_read_or_uploaded(self):
        # A crafted paste can name any URL, a private local file included.
        secret = self.work / "id_rsa"
        secret.write_bytes(b"private key")
        for url in (secret.as_uri(), "https://example.com/voice.3gp", RESOURCE + "?copy"):
            with self.subTest(url=url), no_requests():
                uploads = onenote.Uploads()
                self.assertEqual(uploads.audio_ref(url, "Voice.wav", "nn-audio-pasted"), "")
                self.assertIn("did not come from OneNote", uploads.error)
                self.assertEqual(uploads.parts, [])

    def test_retained_recording_is_recreated_only_from_its_resource(self):
        secret = self.work / "id_rsa"
        secret.write_bytes(b"private key")
        uploads = onenote.Uploads(recordings=[dict(self.recording, id="nn-audio-original")])
        content = uploads.audio_ref(secret.as_uri(), "Voice.3gp", "nn-audio-original")
        with no_requests():
            uploads.materialize([{"target": "object:voice", "action": "replace", "content": content}])
        self.assertIn("did not come from OneNote", uploads.error)
        self.assertEqual(uploads.parts, [])

    def test_instances_sharing_bytes_keep_separate_resource_references(self):
        original = dict(self.recording, id="nn-audio-original")
        copied = dict(self.recording, id="nn-audio-copy", src=COPY, local=COPY)
        uploads = onenote.Uploads(recordings=[original, copied])
        first = onenote.onenote_patch.parse(uploads.audio_ref(RESOURCE, "Voice.3gp", original["id"]))
        second = onenote.onenote_patch.parse(uploads.audio_ref(RESOURCE, "Voice.3gp", copied["id"]))
        self.assertEqual(first.children[0].attrs["data"], RESOURCE)
        self.assertEqual(second.children[0].attrs["data"], COPY)
        self.assertEqual(uploads.parts, [])


class IdentityTests(unittest.TestCase):
    def test_ids_follow_the_resource_and_its_occurrence(self):
        identity = onenote.RecordingIdentity()
        digest = hashlib.sha256(RESOURCE.encode()).hexdigest()
        self.assertEqual(identity.resolve(RESOURCE), (RESOURCE, "nn-audio-legacy-%s-1" % digest))
        self.assertEqual(identity.resolve(RESOURCE), (RESOURCE, "nn-audio-legacy-%s-2" % digest))
        self.assertEqual(identity.resolve(COPY, "nn-audio-pasted"), (COPY, "nn-audio-pasted"))
        self.assertNotEqual(identity.resolve(COPY)[1], identity.resolve(RESOURCE)[1])

    def test_normalization_reads_no_file_a_note_names(self):
        private_cache(self)
        note = {"title": "T", "body": '<audio src="file:///etc/passwd" title="Voice.wav"></audio>'}
        with patch.object(Path, "open", side_effect=AssertionError("a named file was opened")):
            body = onenote.normalize_note(note)["body"]
        self.assertIn('src="file:///etc/passwd"', body)

    def test_the_index_keeps_only_resources_and_instances(self):
        work, _ = private_cache(self)
        onenote.remember_recordings([{"src": RESOURCE, "title": "Voice.3gp", "mime": "video/3gpp",
                                      "local": RESOURCE, "id": "nn-audio-original"},
                                     {"src": "https://example.com/x.3gp", "title": "X", "mime": "", "local": "", "id": ""}])
        index = json.loads((work / "audio/index.json").read_text())
        self.assertEqual(index, {"resources": {RESOURCE: {"title": "Voice.3gp", "mime": "video/3gpp"}},
                                 "instances": {"nn-audio-original": RESOURCE}})


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        WORK.cleanup()
