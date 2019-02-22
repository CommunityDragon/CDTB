import os
import re
import zlib
from contextlib import contextmanager
from typing import List, Dict, Union, Optional, Generator, Iterable
from collections import defaultdict
import logging
import requests
import hachoir.parser
import hachoir.metadata

from .data import Language
from .tools import write_file_or_remove

logger = logging.getLogger(__name__)


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


class Storage:
    """Download and store game files"""

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
        self.url = url
        self.path = path
        self.s = requests.session()

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

    def list_projects(self) -> List['Project']:
        """List projects present in storage"""
        ret = []
        base = self.fspath("projects")
        for name in os.listdir(base):
            if os.path.isdir(f"{base}/{name}/releases"):
                ret.append(Project(self, name))
        return ret

    def list_solutions(self) -> List['Solution']:
        """List solutions present in storage"""
        ret = []
        base = self.fspath("solutions")
        for name in os.listdir(base):
            if os.path.isdir(f"{base}/{name}/releases"):
                ret.append(Solution(self, name))
        return ret


class Solution:
    """A Solution has multiple versions and contains many Projects.

    The Riot Application Distribution System (RADS) has two Solutions: `league_client_sln` and `lol_game_client_sln`.
    The 'league_client_sln' contains data the client (LCU), and the `lol_game_client_sln` contains data for the game client.
    These classes will likely work with other solutions, although some functionality may need to be extended.

    There are multiple versions of a given solution, which can be accessed via the `.versions()` method.
    All versions of a solution can be downloaded and extracted via the `.download()` method.

    Each version of a solution contains multiple projects pertaining to different locales.
    """

    def __init__(self, storage: Storage, name):
        self.storage = storage
        self.path = f"solutions/{name}/releases"
        self.name = name

    def __str__(self):
        return f"s:{self.name}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.name}>"

    def __eq__(self, other):
        if isinstance(other, Solution):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        if isinstance(other, Solution):
            return self.name < other.name
        return NotImplemented

    def versions(self, stored=False) -> List['SolutionVersion']:
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
        return sorted(SolutionVersion(self, Version(l)) for l in listing)

    def download(self, langs, dry_run=False):
        for v in self.versions():
            v.download(langs, dry_run=dry_run)


class SolutionVersion:
    """A single version of a Solution.

    Each SolutionVersion contains data for multiple projects, accessible via the `SolutionVersion.projects` method.
    There is one "main" project, and one project for each language.

    The data contained in a SolutionVersion can be downloaded and extracted via the `.download()` method.
    """

    def __init__(self, solution: Solution, version: 'Version'):
        self.path = f"{solution.path}/{version}"
        self.solution = solution
        self.version = version

    def __str__(self):
        return f"{self.solution}={self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.solution.name}={self.version}>"

    def __eq__(self, other):
        if isinstance(other, SolutionVersion):
            return self.solution == other.solution and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.solution, self.version))

    def __lt__(self, other):
        if isinstance(other, SolutionVersion):
            if self.solution < other.solution:
                return True
            elif self.solution == other.solution:
                return self.version > other.version
            else:
                return False
        return NotImplemented

    def dependencies(self) -> Dict[Union[Language, None], List['ProjectVersion']]:
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
        projects = {}  # {name: ProjectVersion}
        nprojects, idx = int(lines[idx]), idx + 1
        for _ in range(nprojects):
            (name, version, unk1, unk2), idx = lines[idx:idx+4], idx + 4
            unk1, unk2 = int(unk1), int(unk2)
            if unk1 == 0:
                required_projects.append(name)
            else:
                assert unk1 == 10
            assert unk2 == 0
            projects[name] = ProjectVersion(Project(self.solution.storage, name), Version(version))

        langs = {}  # {Language: [ProjectVersion, ...]}
        nlangs, idx = int(lines[idx]), idx + 1
        for _ in range(nlangs):
            (lang, unk1, ndeps), idx = lines[idx:idx+3], idx + 3
            unk1, ndeps = int(unk1), int(ndeps)
            assert unk1 == 0
            deps, idx = lines[idx:idx+ndeps], idx + ndeps
            langs[Language(lang)] = [projects[name] for name in deps]

        langs[None] = list(projects[name] for name in required_projects)
        return langs

    def projects(self, langs: Union[bool, Language, Iterable[Language]]) -> List['ProjectVersion']:
        """Return a list of projects for provided languages

        langs can have the following values:
          False -- common dependencies, not language-dependent
          True -- all languages
          lang -- provided language
          [lang, ...] -- provided languages
        """
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

    def download(self, langs, dry_run=False):
        """Download solution version files"""

        logger.info(f"downloading solution {self}")
        for pv in self.projects(langs):
            pv.download(dry_run=dry_run)

    def patch_version(self) -> Optional['Version']:
        """Return patch version or None if there is None

        This method reads/writes version from/to cache.
        """

        # for PBE: version is always "main"
        if self.solution.storage.url == Storage.URL_PBE:
            return Version("main")

        cache = self.solution.storage.fspath(f"{self.path}/_patch_version")
        if os.path.isfile(cache):
            logger.debug(f"retrieving patch version for {self} from cache")
            with open(cache) as f:
                version = f.read().strip()
                version = Version(version) if version else None
        else:
            version = self._retrieve_patch_version()
            if version is None:
                logger.warning(f"failed to retrieve patch version for {self}")
            else:
                with open(cache, 'w') as f:
                    f.write(f"{version}\n")
        return version

    def _retrieve_patch_version(self) -> Optional['Version']:
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
            # packagemanifest for league_client<=0.0.043 doesn't alway contain system.yaml
            if pv.project.name == 'league_client' and pv.version <= Version('0.0.0.43'):
                return None
            raise ValueError(f"'{file_name}' not found for {pv}")

        version = extractor(fspath)
        # truncate to first 2 numbers
        return Version(version.t[:2])


