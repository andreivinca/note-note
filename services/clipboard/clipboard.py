"""A pasted picture, staged where the editor can show it.

    python3 clipboard.py stage <dir>  <- {"mime": …, "data": <base64>} on stdin
                                      -> {"path": …, "mime": …, "bytes": n}
                                         (a scaled picture: a .png, image/png)

The bytes come from the host's own clipboard reader (QClipboard in the
native host, wl-paste in the Omarchy host — hosts/omarchy/clipboard.py);
the policy is here, once, for both: only supported image types are
accepted, an image too large for the backends is scaled down rather than
refused — a pasted screenshot is usually far bigger than anything a note
needs — and the staged files are pruned.
"""
import json
import base64
import binascii
import os
import shutil
import subprocess
import sys
import time
import tempfile

# What a backend will accept from us, and what a paste may cost on the way in.
MIME_SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
               "image/bmp": ".bmp", "image/tiff": ".tiff"}
SCALED_MIME = "image/png"            # what a picture scaled down becomes
MAX_CLIPBOARD = 40 * 1024 * 1024     # what we will read at all
MAX_IMAGE_ANSWER = 56 * 1024 * 1024  # MAX_CLIPBOARD as base64 (x4/3) in its JSON envelope: a reader's largest answer
MAX_TEXT = 4 * 1024 * 1024           # a paste of text past this is not a note
MAX_STAGED = 40                      # pasted files kept before the oldest go
MAX_STAGED_AGE = 7 * 24 * 3600       # a paste that never reached a backend
MAX_STORED = 3 * 1024 * 1024         # what fits in one Graph request
MAX_WIDTH = 1600                     # a screenshot is wider than any note needs
MAGICK_TIMEOUT = 10


def out(obj):
    sys.stdout.write(json.dumps(obj))


def scaled(path, mime, magick):
    """Bring a pasted screenshot down to something a note can carry.

    Returns the staged picture as (path, mime). A scaled one is a PNG, in a
    file of its own named for it, staged like the paste itself; the original
    goes. A name never says one format while the bytes are another: a
    backend that reads the type from the name (OneNote) uploads it as what
    it is.
    """
    if os.path.getsize(path) <= MAX_STORED or not magick:
        return path, mime
    fd, scaled_path = tempfile.mkstemp(prefix="paste-", suffix=MIME_SUFFIX[SCALED_MIME], dir=os.path.dirname(path))
    os.close(fd)
    if converted(magick, path, scaled_path):
        discard(path)
        return scaled_path, SCALED_MIME
    discard(scaled_path)
    return path, mime


def converted(magick, source, target):
    """Have ImageMagick write the source's first frame, scaled, into target
    as a PNG; True when that came out smaller than the source."""
    try:
        subprocess.run([magick, "-limit", "memory", "128MiB", "-limit", "map", "256MiB",
                        "-limit", "area", "50MP", "-limit", "time", str(MAGICK_TIMEOUT),
                        source + "[0]", "-resize", "%dx>" % MAX_WIDTH, "png:" + target],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=MAGICK_TIMEOUT + 5)
        if not 0 < os.path.getsize(target) < os.path.getsize(source):
            return False
        os.chmod(target, 0o600)
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def discard(path):
    try:
        os.remove(path)
    except OSError:
        pass


def prune(directory):
    """A paste is staged only until the backend has it; old ones are ours to
    clear, and the directory must not grow without limit."""
    try:
        names = [n for n in os.listdir(directory) if n.startswith("paste-")]
    except OSError:
        return
    now = time.time()
    files = []
    for name in names:
        path = os.path.join(directory, name)
        try:
            files.append((os.stat(path).st_mtime, path))
        except OSError:
            continue
    files.sort(reverse=True)
    for index, (mtime, path) in enumerate(files):
        if index >= MAX_STAGED or now - mtime > MAX_STAGED_AGE:
            discard(path)


def stage_image(directory, mime, data):
    """The staging policy both hosts' clipboards go through."""
    if mime not in MIME_SUFFIX:
        return {"error": "unsupported clipboard image type"}
    if not data:
        return {"error": "the clipboard image was empty"}
    if len(data) > MAX_CLIPBOARD:
        return {"error": "the clipboard image is too large"}
    # Owner-only, and never through a path someone else could have replaced.
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="paste-", suffix=MIME_SUFFIX[mime], dir=directory)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    path, mime = scaled(path, mime, shutil.which("magick") or shutil.which("convert"))
    prune(directory)
    return {"path": path, "mime": mime, "bytes": os.path.getsize(path)}


def image_from_stdin(directory):
    raw = sys.stdin.buffer.read(MAX_IMAGE_ANSWER + 1)
    if len(raw) > MAX_IMAGE_ANSWER:
        return {"error": "the clipboard image is too large"}
    try:
        payload = json.loads(raw)
        mime = payload["mime"]
        data = base64.b64decode(payload["data"], validate=True)
    except (ValueError, TypeError, KeyError, binascii.Error):
        return {"error": "invalid clipboard image"}
    return stage_image(directory, mime, data)


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "stage" and len(argv) >= 3:
        out(image_from_stdin(argv[2]))
    else:
        out({"error": "usage: clipboard.py stage <dir>"})
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
