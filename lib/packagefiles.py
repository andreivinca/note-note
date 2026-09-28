"""Bounded access to the files of one installed package.

A package names its files by paths relative to its own root. The walk uses
directory descriptors, so a symlink swapped in along the way never redirects
a read, and nothing outside the root is reachable.
"""
import os
from pathlib import Path, PurePosixPath
import stat
import time

from readfile import read_bytes

MAX_RESOURCE = 256 * 1024
READ_SECONDS = 5


def label(value, name, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\0" in value:
        raise ValueError("invalid " + name)
    return value


def resource_parts(relative):
    label(relative, "resource path", 512)
    parts = PurePosixPath(relative).parts
    if relative.startswith("/") or "\\" in relative or ":" in relative or ".." in parts or not parts:
        raise ValueError("resources must be relative paths inside their package")
    return parts


def open_resource(root, relative, follow_root=False):
    """An open descriptor on a regular file inside `root`.

    Only the root itself may be reached through a symlink, and only when the
    caller says so: that is how legacy providers were documented to install.
    """
    parts = resource_parts(relative)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    directory = os.open(root, flags if follow_root else flags | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            inner = os.open(part, flags | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = inner
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("resource is not a regular file")
        return fd
    finally:
        os.close(directory)


def resource_path(root, relative, follow_root=False):
    """Where a package's file is, once it is known to be one."""
    os.close(open_resource(root, relative, follow_root))
    return str(Path(root) / relative)


def read_resource(root, relative, cap=MAX_RESOURCE):
    with os.fdopen(open_resource(root, relative), "rb") as stream:
        before = os.fstat(stream.fileno())
        data = read_bytes(stream, cap + 1, time.monotonic() + READ_SECONDS)
        after = os.fstat(stream.fileno())
    if len(data) > cap:
        raise ValueError("resource exceeds the byte limit")
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError("resource changed while reading")
    return data.decode("utf-8")
