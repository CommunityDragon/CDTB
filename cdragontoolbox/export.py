#!/usr/bin/env python3
import os
import shutil
import logging
from .downloader import Storage, Version, PatchVersion, BinPackageFile
from .wad import Wad

logger = logging.getLogger("export")


def paths_to_tree(paths):
    """Reduce an iterable of paths into nested mappings

    For leafs, value if set to None.
    There must not be paths empty parts, leading or trailing slashes.

    For instance: ['a/x/1', 'a/2']
    Is reduced to: {'a': {'x': {'1': None}, '2': None}}
    
    """

    tree = {}
    for path in paths:
        *parents, leaf = path.split('/')
        subtree = tree
        for parent in parents:
            subtree = subtree.setdefault(parent, {})
        subtree[leaf] = None
    return tree

def reduce_common_trees(parts, tree1, tree2):
    """Recursive method for reducing paths"""
    if tree1 is None or tree1 == tree2:
        # leaf or common subtree
        yield '/'.join(parts)
        return
    for name in tree1:
        # non-common subtree, compare each subtree
        # tree2[name] must exist, since tree1 must be a subtree of tree2
        yield from reduce_common_trees(parts + [name], tree1[name], tree2[name])

def reduce_common_paths(paths1, paths2):
    """Compare paths lists and return the most common subpaths

    Reduce directories in paths1 that are the same in paths2 so that the
    returned list of paths are common in paths1 and paths2.
    All paths in paths1 must exist in paths2.

    If paths lists are identical, return a list of root's subdirs.
    """

    tree1 = paths_to_tree(paths1)
    tree2 = paths_to_tree(paths2)
    ret = list(reduce_common_trees([], tree1, tree2))
    if len(ret) == 1 and ret[0] == '':
        # trees are identical
        return list(tree1)
    return ret


class Exporter:
    def __init__(self, output: str, patch: PatchVersion, previous_patch: PatchVersion):
        self.storage = patch.storage
        self.output = output
        self.patch = patch
        self.previous_patch = previous_patch
        # list of export path to link from the previous patch, set in export()
        self.previous_links = None

    def export(self):
        """Export files to the output directory, set previous_links

        Files that have changed from the previous patch are copied to the
        output directory.
        Files that didn't changed are added to self.previous_links. It's
        content is reduced so that identical directories result into a single
        link entry.
        """

        logger.info("exporting patch %s based on patch %s", self.patch.version, self.previous_patch.version)

        #self.previous_patch.download(langs=True, latest=True)
        for patch in (self.patch, self.previous_patch):
            #XXX for now, only export files from league_client as lol_game_client is not well known yet
            #patch.download(langs=True, latest=True)
            for sv in patch.solutions(latest=True):
                if sv.solution.name == 'league_client_sln':
                    sv.download(langs=True)

        # iterate on project files, compare files with previous patch
        projects = {pv for sv in self.patch.solutions(latest=True) if sv.solution.name == 'league_client_sln' for pv in sv.projects(True)}
        # match projects with previous projects
        prev_projects = {pv.project.name: pv for sv in self.previous_patch.solutions(latest=True) if sv.solution.name == 'league_client_sln' for pv in sv.projects(True)}

        previous_links = []
        for pv, prev_pv in sorted((pv, prev_projects.get(pv.project.name)) for pv in projects):
            # get export paths from previous package
            prev_extract_paths = {}  # {export_path: extract_path}
            if prev_pv:
                for pf in prev_pv.package_files():
                    path = pf.extract_path()
                    prev_extract_paths[self.to_export_path(path)] = path

            for pf in pv.package_files():
                extract_path = pf.extract_path()
                export_path = self.to_export_path(extract_path)
                prev_extract_path = prev_extract_paths.get(export_path)
                # package files are identical if their extract paths are the same

                if extract_path.endswith('.wad'):
                    # WAD file: link the whole archive or compare file by file using sha256
                    wad = Wad(self.storage.fspath(extract_path))
                    if extract_path == prev_extract_path:
                        logger.debug("unchanged WAD file: %s", extract_path)
                        previous_links += [wf.export_path() for wf in wad.files]
                    else:
                        logger.debug("modified WAD file: %s", extract_path)
                        if prev_extract_path:
                            # compare to the previous WAD based on sha256 hashes
                            prev_wad = Wad(self.storage.fspath(prev_extract_path))
                            prev_sha256 = {wf.path_hash: wf.sha256 for wf in prev_wad.files}
                            wadfiles_to_extract = []
                            for wf in wad.files:
                                export_path = wf.export_path()
                                if wf.sha256 == prev_sha256.get(wf.path_hash):
                                    # same file, add a link
                                    previous_links.append(export_path)
                                else:
                                    wadfiles_to_extract.append(wf)
                            # change the files from the wad so it only extract these
                            wad.files = wadfiles_to_extract
                        logger.info("exporting %d files from %s", len(wad.files), extract_path)
                        #XXX guess extensions() before extract?
                        wad.extract(self.output)

                else:
                    # normal file: link or copy
                    if extract_path == prev_extract_path:
                        logger.debug("unchanged file: %s", extract_path)
                        previous_links.append(export_path)
                    else:
                        logger.debug("modified file: %s", extract_path)
                        self.export_storage_file(extract_path, export_path)

        # get all files from the previous patch to properly reduce the links
        previous_files = []
        for pv in (pv for sv in self.previous_patch.solutions(latest=True) for pv in sv.projects(True)):
            for pf in pv.package_files():
                fspath = pf.fspath()
                if fspath.endswith('.wad'):
                    wad = Wad(fspath)
                    previous_files += [wf.export_path() for wf in wad.files]
                else:
                    previous_files.append(self.to_export_path(pf.extract_path()))

        self.previous_links = reduce_common_paths(previous_links, previous_files)


    def export_storage_file(self, storage_path, export_path):
        logger.info("exporting %s", export_path)
        output_path = os.path.join(self.output, export_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copyfile(self.storage.fspath(storage_path), output_path)

    def write_links(self, path):
        with open(path, 'w') as f:
            for link in sorted(self.previous_links):
                print(link, file=f)

    @staticmethod
    def to_export_path(path):
        """Compute path to which export the file from storage path"""
        # projects/<p_name>/releases/<p_version>/files/<export_path>
        return path.split('/', 5)[5].lower()


def command_export(parser, args):
    storage = Storage(args.storage)

    # retrieve target and previous patch versions
    patch = PatchVersion.version(storage, Version(args.patch))
    if patch is None:
        parser.error("patch not found: %s" % args.patch)
    if args.previous:
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

    exporter = Exporter(args.output, patch, previous_patch)
    exporter.export()
    exporter.write_links(args.output + '.links.txt')


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Gather files to be served for a new patch",
    )

    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="be verbose")

    subparsers = parser.add_subparsers(dest='command', help="command")

    subparser = subparsers.add_parser('export',
                                      help="generate files to export")
    subparser.add_argument('-s', '--storage', default='RADS',
                           help="directory for downloaded files (default: %(default)s)")
    subparser.add_argument('-o', '--output', default='export',
                           help="directory for files to export (default: %(default)s)")
    subparser.add_argument('--previous',
                           help="previous patch version to compare with (default: guessed)")
    subparser.add_argument('patch',
                           help="patch version to export")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        datefmt='%H:%M:%S',
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )
    if args.verbose == 0:
        logger.setLevel(logging.INFO)
        logging.getLogger().setLevel(logging.INFO)
    elif args.verbose == 1:
        logger.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)

    globals()["command_%s" % args.command.replace('-', '_')](parser, args)


if __name__ == "__main__":
    main()