class Project:
    """A Project is a subset of data for a specific locale, or the data for the main/default/common locale.

    There are multiple versions of a given project, which can be accessed via the `.versions()` method.
    All versions of the project can be downloaded and extracted via the `.download()` method.
    The data in ProjectVersions are contained in Bin files, which are extracted.
    """

    def __init__(self, storage: Storage, name):
        self.storage = storage
        self.path = f"projects/{name}/releases"
        self.name = name

    def __str__(self):
        return f"p:{self.name}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.name}>"

    def __eq__(self, other):
        if isinstance(other, Project):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        if isinstance(other, Project):
            return self.name < other.name
        return NotImplemented

    def versions(self) -> List['ProjectVersion']:
        """Retrieve the list of versions of this project"""
        logger.debug(f"retrieve versions of {self}")
        listing = self.storage.request_text(f"{self.path}/releaselisting")
        return [ProjectVersion(self, Version(l)) for l in listing.splitlines()]

    def download(self, dry_run=False):
        for v in self.versions():
            v.download(dry_run=dry_run)


class ProjectVersion:
    """A single version of a Project.

    The data contained in a project can be downloaded and extracted via the `.download()` method.
    The data in these ProjectVersions are contained in Bin files, which are extracted.
    """

    def __init__(self, project: Project, version: 'Version'):
        self.path = f"{project.path}/{version}"
        self.project = project
        self.version = version
        self._package_files = None  # {extract_path: BinPackageFile}

    def __str__(self):
        return f"{self.project}={self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.project.name}={self.version}>"

    def __eq__(self, other):
        if isinstance(other, ProjectVersion):
            return self.project == other.project and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.project, self.version))

    def __lt__(self, other):
        if isinstance(other, ProjectVersion):
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

        # filter already extracted files
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

    def download(self, dry_run=False):
        """Download project version files"""
        logger.info(f"downloading project {self}")
        self.project.storage.download(f"{self.path}/releasemanifest", None)
        if dry_run:
            paths = [p for p in self.filepaths() if not os.path.isfile(self.project.storage.fspath(p))]
            if paths:
                logger.info(f"files to extract: {len(paths)}")
            else:
                logger.info("all files already extracted")
        else:
            self.extract()


