#!/usr/bin/env python3
import os
import re
import sys
import zlib
import json
import itertools
from contextlib import contextmanager
from typing import List, Dict, IO, Union, Optional, Generator
import logging
import requests
from correlator.functions import extract_client_version

logger = logging.getLogger("downloader")


class Version:
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
        return "{}({!r})".format(self.__class__.__qualname__, self.s)

    def __str__(self):
        return self.s

    def __lt__(self, other): return self.t < other.t
    def __le__(self, other): return self.t <= other.t
    def __gt__(self, other): return self.t > other.t
    def __ge__(self, other): return self.t >= other.t

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

    def __hash__(self):
        return hash(self.s)

    def __ne__(self, other):
        return not self == other


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
    """
    Download and store game files
    """

    # all available values are in system.yaml
    # values in use are in RADS/system/system.cfg
    # region is ignored here (it is not actually needed)
    DOWNLOAD_URL = "l3cdn.riotgames.com"
    DOWNLOAD_PATH = "/releases/live"

    def __init__(self, path, url=None):
        if url is None:
            url = f"http://{self.DOWNLOAD_URL}{self.DOWNLOAD_PATH}/"
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

        logger.debug("download file: %s", path)
        try:
            os.makedirs(os.path.dirname(fspath), exist_ok=True)
            r = self.request_get(urlpath)
            r.raise_for_status()
            with open(fspath, 'wb') as f:
                f.write(r.content)
        except:
            # remove partially downloaded file
            try:
                os.remove(fspath)
            except OSError:
                pass
            raise

    @contextmanager
    def stream(self, urlpath) -> RequestStreamReader:
        """Request a path for streaming download"""
        with self.s.get(self.url + urlpath, stream=True) as r:
            r.raise_for_status()
            yield RequestStreamReader(r)


class Project:
    """
    RADS project
    """

    def __init__(self, storage: Storage, name):
        self.storage = storage
        self.path = f"projects/{name}/releases"
        self.name = name

    def __str__(self):
        return f"p:{self.name}"

    def __repr__(self):
        return "<{} {}>".format(self.__class__.__qualname__, self.name)

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
        logger.debug("retrieve versions of %s", self)
        listing = self.storage.request_text(f"{self.path}/releaselisting")
        return [ProjectVersion(self, Version(l)) for l in listing.splitlines()]

    def download(self, force=False, dry_run=False):
        for v in self.versions():
            v.download(force=force, dry_run=dry_run)

    @staticmethod
    def list(storage: Storage) -> List['Project']:
        """List projects present in storage"""
        ret = []
        base = storage.fspath("projects")
        for name in os.listdir(base):
            if os.path.isdir(f"{base}/{name}/releases"):
                ret.append(Project(storage, name))
        return ret


class ProjectVersion:
    """
    A single version of a project
    """

    def __init__(self, project: Project, version: Version):
        self.path = f"{project.path}/{version}"
        self.project = project
        self.version = version

    def __str__(self):
        return f"{self.project}={self.version}"

    def __repr__(self):
        return "<{} {}={}>".format(self.__class__.__qualname__, self.project.name, self.version)

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

    def packages(self, force=False) -> List['BinPackage']:
        """Return the list of packages"""

        files_path = f"{self.path}/packages/files"
        manifest_path = f"{self.path}/packagemanifest"
        manifest_urlpath = f"{self.path}/packages/files/packagemanifest"
        self.project.storage.download(manifest_urlpath, manifest_path, force=force)
        with open(self.project.storage.fspath(manifest_path)) as f:
            lines = f.read().splitlines()

        assert lines[0].startswith('PKG1'), "unexpected packagemanifest magic line"
        packages = {}  # {path: BinPackage}
        for line in lines[1:]:
            file_path, package_name, offset, size, typ = line.split(',')
            package_path = f"{files_path}/{package_name}"
            if package_path not in packages:
                packages[package_path] = BinPackage(self.project.storage, package_path, [])
            packages[package_path].add_file(file_path, int(offset), int(size))
        return list(packages.values())

    def package_files(self, force=False) -> Generator['BinPackageFile', None, None]:
        """Generate a list of all package files"""
        for package in self.packages(force=force):
            yield from package.files

    def download(self, force=False, dry_run=False):
        """Download project version files"""
        logger.info("downloading project %s", self)
        self.project.storage.download(f"{self.path}/releasemanifest", None, force=force)
        for package in self.packages(force):
            if dry_run:
                if package.missing_files():
                    logger.info("package to extract: %s", package.path)
                else:
                    logger.debug("package already extracted: %s", package.path)
            else:
                package.extract()


