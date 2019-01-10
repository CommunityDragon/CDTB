import os
import errno
import json
import re
import shutil
import logging
from io import BytesIO
from PIL import Image

from .storage import Version, Storage, PatchVersion
from .wad import Wad
from .binfile import BinFile
from .tools import write_file_or_remove

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
    """Export files and WADs to a directory"""

    def __init__(self, output: str, storage: Storage):
        self.output = os.path.normpath(output)
        self.storage = storage
        self.wads = {}  # {export_path: Wad}
        self.plain_files = {}  # {export_path: storage_path}
        self.converters = []


    def exported_paths(self):
        """Generate paths of extracted files"""
        yield from self.plain_files
        for wad in self.wads.values():
            yield from (wf.path for wf in wad.files)

    def unknown_hashes(self):
        """Yield all unknown hashes from WAD files"""
        for wad in self.wads.values():
            yield from (wf.path_hash for wf in wad.files if not wf.path)

    def converted_exported_paths(self):
        """Generate paths of extracted files after conversion"""
        yield from (self._get_converter(path)[0] for path in self.exported_paths())

    def walk_output_dir(self):
        """Generate a list of files on disk (even if not in exported files)

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


    def add_storage_path(self, path):
        """Add a path from it's storage path"""

        if path.endswith('.wad') or path.endswith('.wad.client'):
            wad = Wad(self.storage.fspath(path))
            # remove file redirections
            wad.files = [wf for wf in wad.files if wf.type != 2]
            wad.guess_extensions()
            self.wads[self._export_path(path)] = wad
        else:
            self.plain_files[self._export_path(path)] = path

    def add_patch_files(self, patch):
        """Add files to export from a patch"""

        logger.info(f"add list of files to extract for patch {patch.version}")
        projects = self._patch_to_projects(patch)

        # add files to export
        for pv in projects:
            for path in pv.filepaths():
                self.add_storage_path(path)

    def filter_storage_path(self, path):
        """Remove files that are in the provided storage path

        WAD files are first compared by path, then by file's sha256.
        Plain files are simply removed.
        """

        if path in self.plain_files:
            del self.plain_files[path]
        elif path.endswith('.wad') or path.endswith('.wad.client'):
            export_path = self._export_path(path)
            self_wad = self.wads.get(export_path)
            if self_wad is None:
                return  # not exported
            if self_wad.path == path:
                # same path: WADs are identical
                logger.debug(f"filter identical WAD file: {path}")
                del self.wads[export_path]
            else:
                # compare the sha256 hashes to find the common files
                # don't resolve hashes: we just need the sha256
                logger.debug(f"filter modified WAD file: {path}")
                other_wad = Wad(self.storage.fspath(path), hashes={})
                other_sha256 = {wf.path_hash: wf.sha256 for wf in other_wad.files}
                # change the files from the wad so it only extract these
                self_wad.files = [wf for wf in self_wad.files if wf.sha256 != other_sha256.get(wf.path_hash)]
                if not self_wad.files:
                    del self.wads[export_path]

    def filter_export_paths(self, predicate):
        """Filter paths to export using a predicate

        Unknown files are filtered out if None is filtered out.
        """

        self.plain_files = {k: v for k, v in self.plain_files.items() if predicate(k)}
        emptied = []
        for path, wad in self.wads.items():
            wad.files = [wf for wf in wad.files if predicate(wf.path)]
            if not wad.files:
                emptied.append(path)
        for path in emptied:
            del self.wads[path]

    def filter_exporter(self, other):
        """Remove files that are exported by another exporter"""

        for path, other_storage_path in other.plain_files.items():
            if self.plain_files.get(path) == other_storage_path:
                # same storage path: files are identical
                logger.debug(f"filter identical plain file: {path}")
                del self.plain_files[path]

        for path, other_wad in other.wads.items():
            self_wad = self.wads.get(path)
            if self_wad is None:
                continue  # not exported
            if self_wad.path == other_wad.path:
                # same path: WADs are identical
                logger.debug(f"filter identical WAD file: {path}")
                del self.wads[path]
            else:
                # compare the sha256 hashes to find the common files
                # don't resolve hashes: we just need the sha256
                logger.debug(f"filter modified WAD file: {path}")
                other_sha256 = {wf.path_hash: wf.sha256 for wf in other_wad.files}
                # change the files from the wad so it only extract these
                self_wad.files = [wf for wf in self_wad.files if wf.sha256 != other_sha256.get(wf.path_hash)]
                if not self_wad.files:
                    del self.wads[path]

    def export(self, overwrite=True):
        """Export files to the output

        If overwrite is False, don't extract files that already exist on disk.
        """

        logger.info(f"export plain files ({len(self.plain_files)})")
        for export_path, storage_path in self.plain_files.items():
            self._export_plain_file(export_path, storage_path, overwrite)

        for wad in self.wads.values():
            self._export_wad(wad, overwrite)

    def clean_output_dir(self, kept_files, kept_symlinks):
        """Remove regular files/symlinks from output, except given ones

        This method is intended to be used to clean-up files that should not be
        extracted/symlinked. Parent directories are removed (if empty).
        Note: symlinks are assumed to point to the right location.
        """

        # collect files to remove
        to_remove = []
        for path in self.walk_output_dir():
            full_path = os.path.join(self.output, path)
            if os.path.islink(full_path):
                if path in kept_symlinks:
                    continue
            elif os.path.isfile(full_path):
                if path in kept_files:
                    continue
            else:
                raise ValueError(f"unexpected directory: {full_path}")
            to_remove.append(full_path)

        dirs_to_remove = set()
        for path in to_remove:
            logger.info(f"remove extra file or symlink: {path}")
            os.remove(path)
            dirs_to_remove.add(os.path.dirname(path))
        for path in dirs_to_remove:
            try:
                os.removedirs(path)
            except OSError:
                pass


    def _get_converter(self, path):
        """Get converter for given path
        Return (converted_path, converter) or (path, None).
        """
        for converter in self.converters:
            converted_path = converter.handle_path(path)
            if converted_path is not None:
                return (converted_path, converter)
        return (path, None)

    def _export_plain_file(self, export_path, storage_path, overwrite=True):
        """Export a plain file"""

        converted_path, converter = self._get_converter(export_path)

        output_path = os.path.join(self.output, converted_path)
        if not overwrite and os.path.lexists(output_path):
            return

        source_path = self.storage.fspath(storage_path)
        try:
            with open(source_path, 'rb') as fin:
                with write_file_or_remove(output_path) as fout:
                    if converter is None:
                        shutil.copyfileobj(fin, fout)
                    else:
                        converter.convert_to_file(fin, fout)
        except FileConversionError as e:
            logger.warning(f"cannot convert file '{source_path}': {e}")

    def _export_wad(self, wad, overwrite=True):
        logger.info(f"export {wad.path} ({len(wad.files)})")
        # similar to Wad.extract()
        # unknown files are skipped
        with open(wad.path, 'rb') as fwad:
            for wadfile in wad.files:
                if wadfile.path is None:
                    continue
                converted_path, converter = self._get_converter(wadfile.path)
                output_path = os.path.join(self.output, converted_path)
                if not overwrite and os.path.lexists(output_path):
                    continue

                data = wadfile.read_data(fwad)
                if data is None:
                    continue  # should not happen, file redirections have been filtered already

                try:
                    with write_file_or_remove(output_path) as fout:
                        if converter is None:
                            fout.write(data)
                        else:
                            converter.convert_to_file(BytesIO(data), fout)
                except FileConversionError as e:
                    logger.warning(f"cannot convert file '{wadfile.path}': {e}")
                except OSError as e:
                    # Windows does not support path components longer than 255
                    # ignore such files
                    if e.errno == errno.EINVAL:
                        logger.warning(f"ignore file with invalid path: {wad.path}")
                    else:
                        raise

    @staticmethod
    def _export_path(path):
        """Compute path to which export the file from storage path"""
        # projects/<p_name>/releases/<p_version>/files/<export_path>
        return path.split('/', 5)[5].lower()

    @staticmethod
    def _patch_to_projects(patch):
        """Download a path, return a list of projects to export from a patch"""

        solutions = patch.solutions(latest=True)
        for sv in solutions:
            sv.download(langs=True)
        projects = [pv for sv in solutions for pv in sv.projects(True)]
        #XXX for now, exclude lol_game_client language projects
        projects = [pv for pv in projects if not pv.project.name.startswith('lol_game_client_')]

        return projects


