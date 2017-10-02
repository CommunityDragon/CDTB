package lolpatcher;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.MalformedURLException;
import java.security.NoSuchAlgorithmException;

/**
 *
 * @author Rick
 */
public class CopyTask extends PatchTask {

    File from;
    File to;
    boolean merge;
    float percentage = 0;
    
    public CopyTask(File from, File to){
        this(from, to, true);
    }
    
    public CopyTask(File from, File to, boolean merge){
        this.from = from;
        this.to = to;
        this.merge = merge;
    }
    
    public void copy(File f, File dir) throws FileNotFoundException, IOException{
        File f2 = new File(dir, f.getName());
        if(f.isDirectory()){
            f2.mkdir();
            String[] files = f.list();
            for(String s : files){
                currentFile = s;
                copy(new File(f, s), new File(dir, f.getName()));
            }
            return;
        }
        
        f2.createNewFile();
        try (InputStream is = new BufferedInputStream(new FileInputStream(f))) {
            int read;
            byte[] buffer = new byte[4096];

            try(OutputStream os = new BufferedOutputStream(new FileOutputStream(f2))){
                while((read = is.read(buffer)) != -1){
                    os.write(buffer, 0, read);
                    if(done) return;
                    speedStat(read);
                }
            }
        }
    }
    
    
    @Override
    public void patch() throws MalformedURLException, IOException, NoSuchAlgorithmException {
        to.mkdirs();
        
        merge &= from.isDirectory();
        
        percentage = 0;
        if(!merge){
            copy(from, to);
        }else{
            String[] files = from.list();
            for(String s : files){
                currentFile = s;
                copy(new File(from, s), to);
            }
        }
        percentage = 100;
        done = true;
    }
    
    @Override
    public float getPercentage() {
        return percentage;
    }
}
