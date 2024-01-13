import os
import re
import io
import json
import time
import hashlib
import logging
from typing import List, Optional, Generator

from .storage import (
    Storage,
    PatchElement,
    PatchVersion,
    get_system_yaml_version,
    get_content_metadata_version,
)
from .tools import (
    BinaryParser,
    write_file_or_remove,
    zstd_decompress,
)

logger = logging.getLogger(__name__)


class PatcherChunk:
    def __init__(self, chunk_id, bundle, offset, size, target_size):
        self.chunk_id = chunk_id
        self.bundle = bundle
        self.offset = offset
        self.size = size
        self.target_size = target_size

class PatcherBundle:
    def __init__(self, bundle_id):
        self.bundle_id = bundle_id
        self.chunks = []

    def add_chunk(self, chunk_id, size, target_size):
        try:
            last_chunk = self.chunks[-1]
            offset = last_chunk.offset + last_chunk.size
        except IndexError:
            offset = 0
        self.chunks.append(PatcherChunk(chunk_id, self, offset, size, target_size))

class PatcherFile:
    def __init__(self, name, size, link, flags, chunks):
        self.name = name
        self.size = size
        self.link = link
        self.flags = flags
        self.chunks = chunks

    def hexdigest(self):
        """Compute a hash unique for this file content"""
        m = hashlib.sha1()
        for chunk in self.chunks:
            m.update(b"%016X" % chunk.chunk_id)
        return m.hexdigest()

    @staticmethod
    def langs_predicate(langs):
        """Return a predicate function for a locale filtering parameter"""
        if langs is False:
            # assume only locales flags follow this pattern
            return lambda f: f.flags is None or not any('_' in f and len(f) == 5 for f in f.flags)
        elif langs is True:
            return lambda f: True
        else:
            lang = langs.lower()  # compare lowercased
            return lambda f: f.flags is not None and any(f.lower() == lang for f in f.flags)


