#!/usr/bin/env python3
import os
import re
import sys
import zlib
import json
from contextlib import contextmanager
from typing import List, Dict
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


class Downloader:
    """
    Download files from Riot server
    """

    # all available values are in system.yaml
    # values in use are in RADS/system/system.cfg
    # region is ignored here (it is not actually needed)
    DOWNLOAD_URL = "l3cdn.riotgames.com"
    DOWNLOAD_PATH = "/releases/live"

    def __init__(self, url=None):
        if url is None:
            url = f"http://{self.DOWNLOAD_URL}{self.DOWNLOAD_PATH}/"
        self.url = url
        self.s = requests.session()

    def get(self, path, **kwargs) -> requests.Response:
        """Request a path, returns a requests.Response object"""
        return self.s.get(self.url + path, **kwargs)

    def text(self, path) -> str:
        """Request a path, returns content as text"""
        r = self.get(path)
        r.raise_for_status()
        return r.content.decode('utf-8')

    def lines(self, path) -> List[str]:
        return self.text(path).split('\r\n')[:-1]

    def download(self, path, output) -> None:
        """Download to a path

        If output ends with a '/', append path's basename to it.
        """

        if output.endswith('/'):
            output = os.path.join(output, os.path.basename(path))
        os.makedirs(os.path.dirname(output), exist_ok=True)
        r = self.s.get(self.url + path)
        r.raise_for_status()
        with open(output, 'wb') as f:
            f.write(r.content)

    class StreamReader:
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

    @contextmanager
    def stream(self, path) -> StreamReader:
        """Request a path for streaming download"""
        with self.s.get(self.url + path, stream=True) as r:
            r.raise_for_status()
            yield self.StreamReader(r)


dl = Downloader()


class Project:
    """
    RADS project
    """

    def __init__(self, name):
        self.path = f"projects/{name}/releases"
        self.name = name

    def __str__(self):
        return "<{} {}>".format(self.__class__.__name__, self.name)

    def __repr__(self):
        return "{}({!r})".format(self.__class__.__qualname__, self.name)

    def __eq__(self, other):
        if isinstance(other, Project):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def versions(self) -> List['ProjectVersion']:
        """Retrieve the list of versions of this project"""
        logger.debug("retrieve versions of %s", self)
        return [ProjectVersion(self, Version(l)) for l in dl.lines(f"{self.path}/releaselisting")]


class ProjectVersion:
    """
    A single version of a project
    """

    def __init__(self, project: Project, version: Version):
        self.path = f"{project.path}/{version}"
        self.project = project
        self.version = version

    def __str__(self):
        return "<{} {} {}>".format(self.__class__.__name__, self.project.name, self.version)

    def __repr__(self):
        return "{}({!r}, {!r})".format(self.__class__.__qualname__, self.project, self.version)

    def __eq__(self, other):
        if isinstance(other, ProjectVersion):
            return self.project == other.project and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.project, self.version))

    def packages(self):
        """Parse packages from the packagemanifest"""
        logger.debug("retrieve packages of %s", self)
        return BinPackage.from_manifest(f"{self.path}/packages/files/packagemanifest")


class Solution:
    """
    RADS solution

    There are currently two active solutions:
    `league_client_sln` and `lol_game_client_sln`.
    """

    def __init__(self, name):
        self.path = f"solutions/{name}/releases"
        self.name = name

    def __str__(self):
        return "<{} {}>".format(self.__class__.__name__, self.name)

    def __repr__(self):
        return "{}({!r})".format(self.__class__.__qualname__, self.name)

    def __eq__(self, other):
        if isinstance(other, Solution):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def versions(self) -> List['SolutionVersion']:
        """Retrieve the list of versions of this solution"""
        logger.debug("retrieve versions of %s", self)
        return [SolutionVersion(self, Version(l)) for l in dl.lines(f"{self.path}/releaselisting")]


class SolutionVersion:
    """
    A single version of a solution
    """

    def __init__(self, solution: Solution, version: Version):
        self.path = f"{solution.path}/{version}"
        self.solution = solution
        self.version = version

    def __str__(self):
        return "<{} {} {}>".format(self.__class__.__name__, self.solution.name, self.version)

    def __repr__(self):
        return "{}({!r}, {!r})".format(self.__class__.__qualname__, self.solution, self.version)

    def __eq__(self, other):
        if isinstance(other, SolutionVersion):
            return self.solution == other.solution and self.version == other.version
        return False

    def __hash__(self):
        return hash((self.solution, self.version))

    def dependencies(self) -> Dict[str, List[ProjectVersion]]:
        """Parse dependencies from the solutionmanifest

        Return a map of project versions for each lang code.
        The entry None is set to all required project versions.
        """

        logger.debug("retrieve dependencies of %s", self)

        lines = dl.lines(f"{self.path}/solutionmanifest")
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
            projects[name] = ProjectVersion(Project(name), Version(version))

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