class Solution:
    """
    RADS solution

    There are currently two active solutions:
    `league_client_sln` and `lol_game_client_sln`.
    """

    def __init__(self, storage: Storage, name):
        self.storage = storage
        self.path = f"solutions/{name}/releases"
        self.name = name

    def __str__(self):
        return f"s:{self.name}"

    def __repr__(self):
        return "<{} {}>".format(self.__class__.__qualname__, self.name)

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

        If stored in True, only versions in storage are used (to avoid
        downloading new files).
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
            logger.debug("retrieve versions of %s", self)
            listing = self.storage.request_text(f"{self.path}/releaselisting").splitlines()
        return sorted(SolutionVersion(self, Version(l)) for l in listing)

    def download(self, langs, force=False, dry_run=False):
        for v in self.versions():
            v.download(langs, force=force, dry_run=dry_run)

    @staticmethod
    def list(storage: Storage) -> List['Solution']:
        """List solutions present in storage"""
        ret = []
        base = storage.fspath("solutions")
        for name in os.listdir(base):
            if os.path.isdir(f"{base}/{name}/releases"):
                ret.append(Solution(storage, name))
        return ret


class SolutionVersion:
    """
    A single version of a solution
    """

    def __init__(self, solution: Solution, version: Version):
        self.path = f"{solution.path}/{version}"
        self.solution = solution
        self.version = version

    def __str__(self):
        return f"{self.solution}={self.version}"

    def __repr__(self):
        return "<{} {}={}>".format(self.__class__.__qualname__, self.solution.name, self.version)

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

    def dependencies(self, force=False) -> Dict[Union[str, None], List[ProjectVersion]]:
        """Parse dependencies from the solutionmanifest

        Return a map of project versions for each lang code.
        The entry None is set to all required project versions.
        """

        logger.debug("retrieve dependencies of %s", self)

        path = f"{self.path}/solutionmanifest"
        self.solution.storage.download(path, path, force=force)
        with open(self.solution.storage.fspath(path)) as f:
            lines = f.read().splitlines()
        assert lines[0] == "RADS Solution Manifest", "unexpected solutionmanifest magic line"
        assert lines[1] == "1.0.0.0", "unexpected solutionmanifest version"
        assert lines[2] == self.solution.name, "solution name mismatch in solutionmanifest header"
        assert lines[3] == self.version, "solution version mismatch in solutionmanifest header"
        idx = 4

        required_projects = [] # [name, ...]
        projects = {} # {name: ProjectVersion}
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

        langs = {} # {code: [ProjectVersion, ...]}
        nlangs, idx = int(lines[idx]), idx + 1
        for _ in range(nlangs):
            (lang, unk1, ndeps), idx = lines[idx:idx+3], idx + 3
            unk1, ndeps = int(unk1), int(ndeps)
            assert unk1 == 0
            deps, idx = lines[idx:idx+ndeps], idx + ndeps
            langs[lang] = [projects[name] for name in deps]

        langs[None] = list(projects[name] for name in required_projects)
        return langs

    def projects(self, langs, force=False) -> List[ProjectVersion]:
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
        elif isinstance(langs, str):
            return dependencies[langs]
        else:
            return list({pv for lang in langs for pv in dependencies[lang]})

    def download(self, langs, force=False, dry_run=False):
        """Download solution version files"""

        logger.info("downloading solution %s", self)
        for pv in self.projects(langs, force=force):
            pv.download(force=force, dry_run=dry_run)

    def patch_version(self) -> Optional[Version]:
        """Return patch version or None if it cannot be retrieved"""

        if self.solution.name == 'league_client_sln':
            # get patch version from system.yaml
            for pv in self.projects(False):
                if pv.project.name == 'league_client':
                    break
            else:
                raise ValueError("league_client project not found for %s" % self)

            for pkgfile in pv.package_files():
                if pkgfile.extract_path().endswith('/system.yaml'):
                    if not os.path.isfile(pkgfile.fspath()):
                        pkgfile.package.extract()
                    break
            else:
                raise ValueError("system.yaml not found for %s" % pv)
            with open(pkgfile.fspath()) as f:
                for line in f:
                    #TODO do proper yaml parsing
                    m = re.match(r"""^ *game-branch: ["']([0-9.]+)["']$""", line)
                    if m:
                        return Version(m.group(1))
                else:
                    raise ValueError("patch version not found in %s" % system_yaml_path)

        elif self.solution.name == 'lol_game_client_sln':
            # get patch version from .exe metadata
            for pv in self.projects(False):
                if pv.project.name == 'lol_game_client':
                    break
            else:
                raise ValueError("league_client project not found for %s" % self)

            for pkgfile in pv.package_files():
                if pkgfile.extract_path().endswith('/League of Legends.exe'):
                    if not os.path.isfile(pkgfile.fspath()):
                        pkgfile.package.extract()
                    break
            else:
                raise ValueError("'League of Legends.exe' not found for %s" % pv)
            patch = Version(extract_client_version(pkgfile.fspath()))
            return Version(patch.t[:2])

        else:
            logger.info("no known way to retrieve patch version for solution %s", self.solution.name)


