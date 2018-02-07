#!/usr/bin/env python3
import os
import argparse
import textwrap
import logging
import cdragontoolbox
from cdragontoolbox.storage import (
    Version,
    Storage,
    Project, ProjectVersion,
    Solution, SolutionVersion,
    PatchVersion,
    parse_component,
)
from cdragontoolbox.wad import (
    Wad,
    load_hashes, save_hashes,
    discover_hashes,
)
from cdragontoolbox.export import (
    Exporter,
    PatchExporter,
)


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
            component.download(dry_run=args.dry_run)
        elif isinstance(component, (Solution, SolutionVersion)):
            component.download(args.langs, dry_run=args.dry_run)
        elif isinstance(component, PatchVersion):
            component.download(langs=args.langs, latest=args.latest, dry_run=args.dry_run)
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
        for pv in sorted(component.projects(args.langs)):
            print(pv)
    elif isinstance(component, PatchVersion):
        projects = {pv for sv in component.solutions(latest=args.latest) for pv in sv.projects(args.langs)}
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
        for path in component.filepaths():
            print(path)
    elif isinstance(component, SolutionVersion):
        for pv in component.projects(args.langs):
            for path in pv.filepaths():
                print(path)
    elif isinstance(component, PatchVersion):
        projects = {pv for sv in component.solutions(latest=args.latest) for pv in sv.projects(args.langs)}
        for pv in sorted(projects):
            for path in pv.filepaths():
                print(path)
    else:
        parser.error(f"command cannot be used on {component}")


def command_wad_extract(parser, args):
    if not os.path.isfile(args.wad):
        parser.error("WAD file does not exist")
    if not args.output:
        args.output = os.path.splitext(args.wad)[0]
    if os.path.exists(args.output) and not os.path.isdir(args.output):
        parser.error("output is not a directory")

    hashes = load_hashes(args.hashes)
    wad = Wad(args.wad, hashes=hashes)
    if args.unknown == 'yes':
        pass # don't filter
    elif args.unknown == 'only':
        wad.files = [wf for wf in wad.files if wf.path is None]
    elif args.unknown == 'no':
        wad.files = [wf for wf in wad.files if wf.path is not None]

    wad.guess_extensions()
    wad.extract(args.output)


def command_wad_list(parser, args):
    if not os.path.isfile(args.wad):
        parser.error("WAD file does not exist")

    hashes = load_hashes(args.hashes)
    wad = Wad(args.wad, hashes=hashes)

    wadfiles = [(wf.path or ('?.%s' % wf.ext if wf.ext else '?'), wf.path_hash) for wf in wad.files]
    for path, h in sorted(wadfiles):
        print("%016x %s" % (h, path))


def command_hashes_guess(parser, args):
    hashes = load_hashes(args.hashes)

    wads = [Wad(path) for path in args.wad]
    unknown_hashes = set()
    for wad in wads:
        unknown_hashes |= set(wadfile.path_hash for wadfile in wad.files)
    unknown_hashes -= set(hashes)

    new_hashes = {}
    if args.search:
        for wad in wads:
            new_hashes.update(wad.guess_hashes(unknown_hashes))
    new_hashes.update(Wad.guess_hashes_from_known(hashes, unknown_hashes))

    for h, path in new_hashes.items():
        print("%016x %s" % (h, path))

    if not args.dry_run and new_hashes:
        hashes.update(new_hashes)
        save_hashes(args.hashes, hashes)


def command_export(parser, args):
    storage = args.storage

    if args.symlinks:
        # symlink are not supported on Windows because of the
        # 'target_is_directory' parameter which requires extra handling
        if os.name == 'nt' or not hasattr(os, 'symlink'):
            parser.error("symlinks not supported on this platform")

    if not args.patch:
        # multiple patch (update only)
        if not args.update:
            parser.error("patch version required without --update")
        if args.previous:
            parser.error("patch version required with --previous or --full")
        exporter = Exporter(storage, args.output)
        exporter.update()
        if args.symlinks:
            exporter.create_symlinks()
    else:
        # single patch
        # retrieve target and previous patch versions
        patch = PatchVersion.version(storage, Version(args.patch))
        if patch is None:
            parser.error("patch not found: %s" % args.patch)
        if args.previous == 'none':
            previous_patch = None
        elif args.previous:
            previous_patch = PatchVersion.version(storage, Version(args.previous), stored=True)
            if previous_patch is None:
                parser.error("previous patch not found: %s" % args.patch)
        else:
            it = PatchVersion.versions(storage, stored=True)
            for v in it:
                if v.version == args.patch:
                    previous_patch = next(it)
                    break
            else:
                parser.error("cannot guess previous patch")

        exporter = PatchExporter(os.path.join(args.output, str(patch.version)), patch, previous_patch)
        exporter.export(overwrite=not args.update)
        exporter.write_links()
        if args.symlinks:
            exporter.create_symlinks()


def command_upload(parser, args):
    storage = args.storage

    exporter = Exporter(storage, args.output)
    if args.patch:
        version = Version(args.patch)
        for e in exporter.exporters:
            if e.patch.version == version:
                exporter = e
                break
        else:
            parser.error("patch version not found")
    exporter.upload(args.target)


