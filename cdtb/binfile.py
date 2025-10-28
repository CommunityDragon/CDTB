from enum import IntEnum
import struct
from xxhash import xxh64_intdigest
from .hashes import HashFile, default_hash_dir, hashfile_game


def _repr_indent(v):
    return repr(v).replace('\n', '\n  ')

def _repr_indent_list(values):
    if not values:
        return '[]'
    return "[\n%s]" % ''.join(f"  {_repr_indent(v)}\n" for v in values)


hashfile_binentries = HashFile(default_hash_dir / "hashes.binentries.txt", hash_size=8)
hashfile_binhashes = HashFile(default_hash_dir / "hashes.binhashes.txt", hash_size=8)
hashfile_binfields = HashFile(default_hash_dir / "hashes.binfields.txt", hash_size=8)
hashfile_bintypes = HashFile(default_hash_dir / "hashes.bintypes.txt", hash_size=8)
hashfile_binpaths = hashfile_game

def compute_binhash(s):
    """Compute a hash used in BIN files

    FNV-1a hash, on lowercased input
    """
    h = 0x811c9dc5
    for b in s.encode('ascii').lower():
        h = ((h ^ b) * 0x01000193) % 0x100000000
    return h

class BinHashBase:
    """Base class for hashed value"""

    hashfile = None  # to be defined in subclasses

    def __init__(self, h):
        self.h = h
        self.s = self.hashfile.load().get(h)

    def __eq__(self, other):
        if isinstance(other, BinHashBase):
            return self.h == other.h
        elif isinstance(other, str):
            if self.s is None:
                return self.h == self.compute_hash(other)
            else:
                return self.s == other
        else:
            return self.h == other

    def __str__(self):
        if self.s is not None:
            return self.s
        return f"{{{self.hex()}}}"

    __repr__ = __str__
    to_serializable = __str__

    def __hash__(self):
        return self.h

    @classmethod
    def compute_hash(cls, s):
        return compute_binhash(s)

    def hex(self):
        return f"{self.h:08x}"

class BinHashValue(BinHashBase):
    """Hashed name in bin files (hash type)"""

    hashfile = hashfile_binhashes

    def __repr__(self):
        if self.s is not None:
            return repr(self.s)
        return f"{{{self.hex()}}}"

class BinEntryPath(BinHashBase):
    """Path of a bin entry (top level element)"""

    hashfile = hashfile_binentries

    def __repr__(self):
        if self.s is not None:
            return repr(self.s)
        return f"{{{self.hex()}}}"

class BinFieldName(BinHashBase):
    """Name of a struct field"""

    hashfile = hashfile_binfields

class BinTypeName(BinHashBase):
    """Name of a type"""

    hashfile = hashfile_bintypes

class BinPathValue(BinHashBase):
    """Hashed WAD path in bin files"""

    hashfile = hashfile_binpaths

    def hex(self):
        return f"{self.h:016x}"

    @classmethod
    def compute_hash(cls, s):
        return xxh64_intdigest(s.lower())

    def __repr__(self):
        if self.s is not None:
            return repr(self.s)
        return f"{{{self.hex()}}}"


def key_to_hash(key):
    if isinstance(key, BinHashBase):
        return key.h
    elif isinstance(key, str):
        return compute_binhash(key)
    else:
        return key

class BinObjectWithFields:
    """Base class for bin object with fields"""

    def __init__(self, fields):
        self.fields = fields

    def __getitem__(self, key):
        h = key_to_hash(key)
        for v in self.fields:
            if v.name.h == h:
                return v
        raise KeyError(key)

    def __setitem__(self, key, value):
        h = key_to_hash(key)
        for n, v in enumerate(self.fields):
            if v.name.h == h:
                self.fields[n] = value
                break
        else:
            self.fields.append(value)

    def __contains__(self, key):
        h = key_to_hash(key)
        for v in self.fields:
            if v.name.h == h:
                return True
        return False

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def getv(self, key, default=None):
        try:
            return self[key].value
        except KeyError:
            return default

    def get_path(self, *args, default=None):
        """Get value by accessing successive field names"""
        v = self
        try:
            for key in args:
                v = v[key].value
            return v
        except KeyError:
            return default

    def to_serializable(self):
        return dict(f.to_serializable() for f in self.fields)

