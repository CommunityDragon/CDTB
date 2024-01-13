import os
import re
import zlib
from typing import List, Dict, Union, Optional, Generator, Iterable
from collections import defaultdict
import logging
import requests

from .data import Language
from .tools import write_file_or_remove
from .storage import (
    BaseVersion,
    Storage,
    Patch,
    PatchElement,
    PatchVersion,
    get_system_yaml_version,
    get_exe_version,
)

logger = logging.getLogger(__name__)


class RadsVersion(BaseVersion):
    """Wrapper class for version strings used by RADS

    Solutions and projects all have individual version numbers (e.g. "0.0.1.30").
    The version numbers are actually 32-bit unsigned integers represented using dot-notation, exactly the same as the
    notation used for IPv4 addresses. Notably, each individual number caps at 255, so the version after 0.0.0.255 is
    0.0.1.0.
    """

    def __init__(self, v: Union[str, tuple]):
        super().__init__(v)
        assert len(self.t) == 4, "invalid RADS version format: "


class RadsStorage(Storage):
    """
    Storage based on RADS structure

    Configuration options:
      url -- storage URL (see examples below)
      cdn -- 'default', 'kr' or 'pbe' (incompatible with 'url')

    """

    storage_type = 'rads'

    # all available values are in system.yaml
    # values in use are in RADS/system/system.cfg
    # region is ignored here (it is not actually needed)
    DOWNLOAD_URL = "l3cdn.riotgames.com"
    DOWNLOAD_PATH = "/releases/live"
    DOWNLOAD_PATH_KR = "/KR_CBT"
    DOWNLOAD_PATH_PBE = "/releases/pbe"

    URL_DEFAULT = f"http://{DOWNLOAD_URL}{DOWNLOAD_PATH}/"
    URL_KR = f"http://{DOWNLOAD_URL}{DOWNLOAD_PATH_KR}/"
    URL_PBE = f"http://{DOWNLOAD_URL}{DOWNLOAD_PATH_PBE}/"

    def __init__(self, path, url=None):
        if url is None:
            url = self.URL_DEFAULT
        super().__init__(path, url)

    @classmethod
    def from_conf_data(cls, conf):
        if 'cdn' in conf:
            if 'url' in conf:
                raise ValueError("'url' and 'cdn' are mutually exclusive")
            url = getattr(cls, f"URL_{conf['cdn']}".upper())
        else:
            url = conf.get('url')
        return cls(conf['path'], url)

    def list_projects(self) -> List['RadsProject']:
        """List projects present in storage"""
        ret = []
        base = self.fspath("projects")
        for name in os.listdir(base):
            if os.path.isdir(f"{base}/{name}/releases"):
                ret.append(RadsProject(self, name))
        return ret

    def list_solutions(self) -> List['RadsSolution']:
        """List solutions present in storage"""
        ret = []
        base = self.fspath("solutions")
        for name in os.listdir(base):
            if os.path.isdir(f"{base}/{name}/releases"):
                ret.append(RadsSolution(self, name))
        return ret

    def patch_elements(self, stored=False):
        solution_names = ('league_client_sln', 'lol_game_client_sln')

        # peek next element for each solution
        class Peeker:
            def __init__(self, it):
                self.it = it
                self.cur = None

            def peek(self):
                if self.cur is None:
                    try:
                        self.cur = next(self.it)
                    except StopIteration:
                        pass
                return self.cur

            def consume(self):
                assert self.cur is not None
                self.cur = None

        # drop solution versions without a patch
        # convert them to patch elements
        def gen_solution_elements(name):
            solution = RadsSolution(self, name)
            for sv in solution.versions(stored=stored):
                patch = sv.patch_version()
                if patch is None:
                    continue
                yield RadsPatchElement(sv)

        # for each solution, peek the next elements to yield the highest version
        peekers = [Peeker(gen_solution_elements(name)) for name in solution_names]
        while True:
            best_peeker, best_elem = None, None
            for peeker in peekers:
                elem = peeker.peek()
                if elem is None:
                    continue
                if best_elem is None or elem.version > best_elem.version:
                    best_peeker, best_elem = peeker, elem
            if best_peeker is None:
                break  # exhausted
            yield best_elem
            best_peeker.consume()


