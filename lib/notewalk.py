"""The folder walk shared by the local provider's scripts (list.py,
search.py): the notes root itself, then each notebook — a non-hidden folder
right under it — followed by its sections, the folders inside it at any
depth, each level sorted by name. A symlinked folder is not ours and does not
appear — the same policy readfile.py applies to the files inside. The walk
goes MAX_DEPTH folders down at most and takes MAX_FOLDERS folders at most:
a tree deeper or larger is not a notes folder. Either way it says it stopped
short, since a listing that left folders out has not counted what is in
them, and must not offer to delete them."""
import os

MAX_DEPTH = 16
MAX_FOLDERS = 4096


def folder_keys(root):
    """(keys, cut). keys: "" first for the root, then every folder below it
    as its path from the root ("Work", "Work/Projects"), depth first; [] when
    root is unreadable. cut: "" when the walk took the whole tree, otherwise
    why it stopped short of it."""
    keys = [""]
    try:
        cut = _walk(root, "", 1, keys)
    except OSError:
        return [], ""
    return keys, cut


def _walk(root, key, depth, keys):
    """Adds the folders inside `key`, which sit `depth` down, to keys.
    Answers why it left some out, or ""."""
    path = os.path.join(root, key) if key else root
    with os.scandir(path) as it:
        names = sorted(e.name for e in it if not e.name.startswith(".") and e.is_dir(follow_symlinks=False))
    if names and depth > MAX_DEPTH:
        return "the notes folder holds folders more than %d deep" % MAX_DEPTH
    cut = ""
    for name in names:
        # keys holds the root as well as the folders.
        if len(keys) > MAX_FOLDERS:
            return "the notes folder holds more than %d folders" % MAX_FOLDERS
        child = key + "/" + name if key else name
        keys.append(child)
        try:
            cut = _walk(root, child, depth + 1, keys) or cut
        except OSError:
            # Listed all the same: reading its notes fails too, and the
            # listing says so for that folder.
            pass
    return cut
