"""Read section positions from OneDrive's packaged .onetoc2 metadata.

HIGH-RISK WORKAROUND: custom partial binary parser supporting section_order.py,
not an official section-order SDK. The underlying file formats are documented,
but this reader supports only a subset and the cloud download representation
is not guaranteed to remain compatible. Unknown encodings must be rejected,
not guessed. See docs/onenote-section-order.md before extending this reader.

Only the TOC's active object space is materialized. Older revisions provide
inherited objects, but cannot overwrite current ones. This is a bounded
reader for MS-ONESTORE 2.7/2.8 and MS-FSSHTTPB stream objects, not a reader
for page content or arbitrary desktop .one files.
"""
import struct
import uuid
from dataclasses import dataclass

MAX_BYTES = 512 * 1024
MAX_ITEMS = 8192
MAX_DEPTH = 32
NIL = (bytes(16), 0)
PACKAGING_FORMAT = uuid.UUID("638de92f-a6d4-4bc1-9a36-b3fc2511a5b7").bytes_le
DESKTOP_FORMAT = uuid.UUID("109add3f-911b-49f5-a5d0-1791edc8aed8").bytes_le
TOC_SCHEMA = uuid.UUID("e4dbfd38-e5c7-408b-a8a1-0e7b421e1f5f").bytes_le
DATA_ROOT = (uuid.UUID("84defab9-aaa3-4a0d-a3a8-520c77ac7073").bytes_le, 2)
CONTENT_ROOT = (uuid.UUID("4a3717f8-1c14-49e7-9526-81d942de1741").bytes_le, 1)
# Stream object types (MS-FSSHTTPB 2.2.1.5), as the packaging uses them.
PACKAGING = 0x7A                              # MS-ONESTORE 2.8.1, the 32-bit start of the package
DATA_ELEMENT_PACKAGE = 0x15
DATA_ELEMENT = 0x01
STORAGE_INDEX_MANIFEST_MAPPING = 0x11
STORAGE_INDEX_CELL_MAPPING = 0x0E
STORAGE_INDEX_REVISION_MAPPING = 0x0D
STORAGE_MANIFEST_ROOT_DECLARE = 0x07
CELL_MANIFEST_CURRENT_REVISION = 0x0B
REVISION_MANIFEST = 0x1A
REVISION_MANIFEST_ROOT_DECLARE = 0x0A
REVISION_MANIFEST_OBJECT_GROUP_REFERENCES = 0x19
OBJECT_GROUP_DECLARATIONS = 0x1D
OBJECT_GROUP_DATA = 0x1E
OBJECT_GROUP_OBJECT_DECLARE = 0x18
OBJECT_GROUP_OBJECT_DATA = 0x16
# Stream object header types, the low two bits of a header (MS-FSSHTTPB
# 2.2.1.5): a 16-bit or a 32-bit start, an 8-bit or a 16-bit end. A start
# whose COMPOUND bit is set holds children up to its end.
START_16, END_8, START_32, END_16 = 0, 1, 2, 3
COMPOUND = 4
LARGE_LENGTH = 0x7FFF                         # a 32-bit start whose length follows as a compact integer
# Data element types (MS-FSSHTTPB 2.2.1.12).
STORAGE_INDEX_ELEMENT = 1
STORAGE_MANIFEST_ELEMENT = 2
CELL_MANIFEST_ELEMENT = 3
REVISION_MANIFEST_ELEMENT = 4
OBJECT_GROUP_ELEMENT = 5
# An object's partitions in its group (MS-ONESTORE 2.7): its property set,
# and the metadata that says which kind of object it is.
OBJECT_DATA_PARTITION = 1
OBJECT_METADATA_PARTITION = 4
TOC_SECTION_JCID = struct.pack("<I", 0x00020001)   # jcidPersistablePropertyContainerForTOCSection (MS-ONE 2.1.15)
# ObjectSpaceObjectStreamHeader (MS-ONESTORE 2.6.2): a 24-bit count, and
# two flags saying which optional streams follow.
STREAM_COUNT_MASK = 0xFFFFFF
EXTENDED_STREAMS_PRESENT = 0x40000000
OSID_STREAM_NOT_PRESENT = 0x80000000
# PropertyID (MS-ONE 2.6.6): the identifier and its type in the low 31
# bits, a boolean's value in the top one.
PROPERTY_ID_MASK = 0x7FFFFFFF
PROPERTY_BOOL_VALUE = 0x80000000
PROPERTY_TYPE_SHIFT = 26
PROPERTY_TYPE_MASK = 0x1F
# Property types (MS-ONE 2.6.6), the ones a TOC uses.
NO_DATA, BOOL, ONE_BYTE, TWO_BYTES, FOUR_BYTES, EIGHT_BYTES, SIZED_DATA, OBJECT_ID, OBJECT_ID_ARRAY = range(1, 10)
# The TOC's properties (MS-ONE 2.3), type bits included.
CHILDREN = 0x24001CF6                        # ElementChildNodes
FILENAME = 0x1C001D6B                        # FolderChildFilename
ORDER = 0x14001CB9                           # NotebookElementOrderingID
IDENTITY = 0x1C001D94                        # FileIdentityGuid


