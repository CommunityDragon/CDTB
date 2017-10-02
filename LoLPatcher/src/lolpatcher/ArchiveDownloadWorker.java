package lolpatcher;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.zip.InflaterInputStream;
import static lolpatcher.PatchTask.speedStat;
import lolpatcher.manifest.ManifestFile;
import nl.xupwup.Util.MiniHttpClient;

/**
 *
 * @author Rick
 */
public class ArchiveDownloadWorker extends Worker{
    
    LoLPatcher patcher;

    public ArchiveDownloadWorker(LoLPatcher patcher) {
        this.patcher = patcher;
    }

    @Override
    public void run() {
        try {
            try (MiniHttpClient htc = new MiniHttpClient("l3cdn.riotgames.com")) {
                htc.throwExceptionWhenNot200 = true;
                htc.setErrorHandler(defaultHttpErrorHandler);
                
                while(true){
                    LoLPatcher.Archive task;
                    synchronized(patcher.archivesToPatch){
                        if(patcher.archivesToPatch.isEmpty() || patcher.done || patcher.error != null){
                            break;
                        }
                        task = patcher.archivesToPatch.remove(0);
                    }
                    startTime = System.currentTimeMillis();
                    progress = 0;
                    RAFArchive archive = patcher.getArchive(task.versionName); // this file is not closed here, the lolpatcher has to do that
                    for(int i = 0; i < task.files.size(); i++){
                        if(patcher.done || patcher.error != null){
                            break;
                        }
                        ManifestFile file = task.files.get(i);
                        current = file.name;
                        RAFArchive.RafFile raff = archive.dictionary.get(file.path + file.name);
                        
                        if(raff != null){
                            alternative = true;
                            InputStream in = archive.readFile(raff);
                            if(file.fileType == 22){
                                in = new InflaterInputStream(in);
                            }
                            if(checkHash(new BufferedInputStream(in), patcher, file, false)){
                                progress = (float) i / task.files.size();
                                continue;
                            }else{
                                System.out.println("bad file: " + file);
                                archive.fileList.remove(raff);
                                archive.dictionary.remove(file.path + file.name);
                            }
                        }
                        alternative = false;
                        downloadFileToArchive(file, htc, archive);
                        progress = (float) i / task.files.size();
                    }
                    progress = 1;
                    startTime = -1;
                }
            }
        } catch (IOException ex) {
            Logger.getLogger(ArchiveDownloadWorker.class.getName()).log(Level.SEVERE, null, ex);
            if(patcher.error == null){
                patcher.error = ex;
            }
        }
    }
    
    private void downloadFileToArchive(ManifestFile f, MiniHttpClient hc, RAFArchive archive) throws IOException{
        String url = "/releases/"+patcher.branch+"/"+patcher.type+"/"
            + patcher.project + "/releases/" + f.release + "/files/" + 
            f.path.replaceAll(" ", "%20") + f.name.replaceAll(" ", "%20") + (f.fileType > 0 ? ".compressed" : "");
        
        MiniHttpClient.HttpResult hte = hc.get(url);
        InputStream fileStream = hte.in;
        

        try(InputStream in = (f.fileType == 6 ? new InflaterInputStream(fileStream) : fileStream)){
            try(OutputStream os = archive.writeFile(f.path + f.name, f)){
                byte[] buffer = new byte[1024];
                int r;
                while((r = in.read(buffer)) != -1){
                    speedStat(r);
                    if(patcher.done){
                        System.out.println("exited archive purge task");
                        return;
                    }
                    os.write(buffer, 0, r);
                }
            }
        }
    }

}
