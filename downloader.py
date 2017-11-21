#!/usr/bin/env python3
import os
import re
import sys
import zlib
import json
from contextlib import contextmanager
from typing import List, Dict, IO, Union, Optional, Generator
import logging
import requests

logger = logging.getLogger("downloader")


class Version:
    def __init__(self, s):
        self.s = s
        self.t = tuple(int(x) for x in s.split('.'))

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
            raise False

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

    def versions(self) -> List['SolutionVersion']:
        """Retrieve the list of versions of this solution"""
        logger.debug("retrieve versions of %s", self)
        listing = self.storage.request_text(f"{self.path}/releaselisting")
        return [SolutionVersion(self, Version(l)) for l in listing.splitlines()]

    def storage_versions(self) -> List['SolutionVersion']:
        """Get a list of versions on storage"""
        fspath = self.storage.fspath(self.path)
        if not os.path.isdir(fspath):
            return []
        ret = []
        for path in os.listdir(fspath):
            if not os.path.isdir(os.path.join(fspath, path)):
                continue
            ret.append(SolutionVersion(self, Version(path)))
        return sorted(ret)


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
        with open(self.solution.storage.fspath()) as f:
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

    def dependencies_for_langs(self, langs, force=False) -> List[ProjectVersion]:
        """Return a list of dependencies for provided languages
        
        langs can have the following values:
          False -- common dependencies, not language-dependent
          True -- all languages
          lang -- provided languages
          [lang, ...] -- provided languages
        """
        dependencies = self.dependencies()
        if langs is False:
            return dependencies[None]
        elif langs is True:
            return list({pv for pvs in dependencies.values() for pv in pvs})
        elif isinstance(lang, str):
            return dependencies[lang]
        else:
            return list({pv for pv in dependencies[lang] for lang in langs})

    def download(self, langs, force=False, dry_run=False):
        """Download solution version files"""

        logger.info("downloading solution %s", self)
        for pv in self.dependencies_for_langs(langs, force=force):
            pv.download(force=force, dry_run=dry_run)

    def patch_version(self) -> Optional[Version]:
        """Return patch version or None if it cannot be retrieved"""

        if self.solution.name == 'league_client_sln':
            for pv in self.dependencies_for_langs(False):
                if pv.project.name == 'league_client':
                    break
            else:
                raise ValueError("league_client project not found for %s" % self)

            for pkgfile in pv.package_files():
                if pkgfile.extract_path().endswith('/system.yaml'):
                    if os.path.isfile(pkgfile.fspath()):
                        pkgfile.package.extract()
                    break
            else:
                raise ValueError("system.yaml not found for %s" % pv)
            with open(pkgfile.fspath()) as f:
                for line in f:
                    #TODO do proper yaml parsing
                    m = re.match(r"""^ *game-branch: ["']([0-9.]+)["']$""", line)
                    if m:
                        return m.group(1)
                else:
                    raise ValueError("patch version not found in %s" % system_yaml_path)
        else:
            logger.info("no known way to retrieve patch version for solution %s", self.solution.name)



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


def parse_component(parser, storage: Storage, component: str, need_version=False):
    m = re.match(r'^(?:([sp]):)?(\w+)(?:=([0-9]+(?:\.[0-9]+)*))?$', component)
    if not m:
        parser.error(f"invalid component: {component}")
    typ, name, version = m.group(1, 2, 3)
    if not typ:
        typ = 's' if name.endswith('_sln') else 'p'
    if version:
        version = Version(version)
    if typ == 'p':
        project = Project(storage, name)
        if version is not None:
            return ProjectVersion(project, version)
        elif need_version:
            return project.versions()[0]
        else:
            return project
    elif typ == 's':
        solution = Solution(storage, name)
        if version is not None:
            return SolutionVersion(solution, version)
        elif need_version:
            return solution.versions()[0]
        else:
            return solution


def command_download(parser, args):
    if args.no_lang and args.lang:
        parser.error("--no-lang and --lang are incompatible")
    elif args.no_lang:
        langs = False
    elif args.lang:
        langs = args.lang
    else:
        langs = True

    components = [parse_component(parser, args.storage, component, True) for component in args.component]

    for component in components:
        if isinstance(component, ProjectVersion):
            component.download(force=args.force, dry_run=args.dry_run)
        elif isinstance(component, SolutionVersion):
            component.download(langs, force=args.force, dry_run=args.dry_run)
        else:
            raise TypeError(component)


