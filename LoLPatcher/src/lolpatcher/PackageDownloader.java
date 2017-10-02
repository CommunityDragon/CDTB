package lolpatcher;

import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map.Entry;
import java.util.zip.InflaterOutputStream;
import lolpatcher.manifest.ManifestFile;
import nl.xupwup.Util.MiniHttpClient;

/**
 * 
 * @author Rick
 */
public class PackageDownloader {

    MiniHttpClient hc;
    final HashMap<String, PackageFile> fileMap; // name -> packf
    final HashMap<String, Package> packagefiles; // binname -> filelist
    final String target, project, branch;
    long totalBytes = 0;
    long lastSyncTime;
    
    
    private class Package{
        String name;
        ArrayList<PackageFile> packages = new ArrayList<>();
        ArrayList<OpenFile> openfiles = new ArrayList<>();
        int index = 0;
        
        Package(String name){
            this.name = name;
        }
        PackageFile next(){
            return packages.get(index);
        }
        OpenFile openFile(PackageFile pf, LoLPatcher p) throws IOException{
            OpenFile of = new OpenFile(pf, p);
            openfiles.add(of);
            return of;
        }
        private class OpenFile{
            OutputStream os;
            final PackageFile pf;

            OpenFile(PackageFile pf, LoLPatcher p) throws IOException {
                this.pf = pf;
                int fileType = pf.mf.fileType;
                if(fileType == 6 || fileType == 22){
                    os = p.getArchive(pf.mf.release).writeFile(pf.mf.path + pf.mf.name, pf.mf);
                }else{
                    File targetDir = new File(p.getFileDir(pf.mf));
                    File target = new File(targetDir, pf.mf.name);
                    targetDir.mkdirs();
                    os = new BufferedOutputStream(new FileOutputStream(target));
                }
                if(fileType > 0 && fileType != 22){
                    os = new InflaterOutputStream(os);
                }
            }
        }
    }
    
    private class PackageFile{
        final String name;
        final String binName;
        final long offset;
        final int length;
        final int unknown1;
        ManifestFile mf;

        @Override
        public String toString() {
            return name + ", " + binName + ", " + offset + ", " + length + ", " + unknown1;
        }
        
        public PackageFile(String[] split) {
            name = split[0];
            binName = split[1];
            offset = Long.parseLong(split[2]);
            length = Integer.parseInt(split[3]);
            unknown1 = Integer.parseInt(split[4]);
            if(unknown1 != 0){
                System.out.println("mmh... unknown1 is not 0, it is " + unknown1);
            }
        }
    }
    
    private class Range{
        long min, max;

        public Range(long min, long max) {
            this.min = min;
            this.max = max;
        }

        @Override
        public String toString() {
            return "(" + min + ", " + max + ")";
        }
        
    }
    
    
    HashMap<String, ArrayList<Range>> ranges;
    
    public PackageDownloader(String target, String project, String branch) throws IOException{
        this.target = target;
        this.project = project;
        this.branch = branch;
        ranges = new HashMap<>();
        packagefiles = new HashMap<>();
        hc = new MiniHttpClient("l3cdn.riotgames.com");
        hc.throwExceptionWhenNot200 = true;
        hc.setErrorHandler(new MiniHttpClient.ErrorHandler<Exception>() {
            @Override
            public int handle(Exception t) {
                System.err.println("ioex!!");
                t.printStackTrace();
                return 5000;
            }
        });
        fileMap = new HashMap<>();
        MiniHttpClient.HttpResult get = hc.get("/releases/"+branch+"/projects/" + project + "/releases/"+target + "/packages/files/packagemanifest");
        readManifest(get.in);
    }
    
    private void readManifest(InputStream in) throws IOException{
        try (BufferedReader rd = new BufferedReader(new InputStreamReader(in))) {
            String header = rd.readLine();
            if(!header.equals("PKG1")){
                throw new IOException("Header does not equal PKG1. Actual header is: " + header);
            }
            String line;
            while((line = rd.readLine()) != null){
                String[] sp = line.split(",");
                fileMap.put(sp[0], new PackageFile(sp));
            }
        }
        //System.out.println(fileMap);
    }
    
    private PackageFile getPackageFile(ManifestFile f){
        String u = "/projects/"
                + project + "/releases/" + f.release + "/files/" + 
                f.path + f.name + (f.fileType > 0 ? ".compressed" : "");
        PackageFile pf = fileMap.get(u);
        pf.mf = f;
        return pf;
    }
    
