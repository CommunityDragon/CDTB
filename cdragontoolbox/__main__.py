#!/usr/bin/env python3
import os
import sys
import argparse
import textwrap
import fnmatch
import logging
from pathlib import Path
import cdragontoolbox
from cdragontoolbox.storage import (
    Storage,
    Patch,
    PatchVersion,
    parse_storage_component,
    storage_conf_from_path,
)
from cdragontoolbox.patcher import PatcherStorage
from cdragontoolbox.wad import Wad
from cdragontoolbox.export import CdragonRawPatchExporter
from cdragontoolbox.binfile import BinFile
from cdragontoolbox.sknfile import SknFile
from cdragontoolbox.hashes import (
    HashFile,
    LcuHashGuesser,
    GameHashGuesser,
    default_hashfile,
    default_hash_dir,
    update_default_hashfile,
)
from cdragontoolbox.tools import json_dump


def parse_component_arg(parser, storage: Storage, component: str):
    """Wrapper around parse_storage_component() to parse CLI arguments into patch elements"""
    try:
        component = parse_storage_component(storage, component)
    except ValueError:
        parser.error(f"invalid component: {component}")
    if component is None:
        parser.error(f"component not found: {component}")

    if isinstance(component, Patch):
        return list(component.elements)
    else:
        return [component]

def parse_component_args(parser, storage: Storage, components):
    return [e for c in components for e in parse_component_arg(parser, storage, c)]


def parse_storage_args(parser, args) -> Storage:
    """Parse storage-related arguments into a Storage"""

    default_path = os.environ.get('CDRAGONTOOLBOX_STORAGE')

    path = default_path if args.storage is None else args.storage
    if path is None:
        conf = {
            'type': 'patcher',
            'path': 'cdn',
        }
    else:
        conf = storage_conf_from_path(path)
        if conf is None:
            parser.error(f"cannot retrieve storage configuration from '{path}'")
        if args.patchline is not None:
            if conf['type'] == 'patcher':
                conf['patchline'] = args.patchline
            else:
                parser.error("--patchline is only supported for 'patcher' storage")
    return Storage.from_conf(conf)


def command_download(parser, args):
    for component in parse_component_args(parser, args.storage, args.component):
        component.download(langs=args.langs)


def command_files(parser, args):
    for elem in parse_component_arg(parser, args.storage, args.component):
        it = elem.relpaths(langs=args.langs) if args.relative else elem.fspaths(langs=args.langs)
        for path in it:
            print(path)


def command_versions(parser, args):
    for patch in args.storage.patches(stored=args.stored):
        if args.type == 'patch' or args.type in (e.name for e in patch.elements):
            print(patch.version)


def command_fetch_hashes(parser, args):
    if default_hash_dir == Path(__file__).parent:
        if os.name == 'nt':
            user_dir = Path(os.environ.get('LOCALAPPDATA', 'LOCALAPPDATA'))
        else:
            user_dir = Path.home() / ".local/share"
        user_dir = user_dir / 'cdragon'
        parser.error(f"Cannot update hashes bundled with source; create {user_dir} to store them locally")

    print(f"Updating hash files: {default_hash_dir}")
    default_hash_dir.mkdir(parents=True, exist_ok=True)
    hash_files = [
        'hashes.binentries.txt',
        'hashes.binfields.txt',
        'hashes.binhashes.txt',
        'hashes.bintypes.txt',
        'hashes.game.txt',
        'hashes.lcu.txt',
        'hashes.rst.txt',
    ]
    for basename in hash_files:
        update_default_hashfile(basename)


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
        wad.files = [wf for wf in wad.files if any(wf.path is not None and fnmatch.fnmatchcase(wf.path, p) for p in args.pattern)]

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
            component = parse_storage_component(args.storage, path_or_component)
        except ValueError:
            wads.append(Wad(path_or_component))
            continue
        if component is None:
            continue
        if isinstance(component, Patch):
            elements = component.elements
        else:
            elements = [component.elements]
        for elem in elements:
            wads.extend(Wad(p) for p in elem.fspaths() if p.endswith('.wad') or p.endswith('.wad.client'))

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
    overwrite = not args.lazy
    symlinks = bool(args.symlinks)

    if not args.patch:
        # multiple patches (update only)
        if args.previous:
            parser.error("patch version required with --previous or --full")
        if args.first:
            parser.error("--from is required when no patch is provided")
        exporters = CdragonRawPatchExporter.from_directory(storage, args.output, PatchVersion(args.first), symlinks=symlinks)
        for exporter in exporters:
            exporter.process(overwrite=overwrite)
    else:
        if args.first:
            parser.error("--from cannot be used when providing a patch")
        # single patch
        # retrieve target and previous patch versions
        patch = storage.patch(None if args.patch == 'latest' else args.patch)
        if patch is None:
            parser.error(f"patch not found: {args.patch}")
        if args.previous == 'none':
            previous_patch = None
        elif args.previous:
            previous_patch = storage.patch(args.previous, stored=True)
            if previous_patch is None:
                parser.error(f"previous patch not found: {patch.version}")
        else:
            it = storage.patches(stored=True)
            for v in it:
                if v.version == patch.version:
                    previous_patch = next(it)
                    break
            else:
                parser.error("cannot guess previous patch")

        exporter = CdragonRawPatchExporter(os.path.join(args.output, str(patch.version)), patch, previous_patch, symlinks=symlinks)
        exporter.process(overwrite=overwrite)


