package lolpatcher;

import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.MalformedURLException;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import static lolpatcher.Main.patcherVersion;
import nl.xupwup.Util.MiniHttpClient;

/**
 *
 * @author Rick
 */
public class SelfUpdateTask extends PatchTask{
    float percentage = 0;
    
    @Override
    public void patch() throws MalformedURLException, IOException, NoSuchAlgorithmException {
        currentFile = "Checking for updates";
        ArrayList<String> response;
        try (MiniHttpClient hc = new MiniHttpClient("lolpatcher.xupwup.nl")) {
            MiniHttpClient.HttpResult versionRequest = hc.get("/version2");
            response = new ArrayList<>();
            try (BufferedReader in = new BufferedReader(new InputStreamReader(versionRequest.in))) {
                String inputLine;
                while ((inputLine = in.readLine()) != null){
                    response.add(inputLine);
                }
            }
            int version = Integer.parseInt(response.get(0).trim());
            System.out.println("Server has patcher version " + version);
            if(version <= patcherVersion){
                percentage = 100;
                done = true;
                return;
            }
            for(int i = 1; i < response.size(); i++){
                MiniHttpClient.HttpResult get = hc.get("/data/"+response.get(i));
                String filename = response.get(i);
                currentFile = filename;
                try (OutputStream fw = new BufferedOutputStream(new FileOutputStream(filename + ".new"))) {
                    int read;
                    byte[] buffer = new byte[1024];
                    while((read = get.in.read(buffer)) != -1){
                        fw.write(buffer, 0, read);
                    }
                }
                percentage = 100f * i / response.size();
            }
            try (BufferedWriter bw = new BufferedWriter(new FileWriter("patchList.txt"))) {
                for(int i = 1; i < response.size(); i++){
                    bw.write(response.get(i) + "\n");
                }
            }
        }catch(IOException e){
            percentage = 100;
            done = true;
            return;
        }
        
        System.exit(0);
    }

    @Override
    public float getPercentage() {
        return percentage;
    }
    
}