class CdragonRawPatchExporter:
    """Export a single patch, as on raw.communitydragon.org

    Handle symlinking of previous patch files, write list of unknown hashes,
    convert files, etc.
    """

    def __init__(self, output, patch, prev_patch=None, symlinks=None):
        self.output = os.path.normpath(output)
        self.storage = patch.storage
        self.patch = patch
        self.prev_patch = prev_patch
        if symlinks is None:
            if os.name == 'nt' or not hasattr(os, 'symlink'):
                self.create_symlinks = False
            else:
                self.create_symlinks = prev_patch is not None
        else:
            if symlinks and not prev_patch:
                raise ValueError("cannot create symlinks without a previous patch")
            self.create_symlinks = symlinks

    def process(self, overwrite=True):
        exporter = self._create_exporter(self.patch)

        # collect unknown hashes before resolving and filtering anything
        unknown_hashes = sorted(exporter.unknown_hashes())

        logger.info(f"filter and transform exported files for patch {self.patch.version}")
        self._transform_exported_files(exporter)

        if self.prev_patch:
            prev_exporter = self._create_exporter(self.prev_patch)
            self._transform_exported_files(prev_exporter)

        # collect list of paths to extract (new ones, previous ones)
        new_paths = set(exporter.converted_exported_paths())
        symlinked_paths = None
        changed_paths = new_paths  # default: use all new paths
        if self.prev_patch:
            prev_paths = set(prev_exporter.converted_exported_paths())
            # filter out files from previous patch
            exporter.filter_exporter(prev_exporter)
            # collect a list of new paths to actually extract (changed ones)
            if self.create_symlinks:
                changed_paths = set(exporter.converted_exported_paths())
                # build a list of symlinks
                # note: Game files contain some duplicates which will appear in several WAD files.
                # A new version of any duplicate will override any unmodified one.
                symlinked_paths = reduce_common_paths(new_paths - changed_paths, prev_paths, changed_paths)

        exporter.clean_output_dir(changed_paths, set(symlinked_paths or []))

        # extract files, create symlinks if needed
        exporter.export(overwrite=overwrite)
        if symlinked_paths:
            self._create_symlinks(symlinked_paths)

        # write additional txt files
        if symlinked_paths:
            with open(self.output + ".links.txt", 'w', newline='\n') as f:
                for link in sorted(symlinked_paths):
                    print(link, file=f)

        with open(self.output + ".unknown.txt", 'w', newline='\n') as f:
            for h in unknown_hashes:
                print(f"{h:016x}", file=f)

        with open(self.output + ".filelist.txt", 'w', newline='\n') as f:
            for path in sorted(new_paths):
                print(path, file=f)


    def _create_exporter(self, patch):
        exporter = Exporter(self.output, patch.storage)
        exporter.converters = [
            ImageConverter(('.dds', '.tga')),
            BinConverter(re.compile(r'^game/data/characters/[^/.]*/(?:skins/)?[^/.]*\.bin$')),
        ]
        exporter.add_patch_files(patch)
        return exporter

    @staticmethod
    def _transform_exported_files(exporter):
        """Filter exported files, resolve unknowns, etc."""

        # resolve unknowns paths
        for path, wad in exporter.wads.items():
            unknown_path = "unknown"
            # league_client: extract unknown files under plugin directory
            m = re.search(r'^(plugins/rcp-.+?)/[^/]*assets\.wad$', path, re.I)
            if m is not None:
                unknown_path = f"{m.group(1).lower()}/unknown"
            wad.set_unknown_paths(unknown_path)

        # don't export executables
        exporter.filter_export_paths(lambda p: p and not p.endswith('.exe') and not p.endswith('.dll'))

        # Remove 'description.json' files from plain files.
        # They may also also be in WADs (slightly different though), which may
        # result into files being both extracted and symlinked.
        # Just use WAD ones, even if it leads to not having a description.json
        # at all. These files are not needed anyway.
        exporter.plain_files = {k: v for k, v in exporter.plain_files.items() if not k.endswith('/description.json')}

        # game WADs:
        # - keep only images and champion 'bin' files
        # - add 'game/' prefix to export path
        re_game_paths = re.compile(r'(?:\.dds|\.tga|^data/characters/[^/.]*/(?:skins/)?[^/.]*\.bin)$')
        for path, wad in exporter.wads.items():
            if path.endswith('.wad.client'):
                wad.files = [wf for wf in wad.files if re_game_paths.search(wf.path)]
                for wf in wad.files:
                    wf.path = f"game/{wf.path}"
        # remove emptied WADs
        for path, wad in list(exporter.wads.items()):
            if not wad.files:
                del exporter.wads[path]


    def _create_symlinks(self, symlinks):
        if not symlinks:
            return
        dst_output = self.output
        src_output = os.path.join(os.path.dirname(self.output), str(self.prev_patch.version))

        logger.info(f"creating symlinks for patch {self.patch.version}")
        for link in symlinks:
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

    @classmethod
    def from_directory(cls, storage, output: str, first: Version=None, symlinks=None):
        """Handle export of multiple patchs in the same directory

        Exporter for the most oldest patch is returned first.
        """

        #XXX If directories of intermediate patches don't exist, they will
        # be fully extracted. This should be checked.

        # collect all version subdirectories
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

        # get patches from versions (latest to oldest)
        patches = []
        for patch in PatchVersion.versions(storage, stored=True):
            if first and patch.version < first:
                break
            if patch.version in versions:
                patches.append(patch)
                versions.remove(patch.version)
                if not versions:
                    break
        else:
            raise ValueError(f"versions not found: {versions!r}")

        # create patch exporters (latest to oldest)
        exporters = []
        for patch, previous_patch in zip(patches, patches[1:] + [None]):
            patch_output = os.path.join(output, str(patch.version))
            exporters.append(cls(patch_output, patch, previous_patch, symlinks=symlinks if previous_patch else False))
        return exporters[::-1]


class FileConverter:
    """Base class for file conversions"""

    def handle_path(self, path):
        """Return the path of the converted path or None if not handled"""
        raise NotImplementedError()

    def convert_to_file(self, fin, fout):
        """Convert file object content and save it to given file object"""
        raise NotImplementedError()

class FileConversionError(RuntimeError):
    pass

class ImageConverter(FileConverter):
    def __init__(self, extensions):
        self.extensions = extensions

    def handle_path(self, path):
        base, ext = os.path.splitext(path)
        if ext in self.extensions:
            return base + '.png'
        return None

    def convert_to_file(self, fin, fout):
        try:
            im = Image.open(fin)
            im.save(fout)
        except (OSError, NotImplementedError):
            # "OSError: cannot identify image file" happen for some files with a wrong extension
            raise FileConversionError("cannot convert image to PNG")

class BinConverter(FileConverter):
    def __init__(self, regex):
        self.regex = regex

    def handle_path(self, path):
        if self.regex.match(path):
            return path + '.json'
        return None

    def convert_to_file(self, fin, fout):
        binfile = BinFile(fin)
        fout.write(json.dumps(binfile.to_serializable()).encode('ascii'))