class PatchVersion:
    """
    A single game patch version

    This class should not be instanciated directly.
    Use versions() or version() to retrieve patch versions.
    """

    def __init__(self, storage: Storage, version: Version, solutions: List[SolutionVersion]):
        self.storage = storage
        self.version = version
        self._solutions = sorted(solutions)

    def __str__(self):
        return f"patch={self.version}"

    def __repr__(self):
        return "<{} {}={}>".format(self.__class__.__qualname__, self.version)

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

    def download(self, langs=True, latest=False, force=False, dry_run=False):
        for sv in self.solutions(latest=latest):
            sv.download(langs, force=force, dry_run=dry_run)

    @staticmethod
    def versions(storage: Storage, stored=False) -> Generator['PatchVersion', None, None]:
        """Generate patch versions, sorted from the latest one

        If stored is True, only solution versions in storage are used (to avoid
        downloading new files).

        Versions are generated so the caller can stop iterating when needed
        versions have been retrieved, avoiding to fetch all solutions.

        Note: patch versions are assumed to be monotonous in successive
        solution versions (they never decrease).
        """

        solution_names = ('league_client_sln', 'lol_game_client_sln')

        # group versions by patch, drop those without patch
        def gen_solution_patches(name):
            solution = Solution(storage, name)
            previous_patch = None
            for sv in solution.versions(stored=stored):
                patch = sv.patch_version()
                if patch is None:
                    continue
                yield patch, sv
                previous_patch = patch

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
                    yield PatchVersion(storage, cur_patch, cur_solutions)
                cur_patch = patch
                cur_solutions = []
            cur_solutions.append(sv)
            new_patches_iterators[0] = None, None, it
            patches_iterators = new_patches_iterators
        if cur_patch is not None:
            yield PatchVersion(storage, cur_patch, cur_solutions)

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


class BinPackageFile:
    """A single file in a BIN package"""

    def __init__(self, package, path, offset, size):
        self.package = package
        self.path = path.lstrip('/')
        self.offset = offset
        self.size = size

    def __str__(self):
        return "<{} {!r}>".format(self.__class__.__name__, self.path)

    def compressed(self) -> bool:
        return self.path.endswith('.compressed')

    def extract_path(self) -> str:
        """Return the path of the extracted file"""
        if self.compressed():
            return os.path.splitext(self.path)[0]
        else:
            return self.path

    def fspath(self) -> str:
        return self.package.storage.fspath(self.extract_path())


