import os
import re
import io
import json
import hashlib
import logging
from typing import List, Optional, Generator

from .storage import (
    Storage,
    PatchElement,
    PatchVersion,
    get_system_yaml_version,
    get_exe_version,
)
from .tools import (
    BinaryParser,
    write_file_or_remove,
    zstd_decompress,
)
from .data import Language

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
    def __init__(self, name, size, link, langs, chunks):
        self.name = name
        self.size = size
        self.link = link
        self.langs = langs
        self.chunks = chunks

    def hexdigest(self):
        """Compute a hash unique for this file content"""
        m = hashlib.sha1()
        for chunk in self.chunks:
            m.update(b"%016X" % chunk.chunk_id)
        return m.hexdigest()

    @staticmethod
    def langs_predicate(langs):
        """Return a predicate function for a `langs` filtering parameter"""
        if langs is False:
            return lambda f: f.langs is None
        elif langs is True:
            return lambda f: True
        elif isinstance(langs, Language):
            return lambda f: f.langs == [langs]
        else:
            return lambda f: f.langs is not None and langs in f.langs


class PatcherManifest:
    def __init__(self, path_or_f=None):
        self.bundles = None
        self.chunks = None
        self.langs = None
        self.files = None

        if path_or_f is not None:
            if isinstance(path_or_f, str):
                with open(path_or_f, "rb") as f:
                    self.parse_rman(f)
            else:
                self.parse_rman(f)

    def filter_files(self, langs=True) -> List[PatcherFile]:
        """Filter files from the manifest with provided language(s)"""
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
        offsets = list(offsets_base + 4*i + v for i, v in enumerate(parser.unpack(f'<6l')))

        parser.seek(offsets[0])
        self.bundles = list(self._parse_table(parser, self._parse_bundle))

        parser.seek(offsets[1])
        self.langs = {k: Language(v.lower()) for k, v in self._parse_table(parser, self._parse_lang)}

        # build a list of chunks, indexed by ID
        self.chunks = {chunk.chunk_id: chunk for bundle in self.bundles for chunk in bundle.chunks}

        parser.seek(offsets[2])
        file_entries = list(self._parse_table(parser, self._parse_file_entry))
        parser.seek(offsets[3])
        directories = {did: (name, parent) for name, did, parent in self._parse_table(parser, self._parse_directory)}

        # merge files and directory data
        self.files = {}
        for _, name, link, lang_ids, dir_id, filesize, chunk_ids in file_entries:
            while dir_id is not None:
                dir_name, dir_id = directories[dir_id]
                name = f"{dir_name}/{name}"
            if lang_ids is not None:
                langs = [self.langs[i] for i in lang_ids]
            else:
                langs = None
            file_chunks = [self.chunks[chunk_id] for chunk_id in chunk_ids]
            self.files[name] = PatcherFile(name, filesize, link, langs, file_chunks)

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

    @staticmethod
    def _parse_bundle(parser):
        """Parse a bundle entry"""
        _, n, bundle_id = parser.unpack('<llQ')
        # skip remaining header part, if any
        parser.skip(n - 12)

        bundle = PatcherBundle(bundle_id)
        n, = parser.unpack('<l')
        for _ in range(n):
            pos = parser.tell()
            offset, = parser.unpack('<l')
            parser.seek(pos + offset)
            parser.skip(4)  # skip offset table offset
            compressed_size, uncompressed_size, chunk_id = parser.unpack('<LLQ')
            bundle.add_chunk(chunk_id, compressed_size, uncompressed_size)
            parser.seek(pos + 4)

        return bundle

    @staticmethod
    def _parse_lang(parser):
        parser.skip(4)  # skip offset table offset
        lang_id, offset, = parser.unpack('<xxxBl')
        parser.skip(offset - 4)
        return (lang_id, parser.unpack_string())

    @staticmethod
    def _parse_file_entry(parser):
        """Parse a file entry
        (flags, name, link, lang_ids, directory_id, filesize, chunk_ids)
        """
        parser.skip(4)  # skip offset table offset
        pos = parser.tell()

        flags, = parser.unpack('<L')
        if flags == 0x00010200 or (flags >> 24) != 0:
            name_offset, = parser.unpack('<l')
        else:
            name_offset = flags - 4
            flags = 0

        struct_size, link_offset, _file_id = parser.unpack('<llQ')
        # note: name and link_offset are read later, at the end

        if struct_size > 28:
            directory_id, = parser.unpack('<Q')
        else:
            directory_id = None

        filesize, _ = parser.unpack('<LL')  # _ == 0

        if struct_size > 36:
            lang_mask, = parser.unpack('<Q')
            lang_ids = [i+1 for i in range(64) if lang_mask & (1 << i)]
        else:
            lang_ids = None

        _, chunk_count = parser.unpack('<LL')  # _ == 0
        chunk_ids = list(parser.unpack(f'<{chunk_count}Q'))

        parser.seek(pos + 4 + name_offset)
        name = parser.unpack_string()
        parser.seek(pos + 12 + link_offset)
        link = parser.unpack_string()
        if not link:
            link = None

        return (flags, name, link, lang_ids, directory_id, filesize, chunk_ids)

    @staticmethod
    def _parse_directory(parser):
        """Parse a directory entry
        (name, directory_id, parent_id)
        """
        offset_table_offset, = parser.unpack('<l')
        pos = parser.tell()
        # get offsets for directory and parent IDs
        parser.skip(-offset_table_offset)
        directory_id_offset, parent_id_offset = parser.unpack('<hh')
        parser.seek(pos)

        name_offset, = parser.unpack('<l')
        # note: name is read later, at the end
        if directory_id_offset > 0:
            directory_id, = parser.unpack('<Q')
        else:
            directory_id = None
        if parent_id_offset > 0:
            parent_id, = parser.unpack('<Q')
        else:
            parent_id = None

        parser.seek(pos + name_offset)
        name = parser.unpack_string()

        return (name, directory_id, parent_id)


