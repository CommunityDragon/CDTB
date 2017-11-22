from .functions import get_all_client_versions, download_LoL_exe, extract_client_version
import time
import json
import glob
import os

class correlator:
    # constructs the correlator object
    def __init__(self):
        caching_dir = '.cache'
        versions = get_all_client_versions()
        for i in range(0, 30):
            patch = '0.0.0.{}'.format(i)
            versions.remove(patch)
        self.versions = versions
        self.caching_dir = caching_dir
        self.time_stamp = time.time()

        if not os.path.exists(caching_dir):
            os.makedirs(caching_dir)

        if os.path.exists(os.path.join(caching_dir, 'versions.json')):
            with open(os.path.join(caching_dir, 'versions.json'), 'r') as f:
                self.version_conversion = json.load(f)
        else:
            self.version_conversion = {}

    # refreshes the correlator object
    def refresh(self):
        if (self.time_stamp + 3600) < time.time():
            versions = get_all_client_versions()
            for i in range(0, 30):
                patch = '0.0.0.{}'.format(i)
                versions.remove(patch)
            self.versions = versions

    # converts one patch into another
    def convert(self, versions = []):
        self.refresh()
        try:
            data = {}
            requested_versions = None

            if len(versions) == 0:
                requested_versions = self.versions
            else:
                requested_versions = versions

            for version in requested_versions:
                if version in self.versions:
                    if hasattr(self.version_conversion, version):
                        data[version] = self.version_conversion[version]
                    else:  
                        try:
                            client_path = download_LoL_exe(version, output_directory=self.caching_dir)
                            self.version_conversion[version] = extract_client_version(client_path)
                            data[version] = extract_client_version(client_path)
                        except:
                            self.version_conversion[version] = None
                            data[version] = None

            with open(os.path.join(self.caching_dir, 'versions.json'), 'w') as f:
                json.dump(self.version_conversion, f, indent=2)
                
            return data
        except Exception as error:
            print(error)