def command_skn_extract(parser, args):
    if not os.path.isfile(args.skn):
        parser.error(f"SKN file not found: {args.skn}")

    sknfile = SknFile(args.skn)
    if args.output is None:
        args.output = os.path.splitext(args.skn)[0]
    os.makedirs(args.output, exist_ok=True)
    for entry in sknfile.entries:
        name = os.path.join(args.output, entry["name"] + ".obj")
        with open(name, "w") as f:
            f.write(sknfile.to_obj(entry))


def command_bin_dump(parser, args):
    if not os.path.isfile(args.bin):
        parser.error(f"BIN file not found: {args.bin}")

    parsed_version = sum(int(num) * (100 ** i) for i, num in enumerate(reversed(args.patch_version.split('.'))))

    with open(args.bin, 'rb') as f:
        binfile = BinFile(f, btype_version=parsed_version)
    if args.json:
        json_dump(binfile.to_serializable(), sys.stdout)
    else:
        for entry in binfile.entries:
            print(entry)
        if binfile.patch_entries is not None:
            for entry in binfile.patch_entries:
                print(entry)


def create_parser():
    parser = argparse.ArgumentParser('cdragontoolbox',
        description="Toolbox to work with League of Legends game and client files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(f"""
            The following formats are supported for components:

              patch=version    patch with given version
              game=version     game files for patch with given version
              client=version   client files (LCU) for patch with given version

            The following formats are supported for patch version:

              X.Y       patch X.Y (all subpatches)
              X.Y.      latest subpatch for patch X.Y (latest elements)
              <empty>   latest available subpatch

            Hashes directory: {default_hash_dir}

            Environment variables

              CDRAGONTOOLBOX_STORAGE     default `--storage` value
              CDRAGONTOOLBOX_EXPORT      default 'export --output` value
              CDRAGONTOOLBOX_HASHES_DIR  path to directory with hash files
              CDRAGON_DATA               path to `Data` repository, for hash files

        """),
    )

    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="be verbose")

    subparsers = parser.add_subparsers(dest='command', help="command")

    default_export = os.environ.get('CDRAGONTOOLBOX_EXPORT', 'export')

    # storage arguments
    storage_parser = argparse.ArgumentParser(add_help=False)
    storage_parser.add_argument('-s', '--storage', default=None,
                                help="path to downloaded files, with an optional storage type prefix (`type:path`)")
    storage_parser.add_argument('--patchline', choices=["pbe", "live"], default=None,
                                help="select a patchline")

    # component-based commands

    component_parser = argparse.ArgumentParser(add_help=False, parents=[storage_parser])
    component_parser.add_argument('--no-lang', dest='langs', action='store_false', default=True,
                                  help="ignore language projects from solutions")
    component_parser.add_argument('--lang', dest='langs', nargs='*',
                                  help="use projects from solutions in given languages (default: all)")

    subparser = subparsers.add_parser('download', parents=[component_parser],
                                      help="download components to the storage")
    subparser.add_argument('component', nargs='+',
                           help="components to download")

    subparser = subparsers.add_parser('files', parents=[component_parser],
                                      help="list files of a component")
    subparser.add_argument('-r', '--relative', action='store_true',
                           help="print relative export path insted of filesystem path")
    subparser.add_argument('component',
                           help="project version, solution version or patch version")

    subparser = subparsers.add_parser('versions', parents=[storage_parser],
                                      help="list available patch versions for a component")
    subparser.add_argument('-a', '--all', dest='stored', action='store_false', default=True,
                           help="when listing patch versions, don't use only stored solutions")
    subparser.add_argument('type', choices={'patch', 'game', 'client'},
                           help="display versions of given component type")


    # Tooling and maintenance

    subparser = subparsers.add_parser('fetch-hashes',
                                      help="download up-to-date hash lists")


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
    subparser.add_argument('-V', '--patch-version', default="10.8",
                           help="patch version this BIN file belongs to (default: %(default)s)")
    subparser.add_argument('bin',
                           help="BIN file to extract")

    # skn files commands

    subparser = subparsers.add_parser('skn-extract',
                                      help="extract an SKN file to a directory")
    subparser.add_argument('-o', '--output',
                           help="output directory")
    subparser.add_argument('skn',
                           help="SKN file to extract")

    return parser


def main(argv = None):
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

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
