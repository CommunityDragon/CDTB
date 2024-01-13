import os
import errno
import struct
import gzip
import json
import imghdr
import logging
from xxhash import xxh3_64_intdigest

from .hashes import default_hashfile
from .tools import (
    BinaryParser,
    write_file_or_remove,
    zstd_decompress,
)

def test_jpeg_photoshop(h, f):
    if h[:4] == b'\xff\xd8\xff\xe1':
        return 'jpeg'

imghdr.tests.append(test_jpeg_photoshop)


logger = logging.getLogger(__name__)


# Cache for guessed extensions.
# Caching is possible because the same hash should always have the same extension. Since guessing extension requires to
# read file data, caching will reduce I/Os
_hash_to_guessed_extensions = {}


class MalformedSubchunkError(Exception):
    """Subchunk data is invalid or doesn't match the provided subchunktoc"""

    def __init__(self, data):
        self.wad_data = data


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
        b'PTCH': 'bin',
        b'BKHD': 'bnk',
        b'r3d2Mesh': 'scb',
        b'r3d2anmd': 'anm',
        b'r3d2canm': 'anm',
        b'r3d2sklt': 'skl',
        b'r3d2': 'wpk',
        bytes.fromhex('33221100'): 'skn',
        b'PreLoadBuildingBlocks = {': 'preload',
        b'\x1bLuaQ\x00\x01\x04\x04': 'luabin',
        b'\x1bLuaQ\x00\x01\x04\x08': 'luabin64',
        bytes.fromhex('023d0028'): 'troybin',
        b'[ObjectBegin]': 'sco',
        b'OEGM': 'mapgeo',
        b'TEX\0': 'tex'
    }

    def __init__(self, path_hash, offset, compressed_size, size, type, duplicate=None, first_subchunk_index=None, sha256=None):
        self.path_hash = path_hash
        self.offset = offset
        self.size = size
        self.subchunk_count = (type & 0xF0) >> 4
        self.type = type & 0xF
        self.compressed_size = compressed_size
        self.duplicate = bool(duplicate)
        self.first_subchunk_index = first_subchunk_index
        self.sha256 = sha256
        # values that can be guessed
        self.path = None
        self.ext = None

    def read_data(self, f, subchunk_toc=None):
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
        elif self.type == 4:
            # Data is split into individual subchunks that may be zstd compressed
            if subchunk_toc is not None:
                chunks_data = []
                offset = 0
                for index in range(self.first_subchunk_index, self.first_subchunk_index + self.subchunk_count):
                    compressed_size, uncompressed_size, subchunk_hash = struct.unpack('<IIQ', subchunk_toc[16*index:16*(index+1)])
                    # ensure wad data matches with the subchunktoc data
                    subchunk_data = data[offset:offset+compressed_size]
                    if len(data) < offset + compressed_size or xxh3_64_intdigest(subchunk_data) != subchunk_hash:
                        raise MalformedSubchunkError(data)
                    if compressed_size == uncompressed_size:
                        # assume data is uncompressed
                        chunks_data.append(subchunk_data)
                    else:
                        chunks_data.append(zstd_decompress(subchunk_data))
                    offset += compressed_size
                return b"".join(chunks_data)
            else:
                # No subchunk TOC, try to decompress
                try:
                    return zstd_decompress(data)
                except:
                    raise MalformedSubchunkError(data)
        raise ValueError(f"unsupported file type: {self.type}")

    def extract(self, fwad, output_path, subchunk_toc=None):
        """Read data, convert it if needed, and write it to a file

        On error, partially retrieved files are removed.
        File redirections are skipped.
        """

        try:
            data = self.read_data(fwad, subchunk_toc)
        except MalformedSubchunkError:
            return
        if data is None:
            return

        try:
            with write_file_or_remove(output_path) as fout:
                fout.write(data)
        except OSError as e:
            # Path components longer than 255 are not supported, ignore such files
            # TODO: Find a better way of handling these files
            if e.errno in (errno.EINVAL, errno.ENAMETOOLONG):
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
        return None


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
        self.load_subchunk_toc()

    def parse_headers(self):
        """Parse version and file list"""

        logger.debug(f"parse headers of {self.path}")
        with open(self.path, 'rb') as f:
            parser = BinaryParser(f)
            magic, version_major, version_minor = parser.unpack("<2sBB")
            if magic != b'RW':
                raise ValueError("invalid magic code")
            self.version = (version_major, version_minor)

            if version_major == 1:
                parser.seek(8)
            elif version_major == 2:
                parser.seek(100)
            elif version_major == 3:
                parser.seek(268)
            else:
                raise ValueError(f"unsupported WAD version: {version_major}.{version_minor}")

            entry_count, = parser.unpack("<I")

            if version_major == 1:
                self.files = [WadFileHeader(*parser.unpack("<QIIII")) for _ in range(entry_count)]
            else:
                self.files = [WadFileHeader(*parser.unpack("<QIIIB?HQ")) for _ in range(entry_count)]

    def resolve_paths(self, hashes=None):
        """Guess path of files"""

        if hashes is None:
            hashes = default_hashfile(self.path).load()
        for wadfile in self.files:
            if wadfile.path_hash in hashes:
                wadfile.path = hashes[wadfile.path_hash]
                wadfile.ext = os.path.splitext(wadfile.path)[1][1:]

    def load_subchunk_toc(self):
        """Find subchunk TOC if available and parse it"""

        for wadfile in self.files:
            if wadfile.path is None:
                continue
            if not wadfile.path.endswith(".subchunktoc"):
                continue
            with open(self.path, 'rb') as fwad:
                self.subchunk_toc = wadfile.read_data(fwad)
            break
        else:
            # Not found
            self.subchunk_toc = None

    def guess_extensions(self):
        # avoid opening the file if not needed
        unknown_ext = True
        for wadfile in self.files:
            if not wadfile.ext:
                wadfile.ext = _hash_to_guessed_extensions.get(wadfile.path_hash)
                if not wadfile.ext:
                    unknown_ext = True
        if not unknown_ext:
            return  # all extensions are known

        with open(self.path, 'rb') as f:
            for wadfile in self.files:
                if not wadfile.ext:
                    data = self.read_file_data(f, wadfile)
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

    def sanitize_paths(self):
        """Sanitize paths for extract purposes; for example truncating files whose basename has a length of at least 250"""

        for wadfile in self.files:
            if wadfile.path:
                ext = os.path.splitext(wadfile.path)[1]
                if not ext:
                    # some extensionless files conflict with folder names
                    # append a custom suffix to resolve this conflict
                    ext = ".cdtb"

                    if wadfile.ext:
                        # extension was guessed, but the resolved path has no extension
                        # in this case, append the guessed extension
                        ext += f".{wadfile.ext}"

                    wadfile.path += ext

                path, filename = os.path.split(wadfile.path)
                if len(filename) >= 250:
                    wadfile.path = os.path.join(path, f"{filename[:250-17-len(ext)]}.{wadfile.path_hash:016x}{ext}")

    def extract(self, output, overwrite=True):
        """Extract WAD file

        If overwrite is False, don't extract files that already exist on disk.
        """

        logger.info(f"extracting {self.path} to {output}")

        self.sanitize_paths()
        self.set_unknown_paths("unknown")

        with open(self.path, 'rb') as fwad:
            for wadfile in self.files:
                output_path = os.path.join(output, wadfile.path)

                if not overwrite and os.path.exists(output_path):
                    logger.debug(f"skipping {wadfile.path_hash:016x} {wadfile.path} (already extracted)")
                    continue
                logger.debug(f"extracting {wadfile.path_hash:016x} {wadfile.path}")
                wadfile.extract(fwad, output_path, self.subchunk_toc)

    def read_file_data(self, fwad, wadfile):
        """Retrieve (uncompressed) data from WAD file object

        Similar to `WadFileHeader.read_data()` but use wad's subchuk information if available.
        Subchunk errors are ignored and None is returned if one happens.
        """

        try:
            return wadfile.read_data(fwad, self.subchunk_toc)
        except MalformedSubchunkError:
            return None
