package lolpatcher;

import lolpatcher.manifest.ReleaseManifest;
import java.io.File;
import java.io.FilenameFilter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.MalformedURLException;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import lolpatcher.manifest.ManifestFile;

/**
 *
 * @author Rick
 */
public class ArchivePurgeTask extends PatchTask {

    float globalPercentage, archivePercentage;
    int nArchives = 0;
    
    String project, targetVersion, branch, type;

    public ArchivePurgeTask(String project, String targetVersion, String branch, String type) {
        this.project = project;
        this.targetVersion = targetVersion;
        this.branch = branch;
        this.type = type;
    }
    
    
    @Override
    public void patch() throws MalformedURLException, IOException, NoSuchAlgorithmException {
        currentFile = "Reading manifest";
        ReleaseManifest mf = ReleaseManifest.getReleaseManifest(project, targetVersion, branch, type);
        
        ArrayList<LoLPatcher.Archive> archivesToPurge = new ArrayList<>();
        
        ArrayList<ManifestFile> files = new ArrayList<>(mf.files.length);
        Collections.addAll(files, mf.files);
        
        Collections.sort(files, new Comparator<ManifestFile>() {
            @Override
            public int compare(ManifestFile o1, ManifestFile o2) {
                return Integer.compare(o1.releaseInt , o2.releaseInt);
            }
        });
        
        LoLPatcher.Archive lastArchive = null;
        for(ManifestFile f : files){
            if(f.fileType == 22 || f.fileType == 6){
                if(lastArchive == null || !lastArchive.versionName.equals(f.release)){
                    lastArchive = new LoLPatcher.Archive(f.release, new ArrayList<ManifestFile>());
                    archivesToPurge.add(lastArchive);
                }
                lastArchive.files.add(f);
            }
        }
        nArchives = archivesToPurge.size();
        for(int i = 0; i < archivesToPurge.size(); i++){
            globalPercentage = ((float) i / nArchives);
            purgeArchive(archivesToPurge.get(i));
            if(done) return;
        }
        done = true;
        globalPercentage = 1;
        archivePercentage = 0;
    }
    
    private void purgeArchive(LoLPatcher.Archive ar) throws IOException{
        String folderName = "RADS/"+type + "/" + project + "/filearchives/"
            + ar.versionName + "/";
        File folder = new java.io.File(folderName);
        if(!folder.exists()){
            throw new IOException("Invalid installation. Run quick repair first.");
        }
        String[] archives = folder.list(new FilenameFilter() {
            @Override
            public boolean accept(java.io.File dir, String name) {
                return name.matches("Archive_[0-9]+\\.raf");
            }
        });
        if(archives.length != 1){
            throw new IOException("Invalid installation. Expected one archive, "
                    + "found " + archives.length  + " in " +folder.getCanonicalPath()+".");
        }
        if(!new File(folder, archives[0]+".dat").exists()){
            throw new IOException("Invalid installation. Missing .raf.dat file in " +folder.getCanonicalPath()+".");
        }
        File sourceRaf = new File(folder, archives[0]);
        File sourceRafDat = new File(folder, archives[0]+".dat");
        
        int nFilesInTarget = 0;
        
        try (RAFArchive source = new RAFArchive(sourceRaf, sourceRafDat)) {
            File tempDir = new File(folder, "temp");
            if(tempDir.exists()){
                LoLPatcher.deleteDir(tempDir);
            }
            currentFile = ar.versionName;
            long sum = 0;
            for(RAFArchive.RafFile fi : source.fileList){
                sum += fi.size;
            }
            if(source.datRaf.length() == sum && source.fileList.size() == ar.files.size()){
                return; // only purge if file has gaps or contains unneeded files
            }
            tempDir.mkdir();
            currentFile = "Loading " + ar.versionName;
            try (RAFArchive target = new RAFArchive(folderName + "/temp/Archive_1.raf")) {
                for(int i = 0; i < ar.files.size(); i++){
                    ManifestFile f = ar.files.get(i);
                    archivePercentage = (float) i / ar.files.size();
                    currentFile = f.name;
                    nFilesInTarget++;
                    
                    try (InputStream in = source.readFile(f.path + f.name)) {
                        try(OutputStream os = target.writeFile(f.path + f.name, f)){
                            byte[] buffer = new byte[1024];
                            int r;
                            while((r = in.read(buffer)) != -1){
                                speedStat(r);
                                if(done){
                                    System.out.println("exited archive purge task");
                                    return;
                                }
                                os.write(buffer, 0, r);
                            }
                        }
                    }
                    int olen = source.dictionary.get(f.path + f.name).size;
                    int nlen = target.dictionary.get(f.path + f.name).size;
                    if(nlen != olen){
                        throw new IOException("Size mismatch:" + nlen + " " + olen);
                    }
                }
            }
        }
        
        if(nFilesInTarget == 0){
            LoLPatcher.deleteDir(folder);
        }else{
            if(!sourceRaf.delete()){
                throw new IOException("Delete failed for " + folderName + archives[0]);
            }
            if(!sourceRafDat.delete()){
                throw new IOException("Delete failed for " + folderName + archives[0]+".dat");
            }
            if(!new File(folderName + "/temp/Archive_1.raf").renameTo(new File(folder,"Archive_1.raf"))){
                throw new IOException("Move failed for " + folderName + "temp/Archive_1.raf");
            }
            if(!new File(folderName + "/temp/Archive_1.raf.dat").renameTo(new File(folder,"Archive_1.raf.dat"))){
                throw new IOException("Move failed for " + folderName + "temp/Archive_1.raf.dat");
            }
            
            new File(folderName + "/temp/").delete();
        }
    }

    @Override
    public float getPercentage() {
        return 100 * (globalPercentage + archivePercentage / nArchives);
    }
}