class BinPackage:
    """
    A BIN package with several files to extract in it
    """

    def __init__(self, storage: Storage, path, files: List[BinPackageFile]):
        self.storage = storage
        self.path = path
        self.files = files

    def __str__(self):
        return "<{} {!r} files:{}>".format(self.__class__.__name__, self.path, len(self.files))

    def add_file(self, path, offset, size):
        self.files.append(BinPackageFile(self, path, offset, size))

    def missing_files(self):
        """Return files not already extracted"""
        ret = []
        for pkgfile in self.files:
            if os.path.isfile(pkgfile.fspath()):
                logger.debug("file already extracted: %s", pkgfile.path)
            else:
                ret.append(pkgfile)
        return ret

    def extract(self, force=False):
        """Download and extract the package

        If force is False, don't re-extract files already extracted.
        """

        if not force:
            pkgfiles = self.missing_files()
        else:
            pkgfiles = self.files
        if not pkgfiles:
            logger.debug("nothing to extract from %s", self.path)
            return

        logger.info("extracting files from %s", self.path)

        with self.storage.stream(self.path) as reader:
            # sort files by offset to extract while streaming the bin file
            for pkgfile in sorted(self.files, key=lambda f: f.offset):
                logger.debug("extracting %s", pkgfile.path)
                reader.skip_to(pkgfile.offset)
                fspath = pkgfile.fspath()
                try:
                    os.makedirs(os.path.dirname(fspath), exist_ok=True)
                    with open(fspath, mode='wb') as fout:
                        if pkgfile.compressed():
                            zobj = zlib.decompressobj(zlib.MAX_WBITS|32)
                            writer = lambda data: fout.write(zobj.decompress(data))
                            reader.copy(writer, pkgfile.size)
                            fout.write(zobj.flush())
                        else:
                            reader.copy(f.write, pkgfile.size)
                except:
                    # remove partially downloaded files
                    try:
                        os.remove(fspath)
                    except OSError:
                        pass
                    raise


def parse_component(storage: Storage, component: str):
    """Parse a component string representation to an object"""

    m = re.match(r'^(?:([sp]):)?(\w+)(?:=(|[0-9]+(?:\.[0-9]+)*)?)?$', component)
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


def parse_component_arg(parser, storage: Storage, component: str):
    """Wrapper around parse_component() to parse CLI arguments"""
    try:
        return parse_component(storage, component)
    except ValueError:
        parser.error(f"invalid component: {component}")


def command_download(parser, args):
    components = [parse_component_arg(parser, args.storage, component) for component in args.component]
    for component in components:
        if isinstance(component, (Project, ProjectVersion)):
            component.download(force=args.force, dry_run=args.dry_run)
        elif isinstance(component, (Solution, SolutionVersion)):
            component.download(args.langs, force=args.force, dry_run=args.dry_run)
        elif isinstance(component, PatchVersion):
            component.download(langs=args.langs, latest=args.latest, force=args.force, dry_run=args.dry_run)
        else:
            raise TypeError(component)


def command_versions(parser, args):
    if args.component == 'patch':
        # special case for listing patch versions
        for patch in PatchVersion.versions(args.storage, stored=args.stored):
            print(patch.version)
        return

    component = parse_component_arg(parser, args.storage, args.component)
    if isinstance(component, (Project, Solution)):
        for pv in component.versions():
            print(pv.version)
    else:
        parser.error(f"command cannot be used on {component}")


def command_projects(parser, args):
    component = parse_component_arg(parser, args.storage, args.component)
    if isinstance(component, SolutionVersion):
        for pv in sorted(component.projects(args.langs, force=args.force)):
            print(pv)
    elif isinstance(component, PatchVersion):
        projects = {pv for sv in component.solutions(latest=args.latest) for pv in sv.projects(args.langs, force=args.force)}
        for pv in sorted(projects):
            print(pv)
    else:
        parser.error(f"command cannot be used on {component}")


