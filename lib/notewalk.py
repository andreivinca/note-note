"""The folder walk shared by the local provider's scripts (list.py,
search.py): the notes root itself, then each notebook — a non-hidden folder
right under it — followed by its sections, the folders inside it at any
depth, each level sorted by name. A symlinked folder is not ours and does not
appear — the same policy readfile.py applies to the files inside. The walk
goes MAX_DEPTH folders down at most, and stops after MAX_FOLDERS folders:
a tree that large is not a notes folder."""
import os

MAX_DEPTH = 16
MAX_FOLDERS = 4096


def folder_keys(root):
    """Folder keys: "" first for the root, then every folder below it as its
    path from the root ("Work", "Work/Projects"), depth first; [] when root is
    unreadable. More than MAX_FOLDERS keys means the walk stopped short."""
    keys = [""]
    try:
        _walk(root, "", 1, keys)
    except OSError:
        return []
    return keys


def _walk(root, key, depth, keys):
    path = os.path.join(root, key) if key else root
    with os.scandir(path) as it:
        names = sorted(e.name for e in it if not e.name.startswith(".") and e.is_dir(follow_symlinks=False))
    for name in names:
        if len(keys) > MAX_FOLDERS:
            return
        child = key + "/" + name if key else name
        keys.append(child)
        if depth < MAX_DEPTH:
            try:
                _walk(root, child, depth + 1, keys)
            except OSError:
                # Listed all the same: reading its notes fails too, and the
                # listing says so for that folder.
                pass
