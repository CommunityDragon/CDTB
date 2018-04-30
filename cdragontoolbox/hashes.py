from typing import Dict


class HashFile:
    """Store hashes, support save/load and caching"""

    def __init__(self, filename, hash_size=16):
        self.filename = filename
        self.line_format = f"{{:0{hash_size}x}} {{}}"
        self.hashes = None

    def load(self, force=False) -> Dict[int, str]:
        if force or self.hashes is None:
            with open(self.filename) as f:
                hashes = (l.strip().split(' ', 1) for l in f)
                self.hashes = {int(h, 16): s for h, s in hashes}
        return self.hashes

    def save(self):
        with open(self.filename, 'w', newline='') as f:
            for h, s in sorted(self.hashes.items(), key=lambda kv: kv[1]):
                print(self.line_format.format(h, s), file=f)

