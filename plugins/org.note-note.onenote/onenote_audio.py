"""Stable instance IDs for the recordings of a note.

A note names each recording by its Graph resource, and its bytes are fetched
only when someone plays it, so identity never depends on the audio. An
attachment that Graph returns without a data-id is identified by its resource
and its occurrence on the page. A copy pasted in the editor keeps its
original's resource until a save uploads it; the upload's acknowledged
resource then replaces the original's under the copy's ID.
"""
import hashlib

import audio


class RecordingIdentity:
    """Instance IDs for the recordings of one note, assigned in document order."""

    def __init__(self, uploaded=None):
        self.uploaded = uploaded or {}       # instance ID -> its Graph resource
        self.occurrences = {}

    def resolve(self, source, identifier=""):
        """Return the recording's Graph resource and its stable instance ID."""
        if audio.valid_identifier(identifier):
            return self.uploaded.get(identifier, source), identifier
        digest = hashlib.sha256(source.encode()).hexdigest()
        count = self.occurrences.get(digest, 0) + 1
        self.occurrences[digest] = count
        return source, "nn-audio-legacy-%s-%d" % (digest, count)
