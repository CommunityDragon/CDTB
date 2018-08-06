import os
import re
import shutil
import subprocess
import time
import logging
from io import BytesIO
from typing import Optional, List
from PIL import Image

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

    def __init__(self, storage: Storage, output: str, first: Version=None, stored=True):
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
            if first and patch.version < first:
                break
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

        patch_solutions = self.patch.solutions(latest=True)
        for sv in patch_solutions:
            sv.download(langs=True)

        if self.previous_patch:
            prev_patch_solutions = self.previous_patch.solutions(latest=True)
            for sv in prev_patch_solutions:
                sv.download(langs=True)

        # iterate on project files, compare files with previous patch
        projects = {pv for sv in patch_solutions for pv in sv.projects(True)}
        # match projects with previous projects
        if self.previous_patch:
            prev_projects = {pv.project.name: pv for sv in prev_patch_solutions for pv in sv.projects(True)}
        else:
            prev_projects = {}
        #XXX for now, exclude lol_game_client language projects
        projects = {pv for pv in projects if not pv.project.name.startswith('lol_game_client_')}
        prev_projects = {name: pv for name, pv in prev_projects.items() if not name.startswith('lol_game_client_')}

        logger.info("build list of files to extract or link")
        new_symlinks = []
        new_extracts = []
        unknown_hashes = []
        to_extract = []  # StorageFile or Wad instances (with wad.files correctly filled)
        for pv, prev_pv in sorted((pv, prev_projects.get(pv.project.name)) for pv in projects):
            is_game = pv.project.name.startswith('lol_game_client')
            # get export paths from previous package
            prev_extract_paths = {}  # {export_path: extract_path}
            if prev_pv:
                for path in prev_pv.filepaths():
                    prev_extract_paths[self.to_export_path(path)] = path

            for extract_path in pv.filepaths():
                export_path = self.to_export_path(extract_path)
                prev_extract_path = prev_extract_paths.get(export_path)
                # package files with identical extract paths are the same

                if extract_path.endswith('.wad') or extract_path.endswith('.wad.client'):
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
                    # normal file, retrieved directly from storage
                    storage_file = self._storage_file(extract_path, export_path, is_game)
                    if not storage_file:
                        continue
                    if extract_path == prev_extract_path:
                        logger.debug(f"unchanged file: {extract_path}")
                        new_symlinks.append(storage_file.export_path)
                    else:
                        logger.debug(f"modified file: {extract_path}")
                        new_extracts.append(storage_file.export_path)
                        to_extract.append(storage_file)

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
            previous_files = list(self._exported_paths_for_projects(prev_projects.values()))

            # Check for files both extracted and linked, which should only
            # happen for duplicated files. Game files can contain duplicates,
            # so don't fail and ignore symlinks; this will avoid errors later.
            for duplicate in sorted(new_symlinks & new_extracts):
                logger.warning(f"duplicate file: {duplicate}")
                new_symlinks.remove(duplicate)

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
            elif isinstance(elem, StorageFile):
                elem.export(self.output)
            else:
                raise TypeError(f"unexpected element to extract: {elem!r}")


    def _open_wad(self, extract_path: str, unknown: Optional[List]=None) -> Wad:
        """Open a WAD, guess extensions, resolve paths, setup conversions.

        If unknown is set, unknown hashes are appended to it.
        """

        wad = Wad(self.storage.fspath(extract_path))
        wad.guess_extensions()
        if unknown is not None:
            unknown += [wf.path_hash for wf in wad.files if not wf.path]

        if extract_path.endswith('.wad.client'):
            # lol_game_client
            wad.set_unknown_paths("unknown")
            new_files = []
            for wf in wad.files:
                # convert some image formats to .png
                if wf.ext in ('dds', 'tga'):
                    wf.save_method = save_image_to_png
                    wf.ext = 'png'
                    wf.path = wf.path[:-3] + 'png'
                # keep only image files
                if wf.ext != 'png':
                    continue
                # export in 'game/' subdirectory
                wf.path = f"game/{wf.path}"
                new_files.append(wf)
            wad.files = new_files
        else:
            # league_client: extract everything, unknown path depends on WAD path
            m = re.search(r'/(plugins/rcp-.+?)/[^/]*assets\.wad$', extract_path, re.I)
            if m is not None:
                # LCU client: plugins/<plugin-name>
                unknown_path = f"{m.group(1).lower()}/unknown"
            else:
                unknown_path = "unknown"
            wad.set_unknown_paths(unknown_path)
        return wad

    def _storage_file(self, extract_path, export_path, is_game):
        """Create a StorageFile instance, return None if the file must be ignored"""

        save_method = None
        if is_game:
            # convert some image formats to .png
            base, ext = os.path.splitext(export_path)
            if ext in ('.dds', '.tga'):
                export_path = base + '.png'
                save_method = save_image_to_png
            elif ext != '.png':
                return None
            # export in 'game/' subdirectory
            export_path = f"game/{export_path}"
        else:
            # ignore description.json files
            # They may also also be in WADs (slightly different
            # though), which may result into files being both extracted
            # and symlinked.
            # Just use WAD ones, even if it leads to not having a
            # description.json at all. These files are not needed
            # anyway.
            if export_path.endswith('/descriptions.json'):
                return None

        storage_file = StorageFile(self.storage, extract_path, export_path)
        storage_file.save_method = save_method
        return storage_file


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

        patch_solutions = self.patch.solutions(latest=True)
        projects = {pv for sv in patch_solutions for pv in sv.projects(True)}
        #XXX for now, exclude lol_game_client language projects
        projects = {pv for pv in projects if not pv.project.name.startswith('lol_game_client_')}
        yield from self._exported_paths_for_projects(sorted(projects))


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

    def _exported_paths_for_projects(self, projects):
        """Generate exported paths for a list of projects"""

        for pv in projects:
            is_game = pv.project.name.startswith('lol_game_client')
            for extract_path in pv.filepaths():
                if extract_path.endswith('.wad') or extract_path.endswith('.wad.client'):
                    wad = self._open_wad(extract_path)
                    yield from (wf.path for wf in wad.files)
                else:
                    export_path = self.to_export_path(extract_path)
                    storage_file = self._storage_file(extract_path, export_path, is_game)
                    if storage_file:
                        yield storage_file.export_path


class StorageFile:
    """Single exported file from storage"""

    def __init__(self, storage, storage_path, export_path):
        self.source_path = storage.fspath(storage_path)
        self.export_path = export_path
        self.save_method = None

    def export(self, output):
        """Export the file, do nothing if it already exists"""

        output_path = os.path.join(output, self.export_path)
        if os.path.lexists(output_path):
            return
        logger.info(f"exporting {self.export_path}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            if self.save_method is None:
                shutil.copyfile(self.source_path, output_path)
            else:
                with open(self.source_path, 'rb') as fin:
                    with open(output_path, 'wb') as fout:
                        self.save_method(fin, fout)
        except Exception as e:
            # remove partially exported file
            try:
                os.remove(output_path)
            except OSError:
                pass
            if isinstance(e, ValueError):
                logger.warning(f"cannot convert file '{self.source_path}': {e}")
            else:
                raise


def save_image_to_png(data_or_file, fout):
    if isinstance(data_or_file, bytes):
        data_or_file = BytesIO(data_or_file)
    try:
        im = Image.open(data_or_file)
        im.save(fout)
    except NotImplementedError:
        raise ValueError("cannot convert image to PNG")

