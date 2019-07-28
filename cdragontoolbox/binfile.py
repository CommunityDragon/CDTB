import os
from enum import IntEnum
import struct
from .hashes import HashFile


def _repr_indent(v):
    return repr(v).replace('\n', '\n  ')

def _repr_indent_list(values):
    if not values:
        return '[]'
    return "[\n%s]" % ''.join(f"  {_repr_indent(v)}\n" for v in values)


hashfile_binentries = HashFile(os.path.join(os.path.dirname(__file__), "hashes.binentries.txt"), hash_size=8)
hashfile_binhashes = HashFile(os.path.join(os.path.dirname(__file__), "hashes.binhashes.txt"), hash_size=8)
hashfile_binfields = HashFile(os.path.join(os.path.dirname(__file__), "hashes.binfields.txt"), hash_size=8)
hashfile_bintypes = HashFile(os.path.join(os.path.dirname(__file__), "hashes.bintypes.txt"), hash_size=8)

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
                return self.h == compute_binhash(other)
            else:
                return self.s == other
        else:
            return self.h == other

    def __str__(self):
        if self.s is not None:
            return self.s
        return f"{{{self.h:08x}}}"

    __repr__ = __str__
    to_serializable = __str__

    def __hash__(self):
        return self.h

class BinHashValue(BinHashBase):
    """Hashed name in bin files (hash type)"""

    hashfile = hashfile_binhashes

    def __repr__(self):
        if self.s is not None:
            return repr(self.s)
        return f"{{{self.h:08x}}}"

class BinEntryPath(BinHashBase):
    """Path of a bin entry (top level element)"""

    hashfile = hashfile_binentries

    def __repr__(self):
        if self.s is not None:
            return repr(self.s)
        return f"{{{self.h:08x}}}"

class BinFieldName(BinHashBase):
    """Name of a struct field"""

    hashfile = hashfile_binfields

class BinTypeName(BinHashBase):
    """Name of a type"""

    hashfile = hashfile_bintypes


def key_to_hash(key):
    if isinstance(key, BinHashBase):
        return key.h
    elif isinstance(key, str):
        return compute_binhash(key)
    else:
        return key

class BinObjectWithFields:
    """Base class for bin object with fields"""

    def __init__(self, htype, fields):
        self.type = BinTypeName(htype)
        self.fields = fields

    def __getitem__(self, key):
        h = key_to_hash(key)
        for v in self.fields:
            if v.name.h == h:
                return v
        raise KeyError(key)

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

    def to_serializable(self):
        return dict(f.to_serializable() for f in self.fields)


class BinType(IntEnum):
    VEC3_U16 = 0
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
    CONTAINER = 18
    STRUCT = 19
    EMBEDDED = 20
    LINK = 21
    ARRAY = 22
    MAP = 23
    PADDING = 24

class BinStruct(BinObjectWithFields):
    """Structured binary value"""

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<STRUCT {self.type!r} {sfields}>"

class BinEmbedded(BinObjectWithFields):
    """Embedded binary value"""

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<EMBEDDED {self.type!r} {sfields}>"

class BinField:
    """Base class for binary fields

    A field is a value (possibly nested) associated to a hash.
    """
    def __init__(self, hname):
        self.name = BinFieldName(hname)

class BinBasicField(BinField):
    """Binary field for fixed-width, non-nested values"""

    def __init__(self, hname, btype, value):
        super().__init__(hname)
        self.type = btype
        self.value = value

    def __repr__(self):
        return f"<{self.name!r} {self.type.name} {self.value!r}>"

    def to_serializable(self):
        return (self.name.to_serializable(), _to_serializable(self.value))

class BinContainerField(BinField):
    def __init__(self, hname, btype, values):
        super().__init__(hname)
        self.type = btype
        self.value = values

    def __repr__(self):
        svalues = _repr_indent_list(self.value)
        return f"<{self.name!r} CONTAINER({self.type.name}) {svalues}>"

    def to_serializable(self):
        return (self.name.to_serializable(), [_to_serializable(v) for v in self.value])

class BinStructField(BinField):
    def __init__(self, hname, value):
        super().__init__(hname)
        self.value = value

    def __repr__(self):
        sfields = _repr_indent_list(self.value.fields)
        return f"<{self.name!r} STRUCT {self.value.type!r} {sfields}>"

    def to_serializable(self):
        return (self.name.to_serializable(), self.value.to_serializable())

class BinEmbeddedField(BinField):
    def __init__(self, hname, value):
        super().__init__(hname)
        self.value = value

    def __repr__(self):
        sfields = _repr_indent_list(self.value.fields)
        return f"<{self.name!r} EMBEDDED {self.value.type!r} {sfields}>"

    def to_serializable(self):
        return (self.name.to_serializable(), self.value.to_serializable())

class BinArrayField(BinField):
    def __init__(self, hname, vtype, values):
        super().__init__(hname)
        self.vtype = vtype
        self.value = values

    def __repr__(self):
        svalues = _repr_indent_list(self.value)
        return f"<{self.name!r} ARRAY({self.vtype.name}) {svalues}>"

    def to_serializable(self):
        return (self.name.to_serializable(), [_to_serializable(v) for v in self.value])