class PatcherManifest:
    def __init__(self, path_or_f=None):
        self.bundles = None
        self.chunks = None
        self.flags = None
        self.files = None

        if path_or_f is not None:
            if isinstance(path_or_f, str):
                with open(path_or_f, "rb") as f:
                    self.parse_rman(f)
            else:
                self.parse_rman(f)

    def filter_files(self, langs=True) -> List[PatcherFile]:
        """Filter files from the manifest with provided filters"""
        return filter(PatcherFile.langs_predicate(langs), self.files.values())

    def parse_rman(self, f):
        parser = BinaryParser(f)

        magic, version_major, version_minor = parser.unpack("<4sBB")
        if magic != b'RMAN':
            raise ValueError("invalid magic code")
        if (version_major, version_minor) != (2, 0):
            raise ValueError(f"unsupported RMAN version: {version_major}.{version_minor}")

        flags, offset, length, _manifest_id, _body_length = parser.unpack("<HLLQL")
        assert flags & (1 << 9)  # other flags not handled
        assert offset == parser.tell()

        f = io.BytesIO(zstd_decompress(parser.raw(length)))
        return self.parse_body(f)

    def parse_body(self, f):
        parser = BinaryParser(f)

        # header (unknown values, skip it)
        n, = parser.unpack('<l')
        parser.skip(n)

        # offsets to tables (convert to absolute)
        offsets_base = parser.tell()
        offsets = list(offsets_base + 4*i + v for i, v in enumerate(parser.unpack('<6l')))

        parser.seek(offsets[0])
        self.bundles = list(self._parse_table(parser, self._parse_bundle))

        parser.seek(offsets[1])
        self.flags = dict(self._parse_table(parser, self._parse_flag))

        # build a list of chunks, indexed by ID
        self.chunks = {chunk.chunk_id: chunk for bundle in self.bundles for chunk in bundle.chunks}

        parser.seek(offsets[2])
        file_entries = list(self._parse_table(parser, self._parse_file_entry))
        parser.seek(offsets[3])
        directories = {did: (name, parent) for name, did, parent in self._parse_table(parser, self._parse_directory)}

        # merge files and directory data
        self.files = {}
        for name, link, flag_ids, dir_id, filesize, chunk_ids in file_entries:
            while dir_id is not None:
                dir_name, dir_id = directories[dir_id]
                name = f"{dir_name}/{name}"
            if flag_ids is not None:
                flags = [self.flags[i] for i in flag_ids]
            else:
                flags = None
            file_chunks = [self.chunks[chunk_id] for chunk_id in chunk_ids]
            self.files[name] = PatcherFile(name, filesize, link, flags, file_chunks)

        # note: last two tables are unresolved


    @staticmethod
    def _parse_table(parser, entry_parser):
        count, = parser.unpack('<l')

        for _ in range(count):
            pos = parser.tell()
            offset, = parser.unpack('<l')
            parser.seek(pos + offset)
            yield entry_parser(parser)
            parser.seek(pos + 4)

    @classmethod
    def _parse_bundle(cls, parser):
        """Parse a bundle entry"""

        def parse_chunklist(parser):
            fields = cls._parse_field_table(parser, (
                ('chunk_id', '<Q'),
                ('compressed_size', '<L'),
                ('uncompressed_size', '<L'),
            ))
            return fields['chunk_id'], fields['compressed_size'], fields['uncompressed_size']

        fields = cls._parse_field_table(parser, (
            ('bundle_id', '<Q'),
            ('chunks_offset', 'offset'),
        ))

        bundle = PatcherBundle(fields['bundle_id'])
        parser.seek(fields['chunks_offset'])
        for (chunk_id, compressed_size, uncompressed_size) in cls._parse_table(parser, parse_chunklist):
            bundle.add_chunk(chunk_id, compressed_size, uncompressed_size)

        return bundle

    @staticmethod
    def _parse_flag(parser):
        parser.skip(4)  # skip offset table offset
        flag_id, offset, = parser.unpack('<xxxBl')
        parser.skip(offset - 4)
        return (flag_id, parser.unpack_string())

    @classmethod
    def _parse_file_entry(cls, parser):
        """Parse a file entry
        (name, link, flag_ids, directory_id, filesize, chunk_ids)
        """
        fields = cls._parse_field_table(parser, (
            ('file_id', '<Q'),
            ('directory_id', '<Q'),
            ('file_size', '<L'),
            ('name', 'str'),
            ('flags', '<Q'),
            None,
            None,
            ('chunks', 'offset'),
            None,
            ('link', 'str'),
            None,
            None,
            None,
        ))

        flag_mask = fields['flags']
        if flag_mask:
            flag_ids = [i+1 for i in range(64) if flag_mask & (1 << i)]
        else:
            flag_ids = None

        parser.seek(fields['chunks'])
        chunk_count, = parser.unpack('<L')  # _ == 0
        chunk_ids = list(parser.unpack(f'<{chunk_count}Q'))

        return (fields['name'], fields['link'], flag_ids, fields['directory_id'], fields['file_size'], chunk_ids)

    @classmethod
    def _parse_directory(cls, parser):
        """Parse a directory entry
        (name, directory_id, parent_id)
        """
        fields = cls._parse_field_table(parser, (
            ('directory_id', '<Q'),
            ('parent_id', '<Q'),
            ('name', 'str'),
        ))
        return (fields['name'], fields['directory_id'], fields['parent_id'])

    @staticmethod
    def _parse_field_table(parser, fields):
        entry_pos = parser.tell()
        fields_pos = entry_pos - parser.unpack('<l')[0]
        nfields = len(fields)
        output = {}
        parser.seek(fields_pos)
        parser.skip(2) # vtable size
        parser.skip(2) # object size
        for _, field, offset in zip(range(nfields), fields, parser.unpack(f'<{nfields}H')):
            if field is None:
                continue
            name, fmt = field
            if offset == 0 or fmt is None:
                value = None
            else:
                pos = entry_pos + offset
                parser.seek(pos)
                if fmt == 'offset':
                    value = pos + parser.unpack('<l')[0]
                elif fmt == 'str':
                    value = parser.unpack('<l')[0]
                    parser.seek(pos + value)
                    value = parser.unpack_string()
                else:
                    value = parser.unpack(fmt)[0]
            output[name] = value
        return output


