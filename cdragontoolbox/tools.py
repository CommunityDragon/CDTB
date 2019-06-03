import os
import shutil
import struct
from contextlib import contextmanager

import zstd
# support both zstd and zstandard implementations
if hasattr(zstd, 'decompress'):
    zstd_decompress = zstd.decompress
else:
    zstd_decompress = zstd.ZstdDecompressor().decompress


@contextmanager
def write_file_or_remove(path, binary=True):
    """Open a file for writing, create its parent directory if needed

    If the writing fails, the file is removed.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb' if binary else 'w') as f:
            yield f
    except:
        # remove partially written file
        try:
            os.remove(path)
        except OSError:
            pass
        raise

@contextmanager
def write_dir_or_remove(path):
    """Create a directory for writing, and its parent directory if needed

    If the writing fails, the directory and its content is removed.
    """
    try:
        os.makedirs(path, exist_ok=True)
        yield
    except:
        # remove directory
        shutil.rmtree(path, ignore_errors=True)
        raise


class BinaryParser:
    """Helper class to read from binary file object"""

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

    def unpack_string(self):
        """Unpack string prefixed by its 32-bit length"""
        return self.f.read(self.unpack('<L')[0]).decode('utf-8')

