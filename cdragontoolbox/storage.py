import os
import re
import itertools
import json
import glob
from contextlib import contextmanager
from typing import List, Tuple, Union, Optional, Generator
import logging
import requests
import hachoir.parser
import hachoir.metadata

from .tools import write_file_or_remove

logger = logging.getLogger(__name__)


class BaseVersion:
    """Base wrapper class for version strings

    Version instances are comparable and hashable.
    """

    def __init__(self, v: Union[str, tuple]):
        if isinstance(v, str):
            self.s = v
            self.t = tuple(int(x) for x in v.split('.'))
        elif isinstance(v, tuple):
            self.s = '.'.join(str(x) for x in v)
            self.t = v
        else:
            raise TypeError(v)

    def __repr__(self):
        return f"{self.__class__.__qualname__}({self.s!r})"

    def __str__(self):
        return self.s

    def __lt__(self, other):
        return self.t < other.t

    def __le__(self, other):
        return self.t <= other.t

    def __gt__(self, other):
        return self.t > other.t

    def __ge__(self, other):
        return self.t >= other.t

    def __eq__(self, other):
        # allow to compare with any other version instance, string or tuple
        if isinstance(other, BaseVersion):
            return self.s == other.s
        elif isinstance(other, str):
            return self.s == other
        elif isinstance(other, tuple):
            return self.t == other
        else:
            return False

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.s)


class PatchVersion(BaseVersion):
    """Wrapper class for patch version numbers

    Patch versions are X.Y, where X is the season and Y the patch number, starting at 1.
    Mid-update patches (e.g. 8.23.2) are not handled.

    For PBE, the special version `main` is used.
    """

    def __init__(self, v: Union[str, tuple]):
        if isinstance(v, str) and v == "main":
            # make it comparable, but only with itself
            self.s = self.t = v
        else:
            super().__init__(v)
            # support more numbers but truncate to 2
            if len(self.t) > 2:
                self.t = self.t[:2]
                self.s = '.'.join(str(x) for x in self.t)
            assert len(self.t) == 2, "invalid patch version format"


class RequestStreamReader:
    """Wrapper for reading data from stream request"""

    DOWNLOAD_CHUNK_SIZE = 10 * 1024**2

    def __init__(self, r):
        self.it = r.iter_content(self.DOWNLOAD_CHUNK_SIZE)
        self.pos = 0
        self.buf = b''

    def copy(self, writer, n):
        """Read n bytes and write them using writer"""
        self.pos += n
        while n:
            if n <= len(self.buf):
                if writer:
                    writer(self.buf[:n])
                self.buf = self.buf[n:]
                return
            if writer and self.buf:
                writer(self.buf)
            n -= len(self.buf)
            self.buf = next(self.it)

    def skip(self, n):
        """Skip n bytes"""
        self.copy(None, n)

    def skip_to(self, pos):
        assert self.pos <= pos
        self.skip(pos - self.pos)


# registered storage classes
_storage_registry = {}

def load_storage_conf(path):
    with open(path) as f:
        conf = json.load(f)
    if 'type' not in conf:
        raise ValueError("storage configuration file must define its 'type'")
    conf['path'] = os.path.normpath(os.path.join(os.path.dirname(path), conf.get('path', '.')))
    return conf

def storage_conf_from_path(path):
    """Parse a path as supported by Storage.from_path()

    The returned conf is guaranteed to have a `type` and a `path` entries.
    """
    if os.path.isdir(path):
        conf_path = os.path.join(path, 'cdtb.storage.conf')
        if os.path.isfile(conf_path):
            return load_storage_conf(conf_path)
        else:
            conf = guess_storage_conf(path)
            if conf is None:
                raise ValueError(f"cannot guess storage configuration from '{path}'")
            return conf
    elif os.path.isfile(path):
        return load_storage_conf(path)
    elif ':' in path:
        storage_type, storage_path = path.split(':', 1)
        return {'type': storage_type, 'path': storage_path}
    else:
        return {'type': 'patcher', 'path': storage_path}