class PatcherStorage(Storage):
    """
    Storage based on CDN with bundles and chunks

    File tree:
      channels/  -- mirror of CDN's channels/ directory
        public/
          bundles/
          releases/
      cdtb/  -- CDTB files and exported files
        channels/  -- obsolete (used for the previous Riot release versionning)
        releases/{patchline}/{timestamp}/  -- one directory per release (game/client pair)
          release.json  -- release information (notably manifest URLs)
          files/  -- release files, extracted from bundles
          patch_version.{elem}  -- cached patch version for element `name`
        releases/{patchline}/{region}/latest.timestamp  -- last timestamp version
        files/  -- extracted files, named after their hash (shared)

    One instance handles a single patchline, even if all channels are stored
    under the same file tree. This is because only bundles and chunks are
    shared between channels, not versions and extracted files.

    The `cdtb/files/` directory is used to avoid to extract (and store)
    multiple copies of the same file. Actual files are put in `cdtb/files/` and
    `channels/.../files/` contains symlinks to them.
    This can be disabled by setting the `use_extract_symlinks` option to false.

    Sometimes, HTTPS requests to clientconfig.rpg.riotgames.com are denied.
    If `clientconfig_data` is set, the provided file (if available) or URL is used.

    Configuration options:
      patchline -- the patchline name (`live` or `pbe`)
      region -- region from which use configuration
      use_extract_symlinks -- if false, disable use of symlinks for extracted files
      clientconfig_data -- file or URL to use as 'clientconfig.rpg.riotgames.com' data

    """

    storage_type = 'patcher'

    URL_BASE = "https://lol.dyn.riotcdn.net/"
    DEFAULT_PATCHLINE = 'live'
    CLIENT_LIVE_REGION = 'EUW'
    GAME_LIVE_PLATFORM = 'EUW1'

    def __init__(self, path, patchline=DEFAULT_PATCHLINE):
        super().__init__(path, self.URL_BASE)
        self.patchline = patchline
        self.use_extract_symlinks = True
        self.clientconfig_data = None

    @classmethod
    def from_conf_data(cls, conf):
        storage = cls(conf['path'], conf.get('patchline', cls.DEFAULT_PATCHLINE))
        if conf.get('use_extract_symlinks') is False:
            storage.use_extract_symlinks = False
        if 'clientconfig_data' in conf:
            storage.clientconfig_data = conf['clientconfig_data']
        return storage

    def base_release_path(self):
        return self.fspath(f"cdtb/releases/{self.patchline}")

    def iter_releases(self) -> List['PatcherRelease']:
        """Generate releases available in the storage, latest first"""

        base = self.base_release_path()
        if not os.path.isdir(base):
            return
        versions = []
        for version in os.listdir(base):
            try:
                versions.append(int(version))
            except ValueError:
                continue  # ignore extra files

        for version in sorted(versions, reverse=True):
            if os.path.isfile(f"{base}/{version}/release.json"):
                yield PatcherRelease(self, version)

    def patch_elements(self, stored=False):
        if not stored:
            # add latest release to the storage, if any
            self.fetch_latest_update()

        for release in self.iter_releases():
            for elem in release.elements():
                yield PatcherPatchElement(elem)

    def fetch_latest_update(self):
        """Fetch the latest release from the CDN"""

        release_info = {
            'client_patch_url': self.get_latest_client_manifest(),
            'game_patch_url': self.get_latest_game_manifest(),
        }

        latest_timestamp = self.latest_timestamp()
        if latest_timestamp is None:
            latest_release = None
        else:
            latest_release = PatcherRelease(self, latest_timestamp)
        if latest_release and release_info == latest_release.data:
            return  # already up to date

        # Create the release information file and update `latest.timestamp`
        timestamp = int(time.time())
        base = self.base_release_path()
        with write_file_or_remove(f"{base}/{timestamp}/release.json", binary=False) as f:
            json.dump(release_info, f)
        with write_file_or_remove(f"{base}/latest.timestamp", binary=False) as f:
            print(f"{timestamp}", file=f)

    def get_latest_client_manifest(self):
        url_or_path = self.clientconfig_data
        if url_or_path and not url_or_path.startswith('http://') and not url_or_path.startswith('https://') and os.path.exists(url_or_path):
            with open(url_or_path) as f:
                data = json.load(f)
        else:
            url = url_or_path or "https://clientconfig.rpg.riotgames.com/api/v1/config/public?namespace=keystone.products.league_of_legends.patchlines"
            r = self.s.get(url)
            r.raise_for_status()
            data = r.json()
        region = 'PBE' if self.patchline == 'pbe' else self.CLIENT_LIVE_REGION
        for config in data[f"keystone.products.league_of_legends.patchlines.{self.patchline}"]["platforms"]["win"]["configurations"]:
            if config['id'] == region:
                return config['patch_url']
        raise ValueError(f"client configuration not found for {self.patchline}")

    def get_latest_game_manifest(self):
        platform = 'PBE1' if self.patchline == 'pbe' else self.GAME_LIVE_PLATFORM
        r = self.s.get(f"https://sieve.services.riotcdn.net/api/v1/products/lol/version-sets/{platform}?q[platform]=windows&q[published]=true")
        r.raise_for_status()
        data = r.json()
        assert len(data["releases"]) == 1
        return data["releases"][-1]["download"]["url"]

    def latest_timestamp(self):
        path = f"{self.base_release_path()}/latest.timestamp"
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return int(f.read().strip())

    def download_manifest(self, id_or_url):
        """Download a manifest from its ID or full URL if needed, return its path in the storage"""

        if isinstance(id_or_url, str):
            id_or_url = id_or_url.replace(".secure.", ".")
            if not id_or_url.startswith(self.url):
                raise ValueError(f"unexpected base URL for manifest: {id_or_url}")
            m = re.match(r"^channels/public/releases/([0-9A-F]{16})\.manifest$", id_or_url[len(self.url):])
            if not m:
                raise ValueError(f"unexpected manifest URL format: {id_or_url}")
            manif_id = int(m.group(1), 16)
        else:
            manif_id = id_or_url

        path = f"channels/public/releases/{manif_id:016X}.manifest"
        self.download(path, None)
        return path

    def download_bundle(self, bundle_id):
        """Download a bundle from its ID, return its path in the storage"""

        path = f"channels/public/bundles/{bundle_id:016X}.bundle"
        self.download(path, None)
        return path

    def load_chunk(self, chunk: PatcherChunk):
        """Load chunk data from a bundle"""
        path = f"channels/public/bundles/{chunk.bundle.bundle_id:016X}.bundle"
        with open(self.fspath(path), "rb") as f:
            f.seek(chunk.offset)
            # assume chunk is compressed
            return zstd_decompress(f.read(chunk.size))

    def extract_file(self, file: PatcherFile, output, overwrite=False):
        """Extract a file from its chunks, which must be available"""

        if not overwrite and os.path.isfile(output) and os.path.getsize(output) == file.size:
            logger.debug(f"skip {file.name}: already built to {output}")
            return

        if self.use_extract_symlinks:
            real_output = self.fspath(f"cdtb/files/{file.hexdigest()}")
        else:
            real_output = output

        if not os.path.isfile(real_output):
            logger.debug(f"extract {file.name} to {real_output}")
            with write_file_or_remove(real_output) as f:
                for chunk in file.chunks:
                    f.write(self.load_chunk(chunk))

        if self.use_extract_symlinks:
            logger.debug(f"symlink {real_output} to {output}")
            try:
                os.remove(output)
            except OSError:
                pass
            output_dir = os.path.dirname(output)
            os.makedirs(output_dir, exist_ok=True)
            os.symlink(os.path.relpath(real_output, output_dir), output)


