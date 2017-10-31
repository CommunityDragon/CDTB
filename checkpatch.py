"""
Downloads the package manifest for the current version of the lol client and extracts files from it.

Note: `packman` in this code stands for `package manifest`.
"""

import os
import subprocess
import sys
import requests
import json
	
			
class ProjectData:

	def __init__(self,properties):
		self.properties = properties
		self.versionpath = 'Versions'
		self.localversion = os.path.join(self.versionpath, properties['name'])
		self.serverurl = properties['schema']+properties['base']+properties['name']+'/releases/'

	def autorun(self):
		"""main download procedure calls all the functions"""
		build_path(self.versionpath,False)
		print("Name:", self.properties['name'])
		
		local = self.latest_local_version()
		server = self.latest_server_version()
		print("Local version:", str(local))
		print("Server version:", server[0])
		if str(local)  == server[0]:
			print('No new version found for:',self.properties['name'],'\n')
			return('')
		else:
			print('Found new version for:',self.properties['name'],'\n')
			with open(self.localversion, 'w') as f:
				for line in server:
					f.write('%s\n'%line)
			return(self.properties['name'])
		
	def latest_local_version(self):
		try:
			with open(self.localversion, 'r') as f:
				return(f.readline()[:-1])
		except FileNotFoundError:
			print('File does not exist! downloading')
			return(None)

	def latest_server_version(self):
		"""Gets the latest version of the project"""
		target_url = os.path.join(self.serverurl,'releaselisting')
		print(target_url)
		version = requests.get(target_url).content.decode('utf-8')
		return(version.split('\r\n'))
		
def build_path(path,file):
    """create a path of folders from a path"""
    if file:
        path = os.path.dirname(path)
    if not os.path.exists(path):
        os.makedirs(path)
		
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
	
	script = sys.argv[1]
	
	arguments = sys.argv[2]
	
	if sys.argv[3] == 'all':
		projects = sys.argv[4:]
		added = False
	else:
		projects = sys.argv[3:]
		
	lolprojectnames = read_project_list('config/ProjectList')
	if added:
		lolprojectnames = [project for project in lolprojectnames if project['name'] in projects]
	else:
		lolprojectnames = [project for project in lolprojectnames if project['name'] not in projects]
	
	updatelist=[]
	for projectProperties in lolprojectnames:
		project = ProjectData(projectProperties)
		print("Adding download of "+project.properties['name']+" to queue!")
		a = project.autorun()
		if not '' == a:
			updatelist.append(a)
	
	if not len(updatelist) == 0:
		print('Starting Script!')
		print('"{}" {} {}'.format(script, arguments,  " ".join(updatelist)))
		subprocess.call('"{}" {} {}'.format(script, arguments, " ".join(updatelist)))
	else:
		print("Nothing to update!")
	print('Done!')
	
if __name__ == "__main__":
	if len(sys.argv) >= 4:
		main()
	else:
		print("Invalid argv!")