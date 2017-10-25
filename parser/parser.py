import struct
import os
import haslib


"""
The file hashes are generated using xxhash.xxh64 on the filename. The filename starts with plugins/...
Here is a list of all the file names we know about:
https://github.com/Pupix/lol-wad-parser/blob/master/lib/hashes.json
If you take any one of those filenames and prepend "plugins", you should get the correct hash value.
These hash values are stored in the decompressed wad file; however, any leading zeros are not in the file hash in the wad file.

The process here is to:
1) Download a (compressed) wad file.
2) Decompress it if necessary.
3) Look through the file headers for all the files an extract the header info.
4) Inside the header info is the file hash, and we can map that back to the correct filename in the above linked hashes.json file.
5) Pull the file data chunk from the wad file.
6) Save the file data to its filename.
"""


class Parser(object):
    def __init__(self, data):
        self.data = data
        self.position = 0

    def seek(self, position):
        self.position = position

    def skip(self, amount):
        self.position += amount
        return None

    def rewind(self, amount):
        self.position -= amount

    def unpack(self, fmt):
        length = struct.calcsize(fmt)
        result = struct.unpack(fmt, self.data[self.position:self.position + length])
        self.position += length
        return result

    def raw(self, length):
        result = self.data[self.position:self.position + length]
        self.position += length
        return result

    # Info table from struct documentation
    #x   pad byte    no value
    #c   char    bytes of length 1   1
    #b   signed char integer 1   (1),(3)
    #B   unsigned char   integer 1   (3)
    #?   _Bool   bool    1   (1)
    #h   short   integer 2   (3)
    #H   unsigned short  integer 2   (3)
    #i   int integer 4   (3)
    #I   unsigned int    integer 4   (3)
    #l   long    integer 4   (3)
    #L   unsigned long   integer 4   (3)
    #q   long long   integer 8   (2), (3)
    #Q   unsigned long long  integer 8   (2), (3)
    #n   ssize_t integer     (4)
    #N   size_t  integer     (4)
    #e   (7) float   2   (5)
    #f   float   float   4   (5)
    #d   double  float   8   (5)
    #s   char[]  bytes
    #p   char[]  bytes
    #P   void *  integer     (6)


def extract_header_info(data, file_hashes, signatures):
    parser = Parser(data)
    parser.seek(0)

    _magic1, _magic2, version_major, version_minor = parser.unpack("ccBB")
    magic = _magic1 + _magic2; del _magic1; del _magic2

    if version_major == 2:
        parser.skip(84)
        wad_header_unk, wad_header_entry_header_offset, wad_header_entry_header_cell_size, wad_header_file_count = parser.unpack("QHHI")

        wad_file_headers = []
        for i in range(wad_header_file_count):
            path_hash, offset, compressed_file_size, file_size, compressed, duplicate, unk, unk0, sha256 = parser.unpack("QIIIBBBBQ")

            file_hash = hex(path_hash)[2:]  # The [2:] is because hex(some_int) has "0x" prepended to it; it is returned as a string.
            # Left pad with 0s if necessary
            while len(file_hash) < 16:
                file_hash = '0' + file_hash

            # See if we know the filename for this hash; if so, get it!
            unknown_file_path = "unknown"
            filename = file_hashes.get(file_hash, os.path.join(unknown_file_path, file_hash))

            # Get the file extension
            position = parser.position
            parser.seek(offset)
            magic = binascii.hexlify(parser.raw(12))
            parser.seek(position)
            ext = get_extension(magic, signatures)

            wad_file_headers.append({
                "path_hash": path_hash,
                "file_hash": file_hash,
                "filename": filename,
                "extension": ext,
                "offset": offset,
                "compressed_file_size": compressed_file_size,
                "file_size": file_size,
                "compressed": compressed,
                "duplicate": duplicate,
                "unk": unk,
                "unk0": unk0,
                "sha256": sha256
            })
    else:
        raise NotImplementedError("A parser for wad version {} is not implemented.".format(version_major))
    return wad_file_headers


def get_extension(a_hash, signatures):
    for ext_hash, ext_name in signatures.items():
        if a_hash.startswith(ext_hash):
            return ext_name


def extract_file(filename, file_data):
    """
    header_data: a dict from the above extract_header_info function
    file_data: a piece of data from the wad file, extracted via data[header['offset']:header['offset'] + header['file_size']]  (take into account possible compression)
    """
    # Make the direc if it doesn't exist
    head, tail = os.path.split(filename)
    if head != '':
        os.makedirs(head, exists_ok=True)

    # Save the file
    with open(filename, "wb") as f:
        f.write(file_data)


def save_files(data, file_headers):
    parser = Parser(data)
    for header in file_headers:
        parser.seek(header['offset'])
        if header['compressed']:
            file_data = parser.raw(header['compressed_file_size'])
            file_data = zlib.decompress(file_data)
        else:
            file_data = parser.raw(header['file_size'])

        #assert header['sha256'] == hashlib.sha256(file_data).hexdigest()  # Make sure we have the correct data!

        filename = header['filename']
        ext = header['extension']
        if ext is not None:
            filename = filename + '.' + ext

        extract_file(header['filename'], file_data)


def main()
    import sys
    import ujson as json
    import requests

    file_hashes = json.loads(requests.get('https://github.com/Pupix/lol-wad-parser/raw/master/lib/hashes.json').text)
    signatures = json.loads(requests.get('https://github.com/Pupix/lol-wad-parser/raw/master/lib/signatures.json').text)

    try:
        directory = sys.argv[2]
    except IndexError:
        directory = "temp"
    os.makedirs(directory, exists_ok=True)

    try:
        wad_filename = sys.argv[1]
    except IndexError:
        wad_filename = "default-assets.wad"

    with open(wad_filename, "rb") as f:
        data = f.read()
    if wad_filename.endswith(".compressed")
        data = zlib.decompress(data)

    headers = extract_header_info(data, file_hashes, signatures)
    save_files(data, headers)


if __name__ == "__main__":
    main()

