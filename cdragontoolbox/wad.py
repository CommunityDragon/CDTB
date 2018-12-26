import os
import errno
import struct
import gzip
import json
import imghdr
import logging
import zstd
# support both zstd and zstandard implementations
if hasattr(zstd, 'decompress'):
    zstd_decompress = zstd.decompress
else:
    zstd_decompress = zstd.ZstdDecompressor().decompress

from .hashes import default_hashfile
from .storage import (
    PatchVersion,
    ProjectVersion,
    SolutionVersion,
)
from .tools import write_file_or_remove

def test_jpeg_photoshop(h, f):
    if h[:4] == b'\xff\xd8\xff\xe1':
        return 'jpeg'

imghdr.tests.append(test_jpeg_photoshop)


logger = logging.getLogger(__name__)


class Parser:
    def __init__(self, f):
        self.f = f

    def tell(self):
        return self.f.tell()

    def seek(self, position):
        self.f.seek(position, 0)

    def skip(self, amount):
        self.f.seek(amount, 1)

    def rewind(self, amount):
        self.f.seek(-amount, 1)

    def unpack(self, fmt):
        length = struct.calcsize(fmt)
        return struct.unpack(fmt, self.f.read(length))

    def raw(self, length):
        return self.f.read(length)


# Cache for guessed extensions.
# Caching is possible because the same hash should always have the same extension. Since guessing extension requires to
# read file data, caching will reduce I/Os
_hash_to_guessed_extensions = {}


class WadFileHeader:
    """Single file entry in a WAD archive"""

    _magic_numbers_ext = {
        b'OggS': 'ogg',
        bytes.fromhex('00010000'): 'ttf',
        bytes.fromhex('1a45dfa3'): 'webm',
        b'true': 'ttf',
        b'OTTO\0': 'otf',
        b'"use strict";': 'min.js',
        b'<template ': 'template.html',
        b'<!-- Elements -->': 'template.html',
        b'DDS ': 'dds',
        b'<svg': 'svg',
        b'PROP': 'bin',
        b'BKHD': 'bnk',
        b'r3d2Mesh': 'scb',
        b'r3d2anmd': 'anm',
        b'r3d2canm': 'anm',
        b'r3d2sklt': 'skl',
        b'r3d2': 'wpk',
        bytes.fromhex('33221100'): 'skn',
        b'PreLoadBuildingBlocks = {': 'preload',
        b'\x1bLua': 'luabin',
        bytes.fromhex('023d0028'): 'troybin',
        b'[ObjectBegin]': 'sco'
    }

    def __init__(self, path_hash, offset, compressed_size, size, type, duplicate, unk0, unk1, sha256):
        self.path_hash = path_hash
        self.offset = offset
        self.size = size
        self.type = type
        self.compressed_size = compressed_size
        self.duplicate = bool(duplicate)
        self.unk0, self.unk1 = unk0, unk1
        self.sha256 = sha256
        # values that can be guessed
        self.path = None
        self.ext = None

    def read_data(self, f):
        """Retrieve (uncompressed) data from WAD file object"""

        f.seek(self.offset)
        # assume files are small enough to fit in memory
        data = f.read(self.compressed_size)
        if self.type == 0:
            return data
        elif self.type == 1:
            return gzip.decompress(data)
        elif self.type == 2:
            n, = struct.unpack('<L', data[:4])
            target = data[4:4+n].rstrip(b'\0').decode('utf-8')
            logger.debug(f"file redirection: {target}")
            return None
        elif self.type == 3:
            return zstd_decompress(data)
        raise ValueError(f"unsupported file type: {self.type}")

    def extract(self, fwad, output_path):
        """Read data, convert it if needed, and write it to a file

        On error, partially retrieved files are removed.
        File redirections are skipped.
        """

        data = self.read_data(fwad)
        if data is None:
            return

        try:
            with write_file_or_remove(output_path) as fout:
                fout.write(data)
        except OSError as e:
            # Windows does not support path components longer than 255
            # ignore such files
            # TODO: Find a better way of handling these files
            if e.errno == errno.EINVAL:
                logger.warning(f"ignore file with invalid path: {self.path}")
            else:
                raise

    @staticmethod
    def guess_extension(data):
        # image type
        typ = imghdr.what(None, h=data)
        if typ == 'jpeg':
            return 'jpg'
        elif typ == 'xbm':
            pass  # some HLSL files are recognized as xbm
        elif typ is not None:
            return typ

        # json
        try:
            json.loads(data)
            return 'json'
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # others
        for prefix, ext in WadFileHeader._magic_numbers_ext.items():
            if data.startswith(prefix):
                return ext