class RadsSolution:
    """A Solution has multiple versions and contains many Projects.

    The Riot Application Distribution System (RADS) has two Solutions: `league_client_sln` and `lol_game_client_sln`.
    The 'league_client_sln' contains data the client (LCU), and the `lol_game_client_sln` contains data for the game client.
    These classes will likely work with other solutions, although some functionality may need to be extended.

    There are multiple versions of a given solution, which can be accessed via the `.versions()` method.
    All versions of a solution can be downloaded and extracted via the `.download()` method.

    Each version of a solution contains multiple projects pertaining to different locales.
    """

    def __init__(self, storage: RadsStorage, name):
        self.storage = storage
        self.path = f"solutions/{name}/releases"
        self.name = name

    def __str__(self):
        return f"rads:{self.name}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.name}>"

    def __eq__(self, other):
        if isinstance(other, RadsSolution):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        if isinstance(other, RadsSolution):
            return self.name < other.name
        return NotImplemented

    def versions(self, stored=False) -> List['RadsSolutionVersion']:
        """Retrieve a sorted list of versions of this solution

        If stored is True, only versions in storage are used (to avoid downloading new files).
        """

        if stored:
            fspath = self.storage.fspath(self.path)
            if not os.path.isdir(fspath):
                return []  # solution not in storage
            listing = []
            for path in os.listdir(fspath):
                if not os.path.isdir(os.path.join(fspath, path)):
                    continue
                listing.append(path)
        else:
            logger.debug(f"retrieve versions of {self}")
            listing = self.storage.request_text(f"{self.path}/releaselisting").splitlines()
        return sorted(RadsSolutionVersion(self, RadsVersion(l)) for l in listing)

    def download(self, langs):
        for v in self.versions():
            v.download(langs)