class InvalidToc(ValueError):
    """Unsupported or malformed notebook metadata; never guess its order."""


def require(condition, message):
    if not condition:
        raise InvalidToc(message)


def bounded_count(count):
    require(0 <= count <= MAX_ITEMS, "TOC collection exceeds its limit")
    return count


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, size):
        end = self.pos + size
        require(size >= 0 and end <= len(self.data), "truncated TOC metadata")
        value = self.data[self.pos:end]
        self.pos = end
        return value

    def integer(self, size):
        return int.from_bytes(self.take(size), "little")

    def peek(self):
        require(self.pos < len(self.data), "missing TOC stream terminator")
        return self.data[self.pos]

    def finish(self):
        require(self.pos == len(self.data), "unexpected TOC object data")

    def compact(self):
        first = self.peek()
        if first == 0:
            self.take(1)
            return 0
        width = (first & -first).bit_length()
        if width == 8:
            self.take(1)
            return self.integer(8)
        return self.integer(width) >> width

    def exguid(self):
        """An Extended GUID (MS-FSSHTTPB 2.2.1.7): nil, or a GUID and a value
        packed as 5, 10, 17 or 32 bits behind the encoding's marker."""
        first = self.integer(1)
        if first == 0:
            return NIL
        if first & 7 == 4:
            value = first >> 3
        elif first & 63 == 32:
            value = (self.integer(1) << 2) | (first >> 6)
        elif first & 127 == 64:
            value = (self.integer(2) << 1) | (first >> 7)
        elif first == 128:
            value = self.integer(4)
        else:
            raise InvalidToc("invalid extended GUID")
        return self.take(16), value

    def serial(self):
        """A Serial Number (MS-FSSHTTPB 2.2.1.9): none, or a GUID and a
        64-bit value the reader has no use for."""
        kind = self.integer(1)
        require(kind in (0, 128), "invalid serial number")
        if kind:
            self.take(24)


@dataclass
class Node:
    tag: int
    data: bytes
    children: list

    def one(self, tag):
        matches = [child for child in self.children if child.tag == tag]
        require(len(matches) == 1, "missing or duplicate TOC stream object %x" % tag)
        return matches[0]


def stream(reader, budget, depth=0):
    require(depth <= MAX_DEPTH and budget[0] > 0, "TOC stream exceeds its limit")
    budget[0] -= 1
    # Behind the header type and the compound bit, a 16-bit start holds a
    # 6-bit type and a 7-bit length, a 32-bit start a 14-bit type and a
    # 15-bit length; an end holds the type alone.
    kind = reader.peek() & 3
    if kind == START_16:
        header = reader.integer(2)
        tag, size = (header >> 3) & 0x3F, header >> 9
    elif kind == START_32:
        header = reader.integer(4)
        tag, size = (header >> 3) & 0x3FFF, header >> 17
        if size == LARGE_LENGTH:
            size = reader.compact()
    else:
        raise InvalidToc("unexpected TOC stream end")
    node = Node(tag, reader.take(size), [])
    if header & COMPOUND:
        while reader.peek() & 3 in (START_16, START_32):
            node.children.append(stream(reader, budget, depth + 1))
        end = reader.integer(1 if reader.peek() & 3 == END_8 else 2) >> 2
        require(end == tag, "mismatched TOC stream end")
    return node


