# CommunityDragon ToolBox
## A library containing everything to build the files for DragonBuilder

---

## Correlator
#### Description
Correlates Launcher Client patches with Game Client patches

#### Dependencies:
pip install hachoir3

#### Example
```python
from correlator import Correlator

c = Correlator()

c.convert()  # gets all correlations
c.convert(['0.0.0.101', '0.0.0.30']) # gets specific correlations
```

---

## Downloader

Download, extract and manage game files.

### Dependencies

```sh
pip install requests
```

### Components

#### Solutions

Solutions are the top-level components downloaded by the patcher. They are
located under the `solutions/` directory.
Currently, two solutions are used: `league_client_sln` for the LCU and
`lol_game_client_sln` for the in-game client.

Each solution version is located under `solutions/{name}/releases/{version}`.

#### Projects

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

#### Patches

A patch version is the version used publicly by Riot (for instance `7.23`) and
retrieved from downloaded files

Patch version changes independently from solution and project versions.


### CLI interface

The CLI interface allows to download game files and list relations between
components.
Here are some examples, use `./downloader.py --help` for details:

```python
# download and extract files for the latest patch
./downloader.py download patch=

# download a solution, don't download language-specific projects
./downloader.py download lol_game_client_sln=0.0.1.196

# list projects used by patch 7.23
./downloader.py projects patch=7.23

# list patch versions (using already downloaded data)
./downloader.py versions patch

# list files used by a given project version
./downloader.py files league_client_fr_fr=0.0.0.80
```