class RadsSolutionVersion:
    """A single version of a RadsSolution.

    Each RadsSolutionVersion contains data for multiple projects, accessible via the `RadsSolutionVersion.projects` method.
    There is one "main" project, and one project for each language.

    The data contained in a RadsSolutionVersion can be downloaded and extracted via the `.download()` method.
    """

    def __init__(self, solution: RadsSolution, version: 'RadsVersion'):
        self.path = f"{solution.path}/{version}"
        self.solution = solution
        self.version = version

    def __str__(self):
        return f"{self.solution}={self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.solution.name}={self.version}>"

    def __eq__(self, other):
        if isinstance(other, RadsSolutionVersion):
            return self.solution == other.solution and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.solution, self.version))

    def __lt__(self, other):
        if isinstance(other, RadsSolutionVersion):
            if self.solution < other.solution:
                return True
            elif self.solution == other.solution:
                return self.version > other.version
            else:
                return False
        return NotImplemented

    def dependencies(self) -> Dict[Union[Language, None], List['RadsProjectVersion']]:
        """Parse dependencies from the solutionmanifest

        Return a map of project versions for each language.
        The entry None is set to all required project versions.
        """

        logger.debug(f"retrieve dependencies of {self}")

        path = f"{self.path}/solutionmanifest"
        self.solution.storage.download(path, path)
        with open(self.solution.storage.fspath(path)) as f:
            lines = f.read().splitlines()
        assert lines[0] == "RADS Solution Manifest", "unexpected solutionmanifest magic line"
        assert lines[1] == "1.0.0.0", "unexpected solutionmanifest version"
        assert lines[2] == self.solution.name, "solution name mismatch in solutionmanifest header"
        assert lines[3] == self.version, "solution version mismatch in solutionmanifest header"
        idx = 4

        required_projects = []  # [name, ...]
        projects = {}  # {name: RadsProjectVersion}
        nprojects, idx = int(lines[idx]), idx + 1
        for _ in range(nprojects):
            (name, version, unk1, unk2), idx = lines[idx:idx+4], idx + 4
            unk1, unk2 = int(unk1), int(unk2)
            if unk1 == 0:
                required_projects.append(name)
            else:
                assert unk1 == 10
            assert unk2 == 0
            projects[name] = RadsProjectVersion(RadsProject(self.solution.storage, name), RadsVersion(version))

        langs = {}  # {Language: [RadsProjectVersion, ...]}
        nlangs, idx = int(lines[idx]), idx + 1
        for _ in range(nlangs):
            (lang, unk1, ndeps), idx = lines[idx:idx+3], idx + 3
            unk1, ndeps = int(unk1), int(ndeps)
            assert unk1 == 0
            deps, idx = lines[idx:idx+ndeps], idx + ndeps
            langs[Language(lang)] = [projects[name] for name in deps]

        langs[None] = list(projects[name] for name in required_projects)
        return langs

    def projects(self, langs=True) -> List['RadsProjectVersion']:
        """Return a list of projects for provided language(s)"""
        dependencies = self.dependencies()
        if langs is False:
            return dependencies[None]
        elif langs is True:
            return list({pv for pvs in dependencies.values() for pv in pvs})
        elif isinstance(langs, Language):
            return dependencies[langs]
        else:
            return list({pv for lang in langs for pv in dependencies[lang]})

    def filepaths(self, langs) -> Generator[str, None, None]:
        """Generate the extract path of files in the solution version"""
        for pv in self.projects(langs):
            yield from pv.filepaths()

    def download(self, langs=True):
        """Download solution version files"""

        logger.info(f"downloading solution {self}")
        for pv in self.projects(langs):
            pv.download()

    def patch_version(self) -> Optional[PatchVersion]:
        """Return patch version or None if there is None

        This method reads/writes version from/to cache.
        """

        # for PBE: version is always "main"
        if self.solution.storage.url == RadsStorage.URL_PBE:
            return PatchVersion("main")

        cache = self.solution.storage.fspath(f"{self.path}/_patch_version")
        if os.path.isfile(cache):
            logger.debug(f"retrieving patch version for {self} from cache")
            with open(cache) as f:
                version = f.read().strip()
                version = PatchVersion(version) if version else None
        else:
            version = self._retrieve_patch_version()
            if version is None:
                logger.warning(f"failed to retrieve patch version for {self}")
            else:
                with open(cache, 'w') as f:
                    f.write(f"{version}\n")
        return version

    def _retrieve_patch_version(self) -> Optional[PatchVersion]:
        """Retrieve patch version from game files (no cache handling)

        Return None if there is no patch version (because files are not
        available anymore on Riot's CDN).
        Raise an exception if patch version cannot be retrieved.
        """

        logger.debug(f"retrieving patch version for {self}")

        retrievers = {
            # solution_name: (project_name, file_name, extractor)
            'league_client_sln': (
                'league_client',
                'system.yaml',
                get_system_yaml_version,
            ),
            'lol_game_client_sln': (
                'lol_game_client',
                'League of Legends.exe',
                get_exe_version,
            ),
        }

        try:
            project_name, file_name, extractor = retrievers[self.solution.name]
        except KeyError:
            raise RuntimeError(f"no known way to retrieve patch version for solution {self.solution.name}")

        for pv in self.projects(False):
            if pv.project.name == project_name:
                break
        else:
            raise ValueError(f"{project_name} project not found for {self}")

        try:
            filepaths = pv.filepaths()
        except requests.exceptions.HTTPError as e:
            # some packagemanifest files are not available anymore
            # for these project versions, there is no patch version
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

        path_suffix = f'/{file_name}'
        for path in filepaths:
            if path.endswith(path_suffix):
                fspath = self.solution.storage.fspath(path)
                if not os.path.isfile(path):
                    pv.extract([path])
                break
        else:
            # packagemanifest for league_client<=0.0.0.43 doesn't alway contain system.yaml
            if pv.project.name == 'league_client' and pv.version <= RadsVersion('0.0.0.43'):
                return None
            raise ValueError(f"'{file_name}' not found for {pv}")

        version = extractor(fspath)
        return PatchVersion(version)


