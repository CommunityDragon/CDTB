package lolpatcher;

import java.io.File;
import java.io.FilenameFilter;
import java.io.IOException;
import java.net.MalformedURLException;
import java.security.NoSuchAlgorithmException;

/**
 *
 * @author Rick
 */
public class SLNPatcher extends CopyTask{
    boolean force;
    String slnversion;
    
    public SLNPatcher(String gameversion, String slnversion, boolean force) {
        super(new File("RADS/projects/lol_game_client/releases/"+gameversion+"/deploy/"), 
              new File("RADS/solutions/lol_game_client_sln/releases/"+slnversion+"/deploy/"), true);
        this.slnversion = slnversion;
        this.force = force;
    }

    @Override
    public void patch() throws MalformedURLException, IOException, NoSuchAlgorithmException {
        File solutionsDirectory = new File("RADS/solutions/lol_game_client_sln/releases/");
        
        String[] directories = solutionsDirectory.list(new FilenameFilter() {
            @Override
            public boolean accept(File dir, String name) {
                return name.matches("([0-9]+\\.){3}[0-9]+");
            }
        });
        if(directories.length > 1){
            for(String d : directories){
                if(!d.equals(slnversion)){
                    LoLPatcher.deleteDir(new File(solutionsDirectory, d));
                }
            }
        }
        if(to.exists() && new File(to.getParent(), "S_OK").exists() && !force){
            percentage = 100;
            done = true;
            return;
        }
        super.patch();
        new File(to.getParent(), "S_OK").createNewFile();
    }
}