class PatcherRelease:
    """
    A single released version
    """

    def __init__(self, storage: PatcherStorage, version):
        self.storage = storage
        self.version = version
        self.storage_dir = f"{storage.base_release_path()}/{version}"
        with open(f"{self.storage_dir}/release.json") as f:
            self.data = json.load(f)

    def __str__(self):
        return f"patcher:v{self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.version}>"

    def element(self, name) -> Optional['PatcherReleaseElement']:
        """Retrieve element with given name, None if not available"""

        if not self.data.get(f"{name}_patch_url"):
            return None
        return PatcherReleaseElement(self, name)

    def available_elements(self):
        """Return the name of elements available in this release"""
        return [name for name in PatchElement.names if self.data.get(f"{name}_patch_url")]

    def elements(self) -> Generator['PatcherReleaseElement', None, None]:
        """Iterate over available elements"""
        for name in PatchElement.names:
            elem = self.element(name)
            if elem is not None:
                yield elem

    def download_bundles(self, langs=True):
        """Download bundles from CDN for the release"""

        for elem in self.elements():
            elem.download(langs=langs)

    def extract(self, langs=True, overwrite=False):
        """Extract release files from downloaded bundles"""

        for elem in self.elements():
            elem.extract(langs=langs, overwrite=overwrite)