def guess_storage_conf(path):
    """Try to guess storage configuration from path"""

    if os.path.isdir(os.path.join(path, 'channels')):
        return {'type': 'patcher', 'path': path}
    return None


class StorageRegister(type):
    """Metaclass to register storage types"""

    def __new__(mcs, name, bases, class_dict):
        cls = type.__new__(mcs, name, bases, class_dict)
        if cls.storage_type is not None:
            _storage_registry[cls.storage_type] = cls
        return cls

class Storage(metaclass=StorageRegister):
    """
    Download and store game and client files

    Each storage is basically a directory in which files are downloaded and
    extracted if needed. Each storage type can define configuration options.
    """

    storage_type = None

    def __init__(self, path, url):
        self.path = path
        self.url = url
        self.s = requests.session()

    @staticmethod
    def from_path(path):
        """Return a storage from a path

        `path` can points to:
        - a storage configuration file
        - a directory containing a `cdtb.storage.conf` file
        - a directory (storage configuration will be guessed, if possible)
        - `type:dir_path` string
        """

        conf = storage_conf_from_path(path)
        if conf is None:
            raise ValueError(f"cannot retrieve storage configuration from '{path}'")
        return Storage.from_conf(conf)

    @staticmethod
    def from_conf(conf):
        try:
            cls = _storage_registry[conf['type']]
        except KeyError:
            raise ValueError(f"unknown storage type: {conf['type']}")
        return cls.from_conf_data(conf)

    @classmethod
    def from_conf_data(cls, conf):
        raise NotImplementedError()

    def request_get(self, path, **kwargs) -> requests.Response:
        """Request a path, returns a requests.Response object"""
        return self.s.get(self.url + path, **kwargs)

    def request_text(self, path) -> str:
        """Request a path, return content as text"""
        r = self.request_get(path)
        r.raise_for_status()
        r.encoding = 'utf-8'
        return r.text

    def fspath(self, path) -> str:
        """Return full path from a storage-relative path"""
        return os.path.join(self.path, path)

    def download(self, urlpath, path, force=False) -> None:
        """Download a path to disk
        If path is None, use urlpath's value.
        """

        if path is None:
            path = urlpath
        fspath = self.fspath(path)
        if not force and os.path.isfile(fspath):
            return

        logger.debug(f"download file: {path}")
        r = self.request_get(urlpath)
        r.raise_for_status()
        with write_file_or_remove(fspath) as f:
            f.write(r.content)

    @contextmanager
    def stream(self, urlpath) -> RequestStreamReader:
        """Request a path for streaming download"""
        with self.s.get(self.url + urlpath, stream=True) as r:
            r.raise_for_status()
            yield RequestStreamReader(r)

    def patch_elements(self, stored=False) -> Generator['PatchElement', None, None]:
        """Generate patch elements, sorted from the latest one

        If stored is True, only elements already in storage are used (to avoid
        downloading new files).

        Versions are generated so the caller can stop iterating when needed
        versions have been retrieved, avoiding to fetch all solutions.

        Note: patch versions are assumed to be monotonous in successive
        solution versions (they never decrease).

        For PBE, patch version is always 'main'.
        """

        raise NotImplementedError()

    def patch_element(self, name, version=None, stored=False) -> Optional['PatchElement']:
        """Retrieve a single patch element, None if not found

        If version if None, retrieve the latest one with given name.
        """

        for e in self.patch_elements(stored=stored):
            if e.name != name:
                continue
            if version is None or e.version == version:
                return e
        return None

    def patches(self, stored=False) -> Generator['Patch', None, None]:
        """Generate patch, sorted from the latest one

        See patch_elements() for additional remarks.
        """

        for _, group in itertools.groupby(self.patch_elements(stored=stored), key=lambda e: e.version):
            # keep latest sub-patch version of each element
            elements = {}
            for elem in group:
                if elem.name not in elements:
                    elements[elem.name] = elem
            yield Patch._create(list(elements.values()))

    def patch(self, version=None, stored=False) -> Optional['Patch']:
        """Retrieve a single patch, None if not found

        If version if None, retrieve the latest one.
        """

        it = self.patches(stored=stored)
        if version is None:
            return next(it)
        for p in it:
            if p.version == version:
                return p
        return None


