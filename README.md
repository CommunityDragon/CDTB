# CommunityDragon Toolbox

A toolbox to work with League of Legends game files and export files for CDragon.
It can be used as a library or a command-line tool.

## Dependencies

To install dependencies, run:
```
pip install -r requirements.txt
```

**Windows users:** precompiled packages can be found [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/).


## Updating hashes

Most commands require hash lists which are updated frequently and and not bundled with this code.

To download them locally from `raw.communitydragon.org`, run:
```
python3 -m cdragontoolbox fetch-hashes
```

The command will print where they are downloaded.
By default, they will land in `~/.local/share/cdragon` (or `%LOCALAPPDATA%/cdragon` on Windows).
An alternate location can be configured using the `CDRAGONTOOLBOX_HASHES_DIR` or `CDRAGON_DATA` environment variables.

Hashes are versionned in the [Data](https://github.com/CommunityDragon/Data) repository.


## Command-line examples

The CLI interface allows:
 - download game files and list relations between
 - list and extract content of WAD files
 - export game files to be served by CDragon

Here are some examples, use `python3 -m cdragontoolbox -h` for details.

```sh
# download and extract files for the latest patch to the directory `cdn`
# (files from the new patcher will be used)
python3 -m cdragontoolbox -v download -s cdn patch=

# download and extract files from the PBE to the directory `cdn`
python3 -m cdragontoolbox -v download -s cdn --patchline pbe patch=main

# same, but don't download language-specific files
python3 -m cdragontoolbox download -s cdn --no-lang patch=

# list patch versions (using already downloaded data in `cdn/`)
python3 -m cdragontoolbox versions -s cdn patch

# list game files for patch 9.9
python3 -m cdragontoolbox files -s cdn game=9.9

# extract a WAD file
python3 -m cdragontoolbox wad-extract path/to/assets.wad

# list content of a WAD file
python3 -m cdragontoolbox wad-list path/to/assets.wad

# export files from PBE
python3 -m cdragontoolbox export -s cdn --patchline pbe --full main

# export files of patch 7.23 into export/7.23 (deprecated)
python3 -m cdragontoolbox export -o export 7.23
```

## WAD files

WADs are archives used by the clients. They contain assets, game data (e.g.
item description), files for the LCU interface and more.

Paths of files in WAD files are hashed, they are not stored in clear in the
archive. A large number of these hashes have been guessed but there are still a
lot of unresolved hashes.

An hash list is provided and regularly updated with new hashes as they are
discovered, especially after client updates.