class PatcherStorage(Storage):
    """
    Storage based on CDN with bundles and chunks

    File tree:
      channels/  -- mirror of CDN's channels/ directory
        public/
          bundles/
          releases/
      cdtb/  -- CDTB files and exported files
        channels/{channel}/{version}/  -- one directory per channel and release version
          release.json  -- copy of release's JSON file
          files/  -- release files, extracted from bundles
          patch_version.{elem}  -- cached patch version for element `name`
        files/  -- extracted files, named after their hash (shared)

    One instance handles a single channel, even if all channels are stored
    under the same file tree. This is because only bundles and chunks are
    shared between channels, not versions and extracted files.

    The `cdtb/files/` directory is used to avoid to extract (and store)
    multiple copies of the same file. Actual files are put in `cdtb/files/` and
    `channels/.../files/` contains symlinks to them.
    This can be disabled by setting the `use_extract_symlinks` option to false.

    Configuration options:
      channel -- the channel name
      use_extract_symlinks -- if false, disable use of symlinks for extracted files

    """

    storage_type = 'patcher'

    URL_BASE = "https://lol.dyn.riotcdn.net/"
    DEFAULT_CHANNEL = 'live-euw-win'

    def __init__(self, path, channel=DEFAULT_CHANNEL):
        super().__init__(path, self.URL_BASE)
        self.channel = channel
        self.use_extract_symlinks = True

    @classmethod
    def from_conf_data(cls, conf):
        storage = cls(conf['path'], conf.get('channel', cls.DEFAULT_CHANNEL))
        if conf.get('use_extract_symlinks') is False:
            storage.use_extract_symlinks = False
        return storage

    def iter_releases(self) -> List['PatcherRelease']:
        """Generate releases available in the storage, latest first"""

        base = self.fspath(f"cdtb/channels/{self.channel}")
        if not os.path.isdir(base):
            return
        versions = []
        for version in os.listdir(base):
            try:
                versions.append(int(version))
            except ValueError:
                continue

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
        PatcherRelease.fetch_latest(self)

    def request_release_data(self):
        r = self.request_get(f"channels/public/{self.channel}.json")
        r.raise_for_status()
        return r.json()

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
        self.storage_dir = f"cdtb/channels/{storage.channel}/{version}"
        with open(self.storage.fspath(f"{self.storage_dir}/release.json")) as f:
            self.data = json.load(f)

    def __str__(self):
        return f"patcher:v{self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.version}>"

    @classmethod
    def fetch_latest(cls, storage: PatcherStorage):
        data = storage.request_release_data()
        version = data['version']
        # store data in the storage, at the right place
        path = storage.fspath(f"cdtb/channels/{storage.channel}/{version}/release.json")
        with write_file_or_remove(path, binary=False) as f:
            json.dump(data, f)
        return cls(storage, version)

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
        return self.release.storage.fspath(f"{self.release.storage_dir}/files/{file.name}")

    def extract_file(self, file: PatcherFile, overwrite=False):
        """Extract a single file"""
        self.release.storage.extract_file(file, self.extract_path(file), overwrite=overwrite)

    def patch_version(self) -> Optional[PatchVersion]:
        """Return patch version or None if there is none

        This method reads/writes version from/to cache.
        """

        # for PBE: version is always "main"
        if self.release.storage.channel == "pbe-pbe-win":  #XXX better check
            return PatchVersion("main")

        cache = self.release.storage.fspath(f"{self.release.storage_dir}/patch_version.{self.name}")
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
            'game': ('League of Legends.exe', get_exe_version),
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


