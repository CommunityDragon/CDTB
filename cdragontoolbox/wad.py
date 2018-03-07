import os
import re
import struct
import gzip
import json
import imghdr
import logging
import posixpath
from typing import Dict, Iterable
import xxhash
import zstd
# support both zstd and zstandard implementations
if hasattr(zstd, 'decompress'):
    zstd_decompress = zstd.decompress
else:
    zstd_decompress = zstd.ZstdDecompressor().decompress

from .data import REGIONS, Language

HashMap = Dict[int, str]

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
        b'r3d2Mesh': 'scb',
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
        elif self.type == 3:
            return zstd_decompress(data)
        raise ValueError(f"unsupported file type: {self.type}")

    @staticmethod
    def guess_extension(data):
        # image type
        typ = imghdr.what(None, h=data)
        if typ == 'jpeg':
            return 'jpg'
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
    The parsing can be done using the `WAD.extract(...)` method.
    Functionality for guessing new hashes is also included in this class.
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
            hashes = load_hashes()
        for wadfile in self.files:
            if wadfile.path_hash in hashes:
                wadfile.path = hashes[wadfile.path_hash]
                wadfile.ext = wadfile.path.split('.', 1)[1]

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

                fwad.seek(wadfile.offset)
                # assume files are small enough to fit in memory
                data = wadfile.read_data(fwad)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                try:
                    with open(output_path, 'wb') as fout:
                        fout.write(data)
                except:
                    # remove partially downloaded file
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                    raise

    def guess_hashes(self, unknown_hashes):
        """Try to guess hashes"""

        logger.info(f"guessing hashes from {self.path}")

        resolved_paths = set()
        found_paths = set()  # candidate paths
        plugin_name = None

        # parse all information in one pass
        with open(self.path, 'rb') as f:
            for wadfile in self.files:
                # only process text files
                # skip non-text files as soon as possible
                if wadfile.ext in ('png', 'jpg', 'ttf', 'webm', 'ogg', 'dds'):
                    continue
                try:
                    data = wadfile.read_data(f).decode('utf-8-sig')
                except UnicodeDecodeError:
                    continue
                if not data:
                    continue

                if wadfile.ext == 'json':
                    jdata = json.loads(data)
                    if wadfile.path == 'plugins/rcp-fe-lol-loot/global/default/trans.json':
                        found_paths |= {f'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/{k}.png' for k in jdata}
                    elif 'pluginDependencies' in jdata and 'name' in jdata:
                        # retrieve plugin_name from description.json
                        plugin_name = jdata['name']

                # paths starting with /fe/ or /lol-plugin/
                found_paths |= {m.group(1) for m in re.finditer(r'((?:/fe/|/lol-)[a-zA-Z0-9/_.@-]+)', data)}
                # relative path starting with ./ or ../ (e.g. require() use)
                relpaths = {m.group(1) for m in re.finditer(r'[^a-zA-Z0-9/_.\\-]((?:\.|\.\.)/[a-zA-Z0-9/_.-]+)', data)}
                found_paths |= relpaths
                if wadfile.path:
                    resolved_paths |= {posixpath.normpath(posixpath.join(posixpath.dirname(wadfile.path), path)) for path in relpaths}
                # paths with known extension
                found_paths |= {m.group(1) for m in re.finditer(r'''["']([a-zA-Z0-9/_.-]+\.(?:png|jpg|webm|js|html|css|ttf|otf))\b''', data)}
                # template ID to template path
                found_paths |= {f"{m.group(1)}/template.html" for m in re.finditer(r'<template id="[^"]*-template-([^"]+)"', data)}
                # JS maps
                found_paths |= {m.group(1) for m in re.finditer(r'sourceMappingURL=(.*?\.js)\.map', data)}

        # hashed paths are always lowercased, do the same
        found_paths = {p.lower() for p in found_paths}

        if not plugin_name:
            # try to guess plugin_name from path
            # this will work when loading a wad in a RADS tree
            plugin_name = os.path.basename(os.path.dirname(os.path.abspath(self.path)))
            if not plugin_name.startswith("rcp-"):
                plugin_name = None
        default_path = f"plugins/{plugin_name}/global/default" if plugin_name else None

        # resolve parsed paths, using plugin name, known subdirs, ...
        for path in found_paths:

            # plugins/...: no changes
            if path.startswith('plugins/'):
                resolved_paths.add(path)
                continue

            # /fe/{plugin}/{subpath} -> plugins/rcp-[bf]e-{plugin}/global/default/{subpath}
            # /lol-{name}/{subpath}  -> plugins/rcp-[bf]e-lol-{name}/global/default/{subpath}
            m = re.match(r'/(fe/|lol-)([^/]+)/(.*)', path)
            if m:
                prefix, plugin, subpath = m.groups()
                if prefix == 'lol-':
                    plugin = f'lol-{plugin}'
                resolved_paths.add(f'plugins/rcp-fe-{plugin}/global/default/{subpath}')
                resolved_paths.add(f'plugins/rcp-be-{plugin}/global/default/{subpath}')
                if subpath.startswith('assets/'):
                    # lol-game-data paths sometimes have an extra 'assets/'
                    subpath = subpath[len('assets/'):]
                    resolved_paths.add(f'plugins/rcp-fe-{plugin}/global/default/{subpath}')
                    resolved_paths.add(f'plugins/rcp-be-{plugin}/global/default/{subpath}')
                continue

            # starting with './' or '../' without extension, try node module file
            m = re.match(r'\.+/(.*/[^.]+)$', path)
            if m:
                for prefix in ('components', 'components/elements', 'components/dropdowns', 'components/components'):
                    resolved_paths |= {f'{prefix}{suffix}' for suffix in ('.js', '.js.map', '/index.js', '/index.js.map')}

            if default_path:
                basename = posixpath.basename(path)
                # known subdirectories
                m = re.match(r'\b((?:data|assets|images|audio|components|sounds|video|css)/.+)', path)
                if m:
                    subpath = m.group(1)
                    resolved_paths.add(f'{default_path}/{subpath}')
                    resolved_paths.add(f'{default_path}/{posixpath.dirname(subpath)}')
                # combine basename and subpath with known directories
                for subpath in (basename, path.lstrip('./')):
                    resolved_paths.add(f'{default_path}/{subpath}')
                    resolved_paths |= {f'{default_path}/{subdir}/{subpath}' for subdir in (
                        'components', 'components/elements', 'components/dropdowns', 'components/components',
                        'images', 'audio', 'sounds', 'video', 'mograph', 'css',
                        'assets', 'assets/images', 'assets/audio', 'assets/sounds', 'assets/video', 'assets/mograph',
                    )}

        # add common names at root
        if default_path:
            resolved_paths |= {f'{default_path}/{name}' for name in (
                'index.html', 'init.js', 'init.js.map', 'bundle.js', 'trans.json',
                'css/main.css', 'license.json',
            )}
            resolved_paths |= {f'{default_path}/{i}.bundle.js' for i in range(10)}
            resolved_paths.add(f'plugins/{plugin_name}/description.json')

        # try to find new hashes from these paths
        return discover_hashes(unknown_hashes, resolved_paths)

    @staticmethod
    def guess_hashes_from_known(known_hashes, unknown_hashes):
        logger.info("guessing hashes from known path patterns")

        langs = [l.value for l in Language]
        re_plugin_region_lang = re.compile(r'^plugins/([^/]+)/([^/]+)/([^/]+)/')

        champions = set()
        re_tmp = re.compile(r'^plugins/rcp-be-lol-game-data/global/default/(?:assets|data)/characters/(.*?)/')
        for path in known_hashes.values():
            m = re_tmp.match(path)
            if m:
                champions.add(m.group(1))
        champions = sorted(champions)

        new_paths = set()

        # ward skins
        new_paths |= {f'plugins/rcp-be-lol-game-data/global/default/content/src/leagueclient/wardskinimages/wardhero_{i}.png' for i in range(1000)}
        new_paths |= {f'plugins/rcp-be-lol-game-data/global/default/content/src/leagueclient/wardskinimages/wardheroshadow_{i}.png' for i in range(1000)}

        # summoner icons
        new_paths |= {f'plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/{i}.jpg' for i in range(5000)}

        # ultimate skins
        new_paths |= {f'plugins/rcp-be-lol-game-data/global/default/v1/summoner-backdrops/{i}.jpg' for i in range(5000)}
        new_paths |= {f'plugins/rcp-be-lol-game-data/global/default/v1/summoner-backdrops/{i}.webm' for i in range(5000)}

        # loot
        new_paths |= {f'plugins/rcp-fe-lol-loot/global/default/assets/loot_item_icons/chest_{i}.png' for i in range(1000)}
        new_paths |= {f'plugins/rcp-fe-lol-loot/global/default/assets/loot_item_icons/chest_{i}_open.png' for i in range(1000)}
        new_paths |= {f'plugins/rcp-fe-lol-loot/global/default/assets/loot_item_icons/material_{i}.png' for i in range(1000)}

        # runes (perks)
        for i in range(8000, 8500, 100):
            new_paths |= {f'plugins/rcp-fe-lol-perks/global/default/images/inventory-card/{i}/p{i}_s{j}_k{k}.jpg'
                          for j in [0] + list(range(8000, 8500, 100))
                          for k in [0] + list(range(8000, 8500))
                         }
            paths = ['environment.jpg', 'construct.png']
            paths += [f'keystones/{j}.png' for j in range(8000, 8500)]
            paths += [f'second/{j}.png' for j in range(8000, 8500)]
            new_paths |= {f'plugins/rcp-fe-lol-perks/global/default/images/construct/{i}/{p}' for p in paths}

        # spells
        new_paths |= {f'plugins/rcp-fe-lol-champ-select/global/default/sounds/sfx-spellchoose-{i}.ogg' for i in range(100)}

        # champion resources
        for cid in range(1000):
            new_paths |= {
                f'plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/{cid}.jpg',
                f'plugins/rcp-be-lol-game-data/global/default/v1/champion-ban-vo/{cid}.ogg',
                f'plugins/rcp-be-lol-game-data/global/default/v1/champion-choose-vo/{cid}.ogg',
                f'plugins/rcp-be-lol-game-data/global/default/v1/champion-sfx-audio/{cid}.ogg',
                f'plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/{cid}/metadata.json',
            }
            # skins and chromas
            for skin_id in range(cid * 1000, (cid + 1) * 1000):
                new_paths |= {
                    f'plugins/rcp-be-lol-game-data/global/default/v1/champion-tiles/{cid}/{skin_id}.jpg',
                    f'plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/{cid}/{skin_id}.jpg',
                    f'plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/uncentered/{cid}/{skin_id}.jpg',
                    f'plugins/rcp-be-lol-game-data/global/default/v1/champion-chroma-images/{cid}/{skin_id}.png',
                    f'plugins/rcp-be-lol-game-data/global/default/v1/champion-splash-videos/{cid}/{skin_id}.webm',
                    f'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/champion_skin_{skin_id}.png',
                    f'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/champion_skin_rental_{skin_id}.png',
                    f'plugins/rcp-fe-lol-skins-viewer/global/default/video/collection/{cid * 1000 + skin_id}.webm',
                }

        recommended_suffixes = (
            'beginner', 'sr', 'mid', 'top', 'support', 'srsupport', 'aram',
            'tt', 'sg', 'cs', 'asc', 'firstblood', 'kingporo', 'bt', 'dm',
            'map12t', 'pg', 'pr17', 'siege',
        )
        loadscreen_formats = ['plugins/rcp-be-lol-game-data/global/default/assets/characters/%(champion)s/skins/base/%(champion)sloadscreen.png']
        loadscreen_formats += ['plugins/rcp-be-lol-game-data/global/default/assets/characters/%%(champion)s/skins/skin%02d/%%(champion)sloadscreen_%d.png' % (i, i) for i in range(100)]
        loadscreen_formats += ['plugins/rcp-be-lol-game-data/global/default/assets/characters/%%(champion)s/skins/skin%02d/%%(champion)sloadscreen_%d.skins_%%(champion)s_skin%02d.png' % (i, i, i) for i in range(100)]
        loadscreen_formats += [s.replace('/assets/', '/data/') for s in loadscreen_formats]
        for champion in champions:
            # recommended item sets
            new_paths.add(f'plugins/rcp-be-lol-game-data/global/default/data/characters/{champion}/recommended/beginner.json')
            new_paths |= {
                f'plugins/rcp-be-lol-game-data/global/default/data/characters/{champion}/recommended/{champion}{s}.json'
                for s in recommended_suffixes
            }
            # loadscreens
            new_paths |= {fmt % {'champion': champion} for fmt in loadscreen_formats}

        # sanitizer
        paths = set()
        for i in range(5):
            for action in ('filter', 'unfilter'):
                paths |= {f'{i}.{action}.csv'}
                paths |= {f'{i}.{action}.language.{x.split("_")[0]}.csv' for x in langs}
                paths |= {f'{i}.{action}.country.{x.split("_")[1]}.csv' for x in langs}
                paths |= {f'{i}.{action}.region.{x}c.csv' for x in REGIONS}
                paths |= {f'{i}.{action}.locale.{x}.csv' for x in langs}
        for p in 'allowedchars breakingchars projectedchars projectedchars1337 punctuationchars variantaliases'.split():
            paths |= {f'{p}.locale.{x}.txt' for x in langs}
            paths |= {f'{p}.language.{x.split("_")[0]}.txt' for x in langs}
        new_paths |= {f'plugins/rcp-be-sanitizer/global/default/{p}' for p in paths}

        logger.info("building hashes for alternate regions and languages")

        for path in known_hashes.values():
            ext = path.rsplit('.', 1)[1]
            if ext in ('json', 'ogg', 'js', 'txt'):
                # try language variants
                new_paths |= {re_plugin_region_lang.sub(r'plugins/\1/\2/%s/' % lang, path) for lang in langs}
            elif ext in ('png', 'jpg', 'webm'):
                # try region variants
                new_paths |= {re_plugin_region_lang.sub(r'plugins/\1/%s/\3/' % region, path) for region in REGIONS}

        # try to find new hashes from these paths
        return discover_hashes(unknown_hashes, new_paths - set(known_hashes.values()))


