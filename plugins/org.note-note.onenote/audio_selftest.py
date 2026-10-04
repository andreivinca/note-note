"""OneNote recordings: conversion, authenticated cache and media uploads."""
import contextlib
import io
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
PHONE_OBJECT = '<object data-attachment="Audio Recording.3gp" type="video/3gpp" data="%s" />' % RESOURCE


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

    def test_inline_recording_is_fetched_once_and_surrounding_text_survives(self):
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

    def test_failed_download_keeps_an_unavailable_player_and_save_hold(self):
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

    def test_page_load_allows_editing_with_playable_audio(self):
        with patch.object(onenote, "graph_raw", return_value=(200, "<body>" + PHONE_OBJECT + "</body>")), \
                patch.object(onenote, "cached_audio", return_value="file:///tmp/voice.3gp"), \
                patch.object(onenote, "search_ticket", return_value=None), \
                patch.object(onenote, "remember_search"), patch.object(onenote, "remember_recordings"), \
                patch.object(onenote, "remember_images") as images, \
                patch.object(onenote, "resource_read_only", return_value=False):
            result, html = onenote.read_page("page-id")
        self.assertTrue(result["editable"])
        self.assertNotIn("reason", result)
        images.assert_called_once_with("page-id", [], True)
        self.assertIn(PHONE_OBJECT, html)

    def test_shared_read_only_permission_still_applies_to_recordings(self):
        with patch.object(onenote, "graph_raw", return_value=(200, "<body>" + PHONE_OBJECT + "</body>")), \
                patch.object(onenote, "cached_audio", return_value="file:///tmp/voice.3gp"), \
                patch.object(onenote, "search_ticket", return_value=None), \
                patch.object(onenote, "remember_search"), patch.object(onenote, "remember_recordings"), \
                patch.object(onenote, "remember_images"), patch.object(onenote, "resource_read_only", return_value=True):
            result, _ = onenote.read_page("page-id")
        self.assertFalse(result["editable"])
        self.assertEqual(result["reason"], onenote.READ_ONLY_REASON)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=WORK.name)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "Voice.3gp"
        self.path.write_bytes(b"audio bytes")
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(onenote, "AUDIO_INDEX", str(Path(self.directory.name) / "index.json")))
        self.recording = {"src": RESOURCE, "title": "Voice.3gp", "local": self.path.as_uri(), "mime": "video/3gpp"}

    def test_retained_audio_uses_no_upload_bytes(self):
        uploads = onenote.Uploads(recordings=[self.recording])
        rendered = uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
        self.assertEqual(onenote.onenote_patch.parse(rendered).children[0].attrs["data"], RESOURCE)
        commands = uploads.materialize([{"target": "p:text", "action": "replace", "content": "<p>Edited</p>"}])
        self.assertEqual(uploads.parts, [])
        self.assertEqual(commands[0]["content"], "<p>Edited</p>")

    def test_recreated_audio_is_uploaded_with_mime_filename_and_marker(self):
        uploads = onenote.Uploads(recordings=[self.recording])
        content = uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
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

    def test_oversized_audio_can_be_retained_but_cannot_be_reuploaded(self):
        with patch.object(onenote, "MAX_UPLOAD", 4):
            uploads = onenote.Uploads(recordings=[self.recording])
            content = uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
            self.assertFalse(uploads.error)
            uploads.materialize([{"target": "object:voice", "action": "replace", "content": content}])
        self.assertIn("recording is larger", uploads.error)
        self.assertEqual(uploads.parts, [])

    def test_missing_audio_bytes_block_recreation(self):
        uploads = onenote.Uploads(recordings=[self.recording])
        content = uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
        self.path.unlink()
        uploads.materialize([{"target": "object:voice", "action": "replace", "content": content}])
        self.assertIn("could not be read", uploads.error)
        self.assertEqual(uploads.parts, [])

    def test_audio_upload_aliases_follow_unique_markers(self):
        uploads = onenote.Uploads(upload_known=True)
        content = uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
        content = uploads.render_uploads(content)
        self.assertEqual(len(uploads.parts), 1)
        upload = next(iter(uploads.staged.values()))
        remote = '<body><object data-id="%s" data="%s" type="video/3gpp" data-attachment="Voice.3gp"/></body>' % (
            upload["dataId"], RESOURCE)
        onenote.remember_staged(uploads.staged, remote)
        known = onenote.known_recording(self.path.as_uri())
        self.assertEqual(known, {"src": RESOURCE, "title": "Voice.3gp", "mime": "video/3gpp", "local": self.path.as_uri()})

    def test_new_recording_uses_the_shared_upload_limits(self):
        uploads = onenote.Uploads(upload_known=True)
        uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
        with patch.object(onenote, "MAX_UPLOAD_PARTS", 1):
            uploads.audio_ref(self.path.as_uri(), "Voice.3gp")
        self.assertEqual(len(uploads.parts), 1)
        self.assertIn("media files", uploads.error)

    def test_remote_audio_cannot_be_uploaded_as_a_public_url(self):
        uploads = onenote.Uploads()
        self.assertEqual(uploads.audio_ref("https://example.com/voice.3gp", "Voice.3gp"), "")
        self.assertIn("local audio file", uploads.error)
        self.assertEqual(uploads.parts, [])

    def test_instances_sharing_bytes_keep_separate_resource_references(self):
        original = dict(self.recording, id="nn-audio-original")
        copied = dict(self.recording, id="nn-audio-copy", src=RESOURCE.replace("audio-id", "copy-id"))
        onenote.remember_recordings([original, copied])
        uploads = onenote.Uploads(recordings=[original, copied])
        first = onenote.onenote_patch.parse(uploads.audio_ref(self.path.as_uri(), "Voice.3gp", original["id"]))
        second = onenote.onenote_patch.parse(uploads.audio_ref(self.path.as_uri(), "Voice.3gp", copied["id"]))
        self.assertEqual(first.children[0].attrs["data"], original["src"])
        self.assertEqual(second.children[0].attrs["data"], copied["src"])
        self.assertEqual(uploads.parts, [])


