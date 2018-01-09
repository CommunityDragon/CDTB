import os
import shutil
import logging
from typing import Optional, Generator
from .storage import PatchVersion
from .wad import Wad

logger = logging.getLogger(__name__)


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

def reduce_common_trees(parts, tree1, tree2, excludes):
    """Recursive method for reducing paths"""
    if tree1 is None or (tree1 == tree2 and excludes is None):
        # leaf or common, non-excluded subtree
        yield '/'.join(parts)
        return
    for name in tree1:
        # non-common subtree, compare each subtree
        # tree2[name] must exist, since tree1 must be a subtree of tree2
        yield from reduce_common_trees(parts + [name], tree1[name], tree2[name], None if excludes is None else excludes.get(name))

def reduce_common_paths(paths1, paths2, excludes):
    """Compare paths lists and return the most common subpaths

    Reduce directories in paths1 that are the same in paths2 so that the
    returned list of paths are common in paths1 and paths2.
    All paths in paths1 must exist in paths2.

    If paths lists are identical, return a list of root's subdirs.
    """

    tree1 = paths_to_tree(paths1)
    tree2 = paths_to_tree(paths2)
    tree_excludes = paths_to_tree(excludes)
    ret = list(reduce_common_trees([], tree1, tree2, tree_excludes))
    if len(ret) == 1 and ret[0] == '':
        # trees are identical
        return list(tree1)
    return ret


class PatchExporter:
    """Handle export of patch files to a directory"""

    def __init__(self, output: str, patch: PatchVersion, previous_patch: Optional[PatchVersion]):
        self.storage = patch.storage
        self.output = os.path.normpath(output)
        self.patch = patch
        self.previous_patch = previous_patch
        # list of export path to link from the previous patch, set in export()
        self.previous_links = None

    def export(self, overwrite=True):
        """Export modified files to the output directory, set previous_links

        Files that have changed from the previous patch are copied to the
        output directory.
        Files that didn't changed are added to self.previous_links. It's
        content is reduced so that identical directories result into a single
        link entry.
        """

        if self.previous_patch:
            logger.info("exporting patch %s based on patch %s", self.patch.version, self.previous_patch.version)
        else:
            logger.info("exporting patch %s based on (full)", self.patch.version)

        #XXX for now, only export files from league_client as lol_game_client is not well known yet
        patch_solutions = [sv for sv in self.patch.solutions(latest=True) if sv.solution.name == 'league_client_sln']
        for sv in patch_solutions:
            sv.download(langs=True)

        if self.previous_patch:
            prev_patch_solutions = [sv for sv in self.previous_patch.solutions(latest=True) if sv.solution.name == 'league_client_sln']
            for sv in prev_patch_solutions:
                sv.download(langs=True)

        # iterate on project files, compare files with previous patch
        projects = {pv for sv in patch_solutions for pv in sv.projects(True)}
        # match projects with previous projects
        if self.previous_patch:
            prev_projects = {pv.project.name: pv for sv in prev_patch_solutions for pv in sv.projects(True)}
        else:
            prev_projects = {}

        # get stored files, to remove superfluous ones
        original_exported_files = set(self.exported_files())

        previous_links = []
        extracted_paths = []
        for pv, prev_pv in sorted((pv, prev_projects.get(pv.project.name)) for pv in projects):
            # get export paths from previous package
            prev_extract_paths = {}  # {export_path: extract_path}
            if prev_pv:
                for path in prev_pv.filepaths():
                    prev_extract_paths[self.to_export_path(path)] = path

            for extract_path in pv.filepaths():
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
                        extracted_paths += [wf.export_path() for wf in wad.files]
                        logger.info("exporting %d files from %s", len(wad.files), extract_path)
                        #XXX guess extensions() before extract?
                        wad.extract(self.output, overwrite=overwrite)

                else:
                    # normal file: link or copy
                    if extract_path == prev_extract_path:
                        logger.debug("unchanged file: %s", extract_path)
                        previous_links.append(export_path)
                    else:
                        logger.debug("modified file: %s", extract_path)
                        extracted_paths.append(export_path)
                        self.export_storage_file(extract_path, export_path, overwrite=overwrite)

        # remove extra files
        dirs_to_remove = set()
        for path in original_exported_files - set(extracted_paths):
            logger.info("remove extra file: %s", path)
            full_path = os.path.join(self.output, path)
            os.remove(full_path)
            dirs_to_remove.add(os.path.dirname(full_path))
        for path in dirs_to_remove:
            try:
                os.removedirs(path)
            except OSError:
                pass

        if self.previous_patch:
            # get all files from the previous patch to properly reduce the links
            previous_files = []
            for pv in prev_projects.values():
                for path in pv.filepaths():
                    fspath = self.storage.fspath(path)
                    if fspath.endswith('.wad'):
                        wad = Wad(fspath)
                        previous_files += [wf.export_path() for wf in wad.files]
                    else:
                        previous_files.append(self.to_export_path(path))

            self.previous_links = reduce_common_paths(previous_links, previous_files, extracted_paths)


    def export_storage_file(self, storage_path, export_path, overwrite=True):
        output_path = os.path.join(self.output, export_path)
        if overwrite and os.path.exists(output_path):
            return
        logger.info("exporting %s", export_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copyfile(self.storage.fspath(storage_path), output_path)

    def exported_files(self) -> Generator[str, None, None]:
        """Generate a list of files on disk (even if not if patch files)

        Generate paths with forward slashes on all platforms.
        """

        sep = os.path.sep
        for root, dirs, files in os.walk(self.output):
            if files:
                base = os.path.relpath(root, self.output)
                if base == '.':
                    base = ''
                else:
                    if sep != '/':
                        base = base.replace(sep, '/')
                    base += '/'
                for name in files:
                    yield f"{base}{name}"

    def write_links(self, path=None):
        if not self.previous_links:
            return
        if path is None:
            path = self.output + '.links.txt'
        with open(path, 'w', newline='\n') as f:
            for link in sorted(self.previous_links):
                print(link, file=f)

    @staticmethod
    def to_export_path(path):
        """Compute path to which export the file from storage path"""
        # projects/<p_name>/releases/<p_version>/files/<export_path>
        return path.split('/', 5)[5].lower()