class PatcherReleaseElement:
    """
    Element of a release (game or client)
    """

    def __init__(self, release: PatcherRelease, name):
        self.release = release
        self.name = name
        self._manif = None
        self.manif_url = self.release.data.get(f"{self.name}_patch_url")

    @property
    def manif(self):
        if self._manif is None:
            if not self.manif_url:
                raise ValueError("no manifest URL found for {self}")
            path = self.release.storage.download_manifest(self.manif_url)
            self._manif = PatcherManifest(self.release.storage.fspath(path))
        return self._manif

    def __str__(self):
        return f"patcher:v{self.release.version}:{self.name}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.release.version} {self.name}>"

    def bundle_ids(self, langs=True) -> set:
        """Return IDs of bundles used by the element as a set"""

        files = [f for f in self.manif.filter_files(langs) if not f.link]
        return {chunk.bundle.bundle_id for f in files for chunk in f.chunks}

    def download_bundles(self, langs=True):
        """Download bundles from CDN"""

        logger.info(f"download bundles for {self}")
        for bundle_id in sorted(self.bundle_ids(langs=langs)):
            self.release.storage.download_bundle(bundle_id)

    def extract(self, langs=True, overwrite=False):
        """Extract files to the storage"""

        logger.info(f"extract files from {self}")
        files = [f for f in self.manif.filter_files(langs) if not f.link]
        for file in sorted(files, key=lambda f: f.name):
            self.extract_file(file, overwrite=overwrite)

    def extract_path(self, file: PatcherFile):
        """Return the path to which a file is extracted"""
        return f"{self.release.storage_dir}/files/{file.name}"

    def extract_file(self, file: PatcherFile, overwrite=False):
        """Extract a single file"""
        self.release.storage.extract_file(file, self.extract_path(file), overwrite=overwrite)

    def patch_version(self) -> Optional[PatchVersion]:
        """Return patch version or None if there is none

        This method reads/writes version from/to cache.
        """

        # for PBE: version is always "main"
        if self.release.storage.patchline == "pbe":
            return PatchVersion("main")

        cache = f"{self.release.storage_dir}/patch_version.{self.name}"
        if os.path.isfile(cache):
            logger.debug(f"retrieving patch version for {self} from cache")
            with open(cache) as f:
                version = f.read().strip()
                version = PatchVersion(version) if version else None
        else:
            version = self._retrieve_patch_version()
            if version is None:
                logger.warning(f"failed to retrieve patch version of {self}")
            else:
                with open(cache, 'w') as f:
                    f.write(f"{version}\n")
        return version

    def _retrieve_patch_version(self) -> Optional[PatchVersion]:
        """Retrieve patch version from files (no cache handling)

        Return None if there is no patch version (for instance, because files
        are not available anymore).
        Raise an exception if patch version cannot be retrieved.
        """

        logger.debug(f"retrieving patch version for {self}")

        retrievers = {
            # elem_name: (file_name, extractor)
            'client': ('system.yaml', get_system_yaml_version),
            'game': ('content-metadata.json', get_content_metadata_version),
        }

        file_name, extractor = retrievers[self.name]
        file = self.manif.files[file_name]
        # download and extract file if needed
        for bundle_id in {chunk.bundle.bundle_id for chunk in file.chunks}:
            self.release.storage.download_bundle(bundle_id)
        self.extract_file(file)

        version = extractor(self.extract_path(file))
        return PatchVersion(version)


class PatcherPatchElement(PatchElement):
    """Patch element from a patcher storage"""

    def __init__(self, elem: PatcherReleaseElement):
        self.elem = elem
        version = elem.patch_version()
        super().__init__(elem.name, version)

    def download(self, langs=True):
        self.elem.download_bundles(langs=langs)
        self.elem.extract(langs=langs)

    def fspaths(self, langs=True):
        return (self.elem.extract_path(f) for f in self.elem.manif.filter_files(langs=langs))

    def relpaths(self, langs=True):
        return (f.name.lower() for f in self.elem.manif.filter_files(langs=langs))

    def paths(self, langs=True):
        for f in self.elem.manif.filter_files(langs=langs):
            yield (self.elem.extract_path(f), f.name.lower())