_default_hashes = None  # cached
_default_hashes_path = os.path.join(os.path.dirname(__file__), "hashes.txt")

def load_hashes(fname=None) -> HashMap:
    if fname is None:
        global _default_hashes
        if _default_hashes is None:
            _default_hashes = load_hashes(_default_hashes_path)
        return _default_hashes

    if fname.endswith('.json'):
        with open(fname) as f:
            hashes = json.load(f)
    else:
        with open(fname) as f:
            hashes = dict(l.strip().split(' ', 1) for l in f)
    return {int(h, 16): path for h, path in hashes.items()}


def save_hashes(fname, hashes: HashMap) -> None:
    if fname is None:
        fname = _default_hashes_path
    if fname.endswith('.json'):
        with open(fname, 'w', newline='') as f:
            json.dump(hashes, f)
    else:
        with open(fname, 'w', newline='') as f:
            for h, path in sorted(hashes.items(), key=lambda kv: kv[1]):
                print(f"{h:016x} {path}", file=f)


def discover_hashes(unknown_hashes: HashMap, paths: Iterable[str]) -> HashMap:
    """Find new paths from a list and return them"""
    new_hashes = {}
    for path in paths:
        if path == '?':
            continue
        h = xxhash.xxh64(path).intdigest()
        if h in unknown_hashes:
            new_hashes[h] = path
    return new_hashes
