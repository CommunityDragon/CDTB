import json
import requests
import zlib
import re
import os
#python 2.7
#import hachoir_parser, hachoir_metadata

#python 3
import hachoir.parser, hachoir.metadata


def get_all_release_versions():
    url = 'http://l3cdn.riotgames.com/releases/live/projects/league_client/releases/releaselisting'
    versions = requests.get(url).text
    versions = versions.strip().split()
    return versions


def download_LoL_exe(release_version):
    client_filename = "LeagueClient{version}.exe".format(version=release_version)
    if not os.path.exists(client_filename):
        url = 'http://l3cdn.riotgames.com/releases/live/projects/league_client/releases/{}/files/LeagueClient.exe.compressed'.format(release_version)
        client = requests.get(url, stream=True).raw.read()
        client = zlib.decompress(client)
        with open(client_filename, "wb") as f:
            f.write(client)
    return client_filename


def extract_client_version(client_path):
    #assert client_path.endswith("LeagueClient.exe")
    parser = hachoir.parser.createParser(client_path, client_path)
    metadata = hachoir.metadata.extractMetadata(parser=parser)
    metadata = metadata.exportPlaintext()
    version = None
    for md in metadata:
        if "Version" in md:
            version = md
            break

    m = re.search('([\d\.]+)', version)
    version = m.group(0)
    return version


def main():
    all_versions = get_all_release_versions()
    print(all_versions)

    version_conversion = {}
    for version in all_versions:
        try:
            print("Downloading and calculating patch for release version {}...".format(version))
            client_filename = download_LoL_exe(version)
            client_filename = unicode(client_filename)
            client_version = extract_client_version(client_filename)

            version_conversion[version] = client_version
        except Exception as error:
            print(error)

    print(version_conversion)

    with open("version_conversion.json", "w") as f:
        json.dump(version_conversion, f, indent=2)


if __name__ == "__main__":
    main()