class BinObjectWithFieldsAndType(BinObjectWithFields):
    """Base class for bin objects with fields and type"""

    def __init__(self, htype, fields):
        super().__init__(fields)
        self.type = BinTypeName(htype)

    def to_serializable(self):
        serialized = super().to_serializable()
        serialized["__type"] = self.type.to_serializable()
        return serialized

class BinType(IntEnum):
    # See parse_bintype() for remapping depending on version
    EMPTY = 0
    BOOL = 1
    S8 = 2
    U8 = 3
    S16 = 4
    U16 = 5
    S32 = 6
    U32 = 7
    S64 = 8
    U64 = 9
    FLOAT = 10
    VEC2_FLOAT = 11
    VEC3_FLOAT = 12
    VEC4_FLOAT = 13
    MATRIX4X4 = 14
    RGBA = 15
    STRING = 16
    HASH = 17
    PATH = 18  # introduced in 10.23
    # Complex types (0x80 flag introduced in 9.23)
    LIST = 0x80
    LIST2 = 0x81  # introduced in 10.8
    STRUCT = 0x82
    EMBEDDED = 0x83
    LINK = 0x84
    OPTION = 0x85
    MAP = 0x86
    FLAG = 0x87

def format_binvalue(btype, bvalue):
    match btype:
        case BinType.LIST | BinType.LIST2:
            svalues = _repr_indent_list(bvalue)
            return f"{btype.name}({bvalue.vtype.name}) {svalues}"
        case BinType.STRUCT:
            if bvalue.type.h == 0:
                return f"STRUCT {None}"
            sfields = _repr_indent_list(bvalue.fields)
            return f"STRUCT {bvalue.type!r} {sfields}"
        case BinType.EMBEDDED:
            sfields = _repr_indent_list(bvalue.fields)
            return f"EMBEDDED {bvalue.type!r} {sfields}"
        case BinType.OPTION:
            return f"OPTION({bvalue.vtype.name}) {bvalue.value!r}"
        case BinType.MAP:
            svalues = ''.join(f"  {k} => {_repr_indent(v)}\n" for k, v in bvalue.items())
            return f"MAP({bvalue.ktype.name},{bvalue.vtype.name}) {{\n{svalues}}}"
        case _:
            return f"{btype.name} {bvalue!r}"


class BinList(list):
    def __init__(self, vtype, values: list):
        super().__init__(values)
        self.vtype = vtype

    def __repr__(self):
        return f"<{format_binvalue(BinType.LIST, self)}>"

    def to_serializable(self):
        return [_to_serializable(v) for v in self]

class BinStruct(BinObjectWithFieldsAndType):
    """Structured binary value"""

    def __repr__(self):
        return f"<{format_binvalue(BinType.STRUCT, self)}>"

    def to_serializable(self):
        return super().to_serializable() if self.type.h else None

class BinEmbedded(BinObjectWithFieldsAndType):
    """Embedded binary value"""

    def __repr__(self):
        return f"<{format_binvalue(BinType.EMBEDDED, self)}>"

class BinOption:
    def __init__(self, vtype, value):
        self.vtype = vtype
        self.value = value

    def __repr__(self):
        return f"<{format_binvalue(BinType.OPTION, self)}>"

    def to_serializable(self):
        return self.value

class BinMap(dict):
    def __init__(self, ktype, vtype, values: dict):
        super().__init__(values)
        self.ktype = ktype
        self.vtype = vtype

    def __repr__(self):
        return f"<{format_binvalue(BinType.MAP, self)}>"

    def to_serializable(self):
        return {_to_serializable(k): _to_serializable(v) for k,v in self.items()}

class BinField:
    """A field is a value (possibly nested) associated to a hash"""

    def __init__(self, hname, btype, value):
        self.name = BinFieldName(hname)
        self.type = btype
        self.value = value

    def __repr__(self):
        return f"<{self.name!r} {format_binvalue(self.type, self.value)}>"

    def to_serializable(self):
        return (self.name.to_serializable(), _to_serializable(self.value))

class BinPatchField:
    """Similar to BinField but with string path instead of hashed name"""

    def __init__(self, path, btype, value):
        self.path = path
        self.type = btype
        self.value = value

    def __repr__(self):
        return f"<{self.path} {format_binvalue(self.type, self.value)}>"

    def to_serializable(self):
        return (self.path, _to_serializable(self.value))


