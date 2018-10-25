import os
from enum import IntEnum
import struct
import textwrap
from typing import Dict
from .hashes import HashFile

HashMap = Dict[int, str]


def _repr_indent_list(values):
    if not values:
        return '[]'
    return "[\n%s]" % ''.join("%s\n" % textwrap.indent(repr(v), '  ') for v in values)


hashfile_bin = HashFile(os.path.join(os.path.dirname(__file__), "hashes.bin.txt"), hash_size=8)

def compute_binhash(s):
    """Compute a hash used in BIN files

    FNV-1a hash, on lowercased input
    """
    h = 0x811c9dc5
    for b in s.encode('ascii').lower():
        h = ((h ^ b) * 0x01000193) % 0x100000000
    return h


class BinHash:
    """Hash value is in bin files"""

    def __init__(self, h):
        self.h = h
        self.s = hashfile_bin.load().get(h)

    def __repr__(self):
        if self.s is not None:
            return self.s
        return f"{{{self.h:08x}}}"

    to_serializable = __repr__


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

class BinStruct:
    """Structured binary value"""

    def __init__(self, ehash, fields):
        self.ehash = ehash
        self.fields = fields

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<STRUCT {self.ehash} {sfields}>"

    def to_serializable(self):
        return dict(f.to_serializable() for f in self.fields)


class BinEmbedded:
    """Embedded binary value"""

    def __init__(self, ehash, fields):
        self.ehash = ehash
        self.fields = fields

    def __repr__(self):
        sfields = _repr_indent_list(self.fields)
        return f"<EMBEDDED {self.ehash} {sfields}>"

    def to_serializable(self):
        return dict(f.to_serializable() for f in self.fields)

class BinField:
    """Base class for binary fields

    A field is a value (possibly nested) associated to a hash.
    """
    def __init__(self, fhash):
        self.fhash = fhash

class BinBasicField(BinField):
    """Binary field for fixed-width, non-nested values"""

    def __init__(self, fhash, vtype, value):
        super().__init__(fhash)
        self.vtype = vtype
        self.value = value

    def __repr__(self):
        return f"<{self.fhash} {self.vtype.name} {self.value!r}>"

    def to_serializable(self):
        return (self.fhash.to_serializable(), _to_serializable(self.value))

class BinContainerField(BinField):
    def __init__(self, fhash, vtype, values):
        super().__init__(fhash)
        self.vtype = vtype
        self.values = values

    def __repr__(self):
        svalues = _repr_indent_list(self.values)
        return f"<{self.fhash} CONTAINER({self.vtype.name}) {svalues}>"

    def to_serializable(self):
        return (self.fhash.to_serializable(), [_to_serializable(v) for v in self.values])

class BinStructField(BinField):
    def __init__(self, fhash, value):
        super().__init__(fhash)
        self.value = value

    def __repr__(self):
        sfields = _repr_indent_list(self.value.fields)
        return f"<{self.fhash} STRUCT {self.value.ehash} {sfields}>"

    def to_serializable(self):
        return (self.fhash.to_serializable(), self.value.to_serializable())

class BinEmbeddedField(BinField):
    def __init__(self, fhash, value):
        super().__init__(fhash)
        self.value = value

    def __repr__(self):
        sfields = _repr_indent_list(self.value.fields)
        return f"<{self.fhash} EMBEDDED {self.value.ehash} {sfields}>"

    def to_serializable(self):
        return (self.fhash.to_serializable(), self.value.to_serializable())

class BinArrayField(BinField):
    def __init__(self, fhash, vtype, values):
        super().__init__(fhash)
        self.vtype = vtype
        self.values = values

    def __repr__(self):
        svalues = _repr_indent_list(self.values)
        return f"<{self.fhash} ARRAY({self.vtype.name}) {svalues}>"

    def to_serializable(self):
        return (self.fhash.to_serializable(), [_to_serializable(v) for v in self.values])