class RadsProject:
    """A RadsProject is a subset of data for a specific locale, or the data for the main/default/common locale.

    There are multiple versions of a given project, which can be accessed via the `.versions()` method.
    All versions of the project can be downloaded and extracted via the `.download()` method.
    The data in ProjectVersions are contained in Bin files, which are extracted.
    """

    def __init__(self, storage: RadsStorage, name):
        self.storage = storage
        self.path = f"projects/{name}/releases"
        self.name = name

    def __str__(self):
        return f"rads:{self.name}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.name}>"

    def __eq__(self, other):
        if isinstance(other, RadsProject):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        if isinstance(other, RadsProject):
            return self.name < other.name
        return NotImplemented

    def versions(self) -> List['RadsProjectVersion']:
        """Retrieve the list of versions of this project"""
        logger.debug(f"retrieve versions of {self}")
        listing = self.storage.request_text(f"{self.path}/releaselisting")
        return [RadsProjectVersion(self, RadsVersion(l)) for l in listing.splitlines()]

    def download(self):
        for v in self.versions():
            v.download()


class RadsProjectVersion:
    """A single version of a RadsProject.

    The data contained in a project can be downloaded and extracted via the `.download()` method.
    The data in these ProjectVersions are contained in Bin files, which are extracted.
    """

    def __init__(self, project: RadsProject, version: 'Version'):
        self.path = f"{project.path}/{version}"
        self.project = project
        self.version = version
        self._package_files = None  # {extract_path: BinPackageFile}

    def __str__(self):
        return f"{self.project}={self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.project.name}={self.version}>"

    def __eq__(self, other):
        if isinstance(other, RadsProjectVersion):
            return self.project == other.project and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.project, self.version))

    def __lt__(self, other):
        if isinstance(other, RadsProjectVersion):
            if self.project < other.project:
                return True
            elif self.project == other.project:
                return self.version > other.version
            else:
                return False
        return NotImplemented

    def _get_package_files(self) -> Dict[str, 'BinPackageFile']:
        """Retrieve files from packagemanifest"""

        if self._package_files is None:
            manifest_path = f"{self.path}/packagemanifest"
            manifest_urlpath = f"{self.path}/packages/files/packagemanifest"
            self.project.storage.download(manifest_urlpath, manifest_path)
            files = BinPackageFile.from_package_manifest(self.project.storage.fspath(manifest_path))
            self._package_files = {pf.extract_path: pf for pf in files}
        return self._package_files

    def filepaths(self) -> Dict[str, 'BinPackageFile']:
        """Generate the extract path of files in the project version"""
        return self._get_package_files()

    def extract(self, paths=None):
        """Download packages and extract files

        A subset of paths to extract can be provided (they must exist in the project version).
        """

        all_files = self._get_package_files()
        if paths is None:
            extracted_files = all_files.values()
        else:
            extracted_files = [all_files[path] for path in paths]

        # filter already extracted file
        extracted_files = [pf for pf in extracted_files if not os.path.isfile(self.project.storage.fspath(pf.extract_path))]

        # group files by package
        files_by_package = defaultdict(list)
        for pf in extracted_files:
            files_by_package[pf.package].append(pf)

        package_files_path = f"{self.path}/packages/files"

        for package, files in files_by_package.items():
            with self.project.storage.stream(f"{package_files_path}/{package}") as reader:
                # sort files by offset to extract while streaming the bin file
                for pkgfile in sorted(files, key=lambda f: f.offset):
                    logger.debug(f"extracting {pkgfile.path}")
                    reader.skip_to(pkgfile.offset)
                    fspath = self.project.storage.fspath(pkgfile.extract_path)
                    with write_file_or_remove(fspath) as fout:
                        if pkgfile.compressed:
                            zobj = zlib.decompressobj(zlib.MAX_WBITS | 32)
                            def writer(data):
                                return fout.write(zobj.decompress(data))
                            reader.copy(writer, pkgfile.size)
                            fout.write(zobj.flush())
                        else:
                            reader.copy(fout.write, pkgfile.size)

    def download(self):
        """Download project version files"""
        logger.info(f"downloading project {self}")
        self.project.storage.download(f"{self.path}/releasemanifest", None)
        self.extract()