class PatchElement:
    """
    Element of a patch (game or client)

    This base class must not be instantiated directly.

    In methods parameters, `langs` is used to filter language-specific files
    and can have the following values:
      False -- language-independent
      True -- all languages
      lang -- single given language
      [lang, ...] -- list of given languages

    """

    # valid names
    names = ('game', 'client')

    def __init__(self, name, version: PatchVersion):
        self.name = name
        assert name in self.names
        self.version = version

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.name} {self.version}>"

    def __eq__(self, other):
        if isinstance(other, PatchElement):
            return self.name == other.name and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.name, self.version))

    def download(self, langs=True):
        """Download files of this patch element to the storage"""
        raise NotImplementedError()

    def fspaths(self, langs=True) -> Generator[str, None, None]:
        """Generate the path on disk of files in the element"""
        raise NotImplementedError()

    def relpaths(self, langs=True) -> Generator[str, None, None]:
        """Generate the relative (export) path of files in the element, normalized"""
        raise NotImplementedError()

    def paths(self, langs=True) -> Generator[Tuple[str, str], None, None]:
        """Equivalent zip(fspaths(), relpaths())"""
        return zip(self.fspaths(langs=langs), self.relpaths(langs=langs))


class Patch:
    """
    A single League patch version (e.g. patch 8.1)

    This class cannot not be instantiated directly.
    Use patch() or patches() methods on Storage instances.
    """

    def __init__(self):
        raise RuntimeError("This class should not be instantiated by the user.")

    @classmethod
    def _create(cls, elements: List[PatchElement]):
        """Create a patch from its elements"""

        self = cls.__new__(cls)
        versions = {elem.version for elem in elements}
        if len(versions) != 1:
            raise ValueError("versions of patch elements mismatch")
        self.version = versions.pop()
        self.elements = elements
        return self

    def __str__(self):
        return f"patch={self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.version}>"

    def __eq__(self, other):
        if isinstance(other, Patch):
            return self.version == other.version
        return False

    def __hash__(self):
        return hash(self.version)

    def __lt__(self, other):
        if isinstance(other, Patch):
            return self.version > other.version
        return NotImplemented

    def latest(self):
        """Return a new patch with only latest version of each element name"""
        elements = []
        for _, group in itertools.groupby(self.elements, key=lambda e: e.name):
            elements.append(max(group, key=lambda e: e.version))
        return self._create(elements)

    def download(self, langs=True):
        for elem in self.elements:
            elem.download(langs=langs)


def get_system_yaml_version(path) -> str:
    with open(path) as f:
        for line in f:
            # TODO do proper yaml parsing
            # formats: Release/X.Y or 'X.Y'
            m = re.match(r"""^ *(?:game-|)branch: .*["'/]([0-9.]+)["']?$""", line)
            if m:
                return m.group(1)
        return None


def get_exe_version(path) -> str:
    """Return version from an executable"""

    parser = hachoir.parser.createParser(path)
    metadata = hachoir.metadata.extractMetadata(parser=parser)
    return metadata.get('version')


def get_content_metadata_version(path) -> str:
    """Return branch version from content-metadata.json file"""
    with open(path) as f:
        data = json.load(f)
        m = re.match(r"^(\d+\.\d+)\.", data['version'])
        if m:
            return m.group(1)
        return None


def parse_storage_component(storage: Storage, component: str) -> Union[None, Patch, PatchElement]:
    """Parse a component string representation to patch elements"""

    m = re.match(fr'^(patch|{"|".join(PatchElement.names)})=(|[0-9]+(?:\.[0-9]+\.?)*|main)$', component)
    if not m:
        raise ValueError(f"invalid component: {component}")
    name, version = m.group(1, 2)

    if version == '':
        version, latest = None, True
    elif version.endswith('.'):
        version, latest = version.rstrip('.'), True
    else:
        latest = False

    if name == 'patch':
        patch = storage.patch(version)
        if patch is None:
            return None
        if latest:
            patch = patch.latest()
        return patch
    else:
        return storage.patch_element(name, version, stored=version is not None)

