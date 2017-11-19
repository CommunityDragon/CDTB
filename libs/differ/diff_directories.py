from typing import List
from collections import defaultdict
import glob
import hashlib
import os


def diff_directories(directory_list: List, base_path: str):
    """
    :param directory_list (List):
        A list of directories in order from oldest to newest. These directories will be compared.
        The assumption is that the contents of all the directories are directly comparable.

    :return: Mapping
        A mapping from each unique filename in all the directories in `directory_list` to what version of the file should be used when a user requests a filename+version.

    Example output:
        {
          "annie.json": {
            "7.18": "7.18/annie.json",
            "7.19": "7.18/annie.json",
            "7.20": "7.20/annie.json",
            "7.21": "7.20/annie.json",
            "7.22": "7.22/annie.json"
          }
        }
    """

    results = defaultdict(list)
    directory_hashes = defaultdict(dict)
    for version_direc in directory_list:
        version_base_string = f"{base_path}/{version_direc}/"
        for full_fn in glob.iglob(f"{version_base_string}**", recursive=True):
            fn = full_fn[len(f"{version_base_string}"):]
            if os.path.isfile(full_fn):
                directory_hashes[version_direc][fn] = md5(full_fn)

    for version_direc in directory_list:  # Make sure to iterate in order
        filehashes = directory_hashes[version_direc]  # Get all the file hashes for this version
        # Go through all our files. If we have a new hash for a file, append it to our results.
        for fn, hash in filehashes.items():
            if fn in results:
                latest = results[fn][-1]
                old_hash, old_of_file = latest
                if hash == old_hash:
                    results[fn].append(results[fn][-1])
                else:
                    results[fn].append((hash, f"{version_direc}/{fn}"))
            else:
                results[fn].append((hash, f"{version_direc}/{fn}"))

    # Remove the hash from our results
    # Also, make this list into a dict by adding back in the versions that we duplicates, and referencing them to the last version in the list.
    for fn, version_fn_list in results.items():
        for i in range(len(version_fn_list)):
            version_fn_list[i] = version_fn_list[i][1]
        assert len(version_fn_list) == len(directory_list)
        version_fn_dict = {
            directory_list[i]: version_fn_list[i]
            for i in range(len(directory_list))
        }
        results[fn] = version_fn_dict

    return results

def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def main():
    from natsort import natsorted
    import os
    import json

    direc = "./example"
    direcs = os.listdir(direc)
    direcs = natsorted(direcs)
    results = diff_directories(directory_list=direcs, base_path=direc)

    dump = json.dumps(results, indent=2)
    print(dump)

    """
    Output:
    {
      "annie.json": {
        "7.18": "7.18/annie.json",
        "7.19": "7.18/annie.json",
        "7.20": "7.20/annie.json",
        "7.21": "7.20/annie.json",
        "7.22": "7.22/annie.json"
      }
    }
    """


if __name__ == "__main__":
    main()
