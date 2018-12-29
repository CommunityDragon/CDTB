#!/usr/bin/env python3
import os
import sys
import argparse
import json
import textwrap
import fnmatch
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
    wads_from_component,
)
from cdragontoolbox.export import (
    CdragonRawPatchExporter,
)
from cdragontoolbox.binfile import (
    BinFile,
)
from cdragontoolbox.hashes import (
    HashFile,
    default_hashfile,
    LcuHashGuesser,
    GameHashGuesser,
)


def parse_component_arg(parser, storage: Storage, component: str):
    """Wrapper around parse_component() to parse CLI arguments"""
    try:
        return parse_component(storage, component)
    except ValueError:
        parser.error(f"invalid component: {component}")


def parse_storage_args(parser, args) -> Storage:
    """Parse storage-related arguments into a Storage"""

    default_path = os.environ.get('CDRAGONTOOLBOX_STORAGE')
    default_cdn = os.environ.get('CDRAGONTOOLBOX_CDN', 'default')

    cdn = default_cdn if args.cdn is None else args.cdn
    # don't use CDRAGONTOOLBOX_STORAGE when using non-default --cdn is set to
    # avoid mixing files from different CDNs
    if cdn != default_cdn and default_path is not None and args.storage is None:
        parser.error("--storage must be provided when changing --cdn value")

    path = default_path if args.storage is None else args.storage
    if path is None:
        path = "RADS" if cdn == 'default' else f"RADS.{cdn}"

    storage_url = getattr(Storage, f"URL_{cdn}".upper())
    return Storage(path, storage_url)


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
        for sln in args.storage.list_solutions():
            for sv in sln.versions(stored=True):
                if component in (pv.project for pv in sv.projects(True)):
                    print(sv)
    elif isinstance(component, ProjectVersion):
        for sln in args.storage.list_solutions():
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
        for path in component.filepaths(args.langs):
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

    if args.hashes is None:
        hashfile = default_hashfile(args.wad)
    else:
        hashfile = HashFile(args.hashes)
    wad = Wad(args.wad, hashes=hashfile.load())
    if args.unknown == 'yes':
        pass  # don't filter
    elif args.unknown == 'only':
        wad.files = [wf for wf in wad.files if wf.path is None]
    elif args.unknown == 'no':
        wad.files = [wf for wf in wad.files if wf.path is not None]

    if args.pattern:
        wad.files = [wf for wf in wad.files if any(fnmatch.fnmatchcase(wf.path, p) for p in args.pattern)]

    wad.guess_extensions()
    wad.extract(args.output, overwrite=not args.lazy)


def command_wad_list(parser, args):
    if not os.path.isfile(args.wad):
        parser.error("WAD file does not exist")

    if args.hashes is None:
        hashfile = default_hashfile(args.wad)
    else:
        hashfile = HashFile(args.hashes)
    wad = Wad(args.wad, hashes=hashfile.load())

    wadfiles = [(wf.path or ('?.%s' % wf.ext if wf.ext else '?'), wf.path_hash) for wf in wad.files]
    for path, h in sorted(wadfiles):
        print(f"{h:016x} {path}")


