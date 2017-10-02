package lolpatcher.manifest;

import java.io.BufferedInputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.URLConnection;
import java.util.HashMap;
import static lolpatcher.StreamUtils.*;


public class ReleaseManifest {
    int magicHeaderInt;
    int filetype;
    int itemCount;
    int version;
    int releaseVersion;
    String releaseName;
    
    public Directory[] directories;
    public ManifestFile[] files;
    private final HashMap<String, ManifestFile> fileDictionary;
    
    
    
    public class Directory{
        public Directory[] subdirs;
        public ManifestFile[] files;
        public String name;
        public String path;
        public Directory(String name){
            this.name = name;
            this.path = name.length() == 0 ? ""  : name + "/";
        }
    }
    
    
    
    
    
    private class DirectoryMetaData{
        public DirectoryMetaData(int nameindex, int subdirFirstIndex, int nsubdirs, int firstfileIndex, int fileCount) {
            this.nameindex = nameindex;
            this.subdirFirstIndex = subdirFirstIndex;
            this.nsubdirs = nsubdirs;
            this.firstfileIndex = firstfileIndex;
            this.fileCount = fileCount;
        }
        
        int nameindex;
        int subdirFirstIndex;
        int nsubdirs;
        int firstfileIndex;
        int fileCount;
    }
    
    public class FileMetaData{

        public FileMetaData(int nameindex, int release, byte[] checksum, int fileType, int sizeUncompressed, int size, int unknownInt3, int unknownInt4) {
            this.nameindex = nameindex;
            this.release = release;
            this.checksum = checksum;
            this.fileType = fileType;
            this.sizeUncompressed = sizeUncompressed;
            this.sizeCompressed = size;
            this.unknownInt3 = unknownInt3;
            this.unknownInt4 = unknownInt4;
        }
        
        int nameindex;
        int release;
        byte[] checksum;
        /**
         * Type
         * 5 = managed file
         */
        int fileType;
        int sizeCompressed; // size compressed. No idea what this means if a file is not supposed to be compressed
        int sizeUncompressed; // the size of a file when its not compressed
        int unknownInt3;
        int unknownInt4;
    }
    
    
    public ManifestFile getFile(String path){
        return fileDictionary.get(path);
    }
    
    public static String getReleaseName(int rel){
        String s = "" + (rel & 255);
        rel = rel >> 8;
        s = (rel & 255) + "." + s;
        rel = rel >> 8;
        s = (rel & 255) + "." + s;
        rel = rel >> 8;
        s = (rel & 255) + "." + s;
        return s;
    }
    
    public static int getReleaseInt(String rel){
        String[] st = rel.split("\\.");
        int r = 0;
        for(int i = 0; i < st.length; i++){
            int s = Integer.parseInt(st[i]);
            r = r << 8 | s;
        }
        return r;
    }
    
    public static ReleaseManifest getReleaseManifest(String component, String version, String branch, String type) throws IOException{
        URL u = new URL("http://l3cdn.riotgames.com/releases/"+branch+"/"+type+"/"+component+"/releases/"+version+"/releasemanifest");
        URLConnection con = u.openConnection();
        java.io.File f = new java.io.File("RADS/"+type + "/" + component + "/releases/" + version + "/releasemanifest");
        new java.io.File(f.getParent()).mkdirs();
        f.createNewFile();
        
        try (InputStream in = con.getInputStream()) {
            try (OutputStream fo = new FileOutputStream(f)) {
                int read;
                byte[] buffer = new byte[2048];
                while((read = in.read(buffer)) != -1){
                    fo.write(buffer, 0, read);
                }
            }
        }
        return new ReleaseManifest(f);
    }
    
    /**
     * 
     * @param f
     * @throws java.io.IOException
     */
    public ReleaseManifest(java.io.File f) throws IOException{
        try (InputStream data = new BufferedInputStream(new FileInputStream(f))) {
            magicHeaderInt = getInt(data);
            filetype = getInt(data);
            itemCount = getInt(data);
            
            releaseVersion = getInt(data);
            releaseName = getReleaseName(releaseVersion);
            
            
            DirectoryMetaData[] directoryMetaDatas = new DirectoryMetaData[getInt(data)];
            
            for(int i = 0; i < directoryMetaDatas.length; i++){
                directoryMetaDatas[i] = new DirectoryMetaData(getInt(data),
                        getInt(data),
                        getInt(data),
                        getInt(data),
                        getInt(data));
            }
            
            FileMetaData[] fileMetaDatas = new FileMetaData[getInt(data)];
            for(int i = 0; i < fileMetaDatas.length; i++){
                fileMetaDatas[i] = new FileMetaData(getInt(data),
                        getInt(data), 
                        getBytes(data, 16), 
                        getInt(data), 
                        getInt(data), 
                        getInt(data), 
                        getInt(data), 
                        getInt(data));
            }
            String[] strs = new String[getInt(data)];
            int datasize = getInt(data); // ignored
            
            int c;
            int idx = 0;
            StringBuilder sb = new StringBuilder();
            while((c = data.read()) != -1){
                if(c == '\0'){
                    strs[idx] = sb.toString();
                    sb = new StringBuilder();
                    idx++;
                    continue;
                }
                sb.append((char) c);
            }
            //assert(component.equals(strs[strs.length - 1]));
            
            // creating proper objects
            directories = new Directory[directoryMetaDatas.length];
            for(int i = 0; i < directoryMetaDatas.length; i++){
                directories[i] = new Directory(strs[directoryMetaDatas[i].nameindex]);
            }
            // linking subdirectories
            for(int i = 0; i < directoryMetaDatas.length; i++){
                int start = directoryMetaDatas[i].subdirFirstIndex;
                if(start == i) start ++;
                directories[i].subdirs = new Directory[directoryMetaDatas[i].nsubdirs];
                
                for(int j = 0; j < directoryMetaDatas[i].nsubdirs; j++){
                    directories[i].subdirs[j] = directories[start + j];
                    directories[start + j].path = directories[i].path + directories[start + j].path;
                }
            }
            files = new ManifestFile[fileMetaDatas.length];
            for(int i = 0; i < fileMetaDatas.length; i++){
                FileMetaData meta = fileMetaDatas[i];
                files[i] = new ManifestFile(getReleaseName(meta.release),
                        meta.release,
                        strs[meta.nameindex],
                        meta.checksum, meta.sizeCompressed,
                        meta.fileType, meta.sizeUncompressed,
                        meta.unknownInt3, meta.unknownInt4);
            }
            // linking files to directories
            for(int i = 0; i < directoryMetaDatas.length; i++){
                int start = directoryMetaDatas[i].firstfileIndex;
                directories[i].files = new ManifestFile[directoryMetaDatas[i].fileCount];
                
                for(int j = 0; j < directoryMetaDatas[i].fileCount; j++){
                    directories[i].files[j] = files[start + j];
                    files[start + j].path = directories[i].path;
                }
            }
            fileDictionary = new HashMap<>(files.length);
            for(ManifestFile fi : files){
                fileDictionary.put(fi.path + fi.name, fi);
            }
        }
    }

    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder();
        for(ManifestFile f : files){
            sb.append(f.path).append(f.name).append(" type:").append(f.fileType).append(" ").append(f.release).append("\n");
        }
        return sb.toString();
    }
}
