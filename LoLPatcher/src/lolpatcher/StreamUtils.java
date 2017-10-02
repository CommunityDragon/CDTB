package lolpatcher;

import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;

/**
 *
 * @author Rick
 */
public class StreamUtils {
    /**
     * get a 4 byte int
     * byte order: least significant first
     * @param in
     * @return
     * @throws IOException 
     */
    public static int getInt(InputStream in) throws IOException{
        byte[] bytes = getBytes(in, 4);
        int ret = 0;
        for(int i = 3; i >= 0; i--){
            ret = ret << 8 | (bytes[i] & 0xFF);
        }
        return ret;
    }
    /**
     * get a 4 byte int
     * byte order: least significant first
     * @param in
     * @return
     * @throws IOException 
     */
    public static int getInt(RandomAccessFile in) throws IOException{
        byte[] bytes = getBytes(in, 4);
        int ret = 0;
        for(int i = 3; i >= 0; i--){
            ret = ret << 8 | (bytes[i] & 0xFF);
        }
        return ret;
    }
    
    public static byte[] getBytes(InputStream in, int count) throws IOException{
        byte[] bytes = new byte[count];
        int read = 0;
        while(read < count){
            int rd = in.read(bytes, read, count - read);
            if (rd == -1){
                throw new IOException("Stream ended.");
            }
            read += rd;
        }
        return bytes;
    }
    
    public static byte[] getBytes(RandomAccessFile in, int count) throws IOException{
        byte[] bytes = new byte[count];
        int read = 0;
        while(read < count){
            int rd = in.read(bytes, read, count - read);
            if (rd == -1){
                throw new IOException("Stream ended.");
            }
            read += rd;
        }
        return bytes;
    }
}