def create_parser():
    parser = argparse.ArgumentParser("cdragontoolbox",
        description="Toolbox to work with League of Legends game files",
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

    subparsers = parser.add_subparsers(dest='command', help="command")

    default_storage = os.environ.get('CDRAGONTOOLBOX_STORAGE', 'RADS')
    default_export = os.environ.get('CDRAGONTOOLBOX_EXPORT', 'export')

    # component-based commands

    component_parser = argparse.ArgumentParser(add_help=False)
    component_parser.add_argument('-s', '--storage', default=default_storage,
                                  help="directory for downloaded files (default: %(default)s)")
    component_parser.add_argument('--no-lang', dest='langs', action='store_false', default=True,
                                  help="ignore language projects from solutions")
    component_parser.add_argument('--lang', dest='langs', nargs='*',
                                  help="use projects from solutions in given languages (default: all)")
    component_parser.add_argument('-1', '--latest', action='store_true',
                                  help="consider only the most recent solutions when searching for patches")

    subparser = subparsers.add_parser('download', parents=[component_parser],
                                      help="download components to the storage")
    subparser.add_argument('-n', '--dry-run', action='store_true',
                           help="don't actually download package files, just list them")
    subparser.add_argument('component', nargs='+',
                           help="components to download")

    subparser = subparsers.add_parser('versions', parents=[component_parser],
                                      help="list versions of a component")
    subparser.add_argument('-a', '--all', dest='stored', action='store_false', default=True,
                           help="when listing patch versions, don't use only stored solutions")
    subparser.add_argument('component',
                           help="solution, project or 'patch' to list patch versions")

    subparser = subparsers.add_parser('projects', parents=[component_parser],
                                      help="list projects of a component")
    subparser.add_argument('component',
                           help="solution version or patch version")

    subparser = subparsers.add_parser('solutions', parents=[component_parser],
                                      help="list solutions of a component")
    subparser.add_argument('component',
                           help="project, project version or patch version")

    subparser = subparsers.add_parser('files', parents=[component_parser],
                                      help="list files of a component")
    subparser.add_argument('component',
                           help="project version, solution version or patch version")


    # WAD commands

    subparser = subparsers.add_parser('wad-extract',
                                      help="extract a WAD file")
    subparser.add_argument('-o', '--output',
                           help="extract directory")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths (JSON or plain text)")
    subparser.add_argument('-u', '--unknown', choices=('yes', 'only', 'no'), default='yes',
                           help="control extract of unknown files (default: %(default)s)")
    subparser.add_argument('wad',
                           help="WAD file to extract")

    subparser = subparsers.add_parser('wad-list',
                                      help="list WAD content")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths (JSON or plain text)")
    subparser.add_argument('wad',
                           help="WAD file to list")

    subparser = subparsers.add_parser('hashes-guess',
                                      help="guess hashes from WAD content")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths (JSON or plain text)")
    subparser.add_argument('-n', '--dry-run', action='store_true',
                           help="list new hashes but don't update the hashes file")
    subparser.add_argument('-g', '--search', action='store_true',
                           help="search for paths in WAD files")
    subparser.add_argument('wad', nargs='+',
                           help="WAD files to analyze")


    # export command

    subparser = subparsers.add_parser('export',
                                      help="export files to directories, separated by patch")
    subparser.add_argument('-s', '--storage', default=default_storage,
                           help="directory for downloaded files (default: %(default)s)")
    subparser.add_argument('-o', '--output', default=default_export,
                           help="directory for files to export (default: %(default)s)")
    subparser.add_argument('-u', '--update', action='store_true',
                           help="update the export, skip already extracted files")
    subparser.add_argument('-L', '--symlinks', action='store_true',
                           help="create symlinks (if supported by platform)")
    subparser.add_argument('--previous',
                           help="previous patch version to compare with (default: guessed)")
    subparser.add_argument('--full', dest='previous', action='store_const', const='none',
                           help="export the whole patch (don't compare with a previous one)")
    subparser.add_argument('patch', nargs='?',
                           help="patch version to export, can be omitted to update all exported patches")

    subparser = subparsers.add_parser('upload',
                                      help="synchronize exported files to a remote host")
    subparser.add_argument('-s', '--storage', default=default_storage,
                           help="directory for downloaded files (default: %(default)s)")
    subparser.add_argument('-o', '--output', default=default_export,
                           help="directory of source exported files (default: %(default)s)")
    subparser.add_argument('target',
                           help="remote target and path, suitable for rsync")
    subparser.add_argument('patch', nargs='?',
                           help="patch version to export, can be omitted to update all exported patches")

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.verbose >= 3:
        loglevel = logging.DEBUG
    elif args.verbose >= 1:
        loglevel = logging.INFO
    else:
        loglevel = logging.WARNING

    logging.basicConfig(
        level=loglevel,
        datefmt='%H:%M:%S',
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )

    logger = cdragontoolbox.logger
    if args.verbose >= 2:
        logger.setLevel(logging.DEBUG)
    elif args.verbose >= 1:
        logger.setLevel(logging.INFO)

    if hasattr(args, 'storage'):
        args.storage = Storage(args.storage)

    globals()["command_%s" % args.command.replace('-', '_')](parser, args)


if __name__ == "__main__":
    main()
