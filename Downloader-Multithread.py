"""
Downloads the package manifest for the current version of the lol client and extracts files from it.

Note: `packman` in this code stands for `package manifest`.
"""

import os
import sys
import shutil
import requests
import zlib
import json
from libs.EasyThreading.easythreading import *

def Hello(text):
	print(text)


def infinate_loop(text):
	print(text)
	while 1:
		pass

def main1():
	manager = ThreadsManager(cores=8)
	manager.create_priority_ring(2)
	manager.add_priority_fork_job(infinate_loop,0,fork=0,args=['Hello 00'])	
	manager.add_priority_fork_job(Hello,0,fork=1,args=['Hello 01'])		
	manager.add_priority_fork_job(Hello,1,fork=0,args=['Hello 10'])	
	manager.add_priority_fork_job(Hello,1,fork=1,args=['Hello 11'])		
	manager.start_priority_fork_job()
	
			
class ProjectData:

	def __init__(self,properties,RADS):
		self.RADS = RADS
		self.pbe = False
		if properties['name'].endswith('_PBE'):
			properties['name'] = properties['name'][:-4]
			self.RADS += '/PBE'
			self.pbe = True

		self.properties = properties
		self.serverurl = properties['schema']+properties['base']+properties['name']+'/releases/'	
		
	def autorun(self,cores):
		"""main download procedure calls all the functions"""
		self.get_latest_version()
		print("Name:", self.properties['name'])
		print("Version:", self.version)
		self.download_packman()
		self.read_packman()
		self.download_release_manifest()
		self.sort_packman()
		
		manager = ThreadsManager(cores=cores)
		self.manager = manager
		
		manager.create_priority_ring(2)
		self.download_extract_packman_files()
		manager.start_priority_fork_job()
		
	
	def get_latest_version(self):
		"""Gets the latest version of the project"""
		target_url = self.serverurl + 'releaselisting'
		print(target_url)
		version = requests.get(target_url).content.decode('utf-8')
		self.version = version.split('\r\n')[0]
		
	def download_packman(self):
		"""downloads the PackageManifest to memory"""
		target_url = self.serverurl + self.version + '/packages/files/packagemanifest'
		print("Downloading: {}".format(target_url))
		self.packman = requests.get(target_url).content.decode('utf-8')
		
	def read_packman(self):
		"""Reads PackageManifest files and output the propertys for each line"""
		files = self.packman.split('\r\n')
		files = files[1:-1]  # remove the "Magic number" at the beginning and the blank line at the end
		for i, file in enumerate(files):
			files[i] = file.split(',')
		self.packman = files
		
	def download_release_manifest(self):
		"""Download the ReleaseManifest to the RADS folder"""
		url = self.serverurl + self.version + '/releasemanifest'
		path = os.path.join(self.RADS,self.properties['name'],'releases',self.version)
		download_file_RADS(url, path)
		
	def sort_packman(self):
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
		for pack in self.packman:
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

		self.packman = tmp_list
	
	def download_extract_packman_files(self):
		"""downloads temp BIN files"""
		manager = self.manager
		tmp_path = os.path.join('TMP_BINS', self.properties['name'])
		print('Downloading {} BIN files...'.format(len(self.packman)))
		for i in range(len(self.packman)):
			bin_name = self.packman[i][0]
			print('adding BIN file ' + bin_name+' to queue!')
			manager.add_priority_fork_job(download_bin_file,0,fork=i,args=[self.serverurl+self.version, self.properties['name'], bin_name,self.pbe])
			print('adding extract to queue!')
			manager.add_priority_fork_job(self.extract_packman_files,1,fork=i,args=[tmp_path,self.packman[i],bin_name])
			
	def extract_packman_files(self,tmp_path,bin_items,bin_name):
		"""extracts the temp BIN files to the game files from the BIN"""
		files = bin_items[1]
		bin_path = os.path.join(tmp_path, bin_name)
		bin_file = open(bin_path, 'rb')  # open BIN read here
		try:
			for file in files:
				path = file[0].split('/')
				print('Extracting file: ' + path[len(path)-2] + '/' + path[len(path)-1])
				path[4] = self.version
				path[5] = 'deploy'
				path = self.RADS+'/' + ('/'.join(path[2:]))
				build_path(path,True)

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
			shutil.rmtree(bin_path, ignore_errors=True)
		
		
def download_file_RADS(target_url, path):
	"""downloads the files right to the RADS folder"""
	head, tail = os.path.split(target_url)
	path = path+'/'+tail
	build_path(path,True)
	print('Downloading: Release manifest ({})'.format(target_url))
	with open(path, 'wb') as f:
		f.write(requests.get(target_url).content)
		
		
def build_path(path,file):
    """create a path of folders from a path"""
    if file:
        path = os.path.dirname(path)
    if not os.path.exists(path):
        os.makedirs(path)
		
def download_bin_file(target_url, name, bin_filename,ispbe):
	"""downloads the BIN files from Riot Servers"""
	pbe = ''
	if ispbe:
		pbe='PBE'
	target_url += '/packages/files/' + bin_filename
	print("Downloading bin file: {}".format(target_url))
	tmp_bin = os.path.join('TMP_BINS',pbe,name)
	build_path(tmp_bin,False)
	bin_filename = os.path.join(tmp_bin, bin_filename)
	with open(bin_filename, 'wb') as f:
		f.write(requests.get(target_url).content)	
		
def read_project_list(path):
	try:
		with open(path) as f:
			projectlist = f.read().splitlines()
	except FileNotFoundError:
		print('Looks like your missing your "ProjectList" file in your config folder!')
		exit()

	projectlist = [json.loads(line) for line in projectlist if line.startswith('{')]
	return(projectlist)
	
def main():
	"""main download procedure calls all the functions"""
	added = True
	cores = int(sys.argv[1])
	
	if sys.argv[2] == 'all':
		projects = sys.argv[3:]
		added = False
	else:
		projects = sys.argv[2:]
		
	lolprojectnames = read_project_list('config/ProjectList')
	if added:
		lolprojectnames = [project for project in lolprojectnames if project['name'] in projects]
	else:
		lolprojectnames = [project for project in lolprojectnames if project['name'] not in projects]

	for projectProperties in lolprojectnames:
		project = ProjectData(projectProperties,'RADS/projects')
		print("Downloading "+project.properties['name']+"!")
		project.autorun(cores)
			
	
if __name__ == "__main__":
	if len(sys.argv) >= 3:
		main()
	else:
		print("Invalid argv!")