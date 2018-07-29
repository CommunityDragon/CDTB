import os
import re
import shutil
import subprocess
import time
import logging
from typing import Optional, List

from .storage import Version, Storage, PatchVersion
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


class Exporter:
    """Handle export of multiple patchs in the same directory"""

    def __init__(self, storage: Storage, output: str, stored=True):
        self.output = output

        versions = set()
        for path in os.listdir(output):
            if not os.path.isdir(os.path.join(output, path)):
                continue
            try:
                version = Version(path)
            except (ValueError, TypeError):
                continue
            versions.add(version)

        if not versions:
            raise ValueError("no version directory found")

        patches = []
        for patch in PatchVersion.versions(storage, stored=stored):
            if patch.version in versions:
                patches.append(patch)
                versions.remove(patch.version)
                if not versions:
                    break
        else:
            raise ValueError(f"versions not found: {versions!r}")

        self.exporters = []
        for patch, previous_patch in zip(patches, patches[1:] + [None]):
            patch_output = os.path.join(output, str(patch.version))
            self.exporters.append(PatchExporter(patch_output, patch, previous_patch))

    def update(self):
        """Update all patches of the directory"""

        for exporter in self.exporters:
            exporter.export()
            exporter.write_links()
            exporter.write_unknown()

    def create_symlinks(self):
        """Create symlinks for all patches"""

        # create in reverse order, because of chained symlinks
        for exporter in self.exporters[::-1]:
            exporter.create_symlinks()


