import os
import errno
import re
import shutil
import struct
import logging
from io import BytesIO
from PIL import Image

from .storage import PatchVersion
from .wad import Wad
from .binfile import BinFile
from .sknfile import SknFile
from .rstfile import hashfile_rst, RstFile, key_to_hash as key_to_rsthash
from .tools import (
    write_file_or_remove,
    write_dir_or_remove,
    json_dumps
)

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

    def __init__(self, output: str):
        self.output = os.path.normpath(output)
        self.wads = {}  # {export_path: Wad}
        self.plain_files = {}  # {export_path: path}
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
        for path in self.exported_paths():
            converter = self._get_converter(path)
            yield from converter.converted_paths(path)

    def walk_output_dir(self, skip_recurse=None):
        """Generate a list of files on disk (even if not in exported files)

        Don't recurse into directories in `skip_recurse`.
        Generate paths with forward slashes on all platforms.
        """
        # os.walk() handles symlinked directories as directories
        # due to this, it's simpler (and faster) to recurse ourselves
        if not os.path.exists(self.output):
            return
        if skip_recurse is None:
            skip_recurse = []
        to_visit = ['']
        while to_visit:
            base = to_visit.pop()
            with os.scandir(f"{self.output}/{base}") as scan_it:
                for entry in scan_it:
                    if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                        yield f"{base}{entry.name}"
                    elif entry.is_dir():
                        path = f"{base}{entry.name}"
                        if path not in skip_recurse:
                            to_visit.append(f"{path}/")


    def add_path(self, source_path, export_path):
        """Add a path to export

        source_path is the full path to the file to export.
        export_path is the relative export path, it serves as key for
        filtering, etc.
        """

        if source_path.endswith('.wad') or source_path.endswith('.wad.client'):
            wad = Wad(source_path)
            # remove file redirections
            wad.files = [wf for wf in wad.files if wf.type != 2]
            wad.guess_extensions()
            wad.sanitize_paths()
            self.wads[export_path] = wad
        else:
            self.plain_files[export_path] = source_path

    def add_patch_files(self, patch):
        """Add files to export from a patch"""

        logger.info(f"add list of files to extract for patch {patch.version}")

        for elem in patch.latest().elements:
            elem.download(langs=True)

        # add files to export
        for elem in patch.latest().elements:
            for src, dst in elem.paths(langs=True):
                self.add_path(src, dst)

    def filter_path(self, source_path, export_path):
        """Remove files that are in the provided path

        Paths have the same meaning as for add_path().

        WAD files are first compared by source path, then by file's sha256.
        Plain files are simply removed.
        """

        if export_path in self.plain_files:
            del self.plain_files[export_path]
        elif source_path.endswith('.wad') or source_path.endswith('.wad.client'):
            self_wad = self.wads.get(export_path)
            if self_wad is None:
                return  # not exported
            if self_wad.path == source_path:
                # same path: WADs are identical
                logger.debug(f"filter identical WAD file: {source_path}")
                del self.wads[export_path]
            else:
                # compare the sha256 hashes to find the common files
                # don't resolve hashes: we just need the sha256
                logger.debug(f"filter modified WAD file: {source_path}")
                other_wad = Wad(source_path, hashes={})
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
        for export_path, source_path in self.plain_files.items():
            self._export_plain_file(export_path, source_path, overwrite)

        for wad in self.wads.values():
            self._export_wad(wad, overwrite)

    def clean_output_dir(self, kept_files, kept_symlinks):
        """Remove regular files (or directories) and symlinks from output, except given ones

        This method is intended to be used to clean-up files that should not be
        extracted/symlinked. Parent directories are removed (if empty).
        Note: symlinks are assumed to point to the right location.
        """

        # collect files to remove
        # note: empty directories are not removed
        trees_to_remove = []
        files_to_remove = []
        for path in self.walk_output_dir(kept_files):
            full_path = os.path.join(self.output, path)
            if os.path.islink(full_path):
                if path not in kept_symlinks:
                    files_to_remove.append(full_path)
            else:
                if path not in kept_files:
                    if os.path.isdir(full_path):
                        trees_to_remove.append(full_path)
                    else:
                        files_to_remove.append(full_path)

        dirs_to_remove = set()
        for path in files_to_remove:
            logger.info(f"remove extra file or symlink: {path}")
            os.remove(path)
            dirs_to_remove.add(os.path.dirname(path))
        for path in trees_to_remove:
            logger.info(f"remove extra directory: {path}")
            shutil.rmtree(path)
            dirs_to_remove.add(os.path.dirname(path))

        for path in dirs_to_remove:
            try:
                os.removedirs(path)
            except OSError:
                pass


    def _get_converter(self, path):
        """Get converter that handles the given path, or None"""
        for converter in self.converters:
            if converter.is_handled(path):
                return converter
        return CopyConverter.singleton

    def _export_plain_file(self, export_path, source_path, overwrite=True):
        """Export a plain file"""

        converter = self._get_converter(export_path)
        if not overwrite and converter.converted_paths_exist(self.output, export_path):
            return

        try:
            with open(source_path, 'rb') as fin:
                converter.convert(fin, self.output, export_path)
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

                converter = self._get_converter(wadfile.path)
                if not overwrite and converter.converted_paths_exist(self.output, wadfile.path):
                    continue

                data = wad.read_file_data(fwad, wadfile)
                if data is None:
                    continue

                try:
                    converter.convert(BytesIO(data), self.output, wadfile.path)
                except FileConversionError as e:
                    logger.warning(f"cannot convert file '{wadfile.path}': {e}")
                except OSError as e:
                    # Path components longer than 255 are not supported, ignore such files
                    if e.errno in (errno.EINVAL, errno.ENAMETOOLONG):
                        logger.warning(f"ignore file with invalid path: {wad.path}")
                    else:
                        raise