class IdentityTests(unittest.TestCase):
    def test_legacy_references_to_identical_bytes_share_playback_but_not_identity(self):
        with tempfile.TemporaryDirectory(dir=WORK.name) as directory:
            work = Path(directory)
            original, copy = work / "original.3gp", work / "copy.3gp"
            original.write_bytes(b"same audio")
            copy.write_bytes(b"same audio")
            identity = onenote.RecordingIdentity(work / "cache", 100)
            first, first_id = identity.resolve(original.as_uri(), "Recording.3gp")
            second, second_id = identity.resolve(copy.as_uri(), "Recording.3gp")
            self.assertEqual(first, second)
            self.assertNotEqual(first_id, second_id)
            self.assertEqual(Path(onenote.file_path_of(first)).stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(onenote.file_path_of(first)).read_bytes(), b"same audio")
            self.assertEqual(onenote.RecordingIdentity(work / "cache", 100).resolve(first, "Recording.3gp"),
                             (first, first_id))

    def test_pasted_instance_id_survives_and_does_not_renumber_legacy_original(self):
        with tempfile.TemporaryDirectory(dir=WORK.name) as directory:
            work = Path(directory)
            path = work / "voice.3gp"
            path.write_bytes(b"audio")
            identity = onenote.RecordingIdentity(work / "cache", 100)
            source, pasted_id = identity.resolve(path.as_uri(), "Voice.3gp", "nn-audio-pasted")
            _, original_id = identity.resolve(path.as_uri(), "Voice.3gp")
            expected = onenote.RecordingIdentity(work / "cache", 100).resolve(path.as_uri(), "Voice.3gp")
            self.assertEqual(pasted_id, "nn-audio-pasted")
            self.assertEqual((source, original_id), expected)

    def test_identity_normalization_never_reads_unbounded_audio(self):
        with tempfile.TemporaryDirectory(dir=WORK.name) as directory:
            work = Path(directory)
            path = work / "voice.3gp"
            path.write_bytes(b"too much audio")
            source, identifier = onenote.RecordingIdentity(work / "cache", 4).resolve(path.as_uri(), "Voice.3gp")
            self.assertEqual(source, path.as_uri())
            self.assertTrue(onenote.onenote_md.audio.valid_identifier(identifier))
            self.assertFalse((work / "cache").exists())


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=WORK.name)
        self.addCleanup(self.directory.cleanup)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(onenote, "ONENOTE_AUDIO_DIR", self.directory.name))
        self.stack.enter_context(patch.object(onenote, "_page_resource_budget", [0.0, 0]))
        self.stack.enter_context(patch.object(onenote.ratelimit, "slot", side_effect=lambda *a, **kw: contextlib.nullcontext()))
        self.token = self.stack.enter_context(patch.object(onenote, "access_token", return_value="test-token"))

    def test_download_is_private_authenticated_and_reused(self):
        with patch.object(onenote._image_opener, "open", return_value=io.BytesIO(b"recording")) as request:
            url = onenote.cached_audio(RESOURCE, "Audio Recording.3gp")
            cached = onenote.cached_audio(RESOURCE, "Audio Recording.3gp")
        self.assertEqual(url, cached)
        self.assertTrue(url.endswith(".3gp"))
        path = Path(onenote.file_path_of(url))
        self.assertEqual(path.read_bytes(), b"recording")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0].get_header("Authorization"), "Bearer test-token")
        self.token.assert_called_once()

    def test_untrusted_sources_never_receive_a_request(self):
        sources = ("https://example.com/audio.3gp", "file:///etc/passwd",
                   RESOURCE + "?redirect=1", RESOURCE.replace("https:", "http:"))
        with patch.object(onenote._image_opener, "open") as request:
            for source in sources:
                self.assertIsNone(onenote.cached_audio(source, "Voice.3gp"))
        request.assert_not_called()
        self.token.assert_not_called()

    def test_oversize_empty_and_redirected_resources_are_not_cached(self):
        responses = (io.BytesIO(b"123456789"), io.BytesIO(b""),
                     urllib.error.HTTPError(RESOURCE, 302, "redirect", {}, None))
        for response in responses:
            self.addCleanup(response.close)
            with self.subTest(response=response), patch.object(onenote, "MAX_AUDIO", 8):
                if isinstance(response, Exception):
                    context = patch.object(onenote._image_opener, "open", side_effect=response)
                else:
                    context = patch.object(onenote._image_opener, "open", return_value=response)
                with context:
                    self.assertIsNone(onenote.cached_audio(RESOURCE, "Voice.3gp"))
                self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_recordings_share_the_page_request_budget(self):
        with patch.object(onenote, "MAX_PAGE_RESOURCES", 1), \
                patch.object(onenote._image_opener, "open", return_value=io.BytesIO(b"recording")) as request:
            self.assertIsNotNone(onenote.cached_audio(RESOURCE, "Voice.3gp"))
            self.assertIsNone(onenote.cached_audio(RESOURCE.replace("audio-id", "other-id"), "Other.3gp"))
        request.assert_called_once()


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        WORK.cleanup()