def command_solutions(parser, args):
    component = parse_component_arg(parser, args.storage, args.component)
    if isinstance(component, Project):
        for sln in Solution.list(args.storage):
            for sv in sln.versions(stored=True):
                if component in (pv.project for pv in sv.projects(True)):
                    print(sv)
    elif isinstance(component, ProjectVersion):
        for sln in Solution.list(args.storage):
            for sv in sln.versions(stored=True):
                if component in sv.projects(True):
                    print(sv)
    elif isinstance(component, PatchVersion):
        for sv in component.solutions(latest=args.latest):
            print(sv)
    else:
        parser.error(f"command cannot be used on {component}")


def command_files(parser, args):
    component = parse_component_arg(parser, args.storage, args.component)
    if isinstance(component, ProjectVersion):
        for pf in component.package_files(force=args.force):
            print(pf.extract_path())
    elif isinstance(component, SolutionVersion):
        for pv in component.projects(args.langs):
            for pf in pv.package_files(force=args.force):
                print(pf.extract_path())
    elif isinstance(component, PatchVersion):
        projects = {pv for sv in component.solutions(latest=args.latest) for pv in sv.projects(args.langs, force=args.force)}
        for pv in sorted(projects):
            for pf in pv.package_files(force=args.force):
                print(pf.extract_path())
    else:
        parser.error(f"command cannot be used on {component}")


def main():
    """main download procedure calls all the functions"""

    import argparse
    import textwrap

    parser = argparse.ArgumentParser(
        description="Download League of Legends game files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            The following formats are used for components:

              s:solution_name
              s:solution_name=version
              p:project_name
              p:project_name=version
              patch=version

            If version is empty, the latest one is used.
            The `s:` and `p:` prefixes can be omitted if type can be deduced
            from the name, which should always be the case.
            Examples:

              league_client_fr_fr=0.0.0.78
              league_client=
              lol_game_client_sln
              s:league_client_sln=0.0.1.195
              patch=7.23

        """),
    )

    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="be verbose")
    parser.add_argument('-o', '--storage', default='RADS',
                        help="directory for downloaded files (default: %(default)s)")
    parser.add_argument('-f', '--force', action='store_true',
                           help="force redownload of files")

    subparsers = parser.add_subparsers(dest='command', help="command")

    component_parser = argparse.ArgumentParser(add_help=False)
    component_parser.add_argument('--no-lang', dest='langs', action='store_false', default=True,
                                  help="ignore language projects from solutions")
    component_parser.add_argument('--lang', dest='langs', nargs='*',
                                  help="use projects from solutions in given languages (default: all)")
    component_parser.add_argument('-1', '--latest', action='store_true',
                                  help="consider only the most recent solutions when searching for patches")

    subparser = subparsers.add_parser('download', parents=[component_parser],
                                      help="download components")
    subparser.add_argument('-n', '--dry-run', action='store_true',
                           help="don't actually download package files, just list them")
    subparser.add_argument('component', nargs='+',
                           help="components to download")

    subparser = subparsers.add_parser('versions', parents=[component_parser],
                                      help="list versions")
    subparser.add_argument('-a', '--all', dest='stored', action='store_false', default=True,
                           help="when listing patch versions, don't use only stored solutions")
    subparser.add_argument('component',
                           help="solution, project or 'patch' to list patch versions")

    subparser = subparsers.add_parser('projects', parents=[component_parser],
                                      help="list projects")
    subparser.add_argument('component',
                           help="solution version or patch version")

    subparser = subparsers.add_parser('solutions', parents=[component_parser],
                                      help="list solution")
    subparser.add_argument('component',
                           help="project, project version or patch version")

    subparser = subparsers.add_parser('files', parents=[component_parser],
                                      help="list files")
    subparser.add_argument('component',
                           help="project version, solution version or patch version")

    args = parser.parse_args()
    args.storage = Storage(args.storage)

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

    globals()["command_%s" % args.command.replace('-', '_')](parser, args)


if __name__ == "__main__":
    main()