class PatchVersion:
    """A single game patch version (e.g. patch 8.1).

    This class cannot not be instantiated directly. Instead, use PatchVersion.versions or PatchVersion.version.
    """

    def __init__(self):
        raise RuntimeError("This class should not be instantiated by the user.")

    @classmethod
    def _create(cls, storage: Storage, version: 'Version', solutions: List[SolutionVersion]):
        self = cls.__new__(cls)
        self.storage = storage
        self.version = version
        self._solutions = sorted(solutions)
        return self

    def __str__(self):
        return f"patch={self.version}"

    def __repr__(self):
        return f"<{self.__class__.__qualname__} {self.version}>"

    def __eq__(self, other):
        if isinstance(other, PatchVersion):
            return self.version == other.version
        return False

    def __hash__(self):
        return hash(self.version)

    def __lt__(self, other):
        if isinstance(other, PatchVersion):
            return self.version > other.version
        return NotImplemented

    def solutions(self, latest=False):
        """Return solution versions used by the patch version

        If latest_sln is True, only the latest version of each solution is returned.
        """
        if latest:
            ret = []
            previous_solution = None
            for sv in self._solutions:
                if sv.solution != previous_solution:
                    ret.append(sv)
                previous_solution = sv.solution
            return ret
        else:
            return self._solutions

    def download(self, langs=True, latest=False, dry_run=False):
        for sv in self.solutions(latest=latest):
            sv.download(langs, dry_run=dry_run)

    @staticmethod
    def versions(storage: Storage, stored=False) -> Generator['PatchVersion', None, None]:
        """Generate patch versions, sorted from the latest one

        If stored is True, only solution versions in storage are used (to avoid
        downloading new files).

        Versions are generated so the caller can stop iterating when needed
        versions have been retrieved, avoiding to fetch all solutions.

        Note: patch versions are assumed to be monotonous in successive
        solution versions (they never decrease).

        For PBE, patch version is always 'main'.
        """

        solution_names = ('league_client_sln', 'lol_game_client_sln')

        # group versions by patch, drop those without patch
        def gen_solution_patches(name):
            solution = Solution(storage, name)
            for sv in solution.versions(stored=stored):
                patch = sv.patch_version()
                if patch is None:
                    continue
                yield patch, sv

        # for each solution, peek the next patch to yield the lowest one
        patches_iterators = [(None, None, gen_solution_patches(sln)) for sln in solution_names]
        cur_patch = None
        cur_solutions = None
        while True:
            new_patches_iterators = []
            for patch, sv, it in patches_iterators:
                if patch is None:
                    try:
                        patch, sv = next(it)
                    except StopIteration:
                        continue  # exhausted, remove from patches_iterators
                new_patches_iterators.append((patch, sv, it))
            if not new_patches_iterators:
                break  # all iterators exhausted
            # get and "consume" the highest patch version
            new_patches_iterators.sort(key=lambda pit: pit[0], reverse=True)
            patch, sv, it = new_patches_iterators[0]
            if patch != cur_patch:
                if cur_patch is not None:
                    yield PatchVersion._create(storage, cur_patch, cur_solutions)
                cur_patch = patch
                cur_solutions = []
            cur_solutions.append(sv)
            new_patches_iterators[0] = None, None, it
            patches_iterators = new_patches_iterators
        if cur_patch is not None:
            yield PatchVersion._create(storage, cur_patch, cur_solutions)

    @staticmethod
    def version(storage: Storage, version=None, stored=False):
        """Retrieve a single version, None if not found

        If version if None, retrieve the latest one.
        """
        it = PatchVersion.versions(storage, stored=stored)
        if version is None:
            return next(it)
        for v in it:
            if v.version == version:
                return v
        return None


class Version:
    """A wrapper-like class for a version string that converts the string into a format that is usable for comparisons.

    Solutions and projects all have individual version numbers (e.g. "0.0.1.30").
    The version numbers are actually 32-bit unsigned integers represented using dot-notation, exactly the same as the
    notation used for IPv4 addresses. Notably, each individual number caps at 255, so the version after 0.0.0.255 is
    0.0.1.0.

    This version class makes different versions comparable. For example, Version("0.0.0.255") < Version("0.0.1.0").
    """

    def __init__(self, v: Union[str, tuple]):
        if isinstance(v, str):
            self.s = v
            if v == 'main':
                # make it comparable, but only with itself
                self.t = 'main'
            else:
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
        # allow to compare with string or tuple
        if isinstance(other, Version):
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


def get_system_yaml_version(path) -> Optional[Version]:
    with open(path) as f:
        for line in f:
            # TODO do proper yaml parsing
            # formats: Release/X.Y or 'X.Y'
            m = re.match(r"""^ *game-branch: .*["'/]([0-9.]+)["']?$""", line)
            if m:
                return Version(m.group(1))
        else:
            return None


def get_exe_version(path) -> Version:
    """Return version from an executable"""

    parser = hachoir.parser.createParser(path)
    metadata = hachoir.metadata.extractMetadata(parser=parser)
    return Version(metadata.get('version'))


def parse_component(storage: Storage, component: str):
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
    if version is not None and version != '':
        version = Version(version)
    if typ == 'p':
        project = Project(storage, name)
        if version is None:
            return project
        elif version == '':
            return project.versions()[0]
        else:
            return ProjectVersion(project, version)
    elif typ == 's':
        solution = Solution(storage, name)
        if version is None:
            return solution
        elif version == '':
            return solution.versions()[0]
        else:
            return SolutionVersion(solution, version)
    elif typ == 'patch':
        if version is None:
            raise ValueError(f"patch requires a version")
        elif version == '':
            return PatchVersion.version(storage, None)
        else:
            return PatchVersion.version(storage, version)
