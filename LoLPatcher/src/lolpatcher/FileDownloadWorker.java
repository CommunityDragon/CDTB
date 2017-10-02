package lolpatcher;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.MalformedURLException;
import java.security.NoSuchAlgorithmException;
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
public class FileDownloadWorker extends Worker{
    LoLPatcher patcher;

    public FileDownloadWorker(LoLPatcher lp) {
        patcher = lp;
        setName("File downloader");
    }
    
    @Override
    public void run() {
        try {
            try (MiniHttpClient htc = new MiniHttpClient("l3cdn.riotgames.com")) {
                htc.throwExceptionWhenNot200 = true;
                htc.setErrorHandler(defaultHttpErrorHandler);
                
                ManifestFile task;
                while(true){
                    synchronized(patcher.filesToPatch){
                        if(patcher.filesToPatch.isEmpty() || patcher.done || patcher.error != null){
                            break;
                        }
                        task = patcher.filesToPatch.remove(0);
                    }
                    startTime = System.currentTimeMillis();
                    current = task.name;
                    downloadFile(task, htc);
                    startTime = -1;
                }
            }

        } catch (IOException | NoSuchAlgorithmException ex) {
            Logger.getLogger(FileDownloadWorker.class.getName()).log(Level.SEVERE, null, ex);
            if(patcher.error == null){
                patcher.error = ex;
            }
        }
    }
    
    
    private void downloadFile(ManifestFile f, MiniHttpClient hc) throws MalformedURLException, IOException, NoSuchAlgorithmException{
        progress = 0;
        alternative = false;
        java.io.File targetDir = new java.io.File(patcher.getFileDir(f));
        java.io.File target = new java.io.File(targetDir.getPath() + "/" + f.name);
        targetDir.mkdirs();
        
        if(!target.createNewFile() && (patcher.force || patcher.forceSingleFiles)){
            alternative = true;
            if(checkHash(new BufferedInputStream(new FileInputStream(target)), patcher, f)){
                return;
            }
        }
        progress = 0;
        
        String url = "/releases/"+patcher.branch+"/"+patcher.type+"/"
            + patcher.project + "/releases/" + f.release + "/files/" + 
            f.path.replaceAll(" ", "%20") + f.name.replaceAll(" ", "%20") + (f.fileType > 0 ? ".compressed" : "");

        MiniHttpClient.HttpResult hte = hc.get(url);
        InputStream fileStream = hte.in;
        long total = 0;
        
        try(InputStream in = (
                f.fileType > 0 ? 
                    new InflaterInputStream(fileStream) :
                    fileStream)){
            
            try(OutputStream fo = new BufferedOutputStream(new FileOutputStream(target))){
                int read;
                byte[] buffer = new byte[4096];
                while((read = in.read(buffer)) != -1){
                    fo.write(buffer, 0, read);
                    speedStat(read);
                    total += read;
                    progress = (float) total / f.sizeCompressed;
                    if(patcher.done) return;
                }
            }
        }
        progress = 1;
    }
}