def package(data):
    require(68 <= len(data) <= MAX_BYTES, "invalid TOC file size")
    reader = Reader(data)
    if data[48:64] == DESKTOP_FORMAT:
        # Modern downloads wrap the package in a desktop header. The package
        # follows the transaction log; validate the pointer and format instead
        # of searching the binary for a signature that could occur in data.
        require(len(data) >= 1024 and data[32:48] == bytes(16), "unsupported desktop TOC format")
        start, size = struct.unpack_from("<QI", data, 160)
        require(start >= 1024 and start + size <= len(data) - 68, "invalid TOC transaction log")
        reader.take(start + size)
    header = reader.take(68)
    require(header[48:64] == PACKAGING_FORMAT and header[64:] == bytes(4), "unsupported TOC package format")
    root = stream(reader, [MAX_ITEMS])
    require(root.tag == PACKAGING, "missing TOC package")
    require(not any(reader.take(len(data) - reader.pos)), "unexpected data after TOC package")
    info = Reader(root.data)
    index_id = info.exguid()
    require(info.take(16) == TOC_SCHEMA, "file is not a notebook table of contents")
    info.finish()
    elements = {}
    container = root.one(DATA_ELEMENT_PACKAGE)
    require(container.data == b"\0", "invalid TOC package padding")
    for node in container.children:
        require(node.tag == DATA_ELEMENT, "invalid TOC data element")
        info = Reader(node.data)
        key = info.exguid()
        info.serial()
        kind = info.compact()
        info.finish()
        require(key not in elements, "duplicate TOC data element")
        elements[key] = (kind, node)
    return index_id, elements


class Store:
    def __init__(self, data):
        index_id, self.elements = package(data)
        index = self.element(index_id, STORAGE_INDEX_ELEMENT)
        self.revisions = {}
        self.cells = {}
        manifests = []
        for node in index.children:
            reader = Reader(node.data)
            if node.tag == STORAGE_INDEX_MANIFEST_MAPPING:
                manifests.append(reader.exguid())
            elif node.tag == STORAGE_INDEX_REVISION_MAPPING:
                key, value = reader.exguid(), reader.exguid()
                self.revisions[key] = value
            elif node.tag == STORAGE_INDEX_CELL_MAPPING:
                cell = reader.exguid(), reader.exguid()
                self.cells[cell] = reader.exguid()
            else:
                raise InvalidToc("unsupported TOC storage index entry")
            reader.serial()
            reader.finish()
        require(len(manifests) == 1, "expected one TOC storage manifest")
        manifest = self.element(manifests[0], STORAGE_MANIFEST_ELEMENT)
        roots = {}
        for node in manifest.children:
            if node.tag == STORAGE_MANIFEST_ROOT_DECLARE:
                reader = Reader(node.data)
                key = reader.exguid()
                roots[key] = reader.exguid(), reader.exguid()
                reader.finish()
        require(DATA_ROOT in roots and roots[DATA_ROOT] in self.cells, "missing TOC data root")
        cell = self.element(self.cells[roots[DATA_ROOT]], CELL_MANIFEST_ELEMENT).one(CELL_MANIFEST_CURRENT_REVISION)
        reader = Reader(cell.data)
        revision = reader.exguid()
        reader.finish()
        self.objects = {}
        self.root = None
        visited = set()
        while revision != NIL:
            require(revision not in visited, "cyclic TOC revision chain")
            visited.add(revision)
            bounded_count(len(visited))
            node = self.element(self.revisions.get(revision, revision), REVISION_MANIFEST_ELEMENT)
            header = Reader(node.one(REVISION_MANIFEST).data)
            require(header.exguid() == revision, "TOC revision identity mismatch")
            revision = header.exguid()
            header.finish()
            for child in node.children:
                reader = Reader(child.data)
                if child.tag == REVISION_MANIFEST_ROOT_DECLARE:
                    role, object_id = reader.exguid(), reader.exguid()
                    reader.finish()
                    if role == CONTENT_ROOT and self.root is None:
                        self.root = object_id
                elif child.tag == REVISION_MANIFEST_OBJECT_GROUP_REFERENCES:
                    group_id = reader.exguid()
                    reader.finish()
                    self.add_group(self.element(group_id, OBJECT_GROUP_ELEMENT))
        require(self.root in self.objects, "missing TOC content root")

    def element(self, key, expected):
        require(key in self.elements, "missing referenced TOC element")
        kind, node = self.elements[key]
        require(kind == expected, "unexpected TOC element type")
        return node

    def add_group(self, group):
        declarations = group.one(OBJECT_GROUP_DECLARATIONS).children
        values = group.one(OBJECT_GROUP_DATA).children
        require(len(declarations) == len(values), "TOC declaration/data count mismatch")
        partitions = {}
        for declaration, value in zip(declarations, values):
            require(declaration.tag == OBJECT_GROUP_OBJECT_DECLARE and value.tag == OBJECT_GROUP_OBJECT_DATA,
                    "unsupported TOC object encoding")
            reader = Reader(declaration.data)
            key, partition = reader.exguid(), reader.compact()
            size, ref_count, cell_count = reader.compact(), reader.compact(), reader.compact()
            reader.finish()
            reader = Reader(value.data)
            references = [reader.exguid() for _ in range(bounded_count(reader.compact()))]
            count = bounded_count(reader.compact())
            require(count == cell_count == 0, "unexpected cross-cell reference in TOC")
            payload = reader.take(reader.compact())
            reader.finish()
            require(size == len(payload) and ref_count == len(references), "TOC object size/count mismatch")
            require((key, partition) not in partitions, "duplicate TOC object partition")
            partitions[key, partition] = payload, references
        for (key, partition), (payload, references) in partitions.items():
            if partition != OBJECT_DATA_PARTITION or key in self.objects:
                continue
            metadata = partitions.get((key, OBJECT_METADATA_PARTITION))
            require(metadata and metadata[0] == TOC_SECTION_JCID, "invalid TOC property container")
            self.objects[key] = properties(payload, references)
            bounded_count(len(self.objects))

    def entries(self):
        pending = [(self.root, frozenset())]
        entries = {}
        visits = 0
        while pending:
            key, ancestors = pending.pop()
            visits += 1
            bounded_count(visits)
            require(key not in ancestors and len(ancestors) <= MAX_DEPTH, "cyclic or deeply nested TOC entries")
            require(key in self.objects, "missing TOC child")
            value = self.objects[key]
            if FILENAME in value:
                require(ORDER in value, "section has no ordering ID")
                name = value[FILENAME].decode("utf-16-le").rstrip("\0")
                require(name and "\0" not in name, "invalid TOC filename")
                # OneNote escapes these two characters in TOC filenames.
                name = name.replace("^M", "+").replace("^J", ",")
                identity = value.get(IDENTITY)
                require(isinstance(identity, bytes) and len(identity) == 16, "invalid TOC file identity")
                # The root can retain earlier entries for a filename; the last
                # reference is authoritative, even when an older order is lower.
                entries[name] = {"name": name, "order": value[ORDER], "identity": str(uuid.UUID(bytes_le=identity))}
            else:
                for child in reversed(value.get(CHILDREN, [])):
                    pending.append((child, ancestors | {key}))
        return sorted(entries.values(), key=lambda entry: entry["order"])