class RadsPatchElement(PatchElement):
    """Patch element from a RADS storage"""

    solution_name_to_element_name = {
        'league_client_sln': 'client',
        'lol_game_client_sln': 'game',
    }

    def __init__(self, sv: RadsSolutionVersion):
        name = self.solution_name_to_element_name[sv.solution.name]
        version = sv.patch_version()
        if version is None:
            raise ValueError(f"unknown patch version for {sv}")
        super().__init__(name, version)
        self.solution_version = sv

    def download(self, langs=True):
        self.solution_version.download(langs=langs)

    def fspaths(self, langs=True):
        sv = self.solution_version
        storage = sv.solution.storage
        return (storage.fspath(path) for path in sv.filepaths(langs=langs))

    def relpaths(self, langs=True):
        sv = self.solution_version
        return (path.split('/', 5)[5].lower() for path in sv.filepaths(langs=langs))

    def paths(self, langs=True):
        sv = self.solution_version
        storage = sv.solution.storage
        for path in sv.filepaths(langs=langs):
            yield (storage.fspath(path), path.split('/', 5)[5].lower())


class BinPackageFile:
    """A single file in a BIN package"""

    __slots__ = ('path', 'package', 'offset', 'size', 'compressed', 'extract_path')

    def __init__(self, line):
        path, self.package, offset, size, typ = line.split(',')
        self.path = path[1:]  # remove leading '/'
        self.offset = int(offset)
        self.size = int(size)
        self.compressed = self.path.endswith('.compressed')
        if self.compressed:
            self.extract_path = self.path[:-11]  # remove the '.compressed' suffix
        else:
            self.extract_path = self.path

    def __str__(self):
        return f"<{self.__class__.__name__} {self.path!r}>"

    @classmethod
    def from_package_manifest(cls, path) -> Generator['BinPackageFile', None, None]:
        with open(path) as f:
            line = f.readline()
            assert line.startswith('PKG1'), "unexpected packagemanifest magic line"
            for line in f:
                yield cls(line)


def parse_rads_component(storage: RadsStorage, component: str):
    """Parse a component string representation to an object"""

    m = re.match(r'^(?:([sp]):)?(\w+)(?:=(|[0-9]+(?:\.[0-9]+)*|main)?)?$', component)
    if not m:
        raise ValueError(f"invalid component: {component}")
    typ, name, version = m.group(1, 2, 3)
    if not typ:
        if name == 'patch':
            typ = 'patch'
        elif name.endswith('_sln'):
            typ = 's'
        else:
            typ = 'p'

    if typ == 'p':
        project = RadsProject(storage, name)
        if version is None:
            return project
        elif version == '':
            return project.versions()[0]
        else:
            return RadsProjectVersion(project, RadsVersion(version))
    elif typ == 's':
        solution = RadsSolution(storage, name)
        if version is None:
            return solution
        elif version == '':
            return solution.versions()[0]
        else:
            return RadsSolutionVersion(solution, RadsVersion(version))
    elif typ == 'patch':
        if version is None:
            raise ValueError(f"patch requires a version")
        elif version == '':
            return storage.patch(None)
        else:
            return storage.patch(version)

