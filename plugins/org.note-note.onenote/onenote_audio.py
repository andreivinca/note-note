"""Stable recording instances backed by a shared, private playback cache.

Two attachment objects can contain identical audio. Their playback bytes may
be shared, but their editing identities and Graph resources must stay separate.
Legacy notes without instance IDs are normalized by content and occurrence so
old recovery drafts remain comparable with recordings already copied on Graph.
"""
import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import audio
import fileio


class RecordingIdentity:
    def __init__(self, directory, max_bytes, prune=None):
        self.directory = Path(directory)
        self.max_bytes = max_bytes
        self.occurrences = {}
        self.prune = prune

    def resolve(self, source, title, identifier=""):
        """Return the canonical playback URL and this object's stable ID."""
        try:
            parsed = urlsplit(source)
        except ValueError:
            parsed = urlsplit("")
        canonical = source
        digest = hashlib.sha256(source.encode()).hexdigest()
        if parsed.scheme == "file" and not parsed.netloc and parsed.path.startswith("/"):
            path = Path(unquote(parsed.path))
            if path.parent == self.directory and re.fullmatch(r"[a-f0-9]{64}", path.stem):
                digest = path.stem
            else:
                try:
                    with path.open("rb") as stream:
                        data = stream.read(self.max_bytes + 1)
                except OSError:
                    data = b""
                if data and len(data) <= self.max_bytes:
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = path.suffix.lower()
                    cached = self.directory / (digest + suffix)
                    self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if not cached.is_file():
                        fileio.write_atomic(str(cached), data, mode=0o600)
                        if self.prune:
                            self.prune()
                    canonical = cached.as_uri()
        if not audio.valid_identifier(identifier):
            count = self.occurrences.get(digest, 0) + 1
            self.occurrences[digest] = count
            identifier = "nn-audio-legacy-%s-%d" % (digest, count)
        return canonical, identifier