class BinPatchEntry:
    def __init__(self, hpath):
        self.path = BinEntryPath(hpath)
        self.fields = []

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<BinPatchEntry {self.path!r} {sfields}>"

    def to_serializable(self):
        return dict(f.to_serializable() for f in self.fields)

class BinEntry(BinObjectWithFieldsAndType):
    def __init__(self, hpath, htype, fields):
        self.path = BinEntryPath(hpath)
        super().__init__(htype, fields)

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<BinEntry {self.path!r} {self.type!r} {sfields}>"

class BinFile:
    def __init__(self, f, btype_version=None):
        if isinstance(f, str):
            f = open(f, 'rb')
        magic = f.read(4)
        self.is_patch = magic == b'PTCH'
        if self.is_patch:
            patch_header = struct.unpack('<2L', f.read(8))
            assert patch_header == (1, 0)
            magic = f.read(4)
        if magic != b'PROP':
            raise ValueError("missing magic code")
        reader = BinReader(f, btype_version=btype_version)
        self.version, self.linked_files, entry_types = reader.read_binfile_header()
        self.entries = [reader.read_binfile_entry(htype) for htype in entry_types]
        if self.is_patch and self.version >= 3:
            self.patch_entries = reader.read_patch_section()
        else:
            self.patch_entries = None

    def to_serializable(self):
        serialized = {entry.path.to_serializable(): entry.to_serializable() for entry in self.entries}
        if self.linked_files is not None:
            serialized["__linked"] = self.linked_files
        if self.patch_entries is not None:
            serialized["__patches"] = {entry.path.to_serializable(): entry.to_serializable() for entry in self.patch_entries}
        return serialized

    def dump(self, f):
        if self.linked_files is not None:
            print(f"<Linked: {_repr_indent_list(self.linked_files)}>", file=f)
        for entry in self.entries:
            print(entry, file=f)
        if self.patch_entries is not None:
            for entry in self.patch_entries:
                print(entry, file=f)