class Wad:
    """A WAD archive is a file that contains other files.

    It has a header that describes the format. There are multiple
    formats that Riot uses depending on the version of the WAD file, which can be read from the header.
    The files contained in a WAD file generally are all related to one "idea".

    This class has one major purpose: to extract the individual files in a specific WAD archive for further analysis.
    """

    def __init__(self, path, hashes=None):
        self.path = path
        self.version = None
        self.files = None
        self.parse_headers()
        self.resolve_paths(hashes)

    def parse_headers(self):
        """Parse version and file list"""

        logger.debug(f"parse headers of {self.path}")
        with open(self.path, 'rb') as f:
            parser = Parser(f)
            magic, version_major, version_minor = parser.unpack("<2sBB")
            if magic != b'RW':
                raise ValueError("invalid magic code")
            self.version = (version_major, version_minor)

            if version_major == 2:
                parser.seek(100)
            elif version_major == 3:
                parser.seek(268)
            else:
                raise ValueError(f"unsupported WAD version: {version_major}.{version_minor}")

            entry_count, = parser.unpack("<I")
            self.files = [WadFileHeader(*parser.unpack("<QIIIBBBBQ")) for _ in range(entry_count)]

    def resolve_paths(self, hashes=None):
        """Guess path of files"""

        if hashes is None:
            hashes = default_hashfile(self.path).load()
        for wadfile in self.files:
            if wadfile.path_hash in hashes:
                wadfile.path = hashes[wadfile.path_hash]
                wadfile.ext = wadfile.path.rsplit('.', 1)[1]

    def guess_extensions(self):
        # avoid opening the file if not needed
        unknown_ext = True
        for wadfile in self.files:
            if not wadfile.path and not wadfile.ext:
                wadfile.ext = _hash_to_guessed_extensions.get(wadfile.path_hash)
                if not wadfile.ext:
                    unknown_ext = True
        if not unknown_ext:
            return  # all extensions are known

        with open(self.path, 'rb') as f:
            for wadfile in self.files:
                if not wadfile.path and not wadfile.ext:
                    data = wadfile.read_data(f)
                    if not data:
                        continue
                    wadfile.ext = WadFileHeader.guess_extension(data)
                    _hash_to_guessed_extensions[wadfile.path_hash] = wadfile.ext

    def set_unknown_paths(self, path):
        """Set a path for files without one"""

        for wadfile in self.files:
            if not wadfile.path:
                if wadfile.ext:
                    wadfile.path = f"{path}/{wadfile.path_hash:016x}.{wadfile.ext}"
                else:
                    wadfile.path = f"{path}/{wadfile.path_hash:016x}"

    def extract(self, output, overwrite=True):
        """Extract WAD file

        If overwrite is False, don't extract files that already exist on disk.
        """

        logger.info(f"extracting {self.path} to {output}")

        self.set_unknown_paths("unknown")

        with open(self.path, 'rb') as fwad:
            for wadfile in self.files:
                output_path = os.path.join(output, wadfile.path)

                if not overwrite and os.path.exists(output_path):
                    logger.debug(f"skipping {wadfile.path_hash:016x} {wadfile.path} (already extracted)")
                    continue
                logger.debug(f"extracting {wadfile.path_hash:016x} {wadfile.path}")
                wadfile.extract(fwad, output_path)


def wads_from_component(component):
    """Get WADs from a component"""

    if isinstance(component, ProjectVersion):
        it = component.filepaths()
        storage = component.project.storage
    elif isinstance(component, SolutionVersion):
        it = component.filepaths(langs=True)
        storage = component.solution.storage
    elif isinstance(component, PatchVersion):
        # there must be one solution
        it = (p for sv in component.solutions(latest=True) for p in sv.filepaths(langs=True))
        storage = component.storage
    else:
        raise TypeError(f"cannot retrieve WAD files from {component}")
    return [Wad(storage.fspath(p)) for p in it if p.endswith('.wad') or p.endswith('.wad.client')]

