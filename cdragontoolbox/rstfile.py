from xxhash import xxh64_intdigest
from .tools import BinaryParser


def key_to_hash(key):
    if isinstance(key, str):
        return xxh64_intdigest(key.lower()) & 0xffffffffff
    else:
        return key


class RstFile:
    def __init__(self, path_or_f=None):
        self.font_config = None
        self.entries = {}

        if path_or_f is not None:
            if isinstance(path_or_f, str):
                with open(path_or_f, "rb") as f:
                    self.parse_rst(path_or_f)
            else:
                self.parse_rst(path_or_f)

    def __getitem__(self, key):
        h = key_to_hash(key)
        try:
            return self.entries[h]
        except KeyError:
            raise KeyError(key)

    def __contains__(self, key):
        h = key_to_hash(key)
        return h in self.entries

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def parse_rst(self, f):
        parser = BinaryParser(f)

        magic, version_major, version_minor = parser.unpack("<3sBB")
        if magic != b'RST':
            raise ValueError("invalid magic code")
        if (version_major, version_minor) not in ((2, 0), (2, 1)):
            raise ValueError(f"unsupported RST version: {version_major}.{version_minor}")

        if version_minor == 1:
            n, = parser.unpack("<L")
            self.font_config = parser.raw(n).decode("utf-8")
        else:
            self.font_config = None

        count, = parser.unpack("<L")
        entries = []
        for _ in range(count):
            v, = parser.unpack("<Q")
            entries.append((v >> 40, v & 0xffffffffff))

        b = parser.raw(1)
        assert b[0] == version_minor

        data = parser.f.read()
        entries = [(h, data[i:data.find(b"\0", i)]) for i, h in entries]
        # decode unless data starts with 0xFF (illegal UTF-8 sequence)
        self.entries = {h: v if v.startswith(b"\xff") else v.decode("utf-8") for h, v in entries}