class BinReader:
    def __init__(self, f, btype_version=None):
        """
        Initialize a reader for bin files and values

        `btype_version` is a workaround to parse bin types differently
        depending on patch version. Value is based on the patch version.
        """
        self.f = f
        self.btype_version = btype_version or 1008

    def read_fmt(self, fmt):
        length = struct.calcsize(fmt)
        return struct.unpack(fmt, self.f.read(length))

    def read_binfile_header(self):
        """Return a (version, linked_files, entry_types) tuple"""
        version, = self.read_fmt('<L')
        if version >= 2:
            n, = self.read_fmt('<L')
            linked_files = [self.read_string() for _ in range(n)]
        else:
            linked_files = None
        entry_count, = self.read_fmt('<L')
        entry_types = list(self.read_fmt(f"<{entry_count}L"))
        return version, linked_files, entry_types

    def read_binfile_entry(self, htype):
        """Read a single binfile entry"""

        pos = self.f.tell() + 4  # skip 'length' size
        length, hpath, count = self.read_fmt('<LLH')
        values = [self.read_field() for _ in range(count)]
        entry = BinEntry(hpath, htype, values)
        assert self.f.tell() - pos == length
        return entry

    def read_patch_section(self):
        """Reads the entire PTCH section"""

        count = self.read_u32()
        patch_entries = {}
        for _ in range(count):
            hpath = self.read_fmt('<2L')[0]
            btype = self.parse_bintype(self.read_u8())
            object_path = self.read_string()
            binvalue = self.read_bvalue(btype)

            if hpath not in patch_entries:
                patch_entries[hpath] = BinPatchEntry(hpath)
            new_entry = patch_entries[hpath]

            new_entry.fields.append(BinPatchField(object_path, btype, binvalue))

        return list(patch_entries.values())


    def read_bvalue(self, vtype):
        return self._vtype_to_bvalue_reader[vtype](self)

    def read_empty(self):
        return self.read_fmt('<3H')

    def read_bool(self):
        return self.read_fmt('<?')[0]

    def read_s8(self):
        return self.read_fmt('<b')[0]

    def read_u8(self):
        return self.read_fmt('<B')[0]

    def read_s16(self):
        return self.read_fmt('<h')[0]

    def read_u16(self):
        return self.read_fmt('<H')[0]

    def read_s32(self):
        return self.read_fmt('<i')[0]

    def read_u32(self):
        return self.read_fmt('<I')[0]

    def read_s64(self):
        return self.read_fmt('<q')[0]

    def read_u64(self):
        return self.read_fmt('<Q')[0]

    def read_float(self):
        return self.read_fmt('<f')[0]

    def read_vec2_float(self):
        return self.read_fmt('<2f')

    def read_vec3_float(self):
        return self.read_fmt('<3f')

    def read_vec4_float(self):
        return self.read_fmt('<4f')

    def read_matrix4x4(self):
        return tuple(self.read_fmt('<4f') for _ in range(4))

    def read_rgba(self):
        return self.read_fmt('<4B')

    def read_string(self):
        return self.f.read(self.read_fmt('<H')[0]).decode('utf-8')

    def read_hash(self):
        return BinHashValue(self.read_fmt('<L')[0])

    def read_path(self):
        return BinPathValue(self.read_fmt('<Q')[0])

    def read_link(self):
        return BinEntryPath(self.read_fmt('<L')[0])

    def read_flag(self):
        return self.read_fmt('<B')[0]

    def read_list(self):
        vtype, _, count = self.read_fmt('<BLL')
        vtype = self.parse_bintype(vtype)
        return BinList(vtype, [self.read_bvalue(vtype) for _ in range(count)])

    def read_struct(self):
        htype, = self.read_fmt('<L')
        if htype == 0:
            count = 0
        else:
            _, count = self.read_fmt('<LH')
        return BinStruct(htype, [self.read_field() for _ in range(count)])

    def read_embedded(self):
        htype, _, count = self.read_fmt('<LLH')
        return BinEmbedded(htype, [self.read_field() for _ in range(count)])

    def read_option(self):
        vtype, has_value = self.read_fmt('<B?')
        vtype = self.parse_bintype(vtype)
        return BinOption(vtype, self.read_bvalue(vtype) if has_value else None)

    def read_map(self):
        ktype, vtype, _, count = self.read_fmt('<BBLL')
        ktype, vtype = self.parse_bintype(ktype), self.parse_bintype(vtype)
        # assume key type is hashable
        return BinMap(ktype, vtype, dict((self.read_bvalue(ktype), self.read_bvalue(vtype)) for _ in range(count)))

    def read_field(self):
        hname, ftype = self.read_fmt('<LB')
        ftype = self.parse_bintype(ftype)
        return BinField(hname, ftype, self.read_bvalue(ftype))

    def parse_bintype(self, v):
        if self.btype_version < 923:
            if v == 18:
                v = 0x80
            elif v >= 19:
                v = 0x80 + v - 18
        if self.btype_version < 1008:
            if v >= 0x81:
                v += 1
        return BinType(v)


    _vtype_to_bvalue_reader = {
        BinType.EMPTY: read_empty,
        BinType.BOOL: read_bool,
        BinType.S8: read_s8,
        BinType.U8: read_u8,
        BinType.S16: read_s16,
        BinType.U16: read_u16,
        BinType.S32: read_s32,
        BinType.U32: read_u32,
        BinType.S64: read_s64,
        BinType.U64: read_u64,
        BinType.FLOAT: read_float,
        BinType.VEC2_FLOAT: read_vec2_float,
        BinType.VEC3_FLOAT: read_vec3_float,
        BinType.VEC4_FLOAT: read_vec4_float,
        BinType.MATRIX4X4: read_matrix4x4,
        BinType.RGBA: read_rgba,
        BinType.STRING: read_string,
        BinType.HASH: read_hash,
        BinType.PATH: read_path,
        BinType.LIST: read_list,
        BinType.LIST2: read_list,
        BinType.STRUCT: read_struct,
        BinType.EMBEDDED: read_embedded,
        BinType.LINK: read_link,
        BinType.OPTION: read_option,
        BinType.MAP: read_map,
        BinType.FLAG: read_flag,
    }


def _to_serializable(v):
    return v.to_serializable() if hasattr(v, 'to_serializable') else v