class BinMapField(BinField):
    def __init__(self, fhash, ktype, vtype, values):
        super().__init__(fhash)
        self.ktype = ktype
        self.vtype = vtype
        self.values = values

    def __repr__(self):
        svalues = ''.join(f"{k} => {v!r}\n" for k, v in self.values.items())
        svalues = textwrap.indent(svalues, '  ')
        return f"<{self.fhash} MAP({self.ktype.name},{self.vtype.name}) {{\n{svalues}}}>"

    def to_serializable(self):
        return (self.fhash.to_serializable(), {_to_serializable(k): _to_serializable(v) for k,v in self.values.items()})


class BinFileEntry:
    def __init__(self, ehash, etype, values):
        self.ehash = ehash
        self.etype = etype
        self.values = values

    def __repr__(self):
        svalues = _repr_indent_list(self.values)
        return f"<BinFileEntry {self.ehash} {self.etype:08x} {svalues}>"

    def to_serializable(self):
        return [v.to_serializable() for v in self.values]

class BinFile:
    def __init__(self, f):
        if isinstance(f, str):
            f = open(f, 'rb')
        if f.read(4) != b'PROP':
            raise ValueError("missing magic code")
        reader = BinReader(f)
        self.version, self.linked_files, entry_types = reader.read_binfile_header()
        self.entries = [reader.read_binfile_entry(etype) for etype in entry_types]

    def to_serializable(self):
        return {entry.ehash.to_serializable(): entry.to_serializable() for entry in self.entries}


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

    def read_binfile_entry(self, etype):
        """Read a single binfile entry"""

        pos = self.f.tell() + 4  # skip 'length' size
        length, ehash, count = self.read_fmt('<LLH')
        values = [self.read_field() for _ in range(count)]
        entry = BinFileEntry(BinHash(ehash), etype, values)
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
        return BinHash(self.read_fmt('<L')[0])

    def read_link(self):
        return self.read_fmt('<L')[0]

    def read_padding(self):
        return self.read_fmt('<B')[0]

    def read_struct(self):
        ehash, = self.read_fmt('<L')
        if ehash == 0:
            return None
        _, count = self.read_fmt('<LH')
        return BinStruct(BinHash(ehash), [self.read_field() for _ in range(count)])

    def read_embedded(self):
        ehash, = self.read_fmt('<L')
        if ehash == 0:
            return None
        _, count = self.read_fmt('<LH')
        return BinEmbedded(BinHash(ehash), [self.read_field() for _ in range(count)])

    def read_field(self):
        fhash, ftype = self.read_fmt('<LB')
        ftype = BinType(ftype)
        return self._vtype_to_field_reader[ftype](self, BinHash(fhash), ftype)

    def read_field_basic(self, fhash, ftype):
        return BinBasicField(fhash, ftype, self.read_bvalue(ftype))

    def read_field_container(self, fhash, ftype):
        vtype, _, count = self.read_fmt('<BLL')
        vtype = BinType(vtype)
        return BinContainerField(fhash, vtype, [self.read_bvalue(vtype) for _ in range(count)])

    def read_field_struct(self, fhash, ftype):
        return BinStructField(fhash, self.read_bvalue(ftype))

    def read_field_embedded(self, fhash, ftype):
        return BinEmbeddedField(fhash, self.read_bvalue(ftype))

    def read_field_array(self, fhash, ftype):
        vtype, count = self.read_fmt('<BB')
        vtype = BinType(vtype)
        return BinArrayField(fhash, vtype, [self.read_bvalue(vtype) for _ in range(count)])

    def read_field_map(self, fhash, ftype):
        ktype, vtype, _, count = self.read_fmt('<BBLL')
        ktype, vtype = BinType(ktype), BinType(vtype)
        # assume key type is hashable
        values = dict((self.read_bvalue(ktype), self.read_bvalue(vtype)) for _ in range(count))
        return BinMapField(fhash, ktype, vtype, values)

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
