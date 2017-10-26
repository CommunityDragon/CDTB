"""

First download a file like the one below by going to this link in a browser:

http://l3cdn.riotgames.com/releases/pbe/projects/league_client/releases/0.0.1.59/files/Plugins/rcp-be-lol-game-data/default-assets.wad.compressed

That will download a compressed wad file. Then run this file to extract the contents.


"""


def decompress_wad(wad_filename: str, output_filename: str):
    import zlib

    with open(filename, "rb") as f:
        data = f.read()

    data = zlib.decompress(data)

    with open(output_filename, "wb") as f:
        f.write(data)


def download_wad_file(version_number):
    import wget

    url = 'http://l3cdn.riotgames.com/releases/pbe/projects/league_client/releases/{version}/files/Plugins/rcp-be-lol-game-data/default-assets.wad.compressed'.format(version=version_number)
    print(url)
    wget.download(url)
    return 'default-assets.wad.compressed'


if __name__ == "__main__":
    #import sys
    #filename = sys.argv[1]
    #if filename.endswith(".compressed")
    #    output_filename = filename[:-len(".compressed")]
    #else:
    #    output_filename = sys.argv[2]

    print("Downloading...")
    #filename = download_wad_file('0.0.1.59')
    filename = 'default-assets.wad.compressed'
    output_filename = filename[:-len(".compressed")]

    print("Decompressing...")
    decompress_wad(filename, output_filename)
