import glob
import os
import re
import shutil
import struct
from contextlib import contextmanager

import pyzstd
zstd_decompress = pyzstd.decompress
try:
    import ujson
    def json_dump(obj, fp, **kwargs):
        return ujson.dump(obj, fp, **kwargs, escape_forward_slashes=False)
    def json_dumps(obj, **kwargs):
        return ujson.dumps(obj, **kwargs, escape_forward_slashes=False)
except ImportError:
    import json
    json_dump = json.dump
    json_dumps = json.dumps


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

def stringtable_paths(base_dir, game):
    """
    Collect "stringtables" paths, indexed by locale (e.g. `en_us`)
    """

    # Path format history (from oldest to newest)
    # - data/menu/font_config_<lang>.txt
    # - data/menu/main_<lang>.stringtable
    # - <lang>/data/menu/en_us/main.stringtable
    #   (Directory is always `en_us`, cdtb has been adjusted to export to a language-specific subdir.)
    # - <lang>/data/menu/en_us/<game>.stringtable
    #   (game is either `lol` or `tft`)

    # Find the current format in order from newest to oldest
    lang_dict = {re.search(rf"(.._..)/data/menu/en_us/{game}\.stringtable$", path.replace('\\', '/')).group(1): path for path in glob.glob(os.path.join(base_dir, f"??_??/data/menu/en_us/{game}.stringtable"))}
    if not lang_dict:
        lang_dict = {re.search(r"(.._..)/data/menu/en_us/main\.stringtable$", path.replace('\\', '/')).group(1): path for path in glob.glob(os.path.join(base_dir, "??_??/data/menu/en_us/main.stringtable"))}
    if not lang_dict:
        lang_dict = {re.search(r"data/menu/main_(.._..)\.stringtable$", path.replace('\\', '/')).group(1): path for path in glob.glob(os.path.join(base_dir, "data/menu/main_??_??.stringtable"))}
    if not lang_dict:
        lang_dict = {re.search(r"data/menu/fontconfig_(.._..)\.txt$", path.replace('\\', '/')).group(1): path for path in glob.glob(os.path.join(base_dir, "data/menu/fontconfig_??_??.txt"))}
    if lang_dict:
        return lang_dict
    else:
        raise RuntimeError("cannot find stringtable files")

def convert_cdragon_path(path):
    path, ext = os.path.splitext(path.lower())
    if ext == ".dds" or ext == ".tex":
        ext = ".png"
    return path + ext
