from typing import List
import json
import requests
import zlib
import glob
import re
import os
import hachoir.parser, hachoir.metadata


def get_all_client_versions():
    url = 'http://l3cdn.riotgames.com/releases/live/projects/league_client/releases/releaselisting'
    versions = requests.get(url).text
    versions = versions.strip().split()
    return versions


def download_LoL_exe(client_version, output_directory='.cache'):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    client_filename = 'LeagueClient{version}.exe'.format(version=client_version)
    full_path = os.path.join(output_directory, client_filename)
    if not os.path.exists(full_path):
        url = 'http://l3cdn.riotgames.com/releases/live/projects/league_client/releases/{}/files/LeagueClient.exe.compressed'.format(client_version)
        client = requests.get(url, stream=True).raw.read()
        client = zlib.decompress(client)
        with open(full_path, 'wb') as f:
            f.write(client)
    return full_path


def extract_client_version(client_path):
    parser = hachoir.parser.createParser(client_path)
    metadata = hachoir.metadata.extractMetadata(parser=parser)
    metadata = metadata.exportPlaintext()
    version = None
    for md in metadata:
        if 'Version' in md:
            version = md
            break
    m = re.search('([\d\.]+)', version)
    version = m.group(0)
    return version


def get_version_correlation(version: str, caching_direc, logger: bool):
    print(f'Downloading and correlating version {version}...')
    try:
        client_path = download_LoL_exe(version, output_directory=caching_direc)
        client_version = extract_client_version(client_path)
        return client_version
    except Exception as error:
        if logger:
            print(error)
