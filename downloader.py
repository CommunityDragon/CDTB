"""
Downloads the package manifest for the current version of the lol client and extracts files from it.

Note: `packman` in this code stands for `package manifest`.
"""

import os

import shutil
import requests
import zlib


# globals

LOLPATCHSERVER = "http://l3cdn.riotgames.com/"


def sort_packman(packman):
    """
    Returns a sorted list of what files are from what BIN (showed below).
    [
        ["BIN_0x0000002d",
            [
                [ItemPath,ItemOffset,ItemLength,Type],
                [ItemPath,ItemOffset,ItemLength,Type],
                [ItemPath,ItemOffset,ItemLength,Type]...

            ]
        ],
        ["BIN_0x00000005",
            [
                [ItemPath,ItemOffset,ItemLength,Type],
                [ItemPath,ItemOffset,ItemLength,Type],
                [ItemPath,ItemOffset,ItemLength,Type]...

            ]
        ]...
    ]
    """
    tmp_list = []
    for pack in packman:
        meta_items = [pack[0], pack[2], pack[3], pack[4]]
        current_item = pack[1]
        i = 0

        not_found = True
        while i < len(tmp_list) and not_found:
            not_found = current_item not in tmp_list[i]
            i += 1

        if not_found:
            tmp_list.append([current_item])
            tmp_list[len(tmp_list)-1].append([meta_items])
        else:
            tmp_list[i-1][1].append(meta_items)

    return tmp_list


def extract_packman_files(packman, version, name, region):
    """downloads temp BIN files extracts the game files from the BIN"""
    sorted_files = sort_packman(packman)
    tmp_path = os.path.join('TMP_BINS', region, name)
    print('Downloading {} BIN files...'.format(len(sorted_files)))
    for bin_items in sorted_files:
        bin_name = bin_items[0]
        print('Downloading BIN file: ' + bin_name)
        download_bin_file(name, version, region, bin_name)

        files = bin_items[1]
        bin_file = open(os.path.join(tmp_path, bin_name), 'rb')  # open BIN read here
        try:
            for file in files:
                path = file[0].split('/')
                print('Extracting file: ' + path[len(path)-2] + '/' + path[len(path)-1])
                path[4] = version
                path[5] = 'deploy'
                path = 'RADS/' + ('/'.join(path))
                build_path(path)

                offset = int(file[1])
                offlen = int(file[2])

                bin_file.seek(offset)
                compressed_flag = False
                if path.endswith('.compressed'):  # if file is compressed
                    path = path[:-11]
                    compressed_flag = True
                with open(path, 'wb') as f:
                    data = bin_file.read(offlen)
                    if compressed_flag:  # decompress the file
                        print('Decompressing...')
                        data = zlib.decompress(data)
                    f.write(data)
        finally:
            bin_file.close()  # close BIN read here

    shutil.rmtree(tmp_path, ignore_errors=True)


def download_release_manifest(name, version):
    """Download the ReleaseManifest to the RADS folder"""
    stuff = ['live', 'projects', name, 'releases', version, 'releasemanifest']
    url = 'releases' + '/'.join(stuff)
    path = os.path.join('RADS', *stuff)
    download_file_RADS(url, path)


def build_path(path):
    """create a path of folders from a path"""
    if not os.path.exists(path):
        os.makedirs(path)


def download_file_RADS(url, path):
    """downloads the files right to the RADS folder"""
    #path = path.replace('/live', '', 1)
    target_url = os.path.join(LOLPATCHSERVER, url)
    build_path(os.path.split(path)[0])
    target_url = target_url.replace('\\', '//', 1)
    print('Downloading: Release manifest ({}l)'.format(target_url))
    with open(path, 'wb') as f:
        f.write(requests.get(target_url).content)


def get_latest_version(name):
    """Gets the latest version of the project"""
    url = 'releases/live/projects/' + name + '/releases/releaselisting'
    target_url = LOLPATCHSERVER + url
    version = requests.get(target_url).content.decode('utf-8')
    return version.split('\r\n')[0]


def read_packman(packman):
    """Reads PackageManifest files and output the propertys for each line"""
    files = packman.split('\r\n')
    files = files[1:-1]  # remove the "Magic number" at the beginning and the blank line at the end
    for i, file in enumerate(files):
        files[i] = file.split(',')
    return files


def download_packman(name, version):
    """downloads the PackageManifest to memory"""
    url = 'releases/live/projects/' + name + '/releases/' + version + '/packages/files/packagemanifest'
    target_url = LOLPATCHSERVER + url
    print("Downloading: {}".format(target_url))
    packman = requests.get(target_url).content.decode('utf-8')
    return packman


def download_bin_file(name, version, region, bin_filename):
    """downloads the BIN files from Riot Servers"""
    url = 'releases/live/projects/' + name + '/releases/' + version + '/packages/files/' + bin_filename
    target_url = LOLPATCHSERVER + url
    print("Downloading bin file: {}".format(target_url))
    tmp_bin = os.path.join('TMP_BINS', region, name)
    build_path(tmp_bin)
    bin_filename = os.path.join(tmp_bin, bin_filename)
    with open(bin_filename, 'wb') as f:
        f.write(requests.get(target_url).content)


def download(name, region):
    """main download procedure calls all the functions"""
    version = get_latest_version(name)
    print("Name:", name)
    print("Version:", version)
    packman = download_packman(name, version)
    files = read_packman(packman)
    download_release_manifest(name, version)
    extract_packman_files(files, version, name, region)


def main():
    download('lol_game_client', 'NA')


if __name__ == "__main__":
    main()
