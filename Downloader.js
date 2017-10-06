var rmParser = require('lol-releasemanifest-parser'),
    rm = new rmParser();
var url = require("url")
var path = require("path")
var request = require('request');
var fs = require('fs');
var Sync = require('sync');
var BinaryFile = require('binary-file');
var async = require('asyncawait/async');
var await = require('asyncawait/await');
 

//globals
var LoLPatchServer = "http://l3cdn.riotgames.com/"

///some random function might have use later
/*
var ManifestToUrl = function(JSONdata,Name, Version,PackMan){
	
	function CompareManifest(PackMan,Paths, Name, Version) {
		console.log("working");
		console.log(PackMan);
		AddedPath = '/projects/'+Name+'/releases/'+Version+'/files/'
		PatchedList = []
		for (var m in PackMan) {
			temp = "/"+(PackMan[m].split("/").splice(6).join('/'))
			NotFound = true
			for (var p in Paths) {
				if (temp == Paths[p]){
					//console.log("found match");
					PatchedList.push(AddedPath+Paths[p])
					NotFound = false
					break
				}
			}	
			//console.log("ok?");
			if (NotFound){
				console.log("No match found");
				PatchedList.push(PackMan[m])
			}
		}
		return(PatchedList)
	}
	
	function objectToPaths(data) {
	  var validId = /^[a-z_$][a-z0-9_$]*$/i;
	  var result = [];
	  doIt(data, "");
	  return result.splice(1);

	  function doIt(data, s, TruePath) {
		if (data && typeof data === "object") {
		  if (Array.isArray(data)) {
			for (var i = 0; i < data.length; i++) {
			  doIt(data[i], s + "[" + i + "]",TruePath+"/"+data['name']);
			}
		  } else {
			for (var p in data) {
			  if (validId.test(p)) {
				doIt(data[p], s + "." + p,TruePath+"/"+data['name']);
			  } else {
				doIt(data[p], s + "[\"" + p + "\"]","");
			  }
			}
		  }
		} else {
				if (s.endsWith("name")){
					TruePath = TruePath.split('undefined/').join('')
					result.push(TruePath);
				}
			}
	   }
	}
	
	URL = "releases/live/projects/"+Name+"/releases/"+Version+"/"
	Path = "RADS/"+URL+"deploy/"
	URL += "files/"
	
	ServerPath = LoLPatchServer+URL
	
	Paths = objectToPaths(JSONdata);
	console.log(Paths);
	Paths = CompareManifest(PackMan,Paths,Name, Version);
	console.log(Paths);
		
}*/
var ReadAndWriteBIN = function(fBin,SavePath,Seek,len,Type){
	/**
     * 6 = uncompressed - archive
     * 22 = compressed - archive
     * 5 = managedfile
     * greater than 0 = compressed
     * 0 = normal file
     * 2 = compressed file
     * 4 = copy to sln?
     */
	BuildPath(SavePath)
	const SavedFile = new BinaryFile(SavePath, 'w');
	(async (function () {
		try {
			await (fBin.open())
			await (SavedFile.open())
const data= await (fBin.read(len, position = Seek))
			await (SavedFile.write(data))
			await (fBin.close())
			await (SavedFile.close())
		} catch (err) {
			console.log(`There was an error: ${err}`);
		}
	}))();
}

var SortPackMan = function(PackMan,Version,Name){
	TmpArr=[]
	for(var Pack in PackMan){
		metaitems = [PackMan[Pack][0],PackMan[Pack][2],PackMan[Pack][3],PackMan[Pack][4]]
		currentitem = PackMan[Pack][1]
		i=0
		NotFound=true
		while(i < TmpArr.length && NotFound){
			NotFound = (TmpArr[i].indexOf(currentitem) === -1)
			i++
		}
		if (NotFound){
			TmpArr.push([currentitem])
			TmpArr[TmpArr.length-1].push([metaitems])
		}else{
			TmpArr[i-1][1].push(metaitems)
		}		
	}
	return(TmpArr)
}