def command_hashes_guess(parser, args):
    all_methods = [
        ("grep", "search for hashes in WAD files"),
        ("numbers", "substitute numbers in basenames"),
        ("basenames", "substitute basenames"),
        ("words", "substitute known words in basenames"),
        ("ext", "substitute extensions"),
        ("regionlang", "substitute region and lang (LCU only)"),
        ("plugin", "substitute plugin name (LCU only)"),
        ("skin-num", "substitute skinNN numbers (game only)"),
        ("character", "substitute character name (game only)"),
        ("prefixes", "check basename prefixes (game only)"),
    ]
    all_method_names = [name for name, _ in all_methods]

    if args.list_methods:
        name_width = max(len(name) for name in all_method_names)
        for name, desc in all_methods:
            print(f"  {name:{name_width}}  {desc}")
        return
    elif not args.wad:
        parser.error("neither \"wad\" nor \"--list-methods\" argument was found")

    if not args.methods:
        method_names = [name for name in all_method_names if name not in ("basenames", "words")]
    else:
        method_names = [s.strip() for s in args.methods.split(',')]
        for name in method_names:
            if name not in all_method_names:
                parser.error(f"unknown guessing method: {name}")

    # collect WAD paths
    wads = []
    for path_or_component in args.wad:
        try:
            component = parse_component(args.storage, path_or_component)
        except ValueError:
            wads.append(Wad(path_or_component))
            continue
        wads += wads_from_component(component)

    # guess LCU hashes
    guesser = LcuHashGuesser.from_wads(wads)
    if guesser.unknown:
        nunknown = len(guesser.unknown)
        if "grep" in method_names:
            for wad in guesser.wads:
                wad.guess_extensions()
                guesser.grep_wad(wad)
        if "numbers" in method_names:
            guesser.substitute_numbers()
        if "basenames" in method_names:
            guesser.substitute_basenames()
        if "words" in method_names:
            guesser.substitute_basename_words()
        if "ext" in method_names:
            guesser.substitute_extensions()
        if "regionlang" in method_names:
            guesser.substitute_region_lang()
        if "plugin" in method_names:
            guesser.substitute_plugin()

        nfound = nunknown - len(guesser.unknown)
        if nfound:
            print(f"found LCU hashes: {nfound}")
            if not args.dry_run:
                guesser.save()

    # guess game hashes
    guesser = GameHashGuesser.from_wads(wads)
    if guesser.unknown:
        nunknown = len(guesser.unknown)
        if "grep" in method_names:
            for wad in guesser.wads:
                wad.guess_extensions()
                guesser.grep_wad(wad)
        if "numbers" in method_names:
            guesser.substitute_numbers()
        if "basenames" in method_names:
            guesser.substitute_basenames()
        if "words" in method_names:
            guesser.substitute_basename_words()
        if "ext" in method_names:
            guesser.substitute_extensions()
        if "skin-num" in method_names:
            guesser.substitute_skin_numbers()
        if "character" in method_names:
            guesser.substitute_character()
        if "prefixes" in method_names:
            guesser.check_basename_prefixes()

        nfound = nunknown - len(guesser.unknown)
        if nfound:
            print(f"found game hashes: {nfound}")
            if not args.dry_run:
                guesser.save()


def command_export(parser, args):
    storage = args.storage

    if args.symlinks:
        # symlink are not supported on Windows because of the
        # 'target_is_directory' parameter which requires extra handling
        if os.name == 'nt' or not hasattr(os, 'symlink'):
            parser.error("symlinks not supported on this platform")

    overwrite = not args.lazy
    symlinks = bool(args.symlinks)

    if not args.patch:
        # multiple patches (update only)
        if args.previous:
            parser.error("patch version required with --previous or --full")
        if args.first:
            parser.error("--from is required when no patch is provided")
        exporters = CdragonRawPatchExporter.from_directory(storage, args.output, Version(args.first), symlinks=symlinks)
        for exporter in exporters:
            exporter.process(overwrite=overwrite)
    else:
        if args.first:
            parser.error("--from cannot be used when providing a patch")
        # single patch
        # retrieve target and previous patch versions
        patch = PatchVersion.version(storage, None if args.patch == 'latest' else Version(args.patch))
        if patch is None:
            parser.error(f"patch not found: {args.patch}")
        if args.previous == 'none':
            previous_patch = None
        elif args.previous:
            previous_patch = PatchVersion.version(storage, Version(args.previous), stored=True)
            if previous_patch is None:
                parser.error(f"previous patch not found: {patch.version}")
        else:
            it = PatchVersion.versions(storage, stored=True)
            for v in it:
                if v.version == patch.version:
                    previous_patch = next(it)
                    break
            else:
                parser.error("cannot guess previous patch")

        exporter = CdragonRawPatchExporter(os.path.join(args.output, str(patch.version)), patch, previous_patch, symlinks=symlinks)
        exporter.process(overwrite=overwrite)


