import os
from xxhash import xxh64_intdigest
from base64 import b64encode
from .tools import BinaryParser
from .hashes import HashFile, default_hash_dir


def key_to_hash(key, bits=40):
    if isinstance(key, str):
        key = xxh64_intdigest(key.lower())
    return key & ((1 << bits) - 1)


hashfile_rst = HashFile(default_hash_dir / "hashes.rst.txt", hash_size=10)

class RstFile:
    def __init__(self, path_or_f=None):
        self.font_config = None
        self.entries = {}
        self.hash_bits = 40
        self.version = None

        if path_or_f is not None:
            if isinstance(path_or_f, str):
                with open(path_or_f, "rb") as f:
                    self.parse_rst(f)
            else:
                self.parse_rst(path_or_f)

    def __getitem__(self, key):
        try:
            h = key_to_hash(key, self.hash_bits)
            return self.entries[h]
        except (TypeError, KeyError):
            raise KeyError(key)

    def __contains__(self, key):
        try:
            h = key_to_hash(key, self.hash_bits)
            return h in self.entries
        except TypeError:
            return False

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def parse_rst(self, f):
        parser = BinaryParser(f)

        magic, version = parser.unpack("<3sB")
        if magic != b'RST':
            raise ValueError("invalid magic code")

        if version == 2:
            if parser.unpack("<B")[0]:
                n, = parser.unpack("<L")
                self.font_config = parser.raw(n).decode("utf-8")
            else:
                self.font_config = None
        elif version == 3:
            pass
        elif version in (4, 5):
            self.hash_bits = 39
        else:
            raise ValueError(f"unsupported RST version: {version}")
        self.version = version

        hash_mask = (1 << self.hash_bits) - 1
        count, = parser.unpack("<L")
        entries = []
        for _ in range(count):
            v, = parser.unpack("<Q")
            entries.append((v >> self.hash_bits, v & hash_mask))

        has_trenc = False
        if version < 5:
            has_trenc = parser.unpack("<B")[0]

        data = parser.f.read()

        # Files are sometimes messed-up (e.g. windows-1252 quote)
        # Don't fail on UTF-8 decoding errors
        for i, h in entries:
            if has_trenc and data[i] == 0xFF:
                size = int.from_bytes(data[i+1:][:2], 'little')
                d = b64encode(data[i+3:][:size])
                self.entries[h] = d.decode('utf-8', 'replace')
            else:
                end = data.find(b"\0", i)
                d = data[i:end]
                self.entries[h] = d.decode('utf-8', 'replace')