class BinPackage:
    """
    A BIN package with several files to extract in it
    """

    class File:
        """A single file in a BIN package"""

        def __init__(self, path, offset, size):
            self.path = path.lstrip('/')
            self.offset = offset
            self.size = size

        def __str__(self):
            return "<{} {!r}>".format(self.__class__.__name__, self.path)

        def __repr__(self):
            return "{}({!r}, {!r}, {!r}, {!r})".format(self.__class__.__qualname__, self.path, self.offset, self.size)

        def compressed(self):
            return self.path.endswith('.compressed')

        def output_path(self, base):
            if self.compressed():
                path = os.path.splitext(self.path)[0]
            else:
                path = self.path
            return os.path.join(base, path)


    def __init__(self, path, files: List[File]):
        self.path = path
        self.files = files

    def __str__(self):
        return "<{} {!r} files:{}>".format(self.__class__.__name__, self.path, len(self.files))

    @classmethod
    def from_manifest(cls, path) -> List['BinPackage']:
        """Return a list of packages from a packagemanifest"""

        lines = dl.lines(path)
        dirpath = os.path.dirname(path)
        assert lines[0].startswith('PKG1'), "unexpected packagemanifest magic line"
        packages = {}  # {path: BinPackage}
        for line in lines[1:]:
            file_path, package_name, offset, size, typ = line.split(',')
            package_path = f"{dirpath}/{package_name}"
            if package_path not in packages:
                packages[package_path] = cls(package_path, [])
            packages[package_path].add_file(file_path, int(offset), int(size))
        return list(packages.values())

    def add_file(self, path, offset, size):
        self.files.append(self.File(path, offset, size))

    def missing_files(self, output):
        """Return files not already extracted"""
        ret = []
        for pkgfile in self.files:
            foutput = pkgfile.output_path(output)
            if os.path.isfile(foutput):
                logger.debug("file already extracted: %s", pkgfile.path)
            else:
                ret.append(pkgfile)
        return ret

    def extract(self, output, force=False):
        """Download and extract the package

        If force is False, don't re-extract files already extracted.
        """

        if not force:
            pkgfiles = self.missing_files(output)
        else:
            pkgfiles = self.files
        if not pkgfiles:
            logger.debug("nothing to extract from %s", self.path)
            return

        logger.info("extracting files from %s", self.path)

        with dl.stream(self.path) as reader:
            # sort files by offset to extract while streaming the bin file
            for pkgfile in sorted(self.files, key=lambda f: f.offset):
                logger.debug("extracting %s", pkgfile.path)
                reader.skip_to(pkgfile.offset)
                foutput = pkgfile.output_path(output)
                os.makedirs(os.path.dirname(foutput), exist_ok=True)
                try:
                    with open(foutput, 'wb') as fout:
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
                        os.remove(foutput)
                    except OSError:
                        pass
                    raise


def parse_component(parser, component, need_version=False):
    m = re.match(r'^(?:([sp]):)?(\w+)(?:=([0-9]+(?:\.[0-9]+)*))?$', component)
    if not m:
        parser.error(f"invalid component: {component}")
    typ, name, version = m.group(1, 2, 3)
    if not typ:
        typ = 's' if name.endswith('_sln') else 'p'
    if version:
        version = Version(version)
    if typ == 'p':
        project = Project(name)
        if version is not None:
            return ProjectVersion(project, version)
        elif need_version:
            return project.versions()[0]
        else:
            return project
    elif typ == 's':
        solution = Solution(name)
        if version is not None:
            return SolutionVersion(solution, version)
        elif need_version:
            return solution.versions()[0]
        else:
            return solution


def command_download(parser, args):
    if args.no_lang and args.lang:
        parser.error("--no-lang and --lang are incompatible")
    components = [parse_component(parser, component, True) for component in args.component]

    # gather project versions to download
    project_versions = set()
    for component in components:
        if isinstance(component, ProjectVersion):
            project_versions.add(component)
        elif isinstance(component, SolutionVersion):
            dependencies = component.dependencies()
            if args.no_lang:
                project_versions |= set(dependencies[None])
            elif args.lang:
                for lang in args.lang:
                    project_versions |= set(dependencies[lang])
            else:
                for l in dependencies.values():
                    project_versions |= set(l)
        else:
            raise TypeError(component)

    logger.info("projects to download: %d", len(project_versions))
    for pv in project_versions:
        logger.info("downloading project %s=%s", pv.project.name, pv.version)
        for package in pv.packages():
            if args.dry_run:
                if args.force or package.missing_files(args.output):
                    logger.info("package to extract: %s", package.path)
                else:
                    logger.debug("package already extracted: %s", package.path)
            else:
                package.extract(args.output, args.force)


def command_versions(parser, args):
    component = parse_component(parser, args.component)
    if isinstance(component, (Project, Solution)):
        for pv in component.versions():
            print(pv.version)
    elif isinstance(component, SolutionVersion):
        dependencies = component.dependencies()
        all_pvs = {pv for pvs in dependencies.values() for pv in pvs}
        for pv in sorted(all_pvs, key=lambda o: (o.project.name, o.version)):
            print("%s %s" % (pv.project.name, pv.version))
    else:
        raise TypeError(component)


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
        """),
    )

    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="be verbose")

    subparsers = parser.add_subparsers(dest='command', help="command")

    subparser = subparsers.add_parser('download', help="download components")
    subparser.add_argument('-o', '--output', default='RADS',
                        help="output directory for downloaded files (default: %(default)s)")
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

    globals()["command_%s" % args.command](parser, args)


if __name__ == "__main__":
    main()