def properties(payload, references):
    reader = Reader(payload)
    header = reader.integer(4)
    count = bounded_count(header & STREAM_COUNT_MASK)
    reader.take(4 * count)
    require(count == len(references), "TOC object reference count mismatch")
    if not header & OSID_STREAM_NOT_PRESENT:
        extra = reader.integer(4)
        require(extra & STREAM_COUNT_MASK == 0, "unexpected TOC object-space stream")
        if extra & EXTENDED_STREAMS_PRESENT:
            require(reader.integer(4) & STREAM_COUNT_MASK == 0, "unexpected TOC context stream")
    ids = [reader.integer(4) for _ in range(bounded_count(reader.integer(2)))]
    result = {}
    ref_offset = 0
    for prop in ids:
        kind = (prop >> PROPERTY_TYPE_SHIFT) & PROPERTY_TYPE_MASK
        if kind == NO_DATA:
            value = None
        elif kind == BOOL:
            value = bool(prop & PROPERTY_BOOL_VALUE)
        elif kind in (ONE_BYTE, TWO_BYTES, FOUR_BYTES, EIGHT_BYTES):
            value = reader.integer(1 << (kind - ONE_BYTE))
        elif kind == SIZED_DATA:
            value = reader.take(reader.integer(4))
        elif kind in (OBJECT_ID, OBJECT_ID_ARRAY):
            count = 1 if kind == OBJECT_ID else bounded_count(reader.integer(4))
            require(ref_offset + count <= len(references), "missing TOC property references")
            value = references[ref_offset:ref_offset + count]
            ref_offset += count
            if kind == OBJECT_ID:
                value = value[0]
        else:
            raise InvalidToc("unsupported TOC property type %x" % kind)
        key = prop & PROPERTY_ID_MASK
        require(key not in result, "duplicate TOC property")
        result[key] = value
    padding = reader.take(len(payload) - reader.pos)
    require(len(padding) < 8 and not any(padding), "invalid TOC property padding")
    require(ref_offset == len(references), "unused TOC object references")
    return result


def section_entries(data):
    """Return filenames and ordering IDs from the remote TOC's active revision."""
    try:
        return Store(data).entries()
    except (UnicodeError, struct.error) as error:
        raise InvalidToc("invalid TOC metadata encoding") from error