var DownloadPackManFiles = function(PackMan,Version,Name,Region){
	sortedfiles = SortPackMan(PackMan)
	TempPath = 'TMP_BINS/'+Region+'/'+Name+'/'
	for(var binitems in sortedfiles){
		BinName = sortedfiles[binitems][0]
		console.log("Downloading BIN file: " + BinName);
		DownloadBinFile(Name, Version,Region,BinName)
		fBin = new BinaryFile(TempPath+BinName, 'r');
		files = sortedfiles[binitems][1]
		for (var file in files){
			property = files[file]
			Path = property[0].split('/')
			console.log("Extracting file: "+ Path[Path.length-2] + "/" + Path[Path.length-1]);
			Path[4] = Version
			Path[5] = "deploy"
			Path = "RADS"+Path.join("/")
			ReadAndWriteBIN(fBin,Path,parseInt(property[1]),parseInt(property[2]))
		}
	}
	rmDir(TempPath)
}

var rmDir = function(dirPath) {
	try { var files = fs.readdirSync(dirPath); }
	catch(e) { return; }
	if (files.length > 0)
	for (var i = 0; i < files.length; i++) {
		var filePath = dirPath + '/' + files[i];
		if (fs.statSync(filePath).isFile())
			fs.unlinkSync(filePath);
		else
			rmDir(filePath);
	}
	fs.rmdirSync(dirPath);
}

var DownloadReleaseMan = function(Name, Version){
	URL = "live/projects/"+Name+"/releases/"+Version+"/releasemanifest"
	Path = "RADS/"+URL
	Download_File_RADS("releases/"+URL,Path)
}

var BuildPath = function(Path){
	ParsePath = Path.replace(/\/[^\/]+$/, '')//https://stackoverflow.com/questions/27509722/split-string-of-folder-path
	DirectoryPaths = ParsePath.split("/")	
	dir=""
	for (var Directory in DirectoryPaths) {
		dir += DirectoryPaths[Directory]+"/"
		if (!fs.existsSync(dir)){
			fs.mkdirSync(dir);
		}
	}
}

var Download_File_RADS = function(URL,Path,Num){
	function Startdownload(a,b, callback) {
		process.nextTick(function(){
			var file = fs.createWriteStream(a);
			var r = request(b).pipe(file);
			r.on('finish', function() { 
				callback(null);
			});
		})
	}	
	Path = Path.replace('/live', '')
	target_url = path.join(LoLPatchServer,URL)
	BuildPath(Path)
	target_url = target_url.replace('\\','//')

	Startdownload.sync(null, Path,target_url);
}




var Download_File_To_Var = function(URL){
	function Startdownload(a, callback) {
		process.nextTick(function(){
			request(a, function(error, response, body) {
				callback(null, body);
			});
		})
	}	
	
	requestSettings = {
	method: 'GET',
	url: URL,
	};
	
	let result = Startdownload.sync(null, requestSettings);
	return(result)
}

var GetLatestVersion = function(Name,Region){
	URL = "releases/live/projects/"+Name+"/releases/releaselisting_"+Region
	target_url = LoLPatchServer+URL
	version = Download_File_To_Var(target_url).split("\r\n")[0];
	return(version)
}


var ReadPackMan = function(File){
	for (i in File) {
		File[i] = (File[i].split(","))
	}
	File.shift();
	File.pop();
	return (File)
}

var DownloadPackMan = function(Name, Version){
	URL = "releases/live/projects/"+Name+"/releases/"+Version+"/packages/files/packagemanifest"
	target_url = LoLPatchServer+URL
	PackMan = Download_File_To_Var(target_url).split("\r\n");
	return(PackMan)
}

var DownloadBinFile = function(Name, Version,Region,BIN){
	function Startdownload(a,b, callback) {
		process.nextTick(function(){
			var file = fs.createWriteStream(a);
			var r = request(b).pipe(file);
			r.on('finish', function() { 
				callback(null);
			});
		})
	}	
	URL = "releases/live/projects/"+Name+"/releases/"+Version+"/packages/files/"+BIN
	target_url = LoLPatchServer+URL
	tmpbin = 'TMP_BINS/'+Region+'/'+Name+'/'
	BuildPath(tmpbin)
	BIN = tmpbin+BIN
	Startdownload.sync(null, BIN,target_url);
	return(BIN)
}

var Download = function(Region,Name) {
	function SyncOperationToAsync (callback ) {
		Sync(function(){
			version = GetLatestVersion(Name,Region);
			console.log(Name);
			console.log(version);
			PackMan = DownloadPackMan(Name,version);
			PackMan = ReadPackMan(PackMan)
			DownloadReleaseMan(Name,version);
			DownloadPackManFiles(PackMan,version,Name,Region);
			callback(null);
		})
	}

	SyncOperationToAsync (function () {
		
	});
}

var Main = function(){
	Download('NA','lol_game_client')
}
Main();