class MultiPatcherStorage(Storage):
    """
    PatcherStorage merging multiple channels

    This storage always announce a single element which merge the latest
    elements of each individual sub-storage.

    Configuration options:
      channels -- the channel names

    """

    storage_type = 'multipatcher'

    DEFAULT_CHANNELS = tuple(f"live-{x}-win" for x in "br eune euw jp kr la1 la2 na oc1 ru tr".split())

    def __init__(self, path, channels=DEFAULT_CHANNELS):
        if not channels:
            raise ValueError("no channels")
        super().__init__(path, PatcherStorage.URL_BASE)
        self.substorages = [PatcherStorage(path, channel) for channel in channels]

    @classmethod
    def from_conf_data(cls, conf):
        return cls(conf['path'], conf.get('channels', cls.DEFAULT_CHANNELS))

    def patch_elements(self, stored=False):
        if not stored:
            # add latest releases to the storage, if any
            self.fetch_latest_update()

        # Peek next element for each storage.
        # Skip duplicate manifests, order by patch version then timestamp.
        manifest_urls = set()

        class Peeker:
            def __init__(self, it):
                self.it = it
                self.element = self.version = self.date = None

            def peek(self):
                while self.element is None:
                    try:
                        element = next(self.it)
                    except StopIteration:
                        return False
                    if element.manif_url in manifest_urls:
                        continue  # manifest already processed
                    manifest_urls.add(element.manif_url)
                    self.element = element
                    self.version = element.patch_version()
                    self.date = element.release.data["timestamp"]
                    break
                return True

            def consume(self):
                assert self.element is not None
                self.element = self.version = self.date = None

        peekers = [Peeker((e for r in substorage.iter_releases() for e in r.elements())) for substorage in self.substorages]
        current_elements = {}  # {name: [(date, elem)]}
        current_version = {}  # {name: version}

        while True:
            best_peeker = None
            for peeker in peekers:
                if not peeker.peek():
                    continue
                if best_peeker is None or (peeker.version, peeker.date) > (best_peeker.version, best_peeker.date):
                    best_peeker = peeker
            if best_peeker is None:
                break  # exhausted
            name = best_peeker.element.name

            if best_peeker.version != current_version.get(name):
                # new version: yield the previous one
                if name in current_elements:
                    yield MultiPatcherPatchElement(name, best_peeker.version, current_elements[name])
                current_elements[name] = []
                current_version[name] = best_peeker.version
            current_elements[name].append((best_peeker.date, best_peeker.element))
            best_peeker.consume()

        # don't forget the last versions
        for name, elems in current_elements.items():
            if elems:
                yield MultiPatcherPatchElement(name, current_version[name], elems)

    def fetch_latest_update(self):
        """Fetch the latest release from the CDN, for each substorage"""
        for substorage in self.substorages:
            substorage.fetch_latest_update()


class MultiPatcherPatchElement(PatchElement):
    """Patch element from a multi-patcher storage"""

    def __init__(self, name, version, dated_elements):
        super().__init__(name, version)
        self.elements = [e for d, e in sorted(dated_elements, key=lambda o: o[0], reverse=True)]
        files = {}  # {name: (elem, f)}
        for elem in self.elements:
            for fname, f in elem.manif.files.items():
                if fname not in files:
                    files[fname] = (elem, f)
        self.files = files.values()

    def download(self, langs=True):
        for elem in self.elements:
            # There must not be significant overhead for extracting everything,
            # including "duplicate" files. Even for extract, since symlinks are
            # used, it does not cost much. Moreoever, completely identical
            # elements (same manifest) have already been filtered out.
            elem.download_bundles(langs=langs)
            elem.extract(langs=langs)

    def fspaths(self, langs=True):
        pred = PatcherFile.langs_predicate(langs)
        return (elem.extract_path(f) for elem, f in self.files if pred(f))

    def relpaths(self, langs=True):
        pred = PatcherFile.langs_predicate(langs)
        return (f.name.lower() for elem, f in self.files if pred(f))

    def paths(self, langs=True):
        pred = PatcherFile.langs_predicate(langs)
        return ((elem.extract_path(f), f.name.lower()) for elem, f in self.files if pred(f))

