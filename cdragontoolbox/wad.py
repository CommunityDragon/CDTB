import struct
import hashlib
import binascii
import zlib
import gzip
import zstd
import os
import json
import logging

logger = logging.getLogger("wad_parser")

logging.basicConfig(
        level=logging.WARNING,
        datefmt='%H:%M:%S',
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )
logger.setLevel(logging.DEBUG)

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

    if version_major in (2, 3):
        if version_major == 2:
            parser.seek(88)
        if version_major == 3:
            parser.seek(256)
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
            magic = binascii.hexlify(parser.raw(12)).decode()
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
        os.makedirs(head, exist_ok=True)

    # Save the file
    with open(filename, "wb") as f:
        f.write(file_data)


def save_files(directory, data, file_headers, ignore=None):
    parser = Parser(data)
    if ignore is None:
        ignore = {}
    else:
        # convert list to dict for fast lookup
        ignore = {hash: True for hash in ignore}

    _five_percent_interval = int(len(file_headers) / 20.)
    for i, header in enumerate(file_headers):
        parser.seek(header['offset'])
        if header['compressed']:
            file_data = parser.raw(header['compressed_file_size'])
            try:
                file_data = gzip.decompress(file_data)
                #print('gzip:',file_data)
            except OSError: #if gzip wont work must be zstd
                try:
                    file_data = zstd.decompress(file_data)
                    #print('zstd:',file_data)
                except (OSError,ValueError): #if gzip or zstd wont work must be text of some sort (don't know)
                    file_data = file_data[4:]#remove the first 4 bytes useless
                    #print('OSError:',file_data)

        #assert header['sha256'] == hashlib.sha256(file_data).hexdigest()  # Make sure we have the correct data!

        filename = header['filename']
        ext = header['extension']
        if ext is not None and not filename.endswith(ext):
            filename = filename + '.' + ext
        filename = filename.split('/')
        filename = os.path.join(directory, *filename)

        if not ignore.get(header['file_hash'], False):
            #this is broken?
            try:
                extract_file(filename, file_data)
            except UnboundLocalError:
                pass
				
        #this is broken?
        '''
        if i % _five_percent_interval == 0:
            print(f'{i} out of {len(file_headers)} files extracted...')
        '''


def identify_file_type(fn):
    import json
    import scipy.ndimage
    try:
        with open(fn) as f:
            json.load(f)
            return "json"
    except:
        pass
    try:
        scipy.ndimage.imread(fn)
        return "image"
    except OSError:
        pass


def identify_unknown_file_types(directory):
    # We don't know the file name or file signatures for some files, so try a few different methods of opening them until one works
    files = [f for f in os.listdir(os.path.join(directory, 'unknown')) if not os.path.splitext(f)[1]]
    for fn in files:
        fn = os.path.join(directory, 'unknown', fn)
        file_type = identify_file_type(fn)
        if file_type == 'json':
            try:
                os.rename(fn, fn + '.json')
            except FileExistsError:
                os.rename(fn, fn + '(error).json')
        elif file_type == "image":
            # Just assume jpg
            try:
                os.rename(fn, fn + '.jpg')
            except FileExistsError:
                os.rename(fn, fn + '(error).jpg')

class wad():
	def __init__(self,vob):
		import inspect
		scriptpath = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
		
		with open(scriptpath+'\\hashes.json') as f:
			self.file_hashes = json.load(f)
		with open(scriptpath+'\\signatures.json') as f:
			self.signatures = json.load(f)
		with open(scriptpath+'\\ignore.json') as f:
			self.ignore = json.load(f)
		
		if vob >= 1:
			logger.setLevel(logging.DEBUG)
		else:
			logger.setLevel(logging.INFO)
		if vob >= 2:
			logging.getLogger("requests").setLevel(logging.DEBUG)
		
	def extract(self,path):
		logger.info("extracting %s", foutput)
		directory = os.path.dirname(path)
		wad_filename = path
		
		logger.debug("Loading data...")
		with open(wad_filename, "rb") as f:
			data = f.read()
		if wad_filename.endswith(".compressed"):
			logger.debug("Decompressing data...")
			data = zlib.decompress(data)

		logger.debug("Loading headers...")
		headers = extract_header_info(data, self.file_hashes, self.signatures)

		logger.debug(f"Got {len(headers)} headers/files.")

		logger.debug("Saving files...")
		save_files(directory, data, headers, ignore=self.ignore)

		logger.debug("Identifying the type of unknown files...")
		identify_unknown_file_types(directory)
        
def main():
    import sys
    import json

    with open('hashes.json') as f:
        file_hashes = json.load(f)
    with open('signatures.json') as f:
        signatures = json.load(f)
    with open('ignore.json') as f:
        ignore = json.load(f)

    try:
        directory = sys.argv[2]
    except IndexError:
        directory = "temp"
    os.makedirs(directory, exist_ok=True)

    try:
        wad_filename = sys.argv[1]
    except IndexError:
        wad_filename = "default-assets.wad"

    logger.debug("Loading data...")
    with open(wad_filename, "rb") as f:
        data = f.read()
    if wad_filename.endswith(".compressed"):
        logger.debug("Decompressing data...")
        data = zlib.decompress(data)

    logger.debug("Loading headers...")
    headers = extract_header_info(data, file_hashes, signatures)

    logger.debug(f"Got {len(headers)} headers/files.")

    logger.debug("Saving files...")
    save_files(directory, data, headers, ignore=ignore)

    logger.debug("Identifying the type of unknown files...")
    identify_unknown_file_types(directory)


if __name__ == "__main__":
    main()