    public void updateRanges(ArrayList<ManifestFile> files) throws IOException{
        files = new ArrayList<>(files);
        Iterator<ManifestFile> it = files.iterator();
        while(it.hasNext()){
            if(getPackageFile(it.next()) == null){
                it.remove();
            }
        }
        
        for(ManifestFile f : files){
            PackageFile pf = getPackageFile(f);
            Package pack = packagefiles.get(pf.binName);
            if(pack == null){
                pack = new Package(pf.binName);
                packagefiles.put(pf.binName, pack);
            }
            pack.packages.add(pf);
        }
        for(Package pack : packagefiles.values()){
            Collections.sort(pack.packages, new Comparator<PackageFile>() {
                @Override
                public int compare(PackageFile o1, PackageFile o2) {
                    return Long.compare(o1.offset, o2.offset);
                }
            });
        }
        for(Entry<String, Package> e : packagefiles.entrySet()){
            ArrayList<Range> rangeList = ranges.get(e.getKey());
            if(rangeList == null){
                rangeList = new ArrayList<>();
                ranges.put(e.getKey(), rangeList);
            }
            for(PackageFile pf : e.getValue().packages){
                Range lastrange = rangeList.isEmpty() ? null : rangeList.get(rangeList.size()-1);
                if(lastrange == null || pf.offset > lastrange.max){
                    lastrange = new Range(pf.offset, pf.offset + pf.length);
                    rangeList.add(lastrange);
                }else{
                    lastrange.max = Math.max(lastrange.max, pf.offset + pf.length);
                }
            }
        }
        
        
        
        totalBytes = 0;
        for(ArrayList<Range> rangeList : ranges.values()){
            for(Range r : rangeList){
                totalBytes += r.max - r.min;
            }
        }
    }

    public ArrayList<ManifestFile> downloadRanges(LoLPatcher p) throws FileNotFoundException, IOException {
        lastSyncTime = System.currentTimeMillis();
        long bytesRead = 0;
        
        for(Entry<String, ArrayList<Range>> e : ranges.entrySet()){
            ArrayList<Range> rangeList = e.getValue();
            for (Range range : rangeList) {
                MiniHttpClient.HttpResult get = hc.get("/releases/"+branch+"/projects/" + project + "/releases/"+target + "/packages/files/"+e.getKey(), range.min, range.max - 1);
                byte[] bytes = new byte[1024];
                int read;
                long offset = range.min;
                while((read = get.in.read(bytes)) != -1){
                    pushBytes(read, offset, bytes, e.getKey(), p);
                    LoLPatcher.speedStat(read);
                    bytesRead += read;
                    offset += read;
                    if(offset > range.max){
                        throw new IOException("More bytes received than expected.");
                    }
                    p.downloadPercentage = 100f * bytesRead / totalBytes;
                    if(p.done) return new ArrayList<>();
                }
                get.in.close();
                Package pack = packagefiles.get(e.getKey());
                for(Package.OpenFile of : pack.openfiles){
                    of.os.close();
                }
                pack.openfiles.clear();
            }
        }
        p.syncAllArchives();
        ArrayList<ManifestFile> finished = new ArrayList<>();
        for(Package pack : packagefiles.values()){
            for(PackageFile pf : pack.packages){
                finished.add(pf.mf);
            }
        }
        return finished;
    }
    
    /**
     * Push the given bytes to all consumers. Such as archives or normal files. (Sends
     * a slice of the given bytes to the appropriate outputstream(s))
     * 
     * This function assumes that the package file never contains two (or more) 
     * overlapping files that belong to the same archive. If overlap does happen
     * within the same archive, patching will silently create invalid data.
     * Overlapping files that belong to another package, or files that are outside 
     * of any package, are supported however.
     * 
     * I believe that packages never contain two overlapping files that belong to the
     * same package. However, this may change in the future, or I may be wrong right now.
     * 
     * @param read  amount of bytes read
     * @param offset  offset in the bin file
     * @param buf  the byte buffer
     * @param binName  the name of the bin file
     * @param p  a reference to the patcher object.
     * @throws IOException 
     */
    private void pushBytes(int read, long offset, byte[] buf, String binName, LoLPatcher p) throws IOException{
        Package pack = packagefiles.get(binName);
        
        long os;
        while(pack.index < pack.packages.size() && (os = pack.next().offset) < offset + read && os >= offset){
            if(pack.next().offset > offset + read){
                System.err.println("WTF omg omg omg");
            }
            pack.openFile(pack.next(), p);
            pack.index++;
        }
        
        for(int i = 0; i < pack.openfiles.size(); i++){
            Package.OpenFile of = pack.openfiles.get(i);
            if(i == 0){
                p.currentFile = of.pf.mf.name;
            }
            int o = Math.max(0, (int) (of.pf.offset - offset));
            int remaining = Math.max(0, (int) ((of.pf.offset + of.pf.length) - offset));
            int l = Math.min(read, remaining) - o;
            
            try{
                of.os.write(buf, o, l);
            }catch(IOException e){
                System.err.println("o="+o + " l="+l + " bufl=" +buf.length + " offset=" +offset + " foffset="+of.pf.offset + " flen=" + of.pf.length + " ofl=" + pack.openfiles.size() + " read=" + read );
                throw e;
            }
            if(remaining + o <= read){
                of.os.close();
                pack.openfiles.remove(i--);
            }
        }
        if(System.currentTimeMillis() - lastSyncTime > 5000){
            p.syncAllArchives();
            lastSyncTime = System.currentTimeMillis();
        }
    }
}