class BinMapField(BinField):
    def __init__(self, hname, ktype, vtype, values):
        super().__init__(hname)
        self.ktype = ktype
        self.vtype = vtype
        self.value = values

    def __repr__(self):
        svalues = ''.join(f"  {k} => {_repr_indent(v)}\n" for k, v in self.value.items())
        return f"<{self.name!r} MAP({self.ktype.name},{self.vtype.name}) {{\n{svalues}}}>"

    def to_serializable(self):
        return (self.name.to_serializable(), {_to_serializable(k): _to_serializable(v) for k,v in self.value.items()})


class BinEntry(BinObjectWithFields):
    def __init__(self, hpath, htype, fields):
        self.path = BinEntryPath(hpath)
        super().__init__(htype, fields)

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<BinEntry {self.path!r} {self.type!r} {sfields}>"

class BinFile:
    def __init__(self, f):
        if isinstance(f, str):
            f = open(f, 'rb')
        if f.read(4) != b'PROP':
            raise ValueError("missing magic code")
        reader = BinReader(f)
        self.version, self.linked_files, entry_types = reader.read_binfile_header()
        self.entries = [reader.read_binfile_entry(htype) for htype in entry_types]

    def to_serializable(self):
        return {entry.path.to_serializable(): entry.to_serializable() for entry in self.entries}


class BinReader:
    def __init__(self, f):
        self.f = f

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


    def read_bvalue(self, vtype):
        return self._vtype_to_bvalue_reader[vtype](self)

    def read_vec3_u16(self):
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

    def read_link(self):
        return BinEntryPath(self.read_fmt('<L')[0])

    def read_padding(self):
        return self.read_fmt('<B')[0]

    def read_struct(self):
        htype, = self.read_fmt('<L')
        if htype == 0:
            return None
        _, count = self.read_fmt('<LH')
        return BinStruct(htype, [self.read_field() for _ in range(count)])

    def read_embedded(self):
        htype, = self.read_fmt('<L')
        if htype == 0:
            return None
        _, count = self.read_fmt('<LH')
        return BinEmbedded(htype, [self.read_field() for _ in range(count)])

    def read_field(self):
        hname, ftype = self.read_fmt('<LB')
        ftype = BinType(ftype)
        return self._vtype_to_field_reader[ftype](self, hname, ftype)

    def read_field_basic(self, hname, btype):
        return BinBasicField(hname, btype, self.read_bvalue(btype))

    def read_field_container(self, hname, btype):
        vtype, _, count = self.read_fmt('<BLL')
        vtype = BinType(vtype)
        return BinContainerField(hname, vtype, [self.read_bvalue(vtype) for _ in range(count)])

    def read_field_struct(self, hname, btype):
        return BinStructField(hname, self.read_bvalue(btype))

    def read_field_embedded(self, hname, btype):
        return BinEmbeddedField(hname, self.read_bvalue(btype))

    def read_field_array(self, hname, btype):
        vtype, count = self.read_fmt('<BB')
        vtype = BinType(vtype)
        return BinArrayField(hname, vtype, [self.read_bvalue(vtype) for _ in range(count)])

    def read_field_map(self, hname, btype):
        ktype, vtype, _, count = self.read_fmt('<BBLL')
        ktype, vtype = BinType(ktype), BinType(vtype)
        # assume key type is hashable
        values = dict((self.read_bvalue(ktype), self.read_bvalue(vtype)) for _ in range(count))
        return BinMapField(hname, ktype, vtype, values)

    _vtype_to_bvalue_reader = {
        BinType.VEC3_U16: read_vec3_u16,
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
        BinType.STRUCT: read_struct,
        BinType.EMBEDDED: read_embedded,
        BinType.LINK: read_link,
        BinType.PADDING: read_padding,
    }

    _vtype_to_field_reader = {
        BinType.VEC3_U16: read_field_basic,
        BinType.BOOL: read_field_basic,
        BinType.S8: read_field_basic,
        BinType.U8: read_field_basic,
        BinType.S16: read_field_basic,
        BinType.U16: read_field_basic,
        BinType.S32: read_field_basic,
        BinType.U32: read_field_basic,
        BinType.S64: read_field_basic,
        BinType.U64: read_field_basic,
        BinType.FLOAT: read_field_basic,
        BinType.VEC2_FLOAT: read_field_basic,
        BinType.VEC3_FLOAT: read_field_basic,
        BinType.VEC4_FLOAT: read_field_basic,
        BinType.MATRIX4X4: read_field_basic,
        BinType.RGBA: read_field_basic,
        BinType.STRING: read_field_basic,
        BinType.HASH: read_field_basic,
        BinType.CONTAINER: read_field_container,
        BinType.STRUCT: read_field_struct,
        BinType.EMBEDDED: read_field_embedded,
        BinType.LINK: read_field_basic,
        BinType.ARRAY: read_field_array,
        BinType.MAP: read_field_map,
        BinType.PADDING: read_field_basic,
    }


def _to_serializable(v):
    return v.to_serializable() if hasattr(v, 'to_serializable') else v
