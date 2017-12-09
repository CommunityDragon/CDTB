#!/usr/bin/env python3
import os
import re
import struct
import zlib
import gzip
import json
import imghdr
import logging
import posixpath
import xxhash
import zstd
# support both zstd and zstandard implementations
if hasattr(zstd, 'decompress'):
    zstd_decompress = zstd.decompress
else:
    zstd_decompress = zstd.ZstdDecompressor().decompress

logger = logging.getLogger("wad")


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


class WadFileHeader:
    """
    Single file entry in a WAD archive
    """

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
        raise ValueError("unsupported file type: %d" % self.type)

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
    """
    WAD archive
    """

    def __init__(self, path):
        self.path = path
        self.version = None
        self.files = None

    def parse_headers(self):
        """Parse version and file list"""

        logger.debug("parse headers of %s", self.path)
        with open(self.path, 'rb') as f:
            parser = Parser(f)
            magic, version_major, version_minor = parser.unpack("<2sBB")
            if magic != b'RW':
                raise ValueError("invalid magic code")
            self.version = (version_major, version_minor)

            if version_major == 2:
                parser.seek(88)
            elif version_major == 3:
                parser.seek(256)
            else:
                raise ValueError("unsupported WAD version: %d.%d" % (version_major, version_minor))

            unk, entry_header_offset, entry_header_cell_size, entry_count = parser.unpack("<QHHI")
            self.files = [WadFileHeader(*parser.unpack("<QIIIBBBBQ")) for _ in range(entry_count)]

    def resolve_paths(self, hashes):
        """Guess path and/or extension of files"""

        for wadfile in self.files:
            if wadfile.path_hash in hashes:
                wadfile.path = hashes[wadfile.path_hash]
                wadfile.ext = wadfile.path.split('.', 1)[1]

    def guess_extensions(self):
        with open(self.path, 'rb') as f:
            for wadfile in self.files:
                if not wadfile.path and not wadfile.ext:
                    data = wadfile.read_data(f)
                    wadfile.ext = WadFileHeader.guess_extension(data)


    def extract(self, output):
        """Extract WAD file"""

        logger.info("extracting %s to %s", self.path, output)
        assert self.files is not None, "parse_headers() must be called before extract()"

        with open(self.path, 'rb') as fwad:
            for wadfile in self.files:
                path = wadfile.path
                if path is None:
                    path = 'unknown/%016x' % wadfile.path_hash
                    if wadfile.ext:
                        path += '.%s' % wadfile.ext
                output_path = os.path.join(output, path)

                logger.info("extracting %016x %s", wadfile.path_hash, path if path else '?')

                fwad.seek(wadfile.offset)
                # assume files are small enough to fit in memory
                data = wadfile.read_data(fwad)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as fout:
                    fout.write(data)

    def guess_hashes(self, unknown_hashes):
        """Try to guess hashes"""

        logger.info("guessing hashes from %s", self.path)

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
                    # retrieve plugin_name from description.json
                    if 'pluginDependencies' in jdata and 'name' in jdata:
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
                found_paths |= {'%s/template.html' % m.group(1) for m in re.finditer(r'<template id="[^"]*-template-([^"]+)"', data)}

        # hashed paths are always lowercased, do the same
        found_paths = {p.lower() for p in found_paths}

        if not plugin_name:
            # try to guess plugin_name from path
            # this will work when loading a wad in a RADS tree
            plugin_name = os.path.basename(os.path.dirname(os.path.abspath(self.path)))
            if not plugin_name.startswith('rcp-'):
                plugin_name = None
        default_path = f"plugins/{plugin_name}/global/default" if plugin_name else None

        # resolve parsed paths, using plugin name, known subdirs, ...
        for path in found_paths:
            basename = posixpath.basename(path)

            # /fe/{plugin}/{subpath} -> plugins/rcp-[bf]e-{plugin}/global/default/{subpath}
            # /lol-{name}/{subpath}  -> plugins/rcp-[bf]e-lol-{name}/global/default/{subpath}
            m = re.match(r'/(fe/|lol-)([^/]+)/(.*)', path)
            if m:
                prefix, plugin, subpath = m.groups()
                if prefix  == 'lol-':
                    plugin = f"lol-{plugin}"
                resolved_paths.add(f"plugins/rcp-fe-{plugin}/global/default/{subpath}")
                resolved_paths.add(f"plugins/rcp-be-{plugin}/global/default/{subpath}")
                continue

            # starting with './' or '../' without extension, try node module file
            m = re.match(r'\.+/(.*/[^.]+)$', path)
            if m:
                subpath = path.lstrip('./')  # strip all './' and '../' leading parts
                for prefix in ('components', 'components/elements', 'components/dropdowns', 'components/components'):
                    resolved_paths |= {f"{prefix}{suffix}" for suffix in ('.js', '.js.map', '/index.js', '/index.js.map')}

            if default_path:
                # known subdirectories
                m = re.match(r'\b((?:data|assets|images|audio|components|sounds|video|css)/.+)', path)
                if m:
                    subpath = m.group(1)
                    resolved_paths.add(f"{default_path}/{subpath}")
                    resolved_paths.add(f"{default_path}/{posixpath.dirname(subpath)}")
                # combine basename and subpath with known directories
                for subpath in (basename, path.lstrip('./')):
                    resolved_paths.add(f"{default_path}/{subpath}")
                    resolved_paths |= {f"{default_path}/{subdir}/{subpath}" for subdir in (
                        'components', 'components/elements', 'components/dropdowns', 'components/components',
                        'images', 'audio', 'sounds', 'video', 'mograph', 'css',
                        'assets', 'assets/images', 'assets/audio', 'assets/sounds', 'assets/video', 'assets/mograph',
                    )}

        # add common names at root
        if default_path:
            resolved_paths |= {f"{default_path}/{name}" for name in (
                'description.json', 'index.html',
                'init.js', 'init.js.map', 'bundle.js', 'trans.js',
            )}
            resolved_paths |= {f"{default_path}/{i}.bundle.js" for i in range(10)}

        # try to find new hashes from these paths
        discovered_hashes = {}
        for path in resolved_paths:
            h = xxhash.xxh64(path).intdigest()
            if h in unknown_hashes:
                discovered_hashes[h] = path

        return discovered_hashes

    @staticmethod
    def guess_hashes_from_known(known_hashes, unknown_hashes):
        logger.info("guessing hashes from known path patterns")

        regions = 'euw na tr br eune jp kr lan las oce ru la1 la2 oc1 eun id la oc ph sg th vn cn tw pbe garena2 garena3 tencent'.split()
        langs = 'el_gr en_au en_gb en_ph en_sg en_us es_ar es_es es_mx fr_fr hu_hu id_id it_it ja_jp ko_kr ms_my pl_pl pt_br ro_ro ru_ru th_th tr_tr vn_vn zh_cn zh_my zh_tw'.split()
        re_plugin_region_lang = re.compile(r'^plugins/([^/]+)/([^/]+)/([^/]+)/')

        new_paths = set()

        # ward skins
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/content/src/leagueclient/wardskinimages/wardhero_%d.png' % i for i in range(1000)}
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/content/src/leagueclient/wardskinimages/wardheroshadow_%d.png' % i for i in range(1000)}

        # summoner icons
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/%d.jpg' % i for i in range(5000)}

        # ultimate skins
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/summoner-backdrops/%d.jpg' % i for i in range(5000)}
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/summoner-backdrops/%d.webm' % i for i in range(5000)}

        # hextech
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/chest_%d.png' % i for i in range(1000)}
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/chest_%d_open.png' % i for i in range(1000)}
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/loottable_chest_%d.png' % i for i in range(1000)}
        new_paths |= {'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/loottable_chest_%d_%d.png' % (i, j) for i in range(1000) for j in range(4)}

        # runes (perks)
        for i in range(8000, 8500, 100):
            new_paths |= {'plugins/rcp-fe-lol-perks/global/default/images/inventory-card/%d/p%d_s%d_k%d.jpg' % (i, i, j, k)
                          for j in [0] + list(range(8000, 8500, 100))
                          for k in [0] + list(range(8000, 8500, 1))
                          }
            paths = ['environment.jpg', 'construct.png']
            paths += ['keystones/%d.png' % (i + j) for j in range(100)]
            paths += ['second/%d.png' % (i + j) for j in range(100)]
            new_paths |= {'plugins/rcp-fe-lol-perks/global/default/images/construct/%d/%s' % (i, p) for p in paths}

        # champion resources
        for cid in range(1000):
            new_paths |= {
                'plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/%d.jpg' % cid,
                'plugins/rcp-be-lol-game-data/global/default/v1/champion-ban-vo/%d.ogg' % cid,
                'plugins/rcp-be-lol-game-data/global/default/v1/champion-choose-vo/%d.ogg' % cid,
                'plugins/rcp-be-lol-game-data/global/default/v1/champion-sfx-audio/%d.ogg' % cid,
                'plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/%d/metadata.json' % cid,
            }
            # skins and chromas
            for skin_id in range(cid * 1000, (cid + 1) * 1000):
                new_paths |= {
                    'plugins/rcp-be-lol-game-data/global/default/v1/champion-tiles/%d/%d.jpg' % (cid, skin_id),
                    'plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/%d/%d.jpg' % (cid, skin_id),
                    'plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/uncentered/%d/%d.jpg' % (cid, skin_id),
                    'plugins/rcp-be-lol-game-data/global/default/v1/champion-chroma-images/%d/%d.png' % (cid, skin_id),
                    'plugins/rcp-be-lol-game-data/global/default/v1/champion-splash-videos/%d/%d.webm' % (cid, skin_id),
                    'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/champion_skin_%d.png' % skin_id,
                    'plugins/rcp-be-lol-game-data/global/default/v1/hextech-images/champion_skin_rental_%d.png' % skin_id,
                    'plugins/rcp-fe-lol-skins-viewer/global/default/video/collection/%d.webm' % (cid * 1000 + skin_id),
                }

        #TODO
        # plugins/rcp-be-lol-game-data/global/default/data/characters/{name}/skins/skin{NN}/{name}loadscreen_{N}.png

        logger.info("building hashes for alternate regions and languages")

        for path in known_hashes.values():
            ext = path.rsplit('.', 1)
            if ext in ('json', 'ogg'):
                # try language variants
                new_paths |= {re_plugin_region_lang.sub(r'plugins/\1/\2/%s/' % lang, path) for lang in langs}
            elif ext in ('png', 'jpg', 'webm'):
                # try region variants
                new_paths |= {re_plugin_region_lang.sub(r'plugins/\1/%s/\3/' % region, path) for region in regions}

        discovered_hashes = {}
        for path in new_paths:
            h = xxhash.xxh64(path).intdigest()
            if h in unknown_hashes:
                discovered_hashes[h] = path

        return discovered_hashes