class PatchExporter:
    """Handle export of patch files to a directory"""

    def __init__(self, output: str, patch: PatchVersion, previous_patch: Optional[PatchVersion]):
        self.storage = patch.storage
        self.output = os.path.normpath(output)
        self.patch = patch
        self.previous_patch = previous_patch
        # list of export path to link from the previous patch, set in export()
        self.previous_links = None
        # list of all unknown hashes, sorted (including those linked from previous patch)
        self.unknown_hashes = None

    def export(self):
        """Export modified files to the output directory

        Set previous_links and unknown_hashes.

        Files that have changed from the previous patch are copied to the
        output directory.
        Files that didn't changed are added to self.previous_links. It's
        content is reduced so that identical directories result into a single
        link entry.
        """

        if self.previous_patch:
            logger.info(f"exporting patch {self.patch.version} based on patch {self.previous_patch.version}")
        else:
            logger.info(f"exporting patch {self.patch.version} based on (full)")

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

        logger.info("build list of files to extract or link")
        new_symlinks = []
        new_extracts = []
        unknown_hashes = []
        to_extract = []  # (extract, export) or Wad instances with wad.files correctly filled
        for pv, prev_pv in sorted((pv, prev_projects.get(pv.project.name)) for pv in projects):
            # get export paths from previous package
            prev_extract_paths = {}  # {export_path: extract_path}
            if prev_pv:
                for path in prev_pv.filepaths():
                    prev_extract_paths[self.to_export_path(path)] = path

            for extract_path in pv.filepaths():
                export_path = self.to_export_path(extract_path)
                prev_extract_path = prev_extract_paths.get(export_path)
                # package files with identical extract paths are the same

                if extract_path.endswith('.wad'):
                    # WAD file: link the whole archive or compare file by file using sha256
                    wad = self._open_wad(extract_path, unknown_hashes)

                    if extract_path == prev_extract_path:
                        logger.debug(f"unchanged WAD file: {extract_path}")
                        new_symlinks += [wf.path for wf in wad.files]
                    else:
                        logger.debug(f"modified WAD file: {extract_path}")
                        if prev_extract_path:
                            # compare to the previous WAD based on sha256 hashes
                            # note: no need to use _open_wad(), file paths are not used
                            prev_wad = Wad(self.storage.fspath(prev_extract_path), hashes={})
                            prev_sha256 = {wf.path_hash: wf.sha256 for wf in prev_wad.files}
                            wadfiles_to_extract = []
                            for wf in wad.files:
                                if wf.sha256 == prev_sha256.get(wf.path_hash):
                                    # same file, add a link
                                    new_symlinks.append(wf.path)
                                else:
                                    wadfiles_to_extract.append(wf)
                            # change the files from the wad so it only extract these
                            wad.files = wadfiles_to_extract
                        new_extracts += [wf.path for wf in wad.files]
                        to_extract.append(wad)
                else:
                    # ignore description.json files
                    # They may also also be in WADs (slightly different
                    # though), which may result into files being both extracted
                    # and symlinked.
                    # Just use WAD ones, even if it leads to not having a
                    # description.json at all. These files are not needed
                    # anyway.
                    if extract_path.endswith("/description.json"):
                        continue

                    # normal file: link or copy
                    if extract_path == prev_extract_path:
                        logger.debug(f"unchanged file: {extract_path}")
                        new_symlinks.append(export_path)
                    else:
                        logger.debug(f"modified file: {extract_path}")
                        new_extracts.append(export_path)
                        to_extract.append((extract_path, export_path))

        # convert to sets now (we will need it later)
        new_extracts = set(new_extracts)
        new_symlinks = set(new_symlinks)

        # set unknown_hashes
        # filter duplicates, even if there should be none
        self.unknown_hashes = sorted(set(unknown_hashes))

        # get stored files, to remove superfluous ones
        old_extracts = set()
        old_symlinks = set()
        for path in self.exported_files():
            full_path = os.path.join(self.output, path)
            if os.path.islink(full_path):
                old_symlinks.add(path)
            elif os.path.isfile(full_path):
                old_extracts.add(path)
            else:
                raise ValueError(f"unexpected directory: {full_path}")

        # build the reduced list of new symlinks (self.previous_links)
        if self.previous_patch:
            previous_files = []
            for pv in prev_projects.values():
                for path in pv.filepaths():
                    if path.endswith('.wad'):
                        wad = self._open_wad(path)
                        previous_files += [wf.path for wf in wad.files]
                    else:
                        previous_files.append(self.to_export_path(path))

            # check for files both extracted and linked
            # should not happen except in case of duplicated file
            duplicates = new_symlinks & new_extracts
            if duplicates:
                raise RuntimeError(f"duplicate files: {duplicates!r}")

            self.previous_links = reduce_common_paths(new_symlinks, previous_files, new_extracts)
        else:
            assert not new_symlinks
            self.previous_links = None

        # remove extra files and their parent directories (if empty)
        # note: symlinks are assumed to point to the right location
        dirs_to_remove = set()
        for path in list(old_extracts - new_extracts) + list(old_symlinks - set(self.previous_links or [])):
            logger.info(f"remove extra file or symlink: {path}")
            full_path = os.path.join(self.output, path)
            os.remove(full_path)
            dirs_to_remove.add(os.path.dirname(full_path))
        for path in dirs_to_remove:
            try:
                os.removedirs(path)
            except OSError:
                pass

        # extract files, finally
        for elem in to_extract:
            if isinstance(elem, Wad):
                elem.extract(self.output, overwrite=False)
            else:
                self.export_storage_file(*elem)


    def _open_wad(self, extract_path: str, unknown: Optional[List]=None) -> Wad:
        """Open a WAD, guess extensions and resolve paths

        If unknown is set, unknown hashes are appended to it.
        """

        wad = Wad(self.storage.fspath(extract_path))
        wad.guess_extensions()
        if unknown is not None:
            unknown += [wf.path_hash for wf in wad.files if not wf.path]
        # set directory for unknown paths depending on WAD path
        m = re.search(r'/(plugins/rcp-.+?)/[^/]*assets\.wad$', extract_path, re.I)
        unknown_path = "unknown"
        if m is not None:
            # LCU client: plugins/<plugin-name>
            unknown_path = f"{m.group(1).lower()}/unknown"
        wad.set_unknown_paths(unknown_path)
        return wad

    def export_storage_file(self, storage_path, export_path):
        output_path = os.path.join(self.output, export_path)
        if os.path.lexists(output_path):
            return
        logger.info(f"exporting {export_path}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copyfile(self.storage.fspath(storage_path), output_path)

    def exported_files(self):
        """Generate a list of files on disk (even if not if patch files)

        Generate paths with forward slashes on all platforms.
        """
        # os.walk() handles symlinked directories as directories
        # due to this, it's simpler (and faster) to recurse ourselves
        if not os.path.exists(self.output):
            return
        to_visit = ['']
        while to_visit:
            base = to_visit.pop()
            with os.scandir(f"{self.output}/{base}") as scan_it:
                for entry in scan_it:
                    if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                        yield f"{base}{entry.name}"
                    elif entry.is_dir():
                        to_visit.append(f"{base}{entry.name}/")

    def all_exported_paths(self):
        """Generate a list of all files exported by a full export"""

        patch_solutions = [sv for sv in self.patch.solutions(latest=True) if sv.solution.name == 'league_client_sln']
        for pv in sorted(pv for sv in patch_solutions for pv in sv.projects(True)):
            for extract_path in pv.filepaths():
                export_path = self.to_export_path(extract_path)
                if extract_path.endswith('.wad'):
                    wad = self._open_wad(extract_path)
                    yield from (wf.path for wf in wad.files)
                else:
                    yield export_path


    def write_links(self, path=None):
        if self.previous_links is None:
            return
        if path is None:
            path = self.output + ".links.txt"
        with open(path, 'w', newline='\n') as f:
            for link in sorted(self.previous_links):
                print(link, file=f)

    def write_unknown(self, path=None):
        if self.unknown_hashes is None:
            return
        if path is None:
            path = self.output + ".unknown.txt"
        with open(path, 'w', newline='\n') as f:
            for h in self.unknown_hashes:
                print(f"{h:016x}", file=f)

    def create_symlinks(self):
        if self.previous_links is None:
            return
        dst_output = self.output
        src_output = os.path.join(os.path.dirname(self.output), str(self.previous_patch.version))

        logger.info(f"creating symlinks for patch {self.patch.version}")
        for link in self.previous_links:
            dst = os.path.join(dst_output, link)
            if os.path.lexists(dst):
                if not os.path.islink(dst):
                    raise RuntimeError(f"symlink target already exists: {dst}")
                continue  # already set
            dst_dir = os.path.dirname(dst)
            os.makedirs(dst_dir, exist_ok=True)
            src = os.path.relpath(os.path.realpath(os.path.join(src_output, link)), dst_dir)
            logger.info(f"create symlink {dst}")
            os.symlink(src, dst)

    @staticmethod
    def to_export_path(path):
        """Compute path to which export the file from storage path"""
        # projects/<p_name>/releases/<p_version>/files/<export_path>
        return path.split('/', 5)[5].lower()