class CdragonRawPatchExporter:
    """Export a single patch, as on raw.communitydragon.org

    Handle symlinking of previous patch files, write list of unknown hashes,
    convert files, etc.
    """

    def __init__(self, output, patch, prev_patch=None, symlinks=None):
        self.output = os.path.normpath(output)
        self.patch = patch
        self.prev_patch = prev_patch
        if symlinks is None:
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

        # exclude generated "cdragon" files
        changed_paths.add("cdragon")
        exporter.clean_output_dir(changed_paths, set(symlinked_paths or []))

        # extract files, create symlinks if needed
        exporter.export(overwrite=overwrite)
        if symlinked_paths:
            self._create_symlinks(symlinked_paths)

        # write additional txt files
        os.makedirs(os.path.join(self.output, "cdragon"), exist_ok=True)

        if symlinked_paths:
            with open(os.path.join(self.output, "cdragon/files.links.txt"), 'w', newline='\n') as f:
                for link in sorted(symlinked_paths):
                    print(link, file=f)

        with open(os.path.join(self.output, "cdragon/files.unknown.txt"), 'w', newline='\n') as f:
            for h in unknown_hashes:
                print(f"{h:016x}", file=f)

        with open(os.path.join(self.output, "cdragon/files.exported.txt"), 'w', newline='\n') as f:
            for path in sorted(new_paths):
                print(path, file=f)

        logger.info("export TFT data files")
        self.export_tft_data()
        logger.info("export Arena data files")
        self.export_arena_data()

    def export_tft_data(self):
        if self.patch.version != 'main' and self.patch.version < PatchVersion('9.14'):
            return  # no supported TFT data before 9.14
        # don't import in module to be able to execute tftdata module
        from .tftdata import TftTransformer
        transformer = TftTransformer(os.path.join(self.output, "game"))
        transformer.export(os.path.join(self.output, "cdragon/tft"), langs=None)

    def export_arena_data(self):
        if self.patch.version != 'main' and self.patch.version < PatchVersion('13.14'):
            return  # no supported Arena data before 13.14
        # don't import in module to be able to execute arenadata module
        from .arenadata import ArenaTransformer
        transformer = ArenaTransformer(os.path.join(self.output, "game"))
        transformer.export(os.path.join(self.output, "cdragon/arena"), langs=None)

    def _create_exporter(self, patch):
        if patch.version == 'main':
            btype_version = 9999  # also use the latest version
        else:
            v0, v1 = patch.version.t
            btype_version = v0 * 100 + v1
        exporter = Exporter(self.output)
        exporter.converters = [
            ImageConverter(('.dds', '.tga')),
            TexConverter(),
            BinConverter(re.compile(r'game/.*\.bin$'), btype_version),
            SknConverter(),
            RstConverter(re.compile(r'game/data/menu/.*\.(txt|stringtable)$'))
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
        # - keep images and skin files
        # - keep .bin files, except 'data/*_skins_*.bin' files
        # - keep .txt files (some contain useful data)
        # - keep font files
        # - add 'game/' prefix to export path
        def filter_path(path):
            _, ext = os.path.splitext(path)
            if ext == '.bin':
                return '_skins_' not in path
            return ext in ('.dds', '.tga', '.tex', '.skn', '.txt', '.stringtable', '.ttf', '.otf')

        for path, wad in exporter.wads.items():
            if path.endswith('.wad.client'):
                wad.files = [wf for wf in wad.files if filter_path(wf.path)]
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
            src = os.path.relpath(os.path.realpath(os.path.join(src_output, link)), os.path.realpath(dst_dir))
            logger.info(f"create symlink {dst}")
            try:
                os.symlink(src, dst)
            except OSError as e:
                # Path components longer than 255 are not supported, ignore such files
                if e.errno in (errno.EINVAL, errno.ENAMETOOLONG):
                    logger.warning(f"ignore symlink with invalid path: {dst}")
                else:
                    raise

    @classmethod
    def from_directory(cls, storage, output: str, first: PatchVersion=None, symlinks=None):
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
                version = PatchVersion(path)
            except (ValueError, TypeError):
                continue
            versions.add(version)

        if not versions:
            return []  # no version directory found

        # get patches from versions (latest to oldest)
        patches = []
        for patch in storage.patches(stored=True):
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
    """Base class for file conversions

    Each single file can be converted to one or multiple files and/or
    directories (as yielded by `converted_paths()`).
    """

    def is_handled(self, path):
        """Return whether the path is handled"""
        raise NotImplementedError()

    def converted_paths(self, path):
        """Generate paths converted from `path`

        `self.handled(path) is True` can be assumed.
        """
        raise NotImplementedError()

    def converted_paths_exist(self, output, path):
        """Return True if all converted paths exist"""
        return all(os.path.lexists(os.path.join(output, p)) for p in self.converted_paths(path))

    def convert(self, fin, output, path):
        """Convert a source file object

        `output` is the root output directory.
        `path` is the relative path of the converted file.

        Implementations should use `write_file_or_remove()` and
        `write_dir_or_remove()` to ensure files are properly removed on error.

        A `FileConversionError` should be raised on conversion error.

        `self.handled(path) is True` can be assumed.
        """
        raise NotImplementedError()


class FileConversionError(RuntimeError):
    pass

class CopyConverter(FileConverter):
    """Converter that copy as-is (no actual conversion)"""

    def is_handled(self, path):
        return True

    def converted_paths(self, path):
        yield path

    def convert(self, fin, output, path):
        output_path = os.path.join(output, path)
        with write_file_or_remove(output_path) as fout:
            shutil.copyfileobj(fin, fout)

# use as a singleton, to avoid multiple instanciations for nothing
CopyConverter.singleton = CopyConverter()

class ImageConverter(FileConverter):
    def __init__(self, extensions):
        self.extensions = extensions

    def is_handled(self, path):
        return os.path.splitext(path)[1] in self.extensions

    def converted_paths(self, path):
        yield os.path.splitext(path)[0] + '.png'

    def convert(self, fin, output, path):
        output_path = os.path.join(output, os.path.splitext(path)[0] + '.png')
        with write_file_or_remove(output_path) as fout:
            try:
                im = Image.open(fin)
                im.save(fout)
            except (OSError, NotImplementedError):
                # "OSError: cannot identify image file" happen for some files with a wrong extension
                raise FileConversionError("cannot convert image to PNG")

class TexConverter(FileConverter):
    def __init__(self):
        pass

    def is_handled(self, path):
        return path.endswith('.tex')

    def converted_paths(self, path):
        yield os.path.splitext(path)[0] + '.png'

    def convert(self, fin, output, path):
        output_path = os.path.join(output, os.path.splitext(path)[0] + '.png')
        fdds = BytesIO(self.tex_to_dds(fin.read()))
        with write_file_or_remove(output_path) as fout:
            try:
                im = Image.open(fdds)
                im.save(fout)
            except (OSError, NotImplementedError):
                raise FileConversionError("cannot convert image to PNG")

    @staticmethod
    def tex_to_dds(data):
        # Parse TEX header
        if len(data) < 12 or data[:4] != b'TEX\0':
            raise FileConversionError("invalid TEX file")
        _, width, height, format, has_mipmaps = struct.unpack('<4sHHxBx?', data[:12])

        if format == 0x0a:  # DXT1
            ddspf = struct.pack('<LL4s20x', 32, 0x4, b'DXT1')
        elif format == 0x0c:  # DXT5
            ddspf = struct.pack('<LL4s20x', 32, 0x4, b'DXT5')
        elif format == 0x14:  # BGRA8
            ddspf = struct.pack('<LL4x5L', 32, 0x41, 8*4, 0x00ff0000, 0x0000ff00, 0x000000ff, 0xff000000)
        else:
            raise FileConversionError(f"unsupported TEX format: {format:x}")

        if has_mipmaps:
            # Note: only convert the largest mipmap

            if format == 0x0a:  # DXT1
                block_size = 4
                bytes_per_block = 8
            elif format == 0x0c:  # DXT5
                block_size = 4
                bytes_per_block = 16
            elif format == 0x14:  # BGRA8
                block_size = 1
                bytes_per_block = 4

            # Find mipmap count
            n = max(width, height)
            mipmap_count = 0
            while n > 0:
                mipmap_count += 1
                n >>= 1

            block_width = (width + block_size - 1) // block_size
            block_height = (height + block_size - 1) // block_size
            mipmap_size = bytes_per_block * block_width * block_height
            pixels = data[-mipmap_size:]
        else:
            pixels = data[12:]

        dds_header = struct.pack('<4s4L56x32sL16x', b'DDS ', 124, 0x1007, height, width, ddspf, 0x1000)
        return dds_header + pixels

class BinConverter(FileConverter):
    def __init__(self, regex, btype_version=None):
        self.regex = regex
        self.btype_version = btype_version

    def is_handled(self, path):
        return self.regex.search(path) is not None

    def converted_paths(self, path):
        yield path
        yield path + '.json'

    def convert(self, fin, output, path):
        output_path = os.path.join(output, path)
        with write_file_or_remove(output_path) as fout:
            shutil.copyfileobj(fin, fout)
        with write_file_or_remove(output_path + '.json') as fout:
            try:
                binfile = BinFile(output_path, btype_version=self.btype_version)
            except ValueError as e:
                raise FileConversionError(f"failed to parse bin file: {e}")
            fout.write(json_dumps(binfile.to_serializable()).encode('ascii'))

class SknConverter(FileConverter):
    def __init__(self):
        pass

    def is_handled(self, path):
        return path.endswith('.skn')

    def converted_paths(self, path):
        yield path
        yield os.path.splitext(path)[0]

    def convert(self, fin, output, path):
        output_path = os.path.join(output, path)
        with write_file_or_remove(output_path) as fout:
            shutil.copyfileobj(fin, fout)
        obj_output_path = os.path.join(output, os.path.splitext(path)[0])
        shutil.rmtree(obj_output_path, ignore_errors=True)
        with write_dir_or_remove(obj_output_path):
            sknfile = SknFile(output_path)
            for entry in sknfile.entries:
                name = os.path.join(obj_output_path, entry["name"] + ".obj")
                with open(name, "w") as f:
                    f.write(sknfile.to_obj(entry))

class RstConverter(FileConverter):
    def __init__(self, regex):
        self.regex = regex
        self.hashes = hashfile_rst.load()

    def is_handled(self, path):
        return self.regex.search(path) is not None

    def converted_paths(self, path):
        yield path
        yield path + '.json'

    def convert(self, fin, output, path):
        output_path = os.path.join(output, path)
        with write_file_or_remove(output_path) as fout:
            shutil.copyfileobj(fin, fout)

        rstfile = RstFile(output_path)
        hashes = {key_to_rsthash(hash, rstfile.hash_bits): value for hash, value in self.hashes.items()}
        rst_json = {"entries": {}, "version": rstfile.version}
        for key, value in rstfile.entries.items():
            if key in hashes:
                key = hashes[key]
            else:
                key = f"{{{key:010x}}}"
            rst_json["entries"][key] = value

        with write_file_or_remove(output_path + '.json', False) as fout:
            fout.write(json_dumps(rst_json, ensure_ascii=False))