def load_hashes(fname):
    if not fname:
        return None
    if fname.endswith('.json'):
        with open(fname) as f:
            hashes = json.load(f)
    else:
        with open(fname) as f:
            hashes = dict(l.strip().split(' ', 1) for l in f)
    return {int(h, 16): path for h, path in hashes.items()}

def save_hashes(fname, hashes):
    if fname.endswith('.json'):
        with open(fname, 'w', newline='') as f:
            json.dump(hashes, f)
    else:
        with open(fname, 'w', newline='') as f:
            for h, path in sorted(hashes.items(), key=lambda kv: kv[1]):
                print("%016x %s" % (h, path), file=f)


def command_extract(parser, args):
    if not os.path.isfile(args.wad):
        parser.error("WAD file does not exist")
    if not args.output:
        args.output = os.path.splitext(args.wad)[0]
    if os.path.exists(args.output) and not os.path.isdir(args.output):
        parser.error("output is not a directory")

    hashes = load_hashes(args.hashes)
    wad = Wad(args.wad)
    wad.parse_headers()
    if hashes:
        wad.resolve_paths(hashes)
    wad.guess_extensions()
    wad.extract(args.output)


def command_list(parser, args):
    if not os.path.isfile(args.wad):
        parser.error("WAD file does not exist")

    hashes = load_hashes(args.hashes)
    wad = Wad(args.wad)
    wad.parse_headers()
    if hashes:
        wad.resolve_paths(hashes)

    wadfiles = [(wf.path or ('?.%s' % wf.ext if wf.ext else '?'), wf.path_hash) for wf in wad.files]
    for path, h in sorted(wadfiles):
        print("%016x %s" % (h, path))


