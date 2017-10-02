package lolpatcher;

import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.logging.Level;
import java.util.logging.Logger;
import static lolpatcher.StreamUtils.*;
import lolpatcher.manifest.ManifestFile;
import nl.xupwup.Util.FileSliceInputStream;

/**
 *
 * @author Rick
 */
public class RAFArchive implements AutoCloseable{
    File raf;
    File datRaf;
    final RandomAccessFile out;
    boolean changed = false;
    boolean closed = false;
    ArrayList<RafFile> fileList;
    HashMap<String, RafFile> dictionary;
    
    public RAFArchive(String path) throws IOException{
        raf = new File(path);
        datRaf = new File(path + ".dat");
        datRaf.createNewFile();
        fileList = new ArrayList<>();
        out = new RandomAccessFile(datRaf, "rw");
        dictionary = new HashMap<>();
    }
    
    /**
     * 
     * @param f
     * @return whether or not the given file is compressed.
     * @throws java.io.IOException
     */
    public boolean isCompressed(RafFile f) throws IOException{
        try (RandomAccessFile in = new RandomAccessFile(datRaf, "r")) {
            in.seek(f.startindex);
            return in.readByte() == 0x78 && in.readByte() == 0xffffff9c;
        } catch (FileNotFoundException ex) {
            Logger.getLogger(RAFArchive.class.getName()).log(Level.SEVERE, null, ex);
        }
        return false;
    }
    
    public RAFArchive(File raf, File datRaf) throws FileNotFoundException, IOException{
        this.raf = raf;
        this.datRaf = datRaf;
        fileList = new ArrayList<>();
        try (RandomAccessFile in = new RandomAccessFile(raf, "r")) {
            int magicNumber = getInt(in);
            assert(magicNumber == 0x18be0ef0);
            int version = getInt(in);
            //System.out.println("Raf version: " + version);
            int managerIndex = getInt(in);
            //System.out.println("ManagerIndex: " + managerIndex);
            
            int fileListOffset = getInt(in);
            int pathListOffset = getInt(in);
            int nfiles = getInt(in);
            for(int i = 0; i < nfiles; i++){
                int pathHash = getInt(in);
                long offset = getInt(in) & 0x00000000ffffffffL;
                int size = getInt(in);
                int pathlistindex = getInt(in);
                
                RafFile rf = new RafFile(offset, "");
                rf.pathhash = pathHash;
                rf.size = size;
                rf.pathlistindex = pathlistindex;
                
                fileList.add(rf);
            }
            
            long offset = in.getFilePointer();
            int pathListSize = getInt(in);
            int pathListCount = getInt(in);
            for(int i = 0; i < fileList.size(); i++){
                RafFile rf = fileList.get(i);
                in.seek(offset + 8 + rf.pathlistindex * 8);
                int stringOffset = getInt(in);
                int stringLength = getInt(in);
                
                in.seek(stringOffset + offset);
                rf.name = new String(getBytes(in, stringLength-1)); // -1 to clip \0
            }
        }
        dictionary = new HashMap<>();
        long maxindex = 0;
        for(RafFile f : fileList){
            dictionary.put(f.name, f);
            maxindex = Math.max(maxindex, f.startindex + f.size);
        }
        out = new RandomAccessFile(datRaf, "rw");
    }
    
    public class RafFile{
        long startindex; // fits in unsigned int, but not in normal int
        int size = -1;
        String name;
        int pathhash;
        int pathlistindex;
        
        RafFile(long startIndex, String name){
            pathhash = hash(name);
            this.name = name;
            this.startindex = startIndex;
        }

        @Override
        public String toString() {
            return name + " (size: " + size + " startindex: "+startindex + " pathlistindex: "+pathlistindex+")";
        }
    }
    
    /**
     * byte order: least significant first
     * @param in
     * @return
     * @throws IOException 
     */
    private static byte[] getIntBytes(int n){
        byte[] bytes = new byte[4];
        
        for(int i = 0; i < 4; i++){
            bytes[i] = (byte) (n & 0xFF);
            n = n >>> 8;
        }
        return bytes;
    }
    
    /**
     * byte order: least significant first
     * @param in
     * @return
     * @throws IOException 
     */
    private static byte[] getIntBytes(long n){
        byte[] bytes = new byte[4];
        
        for(int i = 0; i < 4; i++){
            bytes[i] = (byte) (n & 0xFF);
            n = n >>> 8;
        }
        return bytes;
    }
    
    /**
     * Writes the .raf file itself
     * @throws java.io.IOException
     */
    @Override
    public void close() throws IOException{
        out.close();
        sync();
        closed = true;
    }
    
