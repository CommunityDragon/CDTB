import os
path = os.path

import shutil
import requests
import zlib

#globals
LoLPatchServer = "http://l3cdn.riotgames.com/"

#some random function might have use later not yet converted to python
'''
var ManifestToUrl = function(JSONdata,Name, Version,PackMan){
	
	function CompareManifest(PackMan,Paths, Name, Version) {
		print("working")
		print(PackMan)
		AddedPath = '/projects/'+Name+'/releases/'+Version+'/files/'
		PatchedList = []
		for (var m in PackMan) {
			temp = "/"+(PackMan[m].split("/").splice(6).join('/'))
			NotFound = true
			for (var p in Paths) {
				if (temp == Paths[p]){
					//print("found match")
					PatchedList.push(AddedPath+Paths[p])
					NotFound = false
					break
				}
			}	
			//print("ok?")
			if (NotFound){
				print("No match found")
				PatchedList.push(PackMan[m])
			}
		}
		return(PatchedList)
	}
	
	function objectToPaths(data) {
	  var validId = /^[a-z_$][a-z0-9_$]*$/i
	  var result = []
	  doIt(data, "")
	  return result.splice(1)

	  function doIt(data, s, TruePath) {
		if (data && typeof data === "object") {
		  if (Array.isArray(data)) {
			for (var i = 0 i < data.length i++) {
			  doIt(data[i], s + "[" + i + "]",TruePath+"/"+data['name'])
			}
		  } else {
			for (var p in data) {
			  if (validId.test(p)) {
				doIt(data[p], s + "." + p,TruePath+"/"+data['name'])
			  } else {
				doIt(data[p], s + "[\"" + p + "\"]","")
			  }
			}
		  }
		} else {
				if (s.endsWith("name")){
					TruePath = TruePath.split('undefined/').join('')
					result.push(TruePath)
				}
			}
	   }
	}
	
	URL = "releases/live/projects/"+Name+"/releases/"+Version+"/"
	Path = "RADS/"+URL+"deploy/"
	URL += "files/"
	
	ServerPath = LoLPatchServer+URL
	
	Paths = objectToPaths(JSONdata)
	print(Paths)
	Paths = CompareManifest(PackMan,Paths,Name, Version)
	print(Paths)
		
}'''
#---------------------------------------------------------------------#
#returns a sorted list of what files are from what BIN (showed below)
'''
	
	["BIN_0x0000002d",
		[
			[ItemPath,ItemOffset,ItemLength,Type],
			[ItemPath,ItemOffset,ItemLength,Type],
			[ItemPath,ItemOffset,ItemLength,Type]...
			
		]
	"BIN_0x00000005",
		[
			[ItemPath,ItemOffset,ItemLength,Type],
			[ItemPath,ItemOffset,ItemLength,Type],
			[ItemPath,ItemOffset,ItemLength,Type]...
			
		]
	]
'''
def SortPackMan (PackMan):
	TmpArr=[]
	for Pack in PackMan:
		metaitems = [Pack[0],Pack[2],Pack[3],Pack[4]]
		currentitem = Pack[1]
		i=0
		
		NotFound=True
		while(i < len(TmpArr) and NotFound):
			NotFound = not currentitem in TmpArr[i]
			i+=1
			
		if (NotFound):
			TmpArr.append([currentitem])
			TmpArr[len(TmpArr)-1].append([metaitems])
		else:
			TmpArr[i-1][1].append(metaitems)
			
	return(TmpArr)


#downloads temp BIN files extracts the game files from the BIN
def ExtractPackManFiles (PackMan,Version,Name,Region):
	sortedfiles = SortPackMan(PackMan)
	TempPath = 'TMP_BINS/'+Region+'/'+Name+'/'
	for binitems in sortedfiles:
		BinName = binitems[0]
		print("Downloading BIN file: " + BinName)
		DownloadBinFile(Name, Version,Region,BinName)
		
		files = binitems[1]
		BINFile = open(TempPath+BinName, "rb")#open BIN read here
		for file in files:
			Path = file[0].split('/')
			print("Extracting file: "+ Path[len(Path)-2] + "/" + Path[len(Path)-1])
			Path[4] = Version
			Path[5] = "deploy"
			Path = "RADS/"+('/'.join(Path))
			BuildPath(Path)

			Offset = int(file[1])
			Offlen = int(file[2])
			
			BINFile.seek(Offset)
			CompressedFlag=False
			if Path.endswith('.compressed'): #if file is compressed
				Path=Path[:-11]
				CompressedFlag = True
			with open(Path, 'wb') as f:
				data = BINFile.read(Offlen)
				if CompressedFlag: #decompress the file
					print("Decompressing...")
					data = zlib.decompress(data)
				f.write(data)
		
		BINFile.close()#close BIN read here
		
	shutil.rmtree(TempPath, ignore_errors=True)

#download the ReleaseManifest to the RADS folder
def DownloadReleaseMan (Name, Version):
	print("Downloading: Release manifest")
	URL = "live/projects/"+Name+"/releases/"+Version+"/releasemanifest"
	Path = "RADS/"+URL
	Download_File_RADS("releases/"+URL,Path)

#creates a path of folders from a path -removes the file at the end
def BuildPath (Path):
	Path = '/'.join(Path.split('/')[:-1])
	if not path.exists(Path):
		os.makedirs(Path)
	
#downloads the files right to the RADS folder
def Download_File_RADS (URL,Path):
	Path = Path.replace('/live', '',1)
	target_url = path.join(LoLPatchServer,URL)
	BuildPath(Path)
	target_url = target_url.replace('\\','//',1)
	with open(Path, 'wb') as f:
		f.write(requests.get(target_url).content)

#Gets the latest version of the project
def GetLatestVersion (Name,Region):
	URL = "releases/live/projects/"+Name+"/releases/releaselisting_"+Region
	target_url = LoLPatchServer+URL
	version = requests.get(target_url).content.decode("utf-8")
	return(version.split("\r\n")[0])

#Reads PackageManifest files and output the propertys for each line
def ReadPackMan(files):
	files = files[1:-1] #remove the "Magic number" at the beginning and the blank line at the end
	for i, file in enumerate(files):
		files[i] = file.split(",")
		
	return (files)

#downloads the PackageManifest to memory
def DownloadPackMan (Name, Version):
	URL = "releases/live/projects/"+Name+"/releases/"+Version+"/packages/files/packagemanifest"
	target_url = LoLPatchServer+URL
	PackMan = requests.get(target_url).content.decode("utf-8")
	return(PackMan.split("\r\n"))

#downloads the BIN files from Riot Servers
def DownloadBinFile(Name, Version,Region,BIN):
	URL = "releases/live/projects/"+Name+"/releases/"+Version+"/packages/files/"+BIN
	target_url = LoLPatchServer+URL
	tmpbin = 'TMP_BINS/'+Region+'/'+Name+'/'
	BuildPath(tmpbin)
	BIN = tmpbin+BIN
	with open(BIN, 'wb') as f:
		f.write(requests.get(target_url).content)

#main download procedure calls all the functions
def Download (Region,Name):
	version = GetLatestVersion(Name,Region)
	print(Name)
	print(version)
	PackMan = DownloadPackMan(Name,version)
	PackMan = ReadPackMan(PackMan)
	DownloadReleaseMan(Name,version)
	ExtractPackManFiles(PackMan,version,Name,Region)

def Main():
	Download('NA','lol_game_client')

Main()