def command_guess_hashes(parser, args):
    hashes = load_hashes(args.hashes)

    wads = [Wad(path) for path in args.wad]
    unknown_hashes = set()
    for wad in wads:
        wad.parse_headers()
        if hashes:
            wad.resolve_paths(hashes)
        unknown_hashes |= set(wadfile.path_hash for wadfile in wad.files)
    unknown_hashes -= set(hashes)

    new_hashes = {}
    for wad in wads:
        new_hashes.update(wad.guess_hashes(unknown_hashes))
    new_hashes.update(Wad.guess_hashes_from_known(hashes, unknown_hashes))

    for h, path in new_hashes.items():
        print("%016x %s" % (h, path))

    if args.update and new_hashes:
        hashes.update(new_hashes)
        save_hashes(args.hashes, hashes)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract WAD files")
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="be verbose")

    subparsers = parser.add_subparsers(dest='command', help="command")

    subparser = subparsers.add_parser('extract',
                                      help="extract a WAD file")
    subparser.add_argument('-o', '--output',
                           help="extract directory")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths (JSON or plain text)")
    subparser.add_argument('wad',
                           help="WAD file to extract")

    subparser = subparsers.add_parser('list',
                                      help="list WAD content")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths (JSON or plain text)")
    subparser.add_argument('wad',
                           help="WAD file to list")

    subparser = subparsers.add_parser('guess-hashes',
                                      help="guess hashes from WAD content")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths (JSON or plain text)")
    subparser.add_argument('-u', '--update', action='store_true',
                           help="update given hashes file")
    subparser.add_argument('wad', nargs='+',
                           help="WAD files to analyze")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        datefmt='%H:%M:%S',
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )
    if args.verbose >= 1:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    if args.verbose >= 2:
        logging.getLogger("requests").setLevel(logging.DEBUG)

    # use default hashes.txt from packages directory if available
    if hasattr(args, 'hashes') and args.hashes is None:
        default_hashes = os.path.join(os.path.dirname(__file__), 'hashes.txt')
        if os.path.isfile(default_hashes):
            args.hashes = default_hashes

    globals()["command_%s" % args.command.replace('-', '_')](parser, args)

if __name__ == "__main__":
    main()
