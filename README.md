# CommunityDragon Toolbox

A toolbox to work with League of Legends game files and export files for CDragon.
It can be used as a library or a command-line tool.

## Dependencies:

```
pip install requests hachoir3
```

## Command-line examples

The CLI interface allows:
 - download game files and list relations between
 - list and extract content of WAD files
 - export game files to be served by CDragon

Here are some examples, use `python3 -m cdragontoolbox -h` for details.

```sh
# download and extract files for the latest patch
python3 -m cdragontoolbox download patch=

# download a solution, don't download language-specific projects
python3 -m cdragontoolbox download --no-lang lol_game_client_sln=0.0.1.196

# list projects used by patch 7.23
python3 -m cdragontoolbox projects patch=7.23

# list patch versions (using already downloaded data)
python3 -m cdragontoolbox versions patch

# list files used by a given project version
python3 -m cdragontoolbox files league_client_fr_fr=0.0.0.80

# extract a WAD file
python3 -m cdragontoolbox wad-extract path/to/assets.wad

# list content of a WAD file
python3 -m cdragontoolbox wad-list path/to/assets.wad

# export files of patch 7.23 into a directory
# (files unchanged from 7.22 files are listed into export.links.txt)
python3 -m cdragontoolbox export -o export 7.23
```

## Components

### Solutions

Solutions are the top-level components downloaded by the patcher. They are
located under the `solutions/` directory.
Currently, two solutions are used: `league_client_sln` for the LCU and
`lol_game_client_sln` for the in-game client.

Each solution version is located under `solutions/{name}/releases/{version}`.

### Projects

Each solution version depends on several projects: a *main* project and
additional projects for each available language. They are located under the
`projects/` directory.
Projects are actually named after the solution, and suffixed by the language
code if any. For instance: `league_client_en_gb`.

Each project version is located under `projects/{name}/releases/{version}`.

When a project is updated, only files that have changed since the previous
version are located under this version directory. Files reused from a previous
version stay in this version directory.
As a result, downloading the latest version of a project actually download
files of previous project versions too.

### Patches

A patch version is the version used publicly by Riot (for instance `7.23`) and
retrieved from downloaded files

Patch version changes independently from solution and project versions.


## WAD files

WADs are archives used by the clients. They contain assets, game data (e.g.
item description), files for the LCU interface and more.

Paths of files in WAD files are hashed, they are not stored in clear in the
archive. A large number of these hashes have been guessed but there are still a
lot of unresolved hashes.

An hash list is provided and regularly updated with new hashes as they are
discovered, especially after client updates.