def command_bin_dump(parser, args):
    if not os.path.isfile(args.bin):
        parser.error("BIN file does not exist")

    with open(args.bin, 'rb') as f:
        binfile = BinFile(f)
    if args.json:
        json.dump(binfile.to_serializable(), sys.stdout)
    else:
        for entry in binfile.entries:
            print(entry)


def create_parser():
    parser = argparse.ArgumentParser('cdragontoolbox',
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

    default_export = os.environ.get('CDRAGONTOOLBOX_EXPORT', 'export')

    # storage arguments
    storage_parser = argparse.ArgumentParser(add_help=False)
    storage_parser.add_argument('-s', '--storage', default=None,
                                help="directory for downloaded files")
    storage_parser.add_argument('--cdn', choices=["default", "pbe", "kr"], default=None,
                                help="use a different CDN")

    # component-based commands

    component_parser = argparse.ArgumentParser(add_help=False, parents=[storage_parser])
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
                           help="hashes of known paths")
    subparser.add_argument('-p', '--pattern', action='append',
                           help="extract only files matching pattern with shell-like wildcards")
    subparser.add_argument('-u', '--unknown', choices=('yes', 'only', 'no'), default='yes',
                           help="control extract of unknown files (default: %(default)s)")
    subparser.add_argument('--lazy', action='store_true',
                           help="don't overwrite files, assume they are already correctly extracted")
    subparser.add_argument('wad',
                           help="WAD file to extract")

    subparser = subparsers.add_parser('wad-list',
                                      help="list WAD content")
    subparser.add_argument('-H', '--hashes',
                           help="hashes of known paths")
    subparser.add_argument('wad',
                           help="WAD file to list")

    subparser = subparsers.add_parser('hashes-guess', parents=[storage_parser],
                                      help="guess hashes from WAD content")
    subparser.add_argument('-n', '--dry-run', action='store_true',
                           help="list new hashes but don't update the hashes file")
    subparser.add_argument('-m', '--methods',
                           help="list of guessing methods to run, comma-separated (default: all except \"basenames\" and \"words\")")
    subparser.add_argument('--list-methods', action='store_true',
                           help="display a list of valid guessing methods and exit")
    subparser.add_argument('wad', nargs='*',
                           help="WAD files or components to analyze")


    # export command

    subparser = subparsers.add_parser('export', parents=[storage_parser],
                                      help="export files to directories, separated by patch")
    subparser.add_argument('-o', '--output', default=default_export,
                           help="directory for files to export (default: %(default)s)")
    subparser.add_argument('-L', '--symlinks', action='store_true',
                           help="create symlinks (if supported by platform)")
    subparser.add_argument('--previous',
                           help="previous patch version to compare with (default: guessed)")
    subparser.add_argument('--full', dest='previous', action='store_const', const='none',
                           help="export the whole patch (don't compare with a previous one)")
    subparser.add_argument('--from', dest='first',
                           help="if a patch is not provided, update all exported patches starting from this one")
    subparser.add_argument('--lazy', action='store_true',
                           help="don't overwrite files, assume they are already correctly extracted")
    subparser.add_argument('patch', nargs='?',
                           help="patch version to export or 'latest', can be omitted to update all exported patches")


    # bin files commands

    subparser = subparsers.add_parser('bin-dump',
                                      help="dump a BIN file as a text tree")
    subparser.add_argument('-j', '--json', action='store_true',
                           help="extract to JSON")
    subparser.add_argument('bin',
                           help="BIN file to extract")


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
        args.storage = parse_storage_args(parser, args)

    globals()[f"command_{args.command.replace('-', '_')}"](parser, args)


if __name__ == "__main__":
    main()
