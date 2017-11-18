"""

First download a file like the one below by going to this link in a browser:

http://l3cdn.riotgames.com/releases/pbe/projects/league_client/releases/0.0.1.59/files/Plugins/rcp-be-lol-game-data/default-assets.wad.compressed

That will download a compressed wad file. Then run this file to extract the contents.


"""


def download_most_recent_version():
    from urllib.error import HTTPError
    for i in range(100, 65, -1):  # We know 0.0.1.66 works; try higher numbers
        version_number = "0.0.1.{}".format(i)
        try:
            return download_wad_file(version_number)
        except HTTPError:
            print(f"Version {version_number} does not exist yet.")


def decompress_wad(wad_filename: str, output_filename: str):
    import zlib

    with open(wad_filename, "rb") as f:
        data = f.read()

    data = zlib.decompress(data)

    with open(output_filename, "wb") as f:
        f.write(data)


def download_wad_file(version_number):
    import wget

    url = 'http://l3cdn.riotgames.com/releases/pbe/projects/league_client/releases/{version}/files/Plugins/rcp-be-lol-game-data/default-assets.wad.compressed'.format(version=version_number)
    print(f"Downloading: {url}")
    wget.download(url)
    return 'default-assets.wad.compressed'


if __name__ == "__main__":
    #filename = download_most_recent_version()
    filename = 'default-assets.wad.compressed'

    if filename.endswith(".compressed"):
        output_filename = filename[:-len(".compressed")]
        print("Decompressing...")
        decompress_wad(filename, output_filename)
