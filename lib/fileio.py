"""The one atomic file writer: local notes, host settings, private caches
and tokens (provider_io.save_private), rate state (ratelimit) and cached
images all commit a file through write_atomic."""
import json
import os
import stat
import sys
import tempfile

MAX_PAYLOAD = 8 * 1024 * 1024


def write_atomic(path, data, exclusive=False, mode=None):
    """Commit a complete file, text or bytes: a fresh O_EXCL temporary beside
    it (mkstemp: 0600, never an existing path or a symlink), the data
    fsynced, then one rename onto the target — which must be a regular file
    or absent, never a link to be written through. `mode` None keeps an
    existing file's permissions and gives a new one 0600; a mode given is
    applied whatever the file had, which is how a private file stays
    private. Answers the file's version (its mtime)."""
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        current = None
    if current is not None and not stat.S_ISREG(current.st_mode):
        raise OSError("destination is not a regular file")
    if mode is None:
        mode = stat.S_IMODE(current.st_mode) if current is not None else 0o600
    directory = os.path.dirname(os.path.abspath(path))
    fd, temporary = tempfile.mkstemp(prefix='.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data.encode('utf-8') if isinstance(data, str) else data)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        return str(os.stat(path, follow_symlinks=False).st_mtime_ns)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD + 1)
        if len(raw) > MAX_PAYLOAD:
            raise ValueError('file payload is too large')
        payload = json.loads(raw)
        path = payload['path']
        if payload.get('parents'):
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        version = write_atomic(path, payload['text'])
        result = {'ok': True, 'version': version}
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'error': str(error)}
    json.dump(result, sys.stdout)
    return 1 if result.get('error') else 0


if __name__ == '__main__':
    sys.exit(main())