def command_versions(parser, args):
    component = parse_component(parser, args.storage, args.component)
    if isinstance(component, (Project, Solution)):
        for pv in component.versions():
            print(pv.version)
    elif isinstance(component, SolutionVersion):
        pvs = component.dependencies_for_langs(True)
        for pv in sorted(pvs, key=lambda o: (o.project.name, o.version)):
            print("%s %s" % (pv.project.name, pv.version))
    else:
        raise TypeError(component)


def command_patches(parser, args):
    solution = Solution(args.storage, 'league_client_sln')

    patches = {} # {patch: [SolutionVersion, ...]}
    if args.version:
        # browse all solution versions for the requested patch
        # stop once the earliest patch has been found
        earliest_patch = sorted(args.version)[0]
        for sv in solution.versions():
            patch = sv.patch_version()
            if patch is None:
                continue
            if args.last_solution and patch in patches:
                continue
            if patch in args.version:
                patches.setdefault(patch, []).append(sv)
            elif patch < earliest_patch:
                break
        not_found = set(args.version) - set(patches)
        if not_found:
            raise ValueError("patches not found: %s" % ' '.join(sorted(not_found)))
    else:
        # use stored versions
        for sv in solution.storage_versions():
            patch = sv.patch_version()
            if patch is None:
                continue
            if args.last_solution and patch in patches:
                continue
            patches.setdefault(patch, []).append(sv)

    patch_content = {} # {patch: sorted_content}
    for patch, svs in patches.items():
        if args.element == 'solutions':
            content = set(svs)
        elif args.element == 'projects':
            content = {pv for sv in svs for pv in sv.dependencies_for_langs(True)}
        elif args.element == 'files':
            pvs = (pv for sv in svs for pv in sv.dependencies_for_langs(True))
            content = {pf.extract_path() for pv in pvs for pf in pv.package_files()}
        patch_content[patch] = sorted(content)

    if args.version and len(args.version) == 1:
        for content in patch_content[args.version[0]]:
            print(content)
    else:
        for patch in sorted(patch_content, reverse=True):
            print(patch)
            for content in patch_content[patch]:
                print(f"  {content}")


def main():
    """main download procedure calls all the functions"""

    import argparse
    import textwrap
    script_dir = os.path.dirname(__file__)

    parser = argparse.ArgumentParser(
        description="Download League of Legends game files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            The following format is supported components:

              [type:](name)[=version]

            Where `type` is `s` for solution and `p` for project.
            If omitted, it is deduced from the name.
            If version is not provided, the latest one is used.
            Examples:

              p:some_project
              s:some_solution
              league_client_sln=0.0.1.195
              lol_game_client_sln

        """),
    )

    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="be verbose")
    parser.add_argument('-o', '--storage', default='RADS',
                        help="directory for downloaded files (default: %(default)s)")

    subparsers = parser.add_subparsers(dest='command', help="command")

    subparser = subparsers.add_parser('download', help="download components")
    subparser.add_argument('-f', '--force', action='store_true',
                        help="force redownload of files")
    subparser.add_argument('-n', '--dry-run', action='store_true',
                        help="don't actually download package files, just list them")
    subparser.add_argument('--no-lang', action='store_true',
                           help="don't download language projects")
    subparser.add_argument('--lang', nargs='*',
                           help="for solutions, download projects in given languages (default: all)")
    subparser.add_argument('component', nargs='+',
                           help="components to download")

    subparser = subparsers.add_parser('versions', help="list versions of a component")
    subparser.add_argument('component',
                           help="component to list versions for")

    subparser = subparsers.add_parser('patches', help="print elements used by patch versions")
    subparser.add_argument('-e', '--element', choices=('files', 'projects', 'solutions'), required=True,
                           help="which elements to display")
    subparser.add_argument('-1', '--last-solution', action='store_true',
                           help="for each patch, consider only the most recent solution")
    subparser.add_argument('version', nargs='*',
                           help="versions to display (default: browse solutions in storage)")

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

    globals()["command_%s" % args.command](parser, args)


if __name__ == "__main__":
    main()