    public void sync() throws IOException{
        if(!changed){
            return;
        }
        raf.createNewFile();
        try (OutputStream rafOut = new BufferedOutputStream(new FileOutputStream(raf))){
            rafOut.write(getIntBytes(0x18be0ef0)); // magic number
            rafOut.write(getIntBytes(1)); // raf version

            rafOut.write(getIntBytes(0)); // raf manager index (why zero??)

            rafOut.write(getIntBytes(20)); // File list offset
            
            ArrayList<RafFile> finishedFiles = new ArrayList<>(fileList.size());
            for(RafFile fi : fileList){
                if(fi.size != -1){
                    finishedFiles.add(fi);
                }
            }
            rafOut.write(getIntBytes(20 + 4 + finishedFiles.size() * 16)); // Path list offset

            rafOut.write(getIntBytes(finishedFiles.size())); // count of file entries

            Collections.sort(finishedFiles, new Comparator<RafFile>(){
                @Override
                public int compare(RafFile o1, RafFile o2) {
                    long o1hash = o1.pathhash & 0xffffffff;
                    long o2hash = o2.pathhash & 0xffffffff;
                    if(o1hash > o2hash){
                        return 1;
                    }else if (o1hash < o2hash){
                        return -1;
                    }else{
                        return o1.name.compareToIgnoreCase(o2.name);
                    }
                }
            });
            int pathlistindex = 0;
            for(RafFile f : finishedFiles){
                rafOut.write(getIntBytes(f.pathhash)); // path hash
                rafOut.write(getIntBytes(f.startindex)); // start index
                rafOut.write(getIntBytes(f.size)); // size
                rafOut.write(getIntBytes(pathlistindex++)); // path list index
            }

            int stringSum = 0;
            for(RafFile f : finishedFiles){
                stringSum += f.name.getBytes().length + 1; // include nul byte
            }
            rafOut.write(getIntBytes(stringSum)); // path list size
            rafOut.write(getIntBytes(finishedFiles.size())); // path list count

            int pathOffset = 8 + finishedFiles.size() * 8;
            for(RafFile f : finishedFiles){
                rafOut.write(getIntBytes(pathOffset)); // path offset
                int l = f.name.getBytes().length + 1;
                pathOffset += l;
                rafOut.write(getIntBytes(l)); // path length
            }
            for(RafFile f : finishedFiles){
                rafOut.write(f.name.getBytes());
                rafOut.write(0x00);
            }
            changed = false;
        } catch (FileNotFoundException ex) {
            Logger.getLogger(RAFArchive.class.getName()).log(Level.SEVERE, null, ex);
        }
    }
    
    
    /**
     * Calculates a hash for a given file path. This is the hash that is part of
     * each FileEntry in a .raf file. Note that this is the file path to which
     * RAFUnpacker will unpack the file.
     *
     * @param filePath the file path from which to construct the hash
     * @return the hash that needs to be set in a FileEntry
     * @author ArcadeStorm
     */
    public static int hash(String filePath) {
        long hash = 0;
        long temp;
        for (int i = 0; i < filePath.length(); i++) {
            hash = ((hash << 4) + Character.toLowerCase(filePath.charAt(i))) & 0xffffffff;
            temp = hash & 0xf0000000;
            hash ^= (temp >>> 24);
            hash ^= temp;
        }
        return (int) hash;
    }

    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder();
        try{
            for(RafFile rf : fileList){
                sb.append(rf.name.replace("\0","\\0")).append(" hash=").append(rf.pathhash).append(" -- ").append(isCompressed(rf)).append("\n");
            }
        }catch(IOException e){
            e.printStackTrace();
        }
        return sb.toString();
    }
    
    public InputStream readFile(RafFile selectedFile) throws IOException{
        return new FileSliceInputStream(datRaf, selectedFile.startindex, selectedFile.size);
    }
    
    public InputStream readFile(String path) throws IOException{
        RafFile selectedFile = dictionary.get(path);
        if(selectedFile == null){
            throw new FileNotFoundException("\"" + path +"\" was not found in archive " + raf.getPath());
        }
        
        return readFile(selectedFile);
    }
    
    /**
     * Writes to the .raf.dat file
     * @param path
     * @param mf
     * @return an outputstream for the file with the given path. (buffered)
     * @throws IOException 
     */
    public OutputStream writeFile(String path, ManifestFile mf) throws IOException{
        RafFile rf = new RafFile(out.length(), path);
        rf.pathlistindex = 0; // this is not used in sync, so it does not need to be correct here
        dictionary.put(rf.name, rf);
        fileList.add(rf);
        synchronized(out){
            out.setLength(out.length() + (mf.fileType == 6 ? mf.sizeUncompressed : mf.sizeCompressed));
        }
        return new BufferedOutputStream(new RafFileOutputStream(mf, rf, out));
    }
    
    /**
     * Note that this class sets the size of the corresponding RafFile when it is
     * completely written. Therefore, you can check whether a file was entirely written
     * by looking at its size field.
     */
    private class RafFileOutputStream extends OutputStream{
        private final ManifestFile mf;
        private final RafFile rf;
        private final RandomAccessFile file;
        int count = 0;
        
        public RafFileOutputStream(ManifestFile mf, RafFile rf, RandomAccessFile file){
            this.file = file;
            this.rf = rf;
            this.mf = mf;
        }
        
        @Override
        public void write(int i) throws IOException {
            write(new byte[]{(byte) i});
        }

        @Override
        public void write(byte[] bytes) throws IOException {
            write(bytes, 0, bytes.length);
        }

        @Override
        public void write(byte[] bytes, int off, int len) throws IOException {
            synchronized(file){
                file.seek(rf.startindex + count);
                file.write(bytes, off, len);
                count += len;
            }
            if(count > (mf.fileType == 6 ? mf.sizeUncompressed : mf.sizeCompressed)){
                throw new IOException("Too many bytes written. File length should have been "
                        + mf.sizeCompressed + " but " + count + " bytes written. Last chunk is l="+len + " == "+ new String(Arrays.copyOfRange(bytes, off, len)) + "\n" + mf);
            }
        }

        @Override
        public void close() throws IOException {
            rf.size = count;
            changed = true;
        }
    }

    @Override
    protected void finalize() throws Throwable {
        super.finalize();

        if(!closed){
            throw new IllegalStateException("Raf file was not closed");
        }
    }
}

